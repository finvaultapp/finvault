"""Registered accounts (TFSA/RRSP/FHSA) and the year-end tax helper."""
import csv
import io
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, owned
from ..models import Account, Category, PlanEntry, RegisteredPlan, Transaction, User
from ..services import plans as plan_svc
from ..services import tax as tax_svc

router = APIRouter(prefix="/api", tags=["plans"])


@router.get("/plans")
def list_plans(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return plan_svc.all_summaries(db, user)


class PlanIn(BaseModel):
    kind: str = Field(pattern="^(tfsa|rrsp|fhsa)$")
    year: int = Field(ge=2009, le=2100)
    room: Decimal | None = Field(default=None, ge=0)  # None: not entered yet (CRA's figure still to come)
    account_id: int | None = None
    notes: str = Field(default="", max_length=2000)


@router.post("/plans")
def create_plan(body: PlanIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.account_id:
        owned(db, Account, body.account_id, user)
    if db.scalar(select(RegisteredPlan).where(RegisteredPlan.user_id == user.id, RegisteredPlan.kind == body.kind,
                                              RegisteredPlan.year == body.year)):
        raise HTTPException(409, f"You already have a {body.kind.upper()} entry for {body.year}. Edit that one instead.")
    p = RegisteredPlan(user_id=user.id, kind=body.kind, year=body.year, room=body.room or 0,
                       room_set=body.room is not None, account_id=body.account_id, notes=body.notes)
    db.add(p)
    db.commit()
    return plan_svc.summary(db, p)


@router.patch("/plans/{pid}")
def update_plan(pid: int, body: PlanIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned(db, RegisteredPlan, pid, user)
    if body.account_id:
        owned(db, Account, body.account_id, user)
    p.kind, p.year, p.account_id, p.notes = body.kind, body.year, body.account_id, body.notes
    p.room, p.room_set = body.room or 0, body.room is not None
    db.commit()
    return plan_svc.summary(db, p)


@router.delete("/plans/{pid}")
def delete_plan(pid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, RegisteredPlan, pid, user))
    db.commit()
    return {"ok": True}


class EntryIn(BaseModel):
    date: date
    amount: Decimal
    note: str = Field(default="", max_length=200)


@router.post("/plans/{pid}/entries")
def add_entry(pid: int, body: EntryIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned(db, RegisteredPlan, pid, user)
    if body.date.year != p.year:
        raise HTTPException(422, f"That date isn't in {p.year}. Add it to that year's entry instead.")
    db.add(PlanEntry(plan_id=p.id, date=body.date, amount=body.amount, note=body.note))
    db.commit()
    return plan_svc.summary(db, p)


@router.delete("/plans/{pid}/entries/{eid}")
def delete_entry(pid: int, eid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned(db, RegisteredPlan, pid, user)
    e = db.get(PlanEntry, eid)
    if not e or e.plan_id != p.id:
        raise HTTPException(404, "Entry not found")
    db.delete(e)
    db.commit()
    return plan_svc.summary(db, p)


# --- Tax helper ---------------------------------------------------------------

@router.get("/tax/summary")
def tax_summary(year: int = Query(default_factory=lambda: date.today().year - (1 if date.today().month < 5 else 0)),
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    return tax_svc.summary(db, user, year) | {"tags": tax_svc.TAGS}


@router.get("/tax/export")
def tax_export(year: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = tax_svc.summary(db, user, year)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"FinVault tax summary {year}", f"Amounts in {s['currency']}", "Confirm eligibility with your accountant or CRA."])
    w.writerow([])
    w.writerow(["Group", "Date", "Description", "Account", "Category", "Amount", "Note"])
    for g in s["groups"]:
        for i in g["items"]:
            w.writerow([g["label"], i["date"], i["description"], i["account"], i["category"] or "", f"{i['amount']:.2f}", i["note"] or ""])
        w.writerow([f"{g['label']} total", "", "", "", "", f"{g['total']:.2f}", ""])
    w.writerow(["All groups total", "", "", "", "", f"{s['total']:.2f}", ""])
    return Response("﻿" + buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="finvault-tax-{year}.csv"'})


class TagIn(BaseModel):
    tax_tag: str | None = Field(default=None, pattern="^(medical|childcare|donations|moving|home_office|other_deductible|none)$")


@router.put("/categories/{cid}/tax-tag")
def tag_category(cid: int, body: TagIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = owned(db, Category, cid, user)
    c.tax_tag = None if body.tax_tag in (None, "none") else body.tax_tag
    db.commit()
    return {"ok": True}


@router.put("/transactions/{tid}/tax-tag")
def tag_transaction(tid: int, body: TagIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = owned(db, Transaction, tid, user)
    t.tax_tag = body.tax_tag
    db.commit()
    return {"ok": True}
