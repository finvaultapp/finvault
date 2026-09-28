"""TFSA / RRSP / FHSA contribution room tracking.

FinVault does not calculate CRA room. The member copies the number from CRA My
Account (or their Notice of Assessment) for each year, and FinVault tracks
contributions and withdrawals against it. Rules shown here are reminders, not
tax advice; the texts say so in the UI.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Category, PlanEntry, RegisteredPlan, Transaction, User
from .reports import f2

KINDS = {"tfsa": "TFSA", "rrsp": "RRSP", "fhsa": "FHSA"}
# The RRSP rules allow a cumulative over-contribution of up to $2,000 before the penalty tax applies.
RRSP_BUFFER = Decimal("2000")


def _linked_moves(db: Session, plan: RegisteredPlan) -> list[dict]:
    """Deposits into / withdrawals out of the linked account during the plan year.

    Lines categorized as income (interest, dividends) are growth, not contributions, so they're skipped.
    """
    if not plan.account_id:
        return []
    income = set(db.scalars(select(Category.id).where(Category.user_id == plan.user_id, Category.kind == "income")))
    rows = db.scalars(select(Transaction).where(
        Transaction.account_id == plan.account_id,
        Transaction.date >= date(plan.year, 1, 1), Transaction.date <= date(plan.year, 12, 31)).order_by(Transaction.date))
    return [{"id": f"t{t.id}", "date": t.date.isoformat(), "amount": f2(t.amount), "note": t.description, "source": "account"}
            for t in rows if t.category_id not in income]


def summary(db: Session, plan: RegisteredPlan) -> dict:
    manual = [{"id": e.id, "date": e.date.isoformat(), "amount": f2(e.amount), "note": e.note, "source": "manual"}
              for e in db.scalars(select(PlanEntry).where(PlanEntry.plan_id == plan.id).order_by(PlanEntry.date))]
    entries = sorted(manual + _linked_moves(db, plan), key=lambda e: e["date"])
    contributed = sum((Decimal(str(e["amount"])) for e in entries if e["amount"] > 0), Decimal(0))
    withdrawn = -sum((Decimal(str(e["amount"])) for e in entries if e["amount"] < 0), Decimal(0))
    room = Decimal(plan.room)
    remaining = room - contributed
    # Codes plus numbers; the page writes the sentence in the member's language.
    warnings = []
    if plan.kind == "rrsp":
        if remaining < -RRSP_BUFFER:
            warnings.append({"level": "danger", "code": "rrsp_over_buffer", "amount": f2(-remaining - RRSP_BUFFER)})
        elif remaining < 0:
            warnings.append({"level": "warn", "code": "rrsp_in_buffer", "amount": f2(-remaining)})
    elif remaining < 0:
        warnings.append({"level": "danger", "code": "over_room", "amount": f2(-remaining)})
    if plan.kind == "tfsa" and withdrawn > 0:
        warnings.append({"level": "info", "code": "tfsa_withdrawn", "amount": f2(withdrawn), "year": plan.year + 1})
    return {"id": plan.id, "kind": plan.kind, "label": KINDS[plan.kind], "year": plan.year, "room": f2(room),
            "account_id": plan.account_id, "notes": plan.notes, "contributed": f2(contributed), "withdrawn": f2(withdrawn),
            "remaining": f2(remaining), "percent": round(float(contributed / room * 100), 1) if room > 0 else None,
            "entries": entries, "warnings": warnings}


def all_summaries(db: Session, user: User) -> list[dict]:
    plans = db.scalars(select(RegisteredPlan).where(RegisteredPlan.user_id == user.id)
                       .order_by(RegisteredPlan.year.desc(), RegisteredPlan.kind))
    return [summary(db, p) for p in plans]
