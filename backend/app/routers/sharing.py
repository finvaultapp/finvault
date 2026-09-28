"""Splits, shared expenses with people, settle-up, and transfer matching."""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, owned
from ..models import Category, Person, Settlement, Share, Transaction, TransactionSplit, User
from ..services import transfers as xfer
from ..services.reports import f2

router = APIRouter(prefix="/api", tags=["sharing"])


# --- Splits & shares on one transaction -------------------------------------------------

def detail(db: Session, t: Transaction) -> dict:
    splits = [{"id": s.id, "category_id": s.category_id, "amount": f2(s.amount), "note": s.note}
              for s in db.scalars(select(TransactionSplit).where(TransactionSplit.transaction_id == t.id))]
    people = {p.id: p.name for p in db.scalars(select(Person).where(Person.user_id == t.user_id))}
    shares = [{"id": s.id, "person_id": s.person_id, "person": people.get(s.person_id), "amount": f2(s.amount)}
              for s in db.scalars(select(Share).where(Share.transaction_id == t.id))]
    return {"transaction_id": t.id, "amount": f2(t.amount), "splits": splits, "shares": shares,
            "transfer_id": t.transfer_id}


@router.get("/transactions/{tid}/detail")
def get_detail(tid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return detail(db, owned(db, Transaction, tid, user))


class SplitLine(BaseModel):
    category_id: int | None = None
    amount: Decimal
    note: str = Field(default="", max_length=200)


class SplitsIn(BaseModel):
    lines: list[SplitLine]


@router.put("/transactions/{tid}/splits")
def set_splits(tid: int, body: SplitsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Replace the splits. An empty list removes the split. Lines must add up to the transaction amount."""
    t = owned(db, Transaction, tid, user)
    for line in body.lines:
        if line.category_id:
            owned(db, Category, line.category_id, user)
    if body.lines:
        total = sum((line.amount for line in body.lines), Decimal(0))
        if abs(total - Decimal(t.amount)) > Decimal("0.01"):
            raise HTTPException(422, f"The parts add up to {total:.2f} but the transaction is {Decimal(t.amount):.2f}.")
        if len(body.lines) < 2:
            raise HTTPException(422, "A split needs at least two parts. To change the category, just pick one.")
    for s in db.scalars(select(TransactionSplit).where(TransactionSplit.transaction_id == t.id)):
        db.delete(s)
    for line in body.lines:
        db.add(TransactionSplit(transaction_id=t.id, category_id=line.category_id,
                                amount=line.amount, note=line.note))
    db.commit()
    return detail(db, t)


class ShareLine(BaseModel):
    person_id: int
    amount: Decimal = Field(gt=0)


class SharesIn(BaseModel):
    shares: list[ShareLine]


@router.put("/transactions/{tid}/shares")
def set_shares(tid: int, body: SharesIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Who owes you part of this payment. Only for money you paid out."""
    t = owned(db, Transaction, tid, user)
    if body.shares and t.amount >= 0:
        raise HTTPException(422, "You can only share a payment you made (money out).")
    total = sum((s.amount for s in body.shares), Decimal(0))
    if total > -Decimal(t.amount) + Decimal("0.01"):
        raise HTTPException(422, "Shares can't add up to more than the payment.")
    for s in body.shares:
        owned(db, Person, s.person_id, user)
    for s in db.scalars(select(Share).where(Share.transaction_id == t.id)):
        db.delete(s)
    for s in body.shares:
        db.add(Share(transaction_id=t.id, person_id=s.person_id, amount=s.amount))
    db.commit()
    return detail(db, t)


# --- People & balances ---------------------------------------------------------------

def balances(db: Session, user: User) -> list[dict]:
    people = list(db.scalars(select(Person).where(Person.user_id == user.id).order_by(Person.name)))
    owed = defaultdict(Decimal)
    for person_id, amount in db.execute(select(Share.person_id, Share.amount).join(Transaction, Transaction.id == Share.transaction_id)
                                        .where(Transaction.user_id == user.id)):
        owed[person_id] += Decimal(amount)
    for person_id, amount in db.execute(select(Settlement.person_id, Settlement.amount).where(Settlement.user_id == user.id)):
        owed[person_id] -= Decimal(amount)
    return [{"id": p.id, "name": p.name, "is_archived": p.is_archived, "balance": f2(owed[p.id]),
             "status": "owes you" if owed[p.id] > 0 else "you owe" if owed[p.id] < 0 else "settled"} for p in people]


@router.get("/people")
def list_people(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"people": balances(db, user), "currency": user.base_currency}


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    is_archived: bool = False


@router.post("/people")
def add_person(body: PersonIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = Person(user_id=user.id, name=body.name.strip())
    db.add(p)
    db.commit()
    return {"id": p.id, "name": p.name}


@router.patch("/people/{pid}")
def edit_person(pid: int, body: PersonIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned(db, Person, pid, user)
    p.name, p.is_archived = body.name.strip(), body.is_archived
    db.commit()
    return {"ok": True}


@router.delete("/people/{pid}")
def delete_person(pid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, Person, pid, user))
    db.commit()
    return {"ok": True}


@router.get("/people/{pid}/activity")
def person_activity(pid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned(db, Person, pid, user)
    items = []
    for s, t in db.execute(select(Share, Transaction).join(Transaction, Transaction.id == Share.transaction_id)
                           .where(Share.person_id == p.id)):
        items.append({"kind": "share", "date": t.date.isoformat(), "description": t.payee or t.description,
                      "amount": f2(s.amount), "transaction_id": t.id, "id": s.id})
    for st in db.scalars(select(Settlement).where(Settlement.person_id == p.id)):
        items.append({"kind": "settlement", "date": st.date.isoformat(), "description": st.note or "Settle up",
                      "amount": f2(-st.amount), "transaction_id": st.transaction_id, "id": st.id})
    items.sort(key=lambda i: i["date"], reverse=True)
    return {"person": {"id": p.id, "name": p.name}, "items": items}


class SettleIn(BaseModel):
    amount: Decimal
    date: date
    note: str = Field(default="", max_length=200)
    transaction_id: int | None = None


@router.post("/people/{pid}/settle")
def settle(pid: int, body: SettleIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Record a payment. Positive: they paid you. Negative: you paid them.

    Linking the bank line of that payment marks it as a reimbursement so it doesn't count as income.
    """
    p = owned(db, Person, pid, user)
    if body.transaction_id:
        t = owned(db, Transaction, body.transaction_id, user)
        name = "Remboursement" if user.locale == "fr" else "Reimbursement"
        cat = db.scalar(select(Category).where(Category.user_id == user.id, Category.name.in_(["Reimbursement", "Remboursement"])))
        if not cat:
            cat = Category(user_id=user.id, name=name, kind="transfer", color="#8a96a0")
            db.add(cat)
            db.flush()
        t.category_id = cat.id
    db.add(Settlement(user_id=user.id, person_id=p.id, amount=body.amount, date=body.date,
                      note=body.note, transaction_id=body.transaction_id))
    db.commit()
    return {"people": balances(db, user)}


@router.delete("/settlements/{sid}")
def delete_settlement(sid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, Settlement, sid, user))
    db.commit()
    return {"ok": True}


# --- Transfer matching ------------------------------------------------------------------

@router.get("/transfers/suggestions")
def transfer_suggestions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [xfer.serialize(p) for p in xfer.candidates(db, user)]


class PairIn(BaseModel):
    out_id: int
    in_id: int


@router.post("/transfers/match")
def match_transfer(body: PairIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    out, inc = owned(db, Transaction, body.out_id, user), owned(db, Transaction, body.in_id, user)
    if not (out.amount < 0 < inc.amount):
        raise HTTPException(422, "Pick the money-out line first and the money-in line second.")
    try:
        xfer.match(db, user, out, inc)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    return {"ok": True}


@router.post("/transfers/auto")
def auto_match(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"matched": xfer.auto_match(db, user)}


@router.delete("/transfers/{tid}")
def unmatch_transfer(tid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    xfer.unmatch(db, user, owned(db, Transaction, tid, user))
    db.commit()
    return {"ok": True}
