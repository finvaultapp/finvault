import re
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, owned
from ..models import Account, Category, Rule, Transaction, User
from ..services.ledger import apply_rules_to_existing, rule_matches

router = APIRouter(prefix="/api", tags=["categories"])


def cat_out(c: Category, count: int = 0) -> dict:
    return {"id": c.id, "name": c.name, "kind": c.kind, "color": c.color, "parent_id": c.parent_id,
            "tax_tag": c.tax_tag, "transaction_count": count}


@router.get("/categories")
def list_categories(user: User = Depends(current_user), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Transaction.category_id, func.count(Transaction.id))
                             .where(Transaction.user_id == user.id).group_by(Transaction.category_id)).all())
    return [cat_out(c, counts.get(c.id, 0)) for c in
            db.scalars(select(Category).where(Category.user_id == user.id).order_by(Category.kind, Category.name))]


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: str = Field(default="expense", pattern="^(expense|income|transfer)$")
    color: str = Field(default="#7c8a96", pattern="^#[0-9a-fA-F]{6}$")
    parent_id: int | None = None


@router.post("/categories")
def create_category(body: CategoryIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.parent_id:
        owned(db, Category, body.parent_id, user)
    c = Category(user_id=user.id, **body.model_dump())
    db.add(c)
    db.commit()
    return cat_out(c)


@router.patch("/categories/{cat_id}")
def update_category(cat_id: int, body: CategoryIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = owned(db, Category, cat_id, user)
    if body.parent_id:
        if body.parent_id == c.id:
            raise HTTPException(422, "A category can't be its own parent.")
        owned(db, Category, body.parent_id, user)
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    db.commit()
    return cat_out(c)


@router.delete("/categories/{cat_id}")
def delete_category(cat_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, Category, cat_id, user))
    db.commit()
    return {"ok": True}


# --- Rules --------------------------------------------------------------------

def rule_out(r: Rule) -> dict:
    return {"id": r.id, "name": r.name, "priority": r.priority, "match_field": r.match_field,
            "match_type": r.match_type, "pattern": r.pattern,
            "amount_min": float(r.amount_min) if r.amount_min is not None else None,
            "amount_max": float(r.amount_max) if r.amount_max is not None else None,
            "account_id": r.account_id, "set_category_id": r.set_category_id, "set_payee": r.set_payee,
            "is_active": r.is_active}


class RuleIn(BaseModel):
    name: str = Field(default="", max_length=120)
    priority: int = 100
    match_field: str = Field(default="description", pattern="^(description|payee)$")
    match_type: str = Field(default="contains", pattern="^(contains|equals|starts_with|regex)$")
    pattern: str = Field(min_length=1, max_length=300)
    amount_min: float | None = None
    amount_max: float | None = None
    account_id: int | None = None
    set_category_id: int | None = None
    set_payee: str | None = Field(default=None, max_length=200)
    is_active: bool = True


def _validate_rule(db: Session, user: User, body: RuleIn) -> dict:
    if body.match_type == "regex":
        try:
            re.compile(body.pattern)
        except re.error as exc:
            raise HTTPException(422, f"Invalid pattern: {exc}") from exc
    if body.set_category_id:
        owned(db, Category, body.set_category_id, user)
    if body.account_id:
        owned(db, Account, body.account_id, user)
    if not body.set_category_id and not body.set_payee:
        raise HTTPException(422, "A rule needs to set a category or a payee.")
    data = body.model_dump()
    for k in ("amount_min", "amount_max"):
        data[k] = Decimal(str(data[k])) if data[k] is not None else None
    return data


@router.get("/rules")
def list_rules(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [rule_out(r) for r in db.scalars(select(Rule).where(Rule.user_id == user.id).order_by(Rule.priority, Rule.id))]


@router.post("/rules")
def create_rule(body: RuleIn, apply: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = Rule(user_id=user.id, **_validate_rule(db, user, body))
    db.add(r)
    db.commit()
    changed = apply_rules_to_existing(db, user) if apply else 0
    return rule_out(r) | {"applied": changed}


@router.patch("/rules/{rule_id}")
def update_rule(rule_id: int, body: RuleIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = owned(db, Rule, rule_id, user)
    for k, v in _validate_rule(db, user, body).items():
        setattr(r, k, v)
    db.commit()
    return rule_out(r)


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, Rule, rule_id, user))
    db.commit()
    return {"ok": True}


@router.post("/rules/test")
def test_rule(body: RuleIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Show which existing transactions a draft rule would match."""
    data = _validate_rule(db, user, body) if (body.set_category_id or body.set_payee) else body.model_dump()
    draft = Rule(**{k: v for k, v in data.items()})
    if draft.amount_min is not None:
        draft.amount_min = Decimal(str(draft.amount_min))
    if draft.amount_max is not None:
        draft.amount_max = Decimal(str(draft.amount_max))
    matches, count = [], 0
    for t in db.scalars(select(Transaction).where(Transaction.user_id == user.id).order_by(Transaction.date.desc()).limit(5000)).unique():
        if rule_matches(draft, t.description, t.payee, Decimal(t.amount), t.account_id):
            count += 1
            if len(matches) < 10:
                matches.append({"date": t.date.isoformat(), "description": t.description, "amount": float(t.amount)})
    return {"count": count, "examples": matches}


class ApplyIn(BaseModel):
    only_uncategorized: bool = True


@router.post("/rules/apply")
def apply_rules(body: ApplyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"changed": apply_rules_to_existing(db, user, body.only_uncategorized)}
