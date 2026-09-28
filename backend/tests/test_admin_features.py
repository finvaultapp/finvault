"""Encrypted backups, audit log and single sign-on (OIDC)."""
import base64
import datetime as dt
import hashlib
import io
import json
import sqlite3
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pyotp
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app import backup_format, config, config_admin
from app.db import SessionLocal
from app.models_admin import AuditEvent
from app.services import audit, backup, nightly
from app.services import oidc as op
from scripts import restore_backup

PW = "correct horse battery"
PASSPHRASE = "a long backup passphrase"


def register(c, email="a@home.lan", **extra):
    r = c.post("/api/auth/register", json={"email": email, "password": PW, "name": "A", **extra})
    assert r.status_code == 200, r.text
    return r.json()


def events(c, **params):
    r = c.get("/api/admin/audit", params=params)
    assert r.status_code == 200, r.text
    return r.json()


# --- Audit log ---------------------------------------------------------------------------------

def test_audit_records_sign_ins_without_passwords(client):
    register(client)
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "a@home.lan", "password": "wrong password!"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "nobody@home.lan", "password": "hunter2hunter2"}).status_code == 401
    client.post("/api/auth/login", json={"email": "a@home.lan", "password": PW})
    failed = events(client, event="auth.login_failed")["items"]
    assert {e["email"] for e in failed} == {"a@home.lan", "nobody@home.lan"}
    assert {e["detail"]["reason"] for e in failed} == {"wrong_password", "unknown_email"}
    assert all(e["ip"] for e in failed)
    assert events(client, event="auth.login")["total"] == 1
    with SessionLocal() as db:
        dump = json.dumps([(e.email, e.detail) for e in db.query(AuditEvent)])
    assert "wrong password!" not in dump and "hunter2" not in dump and PW not in dump


def test_audit_admin_actions_filters_pagination_and_csv(client):
    register(client)
    client.patch("/api/admin/settings", json={"ai_api_key": "sk-supersecret", "ai_enabled": True})
    new = client.post("/api/admin/users", json={"email": "=cmd@home.lan", "password": PW}).json()
    client.patch(f"/api/admin/users/{new['id']}", json={"is_admin": True})
    client.post("/api/admin/invites", json={"days": 3})
    client.delete(f"/api/admin/users/{new['id']}")

    s = events(client, event="admin.settings_changed")["items"][0]
    assert s["detail"]["keys"] == ["ai_api_key", "ai_enabled"]
    assert "sk-supersecret" not in json.dumps(s)
    assert events(client, event="admin.member_deleted")["items"][0]["target_email"] == "=cmd@home.lan"
    # Filter by member (actor or target), and by a whole group of events.
    by_target = events(client, user_id=new["id"])
    assert {e["event"] for e in by_target["items"]} == {"admin.member_created", "admin.member_changed", "admin.member_deleted"}
    assert events(client, event="admin")["total"] >= 5
    page = events(client, page=2, page_size=2)
    assert page["page"] == 2 and len(page["items"]) == 2 and page["pages"] >= 3

    csv = client.get("/api/admin/audit.csv")
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    assert "'=cmd@home.lan" in csv.text  # formula injection defused
    assert "sk-supersecret" not in csv.text
    assert any(e["id"] == "backup.completed" for e in client.get("/api/admin/audit/events").json())


def test_audit_log_is_admin_only(client):
    register(client)
    code = client.post("/api/admin/invites", json={}).json()["code"]
    client.post("/api/auth/logout")
    register(client, "b@home.lan", invite_code=code)
    assert client.get("/api/admin/audit").status_code == 403
    assert client.get("/api/admin/audit.csv").status_code == 403
    assert client.get("/api/admin/backups").status_code == 403


def test_audit_2fa_password_and_sign_out_everywhere(client):
    register(client)
    secret = client.post("/api/auth/2fa/setup").json()["secret"]
    client.post("/api/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()})
    client.post("/api/auth/2fa/disable", json={"code": pyotp.TOTP(secret).now(), "password": PW})
    client.post("/api/auth/password", json={"current_password": PW, "new_password": PW + "!"})
    client.post("/api/auth/logout-all")
    client.post("/api/auth/login", json={"email": "a@home.lan", "password": PW + "!"})
    got = {e["event"] for e in events(client, event="auth")["items"]}
    assert {"auth.2fa_enabled", "auth.2fa_disabled", "auth.password_changed", "auth.logout_all", "auth.login"} <= got


def test_audit_prune_keeps_recent_rows(client):
    with SessionLocal() as db:
        db.add(AuditEvent(event="auth.login", created_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=400)))
        db.add(AuditEvent(event="auth.login"))
        db.commit()
        assert audit.prune(db, 365) == 1
        assert db.query(AuditEvent).count() == 1


# --- Backup file format ---------------------------------------------------------------------------

@pytest.fixture()
def small_chunks(monkeypatch):
    monkeypatch.setattr(backup_format, "CHUNK", 64)


def _roundtrip(data: bytes, pw=PASSPHRASE) -> bytes:
    enc = io.BytesIO()
    backup_format.encrypt_stream(io.BytesIO(data), enc, pw)
    return enc.getvalue()


def _dec(blob: bytes, pw=PASSPHRASE) -> bytes:
    out = io.BytesIO()
    backup_format.decrypt_stream(io.BytesIO(blob), out, pw)
    return out.getvalue()


def test_format_roundtrip_and_tamper_detection(small_chunks):
    data = bytes(range(256)) * 3  # 12 chunks of 64 bytes
    blob = _roundtrip(data)
    assert blob[:4] == b"FVBK" and data not in blob
    assert _dec(blob) == data
    assert _dec(_roundtrip(b"")) == b""
    with pytest.raises(backup_format.BackupError, match="passphrase"):
        _dec(blob, "not the passphrase")
    flipped = bytearray(blob)
    flipped[len(blob) // 2] ^= 1
    with pytest.raises(backup_format.BackupError):
        _dec(bytes(flipped))
    # Dropping the final chunk must not decrypt to a silently shorter file.
    with pytest.raises(backup_format.BackupError):
        _dec(blob[:-(4 + 64 + 16)])
    header = bytearray(blob)
    header[8] ^= 1  # salt
    with pytest.raises(backup_format.BackupError):
        _dec(bytes(header))


def test_sigv4_matches_aws_documented_example():
    # "GET Object" example from the AWS Signature Version 4 documentation for S3.
    h = backup.sigv4_headers(
        "GET", "https://examplebucket.s3.amazonaws.com/test.txt",
        access_key="AKIAIOSFODNN7EXAMPLE", secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        region="us-east-1", payload_sha256=backup.EMPTY_SHA256, headers={"Range": "bytes=0-9"},
        now=dt.datetime(2013, 5, 24, tzinfo=dt.timezone.utc))
    assert h["authorization"] == (
        "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request, "
        "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, "
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41")


# --- Backups end to end ---------------------------------------------------------------------------

@pytest.fixture()
def backup_dir(tmp_path, monkeypatch):
    d = tmp_path / "backups"
    monkeypatch.setattr(config_admin, "BACKUP_DIR", d)
    receipts = config.DATA_DIR / "receipts" / "1"
    receipts.mkdir(parents=True, exist_ok=True)
    (receipts / "r.jpg").write_bytes(b"\xff\xd8\xff receipt")
    return d


def test_backup_settings_never_return_the_passphrase(client, backup_dir):
    register(client)
    s = client.get("/api/admin/backups").json()
    assert s["enabled"] is False and s["passphrase_set"] is False and s["keep"] == 14
    assert client.patch("/api/admin/backups", json={"enabled": True}).status_code == 422
    assert client.patch("/api/admin/backups", json={"passphrase": "short"}).status_code == 422
    r = client.patch("/api/admin/backups", json={"passphrase": PASSPHRASE, "enabled": True, "keep": 3})
    assert r.status_code == 200 and r.json()["passphrase_set"] and r.json()["enabled"]
    assert PASSPHRASE not in r.text and PASSPHRASE not in client.get("/api/admin/settings").text
    with SessionLocal() as db:
        from app.models import AppSetting
        stored = db.get(AppSetting, "backup_passphrase_enc").value
        assert PASSPHRASE not in stored and backup.get_passphrase(db) == PASSPHRASE
    assert events(client, event="backup.settings_changed")["items"][0]["detail"]["keys"] == [
        "backup_passphrase", "backup_keep", "backup_enabled"]


def test_backup_now_list_download_retention_and_restore(client, backup_dir, tmp_path):
    register(client)
    client.post("/api/accounts", json={"name": "Chequing", "currency": "CAD"})
    assert client.post("/api/admin/backups/run").status_code == 422  # no passphrase yet
    client.patch("/api/admin/backups", json={"passphrase": PASSPHRASE, "keep": 2})

    assert client.post("/api/admin/backups/run").status_code == 202
    for _ in range(200):
        if not backup.is_running():
            break
        time.sleep(0.05)
    s = client.get("/api/admin/backups").json()
    assert s["last_run"]["status"] == "ok", s["last_run"]
    assert len(s["backups"]) == 1
    name = s["backups"][0]["name"]

    got = client.get(f"/api/admin/backups/{name}/download")
    assert got.status_code == 200 and got.content[:4] == b"FVBK"
    assert b"Chequing" not in got.content
    assert client.get("/api/admin/backups/..%2Fsecret.key/download").status_code == 404

    backup.run_backup()
    backup.run_backup()
    assert len(backup.list_local()) == 2  # keep last 2
    assert {"backup.started", "backup.completed", "backup.downloaded"} <= {e["event"] for e in events(client, event="backup")["items"]}

    # Restore into a fresh data folder.
    newest = backup_dir / backup.list_local()[0]["name"]
    target = tmp_path / "restored"
    url = f"sqlite:///{target / 'finvault.db'}"
    with pytest.raises(backup_format.BackupError):
        restore_backup.restore(newest, "wrong passphrase!!", target, url, log=lambda *_: None)
    assert not (target / "finvault.db").exists()  # verified before anything was written
    manifest = restore_backup.restore(newest, PASSPHRASE, target, url, log=lambda *_: None)
    assert manifest["database"]["kind"] == "sqlite"
    con = sqlite3.connect(target / "finvault.db")
    assert con.execute("select name from accounts").fetchall() == [("Chequing",)]
    con.close()
    assert (target / "receipts" / "1" / "r.jpg").read_bytes() == b"\xff\xd8\xff receipt"
    assert (target / "secret.key").read_text() == (config.DATA_DIR / "secret.key").read_text()

    # A second restore while the database looks open is refused unless forced.
    Path(f"{target / 'finvault.db'}-wal").write_bytes(b"")
    with pytest.raises(restore_backup.RestoreError, match="still open"):
        restore_backup.restore(newest, PASSPHRASE, target, url, log=lambda *_: None)
    restore_backup.restore(newest, PASSPHRASE, target, url, force=True, log=lambda *_: None)
    assert list(target.glob("finvault.db.before-restore-*")) and list(target.glob("receipts.before-restore-*"))


def test_json_export_path_used_for_postgres(client, backup_dir, tmp_path, monkeypatch):
    register(client)
    client.post("/api/accounts", json={"name": "Épargne", "currency": "CAD", "opening_balance": "12.34"})
    client.patch("/api/admin/backups", json={"passphrase": PASSPHRASE})
    monkeypatch.setattr(backup, "_sqlite_path", lambda: None)  # pretend the server runs on Postgres
    run = backup.run_backup()
    assert run["status"] == "ok", run
    target = tmp_path / "from-json"
    manifest = restore_backup.restore(backup_dir / run["filename"], PASSPHRASE, target,
                                      f"sqlite:///{target / 'finvault.db'}", log=lambda *_: None)
    assert manifest["database"]["kind"] == "json" and manifest["database"]["tables"]["accounts"] == 1
    con = sqlite3.connect(target / "finvault.db")
    assert con.execute("select name, opening_balance from accounts").fetchone()[0] == "Épargne"
    assert con.execute("select count(*) from users").fetchone()[0] == 1
    con.close()


def test_s3_upload_is_signed_and_pruned(client, backup_dir, monkeypatch):
    register(client)
    client.patch("/api/admin/backups", json={"passphrase": PASSPHRASE, "keep": 1})
    for k, v in {"BACKUP_S3_ENDPOINT": "https://s3.nas.lan", "BACKUP_S3_BUCKET": "vault", "BACKUP_S3_ACCESS_KEY": "AK",
                 "BACKUP_S3_SECRET_KEY": "SK", "BACKUP_S3_PREFIX": "fv/"}.items():
        monkeypatch.setattr(config_admin, k, v)
    calls = []

    def fake_request(method, url, headers=None, content=None, timeout=None):
        body = b"".join(content) if content is not None else b""
        calls.append((method, url, headers, body))
        if method == "GET":
            uploaded = "".join(f"<Key>{urlsplit(c[1]).path.split('/vault/')[1]}</Key>" for c in calls if c[0] == "PUT")
            xml = ("<ListBucketResult><Key>fv/finvault-20200101-000000.fvbackup</Key><Key>fv/other.txt</Key>"
                   f"{uploaded}</ListBucketResult>")
            return httpx.Response(200, text=xml)
        return httpx.Response(200)

    monkeypatch.setattr(backup.httpx, "request", fake_request)
    run = backup.run_backup()
    assert run["status"] == "ok" and run["s3_status"] == "ok", run
    put = next(c for c in calls if c[0] == "PUT")
    assert put[1] == f"https://s3.nas.lan/vault/fv/{run['filename']}"
    assert put[2]["authorization"].startswith("AWS4-HMAC-SHA256 Credential=AK/")
    assert put[2]["x-amz-content-sha256"] == hashlib.sha256(put[3]).hexdigest()
    assert put[3][:4] == b"FVBK"
    deletes = [c[1] for c in calls if c[0] == "DELETE"]
    assert deletes == ["https://s3.nas.lan/vault/fv/finvault-20200101-000000.fvbackup"]  # never other.txt


def test_nightly_runs_once_a_day_and_only_when_enabled(client, backup_dir):
    register(client)
    day = dt.datetime(2099, 1, 1, 4, 0)
    assert nightly.run_if_due(day.replace(hour=1)) is False  # before BACKUP_HOUR
    assert nightly.run_if_due(day) is True and backup.list_local() == []  # off by default
    client.patch("/api/admin/backups", json={"passphrase": PASSPHRASE, "enabled": True})
    assert nightly.run_if_due(day) is False  # already ran today
    assert nightly.run_if_due(day + dt.timedelta(days=1)) is True
    assert len(backup.list_local()) == 1


# --- Single sign-on ---------------------------------------------------------------------------------

ISSUER = "https://id.home.lan"


class FakeProvider:
    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        self.jwks = {"keys": [jwk | {"kid": "k1", "use": "sig", "alg": "RS256"}]}
        self.claims = {}
        self.nonce_override = None
        self.last_authorize = None

    def discovery(self):
        return {"issuer": ISSUER, "authorization_endpoint": f"{ISSUER}/authorize", "token_endpoint": f"{ISSUER}/token",
                "jwks_uri": f"{ISSUER}/jwks", "userinfo_endpoint": f"{ISSUER}/userinfo",
                "id_token_signing_alg_values_supported": ["RS256"]}

    def get(self, url, **_):
        if url == f"{ISSUER}/.well-known/openid-configuration":
            return httpx.Response(200, json=self.discovery(), request=httpx.Request("GET", url))
        if url == f"{ISSUER}/jwks":
            return httpx.Response(200, json=self.jwks, request=httpx.Request("GET", url))
        return httpx.Response(404, request=httpx.Request("GET", url))

    def post(self, url, data=None, auth=None, **_):
        assert url == f"{ISSUER}/token" and data["grant_type"] == "authorization_code"
        assert auth == ("finvault", "client-secret")
        q = self.last_authorize
        challenge = base64.urlsafe_b64encode(hashlib.sha256(data["code_verifier"].encode()).digest()).rstrip(b"=").decode()
        assert challenge == q["code_challenge"] and q["code_challenge_method"] == "S256"  # PKCE
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": "finvault", "sub": "user-123", "iat": now, "exp": now + 300,
                  "nonce": self.nonce_override or q["nonce"], "email": "a@home.lan", "email_verified": True} | self.claims
        token = jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": "k1"})
        return httpx.Response(200, json={"id_token": token, "access_token": "at", "token_type": "Bearer"},
                              request=httpx.Request("POST", url))


@pytest.fixture()
def provider(monkeypatch):
    p = FakeProvider()
    for k, v in {"OIDC_ENABLED": True, "OIDC_PROVIDER_NAME": "Authentik", "OIDC_CLIENT_ID": "finvault",
                 "OIDC_DISCOVERY_URL": f"{ISSUER}/.well-known/openid-configuration", "OIDC_CLIENT_SECRET": "client-secret",
                 "OIDC_ALLOW_SIGNUP": False, "OIDC_REDIRECT_URI": ""}.items():
        monkeypatch.setattr(config_admin, k, v)
    monkeypatch.setattr(op.httpx, "get", p.get)
    monkeypatch.setattr(op.httpx, "post", p.post)
    op.reset_cache()
    yield p
    op.reset_cache()


def sso(client, provider, state=None):
    r = client.get("/api/auth/oidc/login", params={"next": "/transactions"}, follow_redirects=False)
    assert r.status_code == 302, r.text
    loc = urlsplit(r.headers["location"])
    assert f"{loc.scheme}://{loc.netloc}{loc.path}" == f"{ISSUER}/authorize"
    provider.last_authorize = {k: v[0] for k, v in parse_qs(loc.query).items()}
    assert provider.last_authorize["redirect_uri"] == "http://testserver/api/auth/oidc/callback"
    return client.get("/api/auth/oidc/callback", params={"code": "c0de", "state": state or provider.last_authorize["state"]},
                      follow_redirects=False)


def test_status_advertises_sso(client, provider):
    s = client.get("/api/auth/status").json()
    assert s["oidc"]["enabled"] and s["oidc"]["provider_name"] == "Authentik" and s["local_auth_enabled"]


def test_sso_success_signs_in_existing_member_and_skips_totp(client, provider):
    register(client)
    secret = client.post("/api/auth/2fa/setup").json()["secret"]
    client.post("/api/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()})
    client.post("/api/auth/logout")
    r = sso(client, provider)
    assert r.status_code == 302 and r.headers["location"] == "/transactions"
    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["email"] == "a@home.lan"
    ok = events(client, event="auth.sso_login")["items"][0]
    assert ok["detail"]["skipped_2fa"] is True
    # The identity is linked by subject: a later email change at the provider still maps to the same member.
    client.post("/api/auth/logout")
    provider.claims = {"email": "renamed@home.lan"}
    assert sso(client, provider).headers["location"] == "/transactions"
    assert client.get("/api/auth/me").json()["email"] == "a@home.lan"


def test_sso_bad_state_is_rejected(client, provider):
    register(client)
    client.post("/api/auth/logout")
    r = sso(client, provider, state="forged-state")
    assert r.status_code == 302 and r.headers["location"] == "/login?sso_error=bad_state"
    assert client.get("/api/auth/me").status_code == 401
    # No flow cookie at all (a callback opened in another browser) is also rejected.
    client.cookies.clear()
    r = client.get("/api/auth/oidc/callback", params={"code": "x", "state": "y"}, follow_redirects=False)
    assert r.headers["location"] == "/login?sso_error=bad_state"


def test_sso_bad_nonce_is_rejected(client, provider):
    register(client)
    client.post("/api/auth/logout")
    provider.nonce_override = "replayed-nonce"
    r = sso(client, provider)
    assert r.headers["location"] == "/login?sso_error=bad_nonce"
    assert client.get("/api/auth/me").status_code == 401


def test_sso_rejects_bad_signature_and_wrong_audience(client, provider):
    register(client)
    client.post("/api/auth/logout")
    provider.claims = {"aud": "some-other-app"}
    assert sso(client, provider).headers["location"] == "/login?sso_error=invalid_token"
    provider.claims = {}
    provider.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)  # not the published key
    assert sso(client, provider).headers["location"] == "/login?sso_error=invalid_token"
    assert client.get("/api/auth/me").status_code == 401


def test_sso_unknown_email_with_signup_off(client, provider):
    register(client)
    client.post("/api/auth/logout")
    provider.claims = {"email": "stranger@home.lan", "sub": "someone-else"}
    r = sso(client, provider)
    assert r.headers["location"] == "/login?sso_error=no_account"
    assert client.get("/api/auth/me").status_code == 401
    client.post("/api/auth/login", json={"email": "a@home.lan", "password": PW})
    failed = events(client, event="auth.sso_failed")["items"][0]
    assert failed["email"] == "stranger@home.lan" and failed["detail"]["reason"] == "no_account"


def test_sso_unverified_email_is_not_matched(client, provider):
    register(client)
    client.post("/api/auth/logout")
    provider.claims = {"email_verified": False}
    assert sso(client, provider).headers["location"] == "/login?sso_error=email_not_verified"


def test_sso_signup_follows_registration_mode(client, provider, monkeypatch):
    register(client)
    client.post("/api/auth/logout")
    monkeypatch.setattr(config_admin, "OIDC_ALLOW_SIGNUP", True)
    provider.claims = {"email": "new@home.lan", "sub": "new-sub", "name": "New"}
    assert sso(client, provider).headers["location"] == "/login?sso_error=invite_required"  # default mode is invite
    client.post("/api/auth/login", json={"email": "a@home.lan", "password": PW})
    client.patch("/api/admin/settings", json={"registration_mode": "open"})
    client.post("/api/auth/logout")
    assert sso(client, provider).headers["location"] == "/transactions"
    me = client.get("/api/auth/me").json()
    assert me["email"] == "new@home.lan" and not me["is_admin"]


def test_local_auth_off_blocks_password_sign_in(client, provider, monkeypatch):
    register(client)
    client.post("/api/auth/logout")
    monkeypatch.setattr(config_admin, "LOCAL_AUTH_ENABLED", False)
    assert client.get("/api/auth/status").json()["local_auth_enabled"] is False
    assert client.post("/api/auth/login", json={"email": "a@home.lan", "password": PW}).status_code == 403
    assert client.post("/api/auth/register", json={"email": "z@home.lan", "password": PW}).status_code == 403
    assert sso(client, provider).status_code == 302
    assert client.get("/api/auth/me").status_code == 200
