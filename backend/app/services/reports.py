"""Reports in the user's base currency. Unconvertible amounts are excluded and reported as warnings."""
import calendar
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account, Asset, Budget, Category, Goal, Share, Transaction, TransactionSplit, User
from .currency import Converter
from .invest import Portfolio
from .ledger import account_balances


def month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def last_months(n: int, today: date | None = None) -> list[tuple[int, int]]:
    today = today or date.today()
    out, y, m = [], today.year, today.month
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


def f2(x: Decimal | None) -> float:
    return float(round(x or Decimal(0), 2))


def _classify(amount: Decimal, kind: str | None) -> str | None:
    if kind == "transfer":
        return None
    if kind == "income":
        return "income"
    if kind == "expense":
        return "expense"
    return "income" if amount > 0 else "expense"


def effective_lines(db: Session, user: User, start: date, end: date, account_ids: list[int] | None = None):
    """(date, amount, category_id, currency, kind) as reports should count them.

    Split transactions contribute one line per split. Shares other people owe you are
    taken out, so a $100 dinner you split 50/50 counts as $50 of your spending. When a
    transaction is both split and shared, the shared part is removed proportionally.
    """
    q = (select(Transaction.id, Transaction.date, Transaction.amount, Transaction.category_id, Account.currency)
         .join(Account, Account.id == Transaction.account_id)
         .where(Transaction.user_id == user.id, Transaction.date >= start, Transaction.date <= end))
    if account_ids:
        q = q.where(Transaction.account_id.in_(account_ids))
    rows = db.execute(q).all()
    if not rows:
        return []
    kinds = dict(db.execute(select(Category.id, Category.kind).where(Category.user_id == user.id)).all())
    ids = [r.id for r in rows]
    splits: dict[int, list] = defaultdict(list)
    shared: dict[int, Decimal] = defaultdict(Decimal)
    for chunk in (ids[i:i + 900] for i in range(0, len(ids), 900)):
        for sp in db.execute(select(TransactionSplit.transaction_id, TransactionSplit.category_id, TransactionSplit.amount)
                             .where(TransactionSplit.transaction_id.in_(chunk))):
            splits[sp.transaction_id].append((sp.category_id, Decimal(sp.amount)))
        for sh in db.execute(select(Share.transaction_id, Share.amount).where(Share.transaction_id.in_(chunk))):
            shared[sh.transaction_id] += Decimal(sh.amount)
    out = []
    for r in rows:
        total = Decimal(r.amount)
        # Owed-to-you shares reduce what you spent (amount is negative, share positive).
        mine = total + shared[r.id] if total < 0 else total - shared[r.id]
        ratio = (mine / total) if total else Decimal(1)
        parts = splits.get(r.id) or [(r.category_id, total)]
        for cat_id, amt in parts:
            out.append((r.date, amt * ratio, cat_id, r.currency, kinds.get(cat_id)))
    return out


_tx_rows = effective_lines


def income_expense(db: Session, user: User, start: date, end: date, account_ids: list[int] | None = None) -> dict:
    conv = Converter(db, user.base_currency)
    cats = {c.id: c for c in db.scalars(select(Category).where(Category.user_id == user.id))}
    months: dict[str, dict] = {}
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        months[f"{y:04d}-{m:02d}"] = {"income": Decimal(0), "expense": Decimal(0)}
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    by_cat = {"income": defaultdict(Decimal), "expense": defaultdict(Decimal)}
    for d, amount, cat_id, currency, kind in _tx_rows(db, user, start, end, account_ids):
        side = _classify(Decimal(amount), kind)
        if side is None:
            continue
        v = conv.convert(Decimal(amount), currency, d)
        if v is None:
            continue
        key = f"{d.year:04d}-{d.month:02d}"
        if side == "income":
            months[key]["income"] += v
            by_cat["income"][cat_id] += v
        else:
            months[key]["expense"] -= v
            by_cat["expense"][cat_id] -= v

    def breakdown(side):
        items = []
        for cid, total in by_cat[side].items():
            c = cats.get(cid)
            items.append({"category_id": cid, "name": c.name if c else "Uncategorized",
                          "color": c.color if c else "#9aa4ad", "total": f2(total)})
        return sorted([i for i in items if i["total"] > 0], key=lambda i: -i["total"])

    series = [{"month": k, "income": f2(v["income"]), "expense": f2(v["expense"]),
               "net": f2(v["income"] - v["expense"])} for k, v in months.items()]
    total_in = sum(v["income"] for v in months.values())
    total_out = sum(v["expense"] for v in months.values())
    return {
        "currency": user.base_currency, "series": series,
        "totals": {"income": f2(total_in), "expense": f2(total_out), "net": f2(total_in - total_out),
                   "savings_rate": round(float((total_in - total_out) / total_in * 100), 1) if total_in > 0 else None},
        "expense_by_category": breakdown("expense"), "income_by_category": breakdown("income"),
        "warnings": conv.warnings(),
    }


def _asset_value_on(asset: Asset, on: date) -> Decimal | None:
    value = None
    for v in asset.values:
        if v.date <= on:
            value = Decimal(v.value)
        else:
            break
    return value


def net_worth(db: Session, user: User, months: int = 12) -> dict:
    conv = Converter(db, user.base_currency)
    accounts = list(db.scalars(select(Account).where(Account.user_id == user.id)))
    assets = list(db.scalars(select(Asset).where(Asset.user_id == user.id)))
    portfolio = Portfolio(db, user)  # investment holdings; empty for most accounts
    series = []
    today = date.today()
    periods = last_months(months)
    for y, m in periods:
        on = min(month_end(y, m), today)
        balances = account_balances(db, user.id, on)
        holdings = portfolio.account_values(on, conv, record=(y, m) == periods[-1]) if not portfolio.empty else {}
        pos = neg = Decimal(0)
        for a in accounts:
            if a.opening_date and a.opening_date > on and balances.get(a.id, 0) == 0 and a.id not in holdings:
                continue
            v = conv.convert(balances.get(a.id, Decimal(0)) + holdings.get(a.id, Decimal(0)), a.currency, on)
            if v is None:
                continue
            if v >= 0:
                pos += v
            else:
                neg -= v
        for asset in assets:
            raw = _asset_value_on(asset, on)
            if raw is None:
                continue
            v = conv.convert(raw, asset.currency, on)
            if v is None:
                continue
            if asset.is_liability:
                neg += abs(v)
            else:
                pos += v
        series.append({"month": f"{y:04d}-{m:02d}", "assets": f2(pos), "liabilities": f2(neg), "net": f2(pos - neg)})
    current = series[-1] if series else {"assets": 0, "liabilities": 0, "net": 0}
    previous = series[-2] if len(series) > 1 else None
    return {"currency": user.base_currency, "series": series, "current": current,
            "change": f2(Decimal(str(current["net"])) - Decimal(str(previous["net"]))) if previous else None,
            "warnings": conv.warnings(), "price_warnings": portfolio.price_warnings()}


def budgets_for_month(db: Session, user: User, y: int, m: int) -> dict:
    conv = Converter(db, user.base_currency)
    start, end = date(y, m, 1), month_end(y, m)
    cats = {c.id: c for c in db.scalars(select(Category).where(Category.user_id == user.id))}
    children = defaultdict(list)
    for c in cats.values():
        if c.parent_id:
            children[c.parent_id].append(c.id)
    spent = defaultdict(Decimal)
    for d, amount, cat_id, currency, kind in _tx_rows(db, user, start, end):
        if cat_id is None or kind == "transfer":
            continue
        v = conv.convert(Decimal(amount), currency, d)
        if v is not None:
            spent[cat_id] -= v  # spending is negative; refunds reduce it
    items = []
    for b in db.scalars(select(Budget).where(Budget.user_id == user.id)):
        c = cats.get(b.category_id)
        if not c:
            continue
        total = spent[c.id] + sum((spent[k] for k in children[c.id]), Decimal(0))
        budget = Decimal(b.amount)
        items.append({"id": b.id, "category_id": c.id, "name": c.name, "color": c.color, "budget": f2(budget),
                      "spent": f2(max(total, Decimal(0))), "remaining": f2(budget - total),
                      "percent": round(float(total / budget * 100), 1) if budget > 0 else None})
    items.sort(key=lambda i: -(i["percent"] or 0))
    # How far through the month we are, so the UI can show pace.
    today = date.today()
    progress = 1.0 if end < today else 0.0 if start > today else today.day / end.day
    return {"month": f"{y:04d}-{m:02d}", "currency": user.base_currency, "items": items,
            "total_budget": f2(sum((Decimal(str(i["budget"])) for i in items), Decimal(0))),
            "total_spent": f2(sum((Decimal(str(i["spent"])) for i in items), Decimal(0))),
            "month_progress": round(progress, 3), "warnings": conv.warnings()}


def goal_progress(db: Session, user: User) -> list[dict]:
    balances = account_balances(db, user.id)
    conv = Converter(db, user.base_currency)
    accounts = {a.id: a for a in db.scalars(select(Account).where(Account.user_id == user.id))}
    out = []
    for g in db.scalars(select(Goal).where(Goal.user_id == user.id).order_by(Goal.target_date.is_(None), Goal.target_date)):
        saved = Decimal(g.saved_amount or 0)
        missing_rate = False
        if g.account_id and g.account_id in accounts:
            acct = accounts[g.account_id]
            bal = balances.get(acct.id, Decimal(0))
            r = conv.rate(acct.currency, target=g.currency)
            if r is None:
                missing_rate = True
            else:
                saved = bal * r
        target = Decimal(g.target_amount)
        monthly_needed = None
        if g.target_date and saved < target:
            months_left = max((g.target_date.year - date.today().year) * 12 + g.target_date.month - date.today().month, 1)
            monthly_needed = f2((target - saved) / months_left)
        out.append({"id": g.id, "name": g.name, "target_amount": f2(target), "currency": g.currency,
                    "target_date": g.target_date.isoformat() if g.target_date else None,
                    "account_id": g.account_id, "saved_amount": f2(g.saved_amount), "saved": f2(saved),
                    "created_at": g.created_at.isoformat() if g.created_at else None,
                    "percent": round(float(saved / target * 100), 1) if target > 0 else None,
                    "monthly_needed": monthly_needed, "missing_rate": missing_rate})
    return out
