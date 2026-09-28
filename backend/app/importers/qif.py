"""QIF (Quicken Interchange Format) parser."""
from .common import ParsedTxn, ParseResult, detect_date_format, parse_amount, try_parse_date


def looks_like_qif(text: str) -> bool:
    return text.lstrip().upper().startswith("!TYPE") or "\n^" in text[:5000]


def parse_qif(text: str, date_format: str | None = None) -> ParseResult:
    result = ParseResult(format="qif")
    records: list[dict] = []
    cur: dict = {}
    for line in text.splitlines():
        line = line.rstrip()
        if not line or line.startswith("!"):
            continue
        if line.startswith("^"):
            if cur:
                records.append(cur)
            cur = {}
            continue
        code, value = line[0], line[1:].strip()
        if code in "DTUPMLN" and code not in cur:
            cur[code] = value
    if cur:
        records.append(cur)

    fmt, ambiguous = detect_date_format([r.get("D", "") for r in records], date_format)
    result.date_format, result.date_format_ambiguous = fmt, ambiguous
    if not fmt:
        result.warnings.append("Could not recognise the date format in this QIF file.")
        return result
    for i, r in enumerate(records, start=1):
        when = try_parse_date(r.get("D", ""), fmt)
        amount = parse_amount(r.get("T") or r.get("U"))
        if when is None or amount is None:
            result.warnings.append(f"Record {i}: skipped, missing date or amount.")
            continue
        payee = r.get("P", "")
        memo = r.get("M", "")
        result.transactions.append(ParsedTxn(
            date=when, amount=amount, description=(payee or memo).strip(), payee=payee, memo=memo,
            bank_category=r.get("L") or None, external_id=None, row=i,
        ))
    return result
