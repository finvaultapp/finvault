"""Registered accounts: counting a plan year by movement type, next year's room as an estimate, and the
bookkeeping after a statement is imported into a TFSA, FHSA or RRSP account.

FinVault never decides anyone's CRA room. The member copies it from CRA My Account; until then a plan made
by an import has no room (room_set False). The next-year figures here are estimates from public rules and
the lines FinVault has seen, labelled as such on the page. CRA's figure always wins.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..importers.registered import KINDS, PLAN_MOVES, classify
from ..models import Account, Category, ImportBatch, PlanEntry, RegisteredPlan, Transaction, User
from .reports import f2

ZERO = Decimal(0)
# Contributions that use room. Withdrawals are recorded but never give room back in the same year.
USES_ROOM = ("contribution", "rrsp_to_fhsa")
NOT_COUNTED = ("transfer_in", "transfer_out", "growth", "fee", "trade", "other")

# TFSA dollar limit by year (CRA). A year that isn't here hasn't been announced yet (CRA announces each fall).
TFSA_LIMITS = {
    2009: 5000, 2010: 5000, 2011: 5000, 2012: 5000, 2013: 5500, 2014: 5500, 2015: 10000, 2016: 5500, 2017: 5500,
    2018: 5500, 2019: 6000, 2020: 6000, 2021: 6000, 2022: 6000, 2023: 6500, 2024: 7000, 2025: 7000, 2026: 7000,
}
FHSA_ANNUAL = Decimal(8000)
FHSA_CARRY_MAX = Decimal(8000)
FHSA_LIFETIME = Decimal(40000)
FHSA_MAX_YEARS = 15  # the account must close by the end of the 15th year after it was first opened
FHSA_CLOSE_WARN_YEARS = 2


# --- Which lines belong to a plan ------------------------------------------------------------

def plan_account_ids(db: Session, plan: RegisteredPlan) -> list[int]:
    """The account linked by hand plus every account of the member marked as this kind of plan."""
    ids = set(db.scalars(select(Account.id).where(Account.user_id == plan.user_id,
                                                   Account.registered_kind == plan.kind)))
    if plan.account_id:
        ids.add(plan.account_id)
    return sorted(ids)


def _lines(db: Session, plan: RegisteredPlan) -> list[dict]:
    ids = plan_account_ids(db, plan)
    if not ids:
        return []
    income = set(db.scalars(select(Category.id).where(Category.user_id == plan.user_id, Category.kind == "income")))
    rows = db.scalars(select(Transaction).where(
        Transaction.user_id == plan.user_id, Transaction.account_id.in_(ids),
        Transaction.date >= date(plan.year, 1, 1), Transaction.date <= date(plan.year, 12, 31)).order_by(Transaction.date))
    out = []
    for t in rows:
        move = t.plan_move
        legacy = move is None
        if legacy:
            # Lines without a type keep the older rule: income lines (interest, dividends) are growth, money in
            # is a contribution and money out a withdrawal.
            if t.category_id in income:
                move = "growth"
            else:
                move = "contribution" if t.amount > 0 else "withdrawal" if t.amount < 0 else "other"
        out.append({"id": f"t{t.id}", "tx_id": t.id, "date": t.date.isoformat(), "amount": Decimal(t.amount),
                    "note": t.description, "source": "account", "account_id": t.account_id, "move": move,
                    "typed": not legacy})
    return out


def counts(db: Session, plan: RegisteredPlan) -> dict:
    """Totals for one plan year by movement type, plus the lines that matter for room."""
    manual = [{"id": e.id, "date": e.date.isoformat(), "amount": Decimal(e.amount), "note": e.note, "source": "manual",
               "move": "contribution" if e.amount > 0 else "withdrawal", "typed": True}
              for e in db.scalars(select(PlanEntry).where(PlanEntry.plan_id == plan.id).order_by(PlanEntry.date))]
    lines = manual + _lines(db, plan)
    sums: dict[str, Decimal] = defaultdict(lambda: ZERO)
    n: dict[str, int] = defaultdict(int)
    for e in lines:
        sums[e["move"]] += e["amount"]
        n[e["move"]] += 1
    used = sum((sums[m] for m in USES_ROOM), ZERO)
    shown = [e for e in lines if e["move"] in USES_ROOM + ("withdrawal", "transfer_in", "transfer_out")]
    return {
        "used": used,
        "withdrawn": -sums["withdrawal"],
        "by_type": {
            "contribution": sums["contribution"], "rrsp_to_fhsa": sums["rrsp_to_fhsa"], "withdrawal": -sums["withdrawal"],
            "transfer_in": sums["transfer_in"], "transfer_out": -sums["transfer_out"], "growth": sums["growth"],
            "fee": -sums["fee"],
        },
        "lines": {m: n[m] for m in PLAN_MOVES if n[m]},
        "entries": sorted(shown, key=lambda e: e["date"]),
        "untyped": sum(1 for e in lines if not e["typed"]),
    }


# --- Next year's room (estimates) -------------------------------------------------------------

def tfsa_estimate(year: int, room: Decimal | None, used: Decimal, withdrawn: Decimal) -> dict | None:
    """Unused room this year + this year's withdrawals + next year's dollar limit."""
    if room is None:
        return {"code": "needs_room", "year": year + 1}
    unused = room - used
    known = unused + withdrawn
    limit = TFSA_LIMITS.get(year + 1)
    out = {"year": year + 1, "unused": f2(unused), "withdrawn": f2(withdrawn)}
    if limit is None:
        return out | {"code": "tfsa_next_partial", "amount": f2(known)}
    return out | {"code": "tfsa_next", "amount": f2(known + limit), "limit": limit}


def fhsa_estimate(year: int, room: Decimal | None, used: Decimal, lifetime: Decimal, opened: int) -> dict | None:
    """min(8,000 + min(max(unused, 0), 8,000), 40,000 - lifetime contributions so far)."""
    close_year = opened + FHSA_MAX_YEARS
    if year + 1 > close_year:
        return {"code": "fhsa_closed", "year": year + 1, "close_year": close_year, "opened": opened}
    if room is None:
        return {"code": "needs_room", "year": year + 1}
    unused = room - used
    carry = min(max(unused, ZERO), FHSA_CARRY_MAX)
    lifetime_left = max(FHSA_LIFETIME - lifetime, ZERO)
    amount = max(min(FHSA_ANNUAL + carry, lifetime_left), ZERO)
    return {"code": "fhsa_next", "year": year + 1, "amount": f2(amount), "carry": f2(carry),
            "lifetime": f2(lifetime), "lifetime_left": f2(lifetime_left), "opened": opened, "close_year": close_year,
            "closing_soon": year + 1 >= close_year - FHSA_CLOSE_WARN_YEARS}


def estimate(plan: RegisteredPlan, c: dict, history: list[tuple[RegisteredPlan, dict]]) -> dict | None:
    """`history` is every plan of the same kind for this member with its counts (any order)."""
    room = Decimal(plan.room) if plan.room_set else None
    if plan.kind == "tfsa":
        return tfsa_estimate(plan.year, room, c["used"], c["withdrawn"])
    if plan.kind == "fhsa":
        opened = min(p.year for p, _ in history)
        lifetime = sum((hc["used"] for p, hc in history if p.year <= plan.year), ZERO)
        return fhsa_estimate(plan.year, room, c["used"], lifetime, opened)
    return None  # RRSP: depends on earned income and the Notice of Assessment


# --- After an import ----------------------------------------------------------------------------

def ensure_plans(db: Session, user: User, account: Account, years: set[int]) -> dict[int, RegisteredPlan]:
    """The plan for each year of this account's kind, created (with no room yet) when missing."""
    kind = account.registered_kind
    plans = {}
    for y in sorted(years):
        p = db.scalar(select(RegisteredPlan).where(RegisteredPlan.user_id == user.id, RegisteredPlan.kind == kind,
                                                   RegisteredPlan.year == y))
        if p is None:
            p = RegisteredPlan(user_id=user.id, kind=kind, year=y, room=ZERO, room_set=False, account_id=account.id,
                               notes="")
            db.add(p)
        elif p.account_id is None:
            p.account_id = account.id
        plans[y] = p
    db.flush()
    return plans


def backfill(db: Session, account: Account) -> int:
    """Give untyped lines in a newly marked registered account a type, and make sure each year has a plan."""
    if account.registered_kind not in KINDS:
        return 0
    rows = list(db.scalars(select(Transaction).where(Transaction.account_id == account.id,
                                                     Transaction.plan_move.is_(None))))
    income = set(db.scalars(select(Category.id).where(Category.user_id == account.user_id, Category.kind == "income")))
    for t in rows:
        move = classify(account.registered_kind, Decimal(t.amount), (), t.description)
        if t.category_id in income and move in ("contribution", "withdrawal"):
            move = "growth"
        t.plan_move = move
    years = set(db.scalars(select(Transaction.date).where(Transaction.account_id == account.id)))
    user = db.get(User, account.user_id)
    ensure_plans(db, user, account, {d.year for d in years})
    return len(rows)


def import_summary(db: Session, user: User, account: Account, batch: ImportBatch) -> dict | None:
    """What a just-imported statement did to the plan: counted lines per year, and whether room is missing."""
    if account.registered_kind not in KINDS:
        return None
    rows = list(db.scalars(select(Transaction).where(Transaction.import_batch_id == batch.id)))
    plans = ensure_plans(db, user, account, {t.date.year for t in rows})
    db.commit()
    years = []
    for y, plan in sorted(plans.items()):
        mine = [t for t in rows if t.date.year == y]

        def total(move):
            ts = [t for t in mine if t.plan_move == move]
            return {"n": len(ts), "amount": f2(abs(sum((Decimal(t.amount) for t in ts), ZERO)))}

        years.append({"year": y, "plan_id": plan.id, "room_missing": not plan.room_set,
                      "contribution": total("contribution"), "rrsp_to_fhsa": total("rrsp_to_fhsa"),
                      "withdrawal": total("withdrawal"),
                      "not_counted": sum(1 for t in mine if (t.plan_move or "other") in NOT_COUNTED)})
    return {"kind": account.registered_kind, "years": years}


def pending_room(db: Session, user: User) -> list[dict]:
    """Plans made by an import that still need the member's CRA figure."""
    return [{"id": p.id, "kind": p.kind, "year": p.year} for p in db.scalars(
        select(RegisteredPlan).where(RegisteredPlan.user_id == user.id, RegisteredPlan.room_set.is_(False))
        .order_by(RegisteredPlan.year.desc()))]
