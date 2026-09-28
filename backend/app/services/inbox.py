"""Watched import folder: drop bank exports into a folder (for example on your NAS) and they're imported.

Layout, one folder per account that has "watch folder" turned on:

    <IMPORT_WATCH_DIR>/<member>/<account>/            <- put QFX/OFX/QBO/QIF/CSV files here
    <IMPORT_WATCH_DIR>/<member>/<account>/imported/   <- moved here after a successful import
    <IMPORT_WATCH_DIR>/<member>/<account>/failed/     <- moved here, with a .txt explaining why

Folder names are derived from the member's email and the account's id and name,
and are shown on the account page, so there's nothing to configure by hand.
"""
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config, settings_store
from ..importers import parse_file
from ..models import Account, User
from . import transfers
from .ledger import commit_import

log = logging.getLogger("finvault.inbox")
ALLOWED = {".qfx", ".ofx", ".qbo", ".qif", ".csv", ".txt", ".tsv"}
MAX_BYTES = 15 * 1024 * 1024


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "x"


def member_folder(user: User) -> str:
    return f"{_slug(user.email.split('@')[0])}-{user.id}"


def account_folder(account: Account) -> str:
    return f"{account.id}-{_slug(account.name)}"


def path_for(user: User, account: Account) -> Path:
    return config.IMPORT_WATCH_DIR / member_folder(user) / account_folder(account)


def enabled(db: Session) -> bool:
    return bool(settings_store.get(db, "folder_import_enabled"))


def prepare(user: User, account: Account) -> Path:
    p = path_for(user, account)
    for sub in (p, p / "imported", p / "failed"):
        sub.mkdir(parents=True, exist_ok=True)
    return p


def _move(src: Path, dest_dir: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = dest_dir / f"{stamp}-{src.name}"
    shutil.move(str(src), dest)
    return dest


def scan(db: Session) -> int:
    if not enabled(db):
        return 0
    root = config.IMPORT_WATCH_DIR.resolve()
    imported = 0
    for account in db.scalars(select(Account).where(Account.watch_folder.is_(True), Account.is_archived.is_(False))):
        user = db.get(User, account.user_id)
        if not user or not user.is_active:
            continue
        folder = prepare(user, account).resolve()
        if root not in folder.parents:
            continue  # never follow a folder outside the watch root
        for f in sorted(folder.iterdir()):
            if not f.is_file() or f.name.startswith(".") or f.suffix.lower() not in ALLOWED:
                continue
            # Skip files still being written (modified in the last 10 seconds).
            if datetime.now().timestamp() - f.stat().st_mtime < 10:
                continue
            try:
                if f.stat().st_size > MAX_BYTES:
                    raise ValueError("File is larger than 15 MB.")
                result = parse_file(f.name, f.read_bytes(), preset_id=account.import_preset,
                                    account_type=account.type, account_currency=account.currency)
                if not result.transactions:
                    raise ValueError("No transactions found. " + " ".join(result.warnings[:3]))
                batch = commit_import(db, user, account, result, f"{f.name} (watched folder)")
                transfers.auto_match(db, user)
                _move(f, folder / "imported")
                imported += batch.imported
                log.info("folder import %s -> %s: %s new", f.name, account.name, batch.imported)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                dest = _move(f, folder / "failed")
                dest.with_suffix(dest.suffix + ".txt").write_text(f"Could not import {f.name}:\n{exc}\n", encoding="utf-8")
                log.warning("folder import failed for %s: %s", f.name, exc)
    return imported
