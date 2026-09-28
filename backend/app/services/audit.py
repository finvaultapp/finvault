"""Security audit log.

Call `record()` after the action it describes has been committed (or, for failures, before raising).
It commits its own row. Never pass passwords, codes, tokens or secret setting values in `detail`:
callers pass key names and flags only, and `record()` drops anything whose name looks secret.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import delete
from sqlalchemy.orm import Session

from .. import config_admin
from ..models_admin import AuditEvent

log = logging.getLogger("finvault.audit")

# Event type -> English label (the frontend translates the label).
EVENTS = {
    "auth.login": "Signed in",
    "auth.login_failed": "Sign-in failed",
    "auth.sso_login": "Signed in with single sign-on",
    "auth.sso_failed": "Single sign-on failed",
    "auth.logout_all": "Signed out everywhere",
    "auth.password_changed": "Password changed",
    "auth.2fa_enabled": "Two-factor turned on",
    "auth.2fa_disabled": "Two-factor turned off",
    "admin.2fa_reset": "Two-factor reset by admin",
    "admin.settings_changed": "Server settings changed",
    "admin.member_created": "Member created",
    "admin.member_deleted": "Member deleted",
    "admin.member_changed": "Member role or status changed",
    "admin.invite_created": "Invite created",
    "backup.started": "Backup started",
    "backup.completed": "Backup completed",
    "backup.failed": "Backup failed",
    "backup.settings_changed": "Backup settings changed",
    "backup.downloaded": "Backup downloaded",
    "sync.connected": "Bank sync connected",
    "sync.disconnected": "Bank sync disconnected",
    "ai.key_connected": "AI key connected",
    "ai.key_removed": "AI key removed",
}

_SECRETISH = ("password", "passphrase", "secret", "token", "code", "api_key", "key_value")


def utc_iso(value: datetime | None) -> str | None:
    """SQLite hands back naive datetimes; they are stored in UTC, so say so in the output."""
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def client_ip(request: Request | None) -> str:
    if request is None or request.client is None:
        return ""
    return (request.client.host or "")[:64]


def _clean(detail: dict) -> dict:
    out = {}
    for k, v in detail.items():
        if any(s in k.lower() for s in _SECRETISH):
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v[:300] if isinstance(v, str) else v
        elif isinstance(v, (list, tuple)):
            out[k] = [str(x)[:100] for x in v][:50]
    return out


def record(db: Session, event: str, *, request: Request | None = None, user=None, email: str = "",
           target=None, **detail) -> None:
    """Write one audit row. `user` is the actor, `target` the member acted on. Failures are logged, never raised."""
    try:
        row = AuditEvent(
            event=event,
            user_id=getattr(user, "id", None),
            email=(email or getattr(user, "email", "") or "")[:255],
            target_user_id=getattr(target, "id", None),
            target_email=(getattr(target, "email", "") or "")[:255],
            ip=client_ip(request),
            detail=json.dumps(_clean(detail)),
        )
        db.add(row)
        db.commit()
    except Exception:  # noqa: BLE001 - auditing must never break the action itself
        log.exception("could not write audit event %s", event)
        db.rollback()


def prune(db: Session, days: int | None = None) -> int:
    days = config_admin.AUDIT_RETENTION_DAYS if days is None else days
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    n = db.execute(delete(AuditEvent).where(AuditEvent.created_at < cutoff)).rowcount or 0
    db.commit()
    return n
