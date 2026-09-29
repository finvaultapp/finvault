"""Tags (labels on transactions), the "By tag" report and budget rollover settings."""
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, owned
from ..models import Budget, Rule, Tag, Transaction, TransactionTag, User
from ..services import tags as tagsvc
from ..services.currency import Converter
from ..services.reports import _classify, effective_lines, f2

router = APIRouter(prefix="/api", tags=["organize"])


def _tag_out(t: Tag, count: int = 0) -> dict:
    return {"id": t.id, "name": t.name, "count": count}


def _counts(db: Session, user: User) -> dict[int, int]:
    return dict(db.execute(select(TransactionTag.tag_id, func.count(TransactionTag.transaction_id))
                           .join(Tag, Tag.id == TransactionTag.tag_id).where(Tag.user_id == user.id)
                           .group_by(TransactionTag.tag_id)).all())


@router.get("/tags")
def list_tags(user: User = Depends(current_user), db: Session = Depends(get_db)):
    counts = _counts(db, user)
    rows = db.scalars(select(Tag).where(Tag.user_id == user.id).order_by(func.lower(Tag.name)))
    return [_tag_out(t, counts.get(t.id, 0)) for t in rows]


class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.post("/tags")
def create_tag(body: TagIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    tag = tagsvc.get_or_create(db, user, body.name)
    db.commit()
    return _tag_out(tag, _counts(db, user).get(tag.id, 0))


@router.patch("/tags/{tag_id}")
def rename_tag(tag_id: int, body: TagIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    tag = tagsvc.owned_tag(db, user, tag_id)
    name = tagsvc.clean_name(body.name)
    if not name:
        raise HTTPException(422, "Give the tag a name.")
    other = tagsvc.find(db, user, name)
    if other is not None and other.id != tag.id:
        raise HTTPException(409, "A tag with that name already exists. Merge the two instead.")
    tag.name = name
    db.commit()
    return _tag_out(tag, _counts(db, user).get(tag.id, 0))


def _drop_tag(db: Session, user: User, tag: Tag, replacement: int | None = None) -> None:
    for r in db.scalars(select(Rule).where(Rule.user_id == user.id, Rule.set_tag_id == tag.id)):
        r.set_tag_id = replacement
        if replacement is None and not r.set_category_id and not r.set_payee:
            db.delete(r)  # a tag-only rule has nothing left to do
    db.execute(delete(TransactionTag).where(TransactionTag.tag_id == tag.id))
    db.delete(tag)


@router.delete("/tags/{tag_id}")
def delete_tag(tag_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _drop_tag(db, user, tagsvc.owned_tag(db, user, tag_id))
    db.commit()
    return {"ok": True}


class MergeIn(BaseModel):
    source_ids: list[int] = Field(min_length=1)
    target_id: int


@router.post("/tags/merge")
def merge_tags(body: MergeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    target = tagsvc.owned_tag(db, user, body.target_id)
    sources = [tagsvc.owned_tag(db, user, i) for i in dict.fromkeys(body.source_ids) if i != target.id]
    have = set(db.scalars(select(TransactionTag.transaction_id).where(TransactionTag.tag_id == target.id)))
    moved = 0
    for src in sources:
        for tx_id in db.scalars(select(TransactionTag.transaction_id).where(TransactionTag.tag_id == src.id)).all():
            if tx_id not in have:
                db.add(TransactionTag(transaction_id=tx_id, tag_id=target.id))
                have.add(tx_id)
                moved += 1
        db.flush()
        _drop_tag(db, user, src, replacement=target.id)
    db.commit()
    return {"merged": len(sources), "moved": moved, "tag": _tag_out(target, len(have))}


class TxTagsIn(BaseModel):
    names: list[str] = Field(default_factory=list, max_length=50)


@router.put("/transactions/{tx_id}/tags")
def set_transaction_tags(tx_id: int, body: TxTagsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = owned(db, Transaction, tx_id, user)
    wanted = {tagsvc.get_or_create(db, user, n).id for n in body.names if tagsvc.clean_name(n)}
    have = set(db.scalars(select(TransactionTag.tag_id).where(TransactionTag.transaction_id == t.id)))
    if have - wanted:
        db.execute(delete(TransactionTag).where(TransactionTag.transaction_id == t.id,
                                                TransactionTag.tag_id.in_(have - wanted)))
    db.add_all(TransactionTag(transaction_id=t.id, tag_id=i) for i in wanted - have)
    db.commit()
    return {"tags": tagsvc.names_by_transaction(db, [t.id]).get(t.id, [])}


class BulkTagIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=5000)
    action: str = Field(pattern="^(add|remove)$")
    tag_id: int | None = None
    name: str | None = Field(default=None, max_length=80)


@router.post("/tags/bulk")
def bulk_tags(body: BulkTagIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.tag_id is not None:
        tag = tagsvc.owned_tag(db, user, body.tag_id)
    elif body.action == "add":
        tag = tagsvc.get_or_create(db, user, body.name or "")
    else:
        tag = tagsvc.find(db, user, body.name or "")
        if tag is None:
            raise HTTPException(404, "Tag not found.")
    ids = set(db.scalars(select(Transaction.id).where(Transaction.user_id == user.id, Transaction.id.in_(body.ids))))
    have = set(db.scalars(select(TransactionTag.transaction_id).where(TransactionTag.tag_id == tag.id,
                                                                    TransactionTag.transaction_id.in_(ids))))
    if body.action == "add":
        db.add_all(TransactionTag(transaction_id=i, tag_id=tag.id) for i in ids - have)
        changed = len(ids - have)
    else:
        if have:
            db.execute(delete(TransactionTag).where(TransactionTag.tag_id == tag.id, TransactionTag.transaction_id.in_(have)))
        changed = len(have)
    db.commit()
    return {"updated": changed, "tag": _tag_out(tag)}


# --- "By tag" report -------------------------------------------------------------

@router.get("/reports/tags")
def tag_report(start: date | None = None, end: date | None = None, user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    """Money in and out per tag over a range, counting splits and shared costs like every other report."""
    end = end or date.today()
    start = start or date(end.year, 1, 1)
    conv = Converter(db, user.base_currency)
    tags = {t.id: t for t in db.scalars(select(Tag).where(Tag.user_id == user.id))}
    links: dict[int, list[int]] = defaultdict(list)
    for tx_id, tag_id in db.execute(select(TransactionTag.transaction_id, TransactionTag.tag_id)
                                    .join(Transaction, Transaction.id == TransactionTag.transaction_id)
                                    .where(Transaction.user_id == user.id, Transaction.date >= start,
                                           Transaction.date <= end)):
        links[tx_id].append(tag_id)
    sums = {tid: {"income": Decimal(0), "expense": Decimal(0), "tx": set()} for tid in tags}
    if links:
        for d, amount, cat_id, currency, kind, tx_id in effective_lines(db, user, start, end, with_ids=True):
            if tx_id not in links:
                continue
            side = _classify(Decimal(amount), kind)
            if side is None:
                continue
            v = conv.convert(Decimal(amount), currency, d)
            if v is None:
                continue
            for tid in links[tx_id]:
                s = sums[tid]
                s["tx"].add(tx_id)
                if side == "income":
                    s["income"] += v
                else:
                    s["expense"] -= v
    items = [{"id": tid, "name": tags[tid].name, "income": f2(s["income"]), "expense": f2(s["expense"]),
              "net": f2(s["income"] - s["expense"]), "count": len(s["tx"])} for tid, s in sums.items() if s["tx"]]
    items.sort(key=lambda i: (-(i["expense"] + i["income"]), i["name"].lower()))
    return {"currency": user.base_currency, "start": start.isoformat(), "end": end.isoformat(),
            "items": items, "warnings": conv.warnings()}


# --- Budget rollover -------------------------------------------------------------

class RolloverIn(BaseModel):
    mode: str = Field(pattern="^(off|carry|carry_all)$")
    start: str | None = Field(default=None, max_length=7)  # YYYY-MM, the first month that carries


@router.put("/budgets/{budget_id}/rollover")
def set_rollover(budget_id: int, body: RolloverIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    b = owned(db, Budget, budget_id, user)
    start = None
    if body.start:
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", body.start):
            raise HTTPException(422, "Pick the start month as year and month, like 2026-01.")
        start = date(int(body.start[:4]), int(body.start[5:7]), 1)
    elif body.mode != "off":
        today = date.today()
        start = b.rollover_start or date(today.year, today.month, 1)
    b.rollover = body.mode
    b.rollover_start = start
    db.commit()
    return {"id": b.id, "rollover": b.rollover, "rollover_start": start.isoformat()[:7] if start else None}
