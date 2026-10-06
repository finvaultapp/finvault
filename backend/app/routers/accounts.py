from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, owned
from ..models import Account, Transaction, User
from ..importers.registered import suggest_kind
from ..services import receipts, registered
from ..services.currency import Converter
from ..services.invest import Portfolio
from ..services.ledger import account_balances
from ..services.reports import f2

router = APIRouter(prefix="/api/accounts", tags=["accounts"])
TYPES = "^(checking|savings|credit_card|investment|cash|loan|other)$"
REGISTERED = "^(tfsa|fhsa|rrsp)$"


def account_out(a: Account, balance: Decimal, converted: Decimal | None, tx_count: int = 0, last_date=None) -> dict:
    return {"id": a.id, "name": a.name, "institution": a.institution, "type": a.type, "currency": a.currency,
            "country": a.country, "opening_balance": f2(a.opening_balance),
            "opening_date": a.opening_date.isoformat() if a.opening_date else None,
            "import_preset": a.import_preset, "is_archived": a.is_archived, "balance": f2(balance),
            "balance_converted": None if converted is None else f2(converted),
            "synced": a.sync_connection_id is not None, "transaction_count": tx_count,
            "last_transaction": last_date.isoformat() if last_date else None,
            "registered_kind": a.registered_kind,
            "registered_suggestion": None if a.registered_kind else suggest_kind(a.name, a.institution or "")}


@router.get("")
def list_accounts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    balances = account_balances(db, user.id)
    conv = Converter(db, user.base_currency)
    stats = {aid: (n, last) for aid, n, last in db.execute(
        select(Transaction.account_id, func.count(Transaction.id), func.max(Transaction.date))
        .where(Transaction.user_id == user.id).group_by(Transaction.account_id))}
    holdings = Portfolio(db, user).account_values(date.today(), conv)  # investment accounts: cash + holdings
    items = []
    for a in db.scalars(select(Account).where(Account.user_id == user.id).order_by(Account.is_archived, Account.name)):
        cash = balances.get(a.id, Decimal(0))
        bal = cash + holdings.get(a.id, Decimal(0))
        n, last = stats.get(a.id, (0, None))
        out = account_out(a, bal, conv.convert(bal, a.currency), n, last)
        if a.id in holdings:
            out |= {"cash_balance": f2(cash), "holdings_value": f2(holdings[a.id])}
        items.append(out)
    return {"items": items, "base_currency": user.base_currency, "warnings": conv.warnings()}


class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    institution: str = Field(default="", max_length=120)
    type: str = Field(default="checking", pattern=TYPES)
    currency: str = Field(default="CAD", min_length=3, max_length=3)
    country: str = Field(default="CA", max_length=2)
    opening_balance: Decimal = Decimal("0")
    opening_date: date | None = None
    import_preset: str | None = None
    registered_kind: str | None = Field(default=None, pattern=REGISTERED)


class AccountPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    institution: str | None = None
    type: str | None = Field(default=None, pattern=TYPES)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    country: str | None = Field(default=None, max_length=2)
    opening_balance: Decimal | None = None
    opening_date: date | None = None
    import_preset: str | None = None
    is_archived: bool | None = None
    registered_kind: str | None = Field(default=None, pattern=REGISTERED)


@router.post("")
def create_account(body: AccountIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = Account(user_id=user.id, **body.model_dump(exclude={"opening_balance", "currency", "country"}),
                opening_balance=body.opening_balance, currency=body.currency.upper(),
                country=body.country.upper())
    db.add(a)
    db.commit()
    return account_out(a, body.opening_balance, None)


@router.patch("/{account_id}")
def update_account(account_id: int, body: AccountPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = owned(db, Account, account_id, user)
    data = body.model_dump(exclude_unset=True)
    if "opening_balance" in data:
        data["opening_balance"] = data["opening_balance"] or Decimal("0")
    for k in ("currency", "country"):
        if data.get(k):
            data[k] = data[k].upper()
    if data.get("country") == "CA" and a.sync_connection_id:
        a.sync_connection_id, a.external_id = None, None  # Canadian accounts are never synced
    newly_registered = bool(data.get("registered_kind")) and data["registered_kind"] != a.registered_kind
    for k, v in data.items():
        setattr(a, k, v)
    typed = registered.backfill(db, a) if newly_registered else 0
    db.commit()
    return {"ok": True, "typed": typed}


@router.delete("/{account_id}")
def delete_account(account_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = owned(db, Account, account_id, user)
    tx_ids = list(db.scalars(select(Transaction.id).where(Transaction.account_id == a.id)))
    receipts.unlink_for_transactions(db, tx_ids)
    db.delete(a)
    db.commit()
    return {"ok": True}


class ReconcileIn(BaseModel):
    balance: Decimal
    on: date | None = None


@router.post("/{account_id}/reconcile")
def reconcile(account_id: int, body: ReconcileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Set the opening balance so the running balance matches the bank's statement balance."""
    a = owned(db, Account, account_id, user)
    on = body.on or date.today()
    if a.opening_date and a.opening_date > on:
        raise HTTPException(422, "The statement date is before the account's opening date.")
    current = account_balances(db, user.id, on).get(a.id, Decimal(0))
    diff = body.balance - current
    a.opening_balance = Decimal(a.opening_balance or 0) + diff
    db.commit()
    return {"adjusted_by": f2(diff)}
