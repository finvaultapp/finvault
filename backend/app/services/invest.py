"""Investment positions, market values, dividends and adjusted cost base (ACB).

Positions
    A `Holding` snapshot (quantity + book cost on `as_of`) is the starting point, and activity
    dated after it is applied on top. For dates before the snapshot, activity between the date
    and the snapshot is backed out. A snapshot with no activity on or before its date only counts
    from its `as_of` date. Without a snapshot the position is built from activity alone.

Values
    Market value uses the latest price on or before the date. When there is no price yet, the
    position is counted at its book cost and `price_warnings` says so. Currency conversion goes
    through the shared Converter, so a missing exchange rate leaves the amount out and produces
    the usual missing-rate warning; nothing is guessed.

Cost and ACB
    Canadian average-cost method: buys (plus commission) and reinvested dividends add to the
    cost, sells remove cost in proportion to units sold, return of capital lowers it (never below
    zero; the excess is a capital gain), splits change units but not cost. ACB is worked out in
    CAD at each activity's date for non-registered accounts. It is a helper, not tax advice: it
    doesn't apply the superficial-loss rule or pool identical securities across accounts.
"""
from __future__ import annotations

import csv
import io
import logging
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account, RegisteredPlan, User
from ..models_invest import Holding, InvestAccountInfo, InvestmentActivity, Security, SecurityPrice
from .currency import Converter

log = logging.getLogger("finvault.invest")
ZERO = Decimal(0)
ACB_NOTE = ("FinVault's ACB is a helper, not tax advice. It uses the average-cost method per account and "
            "doesn't apply the superficial-loss rule or combine identical securities held in other "
            "non-registered accounts. Check with your T5008 slips and an accountant.")
REGISTERED_WORDS = {"tfsa": "tfsa", "celi": "tfsa", "rrsp": "rrsp", "reer": "rrsp", "fhsa": "fhsa", "celiapp": "fhsa",
                    "resp": "resp", "reee": "resp", "rrif": "rrif", "ferr": "rrif", "lira": "lira", "cri": "lira"}
POSITION_KINDS = {"buy", "sell", "reinvested_dividend", "split", "return_of_capital"}
INCOME_KINDS = {"dividend", "distribution", "reinvested_dividend"}


def f2(x: Decimal | None) -> float | None:
    return None if x is None else float(round(x, 2))


def fq(x: Decimal | None) -> float | None:
    return None if x is None else float(round(x, 6))


# --- Average cost engine ------------------------------------------------------------

@dataclass
class CostState:
    quantity: Decimal = ZERO
    cost: Decimal = ZERO
    incomplete: bool = False  # an amount couldn't be converted
    realized: list = field(default_factory=list)  # (date, proceeds, cost_sold, gain)
    rows: list = field(default_factory=list)  # ACB ledger rows

    @property
    def average(self) -> Decimal | None:
        return self.cost / self.quantity if self.quantity > 0 else None


def apply_activity(state: CostState, act: InvestmentActivity, amount: Decimal | None, commission: Decimal | None,
                   ledger: bool = False) -> None:
    """Apply one activity. `amount`/`commission` are already in the state's currency (None = no rate)."""
    kind = act.kind
    qty = Decimal(act.quantity or 0)
    if kind in {"buy", "sell", "reinvested_dividend", "return_of_capital"} and amount is None:
        state.incomplete = True
    amount = amount or ZERO
    commission = commission or ZERO
    gain = proceeds = cost_sold = None
    if kind == "buy":
        state.quantity += qty
        state.cost += amount + commission
    elif kind == "reinvested_dividend":
        # Units bought with a dividend; with no units it's a notional (phantom) distribution.
        state.quantity += qty
        state.cost += amount
    elif kind == "sell":
        qty = min(qty, state.quantity) if state.quantity > 0 else ZERO
        cost_sold = (state.cost * qty / state.quantity) if state.quantity > 0 else ZERO
        proceeds = amount - commission
        gain = proceeds - cost_sold
        state.cost -= cost_sold
        state.quantity -= qty
        if state.quantity <= 0:
            state.quantity, state.cost = ZERO, ZERO
        state.realized.append((act.date, proceeds, cost_sold, gain))
    elif kind == "return_of_capital":
        state.cost -= amount
        if state.cost < 0:
            gain = -state.cost  # ROC beyond the ACB is a capital gain
            state.realized.append((act.date, gain, ZERO, gain))
            state.cost = ZERO
    elif kind == "split":
        ratio = Decimal(act.split_ratio or 0)
        if ratio > 0:
            state.quantity *= ratio
    else:
        return
    if ledger:
        state.rows.append({
            "id": act.id, "date": act.date.isoformat(), "kind": kind, "quantity": fq(Decimal(act.quantity or 0)),
            "amount": f2(amount), "commission": f2(commission),
            "proceeds": f2(proceeds), "cost_sold": f2(cost_sold), "gain": f2(gain),
            "units_after": fq(state.quantity), "acb_after": f2(state.cost),
            "acb_per_unit": fq(state.average) if state.average is not None else None,
        })


def _reverse_quantity(qty: Decimal, acts: list[InvestmentActivity]) -> Decimal:
    """Undo activity (given newest first) to find the quantity before it."""
    for a in acts:
        q = Decimal(a.quantity or 0)
        if a.kind in {"buy", "reinvested_dividend"}:
            qty -= q
        elif a.kind == "sell":
            qty += q
        elif a.kind == "split" and a.split_ratio:
            qty /= Decimal(a.split_ratio)
    return max(qty, ZERO)


# --- Portfolio ----------------------------------------------------------------------

@dataclass
class Position:
    account: Account
    security: Security
    quantity: Decimal
    cost: Decimal  # in the account's currency
    incomplete: bool = False


class Portfolio:
    """Everything a member holds, loaded once so month-by-month valuations stay cheap."""

    def __init__(self, db: Session, user: User, account_ids: list[int] | None = None):
        self.db, self.user = db, user
        q = select(Account).where(Account.user_id == user.id)
        if account_ids:
            q = q.where(Account.id.in_(account_ids))
        self.accounts = {a.id: a for a in db.scalars(q)}
        self.securities = {s.id: s for s in db.scalars(select(Security).where(Security.user_id == user.id))}
        self.snapshots: dict[tuple[int, int], Holding] = {}
        for h in db.scalars(select(Holding).where(Holding.user_id == user.id)):
            if h.account_id in self.accounts:
                self.snapshots[(h.account_id, h.security_id)] = h
        self.activities: dict[tuple[int, int], list[InvestmentActivity]] = defaultdict(list)
        self.all_activities: list[InvestmentActivity] = []
        for a in db.scalars(select(InvestmentActivity).where(InvestmentActivity.user_id == user.id)
                            .order_by(InvestmentActivity.date, InvestmentActivity.id)):
            if a.account_id not in self.accounts:
                continue
            self.all_activities.append(a)
            if a.security_id is not None:
                self.activities[(a.account_id, a.security_id)].append(a)
        self.prices: dict[int, list[tuple[date, Decimal]]] = defaultdict(list)
        if self.securities:
            for p in db.scalars(select(SecurityPrice).where(SecurityPrice.security_id.in_(list(self.securities)))
                                .order_by(SecurityPrice.date)):
                self.prices[p.security_id].append((p.date, Decimal(p.close)))
        self.keys = sorted(set(self.snapshots) | set(self.activities))
        self.at_cost: set[str] = set()

    @property
    def empty(self) -> bool:
        return not self.keys

    def price_on(self, security_id: int, on: date) -> tuple[date, Decimal] | None:
        series = self.prices.get(security_id)
        if not series:
            return None
        idx = bisect_right(series, (on, Decimal("Infinity")))
        return series[idx - 1] if idx else None

    def latest_price(self, security_id: int) -> tuple[date, Decimal] | None:
        series = self.prices.get(security_id)
        return series[-1] if series else None

    # -- positions --

    def _amount_in(self, conv: Converter, act: InvestmentActivity, target: str) -> tuple[Decimal | None, Decimal | None]:
        r = conv.rate(act.currency or target, act.date, target=target)
        if r is None:
            return None, None
        return Decimal(act.amount or 0) * r, Decimal(act.commission or 0) * r

    def position(self, key: tuple[int, int], on: date, conv: Converter) -> Position | None:
        acct, sec = self.accounts[key[0]], self.securities.get(key[1])
        if sec is None:
            return None
        if acct.opening_date and on < acct.opening_date:
            return None
        acts = [a for a in self.activities.get(key, []) if a.kind in POSITION_KINDS]
        snap = self.snapshots.get(key)
        if snap and on < snap.as_of:
            between = [a for a in acts if on < a.date <= snap.as_of]
            if not any(a.date <= snap.as_of for a in acts):
                return None  # nothing tells us it was held before the snapshot
            qty = _reverse_quantity(Decimal(snap.quantity), list(reversed(between)))
            avg = Decimal(snap.cost_basis or 0) / Decimal(snap.quantity) if Decimal(snap.quantity or 0) > 0 else ZERO
            return Position(acct, sec, qty, qty * avg)
        state = CostState(quantity=Decimal(snap.quantity) if snap else ZERO,
                          cost=Decimal(snap.cost_basis or 0) if snap else ZERO)
        for a in acts:
            if a.date > on:
                break
            if snap and a.date <= snap.as_of:
                continue
            amount, commission = self._amount_in(conv, a, acct.currency)
            apply_activity(state, a, amount, commission)
        return Position(acct, sec, state.quantity, state.cost, state.incomplete)

    def positions(self, on: date, conv: Converter) -> list[Position]:
        out = []
        for key in self.keys:
            p = self.position(key, on, conv)
            if p is not None and p.quantity > 0:
                out.append(p)
        return out

    # -- values --

    def market_value(self, p: Position, on: date, conv: Converter, record: bool = True) -> tuple[Decimal | None, bool]:
        """(value in the account's currency or None if no FX rate, valued_at_cost)."""
        price = self.price_on(p.security.id, on)
        if price is None:
            if record:
                self.at_cost.add(p.security.symbol)
            return p.cost, True
        r = conv.rate(p.security.currency, on, target=p.account.currency)
        if r is None:
            return None, False
        return p.quantity * price[1] * r, False

    def account_values(self, on: date, conv: Converter, record: bool = True) -> dict[int, Decimal]:
        """Market value of holdings per account, in each account's currency. Unconvertible parts are left out."""
        out: dict[int, Decimal] = defaultdict(Decimal)
        if self.empty:
            return {}
        for p in self.positions(on, conv):
            v, _ = self.market_value(p, on, conv, record)
            if v is not None:
                out[p.account.id] += v
            else:
                out.setdefault(p.account.id, ZERO)
        return dict(out)

    def price_warnings(self) -> list[dict]:
        return [{"type": "missing_price", "symbol": s,
                 "message": f"No price for {s} yet, so it is counted at its book cost. Add a price to value it."}
                for s in sorted(self.at_cost)]

    # -- income --

    def dividends(self, start: date, end: date) -> list[InvestmentActivity]:
        """Dividends and distributions received. A reinvested dividend counts only when there's no cash
        dividend for the same security within a week (brokers often list both rows)."""
        cash = [a for a in self.all_activities if a.kind in {"dividend", "distribution"}]
        out = [a for a in cash if start <= a.date <= end]
        for a in self.all_activities:
            if a.kind != "reinvested_dividend" or not (start <= a.date <= end) or not a.amount:
                continue
            twin = any(c.security_id == a.security_id and c.account_id == a.account_id
                       and abs((c.date - a.date).days) <= 7 for c in cash)
            if not twin:
                out.append(a)
        return out


# --- Registration and ACB -----------------------------------------------------------

def registration(db: Session, account: Account, info: InvestAccountInfo | None = None) -> tuple[str, bool]:
    """(registration, explicit). Explicit setting, then a linked TFSA/RRSP/FHSA plan, then the name."""
    info = info or db.get(InvestAccountInfo, account.id)
    if info:
        return info.registration, True
    plan = db.scalar(select(RegisteredPlan.kind).where(RegisteredPlan.account_id == account.id).limit(1))
    if plan:
        return plan, False
    words = (account.name + " " + (account.institution or "")).lower().replace("-", " ").split()
    for w in words:
        if w in REGISTERED_WORDS:
            return REGISTERED_WORDS[w], False
    return "non_registered", False


def acb_report(portfolio: Portfolio, account: Account, conv: Converter, year: int | None = None) -> list[dict]:
    """ACB per security in CAD, with a ledger of every activity that changed it."""
    year = year or date.today().year
    out = []
    for key in portfolio.keys:
        if key[0] != account.id:
            continue
        sec = portfolio.securities.get(key[1])
        if sec is None:
            continue
        acts = [a for a in portfolio.activities.get(key, []) if a.kind in POSITION_KINDS]
        snap = portfolio.snapshots.get(key)
        state = CostState()
        start_note = None
        if snap:
            r = conv.rate(account.currency, snap.as_of, target="CAD")
            state.quantity = Decimal(snap.quantity)
            state.cost = Decimal(snap.cost_basis or 0) * r if r is not None else ZERO
            state.incomplete = r is None
            start_note = snap.as_of.isoformat()
            state.rows.append({"id": None, "date": snap.as_of.isoformat(), "kind": "opening", "quantity": fq(state.quantity),
                               "amount": f2(state.cost), "commission": None, "proceeds": None, "cost_sold": None,
                               "gain": None, "units_after": fq(state.quantity), "acb_after": f2(state.cost),
                               "acb_per_unit": fq(state.average) if state.average is not None else None})
        for a in acts:
            if snap and a.date <= snap.as_of:
                continue
            r = conv.rate(a.currency or account.currency, a.date, target="CAD")
            amount = Decimal(a.amount or 0) * r if r is not None else None
            commission = Decimal(a.commission or 0) * r if r is not None else None
            apply_activity(state, a, amount, commission, ledger=True)
        realized_year = sum((g for d, _, _, g in state.realized if d.year == year), ZERO)
        out.append({"security_id": sec.id, "symbol": sec.symbol, "name": sec.name, "units": fq(state.quantity),
                    "acb": f2(state.cost), "acb_per_unit": fq(state.average) if state.average is not None else None,
                    "realized_gain_year": f2(realized_year), "year": year, "incomplete": state.incomplete,
                    "from_snapshot": start_note, "ledger": state.rows})
    out.sort(key=lambda r: r["symbol"])
    return out


# --- Prices -------------------------------------------------------------------------

class PriceProvider:
    """Looks up the latest close for a ticker. Only the ticker symbol is ever sent."""
    name = "base"

    def symbol_for(self, sec: Security) -> str:
        raise NotImplementedError

    def fetch(self, symbol: str) -> tuple[date, Decimal] | None:
        raise NotImplementedError


class StooqProvider(PriceProvider):
    """Stooq's free, keyless CSV quote endpoint. TSX tickers use the .ca suffix (xeqt.ca), US ones .us."""
    name = "stooq"
    URL = "https://stooq.com/q/l/"
    CA = {"TSX", "TSXV", "NEO", "CSE", "CBOE CANADA", "XTSE"}
    US = {"NYSE", "NASDAQ", "ARCA", "AMEX", "NYSEARCA", "BATS", "CBOE"}

    def symbol_for(self, sec: Security) -> str:
        if sec.price_symbol:
            return sec.price_symbol.strip().lower()
        sym = sec.symbol.strip().lower()
        ex = (sec.exchange or "").upper()
        if ex in self.CA or (not ex and sec.currency == "CAD"):
            return f"{sym.replace('.', '-')}.ca"
        if ex in self.US or (not ex and sec.currency == "USD"):
            return f"{sym}.us"
        return sym

    def fetch(self, symbol: str) -> tuple[date, Decimal] | None:
        import httpx

        resp = httpx.get(self.URL, params={"s": symbol, "f": "sd2t2ohlcv", "h": "", "e": "csv"}, timeout=10)
        resp.raise_for_status()
        return self.parse(resp.text)

    @staticmethod
    def parse(text: str) -> tuple[date, Decimal] | None:
        rows = list(csv.DictReader(io.StringIO(text.strip())))
        if not rows:
            return None
        row = {k.strip().lower(): (v or "").strip() for k, v in rows[0].items() if k}
        close, day = row.get("close", ""), row.get("date", "")
        if not close or close.upper() == "N/D" or not day or day.upper() == "N/D":
            return None
        try:
            return date.fromisoformat(day), Decimal(close)
        except (ValueError, ArithmeticError):
            return None


PROVIDERS: dict[str, PriceProvider] = {"stooq": StooqProvider()}


def set_price(db: Session, security_id: int, on: date, close: Decimal, source: str) -> None:
    row = db.scalar(select(SecurityPrice).where(SecurityPrice.security_id == security_id, SecurityPrice.date == on))
    if row:
        if source == "manual" or row.source != "manual":  # automatic prices never overwrite typed ones
            row.close, row.source = close, source
    else:
        db.add(SecurityPrice(security_id=security_id, date=on, close=close, source=source))


def fetch_prices(db: Session, securities: list[Security], provider: PriceProvider | None = None) -> dict:
    """Fetch the latest close for each security. Failures keep the last price and record the error."""
    provider = provider or PROVIDERS["stooq"]
    by_symbol: dict[str, list[Security]] = defaultdict(list)
    for s in securities:
        if s.asset_class == "cash":
            continue
        by_symbol[provider.symbol_for(s)].append(s)
    updated, failed = 0, []
    now = datetime.now(timezone.utc)
    for symbol, secs in by_symbol.items():
        try:
            got = provider.fetch(symbol)
            error = None if got else "No price returned for this symbol."
        except Exception as exc:  # noqa: BLE001
            got, error = None, f"Couldn't reach the price service ({type(exc).__name__})."
        for s in secs:
            s.last_fetch_at = now
            s.last_fetch_error = error
            if got:
                set_price(db, s.id, got[0], got[1], provider.name)
        if got:
            updated += len(secs)
        else:
            failed.extend(s.symbol for s in secs)
    db.commit()
    return {"updated": updated, "failed": sorted(set(failed)), "provider": provider.name}


def held_securities(db: Session, user_id: int | None = None) -> list[Security]:
    """Securities that appear in a holding or in activity (optionally for one member)."""
    ids = set(db.scalars(select(Holding.security_id))) | set(
        db.scalars(select(InvestmentActivity.security_id).where(InvestmentActivity.security_id.is_not(None))))
    if not ids:
        return []
    q = select(Security).where(Security.id.in_(ids))
    if user_id is not None:
        q = q.where(Security.user_id == user_id)
    return list(db.scalars(q))


def fetch_due(db: Session) -> dict | None:
    """Background job: fetch prices at most once every 20 hours, only when the admin turned it on."""
    from .. import settings_store

    if not settings_store.get(db, "prices_fetch_enabled"):
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(hours=20)

    def due(s: Security) -> bool:
        last = s.last_fetch_at
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return last is None or last < cutoff

    secs = [s for s in held_securities(db) if due(s)]
    return fetch_prices(db, secs) if secs else None
