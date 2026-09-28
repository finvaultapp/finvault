"""Price-change and new-subscription alerts, built on recurring detection and transaction history.

(a) Price change: a recurring charge (a saved recurring item or one the detector suggests) whose
    latest amount differs from its usual amount (median of the earlier charges, or the saved
    amount when there is no earlier history) by more than max($1, 5% of the usual amount).
    Charges whose amount already varies (fewer than 75% of earlier charges within that band of
    the usual amount, like fuel or hydro) are skipped, and so is a latest charge that matches
    the one before it (the change was flagged then).
(b) New subscription: a merchant with 2+ charges in the last 90 days, spaced like a monthly bill
    (every gap 24 to 38 days, amounts within 20% of each other), and no charge before 90 days ago.

Alerts are stored once per key, so a dismissed alert stays dismissed. Members with ntfy or email
reminders get each new alert once.
"""
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..importers import normalize_merchant
from ..models import Account, Category, Recurring, Transaction, User
from ..models_plan import ChargeAlert
from . import notify
from . import recurring as rec
from .reports import f2

log = logging.getLogger("finvault.alerts")

NEW_WINDOW_DAYS = 90
HISTORY_DAYS = 400
PERIOD_DAYS = {"weekly": 7, "biweekly": 14, "monthly": 30, "quarterly": 91, "yearly": 365}


def threshold(usual: Decimal) -> Decimal:
    return max(Decimal(1), abs(Decimal(usual)) * Decimal("0.05"))


def price_changed(usual: Decimal, latest: Decimal) -> bool:
    return abs(abs(Decimal(latest)) - abs(Decimal(usual))) > threshold(usual)


def looks_monthly(dates: list[date], amounts: list[Decimal]) -> bool:
    if len(dates) < 2:
        return False
    gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
    if not all(24 <= g <= 38 for g in gaps):
        return False
    typical = Decimal(median(amounts))
    return all(abs(a - typical) <= abs(typical) * Decimal("0.2") for a in amounts)


def _history(db: Session, user_id: int, today: date) -> dict[tuple[int, str], list]:
    """Charges (money out) of the last 400 days grouped by (account, merchant key)."""
    transfer_cats = set(db.scalars(select(Category.id).where(Category.user_id == user_id,
                                                           Category.kind.in_(("transfer", "income")))))
    rows = db.execute(select(Transaction.id, Transaction.date, Transaction.amount, Transaction.description,
                             Transaction.account_id, Transaction.category_id, Transaction.recurring_id,
                             Transaction.transfer_id)
                      .where(Transaction.user_id == user_id, Transaction.date >= today - timedelta(days=HISTORY_DAYS),
                             Transaction.date <= today, Transaction.amount < 0)
                      .order_by(Transaction.date, Transaction.id)).all()
    groups: dict[tuple[int, str], list] = defaultdict(list)
    for r in rows:
        if r.transfer_id is not None or r.category_id in transfer_cats:
            continue
        key = normalize_merchant(r.description)
        if key:
            groups[(r.account_id, key)].append(r)
    return groups


def detect(db: Session, user: User, today: date | None = None) -> list[dict]:
    today = today or date.today()
    groups = _history(db, user.id, today)
    items = list(db.scalars(select(Recurring).where(Recurring.user_id == user.id)))
    known_keys = {normalize_merchant(r.name) for r in items} | {r.name.upper() for r in items}
    found: list[dict] = []

    def price_check(name, account_id, charges, usual_fallback, recurring_id, freq):
        if not charges:
            return
        latest = charges[-1]
        period = PERIOD_DAYS.get(freq, 30)
        if latest.date < today - timedelta(days=max(40, int(period * 1.5))):
            return  # the latest charge is old news
        earlier = [Decimal(c.amount) for c in charges[:-1]][-12:]
        if earlier and not price_changed(earlier[-1], Decimal(latest.amount)):
            return  # same as last time: either nothing changed or the change was already flagged then
        usual = Decimal(median(earlier)) if earlier else usual_fallback
        if len(earlier) >= 2 and sum(1 for a in earlier if not price_changed(usual, a)) < len(earlier) * 0.75:
            return  # the amount varies anyway (fuel, hydro): a different number isn't news
        if usual is None or usual == 0 or not price_changed(usual, Decimal(latest.amount)):
            return
        found.append({"kind": "price_change", "key": f"price:{account_id}:{normalize_merchant(name)}:{latest.id}",
                      "name": name, "account_id": account_id, "recurring_id": recurring_id,
                      "usual_amount": usual, "amount": Decimal(latest.amount), "last_date": latest.date,
                      "hits": len(charges)})

    # (a) saved recurring charges: their postings plus imported lines from the same merchant.
    by_recurring: dict[int, list] = defaultdict(list)
    for (aid, key), charges in groups.items():
        for c in charges:
            if c.recurring_id:
                by_recurring[c.recurring_id].append(c)
    seen_groups = set()
    for r in items:
        if not r.is_active or r.amount >= 0:
            continue
        key = normalize_merchant(r.name)
        merged = {c.id: c for c in by_recurring.get(r.id, [])}
        for c in groups.get((r.account_id, key), []):
            merged[c.id] = c
        seen_groups.add((r.account_id, key))
        charges = sorted(merged.values(), key=lambda c: (c.date, c.id))
        price_check(r.name, r.account_id, charges, Decimal(r.amount), r.id, r.frequency)

    # (a) charges the existing detector says are recurring, but not saved yet.
    for s in rec.detect(db, user.id, {k.lower() for k in known_keys}):
        if s["amount"] >= 0:
            continue
        gk = (s["account_id"], normalize_merchant(s["name"]))
        if gk in seen_groups:
            continue
        seen_groups.add(gk)
        price_check(s["name"], s["account_id"], groups.get(gk, []), None, None, s["frequency"])

    # (b) new merchants that already look like a monthly subscription.
    cutoff = today - timedelta(days=NEW_WINDOW_DAYS)
    merchants_before = {key for (aid, key), charges in groups.items() if charges[0].date < cutoff}
    for (aid, key), charges in groups.items():
        if key in merchants_before or key in known_keys or charges[0].date < cutoff:
            continue
        dates = [c.date for c in charges]
        amounts = [Decimal(c.amount) for c in charges]
        if not looks_monthly(dates, amounts):
            continue
        found.append({"kind": "new_subscription", "key": f"new:{aid}:{key}", "name": charges[-1].description[:200],
                      "account_id": aid, "recurring_id": None, "usual_amount": Decimal(median(amounts)),
                      "amount": amounts[-1], "last_date": dates[-1], "hits": len(charges)})
    return found


def alert_text(a: ChargeAlert, currency: str, hide_amounts: bool) -> tuple[str, str]:
    amt = lambda v: f"{abs(float(v)):,.2f} {currency}".strip()  # noqa: E731
    if a.kind == "price_change":
        title = "FinVault: a recurring charge changed"
        body = (f"{a.name} changed." if hide_amounts else
                f"{a.name} charged {amt(a.amount)} on {a.last_date:%b %d}, usually {amt(a.usual_amount)}.")
    else:
        title = "FinVault: new subscription?"
        body = (f"{a.name} has charged you {a.hits} times about a month apart." if hide_amounts else
                f"{a.name} has charged you {a.hits} times about a month apart, latest {amt(a.amount)}.")
    return title, body


def run(db: Session, user: User, today: date | None = None, send: bool = True) -> int:
    """Store newly found alerts and notify the member about each one once. Returns how many are new."""
    existing = {a.key: a for a in db.scalars(select(ChargeAlert).where(ChargeAlert.user_id == user.id))}
    new = 0
    for f in detect(db, user, today):
        if f["key"] in existing:
            continue
        a = ChargeAlert(user_id=user.id, **f)
        db.add(a)
        existing[f["key"]] = a
        new += 1
    db.commit()
    if send:
        _notify_pending(db, user)
    return new


def _notify_pending(db: Session, user: User) -> None:
    pending = list(db.scalars(select(ChargeAlert).where(ChargeAlert.user_id == user.id, ChargeAlert.notified_at.is_(None),
                                                         ChargeAlert.dismissed_at.is_(None))))
    if not pending:
        return
    channels = bool(user.notify_ntfy_url or (user.notify_email and notify.smtp_configured()))
    currencies = dict(db.execute(select(Account.id, Account.currency).where(Account.user_id == user.id)).all())
    now = datetime.now(timezone.utc)
    for a in pending:
        if not channels:
            a.notified_at = now  # nothing set up: don't hold a backlog to flood them with later
            continue
        title, body = alert_text(a, currencies.get(a.account_id, ""), user.notify_hide_amounts)
        if notify.deliver(user, title, body):
            a.notified_at = now
    db.commit()


def run_safely(db: Session, user: User) -> int:
    """For use after an import: an alert problem must never fail the import itself."""
    try:
        return run(db, user)
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("charge alerts failed for user %s", user.id)
        return 0


def run_all(db: Session) -> int:
    return sum(run_safely(db, user) for user in list(db.scalars(select(User).where(User.is_active.is_(True)))))


def alert_out(a: ChargeAlert, accounts: dict) -> dict:
    acct = accounts.get(a.account_id)
    usual = Decimal(a.usual_amount) if a.usual_amount is not None else None
    return {"id": a.id, "kind": a.kind, "name": a.name, "account_id": a.account_id,
            "account_name": acct.name if acct else None, "currency": acct.currency if acct else None,
            "recurring_id": a.recurring_id, "usual_amount": f2(usual) if usual is not None else None,
            "amount": f2(a.amount), "change": f2(abs(Decimal(a.amount)) - abs(usual)) if usual is not None else None,
            "last_date": a.last_date.isoformat(), "hits": a.hits,
            "created_at": a.created_at.isoformat() if a.created_at else None}
