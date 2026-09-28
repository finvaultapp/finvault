"""Investment CSV exports: holdings snapshots and activity (buys, sells, dividends...).

Supported layouts, detected from the header row:
- Wealthsimple holdings export ("Holdings report": Symbol, Quantity, Book Value, Market Price...)
- Wealthsimple activity: the structured activities export (activity_type, symbol, quantity,
  unit_price...) and the monthly statement CSV (date, transaction, description, amount), where
  the security and share count are read from the description.
- Questrade activity (Transaction Date, Action, Symbol, Quantity, Price, Gross/Net Amount...)
- Generic: any file with date, symbol, type and quantity/amount columns (English or French headers).

Parsers are tolerant: unknown rows (deposits, contributions, internal transfers) are skipped
and counted, never guessed. Cash movements stay with the account's ordinary transactions.
All quantities and amounts come out positive; `kind` gives the direction.
"""
import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .common import decode_bytes, detect_date_format, looks_like_date, normalize_header, parse_amount, try_parse_date

MAX_BYTES = 15 * 1024 * 1024


@dataclass
class ParsedActivity:
    date: date
    kind: str
    symbol: str = ""
    name: str = ""
    exchange: str = ""
    quantity: Decimal = Decimal(0)
    price: Decimal | None = None
    amount: Decimal = Decimal(0)
    commission: Decimal = Decimal(0)
    currency: str | None = None
    split_ratio: Decimal | None = None
    description: str = ""
    row: int | None = None


@dataclass
class ParsedHolding:
    symbol: str
    name: str = ""
    exchange: str = ""
    quantity: Decimal = Decimal(0)
    cost_basis: Decimal | None = None  # book value, total
    cost_currency: str | None = None
    cost_market: Decimal | None = None  # book value in the security's own currency, when given
    cost_market_currency: str | None = None
    price: Decimal | None = None
    price_currency: str | None = None
    market_value: Decimal | None = None
    security_type: str = ""
    account_label: str = ""
    row: int | None = None


@dataclass
class InvestParseResult:
    source: str  # wealthsimple_holdings | wealthsimple_activity | wealthsimple_statement | questrade | generic
    kind: str  # holdings | activity
    activities: list[ParsedActivity] = field(default_factory=list)
    holdings: list[ParsedHolding] = field(default_factory=list)
    as_of: date | None = None
    skipped: int = 0
    skipped_types: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)


# --- Activity types -----------------------------------------------------------------

# Normalised type text -> kind. None means "not an investment activity" (deposits etc.): skipped.
TYPE_WORDS: dict[str, str | None] = {
    "buy": "buy", "bought": "buy", "purchase": "buy", "achat": "buy", "b": "buy", "buy to open": "buy",
    "market buy": "buy", "limit buy": "buy", "trades buy": "buy",
    "sell": "sell", "sold": "sell", "sale": "sell", "vente": "sell", "s": "sell", "market sell": "sell",
    "limit sell": "sell",
    "div": "dividend", "dividend": "dividend", "dividends": "dividend", "cash dividend": "dividend",
    "dividende": "dividend", "dividendes": "dividend",
    "dist": "distribution", "distribution": "distribution", "distributions": "distribution",
    "cash distribution": "distribution", "cil": "distribution",
    "rei": "reinvested_dividend", "reinvest": "reinvested_dividend", "reinvestment": "reinvested_dividend",
    "reinvested dividend": "reinvested_dividend", "drip": "reinvested_dividend", "dividend reinvestment": "reinvested_dividend",
    "reinvested distribution": "reinvested_dividend", "reinvested": "reinvested_dividend",
    "reinvestissement": "reinvested_dividend",
    "fee": "fee", "fees": "fee", "fch": "fee", "commission": "fee", "management fee": "fee", "frais": "fee",
    "fees and rebates": "fee", "admin fee": "fee",
    "split": "split", "stock split": "split", "fractionnement": "split", "stksplit": "split",
    "roc": "return_of_capital", "return of capital": "return_of_capital", "remboursement de capital": "return_of_capital",
    # Cash side: stays with the account's transactions.
    "deposit": None, "dep": None, "con": None, "cont": None, "contribution": None, "withdrawal": None, "wd": None,
    "wdr": None, "transfer": None, "tfr": None, "int": None, "interest": None, "nrt": None, "lending": None,
    "loan": None, "recall": None, "fxt": None, "exchange": None, "brw": None, "cot": None, "deposits": None,
    "withdrawals": None, "interest income": None, "tax": None, "withholding tax": None, "nac": None,
}


def classify_type(*texts: str) -> tuple[str | None, bool]:
    """Return (kind, known). known=False means the text wasn't recognised at all."""
    for text in texts:
        t = normalize_header(text or "")
        if not t:
            continue
        if t in TYPE_WORDS:
            return TYPE_WORDS[t], True
        # Longest phrase contained in the text wins ("reinvested dividend" before "dividend").
        for word in sorted((w for w in TYPE_WORDS if len(w) > 3), key=len, reverse=True):
            if re.search(rf"\b{re.escape(word)}\b", t):
                return TYPE_WORDS[word], True
    return None, False


# --- CSV plumbing -------------------------------------------------------------------

def _rows(text: str) -> list[list[str]]:
    lines = [l for l in text.splitlines()[:30] if l.strip()]
    delim = max([",", ";", "\t"], key=lambda d: sum(l.count(d) for l in lines))
    rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text), delimiter=delim)]
    return [r for r in rows if any(c for c in r)]


COLS: dict[str, list[str]] = {
    "date": ["transaction date", "transaction_date", "trade date", "date", "activity date", "process date",
             "date de transaction", "date d operation", "settlement date"],
    "type": ["action", "activity type", "activity_type", "transaction type", "type", "transaction", "activity",
             "type d operation", "operation"],
    "subtype": ["activity sub type", "activity_sub_type", "sub type", "subtype"],
    "symbol": ["symbol", "ticker", "security symbol", "symbole", "code"],
    "name": ["name", "security name", "security", "security description", "nom", "titre", "description"],
    "quantity": ["quantity", "qty", "shares", "units", "quantite", "nombre de parts", "unites"],
    "price": ["unit price", "unit_price", "price", "execution price", "prix", "prix unitaire", "market price"],
    "amount": ["gross amount", "amount", "value", "montant", "montant brut", "net cash amount", "net_cash_amount",
               "net amount", "montant net"],
    "net": ["net amount", "net cash amount", "net_cash_amount", "montant net"],
    "commission": ["commission", "commissions", "fees", "fee", "frais"],
    "currency": ["currency", "devise", "market price currency", "price currency"],
    "exchange": ["exchange", "market", "bourse", "mic"],
    "ratio": ["split ratio", "ratio"],
    "description": ["description", "details", "memo"],
}


def _norm_header(h: str) -> str:
    return normalize_header(h.replace("_", " "))


def _find_header(rows: list[list[str]], must: set[str]) -> int | None:
    for i, row in enumerate(rows[:30]):
        cells = {_norm_header(c) for c in row}
        if must <= cells:
            return i
    return None


def _map(headers: list[str], roles: list[str]) -> dict[str, int]:
    norm = [_norm_header(h) for h in headers]
    out: dict[str, int] = {}
    used: set[int] = set()
    for role in roles:
        for syn in COLS[role]:
            syn = _norm_header(syn)
            idx = next((i for i, h in enumerate(norm) if h == syn and i not in used), None)
            if idx is not None:
                out[role] = idx
                used.add(idx)
                break
    return out


def _cell(r: list[str], cols: dict[str, int], role: str) -> str:
    i = cols.get(role)
    return r[i].strip() if i is not None and i < len(r) else ""


def _num(value: str) -> Decimal | None:
    v = (value or "").strip()
    if not v or v.upper() in {"N/A", "N/D", "-"}:
        return None
    v = re.sub(r"(?i)\b(shares?|units?|parts?)\b", "", v).strip()
    # parse_amount handles "$1,234.56", "(12.00)" and decimal commas; allow more than 2 decimals too.
    if re.fullmatch(r"-?\d+\.\d{3,}", v):
        return Decimal(v)
    return parse_amount(v)


def _dates(values: list[str]) -> tuple[str | None, bool]:
    return detect_date_format([v for v in values if v])


def _clean_symbol(s: str) -> str:
    s = (s or "").strip().upper()
    return re.sub(r"\s+", "", s)


def _split_exchange(symbol: str) -> tuple[str, str]:
    """'XEQT.TO' -> ('XEQT', 'TSX'); 'TSX:XEQT' -> ('XEQT', 'TSX')."""
    m = re.fullmatch(r"(TSX|TSXV|NYSE|NASDAQ|NEO|CSE|ARCA|AMEX):(.+)", symbol)
    if m:
        return m.group(2), m.group(1)
    for suffix, ex in ((".TO", "TSX"), (".TSX", "TSX"), (".V", "TSXV"), (".NE", "NEO"), (".CN", "CSE")):
        if symbol.endswith(suffix) and len(symbol) > len(suffix):
            return symbol[: -len(suffix)], ex
    return symbol, ""


def _exchange_name(value: str) -> str:
    v = (value or "").strip().upper()
    return {"XTSE": "TSX", "TSE": "TSX", "TOR": "TSX", "XTSX": "TSXV", "XNYS": "NYSE", "XNAS": "NASDAQ",
            "ARCX": "ARCA", "NEOE": "NEO", "XCNQ": "CSE", "BATS": "CBOE"}.get(v, v)


# --- Holdings -----------------------------------------------------------------------

def _as_of_from_text(text: str) -> date | None:
    m = re.search(r"(?i)as of[^0-9]{0,20}(\d{4}-\d{2}-\d{2})", text) or re.search(r"(?i)au[^0-9]{0,10}(\d{4}-\d{2}-\d{2})", text)
    if m:
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            return None
    return None


def parse_holdings(rows: list[list[str]], header_idx: int, text: str, source: str) -> InvestParseResult:
    res = InvestParseResult(source=source, kind="holdings", columns=rows[header_idx])
    headers = [_norm_header(h) for h in rows[header_idx]]

    def find(*names):
        for n in names:
            n = _norm_header(n)
            if n in headers:
                return headers.index(n)
        return None

    ci = {
        "symbol": find("symbol", "ticker", "symbole"),
        "name": find("name", "security name", "description", "nom"),
        "exchange": find("exchange", "mic", "bourse"),
        "quantity": find("quantity", "qty", "shares", "units", "quantite"),
        # Book value in the account's (CAD) currency first, then in the market currency.
        "book": find("book value (cad)", "book value cad", "book value", "book cost", "total cost", "cost basis",
                     "valeur comptable", "cout"),
        "book_ccy": find("book value currency (cad)", "book value currency", "book currency"),
        "book_mkt": find("book value (market)", "book value market"),
        "book_mkt_ccy": find("book value currency (market)", "book value currency market"),
        "price": find("market price", "price", "last price", "prix"),
        "price_ccy": find("market price currency", "price currency", "currency", "devise"),
        "mv": find("market value", "value", "valeur marchande"),
        "type": find("security type", "asset type", "type"),
        "account": find("account name", "account type", "account"),
    }
    res.as_of = _as_of_from_text(text)
    for n, r in enumerate(rows[header_idx + 1:], start=1):
        def c(key):
            i = ci.get(key)
            return r[i].strip() if i is not None and i < len(r) else ""
        sym = _clean_symbol(c("symbol"))
        qty = _num(c("quantity"))
        if not sym or qty is None:
            if any(x.strip() for x in r) and not _as_of_from_text(" ".join(r)):
                res.skipped += 1
            continue
        sym, ex = _split_exchange(sym)
        book = _num(c("book"))
        book_ccy = (c("book_ccy") or "").upper() or None
        book_mkt = _num(c("book_mkt"))
        h = ParsedHolding(symbol=sym, name=c("name"), exchange=_exchange_name(c("exchange")) or ex, quantity=abs(qty),
                          cost_basis=abs(book) if book is not None else None, cost_currency=book_ccy,
                          cost_market=abs(book_mkt) if book_mkt is not None else None,
                          cost_market_currency=(c("book_mkt_ccy") or "").upper()[:3] or None,
                          price=_num(c("price")), price_currency=(c("price_ccy") or "").upper()[:3] or None,
                          market_value=_num(c("mv")), security_type=c("type"), account_label=c("account"), row=n)
        if h.price is None and h.market_value is not None and h.quantity:
            h.price = abs(h.market_value) / h.quantity
        res.holdings.append(h)
    if not res.holdings:
        res.warnings.append("No positions found. The file needs Symbol and Quantity columns.")
    return res


# --- Activity -----------------------------------------------------------------------

_WS_DESC = re.compile(
    r"^(?P<sym>[A-Z0-9][A-Z0-9.\-]{0,14})\s*-\s*(?P<name>.+?):\s*(?P<rest>.*)$")
_WS_TRADE = re.compile(r"(?i)\b(bought|sold)\s+(?P<qty>[\d.,]+)\s+shares?")
# "at $25.10" or "at 25.10", but not "executed at 2026-01-05".
_WS_PRICE = re.compile(r"(?i)\bat\s+(?:\$\s*(?P<p1>\d[\d,]*(?:\.\d+)?)|(?P<p2>\d[\d,]*\.\d+))(?![\d-])")
_WS_SPLIT = re.compile(r"(?i)(?P<a>\d+(?:\.\d+)?)\s*(?:for|:|-for-)\s*(?P<b>\d+(?:\.\d+)?)")


def _activity(res: InvestParseResult, n: int, when: date, kind: str, sym: str, name: str, qty, price, amount,
              commission, currency, ratio=None, description="", exchange="") -> None:
    qty = abs(qty) if qty is not None else Decimal(0)
    amount = abs(amount) if amount is not None else None
    price = abs(price) if price is not None else None
    if amount is None and price is not None and qty:
        amount = qty * price
    if price is None and amount and qty and kind in {"buy", "sell", "reinvested_dividend"}:
        price = amount / qty
    if kind == "split":
        if ratio is None:
            res.warnings.append(f"Row {n}: split without a ratio was skipped. Add it by hand.")
            res.skipped += 1
            return
    elif kind in {"buy", "sell"} and (not qty or amount is None):
        res.warnings.append(f"Row {n}: skipped, a {kind} needs a quantity and a price or amount.")
        res.skipped += 1
        return
    elif amount is None and kind != "reinvested_dividend":
        res.warnings.append(f"Row {n}: skipped, no amount.")
        res.skipped += 1
        return
    sym, ex = _split_exchange(_clean_symbol(sym))
    if kind != "fee" and not sym:
        res.warnings.append(f"Row {n}: skipped, no symbol.")
        res.skipped += 1
        return
    res.activities.append(ParsedActivity(
        date=when, kind=kind, symbol=sym, name=name.strip()[:200], exchange=exchange or ex, quantity=qty, price=price,
        amount=amount or Decimal(0), commission=abs(commission or Decimal(0)),
        currency=(currency or "").upper()[:3] or None, split_ratio=ratio, description=description[:500], row=n))


def _skip(res: InvestParseResult, type_text: str) -> None:
    res.skipped += 1
    key = type_text.strip() or "(blank)"
    res.skipped_types[key] = res.skipped_types.get(key, 0) + 1


def parse_activity(rows: list[list[str]], header_idx: int, source: str) -> InvestParseResult:
    res = InvestParseResult(source=source, kind="activity", columns=rows[header_idx])
    headers = rows[header_idx]
    cols = _map(headers, ["date", "subtype", "type", "symbol", "quantity", "price", "commission", "currency",
                          "exchange", "ratio", "net", "amount", "name", "description"])
    if cols.get("net") == cols.get("amount"):
        cols.pop("net", None)
    if "name" in cols and cols.get("name") == cols.get("description"):
        cols.pop("description")
    data = rows[header_idx + 1:]
    if "date" not in cols or "type" not in cols:
        res.warnings.append("Could not find the date and type columns.")
        return res
    di = cols["date"]
    dated = [r for r in data if di < len(r) and looks_like_date(r[di])]
    res.skipped += len([r for r in data if r not in dated])
    fmt, _ = _dates([r[di] for r in dated])
    if not fmt:
        res.warnings.append("Could not recognise the date format.")
        return res
    for n, r in enumerate(dated, start=1):
        when = try_parse_date(r[di], fmt)
        type_text = _cell(r, cols, "type")
        sub = _cell(r, cols, "subtype")
        desc = _cell(r, cols, "description") or _cell(r, cols, "name")
        kind, known = classify_type(sub, type_text) if sub else classify_type(type_text)
        if kind is None and not known:
            kind, known = classify_type(desc)
        if kind is None:
            _skip(res, type_text)
            continue
        qty = _num(_cell(r, cols, "quantity"))
        price = _num(_cell(r, cols, "price"))
        amount = _num(_cell(r, cols, "amount")) or _num(_cell(r, cols, "net")) or None  # 0 means "not given"
        commission = _num(_cell(r, cols, "commission"))
        ratio = _num(_cell(r, cols, "ratio"))
        if kind == "split" and ratio is None:
            m = _WS_SPLIT.search(desc)
            if m and Decimal(m.group("b")):
                ratio = Decimal(m.group("a")) / Decimal(m.group("b"))
        if kind == "reinvested_dividend" and not qty and amount is None:
            _skip(res, type_text)
            continue
        # Questrade lists REI rows with the shares bought; a DIV row usually precedes it with the cash.
        _activity(res, n, when, kind, _cell(r, cols, "symbol"), _cell(r, cols, "name") or desc, qty, price, amount,
                  commission, _cell(r, cols, "currency"), ratio, desc, _exchange_name(_cell(r, cols, "exchange")))
    return res


def parse_ws_statement(rows: list[list[str]], header_idx: int) -> InvestParseResult:
    """Wealthsimple monthly statement CSV: date, transaction, description, amount, balance, currency."""
    res = InvestParseResult(source="wealthsimple_statement", kind="activity", columns=rows[header_idx])
    headers = [_norm_header(h) for h in rows[header_idx]]
    idx = {k: headers.index(k) for k in ("date", "transaction", "description", "amount", "currency") if k in headers}
    data = [r for r in rows[header_idx + 1:] if idx["date"] < len(r) and looks_like_date(r[idx["date"]])]
    fmt, _ = _dates([r[idx["date"]] for r in data])
    if not fmt:
        res.warnings.append("Could not recognise the date format.")
        return res
    for n, r in enumerate(data, start=1):
        get = lambda k: r[idx[k]].strip() if k in idx and idx[k] < len(r) else ""  # noqa: E731
        when = try_parse_date(get("date"), fmt)
        kind, _ = classify_type(get("transaction"))
        desc = get("description")
        if kind is None:
            _skip(res, get("transaction"))
            continue
        m = _WS_DESC.match(desc)
        sym, name, rest = (m.group("sym"), m.group("name"), m.group("rest")) if m else ("", "", desc)
        qty = price = ratio = None
        t = _WS_TRADE.search(rest)
        if t:
            qty = _num(t.group("qty"))
        p = _WS_PRICE.search(rest)
        if p:
            price = _num(p.group("p1") or p.group("p2"))
        if kind == "split":
            s = _WS_SPLIT.search(rest)
            if s and Decimal(s.group("b")):
                ratio = Decimal(s.group("a")) / Decimal(s.group("b"))
        _activity(res, n, when, kind, sym, name, qty, price, _num(get("amount")), None, get("currency"), ratio, desc)
    return res


# --- Entry point --------------------------------------------------------------------

def _looks(headers: set[str], *names: str) -> bool:
    return all(_norm_header(n) in headers for n in names)


def _any(headers: set[str], *names: str) -> bool:
    return any(_norm_header(n) in headers for n in names)


def parse_investment_file(filename: str, raw: bytes, source: str | None = None) -> InvestParseResult:
    if len(raw) > MAX_BYTES:
        raise ValueError("File is larger than 15 MB.")
    text = decode_bytes(raw)
    if not filename.lower().endswith((".csv", ".txt", ".tsv")) and "," not in text[:2000] and ";" not in text[:2000]:
        raise ValueError("Use a CSV export. Excel files can be saved as CSV first.")
    rows = _rows(text)
    if not rows:
        raise ValueError("The file is empty.")

    # Find the header row: the first row with a symbol-ish or date-ish column pair.
    header_idx = None
    for i, row in enumerate(rows[:30]):
        cells = {_norm_header(c) for c in row}
        if (_any(cells, "symbol", "ticker", "symbole") and _any(cells, "quantity", "qty", "shares", "quantite", "units")) \
                or (_any(cells, "date", "transaction date", "trade date") and len(cells & {
                    "transaction", "action", "type", "activity type", "description", "amount"}) >= 2):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Couldn't find a header row with Symbol and Quantity (holdings) or Date and Type (activity).")
    headers = {_norm_header(c) for c in rows[header_idx]}
    has_date = _any(headers, "date", "transaction date", "trade date", "settlement date", "activity date")

    if source in (None, "", "auto"):
        if _looks(headers, "transaction", "description", "amount") and not _any(headers, "symbol", "quantity"):
            source = "wealthsimple_statement"
        elif _looks(headers, "action", "symbol") and _any(headers, "gross amount", "net amount"):
            source = "questrade"
        elif _looks(headers, "activity type", "symbol"):
            source = "wealthsimple_activity"
        elif not has_date:
            source = "wealthsimple_holdings" if _any(headers, "book value (cad)", "market price currency") else "generic_holdings"
        else:
            source = "generic"
    if source == "wealthsimple_statement":
        return parse_ws_statement(rows, header_idx)
    if source in ("wealthsimple_holdings", "generic_holdings"):
        return parse_holdings(rows, header_idx, text, source)
    return parse_activity(rows, header_idx, source)
