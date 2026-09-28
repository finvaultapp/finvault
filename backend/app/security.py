"""Password hashing, session tokens, TOTP and at-rest encryption of secrets."""
import base64
import hashlib
import json
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import pyotp
import segno
from cryptography.fernet import Fernet, InvalidToken

from . import config

ALGO = "HS256"
_fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(("fernet:" + config.SECRET_KEY).encode()).digest()))


def hash_password(password: str) -> str:
    # bcrypt only looks at 72 bytes; pre-hash so long passphrases keep all their entropy.
    digest = base64.b64encode(hashlib.sha256(password.encode()).digest())
    return bcrypt.hashpw(digest, bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    digest = base64.b64encode(hashlib.sha256(password.encode()).digest())
    try:
        return bcrypt.checkpw(digest, hashed.encode())
    except ValueError:
        return False


def create_token(user_id: int, token_version: int, kind: str = "session", minutes: int | None = None) -> str:
    lifetime = timedelta(minutes=minutes) if minutes else timedelta(hours=config.SESSION_HOURS)
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "tv": token_version, "typ": kind, "iat": now, "exp": now + lifetime}
    return jwt.encode(payload, config.SECRET_KEY, algorithm=ALGO)


def decode_token(token: str, kind: str = "session") -> dict | None:
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[ALGO])
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != kind:
        return None
    return payload


def encrypt(value: str | dict) -> str:
    if isinstance(value, dict):
        value = json.dumps(value)
    return _fernet.encrypt(value.encode()).decode()


def decrypt(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return _fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        return None


def decrypt_json(token: str | None) -> dict:
    raw = decrypt(token)
    return json.loads(raw) if raw else {}


# --- TOTP -------------------------------------------------------------------

def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="FinVault")


def totp_qr_svg(uri: str) -> str:
    return segno.make(uri, error="m").svg_inline(scale=5, dark="#111", light="#fff")


def verify_totp(secret: str, code: str) -> bool:
    code = "".join(ch for ch in code if ch.isdigit())
    return len(code) == 6 and pyotp.TOTP(secret).verify(code, valid_window=1)


def new_recovery_codes(n: int = 8) -> tuple[list[str], list[str]]:
    codes = [f"{secrets.token_hex(3)}-{secrets.token_hex(3)}" for _ in range(n)]
    hashes = [hashlib.sha256(c.encode()).hexdigest() for c in codes]
    return codes, hashes


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(code.strip().lower().encode()).hexdigest()


# --- Login throttling ---------------------------------------------------------

class Throttle:
    """In-memory sliding window. Good enough for a single-process home server."""

    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self.hits: dict[str, deque] = defaultdict(deque)

    def blocked(self, key: str) -> bool:
        q = self.hits[key]
        now = time.monotonic()
        while q and now - q[0] > self.window:
            q.popleft()
        return len(q) >= self.limit

    def hit(self, key: str) -> None:
        self.hits[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        self.hits.pop(key, None)


login_throttle = Throttle(limit=8, window_seconds=15 * 60)
