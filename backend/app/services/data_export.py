"""The "Download all my data" export: one zip of everything that belongs to one member.

Which tables are included is worked out from the SQLAlchemy metadata, so tables added later come along
without changes here:
  - the member's own row in `users` (their profile and notification settings);
  - every table with a `user_id` column that references users.id, limited to the member's rows;
  - every other table that references one of those tables by foreign key (asset values through assets,
    splits and shares through transactions, ...), limited to rows whose parents are the member's own.
    When a table references several owned tables, a row is included only when every one of them is the
    member's (or empty), so a row can never be pulled in through someone else's parent.

Secrets never leave: DENY_TABLES are skipped whole, DENY_COLUMNS are dropped by name, and any other column
whose name looks secret (SECRETISH) is dropped too, as a net for columns added later.

The zip is written to a temporary file (receipts can be large) and streamed from there.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import re
import tempfile
import zipfile
from base64 import b64encode
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Table, and_, or_, select
from sqlalchemy.orm import Session

from ..db import Base
from ..models import Attachment, Transaction, User
from . import receipts

# Whole tables that are never exported, with the reason given in README.txt.
DENY_TABLES = {
    "password_reset_tokens": "password reset links (security data; only hashes are stored anyway)",
    "audit_events": "the household audit log (it is the admin's security record and names other members)",
    "invites": "invite codes (server-wide sign-up secrets)",
    "app_settings": "server settings (shared by the household, may hold secrets)",
}
# Columns dropped from every table where they appear.
DENY_COLUMNS = {
    "password_hash": "your password hash",
    "totp_secret": "your two-factor (TOTP) secret",
    "recovery_codes": "your two-factor recovery codes (stored as hashes)",
    "ai_api_key": "your encrypted AI (OpenAI) API key",
    "credentials": "bank-sync provider credentials and access tokens (encrypted)",
    "token_version": "the internal session counter",
}
# Net for columns added later: anything named like a secret is dropped unless allowed here.
SECRETISH = re.compile(r"password|passphrase|secret|token|api_key|credential|recovery|private_key", re.I)
ALLOW_COLUMNS: set[str] = set()


def _json_default(v):
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray, memoryview)):
        return {"base64": b64encode(bytes(v)).decode()}
    return str(v)


def _drop(col: str) -> bool:
    return col in DENY_COLUMNS or (col not in ALLOW_COLUMNS and bool(SECRETISH.search(col)))


def plan(user_id: int) -> list[tuple[Table, object]]:
    """[(table, where clause)] for every exportable table, parents before children."""
    users = Base.metadata.tables["users"]
    owned: dict[str, object] = {}  # table name -> where clause selecting the member's rows
    out = []
    for table in Base.metadata.sorted_tables:
        if table.name in DENY_TABLES:
            continue
        where = None
        if table.name == "users":
            where = users.c.id == user_id
        elif "user_id" in table.c and any(fk.column.table is users for fk in table.c.user_id.foreign_keys):
            where = table.c.user_id == user_id
        else:
            conds = []
            for col in table.c:
                for fk in col.foreign_keys:
                    parent = fk.column.table
                    if parent.name in owned and parent is not users:
                        sub = select(fk.column).where(owned[parent.name])
                        conds.append(or_(col.is_(None), col.in_(sub)) if col.nullable else col.in_(sub))
            # At least one non-empty link to an owned parent, and every link owned.
            links = [col for col in table.c if any(fk.column.table.name in owned and fk.column.table is not users
                                                   for fk in col.foreign_keys)]
            if conds:
                where = and_(*conds, or_(*[c.is_not(None) for c in links]))
        if where is not None:
            owned[table.name] = where
            out.append((table, where))
    return out


def left_out_columns() -> dict[str, list[str]]:
    res = {}
    for table in Base.metadata.sorted_tables:
        if table.name in DENY_TABLES:
            continue
        cols = [c.name for c in table.c if _drop(c.name)]
        if cols:
            res[table.name] = cols
    return res


def transactions_csv(db: Session, user_id: int) -> str:
    """Exactly what /api/transactions/export?format=csv gives for all of this member's transactions."""
    from ..routers.transactions import csv_text  # routers import services, so this one stays local
    rows = list(db.scalars(select(Transaction).where(Transaction.user_id == user_id)
                           .order_by(Transaction.date, Transaction.id)).unique())
    return csv_text(db, rows)


def _safe_name(name: str) -> str:
    name = re.sub(r"[^\w.\- ]+", "_", Path(name or "receipt").name).strip(" .") or "receipt"
    return name[:120]


def _readme(user: User, counts: dict[str, int], receipt_count: int, missing: int) -> str:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "FinVault data export",
        "====================",
        "",
        f"Member: {user.email}",
        f"Made:   {now}",
        "",
        "Everything FinVault stores that belongs to you, and nothing that belongs to other members.",
        "",
        "What is inside",
        "--------------",
        "data/<table>.json   One file per database table: a JSON list of your rows, one object per row,",
        "                    with the database's own column names. Amounts are strings with full precision",
        "                    (negative means money leaving an account); dates are ISO 8601. Rows refer to each",
        "                    other by id (for example transactions.account_id -> accounts.id).",
        "                    data/users.json is your profile and notification settings.",
        "transactions.csv    All your transactions in the same format as Transactions -> Export -> CSV.",
        "receipts/           Your receipt files, named <attachment id>-<original file name>. The matching",
        "                    rows are in data/attachments.json.",
        "",
        "Rows per table",
        "--------------",
    ]
    lines += [f"  {name}: {n}" for name, n in sorted(counts.items())]
    lines += [f"  receipt files: {receipt_count}" + (f" ({missing} missing on the server)" if missing else ""), ""]
    lines += ["What is left out, and why", "--------------------------",
              "These are secrets or security data. Leaving them out means this file can't be used to sign in",
              "as you or to reach your bank-sync provider.", ""]
    for col, why in DENY_COLUMNS.items():
        lines.append(f"  - {why} (column {col})")
    extra = {t: [c for c in cols if c not in DENY_COLUMNS] for t, cols in left_out_columns().items()}
    for table, cols in extra.items():
        for c in cols:
            lines.append(f"  - {table}.{c} (looks like a secret)")
    for why in DENY_TABLES.values():
        lines.append(f"  - {why}")
    lines += ["  - other members' data, and data shared by the whole server such as exchange rates",
              "", "This file is not encrypted. Keep it somewhere safe.", ""]
    return "\n".join(lines)


def build_zip(db: Session, user: User) -> tuple[str, dict]:
    """Write the export to a temporary file. Returns its path (the caller deletes it) and a summary."""
    fd, path = tempfile.mkstemp(prefix="finvault-export-", suffix=".zip")
    os.close(fd)
    counts: dict[str, int] = {}
    try:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            conn = db.connection()
            for table, where in plan(user.id):
                cols = [c for c in table.c if not _drop(c.name)]
                pk = list(table.primary_key.columns)
                n = 0
                with zf.open(f"data/{table.name}.json", "w") as raw:
                    f = io.TextIOWrapper(raw, encoding="utf-8")
                    f.write("[")
                    for row in conn.execute(select(*cols).where(where).order_by(*pk)).mappings():
                        f.write(("\n  " if n == 0 else ",\n  ") + json.dumps(dict(row), default=_json_default, ensure_ascii=False))
                        n += 1
                    f.write("\n]\n" if n else "]\n")
                    f.flush()
                    f.detach()
                counts[table.name] = n
            zf.writestr("transactions.csv", transactions_csv(db, user.id))
            found = missing = 0
            base = receipts.folder(user.id).resolve()
            for a in db.scalars(select(Attachment).where(Attachment.user_id == user.id).order_by(Attachment.id)):
                p = receipts.file_path(a).resolve()
                if base not in p.parents or not p.is_file():
                    missing += 1
                    continue
                zf.write(p, f"receipts/{a.id}-{_safe_name(a.filename)}")
                found += 1
            zf.writestr("README.txt", _readme(user, counts, found, missing))
    except BaseException:
        os.unlink(path)
        raise
    return path, {"tables": len(counts), "rows": sum(counts.values()), "receipts": found}
