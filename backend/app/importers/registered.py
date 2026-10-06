"""Registered-account statements (TFSA, FHSA, RRSP): which plan a file is for, and what each line is.

Two jobs:

1. `suggest_kind` reads an account name or a statement's text and says tfsa / fhsa / rrsp, or None.
   RRIFs (and LIRAs, RESPs...) are not tracked, so they come back as None and stay plain accounts.
2. `classify` gives every line a plan movement type (PLAN_MOVES) from the statement's own type column
   and description, in English and French. Bank TFSA savings accounts have no type column: money in is
   a contribution, money out a withdrawal, interest is growth.

It also reads two brokerage activity exports that the ordinary CSV mapper can't, both matched by header
names (never by position):

- Wealthsimple activity export (transaction_date, activity_type, activity_sub_type, net_cash_amount...)
- Questrade account activity (Transaction Date, Action, Symbol, Description, Net Amount, Activity Type...)

Neither layout has been confirmed against a real file; they follow the column names the investments
importer (holdings.py) already uses. The member sees every line's type in the preview and can change it.
"""
from __future__ import annotations

import csv
import io
import re
from decimal import Decimal

from .common import ParsedTxn, ParseResult, detect_date_format, looks_like_date, normalize_header, parse_amount, try_parse_date

KINDS = ("tfsa", "fhsa", "rrsp")
PLAN_MOVES = ("contribution", "withdrawal", "transfer_in", "transfer_out", "rrsp_to_fhsa", "growth", "fee", "trade", "other")
PLAN_MOVE_PATTERN = "^(" + "|".join(PLAN_MOVES) + ")$"

# --- Which plan ------------------------------------------------------------------------

_NOT_TRACKED = re.compile(r"\b(?:rrif|ferr|lif|frv|lira|cri|resp|reee|rdsp|reei|registered retirement income fund|"
                          r"fonds enregistre de revenu de retraite|registered education savings)\b")
_KIND_WORDS = {
    # FHSA first: "celiapp" contains "celi".
    "fhsa": re.compile(r"\b(?:fhsa|celiapp|first home savings|compte d epargne libre d impot pour l achat d une premiere propriete)\b"),
    "tfsa": re.compile(r"\b(?:tfsa|celi|tax free savings|compte d epargne libre d impot)\b(?! pour l achat)"),
    "rrsp": re.compile(r"\b(?:rrsp|reer|rsp|registered retirement savings|regime enregistre d epargne retraite)\b"),
}
_SPOUSAL = re.compile(r"\b(?:spousal|conjoint|de conjoint|du conjoint)\b")


def _fold(text: str) -> str:
    return normalize_header(text or "")


def suggest_kind(*texts: str) -> str | None:
    """tfsa / fhsa / rrsp when the text names exactly one tracked plan (or clearly one most often)."""
    folded = " ".join(_fold(t) for t in texts if t)
    if not folded:
        return None
    counts = {k: len(p.findall(folded)) for k, p in _KIND_WORDS.items()}
    # An FHSA statement can mention the RRSP it received a transfer from; count the whole phrase as FHSA.
    moved = len(re.findall(r"\b(?:rrsp|reer)\b \w+ \b(?:fhsa|celiapp)\b", folded))
    counts["rrsp"] -= moved
    found = {k: n for k, n in counts.items() if n > 0}
    if not found:
        return None
    if _NOT_TRACKED.search(folded) and sum(found.values()) <= len(_NOT_TRACKED.findall(folded)):
        return None  # "RRIF" (or a RRSP-to-RRIF statement): not a plan FinVault tracks
    best = max(found.values())
    for k in ("fhsa", "tfsa", "rrsp"):  # ties: the more specific name wins
        if found.get(k) == best:
            return k
    return None


def is_spousal(*texts: str) -> bool:
    folded = " ".join(_fold(t) for t in texts if t)
    return bool(_SPOUSAL.search(folded)) and bool(_KIND_WORDS["rrsp"].search(folded))


# --- What each line is ------------------------------------------------------------------

# Whole type cells (normalized). Statement codes are short, so they're only trusted in the type column.
CODES: dict[str, str] = {}
for _move, _words in {
    "contribution": "cont contrib contribution contributions con cotisation cotisations deposit deposits dep depot depots",
    "withdrawal": "wd wdr withdrawal withdrawals retrait retraits",
    "transfer_in": "tfi trfin transferin transfertentrant",
    "transfer_out": "tfo trfout transferout transfertsortant",
    "growth": ("div divs dividend dividends dividende dividendes int interest interets interet dist dis distribution "
               "distributions rei reinvest drip roc cil fplint"),
    "fee": "fee fees fch frais commission commissions srvchg nrt tax",
    "trade": "buy sell bought sold achat vente trade trades fxt fx",
}.items():
    for _w in _words.split():
        CODES[_w] = _move
for _phrase, _move in {
    "transfer in": "transfer_in", "transfert entrant": "transfer_in", "tf in": "transfer_in",
    "transfer out": "transfer_out", "transfert sortant": "transfer_out", "tf out": "transfer_out",
    "fees and rebates": "fee", "management fee": "fee", "withholding tax": "fee", "non resident tax": "fee",
    "interest income": "growth", "dividend reinvestment": "growth", "reinvested dividend": "growth",
    "return of capital": "growth", "market buy": "trade", "limit buy": "trade", "market sell": "trade",
    "limit sell": "trade", "fx conversion": "trade", "currency conversion": "trade",
}.items():
    CODES[_phrase] = _move

_RRSP_TO_FHSA = re.compile(r"\b(?:rrsp|reer|rsp)\b.{0,30}\b(?:to|au|a|vers|into|dans)\b.{0,12}\b(?:fhsa|celiapp)\b"
                           r"|\b(?:fhsa|celiapp)\b.{0,30}\b(?:from|du|de)\b.{0,12}\b(?:rrsp|reer|rsp)\b"
                           r"|\b(?:transfer|transfert|tfr)\b.{0,6}\b(?:from|du|de)\b (?:(?:an?|un|votre|my|your) )?(?:rrsp|reer)\b")
# (pattern, move); "sign" moves pick their direction from the amount.
_PHRASES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:internal transfer|transfert interne|virement interne|internal)\b"), "sign"),
    (re.compile(r"\b(?:transfer in|transfert entrant|incoming transfer)\b"), "transfer_in"),
    (re.compile(r"\b(?:transfer out|transfert sortant|outgoing transfer)\b"), "transfer_out"),
    (re.compile(r"\b(?:institutional transfer|transfert institutionnel|transfert entre institutions|direct transfer|"
                r"transfert direct|t2033|account transfer|(?:from|to) another (?:institution|financial institution)|"
                r"(?:d|vers) une autre institution)\b"), "transfer"),
    (re.compile(r"\b(?:fees?|frais|commissions?|withholding tax|non resident tax|service charge)\b"), "fee"),
    (re.compile(r"\b(?:dividends?|dividendes?|interest|interets?|distributions?|reinvest\w*|drip|return of capital|"
                r"remboursement de capital)\b"), "growth"),
    (re.compile(r"\b(?:buy|bought|sell|sold|achat|vente|trade|fx conversion|currency conversion|conversion de devises)\b"), "trade"),
    (re.compile(r"\b(?:contributions?|cotisations?|deposits?|depots?)\b"), "contribution"),
    (re.compile(r"\b(?:withdrawals?|retraits?|redemption)\b"), "withdrawal"),
]


def _signed(move: str, amount: Decimal) -> str:
    """Fix the direction of a move from the amount's sign (a contribution can't take money out)."""
    if move in ("sign", "contribution", "withdrawal"):
        if amount > 0:
            return "contribution"
        return "withdrawal" if amount < 0 else "other"
    if move == "transfer":
        return "transfer_in" if amount >= 0 else "transfer_out"
    return move


def classify(kind: str | None, amount: Decimal, type_texts: list[str] | tuple[str, ...] = (), description: str = "",
             strict: bool = False) -> str:
    """The plan movement type for one line.

    `strict` is for brokerage exports: a line nothing recognises is "other" instead of being guessed from its
    sign, because a brokerage account has many money movements that aren't contributions.
    """
    amount = Decimal(amount)
    types = [_fold(t) for t in type_texts if t and _fold(t)]
    desc = _fold(description)
    everything = " ".join(types + [desc])
    if _RRSP_TO_FHSA.search(everything):
        if kind == "fhsa":
            return "rrsp_to_fhsa" if amount >= 0 else "transfer_out"
        if kind == "rrsp":
            return "transfer_out" if amount <= 0 else "transfer_in"
    # Internal and institutional transfers are named in the description even when the type says "transfer".
    for i in (0, 3):
        if _PHRASES[i][0].search(desc):
            return _signed(_PHRASES[i][1], amount)
    for t in types:
        if t in CODES:
            return _signed(CODES[t], amount)
        if t.replace(" ", "") in CODES:
            return _signed(CODES[t.replace(" ", "")], amount)
    for text, is_desc in [(t, False) for t in types] + [(desc, True)]:
        for i, (pat, move) in enumerate(_PHRASES):
            # A bank's "TRANSFER IN" description is usually money from chequing (a contribution), so the
            # direction-only phrases are trusted in a type column, not in descriptions.
            if i in (1, 2) and is_desc:
                continue
            if pat.search(text):
                return _signed(move, amount)
    if strict or amount == 0:
        return "other"
    return _signed("sign", amount)


def leading_code(description: str) -> tuple[str, str]:
    """('CONT', 'Contribution') from 'CONT Contribution': statement PDFs print the type code first."""
    m = re.match(r"\s*([A-Z]{2,7})\b\s*(.*)$", description or "")
    if m and _fold(m.group(1)) in CODES:
        return m.group(1), (m.group(2).strip() or m.group(1))
    return "", description


# --- Brokerage activity exports -----------------------------------------------------------

def _rows(text: str) -> list[list[str]]:
    lines = [l for l in text.splitlines()[:30] if l.strip()]
    delim = max([",", ";", "\t"], key=lambda d: sum(l.count(d) for l in lines))
    rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text), delimiter=delim)]
    return [r for r in rows if any(c for c in r)]


def _col(headers: list[str], *names: str) -> int | None:
    for n in names:
        if n in headers:
            return headers.index(n)
    return None


LAYOUTS = {
    # name: (required headers, column roles -> header synonyms)
    "Wealthsimple activity": (
        # "activity sub type" or "net cash amount" sets it apart from card exports with an activity type (Rogers).
        [("activity type",), ("activity sub type", "net cash amount"), ("net cash amount", "amount"),
         ("transaction date", "date")],
        {"date": ("transaction date", "date"), "amount": ("net cash amount", "amount"), "type": ("activity sub type",),
         "type2": ("activity type",), "symbol": ("symbol",), "name": ("name", "description"),
         "currency": ("currency",), "account": ("account type",), "direction": ("direction",),
         "id": ("transaction id", "activity id", "id")}),
    "Questrade activity": (
        [("action",), ("net amount",), ("transaction date",), ("activity type",)],
        {"date": ("transaction date",), "amount": ("net amount",), "type": ("action",), "type2": ("activity type",),
         "symbol": ("symbol",), "name": ("description",), "currency": ("currency",), "account": ("account type",)}),
}
_OUTFLOW = {"out", "outflow", "debit", "withdrawal", "sortie", "debit cash"}


def _find_layout(rows: list[list[str]]) -> tuple[str, int] | None:
    for i, row in enumerate(rows[:30]):
        headers = [normalize_header(c) for c in row]
        for name, (required, _) in LAYOUTS.items():
            if all(any(n in headers for n in alts) for alts in required):
                # "action" + "net amount" means Questrade, even though it also has an activity type column.
                if name == "Wealthsimple activity" and "action" in headers and "net amount" in headers:
                    continue
                return name, i
    return None


def parse_activity_export(text: str, *, date_format: str | None = None, account_currency: str | None = None,
                          registered_kind: str | None = None) -> ParseResult | None:
    """A ParseResult for a Wealthsimple or Questrade activity export, or None when the file is something else."""
    rows = _rows(text)
    found = _find_layout(rows) if rows else None
    if not found:
        return None
    layout, header_idx = found
    headers = [normalize_header(c) for c in rows[header_idx]]
    cols = {role: _col(headers, *names) for role, names in LAYOUTS[layout][1].items()}
    result = ParseResult(format="csv", layout=layout, columns=rows[header_idx])
    result.mapping = {k: v for k, v in cols.items() if v is not None and k in ("date", "amount", "type", "currency")}
    di = cols["date"]
    data = [r for r in rows[header_idx + 1:] if di < len(r) and looks_like_date(r[di])]
    result.sample_rows = data[:8]
    fmt, ambiguous = detect_date_format([r[di] for r in data], date_format)
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
        amount = parse_amount(cell(r, "amount"))
        if when is None or amount is None:
            result.warnings.append(f"Row {n}: skipped, could not read the date or amount.")
            continue
        if amount > 0 and normalize_header(cell(r, "direction")) in _OUTFLOW:
            amount = -amount
        symbol, name = cell(r, "symbol"), cell(r, "name")
        types = [x for x in (cell(r, "type"), cell(r, "type2")) if x]
        desc = " ".join(x for x in (symbol, name) if x and x not in ("-", "N/A")) or " ".join(types) or "(no description)"
        parsed.append(ParsedTxn(date=when, amount=amount, description=desc[:500], memo=" / ".join(types),
                                currency=(cell(r, "currency") or "").upper()[:3] or None,
                                external_id=cell(r, "id") or None, type_text=" | ".join(types),
                                account_label=cell(r, "account"), row=n))

    labels = sorted({t.account_label for t in parsed if t.account_label})
    if len(labels) > 1:
        if registered_kind:
            keep = [t for t in parsed if suggest_kind(t.account_label) == registered_kind]
            if keep and len(keep) < len(parsed):
                parsed = keep
                result.warnings.append("Lines for other accounts in this file were left out.")
        else:
            result.warnings.append("This file holds lines from more than one account. Check that each belongs here.")
    if account_currency:
        other = [t for t in parsed if t.currency and t.currency != account_currency.upper()]
        if other and len(other) < len(parsed):
            parsed = [t for t in parsed if t not in other]
            result.warnings.append("Lines in another currency were left out. Import them into that currency's account.")
    kinds = {suggest_kind(label) for label in labels}
    result.kind_hint = kinds.pop() if len(kinds) == 1 else None  # a mixed file doesn't name one plan
    result.spousal = is_spousal(*labels)
    result.currency = next((t.currency for t in parsed if t.currency), None)
    if ambiguous:
        result.warnings.append("Dates could be month-first or day-first. Assumed month/day/year; change it if that is wrong.")
    result.transactions = parsed
    return result


def strict_layout(result: ParseResult) -> bool:
    """Brokerage exports, where an unrecognised line is "other" rather than a guess from its sign."""
    return result.layout in LAYOUTS


def classify_result(result: ParseResult, kind: str | None) -> None:
    """Give every parsed line a plan movement type (in place)."""
    strict = strict_layout(result)
    for t in result.transactions:
        texts = [x for x in t.type_text.split(" | ") if x] if t.type_text else []
        t.plan_move = classify(kind, t.amount, texts, t.description, strict=strict)
