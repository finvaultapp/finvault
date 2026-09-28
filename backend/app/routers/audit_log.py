"""Admin: read and export the security audit log."""
import csv
import io
import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import admin_user
from ..models import User
from ..models_admin import AuditEvent
from ..services.audit import EVENTS, utc_iso

router = APIRouter(prefix="/api/admin/audit", tags=["admin"])


def _filtered(event: str | None, user_id: int | None):
    q = select(AuditEvent)
    if event:
        # "auth" matches every auth.* event; "auth.login" matches exactly.
        q = q.where(AuditEvent.event == event) if "." in event else q.where(AuditEvent.event.like(f"{event}.%"))
    if user_id:
        q = q.where(or_(AuditEvent.user_id == user_id, AuditEvent.target_user_id == user_id))
    return q


def _out(e: AuditEvent) -> dict:
    return {"id": e.id, "created_at": utc_iso(e.created_at), "event": e.event, "label": EVENTS.get(e.event, e.event),
            "user_id": e.user_id, "email": e.email, "target_user_id": e.target_user_id, "target_email": e.target_email,
            "ip": e.ip, "detail": json.loads(e.detail or "{}")}


@router.get("/events")
def event_types(_: User = Depends(admin_user)):
    return [{"id": k, "label": v} for k, v in EVENTS.items()]


@router.get("")
def list_events(event: str | None = None, user_id: int | None = None, page: int = Query(1, ge=1),
                page_size: int = Query(50, ge=1, le=200), _: User = Depends(admin_user), db: Session = Depends(get_db)):
    q = _filtered(event, user_id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
                      .offset((page - 1) * page_size).limit(page_size))
    return {"items": [_out(e) for e in rows], "total": total, "page": page, "page_size": page_size,
            "pages": max(1, -(-total // page_size))}


def _cell(v) -> str:
    """Stop spreadsheet apps from treating a value (say, a typed email) as a formula."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


@router.get(".csv")
def export_csv(event: str | None = None, user_id: int | None = None, _: User = Depends(admin_user),
               db: Session = Depends(get_db)):
    rows = db.scalars(_filtered(event, user_id).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["time_utc", "event", "member_email", "member_id", "target_email", "target_id", "ip", "detail"])
    for e in rows:
        w.writerow([_cell(x) for x in (utc_iso(e.created_at), e.event, e.email, e.user_id, e.target_email,
                                        e.target_user_id, e.ip, e.detail)])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": 'attachment; filename="finvault-audit-log.csv"'})
