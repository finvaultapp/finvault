"""Encrypted backups of the database, receipts and the app secret key.

Archive layout (a tar.gz, then encrypted):
    manifest.json        what is inside, with a SHA-256 for every file
    finvault.db          SQLite snapshot taken with the online backup API   (SQLite servers)
    database.jsonl       one JSON object per row: {"t": table, "r": {...}}  (Postgres servers)
    receipts/...         the DATA_DIR/receipts folder
    secret.key           DATA_DIR/secret.key when it exists (2FA secrets and provider tokens need it)

Encrypted file format (".fvbackup"):
    header  = b"FVBK" | version (1) | log2(scrypt N) (1) | r (1) | p (1) | salt (16) | nonce prefix (7)
    chunks  = repeated [ciphertext length (4, big endian) | AES-256-GCM ciphertext + tag ]
The key is scrypt(passphrase, salt). Each chunk's nonce is prefix | counter (4) | last-chunk flag (1),
and the header is the associated data of every chunk (the STREAM construction), so reordering,
truncating or appending chunks, or editing the header, all fail authentication.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import io
import json
import logging
import os
import re
import secrets
import sqlite3
import tarfile
import tempfile
import threading
from base64 import b64encode
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config, config_admin, settings_store
from ..backup_format import CHUNK, NAME_RE, SUFFIX, BackupError, encrypt_stream, sha256_file
from ..security import decrypt, encrypt

log = logging.getLogger("finvault.backup")
MIN_PASSPHRASE = 12
_lock = threading.Lock()


# --- Settings (stored in app_settings; the passphrase is encrypted with the app key) ------------

def get_enabled(db: Session) -> bool:
    v = settings_store.get(db, "backup_enabled")
    return config_admin.BACKUP_ENABLED if v is None else bool(v)


def get_keep(db: Session) -> int:
    v = settings_store.get(db, "backup_keep")
    return max(1, int(v if v is not None else config_admin.BACKUP_KEEP))


def get_passphrase(db: Session) -> str:
    return decrypt(settings_store.get(db, "backup_passphrase_enc")) or ""


def set_passphrase(db: Session, passphrase: str) -> None:
    settings_store.set(db, "backup_passphrase_enc", encrypt(passphrase) if passphrase else "")



# --- Snapshot ------------------------------------------------------------------------------------

def _json_default(v):
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray, memoryview)):
        return {"$b64": b64encode(bytes(v)).decode()}
    raise TypeError(f"can't serialise {type(v).__name__}")


def _sqlite_path() -> Path | None:
    from ..db import engine
    if engine.dialect.name != "sqlite":
        return None
    return Path(engine.url.database).resolve()


def _snapshot_sqlite(src: Path, dst: Path) -> None:
    s = sqlite3.connect(src, timeout=30)
    d = sqlite3.connect(dst)
    try:
        with d:
            s.backup(d)
    finally:
        d.close()
        s.close()


def _export_json(dst: Path) -> dict:
    """Consistent export of every table in one repeatable-read transaction (Postgres, or any SQL database)."""
    from ..db import Base, engine
    counts = {}
    with engine.connect() as conn:
        if engine.dialect.name == "postgresql":
            conn = conn.execution_options(isolation_level="REPEATABLE READ")
        with conn.begin(), open(dst, "w", encoding="utf-8") as f:
            for table in Base.metadata.sorted_tables:
                n = 0
                for row in conn.execute(select(table)).mappings():
                    f.write(json.dumps({"t": table.name, "r": dict(row)}, default=_json_default) + "\n")
                    n += 1
                counts[table.name] = n
    return counts


def build_archive(work: Path) -> Path:
    """Write the unencrypted tar.gz into `work` and return its path."""
    stage = work / "stage"
    stage.mkdir()
    manifest = {"app": "finvault", "format": 1, "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "files": []}
    db_path = _sqlite_path()
    if db_path is not None:
        manifest["database"] = {"kind": "sqlite", "file": "finvault.db"}
        _snapshot_sqlite(db_path, stage / "finvault.db")
    else:
        manifest["database"] = {"kind": "json", "file": "database.jsonl"}
        manifest["database"]["tables"] = _export_json(stage / "database.jsonl")
    out = work / "archive.tar.gz"
    with tarfile.open(out, "w:gz") as tar:
        for name in [manifest["database"]["file"]]:
            p = stage / name
            manifest["files"].append({"path": name, "size": p.stat().st_size, "sha256": sha256_file(p)})
            tar.add(p, arcname=name)
        receipts = config.DATA_DIR / "receipts"
        if receipts.is_dir():
            for p in sorted(receipts.rglob("*")):
                if p.is_file() and not p.is_symlink():
                    arc = "receipts/" + p.relative_to(receipts).as_posix()
                    manifest["files"].append({"path": arc, "size": p.stat().st_size, "sha256": sha256_file(p)})
                    tar.add(p, arcname=arc, recursive=False)
        key = config.DATA_DIR / "secret.key"
        if key.is_file():
            manifest["files"].append({"path": "secret.key", "size": key.stat().st_size, "sha256": sha256_file(key)})
            tar.add(key, arcname="secret.key")
        raw = json.dumps(manifest, indent=2).encode()
        info = tarfile.TarInfo("manifest.json")
        info.size, info.mtime = len(raw), int(dt.datetime.now().timestamp())
        tar.addfile(info, io.BytesIO(raw))
    return out


# --- Destinations --------------------------------------------------------------------------------

def backup_dir() -> Path:
    return config_admin.BACKUP_DIR


def list_local() -> list[dict]:
    d = backup_dir()
    if not d.is_dir():
        return []
    out = []
    for p in d.iterdir():
        if p.is_file() and NAME_RE.match(p.name):
            st = p.stat()
            out.append({"name": p.name, "size": st.st_size,
                        "created_at": dt.datetime.fromtimestamp(st.st_mtime, dt.timezone.utc).isoformat()})
    return sorted(out, key=lambda b: b["name"], reverse=True)


def local_path(name: str) -> Path | None:
    if not NAME_RE.match(name):
        return None
    p = backup_dir() / name
    return p if p.is_file() else None


def local_status() -> dict:
    d = backup_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / f".probe-{secrets.token_hex(4)}"
        probe.write_bytes(b"")
        probe.unlink()
        return {"path": str(d), "ok": True, "error": ""}
    except OSError as exc:
        return {"path": str(d), "ok": False, "error": str(exc)}


def _prune_local(keep: int) -> None:
    for b in list_local()[keep:]:
        try:
            (backup_dir() / b["name"]).unlink()
        except OSError:
            log.warning("could not remove old backup %s", b["name"])


# --- S3-compatible storage with hand-written AWS Signature Version 4 ------------------------------

def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def sigv4_headers(method: str, url: str, *, access_key: str, secret_key: str, region: str,
                  payload_sha256: str, headers: dict | None = None, now: dt.datetime | None = None,
                  service: str = "s3") -> dict:
    """Return the headers (including Authorization) for a signed request. Query values must already be in `url`."""
    now = now or dt.datetime.now(dt.timezone.utc)
    amz_date, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    parts = urlsplit(url)
    host = parts.netloc
    canonical_uri = quote(parts.path or "/", safe="/-_.~%")
    query = []
    if parts.query:
        for pair in parts.query.split("&"):
            k, _, v = pair.partition("=")
            query.append((quote(k, safe="-_.~%"), quote(v, safe="-_.~%")))
    canonical_query = "&".join(f"{k}={v}" for k, v in sorted(query))
    all_headers = {"host": host, "x-amz-content-sha256": payload_sha256, "x-amz-date": amz_date}
    for k, v in (headers or {}).items():
        all_headers[k.lower()] = str(v).strip()
    signed = ";".join(sorted(all_headers))
    canonical_headers = "".join(f"{k}:{all_headers[k]}\n" for k in sorted(all_headers))
    canonical_request = "\n".join([method, canonical_uri, canonical_query, canonical_headers, signed, payload_sha256])
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical_request.encode()).hexdigest()])
    key = _hmac(_hmac(_hmac(_hmac(("AWS4" + secret_key).encode(), day), region), service), "aws4_request")
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    out = {k: v for k, v in all_headers.items() if k != "host"}
    out["authorization"] = f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={signed}, Signature={signature}"
    return out


EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def _s3_url(key: str = "", query: str = "") -> str:
    c = config_admin
    path = f"/{quote(c.BACKUP_S3_BUCKET, safe='')}"
    if key:
        path += "/" + quote(key, safe="/-_.~")
    return f"{c.BACKUP_S3_ENDPOINT}{path}" + (f"?{query}" if query else "")


def _s3_request(method: str, url: str, payload_sha256: str = EMPTY_SHA256, content=None, extra: dict | None = None):
    c = config_admin
    headers = sigv4_headers(method, url, access_key=c.BACKUP_S3_ACCESS_KEY, secret_key=c.BACKUP_S3_SECRET_KEY,
                            region=c.BACKUP_S3_REGION, payload_sha256=payload_sha256, headers=extra)
    r = httpx.request(method, url, headers=headers, content=content, timeout=httpx.Timeout(60, read=600))
    if r.status_code >= 300:
        code = re.search(r"<Code>([^<]+)</Code>", r.text or "")
        raise BackupError(f"S3 {method} failed: HTTP {r.status_code}" + (f" ({code.group(1)})" if code else ""))
    return r


def s3_upload(path: Path) -> None:
    key = config_admin.BACKUP_S3_PREFIX + path.name
    size = path.stat().st_size
    digest = sha256_file(path)

    def chunks():
        with open(path, "rb") as f:
            yield from iter(lambda: f.read(CHUNK), b"")

    _s3_request("PUT", _s3_url(key), payload_sha256=digest, content=chunks(),
                extra={"Content-Length": str(size), "content-type": "application/octet-stream"})


def s3_list() -> list[str]:
    prefix = config_admin.BACKUP_S3_PREFIX
    names, token = [], None
    while True:
        q = "list-type=2&prefix=" + quote(prefix, safe="")
        if token:
            q += "&continuation-token=" + quote(token, safe="")
        body = _s3_request("GET", _s3_url(query=q)).text
        names += [k[len(prefix):] for k in re.findall(r"<Key>([^<]+)</Key>", body) if k.startswith(prefix)]
        m = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", body)
        if not m or "<IsTruncated>true</IsTruncated>" not in body:
            return names
        token = m.group(1)


def _prune_s3(keep: int) -> None:
    ours = sorted((n for n in s3_list() if NAME_RE.match(n)), reverse=True)
    for name in ours[keep:]:
        _s3_request("DELETE", _s3_url(config_admin.BACKUP_S3_PREFIX + name))


# --- Running a backup -----------------------------------------------------------------------------

def is_running() -> bool:
    return _lock.locked()


def _new_name() -> str:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    name, i = f"finvault-{stamp}{SUFFIX}", 1
    while (backup_dir() / name).exists():
        name, i = f"finvault-{stamp}-{i}{SUFFIX}", i + 1
    return name


def run_backup(trigger: str = "manual") -> dict:
    """Make one backup. Safe to call from any thread; a second concurrent call is refused."""
    from ..db import SessionLocal
    from ..models_admin import BackupRun
    from . import audit

    if not _lock.acquire(blocking=False):
        raise BackupError("A backup is already running.")
    try:
        with SessionLocal() as db:
            passphrase = get_passphrase(db)
            keep = get_keep(db)
            run = BackupRun(trigger=trigger, status="running")
            db.add(run)
            db.commit()
            try:
                if len(passphrase) < MIN_PASSPHRASE:
                    raise BackupError("Set a backup passphrase first.")
                d = backup_dir()
                d.mkdir(parents=True, exist_ok=True)
                name = _new_name()
                final = d / name
                with tempfile.TemporaryDirectory(dir=d, prefix=".work-") as tmp:
                    work = Path(tmp)
                    archive = build_archive(work)
                    part = work / (name + ".part")
                    with open(archive, "rb") as src, open(part, "wb") as dst:
                        encrypt_stream(src, dst, passphrase)
                        dst.flush()
                        os.fsync(dst.fileno())
                    os.replace(part, final)
                run.filename, run.size = name, final.stat().st_size
                _prune_local(keep)
                if config_admin.s3_configured():
                    try:
                        s3_upload(final)
                        _prune_s3(keep)
                        run.s3_status = "ok"
                    except Exception as exc:  # noqa: BLE001
                        run.s3_status, run.error = "failed", f"Saved locally, but the S3 copy failed: {exc}"
                        log.warning("S3 upload failed: %s", exc)
                run.status = "ok" if run.s3_status != "failed" else "failed"
            except Exception as exc:  # noqa: BLE001
                log.exception("backup failed")
                run.status, run.error = "failed", str(exc)[:1000]
            run.finished_at = dt.datetime.now(dt.timezone.utc)
            db.commit()
            audit.record(db, "backup.completed" if run.status == "ok" else "backup.failed",
                         trigger=trigger, file=run.filename, size=run.size, s3=run.s3_status,
                         error=run.error[:200] if run.error else None)
            return run_out(run)
    finally:
        _lock.release()


def run_in_background(trigger: str = "manual") -> None:
    if is_running():
        raise BackupError("A backup is already running.")

    def go():
        try:
            run_backup(trigger)
        except BackupError as exc:
            log.warning("backup not started: %s", exc)

    threading.Thread(target=go, name="finvault-backup", daemon=True).start()


def run_out(r) -> dict:
    from .audit import utc_iso

    return {"id": r.id, "trigger": r.trigger, "status": r.status, "filename": r.filename, "size": r.size,
            "s3_status": r.s3_status, "error": r.error,
            "started_at": utc_iso(r.started_at), "finished_at": utc_iso(r.finished_at)}
