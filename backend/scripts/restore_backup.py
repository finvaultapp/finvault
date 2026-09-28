"""Restore a FinVault encrypted backup (.fvbackup).

    python -m scripts.restore_backup BACKUP_FILE [--data-dir DIR] [--database-url URL]
                                                 [--verify-only] [--force] [--yes]

Stop FinVault first. The script:
  1. asks for the backup passphrase, decrypts the file and checks every file against the manifest
     (and runs SQLite's integrity check), all in a temporary folder, before touching anything;
  2. refuses to continue while the server still has the database open, unless --force;
  3. keeps the current database, receipts folder and secret.key next to them as *.before-restore-<time>;
  4. puts the backup's database, receipts and secret.key in place.

The passphrase can also come from the FINVAULT_BACKUP_PASSPHRASE environment variable (for scripted restores).
"""
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from base64 import b64decode
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.backup_format import BackupError, decrypt_and_verify  # noqa: E402  (no app config imported)


class RestoreError(Exception):
    pass


def _sqlite_file(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite"):
        return None
    return Path(database_url.split(":///", 1)[1]).resolve()


def sqlite_in_use(path: Path) -> bool:
    """True while another process has the database open (FinVault runs SQLite in WAL mode)."""
    if not path.exists():
        return False
    if Path(f"{path}-wal").exists() or Path(f"{path}-shm").exists():
        return True
    try:
        con = sqlite3.connect(path, timeout=0)
        try:
            con.execute("BEGIN EXCLUSIVE")
            con.rollback()
        finally:
            con.close()
    except sqlite3.OperationalError:
        return True
    return False


def postgres_in_use(database_url: str) -> bool:
    from sqlalchemy import create_engine, text
    eng = create_engine(database_url)
    try:
        with eng.connect() as c:
            n = c.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                               "AND pid <> pg_backend_pid()")).scalar()
        return (n or 0) > 0
    finally:
        eng.dispose()


def _keep_aside(p: Path, stamp: str) -> Path | None:
    if not p.exists():
        return None
    dest = p.with_name(f"{p.name}.before-restore-{stamp}")
    if p.is_dir():
        p.rename(dest)
    else:
        shutil.copy2(p, dest)
    return dest


def _convert(col, value):
    if value is None:
        return None
    if isinstance(value, dict) and "$b64" in value:
        return b64decode(value["$b64"])
    try:
        py = col.type.python_type
    except NotImplementedError:
        return value
    if py is dt.datetime and isinstance(value, str):
        return dt.datetime.fromisoformat(value)
    if py is dt.date and isinstance(value, str):
        return dt.date.fromisoformat(value)
    if py is Decimal and isinstance(value, str):
        return Decimal(value)
    return value


def _load_json(database_url: str, jsonl: Path) -> dict:
    """Replace every table's rows with the exported ones (any SQLAlchemy database; used for Postgres backups)."""
    from sqlalchemy import Integer, create_engine, delete, text

    from app.db import Base  # imports app config; the data dir and secret.key are already in place by now
    import app.models  # noqa: F401  (registers every table)

    eng = create_engine(database_url)
    Base.metadata.create_all(eng)
    tables = {t.name: t for t in Base.metadata.sorted_tables}
    rows: dict[str, list] = {name: [] for name in tables}
    with open(jsonl, encoding="utf-8") as f:
        for line in f:
            item = json.loads(line)
            t = tables.get(item["t"])
            if t is None:
                continue  # a table this version no longer has
            rows[t.name].append({k: _convert(t.c[k], v) for k, v in item["r"].items() if k in t.c})
    counts = {}
    with eng.begin() as conn:
        for t in reversed(Base.metadata.sorted_tables):
            conn.execute(delete(t))
        for t in Base.metadata.sorted_tables:
            if rows[t.name]:
                conn.execute(t.insert(), rows[t.name])
            counts[t.name] = len(rows[t.name])
        if eng.dialect.name == "postgresql":
            for t in Base.metadata.sorted_tables:
                pk = list(t.primary_key.columns)
                if len(pk) == 1 and isinstance(pk[0].type, Integer):
                    conn.execute(text(f"SELECT setval(pg_get_serial_sequence('{t.name}', '{pk[0].name}'), "
                                      f"COALESCE((SELECT MAX({pk[0].name}) FROM {t.name}), 0) + 1, false)"))
    eng.dispose()
    return counts


def restore(backup_file: Path, passphrase: str, data_dir: Path, database_url: str, *, force: bool = False,
            verify_only: bool = False, confirm=None, log=print) -> dict:
    """Verify, then restore. Returns the manifest. `confirm` is called before anything is overwritten."""
    data_dir = data_dir.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=data_dir, prefix=".restore-") as tmp:
        work = Path(tmp)
        log("Decrypting and checking the backup...")
        manifest = decrypt_and_verify(backup_file, passphrase, work)
        files = work / "files"
        kind = manifest["database"]["kind"]
        log(f"OK: backup from {manifest['created_at']}, {len(manifest['files'])} files, database: {kind}.")
        if verify_only:
            return manifest

        target_db = _sqlite_file(database_url)
        if kind == "sqlite" and target_db is None:
            raise RestoreError("This backup holds a SQLite database, but DATABASE_URL points at another database. "
                               "Restore it with a SQLite DATABASE_URL.")
        if not force:
            busy = sqlite_in_use(target_db) if target_db else postgres_in_use(database_url)
            if busy:
                raise RestoreError("The database is still open, probably by a running FinVault. Stop the server "
                                   "(docker compose stop finvault) and try again, or pass --force if you are sure "
                                   "nothing is using it (for example after a crash).")
        if confirm and not confirm():
            raise RestoreError("Cancelled. Nothing was changed.")

        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        # Database
        if kind == "sqlite":
            if target_db.exists():
                aside = target_db.with_name(f"{target_db.name}.before-restore-{stamp}")
                src, dst = sqlite3.connect(target_db), sqlite3.connect(aside)
                with dst:
                    src.backup(dst)
                src.close()
                dst.close()
                log(f"Kept the current database as {aside.name}")
            for suffix in ("-wal", "-shm"):
                Path(f"{target_db}{suffix}").unlink(missing_ok=True)
            target_db.parent.mkdir(parents=True, exist_ok=True)
            os.replace(files / manifest["database"]["file"], target_db)
        # Secret key first, so the app config imported by a JSON restore reads the restored one.
        key = files / "secret.key"
        if key.is_file():
            current = data_dir / "secret.key"
            if current.is_file() and current.read_bytes() != key.read_bytes():
                _keep_aside(current, stamp)
                log("Kept the current secret.key as secret.key.before-restore-" + stamp)
            os.replace(key, current)
            if os.environ.get("SECRET_KEY"):
                log("Note: SECRET_KEY is set in the environment, so FinVault will use it instead of the restored "
                    "secret.key. It must be the same value the backed-up server used.")
        # Receipts
        receipts = files / "receipts"
        target_receipts = data_dir / "receipts"
        if _keep_aside(target_receipts, stamp):
            log(f"Kept the current receipts folder as receipts.before-restore-{stamp}")
        if receipts.is_dir():
            shutil.move(str(receipts), str(target_receipts))
        if kind == "json":
            os.environ.setdefault("FINVAULT_DATA_DIR", str(data_dir))
            counts = _load_json(database_url, files / manifest["database"]["file"])
            log(f"Loaded {sum(counts.values())} rows into {len(counts)} tables.")
    log("Restore finished. Start FinVault again.")
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Restore a FinVault encrypted backup (.fvbackup).")
    ap.add_argument("backup", type=Path)
    ap.add_argument("--data-dir", type=Path, default=Path(os.environ.get("FINVAULT_DATA_DIR", "./data")))
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--verify-only", action="store_true", help="decrypt and check the backup, change nothing")
    ap.add_argument("--force", action="store_true", help="restore even if the database looks open")
    ap.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    args = ap.parse_args(argv)
    data_dir = args.data_dir.resolve()
    database_url = args.database_url or f"sqlite:///{data_dir / 'finvault.db'}"
    os.environ["FINVAULT_DATA_DIR"] = str(data_dir)
    os.environ["DATABASE_URL"] = database_url
    if not args.backup.is_file():
        print(f"No such file: {args.backup}", file=sys.stderr)
        return 2
    passphrase = os.environ.get("FINVAULT_BACKUP_PASSPHRASE") or getpass.getpass("Backup passphrase: ")

    def confirm():
        if args.yes:
            return True
        where = database_url if not database_url.startswith("sqlite") else _sqlite_file(database_url)
        answer = input(f"Replace the database at {where} and the receipts in {data_dir}? Type 'restore' to go on: ")
        return answer.strip().lower() == "restore"

    try:
        restore(args.backup, passphrase, data_dir, database_url, force=args.force, verify_only=args.verify_only,
                confirm=confirm)
    except (BackupError, RestoreError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
