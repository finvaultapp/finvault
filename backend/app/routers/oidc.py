"""Single sign-on with any standard OpenID Connect provider (Authentik, Pocket ID, Keycloak, ...).

Two-factor note: when a member who has TOTP turned on signs in through the provider, FinVault does not
ask for their TOTP code again. The provider is trusted to do its own multi-factor check; turn MFA on there.
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config, config_admin, settings_store
from ..db import get_db
from ..models import Invite, User
from ..models_admin import OidcIdentity
from ..services import audit
from ..services import oidc as op
from ..services.ledger import seed_categories
from .auth import _set_session

log = logging.getLogger("finvault.oidc")
router = APIRouter(prefix="/api/auth/oidc", tags=["auth"])

FLOW_COOKIE = "fv_oidc"
FLOW_PATH = "/api/auth/oidc"
FLOW_MINUTES = 10


def public_status() -> dict:
    return {"enabled": config_admin.oidc_configured(), "provider_name": config_admin.OIDC_PROVIDER_NAME,
            "login_url": f"{FLOW_PATH}/login", "local_auth_enabled": config_admin.LOCAL_AUTH_ENABLED}


def _redirect_uri(request: Request) -> str:
    if config_admin.OIDC_REDIRECT_URI:
        return config_admin.OIDC_REDIRECT_URI
    return str(request.base_url).rstrip("/") + f"{FLOW_PATH}/callback"


def _safe_next(nxt: str | None) -> str:
    if not nxt or not nxt.startswith("/") or nxt.startswith("//") or "\\" in nxt or nxt.startswith("/api/"):
        return "/"
    return nxt[:500]


def _fail(db: Session, request: Request, code: str, message: str = "", email: str = "") -> RedirectResponse:
    log.warning("single sign-on failed: %s %s", code, message)
    audit.record(db, "auth.sso_failed", request=request, email=email, reason=code)
    resp = RedirectResponse(f"/login?sso_error={code}", status_code=302)
    resp.delete_cookie(FLOW_COOKIE, path=FLOW_PATH)
    return resp


@router.get("/login")
def oidc_login(request: Request, next: str | None = None, invite: str | None = None, db: Session = Depends(get_db)):
    if not config_admin.oidc_configured():
        return RedirectResponse("/login?sso_error=disabled", status_code=302)
    flow = op.new_flow()
    redirect_uri = _redirect_uri(request)
    try:
        url = op.authorize_url(flow, redirect_uri)
    except op.OidcError as exc:
        return _fail(db, request, exc.code, str(exc))
    now = datetime.now(timezone.utc)
    cookie = jwt.encode({"typ": "oidc_flow", "state": flow["state"], "nonce": flow["nonce"], "verifier": flow["verifier"],
                         "redirect_uri": redirect_uri, "next": _safe_next(next), "invite": (invite or "")[:64],
                         "iat": now, "exp": now + timedelta(minutes=FLOW_MINUTES)}, config.SECRET_KEY, algorithm="HS256")
    resp = RedirectResponse(url, status_code=302)
    # Lax is needed: the provider sends the browser back with a top-level GET from its own site.
    resp.set_cookie(FLOW_COOKIE, cookie, max_age=FLOW_MINUTES * 60, httponly=True, samesite="lax",
                    secure=config.COOKIE_SECURE, path=FLOW_PATH)
    return resp


def _read_flow(request: Request) -> dict | None:
    raw = request.cookies.get(FLOW_COOKIE)
    if not raw:
        return None
    try:
        flow = jwt.decode(raw, config.SECRET_KEY, algorithms=["HS256"], options={"require": ["exp"]})
    except jwt.PyJWTError:
        return None
    return flow if flow.get("typ") == "oidc_flow" else None


def _signup(db: Session, ident: dict, invite_code: str) -> tuple[User | None, str]:
    """Create a member for a new provider account, following the registration mode. Returns (user, error code)."""
    first = (db.scalar(select(func.count(User.id))) or 0) == 0
    invite = None
    if not first:
        mode = settings_store.get(db, "registration_mode")
        if mode == "closed":
            return None, "signup_closed"
        if mode == "invite":
            invite = db.scalar(select(Invite).where(Invite.code == invite_code, Invite.used_by.is_(None))) if invite_code else None
            if not invite or (invite.expires_at and invite.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc)):
                return None, "invite_required"
    # "!" is never a valid bcrypt hash, so this account has no usable password until the member sets one.
    user = User(email=ident["email"], name=(ident["name"] or "")[:120], password_hash="!oidc", is_admin=first,
                base_currency=config.DEFAULT_BASE_CURRENCY)
    db.add(user)
    db.flush()
    if invite:
        invite.used_by = user.id
    seed_categories(db, user)
    return user, ""


@router.get("/callback")
def oidc_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None,
                  db: Session = Depends(get_db)):
    if not config_admin.oidc_configured():
        return RedirectResponse("/login?sso_error=disabled", status_code=302)
    flow = _read_flow(request)
    if error:
        return _fail(db, request, "provider_error", error[:100])
    if not flow or not state or not secrets.compare_digest(str(flow.get("state", "")).encode(), state.encode()):
        return _fail(db, request, "bad_state", "state missing or different")
    if not code:
        return _fail(db, request, "provider_error", "no code")
    try:
        tokens = op.exchange_code(code, flow["verifier"], flow["redirect_uri"])
        claims = op.validate_id_token(tokens["id_token"], flow["nonce"])
        ident = op.identity(tokens, claims)
    except op.OidcError as exc:
        return _fail(db, request, exc.code, str(exc))

    created = False
    link = db.scalar(select(OidcIdentity).where(OidcIdentity.issuer == ident["issuer"], OidcIdentity.subject == ident["sub"]))
    user = db.get(User, link.user_id) if link else None
    if user is None:
        if not ident["email"]:
            return _fail(db, request, "no_email", "the provider sent no email")
        if config_admin.OIDC_REQUIRE_VERIFIED_EMAIL and not ident["email_verified"]:
            return _fail(db, request, "email_not_verified", email=ident["email"])
        user = db.scalar(select(User).where(User.email == ident["email"]))
        if user is None:
            if not config_admin.OIDC_ALLOW_SIGNUP:
                return _fail(db, request, "no_account", email=ident["email"])
            user, err = _signup(db, ident, flow.get("invite") or "")
            if err:
                db.rollback()
                return _fail(db, request, err, email=ident["email"])
            created = True
        elif db.scalar(select(OidcIdentity.id).where(OidcIdentity.user_id == user.id,
                                                     OidcIdentity.issuer == ident["issuer"])):
            # This member is already linked to a different account at this provider. Matching by email again
            # would let whoever holds that address at the provider now (a renamed or recycled account) in.
            return _fail(db, request, "already_linked", email=ident["email"])
        link = OidcIdentity(user_id=user.id, issuer=ident["issuer"], subject=ident["sub"])
        db.add(link)
    if not user.is_active:
        db.rollback()
        return _fail(db, request, "inactive", email=user.email)
    link.last_login_at = datetime.now(timezone.utc)
    db.commit()
    if created:
        audit.record(db, "admin.member_created", request=request, user=user, target=user, via="sso")
    audit.record(db, "auth.sso_login", request=request, user=user, provider=config_admin.OIDC_PROVIDER_NAME,
                 skipped_2fa=bool(user.totp_enabled))
    resp = RedirectResponse(flow.get("next") or "/", status_code=302)
    resp.delete_cookie(FLOW_COOKIE, path=FLOW_PATH)
    _set_session(resp, user)
    return resp
