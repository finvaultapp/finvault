import json
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config, config_admin, security, settings_store
from ..db import get_db
from ..deps import COOKIE_NAME, current_user
from ..models import Invite, User
from ..services import audit
from ..services.ledger import seed_categories

router = APIRouter(prefix="/api/auth", tags=["auth"])


def user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "is_admin": u.is_admin, "base_currency": u.base_currency,
            "totp_enabled": u.totp_enabled, "ai_opt_in": u.ai_opt_in, "locale": u.locale or "en"}


def _set_session(response: Response, user: User) -> None:
    response.set_cookie(COOKIE_NAME, security.create_token(user.id, user.token_version), httponly=True,
                        samesite="lax", secure=config.COOKIE_SECURE, max_age=config.SESSION_HOURS * 3600, path="/")


def _require_local_auth() -> None:
    if not config_admin.LOCAL_AUTH_ENABLED:
        raise HTTPException(403, "Password sign-in is turned off on this server. Use single sign-on.")


def _check_password(pw: str) -> None:
    if len(pw) < 10:
        raise HTTPException(422, "Use at least 10 characters for your password.")


@router.get("/status")
def status(db: Session = Depends(get_db)):
    has_users = (db.scalar(select(func.count(User.id))) or 0) > 0
    return {"needs_setup": not has_users, "registration_mode": settings_store.get(db, "registration_mode"),
            "ai_enabled": bool(settings_store.get(db, "ai_enabled")) or bool(settings_store.get(db, "ai_allow_personal_keys")),
            "local_auth_enabled": config_admin.LOCAL_AUTH_ENABLED, "oidc": _oidc_status()}


def _oidc_status() -> dict:
    from .oidc import public_status
    return public_status()


class RegisterIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=200)
    name: str = Field(default="", max_length=120)
    invite_code: str | None = None
    base_currency: str = Field(default=config.DEFAULT_BASE_CURRENCY, min_length=3, max_length=3)
    locale: str = Field(default="en", pattern="^(en|fr)$")


@router.post("/register")
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    _require_local_auth()
    email = body.email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+", email):
        raise HTTPException(422, "Enter a valid email address.")
    _check_password(body.password)
    first = (db.scalar(select(func.count(User.id))) or 0) == 0
    invite = None
    if not first:
        mode = settings_store.get(db, "registration_mode")
        if mode == "closed":
            raise HTTPException(403, "Registration is closed. Ask your admin to create an account for you.")
        if mode == "invite":
            code = (body.invite_code or "").strip()
            invite = db.scalar(select(Invite).where(Invite.code == code, Invite.used_by.is_(None))) if code else None
            if not invite or (invite.expires_at and invite.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc)):
                raise HTTPException(403, "A valid invite code is required to register.")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists.")
    user = User(email=email, name=body.name.strip(), password_hash=security.hash_password(body.password),
                is_admin=first, base_currency=body.base_currency.upper(), locale=body.locale)
    db.add(user)
    db.flush()
    if invite:
        invite.used_by = user.id
    seed_categories(db, user)
    db.commit()
    audit.record(db, "admin.member_created", request=request, user=user, target=user, via="register",
                 is_admin=user.is_admin)
    _set_session(response, user)
    return user_out(user)


class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    _require_local_auth()
    email = body.email.strip().lower()[:255]
    key = f"{request.client.host if request.client else '?'}|{email}"
    email_key = f"email|{email}"
    if security.login_throttle.blocked(key) or security.email_login_throttle.blocked(email_key):
        audit.record(db, "auth.login_failed", request=request, email=email, reason="throttled")
        raise HTTPException(429, "Too many attempts. Wait 15 minutes and try again.")
    user = db.scalar(select(User).where(User.email == email))
    if not user or not security.verify_password(body.password, user.password_hash) or not user.is_active:
        security.login_throttle.hit(key)
        security.email_login_throttle.hit(email_key)
        reason = "unknown_email" if not user else ("inactive" if not user.is_active else "wrong_password")
        audit.record(db, "auth.login_failed", request=request, user=user, email=email, reason=reason)
        raise HTTPException(401, "Email or password is incorrect.")
    if user.totp_enabled:
        return {"requires_2fa": True, "challenge": security.create_token(user.id, user.token_version, "2fa", minutes=5)}
    security.login_throttle.reset(key)
    security.email_login_throttle.reset(email_key)
    audit.record(db, "auth.login", request=request, user=user, method="password")
    _set_session(response, user)
    return {"requires_2fa": False, "user": user_out(user)}


class TwoFactorIn(BaseModel):
    challenge: str
    code: str


@router.post("/login/2fa")
def login_2fa(body: TwoFactorIn, request: Request, response: Response, db: Session = Depends(get_db)):
    _require_local_auth()
    payload = security.decode_token(body.challenge, "2fa")
    if not payload:
        raise HTTPException(401, "Sign-in expired. Enter your password again.")
    user = db.get(User, int(payload["sub"]))
    key = f"2fa|{payload['sub']}"
    if not user or security.login_throttle.blocked(key):
        raise HTTPException(429, "Too many attempts. Wait 15 minutes and try again.")
    secret = security.decrypt(user.totp_secret)
    ok = bool(secret) and security.verify_totp(secret, body.code)
    if not ok and user.recovery_codes:
        codes = json.loads(user.recovery_codes)
        h = security.hash_recovery_code(body.code)
        if h in codes:
            codes.remove(h)
            user.recovery_codes = json.dumps(codes)
            db.commit()
            ok = True
    if not ok:
        security.login_throttle.hit(key)
        audit.record(db, "auth.login_failed", request=request, user=user, reason="wrong_2fa_code")
        raise HTTPException(401, "That code didn't work. Check your authenticator app's time is correct.")
    security.login_throttle.reset(key)
    audit.record(db, "auth.login", request=request, user=user, method="password+2fa")
    _set_session(response, user)
    return {"user": user_out(user)}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.post("/logout-all")
def logout_all(request: Request, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.token_version += 1
    db.commit()
    audit.record(db, "auth.logout_all", request=request, user=user)
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


class ProfileIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    base_currency: str | None = Field(default=None, min_length=3, max_length=3)
    ai_opt_in: bool | None = None
    locale: str | None = Field(default=None, pattern="^(en|fr)$")


@router.patch("/me")
def update_me(body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.name is not None:
        user.name = body.name.strip()
    if body.base_currency:
        user.base_currency = body.base_currency.upper()
    if body.ai_opt_in is not None:
        user.ai_opt_in = body.ai_opt_in
    if body.locale:
        user.locale = body.locale
    db.commit()
    return user_out(user)


class PasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(max_length=200)


@router.post("/password")
def change_password(body: PasswordIn, request: Request, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not security.verify_password(body.current_password, user.password_hash):
        raise HTTPException(401, "Current password is incorrect.")
    _check_password(body.new_password)
    user.password_hash = security.hash_password(body.new_password)
    user.token_version += 1  # sign out other devices
    db.commit()
    audit.record(db, "auth.password_changed", request=request, user=user)
    _set_session(response, user)
    return {"ok": True}


@router.post("/2fa/setup")
def totp_setup(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.totp_enabled:
        raise HTTPException(409, "Two-factor login is already on.")
    secret = security.new_totp_secret()
    user.totp_secret = security.encrypt(secret)
    db.commit()
    uri = security.totp_uri(secret, user.email)
    return {"secret": secret, "uri": uri, "qr_svg": security.totp_qr_svg(uri)}


class CodeIn(BaseModel):
    code: str
    password: str | None = None


@router.post("/2fa/enable")
def totp_enable(body: CodeIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    secret = security.decrypt(user.totp_secret)
    if not secret or not security.verify_totp(secret, body.code):
        raise HTTPException(400, "That code didn't match. Try the next one your app shows.")
    codes, hashes = security.new_recovery_codes()
    user.totp_enabled = True
    user.recovery_codes = json.dumps(hashes)
    db.commit()
    audit.record(db, "auth.2fa_enabled", request=request, user=user)
    return {"recovery_codes": codes}


@router.post("/2fa/disable")
def totp_disable(body: CodeIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not body.password or not security.verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Password is incorrect.")
    secret = security.decrypt(user.totp_secret)
    if not secret or not security.verify_totp(secret, body.code):
        raise HTTPException(400, "That code didn't match.")
    user.totp_enabled = False
    user.totp_secret = None
    user.recovery_codes = None
    db.commit()
    audit.record(db, "auth.2fa_disabled", request=request, user=user)
    return {"ok": True}
