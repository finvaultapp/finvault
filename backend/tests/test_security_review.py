"""Regression tests for the security review: SSO linking, outbound URL checks, the watched folder, upload limits,
sign-in timing and the 2FA step, and reset links after a password change."""
import io
import os
import struct
import time
import zipfile

import pyotp
import pytest
from sqlalchemy import select

from app import config, security
from app.db import SessionLocal
from app.importers import migrate as migrate_importer
from app.importers import holdings
from app.models import Transaction, User
from app.models_account import PasswordResetToken
from app.models_admin import OidcIdentity
from app.routers import auth as auth_router
from app.services import net
from app.services import password_reset as pr
from tests.test_admin_features import FakeProvider, provider, sso  # noqa: F401  (provider is a fixture)
from tests.test_api import PW, register
from tests.test_features import TD

WATCH_CSV = TD


def new_member(client, email):
    r = client.post("/api/admin/users", json={"email": email, "password": PW, "name": email.split("@")[0]})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def signed_in(email):
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    c.headers["X-FinVault"] = "1"
    r = c.post("/api/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 200, r.text
    return c


# --- Single sign-on: a member already linked to a provider account isn't matched by email again ----------------

def test_sso_does_not_link_a_second_provider_account_by_email(client, provider):
    register(client)
    client.post("/api/auth/logout")
    assert sso(client, provider).headers["location"] == "/transactions"  # first sign-in links subject user-123
    client.post("/api/auth/logout")
    client.cookies.clear()

    # Someone else now holds a@home.lan at the provider (recycled or renamed account): a different subject.
    provider.claims = {"sub": "someone-else", "email": "a@home.lan", "email_verified": True}
    r = sso(client, provider)
    assert r.status_code == 302 and r.headers["location"] == "/login?sso_error=already_linked"
    assert client.get("/api/auth/me").status_code == 401
    with SessionLocal() as db:
        assert [i.subject for i in db.scalars(select(OidcIdentity))] == ["user-123"]

    # The original provider account still works.
    provider.claims = {}
    assert sso(client, provider).headers["location"] == "/transactions"
    assert client.get("/api/auth/me").json()["email"] == "a@home.lan"


# --- Outbound URLs: shared address space (Tailscale / CGNAT) and other non-public ranges are refused ----------

@pytest.mark.parametrize("url", ["http://100.100.100.100/topic", "https://100.64.0.1/x", "http://198.18.0.1/x",
                                 "http://[::ffff:127.0.0.1]/x", "http://127.0.0.1/x", "http://192.168.1.2/x"])
def test_outbound_url_rejects_non_public_addresses(url, monkeypatch):
    monkeypatch.setattr(config, "ALLOW_PRIVATE_OUTBOUND_URLS", False)
    with pytest.raises(ValueError):
        net.validate_outbound_url(url)


def test_outbound_url_allows_public_addresses_and_admin_override(monkeypatch):
    monkeypatch.setattr(config, "ALLOW_PRIVATE_OUTBOUND_URLS", False)
    assert net.validate_outbound_url("https://8.8.8.8/topic") == "https://8.8.8.8/topic"
    assert net.validate_outbound_url("http://100.100.100.100/x", allow_private=True)


def test_member_cannot_point_ntfy_at_a_tailnet_host(client, monkeypatch):
    monkeypatch.setattr(config, "ALLOW_PRIVATE_OUTBOUND_URLS", False)
    register(client)
    r = client.put("/api/notifications", json={"ntfy_url": "http://100.101.102.103/finvault"})
    assert r.status_code == 422
    assert client.get("/api/notifications").json()["ntfy_url"] == ""


# --- Watched folder: "Scan now" is per member, and links are never followed ------------------------------------

def _watch(c, name, tmp_path):
    acct = c.post("/api/accounts", json={"name": name}).json()
    status = c.put(f"/api/inbox/accounts/{acct['id']}", json={"watch": True}).json()
    folder = tmp_path / next(a["folder"] for a in status["accounts"] if a["id"] == acct["id"])
    assert folder.is_dir()
    return acct, folder


def _drop(path, text):
    path.write_text(text)
    old = time.time() - 600
    os.utime(path, (old, old))


def test_scan_now_only_imports_the_members_own_folders(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "IMPORT_WATCH_DIR", tmp_path)
    register(client)
    client.patch("/api/admin/settings", json={"folder_import_enabled": True})
    new_member(client, "sam@home.lan")
    sam = signed_in("sam@home.lan")
    _, admin_folder = _watch(client, "Admin chequing", tmp_path)
    _, sam_folder = _watch(sam, "Sam chequing", tmp_path)
    _drop(admin_folder / "a.csv", WATCH_CSV)
    _drop(sam_folder / "s.csv", WATCH_CSV)

    assert sam.post("/api/inbox/scan").json()["imported"] == 2
    assert (admin_folder / "a.csv").exists()  # the admin's file is left for their own scan
    assert not (sam_folder / "s.csv").exists()
    assert client.post("/api/inbox/scan").json()["imported"] == 2


def test_watched_folder_ignores_links_to_other_files(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "IMPORT_WATCH_DIR", tmp_path)
    register(client)
    client.patch("/api/admin/settings", json={"folder_import_enabled": True})
    new_member(client, "sam@home.lan")
    sam = signed_in("sam@home.lan")
    _, admin_folder = _watch(client, "Admin chequing", tmp_path)
    _, sam_folder = _watch(sam, "Sam chequing", tmp_path)
    private = admin_folder / "imported" / "20260901-000000-statement.csv"
    _drop(private, WATCH_CSV)
    link = sam_folder / "steal.csv"
    try:
        os.symlink(private, link)
    except (OSError, NotImplementedError):
        pytest.skip("this system can't create symbolic links")
    old = time.time() - 600
    os.utime(link, (old, old), follow_symlinks=False)

    assert sam.post("/api/inbox/scan").json()["imported"] == 0
    with SessionLocal() as db:
        sam_id = db.scalar(select(User.id).where(User.email == "sam@home.lan"))
        assert db.scalar(select(Transaction.id).where(Transaction.user_id == sam_id)) is None
    assert private.exists()


# --- Upload limits ---------------------------------------------------------------------------------------------

def test_investment_import_does_not_read_past_the_size_limit(client, monkeypatch):
    register(client)
    acct = client.post("/api/accounts", json={"name": "TFSA", "type": "investment"}).json()
    monkeypatch.setattr(holdings, "MAX_BYTES", 1000)
    from app.routers import investments
    monkeypatch.setattr(investments, "MAX_BYTES", 1000)
    seen = {}
    real = investments.parse_investment_file

    def spy(filename, raw, source=None):
        seen["len"] = len(raw)
        return real(filename, raw, source)

    monkeypatch.setattr(investments, "parse_investment_file", spy)
    r = client.post("/api/invest/import/preview", data={"account_id": str(acct["id"])},
                    files={"file": ("big.csv", io.BytesIO(b"a,b\n" * 5000), "text/csv")})
    assert r.status_code == 422 and "larger than 15 MB" in r.json()["detail"]
    assert seen["len"] == 1001


def test_migration_zip_with_a_lying_size_is_a_clean_error(client):
    register(client)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("register.csv", b"0" * 200_000)
    raw = bytearray(buf.getvalue())
    cd = raw.rfind(b"PK\x01\x02")
    raw[cd + 24:cd + 28] = struct.pack("<I", 10)  # claims 10 bytes; inflates to 200 kB
    raw[22:26] = struct.pack("<I", 10)
    with pytest.raises(ValueError):
        migrate_importer.expand_files([("export.zip", bytes(raw))])
    r = client.post("/api/migrate/analyze", files=[("files", ("export.zip", bytes(raw), "application/zip"))])
    assert r.status_code == 422 and r.json()["detail"] == "That zip file could not be opened."


def test_new_upload_routes_still_require_the_csrf_header(client):
    register(client)
    acct = client.post("/api/accounts", json={"name": "TFSA", "type": "investment"}).json()
    for path, data in (("/api/invest/import/preview", {"account_id": str(acct["id"])}),
                       ("/api/migrate/analyze", {})):
        name = "file" if "invest" in path else "files"
        r = client.post(path, data=data, files=[(name, ("x.csv", b"a,b\n1,2\n", "text/csv"))],
                        headers={"X-FinVault": ""})
        assert r.status_code == 403 and r.json()["detail"] == "Missing X-FinVault header"


# --- Sign-in ---------------------------------------------------------------------------------------------------

def test_unknown_email_still_spends_a_password_check(client, monkeypatch):
    register(client)
    client.post("/api/auth/logout")
    calls = []
    real = security.verify_password
    monkeypatch.setattr(security, "verify_password", lambda pw, h: calls.append(h) or real(pw, h))
    r = client.post("/api/auth/login", json={"email": "nobody@home.lan", "password": "whatever-password"})
    assert r.status_code == 401
    assert len(calls) == 1 and calls[0] == auth_router._dummy_hash[0]


def _totp_member(client):
    register(client)
    secret = client.post("/api/auth/2fa/setup").json()["secret"]
    client.post("/api/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()})
    client.post("/api/auth/logout")
    return secret


def test_2fa_step_ends_when_sessions_are_revoked_in_between(client):
    secret = _totp_member(client)
    r = client.post("/api/auth/login", json={"email": "a@home.lan", "password": PW}).json()
    assert r["requires_2fa"]
    with SessionLocal() as db:  # e.g. the password was reset, or "sign out everywhere", after the password step
        u = db.scalar(select(User).where(User.email == "a@home.lan"))
        u.token_version += 1
        db.commit()
    bad = client.post("/api/auth/login/2fa", json={"challenge": r["challenge"], "code": pyotp.TOTP(secret).now()})
    assert bad.status_code == 401 and bad.json()["detail"] == "Sign-in expired. Enter your password again."
    assert client.get("/api/auth/me").status_code == 401


def test_2fa_step_refuses_a_member_turned_off_in_between(client):
    secret = _totp_member(client)
    r = client.post("/api/auth/login", json={"email": "a@home.lan", "password": PW}).json()
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == "a@home.lan"))
        u.is_active = False
        db.commit()
    bad = client.post("/api/auth/login/2fa", json={"challenge": r["challenge"], "code": pyotp.TOTP(secret).now()})
    assert bad.status_code == 401


# --- Reset links stop working once the member changes their password themselves -------------------------------

def test_changing_password_cancels_open_reset_links(client):
    register(client)
    sam_id = new_member(client, "sam@home.lan")
    link = client.post(f"/api/admin/users/{sam_id}/password-reset").json()
    token = link["path"].split("#token=", 1)[1]
    sam = signed_in("sam@home.lan")
    assert sam.post("/api/password-reset/check", json={"token": token}).status_code == 200
    r = sam.post("/api/auth/password", json={"current_password": PW, "new_password": "another long password"})
    assert r.status_code == 200
    pr.token_ip_throttle.hits.clear()
    assert sam.post("/api/password-reset/check", json={"token": token}).status_code == 400
    with SessionLocal() as db:
        assert all(t.used_at is not None for t in db.scalars(select(PasswordResetToken)))
