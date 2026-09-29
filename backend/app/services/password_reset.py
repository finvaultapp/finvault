"""One-time password reset links.

A link carries a random 256-bit token in the URL fragment (/reset-password#token=...), so it never lands in
server access logs or Referer headers. Only the token's SHA-256 is stored. A link works once, expires
(24 hours when an admin makes it, 1 hour when it is emailed), and is cancelled when a newer link is made
for the same member or their password is reset.

Emailed links are built from PUBLIC_URL only, never from the request's Host header, which a client can spoof
to make FinVault email a link that points at someone else's server.
"""
import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import config_admin
from ..models import User
from ..models_account import PasswordResetToken
from ..security import Throttle
from . import audit, notify

log = logging.getLogger("finvault.password_reset")

ADMIN_LINK_HOURS = 24
EMAIL_LINK_HOURS = 1
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").strip().rstrip("/")

# Self-service requests: per address and per client IP. Same response whether or not the address exists.
request_email_throttle = Throttle(limit=3, window_seconds=60 * 60)
request_ip_throttle = Throttle(limit=10, window_seconds=60 * 60)
# Guessing at tokens (check / complete with an unknown token), per client IP.
token_ip_throttle = Throttle(limit=20, window_seconds=15 * 60)

audit.EVENTS.update({
    "admin.password_reset_link": "Password reset link created by admin",
    "auth.password_reset_requested": "Password reset email requested",
    "auth.password_reset": "Password reset with a link",
    "auth.password_reset_failed": "Password reset failed",
    "account.data_exported": "Personal data downloaded",
})


def public_url() -> str:
    url = PUBLIC_URL
    return url if url.startswith(("http://", "https://")) else ""


def self_service_available() -> bool:
    return config_admin.LOCAL_AUTH_ENABLED and notify.smtp_configured() and bool(public_url())


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def link_path(raw: str) -> str:
    return f"/reset-password#token={raw}"


def full_link(raw: str) -> str | None:
    base = public_url()
    return base + link_path(raw) if base else None


def _utc(v: datetime) -> datetime:
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _revoke_open(db: Session, user_id: int, now: datetime) -> None:
    db.execute(update(PasswordResetToken)
               .where(PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None))
               .values(used_at=now).execution_options(synchronize_session=False))


def issue(db: Session, user: User, *, via: str, hours: int, created_by: User | None = None) -> tuple[str, PasswordResetToken]:
    """Make a new link for `user`, cancelling any earlier unused one. Returns the raw token (shown once) and the row."""
    now = datetime.now(timezone.utc)
    _revoke_open(db, user.id, now)
    raw = secrets.token_urlsafe(32)
    row = PasswordResetToken(user_id=user.id, token_hash=hash_token(raw), via=via,
                             created_by=created_by.id if created_by else None,
                             created_at=now, expires_at=now + timedelta(hours=hours))
    db.add(row)
    db.commit()
    return raw, row


def find_valid(db: Session, raw: str) -> tuple[PasswordResetToken, User] | None:
    if not raw or len(raw) > 200:
        return None
    row = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(raw)))
    if row is None or row.used_at is not None or _utc(row.expires_at) <= datetime.now(timezone.utc):
        return None
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    return row, user


def consume(db: Session, row: PasswordResetToken) -> bool:
    """Mark the link used, atomically: of two simultaneous uses, only one wins. Caller commits."""
    now = datetime.now(timezone.utc)
    n = db.execute(update(PasswordResetToken)
                   .where(PasswordResetToken.id == row.id, PasswordResetToken.used_at.is_(None),
                          PasswordResetToken.expires_at > now)
                   .values(used_at=now).execution_options(synchronize_session=False)).rowcount
    if n == 1:
        _revoke_open(db, row.user_id, now)
    return n == 1


_EMAIL = {
    "en": ("Reset your FinVault password",
           "Someone asked to reset the password for this FinVault account.\n\n"
           "Choose a new password here (the link works once, for {hours} hour):\n{link}\n\n"
           "If it wasn't you, ignore this email. Your password stays the same.\n"),
    "fr": ("Réinitialisez votre mot de passe FinVault",
           "Quelqu'un a demandé la réinitialisation du mot de passe de ce compte FinVault.\n\n"
           "Choisissez un nouveau mot de passe ici (le lien fonctionne une seule fois, pendant {hours} heure) :\n{link}\n\n"
           "Si ce n'était pas vous, ignorez ce courriel. Votre mot de passe reste le même.\n"),
}


def send_reset_email(to: str, raw: str, locale: str = "en") -> None:
    link = full_link(raw)
    if not link:
        return
    subject, body = _EMAIL.get(locale, _EMAIL["en"])
    try:
        notify.send_email(to, subject, body.format(hours=EMAIL_LINK_HOURS, link=link))
    except Exception as exc:  # noqa: BLE001 - never tell the requester whether sending worked
        log.warning("password reset email failed: %s", exc)
