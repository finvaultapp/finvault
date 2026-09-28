from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import Account, Transaction, User
from ..services import reports
from ..services.currency import Converter
from ..services.invest import Portfolio
from ..services.ledger import account_balances
from .transactions import tx_out

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _month(month: str | None) -> tuple[int, int]:
    today = date.today()
    if month:
        return int(month[:4]), int(month[5:7])
    return today.year, today.month


def _prev(y: int, m: int) -> tuple[int, int]:
    return (y - 1, 12) if m == 1 else (y, m - 1)


@router.get("/income-expense")
def income_expense(start: date | None = None, end: date | None = None, account_id: list[int] | None = Query(None),
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    end = end or date.today()
    if not start:
        s = end.replace(day=1)
        for _ in range(11):
            s = (s - timedelta(days=1)).replace(day=1)
        start = s
    return reports.income_expense(db, user, start, end, account_id)


@router.get("/net-worth")
def net_worth(months: int = Query(12, ge=2, le=120), user: User = Depends(current_user), db: Session = Depends(get_db)):
    return reports.net_worth(db, user, months)


def _daily_balance(db: Session, user: User, conv: Converter, start: date, end: date) -> list[float]:
    """Total converted balance of all accounts at the end of each day in [start, end]."""
    accounts = {a.id: a for a in db.scalars(select(Account).where(Account.user_id == user.id))}
    opening = account_balances(db, user.id, start - timedelta(days=1))
    total = sum((v for aid, v in ((aid, conv.convert(b, accounts[aid].currency, start)) for aid, b in opening.items()) if v is not None), Decimal(0))
    per_day = defaultdict(Decimal)
    for d, amount, aid in db.execute(select(Transaction.date, Transaction.amount, Transaction.account_id)
                                     .where(Transaction.user_id == user.id, Transaction.date >= start, Transaction.date <= end)):
        v = conv.convert(Decimal(amount), accounts[aid].currency, d)
        if v is not None:
            per_day[d] += v
    out, d = [], start
    while d <= end:
        total += per_day[d]
        out.append(reports.f2(total))
        d += timedelta(days=1)
    return out


@router.get("/dashboard")
def dashboard(month: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    today = date.today()
    y, m = _month(month)
    start = date(y, m, 1)
    end = min(reports.month_end(y, m), today) if start <= today else reports.month_end(y, m)
    py, pm = _prev(y, m)
    pstart, pend = date(py, pm, 1), reports.month_end(py, pm)

    this_month = reports.income_expense(db, user, start, reports.month_end(y, m))
    last_month = reports.income_expense(db, user, pstart, pend)
    nw = reports.net_worth(db, user, 6)
    budgets = reports.budgets_for_month(db, user, y, m)

    conv = Converter(db, user.base_currency)
    on = min(reports.month_end(y, m), today)
    balances = account_balances(db, user.id, on)
    holdings = Portfolio(db, user).account_values(on, conv)  # investment accounts: cash + holdings
    accounts, total_balance, by_currency = [], Decimal(0), defaultdict(Decimal)
    for a in db.scalars(select(Account).where(Account.user_id == user.id, Account.is_archived.is_(False)).order_by(Account.name)):
        bal = balances.get(a.id, Decimal(0)) + holdings.get(a.id, Decimal(0))
        c = conv.convert(bal, a.currency, on)
        by_currency[a.currency] += bal
        if c is not None:
            total_balance += c
        accounts.append({"id": a.id, "name": a.name, "type": a.type, "institution": a.institution,
                         "currency": a.currency, "balance": reports.f2(bal),
                         "balance_converted": reports.f2(c) if c is not None else None})

    # Spending by category with month-over-month change and budget.
    last = {c["category_id"]: c["total"] for c in last_month["expense_by_category"]}
    budget_by_cat = {b["category_id"]: b for b in budgets["items"]}
    spending = []
    for c in this_month["expense_by_category"]:
        prev = last.get(c["category_id"])
        change = round((c["total"] - prev) / prev * 100) if prev else None
        b = budget_by_cat.get(c["category_id"])
        spending.append(c | {"last_total": prev, "change": change,
                             "budget": b["budget"] if b else None, "percent": b["percent"] if b else None})

    days = (reports.month_end(y, m) - start).days + 1
    flow = _daily_balance(db, user, conv, start, end)
    prev_flow = _daily_balance(db, user, conv, pstart, pend)
    series = [{"day": i + 1, "current": flow[i] if i < len(flow) else None,
               "previous": prev_flow[i] if i < len(prev_flow) else None} for i in range(days)]

    uncategorized = db.execute(select(func.count(Transaction.id), func.coalesce(func.sum(func.abs(Transaction.amount)), 0))
                               .where(Transaction.user_id == user.id, Transaction.category_id.is_(None))).one()
    recent = [tx_out(t) for t in db.scalars(select(Transaction).where(Transaction.user_id == user.id)
                                             .order_by(Transaction.date.desc(), Transaction.id.desc()).limit(8)).unique()]
    stale = []
    for a in accounts:
        last_date = db.scalar(select(func.max(Transaction.date)).where(Transaction.account_id == a["id"]))
        if last_date and (today - last_date).days > 35:
            stale.append({"id": a["id"], "name": a["name"], "last": last_date.isoformat()})
    assets_total = nw["current"]["assets"]
    warnings = {w["pair"]: w for w in this_month["warnings"] + nw["warnings"] + budgets["warnings"] + conv.warnings()}
    return {
        "month": f"{y:04d}-{m:02d}", "currency": user.base_currency,
        "net_worth": nw, "this_month": this_month["totals"], "last_month": last_month["totals"],
        "total_balance": reports.f2(total_balance),
        "balance_by_currency": {k: reports.f2(v) for k, v in by_currency.items()},
        "assets_total": assets_total, "spending": spending, "budgets": budgets,
        "balance_flow": {"series": series, "change": (flow[-1] - flow[0]) if flow else 0,
                         "start": start.isoformat(), "end": reports.month_end(y, m).isoformat(),
                         "previous_same_day": prev_flow[min(len(flow), len(prev_flow)) - 1] if flow and prev_flow else None,
                         "current_last": flow[-1] if flow else None, "days_elapsed": len(flow)},
        "accounts": accounts, "recent": recent,
        "uncategorized": {"count": uncategorized[0], "total": reports.f2(Decimal(str(uncategorized[1])))},
        "stale_accounts": stale, "warnings": list(warnings.values()),
    }
