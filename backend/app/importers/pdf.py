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
from datetime import date, datetime, timedelta
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
    r"total payments?|total credits?|total debits?|interest charged|fees charged|payment due|"
    r"payments? (?:&|and) credits|new purchases|credit limit|available credit|amount due|cash advances|"
    r"promotional balances?|annual interest rate)\b"
)
# Words that mark a credit card statement, where the sign convention is the card's, not the bank account's.
CARD_CUES_RE = re.compile(r"(?i)\b(credit limit|available credit|minimum payment|mastercard|visa|american express|amex)\b")
# On a card, these lines reduce what you owe.
CARD_CREDIT_RE = re.compile(r"(?i)\b(payment|paiement|thank[- ]?you|merci|refund|remboursement|return|credit adjustment|rebate|cash ?back)\b")
PERIOD_RE = re.compile(
    rf"(?i)statement\s+period\s*:?\s*((?:{MONTHS})\.?\s+\d{{1,2}},?\s*\d{{4}})\s*[-–to]+\s*((?:{MONTHS})\.?\s+\d{{1,2}},?\s*\d{{4}})"
)
TOTAL_PATTERNS = {
    "purchases": re.compile(r"(?i)new\s+purchases\s*(?:&|and)\s*debits\s*\$?\s*([\d,]+\.\d{2})"),
    "credits": re.compile(r"(?i)payments?\s*(?:&|and)\s*credits\s*\$?\s*([\d,]+\.\d{2})"),
}
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


def _extract_texts(raw: bytes) -> list[str]:
    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001
                raise ValueError("This PDF is encrypted. Save an unlocked copy and import that.") from exc
        plain_pages, layout_pages = [], []
        for page in reader.pages:
            plain_pages.append(page.extract_text() or "")
            try:
                layout_pages.append(page.extract_text(extraction_mode="layout") or "")
            except Exception:  # noqa: BLE001
                layout_pages.append("")
        variants = ["\n".join(plain_pages), "\n".join(layout_pages)]
        out: list[str] = []
        seen: set[str] = set()
        for text in variants:
            key = re.sub(r"\s+", " ", text).strip()
            if key and key not in seen:
                seen.add(key)
                out.append(text)
        return out
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Could not read this PDF statement.") from exc


def _statement_period(text: str) -> tuple[date, date] | None:
    """The statement's own date range, used to give year-less dates the right year."""
    flat = re.sub(r"\s+", " ", text)
    m = PERIOD_RE.search(flat)
    if not m:
        return None
    out = []
    for part in m.groups():
        part = re.sub(r"\s*,\s*", ", ", part.replace(".", "")).strip()
        for fmt in ("%b %d, %Y", "%B %d, %Y"):
            try:
                out.append(datetime.strptime(part, fmt).date())
                break
            except ValueError:
                continue
    return (out[0], out[1]) if len(out) == 2 and out[0] <= out[1] else None


def _fit_to_period(d: date, period: tuple[date, date] | None) -> date:
    """Move a year-less date into the statement period (Dec 28 on a Dec-Jan statement stays in December)."""
    if not period:
        return d
    start, end = period
    for year in {start.year, end.year}:
        try:
            candidate = d.replace(year=year)
        except ValueError:
            continue
        if (start - timedelta(days=10)) <= candidate <= (end + timedelta(days=10)):
            return candidate
    return d


def _statement_totals(text: str) -> dict[str, Decimal]:
    flat = re.sub(r"\s+", " ", text)
    found = {}
    for key, pat in TOTAL_PATTERNS.items():
        m = pat.search(flat)
        if m:
            found[key] = Decimal(m.group(1).replace(",", ""))
    return found


def _card_amount(amount_text: str, description: str) -> Decimal | None:
    """Card statements print purchases as positive and payments as negative or 'CR'. FinVault is the other way round."""
    value = parse_amount(amount_text)
    if value is None:
        return None
    text = amount_text.upper()
    if "CR" in text or "-" in text or "(" in text:
        return abs(value)  # a credit to you: payment, refund
    if "DR" in text:
        return -abs(value)
    return abs(value) if CARD_CREDIT_RE.search(description) else -abs(value)


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


def _candidate_key(c: _Candidate) -> tuple[str, str, str]:
    date_key = re.sub(r"\W+", " ", c.date_text).lower().strip()
    # Layout extraction sometimes drops the spaces between words, so compare without them.
    desc_key = re.sub(r"\W+", "", c.description).lower()
    amount_key = re.sub(r"\s+", "", c.amount_text).lower()
    return date_key, desc_key, amount_key


def _candidates_from_text(text: str) -> tuple[list[_Candidate], list[str]]:
    lines = [_clean_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    candidates = [c for i, line in enumerate(lines, start=1) if (c := _candidate_from_line(line, i))]
    return candidates, lines


def parse_pdf(raw: bytes, *, date_format: str | None = None, invert: bool | None = None,
              account_type: str | None = None) -> ParseResult:
    texts = _extract_texts(raw)
    result = ParseResult(format="pdf")
    all_lines: list[str] = []
    candidates: list[_Candidate] = []
    seen_candidates: set[tuple[str, str, str]] = set()
    for text in texts:
        text_candidates, text_lines = _candidates_from_text(text)
        all_lines.extend(text_lines)
        for c in text_candidates:
            key = _candidate_key(c)
            if key not in seen_candidates:
                seen_candidates.add(key)
                candidates.append(c)
    if not all_lines:
        result.warnings.append("No selectable text was found. Scanned/image-only PDF statements need OCR and cannot be imported yet.")
        return result

    joined = "\n".join(texts)
    full_dates = [c.date_text for c in candidates if _has_year(c.date_text)]
    full_fmt, ambiguous = detect_date_format(full_dates, date_format) if full_dates else (None, False)
    period = _statement_period(joined)
    year = period[1].year if period else _statement_year(joined)
    is_card = account_type == "credit_card" or bool(CARD_CUES_RE.search(joined))
    parsed: list[ParsedTxn] = []
    short_ambiguous = False
    skipped = 0

    for c in candidates:
        when, amb = _parse_date(c.date_text, full_fmt, date_format, year)
        short_ambiguous = short_ambiguous or amb
        if when is not None and not _has_year(c.date_text):
            when = _fit_to_period(when, period)
        if is_card:
            amount = _card_amount(c.amount_text, c.description)
        else:
            amount = parse_amount(c.amount_text)
            if amount is not None and not c.signed_amount:
                amount = _unsigned_amount(amount, c.description, account_type)
        if when is None or amount is None:
            skipped += 1
            continue
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
    # Cross-check against the statement's own summary so a missed or extra row is visible.
    totals = _statement_totals(joined) if is_card else {}
    totals_match = False
    if parsed and totals:
        spent = sum((-t.amount for t in parsed if t.amount < 0), Decimal(0))
        paid = sum((t.amount for t in parsed if t.amount > 0), Decimal(0))
        if invert:
            spent, paid = paid, spent
        checks = [("purchases", spent, "purchases & debits"), ("credits", paid, "payments & credits")]
        mismatched = [(label, got, totals[key]) for key, got, label in checks if key in totals and abs(got - totals[key]) > Decimal("0.01")]
        for label, got, expected in mismatched:
            result.warnings.append(f"The statement lists {label} of {expected:.2f}, but the rows found add up to {got:.2f}. "
                                   "Some rows may be missing or extra; check the preview.")
        if not mismatched:
            totals_match = True
    if not parsed:
        result.warnings.append("No transactions were found in this PDF. Try a QFX/OFX or CSV export, or use a text-based statement PDF.")
    elif totals_match:
        result.warnings.append("PDF import is best-effort, but these rows match the statement's own totals.")
    else:
        result.warnings.append("PDF import is best-effort. Check the preview carefully; QFX/OFX or CSV is safer when your bank offers it.")
    return result
