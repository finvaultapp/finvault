"""Year-end summary of spending tagged as possibly deductible, for the member's accountant.

A category carries a default tag; a single transaction can override it (or opt out
with 'none'). Split lines use their own category's tag. Nothing here decides what
CRA will accept: the page says to confirm eligibility with an accountant.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account, Category, Share, Transaction, TransactionSplit, User
from .currency import Converter
from .reports import f2

TAGS = {
    "medical": "Medical expenses",
    "childcare": "Child care",
    "donations": "Charitable donations",
    "moving": "Moving expenses",
    "home_office": "Home office",
    "other_deductible": "Other possibly deductible",
}


def summary(db: Session, user: User, year: int) -> dict:
    conv = Converter(db, user.base_currency)
    cats = {c.id: c for c in db.scalars(select(Category).where(Category.user_id == user.id))}
    txs = list(db.scalars(select(Transaction).where(
        Transaction.user_id == user.id, Transaction.date >= date(year, 1, 1), Transaction.date <= date(year, 12, 31))
        .order_by(Transaction.date)).unique())
    ids = [t.id for t in txs]
    splits = defaultdict(list)
    shared = defaultdict(Decimal)
    for chunk in (ids[i:i + 900] for i in range(0, len(ids), 900)):
        for sp in db.scalars(select(TransactionSplit).where(TransactionSplit.transaction_id.in_(chunk))):
            splits[sp.transaction_id].append(sp)
        for sh in db.scalars(select(Share).where(Share.transaction_id.in_(chunk))):
            shared[sh.transaction_id] += Decimal(sh.amount)

    groups: dict[str, dict] = {k: {"tag": k, "label": v, "total": Decimal(0), "items": []} for k, v in TAGS.items()}
    for t in txs:
        total = Decimal(t.amount)
        mine = total + shared[t.id] if total < 0 else total
        ratio = mine / total if total else Decimal(1)
        parts = [(sp.category_id, Decimal(sp.amount), sp.note) for sp in splits[t.id]] or [(t.category_id, total, "")]
        for cat_id, amt, note in parts:
            tag = t.tax_tag if (t.tax_tag and not splits[t.id]) else (cats[cat_id].tax_tag if cat_id in cats else None)
            if not tag or tag == "none" or tag not in groups:
                continue
            spent = -(amt * ratio)  # money out is negative; report it as a positive expense
            value = conv.convert(spent, t.account.currency, t.date)
            if value is None:
                continue
            groups[tag]["total"] += value
            groups[tag]["items"].append({
                "transaction_id": t.id, "date": t.date.isoformat(), "description": t.payee or t.description,
                "account": t.account.name, "category": cats[cat_id].name if cat_id in cats else None,
                "amount": f2(value), "note": note or t.notes, "tag_source": "transaction" if t.tax_tag else "category"})
    out = [g | {"total": f2(g["total"]), "count": len(g["items"])} for g in groups.values() if g["items"]]
    return {"year": year, "currency": user.base_currency, "groups": out,
            "total": f2(sum((Decimal(str(g["total"])) for g in out), Decimal(0))), "warnings": conv.warnings(),
            "tagged_categories": [{"id": c.id, "name": c.name, "tax_tag": c.tax_tag} for c in cats.values() if c.tax_tag]}
