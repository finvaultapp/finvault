"""Budgets, recurring transactions and savings goals."""
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, owned
from ..models import Account, Budget, Category, Goal, Recurring, User
from ..services import recurring as rec
from ..services.reports import budgets_for_month, f2, goal_progress

router = APIRouter(prefix="/api", tags=["planning"])


# --- Budgets ------------------------------------------------------------------

@router.get("/budgets")
def get_budgets(month: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    today = date.today()
    y, m = (int(month[:4]), int(month[5:7])) if month else (today.year, today.month)
    return budgets_for_month(db, user, y, m)


class BudgetIn(BaseModel):
    category_id: int
    amount: float = Field(ge=0)


@router.put("/budgets")
def set_budget(body: BudgetIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    cat = owned(db, Category, body.category_id, user)
    if cat.kind != "expense":
        raise HTTPException(422, "Budgets can only be set on expense categories.")
    b = db.scalar(select(Budget).where(Budget.user_id == user.id, Budget.category_id == cat.id))
    if b is None:
        db.add(Budget(user_id=user.id, category_id=cat.id, amount=Decimal(str(body.amount))))
    else:
        b.amount = Decimal(str(body.amount))
    db.commit()
    return {"ok": True}


@router.delete("/budgets/{budget_id}")
def delete_budget(budget_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, Budget, budget_id, user))
    db.commit()
    return {"ok": True}


# --- Recurring ----------------------------------------------------------------

def rec_out(r: Recurring, accounts: dict, cats: dict) -> dict:
    return {"id": r.id, "name": r.name, "amount": f2(r.amount), "account_id": r.account_id,
            "account_name": accounts.get(r.account_id).name if r.account_id in accounts else None,
            "currency": accounts.get(r.account_id).currency if r.account_id in accounts else None,
            "category_id": r.category_id, "category_name": cats.get(r.category_id),
            "frequency": r.frequency, "next_date": r.next_date.isoformat(),
            "end_date": r.end_date.isoformat() if r.end_date else None, "auto_post": r.auto_post, "is_active": r.is_active,
            "remind_days": r.remind_days}


class RecurringIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    amount: float
    account_id: int
    category_id: int | None = None
    frequency: str = Field(default="monthly", pattern="^(weekly|biweekly|monthly|quarterly|yearly)$")
    next_date: date
    end_date: date | None = None
    auto_post: bool = False
    is_active: bool = True


@router.get("/recurring")
def list_recurring(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rec.post_due(db, user.id)
    accounts = {a.id: a for a in db.scalars(select(Account).where(Account.user_id == user.id))}
    cats = {c.id: c.name for c in db.scalars(select(Category).where(Category.user_id == user.id))}
    items = list(db.scalars(select(Recurring).where(Recurring.user_id == user.id).order_by(Recurring.next_date)))
    horizon = date.today() + timedelta(days=45)
    upcoming = []
    for r in items:
        if not r.is_active:
            continue
        for d in rec.occurrences(r, horizon, limit=8):
            upcoming.append({"recurring_id": r.id, "name": r.name, "date": d.isoformat(), "amount": f2(r.amount),
                             "currency": accounts[r.account_id].currency if r.account_id in accounts else None,
                             "auto_post": r.auto_post})
    upcoming.sort(key=lambda u: u["date"])
    monthly = {"weekly": Decimal("4.345"), "biweekly": Decimal("2.1725"), "monthly": Decimal(1),
               "quarterly": Decimal(1) / 3, "yearly": Decimal(1) / 12}
    return {"items": [rec_out(r, accounts, cats) for r in items], "upcoming": upcoming,
            "monthly_outflow_by_currency": _monthly_totals(items, accounts, monthly)}


def _monthly_totals(items, accounts, factor) -> dict:
    totals: dict[str, Decimal] = {}
    for r in items:
        if r.is_active and r.amount < 0 and r.account_id in accounts:
            cur = accounts[r.account_id].currency
            totals[cur] = totals.get(cur, Decimal(0)) + (-Decimal(r.amount) * factor[r.frequency])
    return {k: f2(v) for k, v in totals.items()}


def _check(db, user, body: RecurringIn):
    owned(db, Account, body.account_id, user)
    if body.category_id:
        owned(db, Category, body.category_id, user)


@router.post("/recurring")
def create_recurring(body: RecurringIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _check(db, user, body)
    r = Recurring(user_id=user.id, **body.model_dump(exclude={"amount"}), amount=Decimal(str(body.amount)),
                  anchor_day=body.next_date.day)
    db.add(r)
    db.commit()
    rec.post_due(db, user.id)
    return {"id": r.id}


@router.patch("/recurring/{rid}")
def update_recurring(rid: int, body: RecurringIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = owned(db, Recurring, rid, user)
    _check(db, user, body)
    for k, v in body.model_dump(exclude={"amount"}).items():
        setattr(r, k, v)
    r.amount = Decimal(str(body.amount))
    r.anchor_day = body.next_date.day
    db.commit()
    rec.post_due(db, user.id)
    return {"ok": True}


@router.delete("/recurring/{rid}")
def delete_recurring(rid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, Recurring, rid, user))
    db.commit()
    return {"ok": True}


@router.post("/recurring/{rid}/skip")
def skip_recurring(rid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = owned(db, Recurring, rid, user)
    r.next_date = rec.advance(r.next_date, r.frequency, r.anchor_day)
    db.commit()
    return {"next_date": r.next_date.isoformat()}


@router.get("/recurring/suggestions")
def suggestions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    names = {r.name.lower() for r in db.scalars(select(Recurring).where(Recurring.user_id == user.id))}
    from ..importers import normalize_merchant
    names |= {normalize_merchant(n).lower() for n in names}
    return rec.detect(db, user.id, names)


# --- Goals --------------------------------------------------------------------

class GoalIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_amount: float = Field(gt=0)
    currency: str = Field(default="CAD", min_length=3, max_length=3)
    target_date: date | None = None
    account_id: int | None = None
    saved_amount: float = 0


@router.get("/goals")
def list_goals(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return goal_progress(db, user)


@router.post("/goals")
def create_goal(body: GoalIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.account_id:
        owned(db, Account, body.account_id, user)
    g = Goal(user_id=user.id, name=body.name, target_amount=Decimal(str(body.target_amount)),
             currency=body.currency.upper(), target_date=body.target_date, account_id=body.account_id,
             saved_amount=Decimal(str(body.saved_amount)))
    db.add(g)
    db.commit()
    return {"id": g.id}


@router.patch("/goals/{gid}")
def update_goal(gid: int, body: GoalIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = owned(db, Goal, gid, user)
    if body.account_id:
        owned(db, Account, body.account_id, user)
    g.name, g.target_amount, g.currency = body.name, Decimal(str(body.target_amount)), body.currency.upper()
    g.target_date, g.account_id, g.saved_amount = body.target_date, body.account_id, Decimal(str(body.saved_amount))
    db.commit()
    return {"ok": True}


class ContributeIn(BaseModel):
    amount: float


@router.post("/goals/{gid}/contribute")
def contribute(gid: int, body: ContributeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = owned(db, Goal, gid, user)
    if g.account_id:
        raise HTTPException(422, "This goal tracks a linked account's balance; move money into that account instead.")
    g.saved_amount = Decimal(g.saved_amount or 0) + Decimal(str(body.amount))
    db.commit()
    return {"saved_amount": f2(g.saved_amount)}


@router.delete("/goals/{gid}")
def delete_goal(gid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, Goal, gid, user))
    db.commit()
    return {"ok": True}
