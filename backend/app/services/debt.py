"""Debt payoff planner: avalanche vs snowball for a fixed monthly budget.

Monthly rate per debt:
  * credit cards and loans: APR / 12 (monthly compounding)
  * Canadian mortgages: the Interest Act requires fixed-rate mortgage rates to be compounded
    semi-annually, not in advance. The effective monthly rate is (1 + APR/2) ** (1/6) - 1,
    so six monthly periods compound to exactly one half-year at APR/2.

Each month, in this order: interest is added to every balance, every debt gets its minimum
payment (or what's left of it), and the rest of the budget goes to the target debt; any money
freed when a debt is paid off rolls to the next one. Avalanche targets the highest APR first,
snowball the smallest balance first.
"""
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account, Asset, User
from ..models_plan import DebtSetting
from .currency import Converter
from .ledger import account_balances
from .reports import f2

CENT = Decimal("0.01")
MAX_MONTHS = 600  # 50 years; anything longer is reported as "never paid off"


def cents(x: Decimal) -> Decimal:
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)


def monthly_rate(apr_percent: Decimal, kind: str) -> Decimal:
    apr = Decimal(apr_percent) / 100
    if kind == "mortgage":
        return (1 + apr / 2) ** (Decimal(1) / 6) - 1
    return apr / 12


def mortgage_payment(principal: Decimal, apr_percent: Decimal, years: int) -> Decimal:
    """Monthly payment for a Canadian (semi-annually compounded) mortgage."""
    r = monthly_rate(apr_percent, "mortgage")
    n = years * 12
    if r == 0:
        return cents(Decimal(principal) / n)
    return cents(Decimal(principal) * r / (1 - (1 + r) ** -n))


@dataclass
class Debt:
    id: str
    name: str
    balance: Decimal
    apr: Decimal
    min_payment: Decimal
    kind: str = "card"


def _add_month(y: int, m: int) -> tuple[int, int]:
    return (y + 1, 1) if m == 12 else (y, m + 1)


def simulate(debts: list[Debt], budget: Decimal, strategy: str, start: date | None = None) -> dict:
    """Month-by-month schedule. `strategy` is 'avalanche' or 'snowball'."""
    start = start or date.today()
    bal = {d.id: cents(d.balance) for d in debts if d.balance > 0}
    info = {d.id: d for d in debts}
    rates = {d.id: monthly_rate(d.apr, d.kind) for d in debts}
    budget = cents(budget)
    minimums = sum((min(info[i].min_payment, bal[i]) for i in bal), Decimal(0))
    result = {"strategy": strategy, "budget": f2(budget), "months": 0, "payoff_month": None, "total_interest": 0.0,
              "total_paid": 0.0, "schedule": [], "order": [], "paid_off": {}, "feasible": True, "reason": None}
    if not bal:
        return result
    if budget < minimums:
        result.update(feasible=False, reason="budget_below_minimums", minimums=f2(minimums))
        return result
    total_interest = total_paid = Decimal(0)
    y, m = start.year, start.month
    month = 0
    while any(b > 0 for b in bal.values()) and month < MAX_MONTHS:
        month += 1
        y, m = _add_month(y, m)
        prev_total = sum(bal.values(), Decimal(0))
        interest = {}
        for i in bal:
            if bal[i] > 0:
                interest[i] = cents(bal[i] * rates[i])
                bal[i] += interest[i]
                total_interest += interest[i]
        pay = {i: Decimal(0) for i in bal}
        left = budget
        for i in bal:
            if bal[i] > 0:
                p = min(info[i].min_payment, bal[i], left)
                pay[i] += p
                bal[i] -= p
                left -= p
        active = [i for i in bal if bal[i] > 0]
        if strategy == "avalanche":
            active.sort(key=lambda i: (-info[i].apr, bal[i]))
        else:
            active.sort(key=lambda i: (bal[i], -info[i].apr))
        for i in active:
            if left <= 0:
                break
            p = min(bal[i], left)
            pay[i] += p
            bal[i] -= p
            left -= p
        paid_now = sum(pay.values(), Decimal(0))
        total_paid += paid_now
        if sum(bal.values(), Decimal(0)) >= prev_total:
            # Payments don't even cover the interest: the balance never goes down.
            result.update(feasible=False, reason="never_paid_off")
            break
        label = f"{y:04d}-{m:02d}"
        for i in bal:
            if bal[i] <= 0 and i not in result["paid_off"]:
                result["paid_off"][i] = label
                result["order"].append(i)
        result["schedule"].append({
            "month": label, "payments": {i: f2(v) for i, v in pay.items() if v > 0},
            "interest": {i: f2(v) for i, v in interest.items()},
            "balances": {i: f2(max(v, Decimal(0))) for i, v in bal.items()},
            "total_balance": f2(sum((max(v, Decimal(0)) for v in bal.values()), Decimal(0))),
        })
    if any(b > 0 for b in bal.values()) and result["feasible"]:
        result.update(feasible=False, reason="never_paid_off")
    result["months"] = month
    result["payoff_month"] = result["schedule"][-1]["month"] if result["feasible"] and result["schedule"] else None
    result["total_interest"] = f2(total_interest)
    result["total_paid"] = f2(total_paid)
    return result


# --- Gathering debts from the member's data -----------------------------------------------

def _guess_kind(source: str, obj) -> str:
    if source == "account":
        return "card" if obj.type == "credit_card" else "loan"
    return "mortgage" if obj.kind == "mortgage" else "loan"


def list_debts(db: Session, user: User) -> dict:
    conv = Converter(db, user.base_currency)
    settings = {(s.source, s.ref_id): s for s in db.scalars(select(DebtSetting).where(DebtSetting.user_id == user.id))}
    balances = account_balances(db, user.id)
    out = []
    for a in db.scalars(select(Account).where(Account.user_id == user.id, Account.is_archived.is_(False),
                                              Account.type.in_(("credit_card", "loan"))).order_by(Account.name)):
        owed = -Decimal(balances.get(a.id, Decimal(0)))
        out.append(_debt_out("account", a, a.name, a.currency, owed, settings.get(("account", a.id)), conv))
    for asset in db.scalars(select(Asset).where(Asset.user_id == user.id, Asset.is_liability.is_(True)).order_by(Asset.name)):
        latest = asset.values[-1] if asset.values else None
        owed = abs(Decimal(latest.value)) if latest else Decimal(0)
        out.append(_debt_out("asset", asset, asset.name, asset.currency, owed, settings.get(("asset", asset.id)), conv))
    return {"currency": user.base_currency, "items": out, "warnings": conv.warnings()}


def _debt_out(source, obj, name, currency, owed, s: DebtSetting | None, conv: Converter) -> dict:
    kind = (s.kind if s and s.kind else None) or _guess_kind(source, obj)
    converted = conv.convert(owed, currency)
    return {"id": f"{source}:{obj.id}", "source": source, "ref_id": obj.id, "name": name, "currency": currency,
            "balance": f2(max(owed, Decimal(0))), "balance_converted": f2(max(converted, Decimal(0))) if converted is not None else None,
            "apr": float(s.apr) if s else None, "min_payment": f2(s.min_payment) if s else None, "kind": kind,
            "configured": s is not None}


def plan(db: Session, user: User, budget: Decimal, extra: Decimal = Decimal(0)) -> dict:
    data = list_debts(db, user)
    debts, skipped = [], []
    for d in data["items"]:
        if d["balance_converted"] is None or d["balance_converted"] <= 0:
            continue
        if not d["configured"]:
            skipped.append(d["id"])
            continue
        # Plan in the base currency so one budget can pay debts in different currencies.
        ratio = Decimal(str(d["balance_converted"])) / Decimal(str(d["balance"])) if d["balance"] else Decimal(1)
        debts.append(Debt(d["id"], d["name"], Decimal(str(d["balance_converted"])), Decimal(str(d["apr"])),
                          cents(Decimal(str(d["min_payment"])) * ratio), d["kind"]))
    minimums = sum((min(d.min_payment, d.balance) for d in debts), Decimal(0))
    out = {"currency": data["currency"], "debts": data["items"], "skipped": skipped, "minimums": f2(minimums),
           "budget": f2(budget), "extra": f2(extra), "warnings": data["warnings"]}
    for strategy in ("avalanche", "snowball"):
        out[strategy] = simulate(debts, budget, strategy)
        if extra > 0:
            out[f"{strategy}_extra"] = simulate(debts, budget + extra, strategy)
    return out
