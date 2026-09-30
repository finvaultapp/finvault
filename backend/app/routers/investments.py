"""Investments: holdings, prices, activity, imports and ACB for TFSA/RRSP/FHSA/non-registered accounts."""
import datetime as dt
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import settings_store
from ..db import get_db
from ..deps import current_user, owned
from ..importers.holdings import MAX_BYTES, InvestParseResult, parse_investment_file
from ..models import Account, User
from ..models_invest import (ACTIVITY_KINDS, ASSET_CLASSES, REGISTRATIONS, Holding, InvestAccountInfo, InvestImport,
                             InvestmentActivity, Security, SecurityPrice)
from ..services import invest
from ..services.currency import Converter
from ..services.invest import ACB_NOTE, Portfolio, f2, fq
from ..services.ledger import account_balances

router = APIRouter(prefix="/api/invest", tags=["investments"])
CA_EXCHANGES = {"TSX", "TSXV", "NEO", "CSE"}
US_EXCHANGES = {"NYSE", "NASDAQ", "ARCA", "AMEX", "BATS", "CBOE"}


def _pct(gain: Decimal | None, cost: Decimal | None) -> float | None:
    if gain is None or not cost:
        return None
    return round(float(gain / cost * 100), 2)


# --- Securities ---------------------------------------------------------------------

def guess_asset_class(name: str, security_type: str = "", symbol: str = "") -> str:
    text = f"{name} {security_type}".lower()
    if any(w in text for w in ("bitcoin", "ethereum", "crypto")) or symbol.upper() in {"BTC", "ETH"}:
        return "crypto"
    if any(w in text for w in ("money market", "high interest savings", "cash management", "savings etf", "t-bill", "treasury bill")):
        return "cash"
    if any(w in text for w in ("bond", "fixed income", "obligation", "gic", "debenture")):
        return "fixed_income"
    if "all-equity" in text or "all equity" in text:
        return "equity"
    if any(w in text for w in ("balanced", "growth etf portfolio", "conservative", "income portfolio", "asset allocation")):
        return "balanced"
    if "reit" in text or "real estate" in text:
        return "real_estate"
    if any(w in text for w in ("gold", "silver", "commodit")):
        return "commodity"
    return "equity"


def _default_currency(exchange: str, fallback: str) -> str:
    ex = (exchange or "").upper()
    if ex in CA_EXCHANGES:
        return "CAD"
    if ex in US_EXCHANGES:
        return "USD"
    return fallback


def find_or_create_security(db: Session, user: User, symbol: str, exchange: str = "", name: str = "",
                            currency: str | None = None, fallback_currency: str = "CAD", security_type: str = "") -> Security:
    symbol, exchange = symbol.strip().upper(), (exchange or "").strip().upper()
    same = list(db.scalars(select(Security).where(Security.user_id == user.id, Security.symbol == symbol)))
    match = next((s for s in same if s.exchange == exchange), None)
    if match is None and len(same) == 1 and (not exchange or not same[0].exchange):
        match = same[0]
    if match:
        if not match.name and name:
            match.name = name[:200]
        if not match.exchange and exchange:
            match.exchange = exchange
        return match
    sec = Security(user_id=user.id, symbol=symbol[:30], exchange=exchange[:20], name=(name or "")[:200],
                   currency=(currency or _default_currency(exchange, fallback_currency)).upper()[:3],
                   asset_class=guess_asset_class(name or "", security_type, symbol))
    db.add(sec)
    db.flush()
    return sec


def security_out(s: Security, latest=None) -> dict:
    return {"id": s.id, "symbol": s.symbol, "exchange": s.exchange, "name": s.name, "currency": s.currency,
            "asset_class": s.asset_class, "price_symbol": s.price_symbol,
            "price": fq(latest[1]) if latest else None, "price_date": latest[0].isoformat() if latest else None,
            "last_fetch_error": s.last_fetch_error,
            "last_fetch_at": s.last_fetch_at.isoformat() if s.last_fetch_at else None}


@router.get("/securities")
def list_securities(user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = Portfolio(db, user)
    return [security_out(s, p.latest_price(s.id)) for s in sorted(p.securities.values(), key=lambda s: s.symbol)]


class SecurityIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=30)
    exchange: str = Field(default="", max_length=20)
    name: str = Field(default="", max_length=200)
    currency: str = Field(default="CAD", min_length=3, max_length=3)
    asset_class: str = Field(default="equity", pattern=f"^({'|'.join(ASSET_CLASSES)})$")
    price_symbol: str | None = Field(default=None, max_length=40)


@router.post("/securities")
def create_security(body: SecurityIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    symbol, exchange = body.symbol.strip().upper(), body.exchange.strip().upper()
    if db.scalar(select(Security).where(Security.user_id == user.id, Security.symbol == symbol, Security.exchange == exchange)):
        raise HTTPException(409, "You already have this security.")
    s = Security(user_id=user.id, symbol=symbol, exchange=exchange, name=body.name, currency=body.currency.upper(),
                 asset_class=body.asset_class, price_symbol=(body.price_symbol or "").strip() or None)
    db.add(s)
    db.commit()
    return security_out(s)


class SecurityPatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    exchange: str | None = Field(default=None, max_length=20)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    asset_class: str | None = Field(default=None, pattern=f"^({'|'.join(ASSET_CLASSES)})$")
    price_symbol: str | None = Field(default=None, max_length=40)


@router.patch("/securities/{security_id}")
def update_security(security_id: int, body: SecurityPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = owned(db, Security, security_id, user)
    data = body.model_dump(exclude_unset=True)
    if "currency" in data and data["currency"]:
        data["currency"] = data["currency"].upper()
    if "exchange" in data:
        data["exchange"] = (data["exchange"] or "").upper()
    if "price_symbol" in data:
        data["price_symbol"] = (data["price_symbol"] or "").strip() or None
    for k, v in data.items():
        setattr(s, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/securities/{security_id}")
def delete_security(security_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Removes the security with its prices, positions and activity."""
    db.delete(owned(db, Security, security_id, user))
    db.commit()
    return {"ok": True}


# --- Prices -------------------------------------------------------------------------

@router.get("/securities/{security_id}/prices")
def list_prices(security_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = owned(db, Security, security_id, user)
    return [{"id": p.id, "date": p.date.isoformat(), "close": fq(p.close), "source": p.source}
            for p in db.scalars(select(SecurityPrice).where(SecurityPrice.security_id == s.id)
                                .order_by(SecurityPrice.date.desc()).limit(400))]


class PriceIn(BaseModel):
    close: float = Field(gt=0)
    date: dt.date | None = None


@router.post("/securities/{security_id}/prices")
def add_price(security_id: int, body: PriceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = owned(db, Security, security_id, user)
    invest.set_price(db, s.id, body.date or date.today(), Decimal(str(body.close)), "manual")
    db.commit()
    return {"ok": True}


@router.delete("/prices/{price_id}")
def delete_price(price_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.get(SecurityPrice, price_id)
    if not p or owned(db, Security, p.security_id, user) is None:
        raise HTTPException(404, "Price not found")
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.post("/prices/fetch")
def fetch_prices(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not settings_store.get(db, "prices_fetch_enabled"):
        raise HTTPException(403, "Fetching prices is turned off. An admin can enable it in Admin → Settings.")
    secs = invest.held_securities(db, user.id)
    if not secs:
        return {"updated": 0, "failed": [], "provider": "stooq"}
    return invest.fetch_prices(db, secs)


# --- Holdings and activity ----------------------------------------------------------

class HoldingIn(BaseModel):
    account_id: int
    security_id: int | None = None
    symbol: str | None = Field(default=None, max_length=30)
    exchange: str = Field(default="", max_length=20)
    name: str = Field(default="", max_length=200)
    quantity: float = Field(ge=0)
    cost_basis: float = Field(default=0, ge=0)
    as_of: dt.date | None = None
    price: float | None = Field(default=None, gt=0)


def _security_for(db: Session, user: User, account: Account, security_id, symbol, exchange="", name="", currency=None) -> Security:
    if security_id:
        return owned(db, Security, security_id, user)
    if not symbol:
        raise HTTPException(422, "Pick a security or type its symbol.")
    return find_or_create_security(db, user, symbol, exchange, name, currency, account.currency)


@router.put("/holdings")
def set_holding(body: HoldingIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Set a position by hand: this many units with this book cost (in the account's currency) on this date."""
    account = owned(db, Account, body.account_id, user)
    sec = _security_for(db, user, account, body.security_id, body.symbol, body.exchange, body.name)
    on = body.as_of or date.today()
    h = db.scalar(select(Holding).where(Holding.account_id == account.id, Holding.security_id == sec.id))
    if h is None:
        h = Holding(user_id=user.id, account_id=account.id, security_id=sec.id, quantity=Decimal(0), as_of=on)
        db.add(h)
    h.quantity, h.cost_basis, h.as_of, h.source, h.import_id = (
        Decimal(str(body.quantity)), Decimal(str(body.cost_basis)), on, "manual", None)
    if body.price:
        invest.set_price(db, sec.id, on, Decimal(str(body.price)), "manual")
    db.commit()
    return {"id": h.id, "security_id": sec.id}


@router.delete("/holdings/{holding_id}")
def delete_holding(holding_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, Holding, holding_id, user))
    db.commit()
    return {"ok": True}


def activity_out(a: InvestmentActivity, sec: Security | None) -> dict:
    return {"id": a.id, "account_id": a.account_id, "security_id": a.security_id, "symbol": sec.symbol if sec else None,
            "name": sec.name if sec else None, "date": a.date.isoformat(), "kind": a.kind, "quantity": fq(a.quantity),
            "price": fq(a.price), "amount": f2(a.amount), "commission": f2(a.commission), "currency": a.currency,
            "split_ratio": fq(a.split_ratio), "description": a.description, "imported": a.import_id is not None}


@router.get("/activities")
def list_activities(account_id: int | None = None, limit: int = 200, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    q = select(InvestmentActivity).where(InvestmentActivity.user_id == user.id)
    if account_id:
        q = q.where(InvestmentActivity.account_id == account_id)
    secs = {s.id: s for s in db.scalars(select(Security).where(Security.user_id == user.id))}
    rows = db.scalars(q.order_by(InvestmentActivity.date.desc(), InvestmentActivity.id.desc()).limit(min(limit, 1000)))
    return [activity_out(a, secs.get(a.security_id)) for a in rows]


class ActivityIn(BaseModel):
    account_id: int
    date: dt.date
    kind: str = Field(pattern=f"^({'|'.join(ACTIVITY_KINDS)})$")
    security_id: int | None = None
    symbol: str | None = Field(default=None, max_length=30)
    exchange: str = Field(default="", max_length=20)
    name: str = Field(default="", max_length=200)
    quantity: float = Field(default=0, ge=0)
    price: float | None = Field(default=None, ge=0)
    amount: float | None = Field(default=None, ge=0)
    commission: float = Field(default=0, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    split_ratio: float | None = Field(default=None, gt=0)
    description: str = Field(default="", max_length=500)


@router.post("/activities")
def create_activity(body: ActivityIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    account = owned(db, Account, body.account_id, user)
    sec = None
    if body.kind != "fee" or body.security_id or body.symbol:
        sec = _security_for(db, user, account, body.security_id, body.symbol, body.exchange, body.name)
    qty = Decimal(str(body.quantity))
    price = Decimal(str(body.price)) if body.price is not None else None
    amount = Decimal(str(body.amount)) if body.amount is not None else (qty * price if price is not None else None)
    if body.kind in {"buy", "sell"} and (not qty or amount is None):
        raise HTTPException(422, "A buy or sell needs a quantity and a price or amount.")
    if body.kind == "split" and not body.split_ratio:
        raise HTTPException(422, "A split needs a ratio, e.g. 2 for a 2-for-1 split.")
    if body.kind not in {"split"} and amount is None:
        raise HTTPException(422, "Enter the amount.")
    a = InvestmentActivity(user_id=user.id, account_id=account.id, security_id=sec.id if sec else None, date=body.date,
                           kind=body.kind, quantity=qty, price=price if price is not None else (amount / qty if amount and qty else None),
                           amount=amount or Decimal(0), commission=Decimal(str(body.commission)),
                           currency=(body.currency or account.currency).upper(),
                           split_ratio=Decimal(str(body.split_ratio)) if body.split_ratio else None,
                           description=body.description)
    db.add(a)
    db.commit()
    return activity_out(a, sec)


@router.delete("/activities/{activity_id}")
def delete_activity(activity_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, InvestmentActivity, activity_id, user))
    db.commit()
    return {"ok": True}


class RegistrationIn(BaseModel):
    registration: str = Field(pattern=f"^({'|'.join(REGISTRATIONS)})$")


@router.put("/accounts/{account_id}/registration")
def set_registration(account_id: int, body: RegistrationIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    account = owned(db, Account, account_id, user)
    info = db.get(InvestAccountInfo, account.id)
    if info is None:
        db.add(InvestAccountInfo(account_id=account.id, registration=body.registration))
    else:
        info.registration = body.registration
    db.commit()
    return {"ok": True}


# --- Overview -----------------------------------------------------------------------

@router.get("/overview")
def overview(user: User = Depends(current_user), db: Session = Depends(get_db)):
    today = date.today()
    conv = Converter(db, user.base_currency)
    p = Portfolio(db, user)
    cash_balances = account_balances(db, user.id)
    positions = defaultdict(list)
    for pos in p.positions(today, conv):
        positions[pos.account.id].append(pos)
    infos = {i.account_id: i for i in db.scalars(select(InvestAccountInfo).where(
        InvestAccountInfo.account_id.in_(list(p.accounts) or [0])))}
    holding_ids = {k: h.id for k, h in p.snapshots.items()}
    div_year = p.dividends(date(today.year, 1, 1), today)
    div_by_account: dict[int, Decimal] = defaultdict(Decimal)
    div_items = []
    for a in div_year:
        v = conv.convert(Decimal(a.amount or 0), a.currency, a.date)
        if v is None:
            continue
        div_by_account[a.account_id] += v
        sec = p.securities.get(a.security_id)
        div_items.append({"date": a.date.isoformat(), "symbol": sec.symbol if sec else None, "account_id": a.account_id,
                          "kind": a.kind, "amount": f2(Decimal(a.amount or 0)), "currency": a.currency, "amount_base": f2(v)})
    div_items.sort(key=lambda d: d["date"], reverse=True)

    by_class: dict[str, Decimal] = defaultdict(Decimal)
    by_currency: dict[str, Decimal] = defaultdict(Decimal)
    totals = defaultdict(Decimal)
    accounts_out = []
    for acct in sorted(p.accounts.values(), key=lambda a: (a.is_archived, a.name)):
        if acct.type != "investment" and acct.id not in positions:
            continue
        reg, explicit = invest.registration(db, acct, infos.get(acct.id))
        rows = []
        acct_mv = acct_cost = Decimal(0)
        mv_complete = True
        for pos in sorted(positions.get(acct.id, []), key=lambda x: x.security.symbol):
            sec = pos.security
            mv, at_cost = p.market_value(pos, today, conv)
            price = p.price_on(sec.id, today)
            latest_source = None
            if price:
                row = db.scalar(select(SecurityPrice.source).where(SecurityPrice.security_id == sec.id,
                                                                   SecurityPrice.date == price[0]))
                latest_source = row
            gain = (mv - pos.cost) if (mv is not None and not at_cost) else None
            native = pos.quantity * price[1] if price else None
            rows.append({
                "security_id": sec.id, "holding_id": holding_ids.get((acct.id, sec.id)), "symbol": sec.symbol,
                "name": sec.name, "exchange": sec.exchange, "currency": sec.currency, "asset_class": sec.asset_class,
                "quantity": fq(pos.quantity), "avg_cost": fq(pos.cost / pos.quantity) if pos.quantity else None,
                "cost": f2(pos.cost), "price": fq(price[1]) if price else None,
                "price_date": price[0].isoformat() if price else None,
                "price_age_days": (today - price[0]).days if price else None, "price_source": latest_source,
                "fetch_error": sec.last_fetch_error, "valued_at_cost": at_cost,
                "market_value": f2(mv), "market_value_native": f2(native), "gain": f2(gain), "gain_pct": _pct(gain, pos.cost),
                "cost_incomplete": pos.incomplete,
            })
            if mv is None:
                mv_complete = False
                continue
            acct_mv += mv
            acct_cost += pos.cost
            base_mv = conv.convert(mv, acct.currency, today)
            base_cost = conv.convert(pos.cost, acct.currency, today)
            if base_mv is not None:
                by_class[sec.asset_class] += base_mv
                by_currency[sec.currency] += base_mv
                totals["market_value"] += base_mv
                if base_cost is not None:
                    totals["cost"] += base_cost
                    if not at_cost:
                        totals["gain"] += base_mv - base_cost
                        totals["gain_cost"] += base_cost
        cash = cash_balances.get(acct.id, Decimal(0))
        base_cash = conv.convert(cash, acct.currency, today)
        if base_cash is not None:
            totals["cash"] += base_cash
            if base_cash > 0:
                by_class["cash"] += base_cash
                by_currency[acct.currency] += base_cash
        priced_cost = sum((Decimal(str(r["cost"])) for r in rows if r["gain"] is not None), Decimal(0))
        acct_gain = sum((Decimal(str(r["gain"])) for r in rows if r["gain"] is not None), Decimal(0))
        accounts_out.append({
            "id": acct.id, "name": acct.name, "institution": acct.institution, "type": acct.type, "currency": acct.currency,
            "is_archived": acct.is_archived, "registration": reg, "registration_explicit": explicit,
            "cash": f2(cash), "holdings_value": f2(acct_mv), "holdings_complete": mv_complete, "total": f2(cash + acct_mv),
            "cost": f2(acct_cost), "gain": f2(acct_gain) if rows else None, "gain_pct": _pct(acct_gain, priced_cost),
            "dividends_ytd": f2(div_by_account.get(acct.id, Decimal(0))), "positions": rows,
        })

    def split(d: dict[str, Decimal]) -> list[dict]:
        total = sum((v for v in d.values() if v > 0), Decimal(0))
        return [{"key": k, "value": f2(v), "pct": round(float(v / total * 100), 1) if total else 0}
                for k, v in sorted(d.items(), key=lambda kv: -kv[1]) if v > 0]

    div_total = sum(div_by_account.values(), Decimal(0))
    return {
        "base_currency": user.base_currency, "as_of": today.isoformat(), "year": today.year,
        "totals": {"market_value": f2(totals["market_value"]), "cost": f2(totals["cost"]), "gain": f2(totals["gain"]),
                   "gain_pct": _pct(totals["gain"], totals["gain_cost"]), "cash": f2(totals["cash"]),
                   "total": f2(totals["market_value"] + totals["cash"]), "dividends_ytd": f2(div_total)},
        "accounts": accounts_out,
        "allocation": {"by_class": split(by_class), "by_currency": split(by_currency)},
        "dividends": {"year": today.year, "total": f2(div_total), "items": div_items[:30]},
        "warnings": conv.warnings(), "price_warnings": p.price_warnings(),
        "prices_fetch_enabled": bool(settings_store.get(db, "prices_fetch_enabled")), "acb_note": ACB_NOTE,
    }


@router.get("/acb/{account_id}")
def acb(account_id: int, year: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    account = owned(db, Account, account_id, user)
    reg, _ = invest.registration(db, account)
    conv = Converter(db, "CAD")
    p = Portfolio(db, user, [account.id])
    items = invest.acb_report(p, account, conv, year) if reg == "non_registered" else []
    return {"account_id": account.id, "registration": reg, "currency": "CAD", "items": items,
            "note": ACB_NOTE if reg == "non_registered" else
            "Registered accounts (TFSA, RRSP, FHSA...) don't need an adjusted cost base: gains inside them aren't taxed as capital gains.",
            "warnings": conv.warnings()}


# --- Imports ------------------------------------------------------------------------

def _hash(account_id: int, a, occurrence: int) -> str:
    key = f"{account_id}|{a.date.isoformat()}|{a.kind}|{a.symbol}|{Decimal(a.quantity):.6f}|{Decimal(a.amount):.2f}|{occurrence}"
    return hashlib.sha256(key.encode()).hexdigest()


def _plan(db: Session, account: Account, result: InvestParseResult) -> list[dict]:
    existing = set(db.scalars(select(InvestmentActivity.import_hash).where(
        InvestmentActivity.account_id == account.id, InvestmentActivity.import_hash.is_not(None))))
    seen: Counter = Counter()
    out = []
    for a in result.activities:
        base = (a.date, a.kind, a.symbol, f"{a.quantity:.6f}", f"{a.amount:.2f}")
        h = _hash(account.id, a, seen[base])
        seen[base] += 1
        out.append({"act": a, "hash": h, "duplicate": h in existing})
    return out


def _labels(result: InvestParseResult) -> list[str]:
    return sorted({h.account_label for h in result.holdings if h.account_label})


async def _parse(file: UploadFile, options: str | None) -> tuple[InvestParseResult, dict]:
    opts = json.loads(options) if options else {}
    raw = await file.read(MAX_BYTES + 1)  # enough to tell it's too big, without loading a huge upload into memory
    try:
        result = parse_investment_file(file.filename or "", raw, opts.get("source") or None)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    label = opts.get("account_label")
    if label and result.holdings:
        result.holdings = [h for h in result.holdings if h.account_label == label]
    return result, opts


@router.post("/import/preview")
async def import_preview(account_id: int = Form(...), options: str | None = Form(None), file: UploadFile = File(...),
                         user: User = Depends(current_user), db: Session = Depends(get_db)):
    account = owned(db, Account, account_id, user)
    raw_result, opts = await _parse(file, None)
    result, _ = await _reparse(file, options) if options else (raw_result, opts)
    planned = _plan(db, account, result)
    rows = [{"date": p["act"].date.isoformat(), "kind": p["act"].kind, "symbol": p["act"].symbol, "name": p["act"].name,
             "quantity": fq(p["act"].quantity), "price": fq(p["act"].price), "amount": f2(p["act"].amount),
             "commission": f2(p["act"].commission), "currency": p["act"].currency or account.currency,
             "duplicate": p["duplicate"]} for p in planned[:300]]
    holdings = [{"symbol": h.symbol, "name": h.name, "exchange": h.exchange, "quantity": fq(h.quantity),
                 "cost_basis": f2(h.cost_basis), "cost_currency": h.cost_currency or account.currency,
                 "price": fq(h.price), "price_currency": h.price_currency, "account_label": h.account_label}
                for h in result.holdings[:300]]
    return {"source": result.source, "kind": result.kind, "columns": result.columns,
            "as_of": result.as_of.isoformat() if result.as_of else None,
            "account_labels": _labels(raw_result), "activities": rows, "holdings": holdings,
            "total": len(planned) if result.kind == "activity" else len(result.holdings),
            "new": sum(1 for p in planned if not p["duplicate"]), "duplicates": sum(1 for p in planned if p["duplicate"]),
            "skipped": result.skipped, "skipped_types": result.skipped_types, "warnings": result.warnings[:20]}


async def _reparse(file: UploadFile, options: str | None):
    await file.seek(0)
    return await _parse(file, options)


@router.post("/import/commit")
async def import_commit(account_id: int = Form(...), options: str | None = Form(None), file: UploadFile = File(...),
                        user: User = Depends(current_user), db: Session = Depends(get_db)):
    account = owned(db, Account, account_id, user)
    raw_result, _ = await _parse(file, None)
    result, opts = await _reparse(file, options)
    if result.kind == "holdings" and len(_labels(raw_result)) > 1 and not opts.get("account_label"):
        raise HTTPException(422, "This file lists several accounts. Pick which one to import into this account.")
    if not result.activities and not result.holdings:
        raise HTTPException(422, "Nothing to import. " + " ".join(result.warnings[:3]))
    batch = InvestImport(user_id=user.id, account_id=account.id, filename=(file.filename or "upload")[:255],
                         source=result.source, kind=result.kind)
    db.add(batch)
    db.flush()
    warnings: list[str] = []
    imported = skipped = 0
    if result.kind == "activity":
        for p in _plan(db, account, result):
            if p["duplicate"]:
                skipped += 1
                continue
            a = p["act"]
            sec = None
            if a.symbol:
                sec = find_or_create_security(db, user, a.symbol, a.exchange, a.name, None, account.currency)
            db.add(InvestmentActivity(
                user_id=user.id, account_id=account.id, security_id=sec.id if sec else None, date=a.date, kind=a.kind,
                quantity=a.quantity, price=a.price, amount=a.amount, commission=a.commission,
                currency=(a.currency or account.currency).upper(), split_ratio=a.split_ratio,
                description=a.description[:500], import_hash=p["hash"], import_id=batch.id))
            imported += 1
    else:
        on = date.fromisoformat(opts["as_of"]) if opts.get("as_of") else (result.as_of or date.today())
        conv = Converter(db, account.currency)
        for h in result.holdings:
            sec = find_or_create_security(db, user, h.symbol, h.exchange, h.name, h.price_currency, account.currency,
                                          h.security_type)
            cost = None
            if h.cost_basis is not None and (h.cost_currency or account.currency) == account.currency:
                cost = h.cost_basis
            elif h.cost_market is not None and (h.cost_market_currency or sec.currency) == account.currency:
                cost = h.cost_market
            elif h.cost_basis is not None:
                r = conv.rate(h.cost_currency, on)
                cost = h.cost_basis * r if r is not None else None
            if cost is None:
                warnings.append(f"{h.symbol}: book cost missing or in another currency without a rate; set to 0.")
            row = db.scalar(select(Holding).where(Holding.account_id == account.id, Holding.security_id == sec.id))
            if row is None:
                row = Holding(user_id=user.id, account_id=account.id, security_id=sec.id, quantity=Decimal(0), as_of=on)
                db.add(row)
            row.quantity, row.cost_basis, row.as_of, row.source, row.import_id = h.quantity, cost or Decimal(0), on, "import", batch.id
            if h.price:
                invest.set_price(db, sec.id, on, h.price, "import")
            imported += 1
        warnings.extend(w["message"] for w in conv.warnings())
    batch.imported, batch.skipped = imported, skipped + result.skipped
    db.commit()
    return {"import_id": batch.id, "kind": result.kind, "imported": imported, "skipped": batch.skipped,
            "warnings": (result.warnings + warnings)[:20]}


@router.get("/imports")
def list_imports(user: User = Depends(current_user), db: Session = Depends(get_db)):
    names = {a.id: a.name for a in db.scalars(select(Account).where(Account.user_id == user.id))}
    return [{"id": b.id, "account_id": b.account_id, "account_name": names.get(b.account_id), "filename": b.filename,
             "source": b.source, "kind": b.kind, "imported": b.imported, "skipped": b.skipped,
             "created_at": b.created_at.isoformat()}
            for b in db.scalars(select(InvestImport).where(InvestImport.user_id == user.id)
                                .order_by(InvestImport.created_at.desc()).limit(50))]


@router.delete("/imports/{import_id}")
def undo_import(import_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Removes the activity and position snapshots that came from this file. Prices are kept."""
    b = owned(db, InvestImport, import_id, user)
    removed = 0
    for model in (InvestmentActivity, Holding):
        for row in db.scalars(select(model).where(model.import_id == b.id)):
            db.delete(row)
            removed += 1
    db.delete(b)
    db.commit()
    return {"removed": removed}
