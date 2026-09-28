"""Environment settings for backups, single sign-on and the audit log. Everything is off by default."""
import os
from pathlib import Path

from .config import DATA_DIR, _bool

# --- Encrypted backups -----------------------------------------------------------
# The admin turns backups on and sets the passphrase in the app; this only sets the default.
BACKUP_ENABLED = _bool("BACKUP_ENABLED", False)
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", str(DATA_DIR / "backups"))).resolve()
BACKUP_KEEP = int(os.environ.get("BACKUP_KEEP", "14"))
# Nightly run starts at the first hourly check at or after this local hour.
BACKUP_HOUR = int(os.environ.get("BACKUP_HOUR", "3"))
BACKUP_S3_ENDPOINT = os.environ.get("BACKUP_S3_ENDPOINT", "").rstrip("/")
BACKUP_S3_BUCKET = os.environ.get("BACKUP_S3_BUCKET", "")
BACKUP_S3_ACCESS_KEY = os.environ.get("BACKUP_S3_ACCESS_KEY", "")
BACKUP_S3_SECRET_KEY = os.environ.get("BACKUP_S3_SECRET_KEY", "")
BACKUP_S3_PREFIX = os.environ.get("BACKUP_S3_PREFIX", "finvault/").lstrip("/")
BACKUP_S3_REGION = os.environ.get("BACKUP_S3_REGION", "us-east-1")

# --- Single sign-on (OpenID Connect) ---------------------------------------------
OIDC_ENABLED = _bool("OIDC_ENABLED", False)
OIDC_PROVIDER_NAME = os.environ.get("OIDC_PROVIDER_NAME", "SSO")
OIDC_DISCOVERY_URL = os.environ.get("OIDC_DISCOVERY_URL", "")
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")
# Empty means <origin of the request>/api/auth/oidc/callback.
OIDC_REDIRECT_URI = os.environ.get("OIDC_REDIRECT_URI", "")
OIDC_ALLOW_SIGNUP = _bool("OIDC_ALLOW_SIGNUP", False)
OIDC_SCOPES = os.environ.get("OIDC_SCOPES", "openid email profile")
# Only turn this off if your provider never sends email_verified and you control every account on it.
OIDC_REQUIRE_VERIFIED_EMAIL = _bool("OIDC_REQUIRE_VERIFIED_EMAIL", True)
LOCAL_AUTH_ENABLED = _bool("LOCAL_AUTH_ENABLED", True)

# --- Audit log ---------------------------------------------------------------------
AUDIT_RETENTION_DAYS = int(os.environ.get("AUDIT_RETENTION_DAYS", "365"))


def oidc_configured() -> bool:
    return OIDC_ENABLED and bool(OIDC_DISCOVERY_URL and OIDC_CLIENT_ID)


def s3_configured() -> bool:
    return bool(BACKUP_S3_ENDPOINT and BACKUP_S3_BUCKET and BACKUP_S3_ACCESS_KEY and BACKUP_S3_SECRET_KEY)
