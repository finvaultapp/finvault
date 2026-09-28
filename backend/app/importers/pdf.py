"""Best-effort PDF statement parser.

PDFs are presentation documents, not bank-export files, so there is no stable
schema to map. This parser handles selectable-text statements where each
transaction row has a date, a description, and one or more money values.
"""
from __future__ import annotations

import io
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from pypdf import PdfReader

from .common import ParsedTxn, ParseResult, detect_date_format, parse_amount, try_parse_date

MONTHS = r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
FULL_DATE_RE = re.compile(
    rf"\b(\d{{4}}[-/]\d{{1,2}}[-/]\d{{1,2}}|\d{{1,2}}[-/]\d{{1,2}}[-/]\d{{2,4}}|"
    rf"(?:{MONTHS})\.?\s+\d{{1,2}},?\s+\d{{4}}|\d{{1,2}}\s+(?:{MONTHS})\.?,?\s+\d{{4}})\b",
    re.I,
)
SHORT_DATE_RE = re.compile(
    rf"\b(\d{{1,2}}[-/]\d{{1,2}}|(?:{MONTHS})\.?\s+\d{{1,2}}|\d{{1,2}}\s+(?:{MONTHS})\.?)\b",
    re.I,
)
DATE_RE = re.compile(f"{FULL_DATE_RE.pattern}|{SHORT_DATE_RE.pattern}", re.I)
MONEY_RE = re.compile(
    r"(?<![\w/])(?:[-+]?[$€£]?\s?\(?\d{1,3}(?:[,\s]\d{3})*(?:[.,]\d{2})\)?|"
    r"[-+]?[$€£]?\s?\(?\d+[.,]\d{2}\)?)(?:\s?(?:CR|DR))?-?(?![\w/])",
    re.I,
)
NOISE_RE = re.compile(
    r"(?i)\b(date|description|withdrawals?|deposits?|credits?|debits?|balance|amount|transaction|posted|"
    r"statement|opening|closing|previous|new balance|minimum payment|page \d+)\b"
)
SUMMARY_LINE_RE = re.compile(
    r"(?i)\b(statement period|opening balance|closing balance|previous balance|new balance|minimum payment|"
    r"total payments?|total credits?|total debits?|interest charged|fees charged)\b"
)
POSITIVE_RE = re.compile(
    r"(?i)\b(payroll|salary|direct deposit|deposit|depot|refund|rebate|interest|dividend|e-transfer from|"
    r"transfer from|received|incoming|credit)\b"
)
NEGATIVE_RE = re.compile(
    r"(?i)\b(purchase|debit|withdrawal|withdraw|fee|charge|bill payment|payment to|e-transfer to|"
    r"transfer to|preauthorized debit|pos purchase)\b"
)


@dataclass
class _Candidate:
    date_text: str
    description: str
    amount_text: str
    signed_amount: bool
    line_no: int


def looks_like_pdf(raw: bytes) -> bool:
    return raw.lstrip().startswith(b"%PDF")


def _clean_line(line: str) -> str:
    line = line.replace("\u00a0", " ").replace("\u202f", " ")
    line = re.sub(r"\s+", " ", line)
    return line.strip()


def _extract_text(raw: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001
                raise ValueError("This PDF is encrypted. Save an unlocked copy and import that.") from exc
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Could not read this PDF statement.") from exc


def _statement_year(text: str) -> int:
    years = Counter(int(y) for y in re.findall(r"\b(20\d{2}|19\d{2})\b", text))
    if years:
        return years.most_common(1)[0][0]
    return date.today().year


def _has_year(value: str) -> bool:
    return bool(re.search(r"\b(20\d{2}|19\d{2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b", value))


def _has_explicit_sign(value: str) -> bool:
    return bool(re.search(r"[-()]|\b(?:CR|DR)\b", value, re.I))


def _parse_short_date(value: str, preferred: str | None, year: int) -> tuple[date | None, bool]:
    v = value.strip().replace(".", "")
    month_first = True
    ambiguous = False
    if re.match(r"^\d{1,2}[-/]\d{1,2}$", v):
        a, b = [int(x) for x in re.split(r"[-/]", v)]
        if preferred and preferred.startswith("%d"):
            month_first = False
        elif a > 12 and b <= 12:
            month_first = False
        elif a <= 12 and b <= 12 and not preferred:
            ambiguous = True
        month, day = (a, b) if month_first else (b, a)
        try:
            return date(year, month, day), ambiguous
        except ValueError:
            return None, ambiguous
    for fmt in ("%b %d %Y", "%B %d %Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(f"{v} {year}", fmt).date(), False
        except ValueError:
            continue
    return None, False


def _parse_date(value: str, full_fmt: str | None, preferred: str | None, year: int) -> tuple[date | None, bool]:
    if _has_year(value):
        fmt = full_fmt or detect_date_format([value], preferred)[0]
        return (try_parse_date(value, fmt) if fmt else None), False
    return _parse_short_date(value, preferred, year)


def _unsigned_amount(amount: Decimal, description: str, account_type: str | None) -> Decimal:
    desc = description.lower()
    if NEGATIVE_RE.search(desc):
        return -abs(amount)
    if POSITIVE_RE.search(desc) or (account_type == "credit_card" and "payment" in desc):
        return abs(amount)
    return -abs(amount)


def _candidate_from_line(line: str, line_no: int) -> _Candidate | None:
    if SUMMARY_LINE_RE.search(line):
        return None
    date_match = DATE_RE.search(line)
    if not date_match or date_match.start() > 24:
        return None
    money_matches = list(MONEY_RE.finditer(line))
    if not money_matches:
        return None
    money_match = next((m for m in money_matches if m.start() > date_match.end()), money_matches[0])
    if money_match.start() <= date_match.end():
        return None
    desc = line[date_match.end():money_match.start()].strip(" -:\u2013\u2014")
    second_date = DATE_RE.match(desc)
    if second_date:
        desc = desc[second_date.end():].strip(" -:\u2013\u2014")
    desc = re.sub(r"\s+", " ", desc)
    if not desc or NOISE_RE.fullmatch(desc):
        return None
    return _Candidate(
        date_text=date_match.group(0),
        description=desc[:500],
        amount_text=money_match.group(0),
        signed_amount=_has_explicit_sign(money_match.group(0)),
        line_no=line_no,
    )


def parse_pdf(raw: bytes, *, date_format: str | None = None, invert: bool | None = None,
              account_type: str | None = None) -> ParseResult:
    text = _extract_text(raw)
    result = ParseResult(format="pdf")
    lines = [_clean_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        result.warnings.append("No selectable text was found. Scanned/image-only PDF statements need OCR and cannot be imported yet.")
        return result

    candidates = [c for i, line in enumerate(lines, start=1) if (c := _candidate_from_line(line, i))]
    full_dates = [c.date_text for c in candidates if _has_year(c.date_text)]
    full_fmt, ambiguous = detect_date_format(full_dates, date_format) if full_dates else (None, False)
    year = _statement_year(text)
    parsed: list[ParsedTxn] = []
    short_ambiguous = False
    skipped = 0

    for c in candidates:
        when, amb = _parse_date(c.date_text, full_fmt, date_format, year)
        short_ambiguous = short_ambiguous or amb
        amount = parse_amount(c.amount_text)
        if when is None or amount is None:
            skipped += 1
            continue
        if not c.signed_amount:
            amount = _unsigned_amount(amount, c.description, account_type)
        parsed.append(ParsedTxn(date=when, amount=amount, description=c.description, row=c.line_no))

    if invert:
        for txn in parsed:
            txn.amount = -txn.amount
    result.inverted = bool(invert)
    result.date_format = full_fmt or date_format
    result.date_format_ambiguous = ambiguous or short_ambiguous
    result.transactions = parsed
    result.sample_rows = [[c.date_text, c.description, c.amount_text] for c in candidates[:8]]
    result.columns = ["Date", "Description", "Amount"]
    result.mapping = {"date": 0, "description": 1, "amount": 2}

    if ambiguous or short_ambiguous:
        result.warnings.append("Some PDF dates could be month-first or day-first. Assumed month/day/year; change the date format if that is wrong.")
    if skipped:
        result.warnings.append(f"Skipped {skipped} PDF rows that did not have a readable date or amount.")
    if not parsed:
        result.warnings.append("No transactions were found in this PDF. Try a QFX/OFX or CSV export, or use a text-based statement PDF.")
    else:
        result.warnings.append("PDF import is best-effort. Check the preview carefully; QFX/OFX or CSV is safer when your bank offers it.")
    return result
