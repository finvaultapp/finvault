"""Receipts, bill reminders and the watched import folder."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config, settings_store
from ..db import get_db
from ..deps import current_user, owned
from ..models import Account, Attachment, Recurring, Transaction, User
from ..services import inbox, notify, receipts
from ..services.recurring import occurrences
from ..services.reports import f2

router = APIRouter(prefix="/api", tags=["extras"])


# --- Receipts -----------------------------------------------------------------------

def att_out(a: Attachment) -> dict:
    return {"id": a.id, "transaction_id": a.transaction_id, "filename": a.filename, "content_type": a.content_type,
            "size": a.size, "ocr_status": a.ocr_status, "ocr_text": a.ocr_text if a.ocr_status == "done" else None,
            "ocr_error": a.ocr_text if a.ocr_status == "failed" else None,
            "total_guess": receipts.guess_total(a.ocr_text) if a.ocr_status == "done" else None,
            "url": f"/api/attachments/{a.id}/file", "created_at": a.created_at.isoformat()}


@router.get("/transactions/{tid}/attachments")
def list_attachments(tid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = owned(db, Transaction, tid, user)
    return [att_out(a) for a in db.scalars(select(Attachment).where(Attachment.transaction_id == t.id).order_by(Attachment.id))]


@router.post("/transactions/{tid}/attachments")
async def upload_attachment(tid: int, file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = owned(db, Transaction, tid, user)
    raw = await file.read(receipts.MAX_BYTES + 1)
    try:
        a = receipts.save(db, user.id, t.id, file.filename or "receipt", raw, file.content_type)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return att_out(a)


@router.get("/attachments/{aid}/file")
def get_attachment(aid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = owned(db, Attachment, aid, user)
    path = receipts.file_path(a)
    if not path.exists():
        raise HTTPException(404, "The file is missing from the server's data folder.")
    # Images get a locked-down sandbox. PDFs open in the browser's own viewer, which a sandbox would break.
    csp = "default-src 'none'" if a.content_type == "application/pdf" else "default-src 'none'; img-src 'self'; sandbox"
    return FileResponse(path, media_type=a.content_type, filename=a.filename, content_disposition_type="inline",
                        headers={"Content-Security-Policy": csp})


@router.post("/attachments/{aid}/ocr")
def rerun_ocr(aid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = owned(db, Attachment, aid, user)
    if not settings_store.get(db, "ocr_enabled"):
        raise HTTPException(403, "Receipt text reading is turned off. An admin can enable it.")
    a.ocr_status, a.ocr_text = "pending", None
    db.commit()
    receipts.run_pending()
    db.refresh(a)
    return att_out(a)


@router.delete("/attachments/{aid}")
def delete_attachment(aid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    receipts.delete(db, owned(db, Attachment, aid, user))
    return {"ok": True}


# --- Notifications & bill calendar -------------------------------------------------------

@router.get("/notifications")
def get_notifications(user: User = Depends(current_user)):
    return {"ntfy_url": user.notify_ntfy_url or "", "email": user.notify_email, "hide_amounts": user.notify_hide_amounts,
            "email_available": notify.smtp_configured(), "address": user.email}


class NotifyIn(BaseModel):
    ntfy_url: str = Field(default="", max_length=300)
    email: bool = False
    hide_amounts: bool = False


@router.put("/notifications")
def set_notifications(body: NotifyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    url = body.ntfy_url.strip()
    if url and not url.startswith(("https://", "http://")):
        raise HTTPException(422, "The ntfy address should look like https://ntfy.sh/your-private-topic.")
    user.notify_ntfy_url = url or None
    user.notify_email = body.email and notify.smtp_configured()
    user.notify_hide_amounts = body.hide_amounts
    db.commit()
    return get_notifications(user)


@router.post("/notifications/test")
def test_notification(user: User = Depends(current_user)):
    sent = notify.deliver(user, "FinVault test", "Bill reminders from FinVault will look like this.")
    if not sent:
        raise HTTPException(400, "Nothing was sent. Check the ntfy address, or ask your admin to set up email.")
    return {"sent": sent}


@router.get("/bills/calendar")
def bill_calendar(month: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Every recurring item due in the month, for the calendar view."""
    y, m = int(month[:4]), int(month[5:7])
    start = date(y, m, 1)
    end = (date(y + (m == 12), m % 12 + 1, 1)) - timedelta(days=1)
    accounts = {a.id: a for a in db.scalars(select(Account).where(Account.user_id == user.id))}
    items = []
    for r in db.scalars(select(Recurring).where(Recurring.user_id == user.id, Recurring.is_active.is_(True))):
        for d in occurrences(r, end, limit=40):
            if d >= start:
                acct = accounts.get(r.account_id)
                items.append({"recurring_id": r.id, "name": r.name, "date": d.isoformat(), "amount": f2(r.amount),
                              "currency": acct.currency if acct else None, "account_name": acct.name if acct else None,
                              "auto_post": r.auto_post, "remind_days": r.remind_days})
    items.sort(key=lambda i: i["date"])
    return {"month": month, "items": items}


class RemindIn(BaseModel):
    remind_days: int | None = Field(default=None, ge=0, le=30)


@router.put("/recurring/{rid}/reminder")
def set_reminder(rid: int, body: RemindIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = owned(db, Recurring, rid, user)
    r.remind_days = body.remind_days
    r.last_reminded_for = None
    db.commit()
    return {"ok": True}


# --- Watched import folder ------------------------------------------------------------------

@router.get("/inbox")
def inbox_status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    accounts = []
    for a in db.scalars(select(Account).where(Account.user_id == user.id, Account.is_archived.is_(False)).order_by(Account.name)):
        rel = f"{inbox.member_folder(user)}/{inbox.account_folder(a)}"
        accounts.append({"id": a.id, "name": a.name, "watch": a.watch_folder, "folder": rel})
    return {"enabled": inbox.enabled(db), "root": str(config.IMPORT_WATCH_DIR), "accounts": accounts}


class WatchIn(BaseModel):
    watch: bool


@router.put("/inbox/accounts/{aid}")
def set_watch(aid: int, body: WatchIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = owned(db, Account, aid, user)
    if body.watch and not inbox.enabled(db):
        raise HTTPException(403, "The watched import folder is turned off. An admin can enable it.")
    a.watch_folder = body.watch
    db.commit()
    if body.watch:
        inbox.prepare(user, a)
    return inbox_status(user, db)


@router.post("/inbox/scan")
def scan_now(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not inbox.enabled(db):
        raise HTTPException(403, "The watched import folder is turned off.")
    return {"imported": inbox.scan(db)}
