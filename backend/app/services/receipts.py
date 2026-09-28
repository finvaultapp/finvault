"""Receipt files attached to transactions, with optional OCR done on this server.

Files are stored under <data>/receipts/<user id>/ with random names. OCR uses
Tesseract when it is installed (the Docker image includes it) and the admin has
turned it on; text PDFs are read directly without OCR.
"""
import logging
import re
import secrets
import shutil
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from .. import config, settings_store
from ..db import SessionLocal
from ..models import Attachment

log = logging.getLogger("finvault.receipts")
TYPES = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/heic": ".heic",
    "application/pdf": ".pdf",
}
MAX_BYTES = 10 * 1024 * 1024


def folder(user_id: int) -> Path:
    p = config.DATA_DIR / "receipts" / str(user_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def sniff_type(raw: bytes, declared: str | None) -> str | None:
    """Trust the file's bytes, not the browser's label."""
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw.startswith(b"%PDF"):
        return "application/pdf"
    if raw[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftypmsf1"):
        return "image/heic"
    return None


def save(db: Session, user_id: int, transaction_id: int, filename: str, raw: bytes, declared: str | None) -> Attachment:
    if len(raw) > MAX_BYTES:
        raise ValueError("Receipts can be up to 10 MB.")
    ctype = sniff_type(raw, declared)
    if not ctype:
        raise ValueError("Use a JPG, PNG, WebP, HEIC photo or a PDF.")
    stored = secrets.token_hex(16) + TYPES[ctype]
    (folder(user_id) / stored).write_bytes(raw)
    ocr_on = bool(settings_store.get(db, "ocr_enabled"))
    a = Attachment(user_id=user_id, transaction_id=transaction_id, filename=Path(filename or "receipt").name[:255],
                   content_type=ctype, size=len(raw), stored_name=stored, ocr_status="pending" if ocr_on else "none")
    db.add(a)
    db.commit()
    return a


def file_path(a: Attachment) -> Path:
    return folder(a.user_id) / a.stored_name


def delete(db: Session, a: Attachment) -> None:
    try:
        file_path(a).unlink(missing_ok=True)
    except OSError:
        pass
    db.delete(a)
    db.commit()


def ocr_available() -> bool:
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return shutil.which("tesseract") is not None


def _extract_text(path: Path, ctype: str) -> str:
    if ctype == "application/pdf":
        from pypdf import PdfReader
        text = "\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages[:5])
        if text.strip():
            return text
        raise ValueError("This PDF is a scan without text; attach it as a photo to read it.")
    import pytesseract
    from PIL import Image
    with Image.open(path) as img:
        return pytesseract.image_to_string(img, lang="eng+fra")


TOTAL_RE = re.compile(r"(?im)^(?:.*\b(total|montant|amount due|balance due|à payer)\b.*?)(\d{1,5}[.,]\d{2})\s*$")


def guess_total(text: str) -> float | None:
    """Best guess at the receipt total, to compare with the transaction amount."""
    hits = [m.group(2) for m in TOTAL_RE.finditer(text or "")]
    if not hits:
        return None
    return float(Decimal(hits[-1].replace(",", ".")))


def run_pending() -> int:
    """Called from the background loop."""
    done = 0
    with SessionLocal() as db:
        if not settings_store.get(db, "ocr_enabled"):
            return 0
        for a in db.query(Attachment).filter(Attachment.ocr_status == "pending").limit(10):
            try:
                if a.content_type != "application/pdf" and not ocr_available():
                    raise ValueError("Tesseract isn't installed on this server.")
                a.ocr_text = _extract_text(file_path(a), a.content_type)[:20000]
                a.ocr_status = "done"
                done += 1
            except Exception as exc:  # noqa: BLE001
                a.ocr_status = "failed"
                a.ocr_text = str(exc)[:500]
                log.warning("OCR failed for attachment %s: %s", a.id, exc)
            db.commit()
    return done
