"""Cash-flow forecast, debt payoff planner, recurring-charge alerts and year in review."""
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, owned
from ..models import Account, Asset, User
from ..models_plan import ChargeAlert, DebtSetting, PlanPrefs
from ..services import charge_alerts, debt, forecast, year_review
from ..services import recurring as rec
from ..services.reports import f2

router = APIRouter(prefix="/api", tags=["plan ahead"])


# --- Forecast ---------------------------------------------------------------------------

@router.get("/forecast")
def get_forecast(days: int = Query(90, ge=7, le=180), user: User = Depends(current_user), db: Session = Depends(get_db)):
    rec.post_due(db, user.id)
    return forecast.forecast(db, user, days)


@router.get("/forecast/warnings")
def forecast_warnings(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Just the low-balance warnings, for the dashboard banner."""
    data = forecast.forecast(db, user, 90)
    return {"warnings": data["warnings"], "cushion": data["cushion"]}


class CushionIn(BaseModel):
    cushion: float = Field(ge=0, le=10_000_000)


@router.put("/forecast/settings")
def forecast_settings(body: CushionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    forecast.set_cushion(db, user, Decimal(str(body.cushion)))
    return {"cushion": body.cushion}


# --- Debts ------------------------------------------------------------------------------

@router.get("/debts")
def get_debts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = debt.list_debts(db, user)
    prefs = db.get(PlanPrefs, user.id)
    data["budget"] = f2(prefs.debt_budget) if prefs and prefs.debt_budget is not None else None
    return data


class DebtIn(BaseModel):
    apr: float = Field(ge=0, le=100)
    min_payment: float = Field(ge=0, le=10_000_000)
    kind: str | None = Field(default=None, pattern="^(card|loan|mortgage)$")


@router.put("/debts/{source}/{ref_id}")
def set_debt(source: str, ref_id: int, body: DebtIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if source == "account":
        a = owned(db, Account, ref_id, user)
        if a.type not in ("credit_card", "loan"):
            raise HTTPException(422, "Only credit card and loan accounts are debts.")
    elif source == "asset":
        a = owned(db, Asset, ref_id, user)
        if not a.is_liability:
            raise HTTPException(422, "Only debts (liabilities) can be planned.")
    else:
        raise HTTPException(404, "Unknown debt")
    s = db.scalar(select(DebtSetting).where(DebtSetting.user_id == user.id, DebtSetting.source == source,
                                            DebtSetting.ref_id == ref_id))
    if s is None:
        s = DebtSetting(user_id=user.id, source=source, ref_id=ref_id)
        db.add(s)
    s.apr, s.min_payment, s.kind = Decimal(str(body.apr)), Decimal(str(body.min_payment)), body.kind
    db.commit()
    return {"ok": True}


class PlanIn(BaseModel):
    budget: float = Field(ge=0, le=10_000_000)
    extra: float = Field(default=0, ge=0, le=10_000_000)
    remember: bool = True


@router.post("/debts/plan")
def debt_plan(body: PlanIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.remember:
        prefs = db.get(PlanPrefs, user.id)
        if prefs is None:
            prefs = PlanPrefs(user_id=user.id, cushion=Decimal(0))
            db.add(prefs)
        prefs.debt_budget = Decimal(str(body.budget))
        db.commit()
    return debt.plan(db, user, Decimal(str(body.budget)), Decimal(str(body.extra)))


@router.get("/debts/mortgage-payment")
def mortgage_payment(principal: float = Query(gt=0), apr: float = Query(ge=0, le=100), years: int = Query(25, ge=1, le=40),
                     _: User = Depends(current_user)):
    return {"payment": f2(debt.mortgage_payment(Decimal(str(principal)), Decimal(str(apr)), years)),
            "monthly_rate": float(debt.monthly_rate(Decimal(str(apr)), "mortgage"))}


# --- Charge alerts ----------------------------------------------------------------------

@router.get("/alerts/charges")
def list_charge_alerts(refresh: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if refresh:
        charge_alerts.run(db, user)
    accounts = {a.id: a for a in db.scalars(select(Account).where(Account.user_id == user.id))}
    rows = db.scalars(select(ChargeAlert).where(ChargeAlert.user_id == user.id, ChargeAlert.dismissed_at.is_(None))
                      .order_by(ChargeAlert.last_date.desc(), ChargeAlert.id.desc()))
    return [charge_alerts.alert_out(a, accounts) for a in rows]


@router.post("/alerts/charges/{alert_id}/dismiss")
def dismiss_charge_alert(alert_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = owned(db, ChargeAlert, alert_id, user)
    a.dismissed_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


# --- Year in review ---------------------------------------------------------------------

@router.get("/reports/year-review")
def year_in_review(year: int | None = Query(None, ge=1990, le=2100), user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    return year_review.summary(db, user, year or date.today().year)
