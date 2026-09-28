"""Year in review, built on the report functions so splits and shared costs count the same way everywhere.

Totals, savings rate, months and categories come from reports.income_expense (which reads
reports.effective_lines). Merchants and single purchases need the description, so they read
transactions directly and apply the same "your part" rule as effective_lines: shares other people
owe you are taken out of the amount, and lines in transfer or income categories are left out.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..importers import normalize_merchant
from ..models import Account, Asset, Category, Share, Transaction, TransactionSplit, User
from . import plans as plans_service
from .currency import Converter
from .ledger import account_balances
from .reports import _asset_value_on, effective_lines, f2, income_expense

SUBSCRIPTION_NAMES = {"subscriptions", "abonnements"}


def net_worth_on(db: Session, user: User, conv: Converter, on: date) -> Decimal:
    balances = account_balances(db, user.id, on)
    total = Decimal(0)
    for a in db.scalars(select(Account).where(Account.user_id == user.id)):
        v = conv.convert(balances.get(a.id, Decimal(0)), a.currency, on)
        if v is not None:
            total += v
    for asset in db.scalars(select(Asset).where(Asset.user_id == user.id)):
        raw = _asset_value_on(asset, on)
        if raw is None:
            continue
        v = conv.convert(raw, asset.currency, on)
        if v is not None:
            total += -abs(v) if asset.is_liability else v
    return total


def _purchases(db: Session, user: User, conv: Converter, start: date, end: date) -> list[dict]:
    """Money-out transactions as your part (shares owed to you removed), in the base currency."""
    kinds = dict(db.execute(select(Category.id, Category.kind).where(Category.user_id == user.id)).all())
    rows = db.execute(select(Transaction.id, Transaction.date, Transaction.amount, Transaction.description,
                             Transaction.payee, Transaction.category_id, Transaction.transfer_id, Account.currency)
                      .join(Account, Account.id == Transaction.account_id)
                      .where(Transaction.user_id == user.id, Transaction.date >= start, Transaction.date <= end,
                             Transaction.amount < 0)).all()
    ids = [r.id for r in rows]
    shared: dict[int, Decimal] = defaultdict(Decimal)
    split_kinds: dict[int, list] = defaultdict(list)
    for chunk in (ids[i:i + 900] for i in range(0, len(ids), 900)):
        for sh in db.execute(select(Share.transaction_id, Share.amount).where(Share.transaction_id.in_(chunk))):
            shared[sh.transaction_id] += Decimal(sh.amount)
        for sp in db.execute(select(TransactionSplit.transaction_id, TransactionSplit.category_id, TransactionSplit.amount)
                             .where(TransactionSplit.transaction_id.in_(chunk))):
            split_kinds[sp.transaction_id].append((kinds.get(sp.category_id), Decimal(sp.amount)))
    out = []
    for r in rows:
        if r.transfer_id is not None:
            continue
        total = Decimal(r.amount)
        if split_kinds.get(r.id):
            spend = sum((-a for k, a in split_kinds[r.id] if k not in ("transfer", "income")), Decimal(0))
        elif kinds.get(r.category_id) in ("transfer", "income"):
            continue
        else:
            spend = -total
        mine = spend * ((total + shared[r.id]) / total) if total else spend
        if mine <= 0:
            continue
        v = conv.convert(mine, r.currency, r.date)
        if v is None:
            continue
        out.append({"id": r.id, "date": r.date.isoformat(), "description": r.description, "payee": r.payee,
                    "category_id": r.category_id, "amount": v})
    return out


def summary(db: Session, user: User, year: int) -> dict:
    start, end = date(year, 1, 1), date(year, 12, 31)
    today = date.today()
    conv = Converter(db, user.base_currency)
    cur = income_expense(db, user, start, end)
    prev = income_expense(db, user, date(year - 1, 1, 1), date(year - 1, 12, 31))
    cats = {c.id: c for c in db.scalars(select(Category).where(Category.user_id == user.id))}

    # Categories this year against last year.
    last = {c["category_id"]: c["total"] for c in prev["expense_by_category"]}
    categories = []
    for c in cur["expense_by_category"]:
        before = last.pop(c["category_id"], 0.0)
        categories.append({**c, "last_year": before, "change": f2(Decimal(str(c["total"])) - Decimal(str(before))),
                           "change_pct": round((c["total"] - before) / before * 100, 1) if before else None})
    for cid, before in last.items():
        cat = cats.get(cid)
        categories.append({"category_id": cid, "name": cat.name if cat else "Uncategorized",
                           "color": cat.color if cat else "#9aa4ad", "total": 0.0, "last_year": before,
                           "change": f2(-Decimal(str(before))), "change_pct": -100.0})

    months = [m for m in cur["series"] if m["income"] or m["expense"]]
    biggest = sorted(months, key=lambda m: -m["expense"])[:3]
    best_saving = max(months, key=lambda m: m["net"]) if months else None

    purchases = _purchases(db, user, conv, start, end)
    merchants: dict[str, dict] = {}
    for p in purchases:
        key = normalize_merchant(p["payee"] or p["description"]) or (p["payee"] or p["description"]).upper()
        m = merchants.setdefault(key, {"name": p["payee"] or p["description"], "total": Decimal(0), "count": 0})
        m["total"] += p["amount"]
        m["count"] += 1
    top_merchants = [{"name": m["name"][:120], "total": f2(m["total"]), "count": m["count"]}
                     for m in sorted(merchants.values(), key=lambda m: -m["total"])[:10]]
    largest = [{"id": p["id"], "date": p["date"], "description": p["description"][:160],
                "category": cats[p["category_id"]].name if p["category_id"] in cats else None, "amount": f2(p["amount"])}
               for p in sorted(purchases, key=lambda p: -p["amount"])[:8]]

    # Subscriptions: the Subscriptions category (English or French default name) and its sub-categories.
    sub_ids = {cid for cid, c in cats.items() if c.name.strip().lower() in SUBSCRIPTION_NAMES}
    sub_ids |= {cid for cid, c in cats.items() if c.parent_id in sub_ids}
    subs = Decimal(0)
    for d, amount, cat_id, currency, kind in effective_lines(db, user, start, end):
        if cat_id in sub_ids:
            v = conv.convert(Decimal(amount), currency, d)
            if v is not None:
                subs -= v

    # Net worth at the end of last year and at the end of this one (or today, for the current year).
    close = min(end, today)
    nw_start = net_worth_on(db, user, conv, date(year - 1, 12, 31))
    nw_end = net_worth_on(db, user, conv, close)

    registered = []
    for p in plans_service.all_summaries(db, user):
        if p["year"] == year:
            registered.append({"kind": p["kind"], "label": p["label"], "contributed": p["contributed"],
                               "withdrawn": p["withdrawn"], "room": p["room"]})

    has_data = db.scalar(select(func.count(Transaction.id)).where(
        Transaction.user_id == user.id, Transaction.date >= start, Transaction.date <= end)) or 0
    first_year = db.scalar(select(func.min(Transaction.date)).where(Transaction.user_id == user.id))
    warnings = {w["pair"]: w for w in cur["warnings"] + prev["warnings"] + conv.warnings()}
    return {
        "year": year, "currency": user.base_currency, "partial": close < end, "through": close.isoformat(),
        "transaction_count": has_data, "first_year": first_year.year if first_year else None,
        "totals": cur["totals"], "last_year_totals": prev["totals"],
        "net_worth": {"start": f2(nw_start), "end": f2(nw_end), "change": f2(nw_end - nw_start)},
        "months": cur["series"], "biggest_months": biggest, "best_month": best_saving,
        "categories": sorted(categories, key=lambda c: -max(c["total"], c["last_year"])),
        "top_merchants": top_merchants, "largest_purchases": largest,
        "subscriptions": {"total": f2(subs), "has_category": bool(sub_ids)},
        "registered": registered,
        "warnings": list(warnings.values()),
    }
