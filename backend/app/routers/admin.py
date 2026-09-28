import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import security, settings_store
from ..db import get_db
from ..deps import admin_user
from ..models import Account, Invite, Transaction, User
from ..services import receipts
from ..services.ai import is_local_url
from ..services.ledger import seed_categories

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
def list_users(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Transaction.user_id, func.count(Transaction.id)).group_by(Transaction.user_id)).all())
    accts = dict(db.execute(select(Account.user_id, func.count(Account.id)).group_by(Account.user_id)).all())
    return [{"id": u.id, "email": u.email, "name": u.name, "is_admin": u.is_admin, "is_active": u.is_active,
             "totp_enabled": u.totp_enabled, "created_at": u.created_at.isoformat(),
             "transactions": counts.get(u.id, 0), "accounts": accts.get(u.id, 0)}
            for u in db.scalars(select(User).order_by(User.created_at))]


class NewUserIn(BaseModel):
    email: str
    name: str = ""
    password: str = Field(min_length=10)
    is_admin: bool = False


@router.post("/users")
def create_user(body: NewUserIn, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists.")
    u = User(email=email, name=body.name, password_hash=security.hash_password(body.password), is_admin=body.is_admin)
    db.add(u)
    db.flush()
    seed_categories(db, u)
    db.commit()
    return {"id": u.id}


class UserPatch(BaseModel):
    is_admin: bool | None = None
    is_active: bool | None = None


def _admins_left(db: Session, excluding: int) -> int:
    return db.scalar(select(func.count(User.id)).where(User.is_admin.is_(True), User.is_active.is_(True), User.id != excluding)) or 0


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserPatch, me: User = Depends(admin_user), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    removing_admin = (body.is_admin is False and u.is_admin) or (body.is_active is False and u.is_admin)
    if removing_admin and _admins_left(db, u.id) == 0:
        raise HTTPException(409, "There must be at least one active admin.")
    if body.is_admin is not None:
        u.is_admin = body.is_admin
    if body.is_active is not None:
        u.is_active = body.is_active
        if not body.is_active:
            u.token_version += 1
    db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/reset-2fa")
def reset_2fa(user_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    u.totp_enabled, u.totp_secret, u.recovery_codes = False, None, None
    u.token_version += 1
    db.commit()
    return {"ok": True}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, me: User = Depends(admin_user), db: Session = Depends(get_db)):
    if user_id == me.id:
        raise HTTPException(409, "You can't delete your own account here.")
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.is_admin and _admins_left(db, u.id) == 0:
        raise HTTPException(409, "There must be at least one active admin.")
    tx_ids = list(db.scalars(select(Transaction.id).where(Transaction.user_id == u.id)))
    receipts.unlink_for_transactions(db, tx_ids)
    db.delete(u)
    db.commit()
    return {"ok": True}


@router.get("/invites")
def list_invites(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    return [{"id": i.id, "code": i.code, "note": i.note, "used": i.used_by is not None,
             "expires_at": i.expires_at.isoformat() if i.expires_at else None, "created_at": i.created_at.isoformat()}
            for i in db.scalars(select(Invite).order_by(Invite.created_at.desc()))]


class InviteIn(BaseModel):
    note: str = ""
    days: int = Field(default=7, ge=1, le=90)


@router.post("/invites")
def create_invite(body: InviteIn, me: User = Depends(admin_user), db: Session = Depends(get_db)):
    inv = Invite(code=secrets.token_urlsafe(9), note=body.note[:200], created_by=me.id,
                 expires_at=datetime.now(timezone.utc) + timedelta(days=body.days))
    db.add(inv)
    db.commit()
    return {"id": inv.id, "code": inv.code}


@router.delete("/invites/{invite_id}")
def delete_invite(invite_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    inv = db.get(Invite, invite_id)
    if inv:
        db.delete(inv)
        db.commit()
    return {"ok": True}


@router.get("/settings")
def get_settings(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    s = settings_store.public(db)
    s["ai_endpoint_is_local"] = is_local_url(s["ai_base_url"] or "")
    return s


class SettingsIn(BaseModel):
    registration_mode: str | None = Field(default=None, pattern="^(open|invite|closed)$")
    ai_enabled: bool | None = None
    ai_base_url: str | None = None
    ai_model: str | None = None
    ai_api_key: str | None = None
    ai_max_transactions: int | None = Field(default=None, ge=0, le=5000)
    ai_allow_personal_keys: bool | None = None
    folder_import_enabled: bool | None = None
    ocr_enabled: bool | None = None
    bank_sync_enabled: bool | None = None
    simplefin_enabled: bool | None = None
    fx_fetch_enabled: bool | None = None


@router.patch("/settings")
def update_settings(body: SettingsIn, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    for key, value in body.model_dump(exclude_none=True).items():
        if key == "ai_base_url" and value and not value.startswith(("http://", "https://")):
            raise HTTPException(422, "The AI endpoint must start with http:// or https://")
        settings_store.set(db, key, value)
    db.commit()
    return get_settings(_, db)
