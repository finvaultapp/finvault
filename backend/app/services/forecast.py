"""Cash-flow forecast: projected balances for the next 30, 60 and 90 days.

The projection for each account is

    balance(day n) = balance today
                     + sum of active recurring items (bills and income) dated in (today, day n]
                     - n * baseline daily spend

The baseline is everyday discretionary spending: the median of the last 13 weekly
totals (91 days, ending yesterday) divided by 7. Weekly buckets are used so days with
no purchases don't pull the median to $0, while one big purchase can't inflate it.
Left out of the baseline: transfer-kind categories, matched transfers, income,
transactions posted by a recurring item and any category a recurring item already
covers, so bills are not counted twice. Splits and shared costs are respected through
reports.effective_lines. It is an estimate, and the API says so.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account, Category, Recurring, Transaction, User
from ..models_plan import PlanPrefs
from . import recurring as rec
from .currency import Converter
from .ledger import account_balances
from .reports import effective_lines, f2

HORIZONS = (30, 60, 90)
BASELINE_WEEKS = 13


def occurrences_between(r: Recurring, after: date, until: date) -> list[date]:
    """Dates of a recurring item in (after, until]. Stale next_dates are walked forward."""
    out, d, guard = [], r.next_date, 0
    while d <= until and guard < 2000 and (r.end_date is None or d <= r.end_date):
        if d > after:
            out.append(d)
        d = rec.advance(d, r.frequency, r.anchor_day)
        guard += 1
    return out


def weekly_baseline(daily: dict[date, Decimal], end: date, first_seen: date | None,
                    weeks: int = BASELINE_WEEKS) -> Decimal:
    """Median of weekly spend totals ending on `end`, divided by 7. Weeks before any history are skipped."""
    totals = []
    for w in range(weeks):
        stop = end - timedelta(days=7 * w)
        start = stop - timedelta(days=6)
        if first_seen is None or stop < first_seen:
            continue
        totals.append(max(Decimal(0), sum((daily.get(start + timedelta(days=i), Decimal(0)) for i in range(7)), Decimal(0))))
    if not totals:
        return Decimal(0)
    return Decimal(median(totals)) / 7


def project(balance: Decimal, daily_spend: Decimal, events: list[tuple[date, Decimal]], today: date,
            days: int) -> list[Decimal]:
    """Balance at the end of each day for days 1..days. `events` are (date, signed amount)."""
    by_day: dict[date, Decimal] = defaultdict(Decimal)
    for d, amt in events:
        by_day[d] += amt
    out, b = [], Decimal(balance)
    for n in range(1, days + 1):
        d = today + timedelta(days=n)
        b = b - daily_spend + by_day.get(d, Decimal(0))
        out.append(b)
    return out


def first_shortfall(balances: list[Decimal], events: list[dict], today: date, cushion: Decimal) -> dict | None:
    """First day the balance drops below the cushion, plus the bill it lands before (or on)."""
    for n, b in enumerate(balances, start=1):
        if b < cushion:
            d = today + timedelta(days=n)
            bill = next((e for e in events if e["amount"] < 0 and e["date"] >= d.isoformat()), None)
            return {"date": d.isoformat(), "balance": f2(b), "bill": bill}
    return None


def _baseline_for(db: Session, user: User, account: Account, excluded: set[int], kinds: dict, today: date,
                  skip: dict[date, Decimal]) -> tuple[Decimal, dict]:
    end = today - timedelta(days=1)
    start = end - timedelta(days=7 * BASELINE_WEEKS - 1)
    daily: dict[date, Decimal] = defaultdict(Decimal)
    for d, amount, cat_id, _cur, kind in effective_lines(db, user, start, end, [account.id]):
        if kind in ("transfer", "income") or cat_id in excluded:
            continue
        if kind is None and amount > 0:
            continue  # uncategorized money in is not a refund of spending
        daily[d] -= Decimal(amount)  # spending positive, refunds negative
    for d, amt in skip.items():
        daily[d] -= amt
    first = db.scalar(select(Transaction.date).where(Transaction.account_id == account.id)
                      .order_by(Transaction.date).limit(1))
    if account.opening_date and (first is None or account.opening_date < first):
        first = account.opening_date
    base = weekly_baseline(daily, end, first)
    return base, {"window_start": start.isoformat(), "window_end": end.isoformat()}


def forecast(db: Session, user: User, days: int = 90, today: date | None = None) -> dict:
    today = today or date.today()
    days = max(1, min(days, 365))
    until = today + timedelta(days=days)
    prefs = db.get(PlanPrefs, user.id)
    cushion = Decimal(prefs.cushion) if prefs and prefs.cushion is not None else Decimal(0)
    conv = Converter(db, user.base_currency)
    accounts = list(db.scalars(select(Account).where(Account.user_id == user.id, Account.is_archived.is_(False))
                               .order_by(Account.id)))
    balances = account_balances(db, user.id, today)
    items = list(db.scalars(select(Recurring).where(Recurring.user_id == user.id, Recurring.is_active.is_(True))))
    kinds = dict(db.execute(select(Category.id, Category.kind).where(Category.user_id == user.id)).all())
    excluded = {r.category_id for r in items if r.category_id is not None}

    # Transactions the baseline must not see even when their category is fine: recurring postings and matched transfers.
    window_start = today - timedelta(days=7 * BASELINE_WEEKS)
    skip: dict[int, dict[date, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for t in db.execute(select(Transaction.account_id, Transaction.date, Transaction.amount, Transaction.category_id)
                        .where(Transaction.user_id == user.id, Transaction.date >= window_start, Transaction.date < today,
                               (Transaction.recurring_id.is_not(None)) | (Transaction.transfer_id.is_not(None)))):
        if t.category_id in excluded or kinds.get(t.category_id) in ("transfer", "income"):
            continue  # already left out by category
        if kinds.get(t.category_id) is None and t.amount > 0:
            continue
        skip[t.account_id][t.date] -= Decimal(t.amount)

    series = [{"date": (today + timedelta(days=n)).isoformat(), "total": Decimal(0)} for n in range(0, days + 1)]
    out_accounts, upcoming, warnings = [], [], []
    for a in accounts:
        events = []
        for r in items:
            if r.account_id != a.id:
                continue
            for d in occurrences_between(r, today, until):
                events.append({"date": d.isoformat(), "name": r.name, "amount": Decimal(r.amount), "recurring_id": r.id})
        events.sort(key=lambda e: (e["date"], e["amount"]))
        daily_spend, window = _baseline_for(db, user, a, excluded, kinds, today, skip.get(a.id, {}))
        start = Decimal(balances.get(a.id, Decimal(0)))
        proj = project(start, daily_spend, [(date.fromisoformat(e["date"]), e["amount"]) for e in events], today, days)
        points = [start] + proj
        low_i = min(range(len(points)), key=lambda i: points[i])
        rate = conv.rate(a.currency, today)
        for i, p in enumerate(points):
            series[i][f"a{a.id}"] = f2(p)
            if rate is not None:
                series[i]["total"] += p * rate
        running = {(today + timedelta(days=n)).isoformat(): points[n] for n in range(len(points))}
        for e in events:
            upcoming.append({**e, "amount": f2(e["amount"]), "account_id": a.id, "account_name": a.name,
                             "currency": a.currency, "balance_after": f2(running[e["date"]]),
                             "below_cushion": a.type == "checking" and running[e["date"]] < cushion})
        warning = None
        if a.type == "checking":
            if start < cushion:
                warning = {"code": "already_below", "date": today.isoformat(), "balance": f2(start),
                           "bill": next(({**e, "amount": f2(e["amount"])} for e in events if e["amount"] < 0), None)}
            else:
                sf = first_shortfall(proj, events, today, cushion)
                if sf:
                    warning = {"code": "below_cushion", **sf,
                               "bill": {**sf["bill"], "amount": f2(sf["bill"]["amount"])} if sf["bill"] else None}
            if warning and not warning["bill"]:
                warning = None  # the warning is about being short for a bill; no bill ahead, nothing to warn about
            if warning:
                warning.update({"account_id": a.id, "account_name": a.name, "currency": a.currency, "cushion": f2(cushion)})
                warnings.append(warning)
        out_accounts.append({
            "id": a.id, "name": a.name, "type": a.type, "currency": a.currency, "balance": f2(start),
            "daily_spend": f2(daily_spend), "baseline_window": window, "converted": rate is not None,
            "horizons": {str(h): f2(points[h]) for h in HORIZONS if h <= days},
            "lowest": {"date": (today + timedelta(days=low_i)).isoformat(), "balance": f2(points[low_i])},
            "warning": warning,
        })

    totals = [s["total"] for s in series]
    low_i = min(range(len(totals)), key=lambda i: totals[i]) if totals else 0
    for s in series:
        s["total"] = f2(s["total"])
    upcoming.sort(key=lambda u: (u["date"], u["amount"]))
    return {
        "currency": user.base_currency, "today": today.isoformat(), "days": days, "cushion": f2(cushion),
        "accounts": out_accounts, "series": series, "upcoming": upcoming, "warnings": warnings,
        "total": {"balance": series[0]["total"] if series else 0,
                  "horizons": {str(h): series[h]["total"] for h in HORIZONS if h <= days},
                  "lowest": {"date": series[low_i]["date"], "balance": series[low_i]["total"]} if series else None,
                  "daily_spend": f2(sum((Decimal(str(a["daily_spend"])) * (conv.rate(a["currency"], today) or 0)
                                         for a in out_accounts), Decimal(0)))},
        "rate_warnings": conv.warnings(),
        "estimate": True,
    }


def set_cushion(db: Session, user: User, cushion: Decimal) -> None:
    prefs = db.get(PlanPrefs, user.id)
    if prefs is None:
        prefs = PlanPrefs(user_id=user.id, cushion=cushion)
        db.add(prefs)
    else:
        prefs.cushion = cushion
    db.commit()
