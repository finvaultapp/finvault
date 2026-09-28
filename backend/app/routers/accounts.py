from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, owned
from ..models import Account, Transaction, User
from ..services.currency import Converter
from ..services.ledger import account_balances
from ..services.reports import f2

router = APIRouter(prefix="/api/accounts", tags=["accounts"])
TYPES = "^(checking|savings|credit_card|investment|cash|loan|other)$"


def account_out(a: Account, balance: Decimal, converted: Decimal | None, tx_count: int = 0, last_date=None) -> dict:
    return {"id": a.id, "name": a.name, "institution": a.institution, "type": a.type, "currency": a.currency,
            "country": a.country, "opening_balance": f2(a.opening_balance),
            "opening_date": a.opening_date.isoformat() if a.opening_date else None,
            "import_preset": a.import_preset, "is_archived": a.is_archived, "balance": f2(balance),
            "balance_converted": None if converted is None else f2(converted),
            "synced": a.sync_connection_id is not None, "transaction_count": tx_count,
            "last_transaction": last_date.isoformat() if last_date else None}


@router.get("")
def list_accounts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    balances = account_balances(db, user.id)
    conv = Converter(db, user.base_currency)
    stats = {aid: (n, last) for aid, n, last in db.execute(
        select(Transaction.account_id, func.count(Transaction.id), func.max(Transaction.date))
        .where(Transaction.user_id == user.id).group_by(Transaction.account_id))}
    items = []
    for a in db.scalars(select(Account).where(Account.user_id == user.id).order_by(Account.is_archived, Account.name)):
        bal = balances.get(a.id, Decimal(0))
        n, last = stats.get(a.id, (0, None))
        items.append(account_out(a, bal, conv.convert(bal, a.currency), n, last))
    return {"items": items, "base_currency": user.base_currency, "warnings": conv.warnings()}


class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    institution: str = Field(default="", max_length=120)
    type: str = Field(default="checking", pattern=TYPES)
    currency: str = Field(default="CAD", min_length=3, max_length=3)
    country: str = Field(default="CA", max_length=2)
    opening_balance: float = 0
    opening_date: date | None = None
    import_preset: str | None = None


class AccountPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    institution: str | None = None
    type: str | None = Field(default=None, pattern=TYPES)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    country: str | None = Field(default=None, max_length=2)
    opening_balance: float | None = None
    opening_date: date | None = None
    import_preset: str | None = None
    is_archived: bool | None = None


@router.post("")
def create_account(body: AccountIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = Account(user_id=user.id, **body.model_dump(exclude={"opening_balance", "currency", "country"}),
                opening_balance=Decimal(str(body.opening_balance)), currency=body.currency.upper(),
                country=body.country.upper())
    db.add(a)
    db.commit()
    return account_out(a, Decimal(str(body.opening_balance)), None)


@router.patch("/{account_id}")
def update_account(account_id: int, body: AccountPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = owned(db, Account, account_id, user)
    data = body.model_dump(exclude_unset=True)
    if "opening_balance" in data:
        data["opening_balance"] = Decimal(str(data["opening_balance"] or 0))
    for k in ("currency", "country"):
        if data.get(k):
            data[k] = data[k].upper()
    if data.get("country") == "CA" and a.sync_connection_id:
        a.sync_connection_id, a.external_id = None, None  # Canadian accounts are never synced
    for k, v in data.items():
        setattr(a, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/{account_id}")
def delete_account(account_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = owned(db, Account, account_id, user)
    db.delete(a)
    db.commit()
    return {"ok": True}


class ReconcileIn(BaseModel):
    balance: float
    on: date | None = None


@router.post("/{account_id}/reconcile")
def reconcile(account_id: int, body: ReconcileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Set the opening balance so the running balance matches the bank's statement balance."""
    a = owned(db, Account, account_id, user)
    on = body.on or date.today()
    if a.opening_date and a.opening_date > on:
        raise HTTPException(422, "The statement date is before the account's opening date.")
    current = account_balances(db, user.id, on).get(a.id, Decimal(0))
    diff = Decimal(str(body.balance)) - current
    a.opening_balance = Decimal(a.opening_balance or 0) + diff
    db.commit()
    return {"adjusted_by": f2(diff)}
