import datetime as dt
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config, settings_store
from ..db import get_db
from ..deps import current_user
from ..models import Account, Asset, ExchangeRate, Goal, User
from ..services.currency import Converter, fetch_ecb_rates

router = APIRouter(prefix="/api/currency", tags=["currency"])


def _used_currencies(db: Session) -> set[str]:
    used = set(db.scalars(select(Account.currency).distinct())) | set(db.scalars(select(Asset.currency).distinct()))
    used |= set(db.scalars(select(Goal.currency).distinct())) | set(db.scalars(select(User.base_currency).distinct()))
    return {c for c in used if c}


@router.get("/status")
def status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Which currencies are in use, and which can't be converted to this user's base currency."""
    conv = Converter(db, user.base_currency)
    mine = set(db.scalars(select(Account.currency).where(Account.user_id == user.id).distinct()))
    mine |= set(db.scalars(select(Asset.currency).where(Asset.user_id == user.id).distinct()))
    pairs = []
    for c in sorted(mine - {user.base_currency}):
        r = conv.rate(c)
        pairs.append({"currency": c, "rate": float(r) if r is not None else None})
    return {"base_currency": user.base_currency, "pairs": pairs,
            "missing": [p["currency"] for p in pairs if p["rate"] is None],
            "fetch_enabled": bool(settings_store.get(db, "fx_fetch_enabled"))}


@router.get("/rates")
def list_rates(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [{"id": r.id, "base": r.base, "quote": r.quote, "date": r.date.isoformat(), "rate": float(r.rate),
             "source": r.source}
            for r in db.scalars(select(ExchangeRate).order_by(ExchangeRate.date.desc()).limit(500))]


class RateIn(BaseModel):
    base: str = Field(min_length=3, max_length=3)
    quote: str = Field(min_length=3, max_length=3)
    rate: Decimal = Field(gt=0)
    date: dt.date | None = None


@router.post("/rates")
def set_rate(body: RateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    base, quote, on = body.base.upper(), body.quote.upper(), body.date or date.today()
    if base == quote:
        raise HTTPException(422, "Pick two different currencies.")
    r = db.scalar(select(ExchangeRate).where(ExchangeRate.base == base, ExchangeRate.quote == quote, ExchangeRate.date == on))
    if r:
        r.rate, r.source = body.rate, "manual"
    else:
        db.add(ExchangeRate(base=base, quote=quote, date=on, rate=body.rate, source="manual"))
    db.commit()
    return {"ok": True}


@router.delete("/rates/{rate_id}")
def delete_rate(rate_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(ExchangeRate, rate_id)
    if r:
        db.delete(r)
        db.commit()
    return {"ok": True}


@router.post("/rates/fetch")
def fetch(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not settings_store.get(db, "fx_fetch_enabled"):
        raise HTTPException(403, "Fetching rates is turned off. An admin can enable it in Admin → Settings.")
    try:
        n = fetch_ecb_rates(db, user.base_currency, list(_used_currencies(db)), config.FX_API_URL)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Couldn't reach the rate service: {exc}") from exc
    return {"updated": n}
