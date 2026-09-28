import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from . import config, settings_store
from .db import SessionLocal, migrate_schema
from .models import SyncConnection
from .routers import (accounts, admin, ai, assets, auth, categories, currency, extras, imports, planning, plans, reports,
                      sharing, sync, transactions)
from .services import inbox, notify, receipts, recurring
from .services.sync import SyncError, sync_connection

log = logging.getLogger("finvault")


def _hourly_jobs() -> None:
    with SessionLocal() as db:
        if not settings_store.acquire_lock(db, "hourly_jobs", 55 * 60):
            return
        recurring.post_due(db)
        try:
            notify.send_due_reminders(db)
        except Exception:  # noqa: BLE001
            log.exception("bill reminders failed")
        if not settings_store.get(db, "bank_sync_enabled"):
            return
        cutoff = datetime.now(timezone.utc) - timedelta(hours=config.SYNC_INTERVAL_HOURS)
        for conn in db.scalars(select(SyncConnection).where(SyncConnection.status == "active")):
            last = conn.last_synced_at.replace(tzinfo=timezone.utc) if conn.last_synced_at and conn.last_synced_at.tzinfo is None else conn.last_synced_at
            if last is None or last < cutoff:
                try:
                    sync_connection(db, conn)
                except SyncError as exc:
                    log.warning("sync %s failed: %s", conn.id, exc)


async def _scheduler():
    while True:
        try:
            await asyncio.to_thread(_hourly_jobs)
        except Exception:  # noqa: BLE001
            log.exception("background job failed")
        await asyncio.sleep(3600)


def _frequent_jobs() -> None:
    with SessionLocal() as db:
        if not settings_store.acquire_lock(db, "frequent_jobs", 110):
            return
        inbox.scan(db)
    receipts.run_pending()


async def _frequent():
    while True:
        await asyncio.sleep(120)
        try:
            await asyncio.to_thread(_frequent_jobs)
        except Exception:  # noqa: BLE001
            log.exception("folder import / OCR job failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    migrate_schema()
    tasks = [asyncio.create_task(_scheduler()), asyncio.create_task(_frequent())]
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="FinVault", version="1.0.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.middleware("http")
async def guard(request: Request, call_next):
    # Cookie-authenticated writes must come from our own frontend (CSRF defence on top of SameSite=Lax).
    if (request.url.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}
            and "authorization" not in request.headers and request.headers.get("x-finvault") != "1"):
        return JSONResponse({"detail": "Missing X-FinVault header"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    else:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; "
            "font-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
    return response


for r in (auth, admin, accounts, transactions, imports, categories, planning, assets, reports, currency, sync, ai,
          plans, sharing, extras):
    app.include_router(r.router)

from .routers import ai_tools  # noqa: E402
app.include_router(ai_tools.router)


@app.get("/api/health")
def health():
    return {"ok": True}


if (config.STATIC_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=config.STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        candidate = (config.STATIC_DIR / path).resolve()
        if path and candidate.is_file() and config.STATIC_DIR.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(config.STATIC_DIR / "index.html")
