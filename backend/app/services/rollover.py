"""Envelope-style budget rollover.

Each budget has a mode:
  off        no carrying (the default; every month starts at its limit)
  carry      unspent money adds to next month; an overspent month carries nothing
  carry_all  unspent money adds to next month and overspending takes away from it

Walking month by month from the budget's start month (at most MAX_MONTHS back):
  available(m) = limit + carried(m)
  left(m)      = available(m) - spent(m)
  carried(m+1) = left(m)            for carry_all
               = max(left(m), 0)    for carry
The first month of the walk carries 0 in. Spending is counted the way budgets count it: splits and
the part other people owe you come from reports.effective_lines, refunds reduce spending, subcategory
spending counts toward the parent's budget, and amounts are converted to the base currency.
The walk uses today's limit for every past month (limits have no history).
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from ..models import Budget, User
from .currency import Converter

MAX_MONTHS = 24
MODES = ("off", "carry", "carry_all")


def month_index(y: int, m: int) -> int:
    return y * 12 + (m - 1)


def from_index(i: int) -> tuple[int, int]:
    return i // 12, i % 12 + 1


def carry_forward(limit: Decimal, spent: list[Decimal], mode: str) -> Decimal:
    """What carries into the month after `spent` (net spending per month, oldest first)."""
    if mode not in ("carry", "carry_all"):
        return Decimal(0)
    carried = Decimal(0)
    for s in spent:
        left = limit + carried - s
        carried = left if mode == "carry_all" else max(left, Decimal(0))
    return carried


def walk_start(target: int, start: date | None) -> int:
    """First month (as an index) whose spending counts toward the carry into `target`."""
    earliest = target - MAX_MONTHS
    return earliest if start is None else max(month_index(start.year, start.month), earliest)


def carried_amounts(db: Session, user: User, budgets: list[Budget], children: dict[int, list[int]],
                    y: int, m: int, conv: Converter) -> dict[int, Decimal]:
    """{budget_id: amount carried into month y-m} for budgets with rollover on."""
    from .reports import effective_lines, month_end

    target = month_index(y, m)
    active = [(b, walk_start(target, b.rollover_start)) for b in budgets if (b.rollover or "off") != "off"]
    active = [(b, s) for b, s in active if s < target]
    if not active:
        return {}
    first = min(s for _, s in active)
    fy, fm = from_index(first)
    ly, lm = from_index(target - 1)
    spent: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
    for d, amount, cat_id, currency, kind in effective_lines(db, user, date(fy, fm, 1), month_end(ly, lm)):
        if cat_id is None or kind == "transfer":
            continue
        v = conv.convert(Decimal(amount), currency, d)
        if v is not None:
            spent[(cat_id, month_index(d.year, d.month))] -= v
    out = {}
    for b, s in active:
        cats = [b.category_id, *children.get(b.category_id, [])]
        per_month = [sum((spent[(c, i)] for c in cats), Decimal(0)) for i in range(s, target)]
        out[b.id] = carry_forward(Decimal(b.amount), per_month, b.rollover)
    return out
