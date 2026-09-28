"""CSV statement parser with preset detection and a generic column matcher."""
import csv
import io
from decimal import Decimal

from .common import ParsedTxn, ParseResult, detect_date_format, looks_like_date, normalize_header, parse_amount, try_parse_date
from .presets import PRESETS, PRESETS_BY_ID

# Generic header synonyms, most specific first. English and French.
SYNONYMS: dict[str, list[str]] = {
    "date": ["transaction date", "trans date", "date of transaction", "date posted", "posted date", "posting date",
             "transfer date", "booking date", "value date", "activity date", "date de transaction",
             "date de l operation", "date operation", "date"],
    "description": ["description 1", "transaction details", "transaction description", "description", "merchant name",
                    "merchant", "details", "name", "libelle", "narrative", "particulars"],
    "description2": ["description 2", "sub description", "additional description", "memo"],
    "payee": ["payee", "beneficiaire"],
    "amount": ["transaction amount", "amount", "cad", "amount cad", "net amount", "montant", "value"],
    "debit": ["debit", "debits", "withdrawal", "withdrawals", "funds out", "money out", "paid out", "retrait",
              "retraits", "debit amount", "out"],
    "credit": ["credit", "credits", "deposit", "deposits", "funds in", "money in", "paid in", "depot", "depots",
               "credit amount", "in"],
    "currency": ["currency", "currency code", "devise"],
    "type": ["transaction type", "type of transaction", "activity type", "type"],
    "category": ["merchant category description", "merchant category", "category", "categorie"],
    "balance": ["running balance", "balance", "solde"],
    "id": ["reference number", "transaction id", "reference", "fitid"],
}
ROLES = list(SYNONYMS)
NEGATIVE_TYPES = {"debit", "dr", "withdrawal", "withdraw", "purchase", "sale", "fee", "charge", "retrait", "achat", "debit card"}
POSITIVE_TYPES = {"credit", "cr", "deposit", "refund", "return", "depot", "remboursement", "interest"}


def _sniff_delimiter(text: str) -> str:
    lines = [l for l in text.splitlines()[:30] if l.strip()]
    best, best_score = ",", -1
    for d in [",", ";", "\t", "|"]:
        counts = [l.count(d) for l in lines]
        common = max(set(counts), key=counts.count) if counts else 0
        score = common * sum(1 for c in counts if c == common)
        if common > 0 and score > best_score:
            best, best_score = d, score
    return best


def _find_header(rows: list[list[str]]) -> int | None:
    all_syn = {s for syns in SYNONYMS.values() for s in syns}
    for i, row in enumerate(rows[:30]):
        cells = [normalize_header(c) for c in row]
        hits = sum(1 for c in cells if c in all_syn)
        if hits >= 2 and not any(looks_like_date(c) for c in row if c.strip()):
            return i
    return None


def _match_preset(headers: list[str]) -> dict | None:
    hs = set(headers)
    for p in PRESETS:
        spec = p.get("csv")
        if spec and not spec.get("headerless") and not spec.get("weak") and all(s in hs for s in spec["signature"]):
            return p
    return None


def _auto_map_headers(headers: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    used: set[int] = set()
    for role in ROLES:
        for syn in SYNONYMS[role]:
            idx = next((i for i, h in enumerate(headers) if h == syn and i not in used), None)
            if idx is not None:
                mapping[role] = idx
                used.add(idx)
                break
    if "amount" in mapping and ("debit" in mapping or "credit" in mapping):
        # A real amount column wins; stray 'in'/'out' matches are dropped.
        mapping.pop("debit", None)
        mapping.pop("credit", None)
    if "description" not in mapping and "payee" in mapping:
        mapping["description"] = mapping.pop("payee")
    return mapping


def _infer_headerless(rows: list[list[str]]) -> dict[str, int]:
    """Guess columns from content: TD/CIBC style date, text, out, in[, balance]."""
    width = max(len(r) for r in rows)
    sample = rows[:200]

    def col(i):
        return [r[i].strip() if i < len(r) else "" for r in sample]

    date_cols, num_cols, text_cols, empty_cols = [], [], [], set()
    for i in range(width):
        vals = [v for v in col(i) if v]
        if not vals:
            empty_cols.add(i)
            continue
        if sum(looks_like_date(v) for v in vals) / len(vals) > 0.9:
            date_cols.append(i)
        elif sum(parse_amount(v) is not None for v in vals) / len(vals) > 0.8:
            num_cols.append(i)
        else:
            text_cols.append((sum(len(v) for v in vals) / len(vals), i))
    mapping: dict[str, int] = {}
    if date_cols:
        mapping["date"] = date_cols[0]
    if text_cols:
        mapping["description"] = max(text_cols)[1]
    # A short statement can have an all-empty "money in" (or "money out") column right next to
    # the other one; it is still a debit/credit pair, not amount + balance.
    if num_cols and num_cols[0] + 1 in empty_cols and len(num_cols) >= 2 and num_cols[1] == num_cols[0] + 2:
        mapping["debit"], mapping["credit"], mapping["balance"] = num_cols[0], num_cols[0] + 1, num_cols[1]
    elif num_cols and num_cols[0] - 1 in empty_cols and num_cols[0] - 1 > max(date_cols + [t[1] for t in text_cols] + [-1]):
        mapping["debit"], mapping["credit"] = num_cols[0] - 1, num_cols[0]
        if len(num_cols) >= 2:
            mapping["balance"] = num_cols[1]
    elif len(num_cols) == 1:
        mapping["amount"] = num_cols[0]
    elif len(num_cols) >= 2:
        a, b = num_cols[0], num_cols[1]
        both = sum(1 for r in sample if a < len(r) and b < len(r) and r[a].strip() and r[b].strip())
        if both / max(len(sample), 1) < 0.1:
            mapping["debit"], mapping["credit"] = a, b
            if len(num_cols) >= 3:
                mapping["balance"] = num_cols[2]
        else:
            mapping["amount"], mapping["balance"] = a, b
    return mapping


def parse_csv(text: str, *, preset_id: str | None = None, mapping: dict | None = None,
              date_format: str | None = None, invert: bool | None = None,
              account_type: str | None = None, account_currency: str | None = None) -> ParseResult:
    result = ParseResult(format="csv")
    delim = _sniff_delimiter(text)
    rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text), delimiter=delim)]
    rows = [r for r in rows if any(c for c in r)]
    if not rows:
        result.warnings.append("The file is empty.")
        return result

    preset = PRESETS_BY_ID.get(preset_id) if preset_id else None
    spec = (preset or {}).get("csv") or {}
    header_idx = None if spec.get("headerless") else _find_header(rows)

    if header_idx is not None:
        headers = [normalize_header(h) for h in rows[header_idx]]
        result.columns = rows[header_idx]
        data = rows[header_idx + 1:]
        if not preset:
            preset = _match_preset(headers)
            spec = (preset or {}).get("csv") or {}
    else:
        headers = []
        data = rows
        width = max(len(r) for r in rows)
        result.columns = [f"Column {i + 1}" for i in range(width)]

    result.preset = preset["id"] if preset else None

    # Resolve the column mapping: explicit > preset > generic.
    if mapping:
        cols = {k: int(v) for k, v in mapping.items() if v is not None and str(v) != ""}
    elif spec.get("map") and (spec.get("headerless") or header_idx is not None):
        cols = {}
        for role, ref in spec["map"].items():
            if isinstance(ref, int):
                cols[role] = ref
            elif ref in headers:
                cols[role] = headers.index(ref)
        if spec.get("headerless") and header_idx is None:
            width = max(len(r) for r in data)
            cols = {k: v for k, v in cols.items() if v < width}
    elif header_idx is not None:
        cols = _auto_map_headers(headers)
    else:
        cols = _infer_headerless(data)
    result.mapping = cols
    result.sample_rows = data[:8]

    if "date" not in cols or not ({"amount", "debit", "credit"} & cols.keys()):
        result.warnings.append("Could not find the date and amount columns. Pick them in the column mapping.")
        return result

    # Keep only rows whose date cell parses; this drops footers and totals.
    di = cols["date"]
    data = [r for r in data if di < len(r) and looks_like_date(r[di])]
    fmt, ambiguous = detect_date_format([r[di] for r in data], date_format or spec.get("date_format"))
    result.date_format, result.date_format_ambiguous = fmt, ambiguous
    if not fmt:
        result.warnings.append("Could not recognise the date format. Choose one in the preview.")
        return result

    def cell(r, role):
        i = cols.get(role)
        return r[i].strip() if i is not None and i < len(r) else ""

    parsed: list[ParsedTxn] = []
    for n, r in enumerate(data, start=1):
        when = try_parse_date(r[di], fmt)
        currency = cell(r, "currency").upper() or None
        if "amount" in cols:
            amount = parse_amount(cell(r, "amount"))
            if amount is None and "amount_alt" in cols:
                amount = parse_amount(cell(r, "amount_alt"))
                if amount is not None:
                    currency = spec.get("amount_alt_currency", currency)
        else:
            out_, in_ = parse_amount(cell(r, "debit")), parse_amount(cell(r, "credit"))
            amount = None if out_ is None and in_ is None else (abs(in_ or Decimal(0)) - abs(out_ or Decimal(0)))
        if when is None or amount is None:
            result.warnings.append(f"Row {n}: skipped, could not read the date or amount.")
            continue
        desc = " ".join(x for x in [cell(r, "description"), cell(r, "description2")] if x)
        parsed.append(ParsedTxn(
            date=when, amount=amount, description=desc or cell(r, "type") or "(no description)",
            payee=cell(r, "payee"), external_id=cell(r, "id") or None,
            currency=currency, bank_category=cell(r, "category") or None, row=n,
        ))
        parsed[-1].memo = cell(r, "type")

    # All-positive amounts with a Debit/Credit type column: use the type for the sign.
    if parsed and "type" in cols and all(t.amount >= 0 for t in parsed):
        types = {t.memo.lower() for t in parsed}
        if types & (NEGATIVE_TYPES | POSITIVE_TYPES):
            for t in parsed:
                if t.memo.lower() in NEGATIVE_TYPES:
                    t.amount = -t.amount
            result.warnings.append("Amounts were all positive, so the transaction type column was used to set the sign.")

    if invert is None:
        invert = bool(spec.get("invert"))
        if not invert and account_type == "credit_card" and parsed:
            positives = sum(1 for t in parsed if t.amount > 0)
            if positives / len(parsed) > 0.7:
                invert = True
                result.warnings.append("Most amounts are positive on a credit card, so purchases were treated as spending (amounts flipped). Turn off \"Flip signs\" if that is wrong.")
    if invert:
        for t in parsed:
            t.amount = -t.amount
    result.inverted = bool(invert)

    if result.date_format_ambiguous:
        result.warnings.append("Dates could be month-first or day-first. Assumed month/day/year; change it if that is wrong.")
    currencies = {t.currency for t in parsed if t.currency}
    if account_currency and currencies - {account_currency.upper()}:
        result.warnings.append(f"This file contains amounts in {', '.join(sorted(currencies))}; they will be recorded in the account currency ({account_currency}).")
    result.transactions = parsed
    return result
