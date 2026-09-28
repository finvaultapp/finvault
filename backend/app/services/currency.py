"""Currency conversion with honest reporting of missing rates.

Lookup order for a pair on a date: direct rate, inverse rate, then a one-hop
cross rate through any currency that has rates to both sides. For each pair the
latest rate on or before the date is used; if the only rates are newer, the
oldest one is used. If no rate exists for a pair, conversion returns None and
the pair is recorded in `missing`, so callers can show a warning instead of
silently guessing.
"""
from bisect import bisect_right
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ExchangeRate


class Converter:
    def __init__(self, db: Session, target: str):
        self.target = target.upper()
        self.missing: set[str] = set()
        # (base, quote) -> sorted list of (date, rate)
        self._rates: dict[tuple[str, str], list[tuple[date, Decimal]]] = defaultdict(list)
        for r in db.scalars(select(ExchangeRate).order_by(ExchangeRate.date)):
            self._rates[(r.base, r.quote)].append((r.date, Decimal(r.rate)))
        self._neighbours: dict[str, set[str]] = defaultdict(set)
        for b, q in self._rates:
            self._neighbours[b].add(q)
            self._neighbours[q].add(b)

    def _pick(self, pair: tuple[str, str], on: date) -> Decimal | None:
        series = self._rates.get(pair)
        if not series:
            return None
        idx = bisect_right(series, (on, Decimal("Infinity")))
        return series[idx - 1][1] if idx else series[0][1]

    def _pair(self, a: str, b: str, on: date) -> Decimal | None:
        rate = self._pick((a, b), on)
        if rate is not None:
            return rate
        inv = self._pick((b, a), on)
        if inv:
            return Decimal(1) / inv
        return None

    def rate(self, source: str, on: date | None = None, target: str | None = None) -> Decimal | None:
        source = source.upper()
        target = (target or self.target).upper()
        on = on or date.today()
        if source == target:
            return Decimal(1)
        direct = self._pair(source, target, on)
        if direct is not None:
            return direct
        for via in self._neighbours[source] & self._neighbours[target]:
            a = self._pair(source, via, on)
            b = self._pair(via, target, on)
            if a is not None and b is not None:
                return a * b
        self.missing.add(f"{source}→{target}")
        return None

    def convert(self, amount: Decimal | float, source: str, on: date | None = None) -> Decimal | None:
        r = self.rate(source, on)
        if r is None:
            return None
        return Decimal(amount) * r

    def warnings(self) -> list[dict]:
        return [
            {"type": "missing_rate", "pair": p,
             "message": f"No exchange rate for {p}. Amounts in {p.split('→')[0]} are left out of totals until you add one."}
            for p in sorted(self.missing)
        ]


def fetch_ecb_rates(db: Session, base: str, symbols: list[str], api_url: str) -> int:
    """Fetch latest ECB reference rates. Only currency codes are sent."""
    import httpx

    symbols = [s for s in {s.upper() for s in symbols} if s != base.upper()]
    if not symbols:
        return 0
    resp = httpx.get(f"{api_url}/latest", params={"from": base.upper(), "to": ",".join(symbols)}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    on = date.fromisoformat(data["date"])
    count = 0
    for quote, rate in data.get("rates", {}).items():
        existing = db.scalar(select(ExchangeRate).where(
            ExchangeRate.base == base.upper(), ExchangeRate.quote == quote, ExchangeRate.date == on))
        if existing:
            existing.rate = Decimal(str(rate))
            existing.source = "ecb"
        else:
            db.add(ExchangeRate(base=base.upper(), quote=quote, date=on, rate=Decimal(str(rate)), source="ecb"))
        count += 1
    db.commit()
    return count
