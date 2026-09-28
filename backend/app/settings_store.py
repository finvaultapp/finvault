"""Server-wide settings editable by admins. Environment variables provide the defaults."""
import json
import time

from sqlalchemy.orm import Session

from . import config
from .models import AppSetting

DEFAULTS = {
    "registration_mode": config.DEFAULT_REGISTRATION_MODE,
    "ai_enabled": config.AI_ENABLED,
    "ai_base_url": config.AI_BASE_URL,
    "ai_model": config.AI_MODEL,
    "ai_max_transactions": 300,
    "ai_allow_personal_keys": False,
    "bank_sync_enabled": config.BANK_SYNC_ENABLED,
    "simplefin_enabled": config.SIMPLEFIN_ENABLED,
    "fx_fetch_enabled": config.FX_FETCH_ENABLED,
    "folder_import_enabled": config.FOLDER_IMPORT_ENABLED,
    "ocr_enabled": config.OCR_ENABLED,
}
# Stored encrypted and never returned to the browser.
SECRET_KEYS = {"ai_api_key"}


def get(db: Session, key: str):
    row = db.get(AppSetting, key)
    if row is None:
        if key == "ai_api_key":
            return config.AI_API_KEY
        return DEFAULTS.get(key)
    value = json.loads(row.value)
    if key in SECRET_KEYS:
        from .security import decrypt
        return decrypt(value) or ""
    return value


def set(db: Session, key: str, value) -> None:
    if key in SECRET_KEYS:
        from .security import encrypt
        value = encrypt(value) if value else ""
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=json.dumps(value)))
    else:
        row.value = json.dumps(value)


def acquire_lock(db: Session, key: str, ttl_seconds: int) -> bool:
    """Best-effort cross-process lease stored in app_settings."""
    lock_key = f"lock:{key}"
    now = time.time()
    row = db.get(AppSetting, lock_key)
    if row is not None:
        try:
            expires = float(json.loads(row.value))
        except (TypeError, ValueError, json.JSONDecodeError):
            expires = 0
        if expires > now:
            return False
        row.value = json.dumps(now + ttl_seconds)
    else:
        db.add(AppSetting(key=lock_key, value=json.dumps(now + ttl_seconds)))
    db.commit()
    return True


def public(db: Session) -> dict:
    out = {k: get(db, k) for k in DEFAULTS}
    out["ai_api_key_set"] = bool(get(db, "ai_api_key"))
    return out
