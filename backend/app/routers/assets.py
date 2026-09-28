import datetime as dt
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, owned
from ..models import Asset, AssetValue, User
from ..services.currency import Converter
from ..services.reports import f2

router = APIRouter(prefix="/api/assets", tags=["assets"])
LIABILITY_KINDS = {"mortgage", "loan", "other_debt"}


def asset_out(a: Asset, conv: Converter) -> dict:
    latest = a.values[-1] if a.values else None
    value = Decimal(latest.value) if latest else None
    converted = conv.convert(value, a.currency) if value is not None else None
    return {"id": a.id, "name": a.name, "kind": a.kind, "is_liability": a.is_liability, "currency": a.currency,
            "notes": a.notes, "value": f2(value) if value is not None else None,
            "value_converted": f2(converted) if converted is not None else None,
            "as_of": latest.date.isoformat() if latest else None,
            "history": [{"id": v.id, "date": v.date.isoformat(), "value": f2(v.value)} for v in a.values]}


@router.get("")
def list_assets(user: User = Depends(current_user), db: Session = Depends(get_db)):
    conv = Converter(db, user.base_currency)
    items = [asset_out(a, conv) for a in db.scalars(select(Asset).where(Asset.user_id == user.id).order_by(Asset.is_liability, Asset.name))]
    return {"items": items, "base_currency": user.base_currency, "warnings": conv.warnings()}


class AssetIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="other", pattern="^(real_estate|vehicle|investment|retirement|cash|valuables|other|mortgage|loan|other_debt)$")
    currency: str = Field(default="CAD", min_length=3, max_length=3)
    notes: str = ""
    value: Decimal | None = None
    as_of: date | None = None


@router.post("")
def create_asset(body: AssetIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = Asset(user_id=user.id, name=body.name, kind=body.kind, is_liability=body.kind in LIABILITY_KINDS,
              currency=body.currency.upper(), notes=body.notes)
    if body.value is not None:
        a.values.append(AssetValue(date=body.as_of or date.today(), value=abs(body.value)))
    db.add(a)
    db.commit()
    return {"id": a.id}


@router.patch("/{asset_id}")
def update_asset(asset_id: int, body: AssetIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = owned(db, Asset, asset_id, user)
    a.name, a.kind, a.currency, a.notes = body.name, body.kind, body.currency.upper(), body.notes
    a.is_liability = body.kind in LIABILITY_KINDS
    db.commit()
    return {"ok": True}


@router.delete("/{asset_id}")
def delete_asset(asset_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, Asset, asset_id, user))
    db.commit()
    return {"ok": True}


class ValueIn(BaseModel):
    date: dt.date
    value: Decimal


@router.post("/{asset_id}/values")
def add_value(asset_id: int, body: ValueIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = owned(db, Asset, asset_id, user)
    existing = next((v for v in a.values if v.date == body.date), None)
    if existing:
        existing.value = abs(body.value)
    else:
        db.add(AssetValue(asset_id=a.id, date=body.date, value=abs(body.value)))
    db.commit()
    return {"ok": True}


@router.delete("/{asset_id}/values/{value_id}")
def delete_value(asset_id: int, value_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = owned(db, Asset, asset_id, user)
    v = db.get(AssetValue, value_id)
    if not v or v.asset_id != a.id:
        raise HTTPException(404, "Value not found")
    db.delete(v)
    db.commit()
    return {"ok": True}
