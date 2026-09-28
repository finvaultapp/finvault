"""Runtime configuration, read once from environment variables."""
import os
import secrets
from pathlib import Path


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


DATA_DIR = Path(os.environ.get("FINVAULT_DATA_DIR", "./data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR / 'finvault.db'}")


def _load_secret_key() -> str:
    """Use SECRET_KEY if given, otherwise generate one and keep it in the data volume."""
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    path = DATA_DIR / "secret.key"
    if path.exists():
        return path.read_text().strip()
    key = secrets.token_urlsafe(48)
    path.write_text(key)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return key


SECRET_KEY = _load_secret_key()
SESSION_HOURS = int(os.environ.get("SESSION_HOURS", "12"))
# Set to false only when serving over plain http on a trusted LAN.
COOKIE_SECURE = _bool("COOKIE_SECURE", False)
ALLOW_PRIVATE_OUTBOUND_URLS = _bool("ALLOW_PRIVATE_OUTBOUND_URLS", False)

# open | invite | closed. The very first account can always be created and becomes admin.
DEFAULT_REGISTRATION_MODE = os.environ.get("REGISTRATION_MODE", "invite")
DEFAULT_BASE_CURRENCY = os.environ.get("DEFAULT_CURRENCY", "CAD").upper()

# Optional bank sync. Everything is off unless credentials are supplied.
BANK_SYNC_ENABLED = _bool("BANK_SYNC_ENABLED", False)
GOCARDLESS_SECRET_ID = os.environ.get("GOCARDLESS_SECRET_ID", "")
GOCARDLESS_SECRET_KEY = os.environ.get("GOCARDLESS_SECRET_KEY", "")
PLUGGY_CLIENT_ID = os.environ.get("PLUGGY_CLIENT_ID", "")
PLUGGY_CLIENT_SECRET = os.environ.get("PLUGGY_CLIENT_SECRET", "")
SIMPLEFIN_ENABLED = _bool("SIMPLEFIN_ENABLED", False)
SYNC_INTERVAL_HOURS = int(os.environ.get("SYNC_INTERVAL_HOURS", "12"))

# Optional AI chat. Off by default; admins can also toggle it in the UI.
AI_ENABLED = _bool("AI_ENABLED", False)
AI_BASE_URL = os.environ.get("AI_BASE_URL", "http://ollama:11434/v1")
AI_MODEL = os.environ.get("AI_MODEL", "llama3.1")
AI_API_KEY = os.environ.get("AI_API_KEY", "")

# Exchange-rate fetching from the ECB via frankfurter.app (sends only currency codes).
FX_FETCH_ENABLED = _bool("FX_FETCH_ENABLED", False)
FX_API_URL = os.environ.get("FX_API_URL", "https://api.frankfurter.app")

STATIC_DIR = Path(os.environ.get("FINVAULT_STATIC_DIR", Path(__file__).resolve().parent.parent / "static"))

# Watched import folder (mount your NAS share here). Off until an admin enables it.
IMPORT_WATCH_DIR = Path(os.environ.get("IMPORT_WATCH_DIR", str(DATA_DIR / "inbox"))).resolve()
FOLDER_IMPORT_ENABLED = _bool("FOLDER_IMPORT_ENABLED", False)

# Receipt OCR with Tesseract on this server. Off by default; the Docker image ships Tesseract.
OCR_ENABLED = _bool("OCR_ENABLED", False)

# Email for bill reminders (optional). ntfy needs no server config.
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "")
SMTP_STARTTLS = _bool("SMTP_STARTTLS", True)
