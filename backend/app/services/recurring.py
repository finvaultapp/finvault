"""Recurring transactions: scheduling, auto-posting and detection from history."""
import calendar
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..importers import normalize_merchant
from ..models import Recurring, Transaction

FREQUENCIES = {"weekly", "biweekly", "monthly", "quarterly", "yearly"}


def _add_months(d: date, months: int, anchor: int | None) -> date:
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    day = min(anchor or d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def advance(d: date, frequency: str, anchor: int | None = None) -> date:
    if frequency == "weekly":
        return d + timedelta(days=7)
    if frequency == "biweekly":
        return d + timedelta(days=14)
    if frequency == "quarterly":
        return _add_months(d, 3, anchor)
    if frequency == "yearly":
        return _add_months(d, 12, anchor)
    return _add_months(d, 1, anchor)


def occurrences(r: Recurring, until: date, limit: int = 60) -> list[date]:
    out, d = [], r.next_date
    while d <= until and len(out) < limit and (r.end_date is None or d <= r.end_date):
        out.append(d)
        d = advance(d, r.frequency, r.anchor_day)
    return out


def post_due(db: Session, user_id: int | None = None, today: date | None = None) -> int:
    """Create transactions for auto-post items that are due. Safe to call repeatedly."""
    today = today or date.today()
    q = select(Recurring).where(Recurring.is_active.is_(True), Recurring.auto_post.is_(True),
                                Recurring.next_date <= today)
    if user_id is not None:
        q = q.where(Recurring.user_id == user_id)
    created = 0
    for r in db.scalars(q):
        for d in occurrences(r, today):
            db.add(Transaction(user_id=r.user_id, account_id=r.account_id, date=d, amount=r.amount,
                               description=r.name, payee=r.name, category_id=r.category_id, recurring_id=r.id))
            created += 1
            r.next_date = advance(d, r.frequency, r.anchor_day)
        if r.end_date and r.next_date > r.end_date:
            r.is_active = False
    db.commit()
    return created


def detect(db: Session, user_id: int, existing_names: set[str]) -> list[dict]:
    """Suggest recurring items: same merchant, 3+ times, steady interval, similar amount."""
    since = date.today() - timedelta(days=400)
    rows = db.execute(select(Transaction.date, Transaction.amount, Transaction.description, Transaction.account_id,
                             Transaction.category_id)
                      .where(Transaction.user_id == user_id, Transaction.date >= since,
                             Transaction.recurring_id.is_(None))
                      .order_by(Transaction.date)).all()
    groups: dict[str, list] = defaultdict(list)
    for row in rows:
        key = normalize_merchant(row.description)
        if key:
            groups[key].append(row)
    suggestions = []
    for key, items in groups.items():
        if len(items) < 3 or key.lower() in existing_names:
            continue
        gaps = [(b.date - a.date).days for a, b in zip(items, items[1:])]
        g = median(gaps)
        freq = ("weekly" if 6 <= g <= 8 else "biweekly" if 13 <= g <= 16 else "monthly" if 27 <= g <= 33
                else "quarterly" if 85 <= g <= 95 else "yearly" if 355 <= g <= 375 else None)
        if not freq:
            continue
        spread = sum(1 for x in gaps if abs(x - g) <= max(3, g * 0.15)) / len(gaps)
        amounts = [Decimal(i.amount) for i in items]
        typical = Decimal(median(amounts))
        similar = sum(1 for a in amounts if abs(a - typical) <= abs(typical) * Decimal("0.2")) / len(amounts)
        if spread < 0.7 or similar < 0.7:
            continue
        last = items[-1]
        nxt = advance(last.date, freq, last.date.day)
        if nxt < date.today() - timedelta(days=g):
            continue  # stopped a while ago
        suggestions.append({
            "name": last.description[:120], "amount": float(round(typical, 2)), "frequency": freq,
            "next_date": nxt.isoformat(), "account_id": last.account_id, "category_id": last.category_id,
            "occurrences": len(items),
        })
    suggestions.sort(key=lambda s: -abs(s["amount"]))
    return suggestions[:20]
