from .common import ParsedTxn, ParseResult, decode_bytes, normalize_merchant
from .csvfile import parse_csv
from .ofx import looks_like_ofx, parse_ofx
from .pdf import looks_like_pdf, parse_pdf
from .qif import looks_like_qif, parse_qif
from .registered import is_spousal, leading_code, parse_activity_export, suggest_kind

MAX_BYTES = 15 * 1024 * 1024


def parse_file(filename: str, raw: bytes, *, preset_id=None, mapping=None, date_format=None,
               invert=None, account_type=None, account_currency=None, registered_kind=None) -> ParseResult:
    if len(raw) > MAX_BYTES:
        raise ValueError("File is larger than 15 MB.")
    name = (filename or "").lower()
    if name.endswith(".pdf") or looks_like_pdf(raw):
        result = parse_pdf(raw, date_format=date_format, invert=invert, account_type=account_type)
    else:
        text = decode_bytes(raw)
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
        elif not mapping and (activity := parse_activity_export(
                text, date_format=date_format, account_currency=account_currency, registered_kind=registered_kind)):
            result = activity  # Wealthsimple / Questrade activity export, matched by its header names
            if invert:
                for t in result.transactions:
                    t.amount = -t.amount
                result.inverted = True
        elif name.endswith((".csv", ".txt", ".tsv")) or "," in text[:500] or ";" in text[:500]:
            result = parse_csv(text, preset_id=preset_id, mapping=mapping, date_format=date_format, invert=invert,
                               account_type=account_type, account_currency=account_currency)
        else:
            raise ValueError("Unsupported file. Use OFX, QFX, QBO, QIF, CSV or a text-based PDF statement.")
    if result.format != "csv" and preset_id:
        result.preset = preset_id
    _registered_hints(result, filename)
    return result


def _registered_hints(result: ParseResult, filename: str) -> None:
    """Which plan the file is for (from its name, its text or its account column), and type codes printed in PDFs."""
    if result.format == "pdf" and "wealthsimple" in result.text_sample.lower():
        for t in result.transactions:
            code, rest = leading_code(t.description)
            if code:
                t.type_text, t.description = code, rest
    labels = {t.account_label for t in result.transactions if t.account_label}
    if not result.kind_hint and len({suggest_kind(label) for label in labels}) <= 1:  # a mixed file names no plan
        sources = [filename or "", result.text_sample[:1500], " ".join(sorted(labels))]
        result.kind_hint = suggest_kind(*sources)
        result.spousal = result.kind_hint == "rrsp" and is_spousal(*sources)


__all__ = ["ParsedTxn", "ParseResult", "parse_file", "normalize_merchant"]
