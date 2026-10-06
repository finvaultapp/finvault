"""TFSA / RRSP / FHSA contribution room tracking.

FinVault does not calculate CRA room. The member copies the number from CRA My Account (or their Notice of
Assessment) for each year, and FinVault tracks contributions and withdrawals against it. A plan made by a
statement import has no room until the member enters it. Lines in a registered account carry a movement type
(services/registered.py); only contributions and RRSP-to-FHSA transfers use room. Rules shown here are
reminders, not tax advice; the texts say so in the UI.
"""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account, RegisteredPlan, User
from . import registered
from .reports import f2

KINDS = {"tfsa": "TFSA", "rrsp": "RRSP", "fhsa": "FHSA"}
# The RRSP rules allow a cumulative over-contribution of up to $2,000 before the penalty tax applies.
RRSP_BUFFER = Decimal("2000")


def _entry_out(e: dict) -> dict:
    return {k: (f2(v) if k == "amount" else v) for k, v in e.items()}


def summary(db: Session, plan: RegisteredPlan, *, history: list | None = None, counted: dict | None = None) -> dict:
    c = counted or registered.counts(db, plan)
    if history is None:
        same = db.scalars(select(RegisteredPlan).where(RegisteredPlan.user_id == plan.user_id,
                                                       RegisteredPlan.kind == plan.kind))
        history = [(p, c if p.id == plan.id else registered.counts(db, p)) for p in same]
    contributed, withdrawn = c["used"], c["withdrawn"]
    room = Decimal(plan.room) if plan.room_set else None
    remaining = None if room is None else room - contributed
    # Codes plus numbers; the page writes the sentence in the member's language.
    warnings = []
    if room is None:
        warnings.append({"level": "info", "code": "needs_room", "year": plan.year})
    elif plan.kind == "rrsp":
        if remaining < -RRSP_BUFFER:
            warnings.append({"level": "danger", "code": "rrsp_over_buffer", "amount": f2(-remaining - RRSP_BUFFER)})
        elif remaining < 0:
            warnings.append({"level": "warn", "code": "rrsp_in_buffer", "amount": f2(-remaining)})
    elif remaining < 0:
        warnings.append({"level": "danger", "code": "over_room", "amount": f2(-remaining)})
    if plan.kind == "tfsa" and withdrawn > 0:
        warnings.append({"level": "info", "code": "tfsa_withdrawn", "amount": f2(withdrawn), "year": plan.year + 1})
    if plan.kind == "fhsa" and withdrawn > 0:
        warnings.append({"level": "info", "code": "fhsa_withdrawn", "amount": f2(withdrawn)})
    ids = registered.plan_account_ids(db, plan)
    names = dict(db.execute(select(Account.id, Account.name).where(Account.id.in_(ids))).all()) if ids else {}
    return {"id": plan.id, "kind": plan.kind, "label": KINDS[plan.kind], "year": plan.year,
            "room": None if room is None else f2(room), "room_set": room is not None,
            "account_id": plan.account_id, "accounts": [{"id": i, "name": names.get(i, "")} for i in ids],
            "notes": plan.notes, "contributed": f2(contributed), "withdrawn": f2(withdrawn),
            "remaining": None if remaining is None else f2(remaining),
            "percent": round(float(contributed / room * 100), 1) if room else None,
            "by_type": {k: f2(v) for k, v in c["by_type"].items()}, "lines": c["lines"], "untyped": c["untyped"],
            "entries": [_entry_out(e) for e in c["entries"]], "warnings": warnings,
            "estimate": registered.estimate(plan, c, history)}


def all_summaries(db: Session, user: User) -> list[dict]:
    plans = list(db.scalars(select(RegisteredPlan).where(RegisteredPlan.user_id == user.id)
                            .order_by(RegisteredPlan.year.desc(), RegisteredPlan.kind)))
    counted = {p.id: registered.counts(db, p) for p in plans}
    by_kind: dict[str, list] = {}
    for p in plans:
        by_kind.setdefault(p.kind, []).append((p, counted[p.id]))
    return [summary(db, p, history=by_kind[p.kind], counted=counted[p.id]) for p in plans]
