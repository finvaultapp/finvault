from .common import ParsedTxn, ParseResult, decode_bytes, normalize_merchant
from .csvfile import parse_csv
from .ofx import looks_like_ofx, parse_ofx
from .qif import looks_like_qif, parse_qif

MAX_BYTES = 15 * 1024 * 1024


def parse_file(filename: str, raw: bytes, *, preset_id=None, mapping=None, date_format=None,
               invert=None, account_type=None, account_currency=None) -> ParseResult:
    if len(raw) > MAX_BYTES:
        raise ValueError("File is larger than 15 MB.")
    text = decode_bytes(raw)
    name = (filename or "").lower()
    if name.endswith((".ofx", ".qfx", ".qbo")) or looks_like_ofx(text):
        result = parse_ofx(text)
        if invert:
            for t in result.transactions:
                t.amount = -t.amount
            result.inverted = True
    elif name.endswith(".qif") or looks_like_qif(text):
        result = parse_qif(text, date_format)
        if invert:
            for t in result.transactions:
                t.amount = -t.amount
            result.inverted = True
    elif name.endswith((".csv", ".txt", ".tsv")) or "," in text[:500] or ";" in text[:500]:
        result = parse_csv(text, preset_id=preset_id, mapping=mapping, date_format=date_format, invert=invert,
                           account_type=account_type, account_currency=account_currency)
    else:
        raise ValueError("Unsupported file. Use OFX, QFX, QBO, QIF or CSV. PDF statements can't be imported.")
    if result.format != "csv" and preset_id:
        result.preset = preset_id
    return result


__all__ = ["ParsedTxn", "ParseResult", "parse_file", "normalize_merchant"]
