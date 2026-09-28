"""Admin: encrypted backup settings, status, "Back up now" and download."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config_admin, settings_store
from ..db import get_db
from ..deps import admin_user
from ..models import User
from ..models_admin import BackupRun
from ..services import audit, backup

router = APIRouter(prefix="/api/admin/backups", tags=["admin"])


def _status(db: Session) -> dict:
    last = db.scalar(select(BackupRun).order_by(BackupRun.id.desc()).limit(1))
    last_ok = db.scalar(select(BackupRun).where(BackupRun.status == "ok").order_by(BackupRun.id.desc()).limit(1))
    c = config_admin
    return {
        "enabled": backup.get_enabled(db),
        "passphrase_set": bool(backup.get_passphrase(db)),
        "keep": backup.get_keep(db),
        "hour": c.BACKUP_HOUR,
        "running": backup.is_running(),
        "local": backup.local_status(),
        "s3": {"configured": c.s3_configured(), "endpoint": c.BACKUP_S3_ENDPOINT, "bucket": c.BACKUP_S3_BUCKET,
               "prefix": c.BACKUP_S3_PREFIX},
        "last_run": backup.run_out(last) if last else None,
        "last_success": backup.run_out(last_ok) if last_ok else None,
        "backups": backup.list_local(),
    }


@router.get("")
def get_backups(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    return _status(db)


class BackupSettingsIn(BaseModel):
    enabled: bool | None = None
    passphrase: str | None = Field(default=None, max_length=1000)
    keep: int | None = Field(default=None, ge=1, le=365)


@router.patch("")
def update_backups(body: BackupSettingsIn, request: Request, me: User = Depends(admin_user), db: Session = Depends(get_db)):
    changed = []
    if body.passphrase is not None:
        if len(body.passphrase) < backup.MIN_PASSPHRASE:
            raise HTTPException(422, f"Use at least {backup.MIN_PASSPHRASE} characters for the backup passphrase.")
        backup.set_passphrase(db, body.passphrase)
        changed.append("backup_passphrase")
    if body.keep is not None:
        settings_store.set(db, "backup_keep", body.keep)
        changed.append("backup_keep")
    if body.enabled is not None:
        if body.enabled and body.passphrase is None and not backup.get_passphrase(db):
            raise HTTPException(422, "Set a backup passphrase before turning backups on.")
        settings_store.set(db, "backup_enabled", body.enabled)
        changed.append("backup_enabled")
    db.commit()
    if changed:
        audit.record(db, "backup.settings_changed", request=request, user=me, keys=changed,
                     enabled=body.enabled if body.enabled is not None else None)
    return _status(db)


@router.post("/run", status_code=202)
def run_now(request: Request, me: User = Depends(admin_user), db: Session = Depends(get_db)):
    if not backup.get_passphrase(db):
        raise HTTPException(422, "Set a backup passphrase first.")
    try:
        backup.run_in_background("manual")
    except backup.BackupError as exc:
        raise HTTPException(409, str(exc)) from exc
    audit.record(db, "backup.started", request=request, user=me)
    return {"started": True}


@router.get("/{name}/download")
def download(name: str, request: Request, me: User = Depends(admin_user), db: Session = Depends(get_db)):
    path = backup.local_path(name)
    if path is None:
        raise HTTPException(404, "Backup not found")
    audit.record(db, "backup.downloaded", request=request, user=me, file=name)
    return FileResponse(path, media_type="application/octet-stream", filename=name)
