"""Shared parsing helpers for statement files."""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


@dataclass
class ParsedTxn:
    date: date
    amount: Decimal
    description: str
    payee: str = ""
    memo: str = ""
    external_id: str | None = None
    currency: str | None = None
    bank_category: str | None = None
    row: int | None = None  # source row number, for error messages


@dataclass
class ParseResult:
    format: str  # ofx | qif | csv
    transactions: list[ParsedTxn] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    preset: str | None = None
    columns: list[str] = field(default_factory=list)
    mapping: dict = field(default_factory=dict)
    date_format: str | None = None
    date_format_ambiguous: bool = False
    inverted: bool = False
    currency: str | None = None
    account_number: str | None = None
    statement_balance: Decimal | None = None
    sample_rows: list[list[str]] = field(default_factory=list)


def decode_bytes(raw: bytes) -> str:
    enc = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"
    try:
        return raw.decode(enc)
    except UnicodeDecodeError:
        pass
    # Older Canadian bank exports are often Windows-1252 (accents in French descriptions).
    return raw.decode("cp1252", errors="replace")


def normalize_header(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = value.lower().replace("$", " ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


_CURRENCY_NOISE = re.compile(r"(?i)\b(cad|usd|eur|gbp|brl|ca|us)\b|[$€£¥]|r\$")


def parse_amount(value: str | None) -> Decimal | None:
    """Parse bank amounts: '$1,234.56', '(12.00)', '12.00-', '12.00 CR', '1 234,56', '-€5'."""
    if value is None:
        return None
    s = str(value).strip().replace(" ", " ").replace(" ", " ")
    if not s or s in {"-", "--"}:
        return None
    negative = False
    upper = s.upper()
    if upper.endswith(" DR") or upper.endswith("DR"):
        negative, s = True, s[:-2]
    elif upper.endswith(" CR") or upper.endswith("CR"):
        s = s[:-2]
    s = _CURRENCY_NOISE.sub("", s).strip()
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1]
    if s.endswith("-"):
        negative, s = True, s[:-1]
    if s.startswith("+"):
        s = s[1:]
    if s.startswith("-"):
        negative, s = (not negative), s[1:]
    s = s.replace(" ", "")
    if re.fullmatch(r"\d{1,3}(\.\d{3})*,\d{1,2}", s) or re.fullmatch(r"\d+,\d{1,2}", s):
        s = s.replace(".", "").replace(",", ".")  # European / French-Canadian decimal comma
    else:
        s = s.replace(",", "")
    if not re.fullmatch(r"\d*\.?\d+", s):
        return None
    try:
        amount = Decimal(s)
    except InvalidOperation:
        return None
    return -amount if negative else amount


DATE_FORMATS = [
    "%Y-%m-%d", "%Y/%m/%d", "%Y%m%d",
    "%m/%d/%Y", "%d/%m/%Y", "%m/%d/%y", "%d/%m/%y",
    "%m-%d-%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%b %d, %Y", "%b %d %Y", "%d %b %Y", "%d-%b-%Y", "%d-%b-%y", "%B %d, %Y", "%d %B %Y",
]
# Pairs that read the same digits in a different order.
_AMBIGUOUS = {("%m/%d/%Y", "%d/%m/%Y"), ("%m/%d/%y", "%d/%m/%y"), ("%m-%d-%Y", "%d-%m-%Y")}


def _clean_date(value: str) -> str:
    v = value.strip().strip('"')
    v = re.sub(r"[T ]\d{1,2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$", "", v)  # drop times
    v = re.sub(r"\s+\d{1,2}:\d{2}(:\d{2})?\s*(AM|PM)?$", "", v, flags=re.I)
    v = v.replace("'", "/")  # QIF style 1/15'24
    return v.strip()


def try_parse_date(value: str, fmt: str) -> date | None:
    try:
        return datetime.strptime(_clean_date(value), fmt).date()
    except (ValueError, TypeError):
        return None


def looks_like_date(value: str) -> bool:
    return any(try_parse_date(value, f) for f in DATE_FORMATS)


def detect_date_format(values: list[str], preferred: str | None = None) -> tuple[str | None, bool]:
    """Return (format, ambiguous). Picks a format that parses every non-empty value.

    When a file only has days <= 12 both month-first and day-first work; most Canadian
    bank exports are month-first, so that wins, and we flag it so the UI can ask.
    """
    vals = [v for v in values if v and v.strip()]
    if not vals:
        return None, False
    fits = [f for f in DATE_FORMATS if all(try_parse_date(v, f) for v in vals)]
    if not fits:
        return None, False
    if preferred and preferred in fits:
        choice = preferred
    else:
        choice = fits[0]
    ambiguous = any((a in fits and b in fits) for a, b in _AMBIGUOUS) and not preferred
    return choice, ambiguous


def normalize_merchant(text: str) -> str:
    """Stable key for 'the same merchant': drops store numbers, card digits, locations noise."""
    t = text.upper()
    t = re.sub(r"\b(POS|PURCHASE|INTERAC|DEBIT|VISA|MC|APOS|OPOS|IDP|FPOS|RETAIL)\b", " ", t)
    t = re.sub(r"[#*]\s*\w*\d\w*", " ", t)
    t = re.sub(r"\d{3,}", " ", t)
    t = re.sub(r"[^A-Z& ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()
