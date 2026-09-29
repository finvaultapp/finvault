"""Account recovery (password reset links) and the member's own data export."""
import json
import os
import re
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from .. import config_admin, security
from ..db import get_db
from ..deps import COOKIE_NAME, admin_user, current_user
from ..models import User
from ..services import audit, data_export, notify
from ..services import password_reset as pr
from .auth import _check_password, _require_local_auth

router = APIRouter(tags=["account"])

INVALID_LINK = "This reset link is invalid, already used or expired. Ask for a new one."


def _ip(request: Request) -> str:
    return f"ip|{request.client.host if request.client else '?'}"


# --- Admin: make a reset link -----------------------------------------------------------------------

@router.post("/api/admin/users/{user_id}/password-reset")
def admin_reset_link(user_id: int, request: Request, me: User = Depends(admin_user), db: Session = Depends(get_db)):
    _require_local_auth()
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if not u.is_active:
        raise HTTPException(409, "This member is turned off. Turn them back on first.")
    raw, row = pr.issue(db, u, via="admin", hours=pr.ADMIN_LINK_HOURS, created_by=me)
    audit.record(db, "admin.password_reset_link", request=request, user=me, target=u,
                 hours=pr.ADMIN_LINK_HOURS, link_id=row.id)
    # The admin passes the link on; they never see or choose the password.
    return {"path": pr.link_path(raw), "url": pr.full_link(raw), "expires_at": audit.utc_iso(row.expires_at),
            "hours": pr.ADMIN_LINK_HOURS, "needs_2fa": u.totp_enabled}


# --- Self-service by email ----------------------------------------------------------------------------

@router.get("/api/password-reset/options")
def options():
    # smtp: show "Forgot password?" at all. self_service: the email form works (SMTP and PUBLIC_URL are set).
    return {"local_auth": config_admin.LOCAL_AUTH_ENABLED, "smtp": notify.smtp_configured(),
            "self_service": pr.self_service_available(), "email_link_hours": pr.EMAIL_LINK_HOURS}


class ForgotIn(BaseModel):
    email: str = Field(max_length=255)


@router.post("/api/password-reset/request")
def request_reset(body: ForgotIn, request: Request, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    _require_local_auth()
    if not pr.self_service_available():
        raise HTTPException(409, "Password reset by email isn't set up on this server. Ask your household admin for a reset link.")
    email = body.email.strip().lower()
    ip_key, email_key = _ip(request), f"email|{email}"
    if pr.request_ip_throttle.blocked(ip_key) or pr.request_email_throttle.blocked(email_key):
        raise HTTPException(429, "Too many reset requests. Wait an hour and try again.")
    pr.request_ip_throttle.hit(ip_key)
    pr.request_email_throttle.hit(email_key)
    user = db.scalar(select(User).where(User.email == email)) if re.fullmatch(r"[^@\s]+@[^@\s]+", email) else None
    if user and user.is_active:
        raw, _ = pr.issue(db, user, via="email", hours=pr.EMAIL_LINK_HOURS)
        # Sent after the response, so the time taken doesn't reveal whether the address has an account.
        tasks.add_task(pr.send_reset_email, user.email, raw, user.locale or "en")
        audit.record(db, "auth.password_reset_requested", request=request, user=user)
    else:
        audit.record(db, "auth.password_reset_requested", request=request, email=email,
                     reason="inactive" if user else "unknown_email")
    return {"ok": True}


# --- Using a link -------------------------------------------------------------------------------------

class TokenIn(BaseModel):
    token: str = Field(max_length=200)


def _valid_or_400(db: Session, request: Request, raw: str):
    key = _ip(request)
    if pr.token_ip_throttle.blocked(key):
        raise HTTPException(429, "Too many attempts. Wait 15 minutes and try again.")
    found = pr.find_valid(db, raw)
    if not found:
        pr.token_ip_throttle.hit(key)
        raise HTTPException(400, INVALID_LINK)
    return found


@router.post("/api/password-reset/check")
def check_link(body: TokenIn, request: Request, db: Session = Depends(get_db)):
    _require_local_auth()
    row, user = _valid_or_400(db, request, body.token)
    return {"email": user.email, "needs_2fa": user.totp_enabled, "expires_at": audit.utc_iso(row.expires_at)}


class ResetIn(TokenIn):
    new_password: str = Field(max_length=200)
    code: str = Field(default="", max_length=40)


def _second_factor_ok(db: Session, user: User, code: str) -> bool:
    """A current TOTP code, or an unused recovery code (removed from the list; the caller commits)."""
    code = (code or "").strip()
    if not code:
        return False
    secret = security.decrypt(user.totp_secret)
    if secret and security.verify_totp(secret, code):
        return True
    if user.recovery_codes:
        codes = json.loads(user.recovery_codes)
        h = security.hash_recovery_code(code)
        if h in codes:
            codes.remove(h)
            user.recovery_codes = json.dumps(codes)
            return True
    return False


@router.post("/api/password-reset/complete")
def complete_reset(body: ResetIn, request: Request, response: Response, db: Session = Depends(get_db)):
    _require_local_auth()
    row, user = _valid_or_400(db, request, body.token)
    _check_password(body.new_password)
    if user.totp_enabled:
        key = f"2fa|{user.id}"  # shares the sign-in 2FA budget, so the reset page isn't a second guessing lane
        if security.login_throttle.blocked(key):
            raise HTTPException(429, "Too many attempts. Wait 15 minutes and try again.")
        if not _second_factor_ok(db, user, body.code):
            db.rollback()
            security.login_throttle.hit(key)
            audit.record(db, "auth.password_reset_failed", request=request, user=user, reason="wrong_2fa_code")
            raise HTTPException(401, "That two-factor code didn't work. Enter a current code from your authenticator app, or a recovery code.")
    if not pr.consume(db, row):
        db.rollback()
        raise HTTPException(400, INVALID_LINK)
    user.password_hash = security.hash_password(body.new_password)
    user.token_version += 1  # signs out every existing session
    db.commit()
    security.login_throttle.reset(f"2fa|{user.id}")
    security.email_login_throttle.reset(f"email|{user.email}")
    audit.record(db, "auth.password_reset", request=request, user=user, via=row.via, link_id=row.id)
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


# --- Download all my data -----------------------------------------------------------------------------

@router.get("/api/account/export")
def export_my_data(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    path, summary = data_export.build_zip(db, user)
    audit.record(db, "account.data_exported", request=request, user=user, **summary)
    return FileResponse(path, media_type="application/zip",
                        filename=f"finvault-my-data-{date.today().isoformat()}.zip",
                        background=BackgroundTask(os.unlink, path))
