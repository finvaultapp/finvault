"""Layout-aware building blocks for the PDF statement parser.

Everything here works on one line of extracted text at a time. pypdf's layout mode keeps
columns roughly where they are on the page, so character positions stand in for x positions:
a header line tells us where the Withdrawals / Deposits / Balance (or Amount) columns are,
and each money value on a row is assigned to the nearest column.

Two row readers are provided:
- read_ledger: chequing / savings statements with a running balance. The balance, not the
  wording, decides each row's sign whenever it can, and every group of rows between two printed
  balances is checked.
- read_card: credit card statements (one amount column, CR / minus for credits).

English and French (Canadian) wording is recognised. None of this has been confirmed against
real statements from each bank; it follows the commonly published layouts.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal
from itertools import product

from .common import parse_amount

# ---------------------------------------------------------------------------- text helpers

_SPECIAL = {"–": "-", "—": "-", "−": "-", "‘": "'", "’": "'", " ": " ",
            " ": " ", " ": " ", " ": " ", "\t": " ", "\r": " "}


def norm_line(line: str) -> str:
    """Same-length copy with odd spaces and dashes made plain (keeps case and accents)."""
    return "".join(_SPECIAL.get(ch, ch) for ch in line)


def fold(text: str) -> str:
    """Lower-case, accent-free copy of text with the same length, so positions line up with the original."""
    out = []
    for ch in text:
        if ch in _SPECIAL:
            out.append(_SPECIAL[ch])
        elif ord(ch) < 128:
            out.append(ch)
        else:
            base = unicodedata.normalize("NFKD", ch)[:1]
            out.append(base if base and ord(base) < 128 else "?")
    return "".join(out).lower()


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" -:*–—|")


def lab(*phrases: str) -> str:
    """Regex alternation for label phrases; layout text may add or drop spaces between words."""
    return "|".join(p.replace(" ", r"\s*") for p in phrases)


# ---------------------------------------------------------------------------- dates

MONTHS = {
    "january": 1, "janvier": 1, "janv": 1, "jan": 1,
    "february": 2, "fevrier": 2, "fevr": 2, "fev": 2, "feb": 2,
    "march": 3, "mars": 3, "mar": 3,
    "april": 4, "avril": 4, "avr": 4, "apr": 4,
    "may": 5, "mai": 5,
    "june": 6, "juin": 6, "jun": 6,
    "july": 7, "juillet": 7, "juil": 7, "jul": 7,
    "august": 8, "aout": 8, "aou": 8, "aug": 8,
    "september": 9, "septembre": 9, "sept": 9, "sep": 9,
    "october": 10, "octobre": 10, "oct": 10,
    "november": 11, "novembre": 11, "nov": 11,
    "december": 12, "decembre": 12, "dec": 12,
}
_MON = "|".join(sorted(MONTHS, key=len, reverse=True))
_YEAR = r"(?:19|20)\d{2}"
_DATE_PATTERNS = [
    ("iso", re.compile(rf"(?<![\d.,/-])({_YEAR})[-/.](\d{{1,2}})[-/.](\d{{1,2}})(?!\d)")),
    ("numy", re.compile(rf"(?<![\d.,/-])(\d{{1,2}})[-/.](\d{{1,2}})[-/.]({_YEAR}|\d{{2}})(?!\d)")),
    ("mdy", re.compile(rf"(?<![a-z0-9])({_MON})\.?\s{{0,3}}(\d{{1,2}})(?:er)?(?!\d)(?:,?\s{{1,4}}({_YEAR})(?!\d))?(?![a-z])")),
    ("dmy", re.compile(rf"(?<![a-z0-9.,])(\d{{1,2}})(?:er)?\s{{0,3}}-?({_MON})\.?(?:[,-]?\s{{0,4}}({_YEAR})(?!\d))?(?![a-z])")),
    ("num", re.compile(r"(?<![\d.,/-])(\d{1,2})[/-](\d{1,2})(?![\d/.,-]?\d)")),
]


@dataclass
class DateTok:
    start: int
    end: int
    text: str
    year: int | None = None
    month: int | None = None
    day: int | None = None
    a: int | None = None  # numeric dates: first and second number, order decided per statement
    b: int | None = None

    @property
    def numeric(self) -> bool:
        return self.a is not None


def _date_tok(kind: str, m: re.Match, original: str) -> DateTok | None:
    g = m.groups()
    tok = DateTok(m.start(), m.end(), original[m.start():m.end()].strip())
    if kind == "iso":
        tok.year, tok.month, tok.day = int(g[0]), int(g[1]), int(g[2])
    elif kind in ("numy", "num"):
        tok.a, tok.b = int(g[0]), int(g[1])
        if kind == "numy":
            tok.year = int(g[2]) + (2000 if len(g[2]) == 2 else 0)
        if not (1 <= tok.a <= 31 and 1 <= tok.b <= 31 and min(tok.a, tok.b) <= 12):
            return None
        return tok
    elif kind == "mdy":
        tok.month, tok.day = MONTHS[g[0]], int(g[1])
        tok.year = int(g[2]) if g[2] else None
    else:
        tok.day, tok.month = int(g[0]), MONTHS[g[1]]
        tok.year = int(g[2]) if g[2] else None
    if not (1 <= (tok.month or 0) <= 12 and 1 <= (tok.day or 0) <= 31):
        return None
    return tok


def find_dates(f: str, original: str | None = None) -> list[DateTok]:
    original = original if original is not None else f
    found = []
    for kind, pat in _DATE_PATTERNS:
        for m in pat.finditer(f):
            tok = _date_tok(kind, m, original)
            if tok:
                found.append(tok)
    found.sort(key=lambda t: (t.start, -(t.end - t.start)))
    out, last_end = [], -1
    for t in found:
        if t.start >= last_end:
            out.append(t)
            last_end = t.end
    return out


@dataclass
class Prefix:
    first: DateTok
    second: DateTok | None
    end: int


_REF = re.compile(r"(?:\d{3,}|\d{1,2}(?=\s{2,}))\s+")


def date_prefix(f: str, dates: list[DateTok]) -> Prefix | None:
    """The date (or transaction + posting date pair) a row starts with, if any."""
    i = len(f) - len(f.lstrip())
    starts = {t.start: t for t in dates}
    first = starts.get(i)
    if first is None:
        m = _REF.match(f, i)  # a reference-number column before the date (Scotia style)
        if m and m.end() in starts:
            first = starts[m.end()]
    if first is None:
        return None
    second, end = None, first.end
    j = end + len(f[end:]) - len(f[end:].lstrip())
    if j in starts and j - end <= 12:
        second = starts[j]
        end = second.end
    return Prefix(first, second, end)


# ---------------------------------------------------------------------------- money

_NUM = r"(?:\d{1,3}(?:,\d{3})+\.\d{2}|\d{1,3}(?:\.\d{3})+,\d{2}|\d{1,3}(?: \d{3})+,\d{2}|\d+[.,]\d{2})"
_MONEY_RE = re.compile(
    rf"(?<![\w.,/$@-])(?:\(\s?)?[-+]?\s?\$?\s?[-+]?{_NUM}(?!\d)(?![.,]\d)(?:\s?\$)?(?:\s?\))?"
    rf"(?:\s{{0,2}}(?:cr|dr|od)\b|-(?!\w))?(?!\s?%)"
)
_CCY = r"(?:usd|us\$|eur|gbp|jpy|chf|aud|nzd|mxn|inr|cny|hkd|sgd|sek|nok|dkk|brl|krw|thb|php|zar|ils|aed)"
_FX_BEFORE = re.compile(rf"(?:{_CCY}\s*\$?\s*|(?:@|rate|taux|exchange)\s*:?\s*)$")
_FX_AFTER = re.compile(rf"\s*(?:{_CCY}(?![a-z])|@|united\s*states|u\.?s\.?\s*dollar|dollars?\s*(?:us|americains?)|euros?\b)")
FX_CUE = re.compile(rf"(?<![a-z]){_CCY}(?![a-z])|@\s*\d|exchange\s*rate|taux\s*de\s*change|foreign\s*currency|devise")


@dataclass
class Money:
    start: int
    end: int
    text: str
    value: Decimal
    credit: bool = False  # printed with CR
    debit: bool = False  # printed with DR
    foreign: bool = False  # a foreign-currency amount or exchange rate, not the CAD amount

    @property
    def negative(self) -> bool:
        return self.value < 0


def _mask_dates(f: str, dates: list[DateTok]) -> str:
    chars = list(f)
    for t in dates:
        chars[t.start:t.end] = " " * (t.end - t.start)
    return "".join(chars)


def money_tokens(f: str, dates: list[DateTok] | None = None, start: int = 0) -> list[Money]:
    masked = _mask_dates(f, dates if dates is not None else find_dates(f))
    out = []
    for m in _MONEY_RE.finditer(masked, start):
        text = m.group(0).strip()
        tail = re.search(r"\s*(cr|dr|od)$", text)
        suffix = tail.group(1) if tail else ""
        value = parse_amount(text[:tail.start()] if suffix == "od" else text)
        if value is None:
            continue
        if suffix == "od":  # overdrawn balance
            value = -abs(value)
        tok_start = m.start() + (len(m.group(0)) - len(m.group(0).lstrip()))
        before = masked[max(0, tok_start - 10):tok_start]
        after = masked[m.end():m.end() + 16]
        fx_before = _FX_BEFORE.search(before)
        foreign = bool(fx_before or _FX_AFTER.match(after))
        if fx_before and re.search(_CCY, fx_before.group(0)):
            tok_start -= len(fx_before.group(0))
        out.append(Money(tok_start, m.end(), text, value, suffix == "cr", suffix == "dr", foreign))
    return out


# ---------------------------------------------------------------------------- column headers

_HEADER_LABELS = [
    ("date", re.compile(r"\b(?:(?:trans(?:action)?|post(?:ing|ed)?|effective|value)\.?\s*)?date\b"
                        r"(?:\s+(?:de\s+|d')?(?:la\s+|l')?(?:transaction|operation|inscription|l'operation))?"
                        r"|\b(?:trans|post)\b\.?")),
    ("withdraw", re.compile(r"\b(?:cheques?\s*(?:&|and|/)\s*debits?|withdrawals?(?:\s*(?:&|and)\s*debits?)?|withdrawn|"
                            r"debits?|retraits?|paid\s*out|money\s*out|funds\s*out|sorties?)\b")),
    ("deposit", re.compile(r"\b(?:deposits?(?:\s*(?:&|and|/)\s*credits?)?|credits?|depots?|paid\s*in|money\s*in|"
                           r"funds\s*in|entrees?)\b")),
    ("balance", re.compile(r"\b(?:balance|solde)\b")),
    ("amount", re.compile(r"\b(?:amount|montant)\b")),
    ("description", re.compile(r"\b(?:description|transaction\s*details|details|particulars|libelle|"
                               r"transactions?|operations?|activity)\b")),
]
_NOT_HEADER = re.compile(r"previous|new\s*balance|opening|closing|minimum|total|purchases|achats|paiements|"
                         r"payments?\b|precedent|nouveau|ouverture|fermeture|cloture|limit|available|disponible|"
                         r"\bdue\b|echeance|interest\s*rate|taux|forward")
MONEY_ROLES = ("withdraw", "deposit", "amount", "balance")


def detect_header(f: str) -> dict[str, tuple[int, int]] | None:
    """Column positions if this line is a table header (Date / Description / Withdrawals / ...)."""
    if _NOT_HEADER.search(f) or find_dates(f) or money_tokens(f, []):
        return None
    masked, cols = f, {}
    for role, pat in _HEADER_LABELS:
        for m in pat.finditer(masked):
            cols.setdefault(role, (m.start(), m.end()))
            masked = masked[:m.start()] + " " * (m.end() - m.start()) + masked[m.end():]
    letters = sum(c.isalpha() for c in f)
    left = sum(c.isalpha() for c in masked)
    if len(cols) < 2 or not any(r in cols for r in MONEY_ROLES) or letters == 0 or left > 0.4 * letters:
        return None
    return cols


def is_ledger_header(cols: dict | None) -> bool:
    return bool(cols) and "balance" in cols and any(r in cols for r in ("withdraw", "deposit", "amount"))


def nearest_role(tok: Money, cols: dict | None, roles=MONEY_ROLES) -> str | None:
    best = None
    for role in roles:
        if not cols or role not in cols:
            continue
        s, e = cols[role]
        d = min(abs(tok.end - e), abs((tok.start + tok.end) / 2 - (s + e) / 2))
        if best is None or d < best[0]:
            best = (d, role)
    return best[1] if best else None


# ---------------------------------------------------------------------------- wording

SUMMARY_HARD = re.compile(lab(
    "statement period", "period covered", "opening balance", "closing balance", "previous balance", "new balance",
    "minimum payment", "total payments", "total credits", "total debits", "payment due", "payments & credits",
    "payments and credits", "new purchases", "purchases & debits", "purchases and debits", "credit limit",
    "available credit", "amount due", "promotional balance", "annual interest rate", "interest rate",
    "periode du releve", "solde precedent", "nouveau solde", "paiement minimum", "limite de credit",
    "credit disponible", "paiements et credits", "achats et debits", "date d'echeance", "montant du",
    "taux d'interet", "total des",
))
# "Visa" alone is not enough: chequing statements mention Visa Debit cards.
CARD_CUES = re.compile(lab("credit limit", "available credit", "minimum payment", "limite de credit", "credit disponible",
                           "paiement minimum", "paiement minimal")
                       + r"|\b(?:mastercard|visa|american\s*express|amex)\b.*?" + f"(?:{lab('new balance', 'payment due', 'nouveau solde', 'echeance')})")
CARD_CREDIT = re.compile(r"\b(?:payment|paiement|thank\s*-?\s*you|merci|refund|remboursement|return|retour|"
                         r"credit\s*(?:adjustment|voucher|memo)|ajustement|rebate|cash\s*back|remise|reversal|annulation)")
FEE_WORDS = re.compile(r"\b(?:interest|interets?|fees?|frais|cotisation|nsf|over\s*limit|late\s*(?:payment\s*)?charge|"
                       r"service\s*charge|insurance|assurance|protection|cash\s*advance\s*fee)")
_FEE_BACK = re.compile(r"\b(?:reversal|refund|rebate|remboursement|annulation|waived?|credit)\b")
BANK_OUT = re.compile(r"\b(?:purchase|achat|debit|withdrawal|withdraw|retrait|fees?|frais|charge|bill\s*payment|"
                      r"paiement\s*de\s*facture|payment\s*to|e-?transfer\s*(?:sent|to)|virement\s*envoye|transfer\s*to|"
                      r"preauthori[sz]ed|prelevement|pos|cheque|chq|nsf)\b")
BANK_IN = re.compile(r"\b(?:payroll|salary|salaire|paie|direct\s*deposit|deposit|depot|refund|remboursement|rebate|"
                     r"interest|interets?|dividend|e-?transfer\s*(?:received|from)|virement\s*recu|transfer\s*from|"
                     r"received|incoming|credit)\b")
FORWARD = re.compile(lab("balance forward", "brought forward", "balance carried forward", "carried forward",
                         "solde reporte", "report du solde"))
OPENING = re.compile(lab("opening balance", "previous balance", "starting balance",
                         "beginning balance", "balance at beginning", "solde d'ouverture", "solde d ouverture",
                         "solde precedent", "solde anterieur", "solde reporte", "solde initial", "solde de depart",
                         "ancien solde", "solde au debut", "solde d'ouverture"))
CLOSING = re.compile(lab("closing balance", "ending balance", "balance at end", "final balance", "solde de fermeture",
                         "solde de cloture", "solde final", "solde a la fin", "nouveau solde", "closing totals"))
_TOTAL_ROW = re.compile(r"^\s*(?:sub\s*-?\s*totals?|sous\s*-?\s*total|totals?|total\s+des)\b")
_BANK_SKIP = re.compile(lab("interest rate", "taux d'interet", "year to date", "year-to-date", "cumul annuel",
                            "account number", "numero de compte"))
_FOOTER = re.compile(r"page\s*\d|\d+\s*(?:of|de|/)\s*\d+|continued|suite|a\s*suivre|account\s*(?:number|no)|"
                     r"numero\s*de\s*compte|statement|releve|balance|solde|total|www\.|https?:|member|membre|"
                     r"trademark|marque")
FRENCH_CUES = re.compile(r"\b(?:solde|retraits?|depots?|releve|periode|paiements?|achats|montant|janv|fevr|avr|juil|"
                         r"aout|decembre|du|au|et|des)\b")
ENGLISH_CUES = re.compile(r"\b(?:balance|withdrawals?|deposits?|statement|period|payments?|purchases|amount|the|and|of|to)\b")


def keyword_sign(desc_f: str) -> int:
    """Chequing guess from wording, used only when neither the balance nor the column says."""
    if BANK_OUT.search(desc_f):
        return -1
    if BANK_IN.search(desc_f):
        return 1
    return -1


def card_sign(tok: Money, desc_f: str, role: str | None = None) -> int:
    """FinVault sign for a card row: purchases, interest and fees are money out; payments and credits are money in."""
    if tok.credit or tok.negative:
        return 1
    if tok.debit:
        return -1
    if role == "deposit":
        return 1
    if role == "withdraw":
        return -1
    if FEE_WORDS.search(desc_f):
        return 1 if _FEE_BACK.search(desc_f) else -1
    return 1 if CARD_CREDIT.search(desc_f) else -1


# ---------------------------------------------------------------------------- rows


@dataclass
class Row:
    date: DateTok | None
    desc: str
    amount: Decimal | None  # absolute; None marks a balance checkpoint, not a transaction
    amount_text: str = ""
    balance: Decimal | None = None
    hint: int | None = None  # sign from the column or an explicit sign
    guess: int = -1  # sign from the wording
    line_no: int = 0
    memo: str = ""
    desc_start: int = 0
    money_start: int = 10_000
    sign: int = 0
    verified: bool = False
    fee: bool = False
    continuations: int = 0

    @property
    def signed(self) -> Decimal:
        return (self.amount or Decimal(0)) * self.sign


@dataclass
class Reading:
    kind: str  # ledger | card
    rows: list[Row] = field(default_factory=list)  # transactions and balance checkpoints, in order
    opening: Decimal | None = None
    closing: Decimal | None = None
    columns_found: bool = False
    problems: list = field(default_factory=list)  # (last row of group, balance change, rows' change)
    unverified: int = 0

    @property
    def transactions(self) -> list[Row]:
        return [r for r in self.rows if r.amount is not None]


def _continuation_ok(target: Row | None, f: str, cols: dict | None) -> bool:
    """A wrapped description line: no date, no amount, sitting under the previous row's description."""
    if target is None or target.continuations >= 2:
        return False
    text = f.strip()
    if not text or len(text) > 60 or not re.search(r"[a-z]", text) or _FOOTER.search(text) or FX_CUE.search(text):
        return False
    pos = len(f) - len(f.lstrip())
    left = cols["description"][0] if cols and "description" in cols else target.desc_start
    right = target.money_start
    if cols:
        money_cols = [cols[r][0] for r in ("withdraw", "deposit", "amount", "balance") if r in cols]
        if money_cols:
            right = min(right, min(money_cols) + 2)
    return pos >= left - 3 and pos + len(text) <= right + 2


def _append_desc(target: Row, line: str, f: str) -> None:
    target.desc = collapse(f"{target.desc} {line.strip()}")
    target.continuations += 1


def _row_text(line: str, start: int, end: int) -> str:
    return collapse(line[start:end])


def _side_date(dates: list[DateTok], cols: dict | None) -> DateTok | None:
    """TD-style rows put the date in its own column after the amounts instead of first."""
    if not cols or "date" not in cols or "description" not in cols or cols["date"][0] < cols["description"][0]:
        return None
    ds, de = cols["date"]
    return next((t for t in dates if t.start <= de + 4 and t.end >= ds - 4), None)


def read_ledger(lines: list[str], debt: bool = False) -> Reading:
    """Chequing/savings rows. With debt=True (card or loan ledger) the balance is what you owe."""
    reading = Reading("ledger")
    cols: dict | None = None
    in_table = False
    pending: Row | None = None  # a dated line whose amount comes on a following line
    last: Row | None = None
    cur_date: DateTok | None = None

    for n, raw_line in enumerate(lines, start=1):
        line = norm_line(raw_line).rstrip()
        f = fold(line)
        if not f.strip():
            continue
        dates = find_dates(f, line)
        hdr = detect_header(f)
        if hdr:
            if is_ledger_header(hdr) or not cols:
                cols = hdr
                reading.columns_found = reading.columns_found or is_ledger_header(hdr)
            in_table, pending, last = True, None, None
            continue
        toks = money_tokens(f, dates)
        real = [t for t in toks if not t.foreign]

        labels = sorted((m for pat in (CLOSING, OPENING, FORWARD) for m in pat.finditer(f)), key=lambda m: m.start())
        if labels:
            on_balance = [t for t in real if nearest_role(t, cols) == "balance"] if is_ledger_header(cols) else []
            for i, label in enumerate(labels):
                stop = labels[i + 1].start() if i + 1 < len(labels) else len(f)
                after = [t for t in real if label.end() <= t.start < stop]
                # In the table the balance column holds it; in a summary box it follows the label.
                pick = on_balance[-1] if on_balance and len(labels) == 1 else (after[0] if after else None)
                if pick is None:
                    continue
                if label.re is CLOSING:
                    reading.closing = pick.value
                    if reading.transactions:
                        in_table = False  # what follows the closing balance is summary text
                elif label.re is OPENING and reading.opening is None:
                    reading.opening = pick.value  # may be in a summary box after the table
                elif label.re is FORWARD:
                    if reading.transactions:  # top of a new page: a checkpoint for the running balance
                        reading.rows.append(Row(None, "", None, balance=pick.value, line_no=n))
                    elif reading.opening is None:
                        reading.opening = pick.value
            pending = last = None
            continue

        pref = date_prefix(f, dates)
        row_date = pref.first if pref else _side_date(dates, cols)
        if row_date:
            cur_date = row_date
        desc_start = pref.end if pref else len(f) - len(f.lstrip())
        first_money = min([t.start for t in toks] + ([row_date.start] if row_date and not pref else []),
                          default=len(line))
        desc = _row_text(line, desc_start, first_money)
        desc_f = fold(desc)

        if _TOTAL_ROW.search(desc_f) or _BANK_SKIP.search(f) or SUMMARY_HARD.search(f):
            pending = last = None
            continue

        if not real:
            if toks and last is not None and FX_CUE.search(f):
                last.memo = collapse(f"{last.memo} {line.strip()}")
                continue
            if row_date:
                pending = Row(row_date, desc, None, line_no=n, desc_start=desc_start)
                last = None
                continue
            target = pending or last
            if _continuation_ok(target, f, cols):
                _append_desc(target, line, f)
                continue
            pending = last = None
            continue

        # a line with money on it
        date_tok = row_date
        if date_tok is None:
            if pending is not None and (in_table or cols is None):
                date_tok = pending.date
                desc = collapse(f"{pending.desc} {desc}")
                desc_start = pending.desc_start
            elif in_table and cur_date is not None and desc:
                date_tok = cur_date  # later rows of the same day often leave the date blank
            else:
                pending = last = None
                continue
        pending = None
        if not desc or re.fullmatch(r"[\W\d]*", desc):
            last = None
            continue

        balance_tok = None
        if is_ledger_header(cols):
            if len(real) >= 2:
                balance_tok, amount_tok = real[-1], real[-2]
            elif nearest_role(real[0], cols) == "balance":
                reading.rows.append(Row(None, "", None, balance=real[0].value, line_no=n))
                last = None
                continue
            else:
                amount_tok = real[0]
        elif cols is None and len(real) >= 2:
            balance_tok, amount_tok = real[-1], real[-2]
        else:
            amount_tok = real[-1]

        role = nearest_role(amount_tok, cols, ("withdraw", "deposit", "amount")) if cols else None
        if role == "withdraw":
            hint = -1
        elif role == "deposit":
            hint = 1
        elif amount_tok.negative or amount_tok.debit:
            hint = -1
        elif amount_tok.credit or amount_tok.text.startswith("+"):
            hint = 1
        else:
            hint = None
        fx = [t for t in toks if t.foreign]
        row = Row(date_tok, desc, abs(amount_tok.value), amount_tok.text,
                  balance=balance_tok.value if balance_tok else None, hint=hint, guess=keyword_sign(desc_f),
                  line_no=n, desc_start=desc_start, money_start=first_money,
                  memo=_row_text(line, fx[0].start, amount_tok.start) if fx else "")
        reading.rows.append(row)
        last = row
    _resolve_ledger_signs(reading, debt)
    return reading


def _solve(group: list[Row], want: Decimal) -> tuple[list[int] | None, bool]:
    """Signs for the rows that make the balance move by `want`. Returns (signs, unique)."""
    amounts = [r.amount for r in group]
    prefs = [r.hint if r.hint is not None else r.guess for r in group]
    if len(group) > 12:
        total = sum(a * s for a, s in zip(amounts, prefs))
        return (prefs, False) if total == want else (None, False)
    best, best_score, ties = None, -1, 0
    for signs in product((1, -1), repeat=len(group)):
        if sum(a * s for a, s in zip(amounts, signs)) != want:
            continue
        score = sum(s == p for s, p in zip(signs, prefs))
        if score > best_score:
            best, best_score, ties = list(signs), score, 1
        elif score == best_score:
            ties += 1
    return best, ties == 1


def _resolve_ledger_signs(reading: Reading, debt: bool = False) -> None:
    """Give each row the sign that makes the running balance work, and record where it doesn't."""
    reading.problems, reading.unverified = [], 0
    prev = reading.opening
    group: list[Row] = []

    def settle(target: Decimal | None) -> None:
        nonlocal prev
        if group:
            if prev is None or target is None:
                for r in group:
                    r.sign = r.hint if r.hint is not None else r.guess
                reading.unverified += len(group)
            else:
                want = target - prev
                if debt:
                    want = -want
                signs, unique = _solve(group, want)
                if signs is None:
                    for r in group:
                        r.sign = r.hint if r.hint is not None else r.guess
                    got = sum((r.signed for r in group), Decimal(0))
                    reading.problems.append((group[-1], want, got))
                else:
                    for r, s in zip(group, signs):
                        r.sign, r.verified = s, unique
                    if not unique:
                        reading.unverified += len(group)
        group.clear()
        if target is not None:
            prev = target

    for r in reading.rows:
        if r.amount is None:
            settle(r.balance)
            continue
        group.append(r)
        if r.balance is not None:
            settle(r.balance)
    settle(reading.closing)


def read_card(lines: list[str]) -> Reading:
    reading = Reading("card")
    cols: dict | None = None
    last: Row | None = None
    for n, raw_line in enumerate(lines, start=1):
        line = norm_line(raw_line).rstrip()
        f = fold(line)
        if not f.strip():
            continue
        hdr = detect_header(f)
        if hdr:
            cols, last = hdr, None
            reading.columns_found = True
            continue
        if SUMMARY_HARD.search(f):
            last = None
            continue
        dates = find_dates(f, line)
        pref = date_prefix(f, dates)
        if pref is None:
            toks = money_tokens(f, dates)
            if last is not None and toks and (all(t.foreign for t in toks) or FX_CUE.search(f)):
                last.memo = collapse(f"{last.memo} {line.strip()}")
            elif last is not None and not toks and _continuation_ok(last, f, cols):
                _append_desc(last, line, f)
            else:
                last = None
            continue
        toks = money_tokens(f, dates, pref.end)
        real = [t for t in toks if not t.foreign]
        if not real:
            last = None
            continue
        tok = real[-1]
        if cols and "amount" in cols and len(real) > 1:
            tok = min(real, key=lambda t: abs(t.end - cols["amount"][1]))
        first_money = min(t.start for t in toks)
        desc = _row_text(line, pref.end, first_money)
        desc = re.sub(rf"(?i)\s+{_CCY}$", "", desc)
        desc_f = fold(desc)
        if not desc or re.fullmatch(r"[\W\d]*", desc) or _TOTAL_ROW.search(desc_f):
            last = None
            continue
        fx = [t for t in toks if t.foreign]
        role = nearest_role(tok, cols, ("withdraw", "deposit", "amount")) if cols else None
        row = Row(pref.first, desc, abs(tok.value), tok.text, line_no=n, desc_start=pref.end, money_start=first_money,
                  memo=_row_text(line, fx[0].start, tok.start) if fx else "")
        row.sign = card_sign(tok, desc_f, role)
        row.fee = bool(FEE_WORDS.search(desc_f)) and row.sign < 0
        reading.rows.append(row)
        last = row
    return reading


# ---------------------------------------------------------------------------- statement summaries

_FLAT_AMT = rf"[=+]?\s?(-?\s?\$?\s?-?{_NUM}(?:\s?\$)?(?:\s?cr\b|-(?!\d))?)(?![\d%])"
CARD_TOTALS = {
    "previous": [lab("previous statement balance", "previous balance", "balance from last statement",
                     "balance from your last statement", "solde precedent", "solde anterieur", "solde du releve precedent")],
    "new": [lab("new statement balance", "new balance", "nouveau solde", "solde du present releve", "solde de ce releve")],
    "purchases": [lab("new purchases & debits", "new purchases and debits", "purchases & debits", "purchases and debits",
                      "purchases & other charges", "purchases and other charges", "total purchases", "total new purchases",
                      "achats et debits", "achats et autres debits", "nouveaux achats et debits", "total des achats",
                      "nouveaux achats"),
                  lab("new purchases", "purchases", "achats")],
    "credits": [lab("total payments & credits", "total payments and credits", "payments & credits", "payments and credits",
                    "payments & other credits", "payments and other credits", "total des paiements et credits",
                    "paiements et credits", "paiements et autres credits"),
                lab("total payments", "payments", "paiements")],
    "interest": [lab("interest charged", "interest charges", "total interest charged", "total interest",
                     "frais d'interet", "interets debiteurs", "interets"), lab("interest")],
    "fees": [lab("fees charged", "total fees charged", "total fees", "frais divers", "fees", "frais")],
    "cash": [lab("cash advances & other debits", "cash advances", "cash advance", "avances de fonds", "avances en especes")],
}
BANK_TOTALS = {
    "deposits": [lab("total deposits & credits", "total deposits and credits", "total deposits into your account",
                     "total deposits", "total credits", "deposits & credits", "total des depots", "total des credits")],
    "withdrawals": [lab("total withdrawals & debits", "total withdrawals and debits", "total cheques & debits",
                        "total withdrawals from your account", "total withdrawals", "total debits",
                        "cheques & debits", "total des retraits", "total des debits")],
}


def read_totals(flat_f: str, spec: dict[str, list[str]]) -> dict[str, Decimal]:
    found = {}
    for key, groups in spec.items():
        for alternation in groups:
            m = re.search(rf"(?<![a-z])(?:{alternation})(?![a-z])\s*(?:\([^)]{{0,20}}\))?\s*:?\s*{_FLAT_AMT}", flat_f)
            if m:
                value = parse_amount(m.group(1).replace(" $", "$"))
                if value is not None and re.search(r"cr", m.group(1)):
                    value = -abs(value)  # a credit balance: the bank owes you
                if value is not None:
                    found[key] = value
                    break
    return found


def looks_french(flat_f: str) -> bool:
    return len(FRENCH_CUES.findall(flat_f)) > len(ENGLISH_CUES.findall(flat_f))
