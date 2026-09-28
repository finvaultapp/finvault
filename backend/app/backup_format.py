"""The .fvbackup file format: streaming AES-256-GCM with an scrypt key, plus archive verification.

Kept free of app imports so the restore script can use it without loading the app's configuration.
Header: b"FVBK" | version | log2(scrypt N) | r | p | salt (16) | nonce prefix (7). Then chunks of
[4-byte big-endian length | AES-256-GCM ciphertext+tag]; chunk nonce = prefix | counter (4) | last flag (1),
and the header is every chunk's associated data (STREAM), so truncation, reordering and header edits fail.
See app/services/backup.py for the archive layout.
"""
import hashlib
import io
import json
import re
import secrets
import sqlite3
import struct
import tarfile
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"FVBK"
VERSION = 1
SCRYPT_LOG_N, SCRYPT_R, SCRYPT_P = 15, 8, 1
CHUNK = 1024 * 1024
HEADER_LEN = 4 + 1 + 3 + 16 + 7
SUFFIX = ".fvbackup"
NAME_RE = re.compile(r"^finvault-\d{8}-\d{6}(-\d+)?\.fvbackup$")


class BackupError(Exception):
    pass


# --- Encryption ----------------------------------------------------------------------------------

def _derive(passphrase: str, salt: bytes, log_n: int, r: int, p: int) -> bytes:
    if not (10 <= log_n <= 20 and 1 <= r <= 32 and 1 <= p <= 16):
        raise BackupError("This file has unexpected key settings and was not made by FinVault.")
    return Scrypt(salt=salt, length=32, n=2 ** log_n, r=r, p=p).derive(passphrase.encode("utf-8"))


def _nonce(prefix: bytes, counter: int, last: bool) -> bytes:
    return prefix + struct.pack(">I", counter) + (b"\x01" if last else b"\x00")


def encrypt_stream(src, dst, passphrase: str) -> None:
    salt, prefix = secrets.token_bytes(16), secrets.token_bytes(7)
    header = MAGIC + bytes([VERSION, SCRYPT_LOG_N, SCRYPT_R, SCRYPT_P]) + salt + prefix
    aead = AESGCM(_derive(passphrase, salt, SCRYPT_LOG_N, SCRYPT_R, SCRYPT_P))
    dst.write(header)
    counter = 0
    block = src.read(CHUNK)
    while True:
        nxt = src.read(CHUNK)
        last = not nxt
        ct = aead.encrypt(_nonce(prefix, counter, last), block, header)
        dst.write(struct.pack(">I", len(ct)) + ct)
        if last:
            break
        counter += 1
        if counter >= 2 ** 32 - 1:
            raise BackupError("Backup is too large.")
        block = nxt


def decrypt_stream(src, dst, passphrase: str) -> None:
    """Decrypt into dst. Raises BackupError on a wrong passphrase or any tampering."""
    header = src.read(HEADER_LEN)
    if len(header) != HEADER_LEN or header[:4] != MAGIC:
        raise BackupError("This isn't a FinVault backup file.")
    if header[4] != VERSION:
        raise BackupError(f"Unsupported backup version {header[4]}.")
    log_n, r, p = header[5], header[6], header[7]
    salt, prefix = header[8:24], header[24:31]
    aead = AESGCM(_derive(passphrase, salt, log_n, r, p))
    counter = 0
    while True:
        raw_len = src.read(4)
        if len(raw_len) != 4:
            raise BackupError("The backup file is cut short (missing its last part).")
        (n,) = struct.unpack(">I", raw_len)
        if n > CHUNK + 16:
            raise BackupError("The backup file is damaged.")
        ct = src.read(n)
        if len(ct) != n:
            raise BackupError("The backup file is cut short.")
        peek_last = src.read(1) == b""
        if not peek_last:
            src.seek(-1, io.SEEK_CUR)
        try:
            pt = aead.decrypt(_nonce(prefix, counter, peek_last), ct, header)
        except InvalidTag:
            if counter == 0:
                raise BackupError("Wrong passphrase, or the file was changed.") from None
            raise BackupError("The backup file is damaged or was changed.") from None
        dst.write(pt)
        if peek_last:
            return
        counter += 1


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


# --- Verify and extract (used by the restore script) ----------------------------------------------

def _safe_member(m: tarfile.TarInfo) -> bool:
    p = Path(m.name)
    return m.isfile() and not p.is_absolute() and ".." not in p.parts and not m.name.startswith(("/", "\\"))


def decrypt_and_verify(backup_file: Path, passphrase: str, out_dir: Path) -> dict:
    """Decrypt, unpack into out_dir and check every file against the manifest. Returns the manifest."""
    archive = out_dir / "archive.tar.gz"
    with open(backup_file, "rb") as src, open(archive, "wb") as dst:
        decrypt_stream(src, dst, passphrase)
    files = out_dir / "files"
    files.mkdir()
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        bad = [m.name for m in members if not _safe_member(m)]
        if bad:
            raise BackupError(f"The archive contains unsafe entries: {', '.join(bad[:3])}")
        tar.extractall(files, members=members, filter="data")
    archive.unlink()
    mf = files / "manifest.json"
    if not mf.is_file():
        raise BackupError("The archive has no manifest.")
    manifest = json.loads(mf.read_text("utf-8"))
    if manifest.get("app") != "finvault":
        raise BackupError("The manifest isn't from FinVault.")
    for entry in manifest["files"]:
        p = files / entry["path"]
        if not p.is_file() or sha256_file(p) != entry["sha256"]:
            raise BackupError(f"{entry['path']} doesn't match the manifest.")
    db = manifest["database"]
    if db["kind"] == "sqlite":
        con = sqlite3.connect(files / db["file"])
        try:
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BackupError("The database in the backup failed SQLite's integrity check.")
        finally:
            con.close()
    return manifest


