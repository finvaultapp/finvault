"""Move from another app: a one-time wizard that brings a household's history in from YNAB, Actual Budget,
Mint, Monarch Money or another app's CSV. The browser keeps the files and sends them with each step, so
nothing is stored between steps; `options` carries the source, date format, and the plan built so far.
"""
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..importers.migrate import MAX_UPLOAD_BYTES, MigrationData, parse_migration
from ..models import User
from ..services import migrate as service
from ..services.charge_alerts import run_safely as charge_alerts_after_import

router = APIRouter(prefix="/api/migrate", tags=["migrate"])


async def _load(files: list[UploadFile], options: str | None) -> tuple[MigrationData, dict]:
    try:
        opts = json.loads(options) if options else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(422, "The move settings could not be read. Start again from the first step.") from exc
    if not isinstance(opts, dict):
        raise HTTPException(422, "The move settings could not be read. Start again from the first step.")
    raw, total = [], 0
    for f in files:
        data = await f.read(MAX_UPLOAD_BYTES + 1)
        total += len(data)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "These files are larger than 50 MB together.")
        raw.append((f.filename or "upload.csv", data))
    try:
        parsed = parse_migration(raw, source=opts.get("source") or None, date_format=opts.get("date_format") or None,
                                 generic=opts.get("generic") or None)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return parsed, opts.get("plan") or {}


@router.post("/analyze")
async def analyze(files: list[UploadFile] = File(...), options: str | None = Form(None),
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    data, _ = await _load(files, options)
    return service.analyze(db, user, data)


@router.post("/preview")
async def preview(files: list[UploadFile] = File(...), options: str | None = Form(None),
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    data, plan = await _load(files, options)
    try:
        return service.preview(db, user, data, plan)
    except service.PlanError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/commit")
async def commit(files: list[UploadFile] = File(...), options: str | None = Form(None),
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    data, plan = await _load(files, options)
    if not data.transactions:
        raise HTTPException(422, "No transactions were found in these files.")
    try:
        result = service.commit(db, user, data, plan)
    except service.PlanError as exc:
        raise HTTPException(422, str(exc)) from exc
    charge_alerts_after_import(db, user)
    return result
