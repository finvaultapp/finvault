"""Payees: one place to clean up messy merchant names.

Transactions are grouped by merchant key (ledger.merchant_key, i.e. importers.normalize_merchant), so
"LOBLAWS #1234 TORONTO" and "LOBLAWS 5678 TORONTO" are one payee. Renaming sets the payee on every
matching transaction; renaming future imports and default categories are ordinary rules of match type
"merchant" (one rule per key), so the Rules page, imports and "Run on uncategorized" all see them.
"""
import re
from collections import Counter
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, owned
from ..models import Account, Category, Rule, Transaction, User
from ..services.currency import Converter
from ..services.ledger import merchant_key
from ..services.reports import f2

router = APIRouter(prefix="/api/payees", tags=["payees"])

SORTS = {"count", "name", "total", "last"}


def _merchant_rules(db: Session, user: User) -> dict[str, Rule]:
    """Rules that target exactly one merchant key and nothing else (the ones this page manages)."""
    out = {}
    for r in db.scalars(select(Rule).where(Rule.user_id == user.id, Rule.match_type == "merchant",
                                           Rule.match_field == "description", Rule.account_id.is_(None),
                                           Rule.amount_min.is_(None), Rule.amount_max.is_(None))
                        .order_by(Rule.priority, Rule.id)):
        out.setdefault((r.pattern or "").strip().upper(), r)
    return out


def _groups(db: Session, user: User):
    rows = db.execute(select(Transaction.id, Transaction.date, Transaction.amount, Transaction.description,
                             Transaction.payee, Transaction.category_id, Account.currency)
                      .join(Account, Account.id == Transaction.account_id)
                      .where(Transaction.user_id == user.id)).all()
    groups: dict[str, dict] = {}
    for r in rows:
        key = merchant_key(r.description)
        if not key:
            continue
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"key": key, "ids": [], "payees": Counter(), "descriptions": Counter(),
                               "cats": Counter(), "rows": []}
        g["ids"].append(r.id)
        if (r.payee or "").strip():
            g["payees"][r.payee.strip()] += 1
        g["descriptions"][r.description] += 1
        if r.category_id:
            g["cats"][r.category_id] += 1
        g["rows"].append((r.date, Decimal(r.amount), r.currency))
    return groups


@router.get("")
def list_payees(q: str | None = None, sort: str = "-count", page: int = Query(1, ge=1),
                page_size: int = Query(50, ge=1, le=200), user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    conv = Converter(db, user.base_currency)
    cats = {c.id: c for c in db.scalars(select(Category).where(Category.user_id == user.id))}
    rules = _merchant_rules(db, user)
    items = []
    for key, g in _groups(db, user).items():
        display = (g["payees"].most_common(1) or g["descriptions"].most_common(1))[0][0]
        total, last = Decimal(0), None
        for d, amount, currency in g["rows"]:
            v = conv.convert(amount, currency, d)
            if v is not None:
                total += v
            last = d if last is None or d > last else last
        usual = cats.get(g["cats"].most_common(1)[0][0]) if g["cats"] else None
        rule = rules.get(key)
        rule_cat = cats.get(rule.set_category_id) if rule and rule.set_category_id else None
        items.append({
            "key": key, "payee": display, "count": len(g["ids"]), "total": f2(total),
            "last_seen": last.isoformat() if last else None,
            "renamed": bool(g["payees"]) and len(g["payees"]) == 1 and sum(g["payees"].values()) == len(g["ids"]),
            "payee_variants": len(g["payees"]),
            "examples": [d for d, _ in g["descriptions"].most_common(3)],
            "usual_category": {"id": usual.id, "name": usual.name, "color": usual.color} if usual else None,
            "rule": {"id": rule.id, "set_payee": rule.set_payee, "set_category_id": rule.set_category_id,
                     "category_name": rule_cat.name if rule_cat else None,
                     "category_color": rule_cat.color if rule_cat else None} if rule else None,
        })
    if q and q.strip():
        needle = q.strip().lower()
        items = [i for i in items if needle in i["key"].lower() or needle in i["payee"].lower()
                 or any(needle in e.lower() for e in i["examples"])]
    field = sort.lstrip("-")
    field = field if field in SORTS else "count"
    desc = sort.startswith("-")
    keyfn = {"count": lambda i: (i["count"], i["payee"].lower()),
             "name": lambda i: i["payee"].lower(),
             "total": lambda i: (abs(i["total"]), i["payee"].lower()),
             "last": lambda i: (i["last_seen"] or "", i["payee"].lower())}[field]
    items.sort(key=keyfn, reverse=desc)
    total = len(items)
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size], "total": total, "page": page, "page_size": page_size,
            "currency": user.base_currency, "warnings": conv.warnings()}


def _clean_keys(keys: list[str]) -> list[str]:
    out = list(dict.fromkeys(re.sub(r"\s+", " ", k).strip().upper() for k in keys if k and k.strip()))
    if not out:
        raise HTTPException(422, "Choose at least one payee.")
    return out


def _ids_for(db: Session, user: User, keys: set[str]) -> list[int]:
    rows = db.execute(select(Transaction.id, Transaction.description).where(Transaction.user_id == user.id)).all()
    return [r.id for r in rows if merchant_key(r.description) in keys]


def _rule_for(db: Session, user: User, rules: dict[str, Rule], key: str, name: str) -> Rule:
    r = rules.get(key)
    if r is None:
        r = Rule(user_id=user.id, name=name[:120], match_field="description", match_type="merchant", pattern=key[:300],
                 priority=100, is_active=True)
        db.add(r)
        rules[key] = r
    return r


class RenameIn(BaseModel):
    keys: list[str] = Field(min_length=1, max_length=500)
    payee: str = Field(max_length=200)
    create_rule: bool = False  # rename future imports too


@router.post("/rename")
def rename(body: RenameIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Rename one payee, or merge several merchant keys into one payee name."""
    keys = _clean_keys(body.keys)
    payee = re.sub(r"\s+", " ", body.payee).strip()
    if not payee:
        raise HTTPException(422, "Give the payee a name.")
    ids = _ids_for(db, user, set(keys))
    for i in range(0, len(ids), 900):
        db.execute(update(Transaction).where(Transaction.id.in_(ids[i:i + 900])).values(payee=payee))
    rules = 0
    if body.create_rule:
        existing = _merchant_rules(db, user)
        for key in keys:
            r = _rule_for(db, user, existing, key, payee)
            r.set_payee = payee
            rules += 1
    db.commit()
    return {"updated": len(ids), "rules": rules}


class CategoryIn(BaseModel):
    keys: list[str] = Field(min_length=1, max_length=500)
    category_id: int | None = None  # None clears the default
    apply: str = Field(default="uncategorized", pattern="^(none|uncategorized|all)$")


@router.put("/category")
def set_default_category(body: CategoryIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Default category for a merchant, kept as a merchant rule (created or updated)."""
    keys = _clean_keys(body.keys)
    if body.category_id is not None:
        owned(db, Category, body.category_id, user)
    existing = _merchant_rules(db, user)
    groups = _groups(db, user) if body.category_id is not None else {}
    rule_ids = []
    for key in keys:
        if body.category_id is None:
            r = existing.get(key)
            if r is None:
                continue
            r.set_category_id = None
            if not r.set_payee and not r.set_tag_id:
                db.delete(r)
            continue
        g = groups.get(key)
        name = (g["payees"].most_common(1) or g["descriptions"].most_common(1))[0][0] if g else key
        r = _rule_for(db, user, existing, key, name)
        r.set_category_id = body.category_id
        r.is_active = True
        db.flush()
        rule_ids.append(r.id)
    updated = 0
    if body.category_id is not None and body.apply != "none":
        ids = [i for k in keys for i in (groups.get(k) or {"ids": []})["ids"]]
        for i in range(0, len(ids), 900):
            stmt = update(Transaction).where(Transaction.id.in_(ids[i:i + 900]))
            if body.apply == "uncategorized":
                stmt = stmt.where(Transaction.category_id.is_(None))
            updated += db.execute(stmt.values(category_id=body.category_id)).rowcount or 0
    db.commit()
    return {"rules": rule_ids, "updated": updated}


@router.get("/transactions")
def payee_transactions(key: str, limit: int = Query(20, le=100), user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    """The most recent transactions for one merchant key (for the detail view)."""
    k = _clean_keys([key])[0]
    ids = set(_ids_for(db, user, {k}))
    rows = db.execute(select(Transaction.id, Transaction.date, Transaction.amount, Transaction.description,
                             Transaction.payee, Account.currency)
                      .join(Account, Account.id == Transaction.account_id)
                      .where(Transaction.user_id == user.id).order_by(Transaction.date.desc(), Transaction.id.desc())).all()
    out = [{"id": r.id, "date": r.date.isoformat(), "amount": f2(r.amount), "description": r.description,
            "payee": r.payee, "currency": r.currency} for r in rows if r.id in ids][:limit]
    return {"key": k, "items": out, "total": len(ids)}
