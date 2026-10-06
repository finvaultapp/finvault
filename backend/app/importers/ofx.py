"""OFX / QFX / QBO parser (both SGML 1.x and XML 2.x).

QFX (Quicken) and QBO (QuickBooks) are OFX with a couple of extra tags, so one
parser covers every "Quicken / Money / QuickBooks" download Canadian banks offer.
"""
import re
from datetime import date

from .common import ParsedTxn, ParseResult, parse_amount

_TXN_BLOCK = re.compile(r"<STMTTRN>(.*?)(?=</STMTTRN>|<STMTTRN>|</BANKTRANLIST>)", re.S | re.I)
_LEAF = re.compile(r"<([A-Z0-9.]+)>([^<\r\n]*)", re.I)


def looks_like_ofx(text: str) -> bool:
    head = text[:2000].upper()
    return "OFXHEADER" in head or "<OFX>" in head or "<?OFX" in head


def _ofx_date(value: str) -> date | None:
    digits = re.sub(r"\D", "", value)[:8]
    if len(digits) < 8:
        return None
    try:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    except ValueError:
        return None


def _leaves(block: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for tag, value in _LEAF.findall(block):
        value = value.strip()
        if value:
            out.setdefault(tag.upper(), value)
    return out


def _unescape(s: str) -> str:
    return s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&apos;", "'").replace("&quot;", '"')


def parse_ofx(text: str) -> ParseResult:
    result = ParseResult(format="ofx")
    head = _leaves(text.split("<BANKTRANLIST>")[0] if "<BANKTRANLIST>" in text else text[:5000])
    result.currency = head.get("CURDEF")
    result.account_number = head.get("ACCTID")
    result.text_sample = " ".join(v for k, v in head.items() if k in ("ACCTTYPE", "DESC", "NAME", "ORG", "ACCTID"))
    bal = re.search(r"<LEDGERBAL>.*?<BALAMT>([^<\r\n]+)", text, re.S | re.I)
    if bal:
        result.statement_balance = parse_amount(bal.group(1))

    for i, block in enumerate(_TXN_BLOCK.findall(text), start=1):
        f = _leaves(block)
        when = _ofx_date(f.get("DTPOSTED", "") or f.get("DTUSER", ""))
        amount = parse_amount(f.get("TRNAMT"))
        if when is None or amount is None:
            result.warnings.append(f"Transaction {i}: skipped, missing date or amount.")
            continue
        name = _unescape(f.get("NAME", ""))
        memo = _unescape(f.get("MEMO", ""))
        description = name or memo or f.get("TRNTYPE", "")
        if name and memo and memo.upper() not in name.upper():
            description = f"{name} {memo}"
        result.transactions.append(ParsedTxn(
            date=when, amount=amount, description=description.strip(), payee=name.strip(), memo=memo,
            external_id=f.get("FITID"), currency=result.currency, type_text=f.get("TRNTYPE", ""), row=i,
        ))
    if not result.transactions:
        result.warnings.append("No transactions found in this OFX/QFX file.")
    return result
