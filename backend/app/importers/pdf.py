"""Best-effort PDF statement parser.

PDFs are presentation documents, not bank-export files, so there is no stable schema to map.
This parser handles selectable-text statements in the common Canadian styles:

- chequing / savings statements with Withdrawals / Deposits / Balance columns (English or French),
  where the running balance sets and confirms each row's sign;
- credit card statements with one amount column, CR or minus for credits, transaction and posting
  dates, foreign-currency detail lines, and a summary box to cross-check against.

The column and wording rules live in pdf_layouts.py. They follow publicly known layouts and have
not been confirmed against real statements from every bank, so every result says it is best-effort
and any check that fails is reported rather than papered over.
"""
from __future__ import annotations

import io
import logging
import re
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal

from pypdf import PdfReader

from .common import ParsedTxn, ParseResult
from .pdf_layouts import (
    BANK_TOTALS, CARD_CUES, CARD_TOTALS, DateTok, Reading, collapse, date_prefix, detect_header, find_dates, fold,
    is_ledger_header, lab, looks_french, norm_line, read_card, read_ledger, read_totals,
)

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")
USE_EXPORT = "QFX/OFX or CSV exports from your bank are safer when they are available."
NO_TEXT = ("No selectable text was found. Scanned/image-only PDF statements need OCR and cannot be imported yet. "
           "Download a CSV or QFX/OFX file from your bank instead.")
NOT_UNDERSTOOD = ("FinVault could not make sense of this PDF's layout (PDF import is best-effort). "
                  "Download a CSV or QFX/OFX export from your bank's website and import that instead.")
NOTHING_FOUND = ("No transactions were found in this PDF; its layout was not recognised (PDF import is best-effort). "
                 "Try a QFX/OFX or CSV export from your bank instead, or a text-based statement PDF.")
_PERIOD_LABEL = re.compile(lab("statement period", "period covered", "for the period", "statement from",
                               "periode du releve", "periode de releve", "periode visee", "periode")
                           + r"|\bfrom\b|\bdu\b")
_PERIOD_SEP = re.compile(r"\s*(?:-|to|au|a|through|thru|until|jusqu'au)\s*")


class _PdfProblem(Exception):
    pass


def looks_like_pdf(raw: bytes) -> bool:
    return raw.lstrip().startswith(b"%PDF")


def _extract_texts(raw: bytes) -> tuple[str, str]:
    """(layout text, plain text). Layout mode keeps columns in place; plain mode keeps words intact."""
    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001
                raise _PdfProblem("This PDF is encrypted. Save an unlocked copy and import that.") from exc
        layout, plain = [], []
        for page in reader.pages:
            try:
                plain.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001
                plain.append("")
            try:
                layout.append(page.extract_text(extraction_mode="layout") or "")
            except Exception:  # noqa: BLE001
                layout.append("")
        return "\n".join(layout), "\n".join(plain)
    except _PdfProblem:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _PdfProblem("Could not read this PDF statement. " + USE_EXPORT) from exc


# ---------------------------------------------------------------------------- dates


def _ymd(tok: DateTok, day_first: bool) -> tuple[int | None, int, int]:
    if tok.numeric:
        month, day = (tok.b, tok.a) if day_first else (tok.a, tok.b)
        return tok.year, month, day
    return tok.year, tok.month, tok.day


def _make_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _statement_period(flat_f: str, day_first: bool) -> tuple[date, date] | None:
    """The statement's own date range, used to give year-less dates the right year."""
    dates = find_dates(flat_f)
    candidates = []
    for i in range(len(dates) - 1):
        a, b = dates[i], dates[i + 1]
        if not _PERIOD_SEP.fullmatch(flat_f[a.end:b.start]):
            continue
        (ya, ma, da), (yb, mb, db) = _ymd(a, day_first), _ymd(b, day_first)
        if ya is None and yb is None:
            continue
        if yb is None:
            yb = ya if (mb, db) >= (ma, da) else ya + 1
        if ya is None:
            ya = yb if (ma, da) <= (mb, db) else yb - 1
        start, end = _make_date(ya, ma, da), _make_date(yb, mb, db)
        if start and end and 0 <= (end - start).days <= 70:
            labelled = bool(_PERIOD_LABEL.search(flat_f[max(0, a.start - 40):a.start]))
            candidates.append((not labelled, i, (start, end)))
    return min(candidates)[2] if candidates else None


def _fit_to_period(d: date, period: tuple[date, date] | None) -> date:
    """Move a year-less date into the statement period (Dec 28 on a Dec-Jan statement stays in December)."""
    if not period:
        return d
    start, end = period
    for year in sorted({start.year, end.year}):
        try:
            candidate = d.replace(year=year)
        except ValueError:
            continue
        if (start - timedelta(days=10)) <= candidate <= (end + timedelta(days=10)):
            return candidate
    return d


def _statement_year(text: str) -> int:
    years = Counter(int(y) for y in re.findall(r"\b(20\d{2}|19\d{2})\b", text))
    if years:
        return years.most_common(1)[0][0]
    return date.today().year


def _day_first(tokens: list[DateTok], date_format: str | None, french: bool) -> tuple[bool, bool]:
    """(day_first, ambiguous) for numeric dates like 03/04/2026, decided once per statement."""
    numeric = [t for t in tokens if t.numeric]
    if date_format and date_format.startswith("%d"):
        return True, False
    if date_format and date_format.startswith("%m"):
        return False, False
    if any(t.a > 12 for t in numeric):
        return True, False
    if any(t.b > 12 for t in numeric):
        return False, False
    return french, bool(numeric)


# ---------------------------------------------------------------------------- choosing a reading


def _nospace(text: str) -> str:
    return re.sub(r"\W+", "", fold(text))


def _read(text: str, mode: str, debt: bool) -> Reading:
    lines = text.splitlines()
    return read_ledger(lines, debt) if mode == "ledger" else read_card(lines)


def _score(reading: Reading) -> tuple[int, int]:
    return (-len(reading.problems), len(reading.transactions))


def _best_reading(texts: list[str], mode: str, debt: bool) -> Reading:
    readings = [_read(t, mode, debt) for t in texts]
    primary = readings[0]
    for other in readings[1:]:
        if not primary.transactions or (other.transactions and _score(other) > _score(primary)):
            primary, other = other, primary
        # Plain extraction keeps words intact where layout mode sometimes drops spaces; borrow its wording.
        a, b = primary.transactions, other.transactions
        if len(a) == len(b) and all(x.amount == y.amount for x, y in zip(a, b)):
            for x, y in zip(a, b):
                if _nospace(x.desc) == _nospace(y.desc) and len(y.desc) > len(x.desc):
                    x.desc = y.desc
    return primary


# ---------------------------------------------------------------------------- checks


def _money(value: Decimal) -> str:
    return f"{value:,.2f}"


def _ledger_checks(result: ParseResult, reading: Reading, flat_f: str, debt: bool) -> bool:
    """Warnings for the running balance and the opening/closing balances. True when everything reconciles."""
    rows = [r for r in reading.transactions if r.sign]
    for row, want, got in reading.problems[:3]:
        when = row.date.text if row.date else "?"
        result.warnings.append(
            f"Running balance check failed near {when} \"{row.desc[:40]}\": the balance moved by {want:+,.2f} "
            f"but the rows read add up to {got:+,.2f}. Rows may be missing, misread or have the wrong sign; check them.")
    if len(reading.problems) > 3:
        result.warnings.append(f"The running balance did not reconcile in {len(reading.problems) - 3} more places.")
    has_balances = any(r.balance is not None for r in reading.rows) or reading.opening is not None
    if reading.unverified:
        if has_balances:
            result.warnings.append(
                f"{reading.unverified} of {len(rows)} rows could not be checked against the running balance, so their "
                "sign (money in or out) was taken from the column or the wording. Check them in the preview.")
        else:
            result.warnings.append(
                "This PDF shows no running balance, so each row's sign (money in or out) was taken from the column "
                "or the wording and could not be verified. Check the preview.")
    reconciled = not reading.problems and not reading.unverified and bool(rows)
    total = sum((r.signed for r in rows), Decimal(0))
    if reading.opening is not None and reading.closing is not None and rows:
        expected = reading.closing - reading.opening
        if debt:
            expected = -expected
        if abs(total - expected) > CENT:
            reconciled = False
            result.warnings.append(
                f"The statement's opening balance ({_money(reading.opening)}) and closing balance "
                f"({_money(reading.closing)}) differ by {expected:+,.2f}, but the rows found add up to {total:+,.2f}. "
                "Some rows may be missing or extra; check the preview.")
    else:
        reconciled = reconciled and has_balances
    totals = read_totals(flat_f, BANK_TOTALS)
    for key, label, got in (("deposits", "total deposits", sum((r.signed for r in rows if r.sign > 0), Decimal(0))),
                            ("withdrawals", "total withdrawals", sum((-r.signed for r in rows if r.sign < 0), Decimal(0)))):
        if key in totals and abs(abs(totals[key]) - got) > CENT:
            reconciled = False
            result.warnings.append(f"The statement lists {label} of {_money(abs(totals[key]))}, but the rows found "
                                   f"add up to {_money(got)}. Some rows may be missing or extra; check the preview.")
    if reading.closing is not None:
        result.statement_balance = -reading.closing if debt else reading.closing
    return reconciled


def _card_checks(result: ParseResult, reading: Reading, flat_f: str) -> bool:
    """Cross-check card rows against the statement's own summary box. True when every check that could run passed."""
    rows = reading.transactions
    t = read_totals(flat_f, CARD_TOTALS)
    charges = sum((r.amount for r in rows if r.sign < 0), Decimal(0))
    credits = sum((r.amount for r in rows if r.sign > 0), Decimal(0))
    fee_rows = sum((r.amount for r in rows if r.fee), Decimal(0))
    extras = sum((abs(t[k]) for k in ("interest", "fees", "cash") if k in t), Decimal(0))
    checked, ok = False, True
    if "purchases" in t:
        checked = True
        expected = abs(t["purchases"])
        # Some issuers fold interest and fees into "purchases & debits", some list them separately.
        if not any(abs(got - expected) <= CENT for got in (charges, charges - fee_rows, charges - extras)):
            ok = False
            result.warnings.append(f"The statement lists purchases & debits of {expected:.2f}, but the rows found add up "
                                   f"to {charges:.2f}. Some rows may be missing or extra; check the preview.")
    if "credits" in t:
        checked = True
        expected = abs(t["credits"])
        if abs(credits - expected) > CENT:
            ok = False
            result.warnings.append(f"The statement lists payments & credits of {expected:.2f}, but the rows found add up "
                                   f"to {credits:.2f}. Some rows may be missing, extra or have the wrong sign; check the preview.")
    if "previous" in t and "new" in t:
        checked = True
        change = t["new"] - t["previous"]
        got = charges - credits
        if abs(got - change) > CENT:
            ok = False
            result.warnings.append(
                f"The statement goes from a previous balance of {_money(t['previous'])} to a new balance of "
                f"{_money(t['new'])} ({change:+,.2f}), but the rows found change it by {got:+,.2f}. "
                "Some rows may be missing, extra or have the wrong sign; check the preview.")
        if "purchases" in t and "credits" in t:
            base = t["previous"] - abs(t["credits"]) + abs(t["purchases"])
            if not any(abs(base + x - t["new"]) <= CENT for x in (Decimal(0), extras)):
                ok = False
                result.warnings.append("The statement's own summary figures (previous balance, payments, purchases, "
                                       "interest, fees, new balance) don't add up as read, so the PDF text may have "
                                       "been misread. Check the preview.")
        result.statement_balance = -t["new"]  # what you owe, in FinVault's sign convention
    return checked and ok


# ---------------------------------------------------------------------------- entry point


def parse_pdf(raw: bytes, *, date_format: str | None = None, invert: bool | None = None,
              account_type: str | None = None) -> ParseResult:
    """Never raises: problems come back as warnings, with a pointer to CSV/QFX when the layout isn't understood."""
    result = ParseResult(format="pdf")
    try:
        layout_text, plain_text = _extract_texts(raw)
    except _PdfProblem as exc:
        result.warnings.append(str(exc))
        return result
    texts = [t for t in (layout_text, plain_text) if t.strip()]
    if not texts:
        result.warnings.append(NO_TEXT)
        return result
    result.text_sample = (plain_text or layout_text)[:4000]
    try:
        _parse(result, texts, date_format=date_format, invert=invert, account_type=account_type)
    except Exception:  # noqa: BLE001 - an odd PDF must not break the import page
        logger.exception("PDF statement parsing failed")
        result.transactions, result.sample_rows = [], []
        result.warnings = [NOT_UNDERSTOOD]
    return result


def _parse(result: ParseResult, texts: list[str], *, date_format, invert, account_type) -> None:
    lines = [norm_line(line) for line in texts[0].splitlines()]
    folded = [fold(line) for line in lines]
    flat_f = collapse(" ".join(folded))
    # Summary figures come from lines that are not transaction rows.
    summary_f = collapse(" ".join(f for f in folded if not date_prefix(f, find_dates(f))))
    ledger_header = any(is_ledger_header(detect_header(f)) for f in folded)
    card_like = account_type == "credit_card" or bool(CARD_CUES.search(flat_f))
    mode = "ledger" if ledger_header or not card_like else "card"
    debt = mode == "ledger" and account_type in ("credit_card", "loan")
    reading = _best_reading(texts, mode, debt)

    french = looks_french(flat_f)
    rows = reading.transactions
    day_first, ambiguous = _day_first([r.date for r in rows if r.date], date_format, french)
    period = _statement_period(flat_f, day_first)
    year = period[1].year if period else _statement_year("\n".join(texts))

    parsed: list[ParsedTxn] = []
    skipped = 0
    for r in rows:
        when = None
        if r.date is not None:
            y, m, d = _ymd(r.date, day_first)
            when = _make_date(y or year, m, d)
            if when is not None and y is None:
                when = _fit_to_period(when, period)
        if when is None or not r.sign:
            skipped += 1
            continue
        parsed.append(ParsedTxn(date=when, amount=r.signed, description=r.desc[:500], memo=r.memo[:500], row=r.line_no))

    if mode == "ledger":
        checked = _ledger_checks(result, reading, summary_f, debt)
    else:
        checked = _card_checks(result, reading, summary_f)

    if invert:
        for txn in parsed:
            txn.amount = -txn.amount
    result.inverted = bool(invert)
    numeric = [r.date for r in rows if r.date and r.date.numeric]
    if numeric and any(t.year for t in numeric):
        result.date_format = "%d/%m/%Y" if day_first else "%m/%d/%Y"
    elif any(r.date and r.date.year and not r.date.numeric and r.date.text[:4].isdigit() for r in rows):
        result.date_format = "%Y-%m-%d"
    else:
        result.date_format = date_format
    result.date_format_ambiguous = ambiguous
    result.transactions = parsed
    result.sample_rows = [[r.date.text if r.date else "", r.desc, r.amount_text] for r in rows[:8]]
    result.columns = ["Date", "Description", "Amount"]
    result.mapping = {"date": 0, "description": 1, "amount": 2}

    if ambiguous:
        order = "day/month/year" if day_first else "month/day/year"
        result.warnings.insert(0, f"Some PDF dates could be month-first or day-first. Assumed {order}; "
                                  "change the date format if that is wrong.")
    if skipped:
        result.warnings.append(f"Skipped {skipped} PDF rows that did not have a readable date or amount.")
    if not parsed:
        result.warnings.append(NOTHING_FOUND)
    elif checked and mode == "ledger":
        result.warnings.append("PDF import is best-effort, but every row's sign was confirmed by the running balance "
                               "and the rows match the statement's balances.")
    elif checked:
        result.warnings.append("PDF import is best-effort, but these rows match the statement's own totals.")
    else:
        result.warnings.append("PDF import is best-effort. Check the preview carefully; " + USE_EXPORT)
