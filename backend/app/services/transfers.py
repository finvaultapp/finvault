"""Pair the two legs of a transfer between your own accounts so neither counts as income or spending.

A pair is money out of one account and the same amount into another, a few days apart.
Matched legs get a transfer-kind category ("Credit card payment" when a card is involved,
otherwise "Transfer") and point at each other through `transfer_id`.
"""
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account, Category, Transaction, User

WINDOW_DAYS = 4
HINTS = ("TRANSFER", "PAYMENT", "PAIEMENT", "VIREMENT", "E-TRANSFER", "ETRANSFER", "TFR", "XFER", "THANK YOU", "MERCI", "PYMT")


def _transfer_categories(db: Session, user_id: int) -> tuple[int | None, int | None]:
    cats = {c.name: c.id for c in db.scalars(select(Category).where(Category.user_id == user_id, Category.kind == "transfer"))}
    general = cats.get("Transfer") or cats.get("Virement") or next(iter(cats.values()), None)
    return general, cats.get("Credit card payment") or cats.get("Paiement de carte de crédit") or general


def candidates(db: Session, user: User, limit: int = 50) -> list[dict]:
    accounts = {a.id: a for a in db.scalars(select(Account).where(Account.user_id == user.id))}
    if len(accounts) < 2:
        return []
    rows = list(db.scalars(select(Transaction).where(Transaction.user_id == user.id, Transaction.transfer_id.is_(None))
                           .order_by(Transaction.date)).unique())
    incoming: dict[str, list[Transaction]] = {}
    for t in rows:
        if t.amount > 0:
            incoming.setdefault(f"{Decimal(t.amount):.2f}", []).append(t)
    pairs, used = [], set()
    for out in rows:
        if out.amount >= 0 or out.id in used:
            continue
        options = [t for t in incoming.get(f"{-Decimal(out.amount):.2f}", [])
                   if t.id not in used and t.account_id != out.account_id and abs((t.date - out.date).days) <= WINDOW_DAYS]
        if not options:
            continue
        best = min(options, key=lambda t: abs((t.date - out.date).days))
        text = f"{out.description} {best.description}".upper()
        card = accounts[out.account_id].type == "credit_card" or accounts[best.account_id].type == "credit_card"
        confident = len(options) == 1 and (card or any(h in text for h in HINTS)
                                           or accounts[best.account_id].type in {"savings", "investment"})
        pairs.append({"out": out, "in": best, "confident": confident, "card": card})
        used.update({out.id, best.id})
        if len(pairs) >= limit:
            break
    return pairs


def serialize(pair: dict) -> dict:
    def leg(t):
        return {"id": t.id, "date": t.date.isoformat(), "amount": float(t.amount), "description": t.description,
                "account_name": t.account.name, "currency": t.account.currency}
    return {"out": leg(pair["out"]), "in": leg(pair["in"]), "confident": pair["confident"], "card": pair["card"]}


def match(db: Session, user: User, out: Transaction, inc: Transaction) -> None:
    if out.user_id != user.id or inc.user_id != user.id or out.account_id == inc.account_id:
        raise ValueError("Those two transactions can't be a transfer between your own accounts.")
    general, card_cat = _transfer_categories(db, user.id)
    card = out.account.type == "credit_card" or inc.account.type == "credit_card"
    cat = card_cat if card else general
    out.transfer_id, inc.transfer_id = inc.id, out.id
    if cat:
        out.category_id = inc.category_id = cat


def unmatch(db: Session, user: User, t: Transaction) -> None:
    other = db.get(Transaction, t.transfer_id) if t.transfer_id else None
    t.transfer_id = None
    if other and other.user_id == user.id:
        other.transfer_id = None


def auto_match(db: Session, user: User) -> int:
    """Match only the pairs we're confident about; the rest are offered as suggestions."""
    n = 0
    for p in candidates(db, user, limit=500):
        if p["confident"]:
            match(db, user, p["out"], p["in"])
            n += 1
    db.commit()
    return n
