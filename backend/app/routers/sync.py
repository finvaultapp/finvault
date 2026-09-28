from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import settings_store
from ..db import get_db
from ..deps import current_user, owned
from ..models import Account, SyncConnection, User
from ..services import sync as s

router = APIRouter(prefix="/api/sync", tags=["sync"])


def _require(db: Session, provider: str):
    status = s.providers_status(db)
    p = next((p for p in status["providers"] if p["id"] == provider), None)
    if not p or not p["available"]:
        raise HTTPException(403, f"{p['name'] if p else provider} isn't set up on this server.")


def _err(exc: Exception):
    raise HTTPException(400, str(exc)) from exc


@router.get("/status")
def status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    conns = []
    for c in db.scalars(select(SyncConnection).where(SyncConnection.user_id == user.id)):
        linked = [{"id": a.id, "name": a.name} for a in db.scalars(select(Account).where(Account.sync_connection_id == c.id))]
        conns.append({"id": c.id, "provider": c.provider, "name": c.name, "status": c.status,
                      "last_synced_at": c.last_synced_at.isoformat() if c.last_synced_at else None,
                      "last_error": c.last_error, "accounts": linked})
    return s.providers_status(db) | {"connections": conns}


@router.get("/gocardless/institutions")
def gc_institutions(country: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _require(db, "gocardless")
    try:
        return s.gc_institutions(country)
    except s.SyncError as exc:
        _err(exc)


class GcStartIn(BaseModel):
    institution_id: str
    redirect_url: str


@router.post("/gocardless/start")
def gc_start(body: GcStartIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _require(db, "gocardless")
    try:
        conn, link = s.gc_start(db, user, body.institution_id, body.redirect_url)
    except s.SyncError as exc:
        _err(exc)
    return {"connection_id": conn.id, "link": link}


class TokenIn(BaseModel):
    token: str


@router.post("/simplefin/connect")
def simplefin_connect(body: TokenIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _require(db, "simplefin")
    try:
        conn = s.simplefin_connect(db, user, body.token)
    except s.SyncError as exc:
        _err(exc)
    return {"connection_id": conn.id}


@router.post("/pluggy/connect")
def pluggy_connect(body: TokenIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _require(db, "pluggy")
    try:
        conn = s.pluggy_connect(db, user, body.token)
    except s.SyncError as exc:
        _err(exc)
    return {"connection_id": conn.id}


@router.get("/connections/{cid}/accounts")
def remote_accounts(cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    conn = owned(db, SyncConnection, cid, user)
    try:
        return s.remote_accounts(conn)
    except Exception as exc:  # noqa: BLE001
        _err(exc)


class LinkIn(BaseModel):
    external_id: str
    account_id: int | None = None  # None creates a new account


@router.post("/connections/{cid}/link")
def link(cid: int, body: LinkIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    conn = owned(db, SyncConnection, cid, user)
    try:
        ext = next((a for a in s.remote_accounts(conn) if a["id"] == body.external_id), None)
        if not ext:
            raise s.SyncError("That account wasn't found at the provider.")
        account = owned(db, Account, body.account_id, user) if body.account_id else None
        acct = s.link_account(db, user, conn, ext, account)
    except s.SyncError as exc:
        _err(exc)
    return {"account_id": acct.id}


@router.post("/connections/{cid}/sync")
def sync_now(cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    conn = owned(db, SyncConnection, cid, user)
    try:
        return {"imported": s.sync_connection(db, conn)}
    except s.SyncError as exc:
        _err(exc)


@router.delete("/connections/{cid}")
def disconnect(cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Removes stored provider credentials. Imported transactions stay."""
    conn = owned(db, SyncConnection, cid, user)
    for a in db.scalars(select(Account).where(Account.sync_connection_id == conn.id)):
        a.sync_connection_id, a.external_id = None, None
    db.delete(conn)
    db.commit()
    return {"ok": True}
