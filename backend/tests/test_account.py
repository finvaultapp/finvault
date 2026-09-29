"""Password reset links (admin and self-service) and the member's own data export."""
import csv
import hashlib
import io
import json
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import config, config_admin, security
from app.db import SessionLocal
from app.main import app
from app.models import (Account, Asset, AssetValue, Category, Person, PlanEntry, RegisteredPlan, Share,
                        SyncConnection, Transaction, TransactionSplit, User)
from app.models_account import PasswordResetToken
from app.models_admin import AuditEvent
from app.models_ai import AiMerchantSuggestion
from app.models_invest import Security, SecurityPrice
from app.services import data_export, notify, receipts
from app.services import password_reset as pr

PW = "correct horse battery"
NEW_PW = "a brand new passphrase"


@pytest.fixture(autouse=True)
def _fresh_throttles():
    for th in (pr.request_email_throttle, pr.request_ip_throttle, pr.token_ip_throttle):
        th.hits.clear()
    yield


def new_client() -> TestClient:
    c = TestClient(app)
    c.headers["X-FinVault"] = "1"
    return c


def setup_household(client):
    """Admin signed in on `client`; returns (admin id, member id)."""
    r = client.post("/api/auth/register", json={"email": "admin@home.lan", "password": PW, "name": "Admin"})
    assert r.status_code == 200, r.text
    m = client.post("/api/admin/users", json={"email": "sam@home.lan", "password": PW, "name": "Sam"})
    assert m.status_code == 200, m.text
    return r.json()["id"], m.json()["id"]


def sign_in(email, password=PW) -> TestClient:
    c = new_client()
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200 and not r.json()["requires_2fa"], r.text
    return c


def token_of(link: dict) -> str:
    assert link["path"].startswith("/reset-password#token=")
    return link["path"].split("#token=", 1)[1]


def events(name):
    with SessionLocal() as db:
        return list(db.scalars(select(AuditEvent).where(AuditEvent.event == name)))


# --- Admin reset links ---------------------------------------------------------------------------

def test_only_admins_create_links(client):
    _, sam = setup_household(client)
    member = sign_in("sam@home.lan")
    assert member.post(f"/api/admin/users/{sam}/password-reset").status_code == 403
    assert new_client().post(f"/api/admin/users/{sam}/password-reset").status_code == 401
    assert client.post("/api/admin/users/9999/password-reset").status_code == 404
    with SessionLocal() as db:
        assert db.scalar(select(PasswordResetToken)) is None


def test_admin_link_is_hashed_single_use_and_revokes_sessions(client):
    _, sam = setup_household(client)
    member = sign_in("sam@home.lan")
    assert member.get("/api/auth/me").status_code == 200

    link = client.post(f"/api/admin/users/{sam}/password-reset").json()
    raw = token_of(link)
    assert link["url"] is None and link["hours"] == 24 and link["needs_2fa"] is False  # no PUBLIC_URL in tests
    with SessionLocal() as db:
        row = db.scalar(select(PasswordResetToken))
        assert row.token_hash == hashlib.sha256(raw.encode()).hexdigest() and row.token_hash != raw
        assert row.via == "admin"
        exp = row.expires_at.replace(tzinfo=timezone.utc)
        assert timedelta(hours=23, minutes=59) < exp - datetime.now(timezone.utc) <= timedelta(hours=24)
    # The raw token is nowhere in the database or the audit log.
    for f in config.DATA_DIR.glob("test.db*"):
        assert raw.encode() not in f.read_bytes()

    anon = new_client()
    assert anon.post("/api/password-reset/check", json={"token": raw}).json() == {
        "email": "sam@home.lan", "needs_2fa": False, "expires_at": link["expires_at"]}
    assert anon.post("/api/password-reset/complete", json={"token": raw, "new_password": "short"}).status_code == 422
    r = anon.post("/api/password-reset/complete", json={"token": raw, "new_password": NEW_PW})
    assert r.status_code == 200, r.text

    # Every existing session is signed out, the old password is gone and the link can't be used again.
    assert member.get("/api/auth/me").status_code == 401
    assert new_client().post("/api/auth/login", json={"email": "sam@home.lan", "password": PW}).status_code == 401
    sign_in("sam@home.lan", NEW_PW)
    again = anon.post("/api/password-reset/complete", json={"token": raw, "new_password": "yet another password"})
    assert again.status_code == 400
    assert anon.post("/api/password-reset/check", json={"token": raw}).status_code == 400

    made, used = events("admin.password_reset_link"), events("auth.password_reset")
    assert len(made) == 1 and made[0].target_user_id == sam and made[0].email == "admin@home.lan"
    assert len(used) == 1 and used[0].user_id == sam and json.loads(used[0].detail)["via"] == "admin"
    assert raw not in json.dumps([(e.detail, e.email) for e in made + used])


def test_expired_and_replaced_links_fail(client):
    _, sam = setup_household(client)
    first = token_of(client.post(f"/api/admin/users/{sam}/password-reset").json())
    second = token_of(client.post(f"/api/admin/users/{sam}/password-reset").json())
    anon = new_client()
    # A newer link cancels the older one.
    assert anon.post("/api/password-reset/check", json={"token": first}).status_code == 400
    assert anon.post("/api/password-reset/check", json={"token": second}).status_code == 200
    with SessionLocal() as db:
        row = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == pr.hash_token(second)))
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert anon.post("/api/password-reset/check", json={"token": second}).status_code == 400
    assert anon.post("/api/password-reset/complete", json={"token": second, "new_password": NEW_PW}).status_code == 400
    assert anon.post("/api/password-reset/complete", json={"token": "made-up", "new_password": NEW_PW}).status_code == 400
    sign_in("sam@home.lan")  # password unchanged


def test_inactive_member_gets_no_link(client):
    _, sam = setup_household(client)
    raw = token_of(client.post(f"/api/admin/users/{sam}/password-reset").json())
    client.patch(f"/api/admin/users/{sam}", json={"is_active": False})
    assert new_client().post("/api/password-reset/check", json={"token": raw}).status_code == 400
    assert client.post(f"/api/admin/users/{sam}/password-reset").status_code == 409


def test_guessing_tokens_is_throttled(client):
    setup_household(client)
    anon = new_client()
    codes = [anon.post("/api/password-reset/check", json={"token": f"guess-{i}"}).status_code for i in range(22)]
    assert codes[:20] == [400] * 20 and codes[20:] == [429, 429]


def test_two_factor_members_also_need_a_code(client):
    _, sam = setup_household(client)
    secret = pyotp.random_base32()
    codes, hashes = security.new_recovery_codes()
    with SessionLocal() as db:
        u = db.get(User, sam)
        u.totp_secret, u.totp_enabled, u.recovery_codes = security.encrypt(secret), True, json.dumps(hashes)
        db.commit()
    link = client.post(f"/api/admin/users/{sam}/password-reset").json()
    raw = token_of(link)
    assert link["needs_2fa"] is True
    anon = new_client()
    assert anon.post("/api/password-reset/check", json={"token": raw}).json()["needs_2fa"] is True
    for code in ("", "000000", "abc123-def456"):
        r = anon.post("/api/password-reset/complete", json={"token": raw, "new_password": NEW_PW, "code": code})
        assert r.status_code == 401, r.text
    assert events("auth.password_reset_failed")
    # Wrong codes don't burn the link. A recovery code works once and is used up.
    r = anon.post("/api/password-reset/complete", json={"token": raw, "new_password": NEW_PW, "code": codes[0]})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        left = json.loads(db.get(User, sam).recovery_codes)
    assert len(left) == 7 and hashes[0] not in left

    # A current authenticator code works too.
    raw2 = token_of(client.post(f"/api/admin/users/{sam}/password-reset").json())
    r = anon.post("/api/password-reset/complete",
                  json={"token": raw2, "new_password": "third password here", "code": pyotp.TOTP(secret).now()})
    assert r.status_code == 200, r.text


def test_sso_only_servers_refuse(client, monkeypatch):
    _, sam = setup_household(client)
    raw = token_of(client.post(f"/api/admin/users/{sam}/password-reset").json())
    monkeypatch.setattr(config_admin, "LOCAL_AUTH_ENABLED", False)
    anon = new_client()
    assert client.post(f"/api/admin/users/{sam}/password-reset").status_code == 403
    assert anon.post("/api/password-reset/check", json={"token": raw}).status_code == 403
    assert anon.post("/api/password-reset/complete", json={"token": raw, "new_password": NEW_PW}).status_code == 403
    assert anon.post("/api/password-reset/request", json={"email": "sam@home.lan"}).status_code == 403
    assert anon.get("/api/password-reset/options").json()["self_service"] is False


# --- Self-service by email ------------------------------------------------------------------------

@pytest.fixture()
def mail(monkeypatch):
    sent = []
    monkeypatch.setattr(config, "SMTP_HOST", "smtp.home.lan")
    monkeypatch.setattr(config, "SMTP_FROM", "finvault@home.lan")
    monkeypatch.setattr(pr, "PUBLIC_URL", "https://money.home.lan")
    monkeypatch.setattr(notify, "send_email", lambda to, subject, body: sent.append((to, subject, body)))
    return sent


def test_self_service_needs_smtp_and_public_url(client, monkeypatch):
    setup_household(client)
    anon = new_client()
    assert anon.get("/api/password-reset/options").json()["self_service"] is False
    assert anon.post("/api/password-reset/request", json={"email": "sam@home.lan"}).status_code == 409
    monkeypatch.setattr(config, "SMTP_HOST", "smtp.home.lan")
    monkeypatch.setattr(config, "SMTP_FROM", "finvault@home.lan")
    assert anon.get("/api/password-reset/options").json()["self_service"] is False  # still no PUBLIC_URL
    monkeypatch.setattr(pr, "PUBLIC_URL", "money.home.lan")  # not a URL: ignored
    assert anon.get("/api/password-reset/options").json()["self_service"] is False
    monkeypatch.setattr(pr, "PUBLIC_URL", "https://money.home.lan")
    assert anon.get("/api/password-reset/options").json()["self_service"] is True


def test_self_service_does_not_reveal_accounts_and_ignores_host_header(client, mail):
    _, sam = setup_household(client)
    anon = new_client()
    known = anon.post("/api/password-reset/request", json={"email": "Sam@home.lan"}, headers={"Host": "evil.example"})
    unknown = anon.post("/api/password-reset/request", json={"email": "nobody@home.lan"}, headers={"Host": "evil.example"})
    assert known.status_code == unknown.status_code == 200
    assert known.content == unknown.content
    assert len(mail) == 1 and mail[0][0] == "sam@home.lan"
    body = mail[0][2]
    assert "evil.example" not in body and "https://money.home.lan/reset-password#token=" in body
    raw = body.split("#token=", 1)[1].split()[0]
    with SessionLocal() as db:
        row = db.scalar(select(PasswordResetToken))
        assert row.via == "email" and row.token_hash == pr.hash_token(raw)
        assert row.expires_at.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc) <= timedelta(hours=1)
    assert anon.post("/api/password-reset/complete", json={"token": raw, "new_password": NEW_PW}).status_code == 200
    sign_in("sam@home.lan", NEW_PW)
    requested = events("auth.password_reset_requested")
    assert {json.loads(e.detail).get("reason") for e in requested} == {None, "unknown_email"}
    assert json.loads(events("auth.password_reset")[0].detail)["via"] == "email"


def test_self_service_is_rate_limited_per_email_and_ip(client, mail):
    setup_household(client)
    anon = new_client()
    for email in ("sam@home.lan", "nobody@home.lan"):  # same limit whether or not the account exists
        codes = [anon.post("/api/password-reset/request", json={"email": email}).status_code for _ in range(4)]
        assert codes == [200, 200, 200, 429], email
    assert len(mail) == 3
    # Per IP: 10 requests an hour, whichever addresses they name (6 used above).
    codes = [anon.post("/api/password-reset/request", json={"email": f"x{i}@home.lan"}).status_code for i in range(5)]
    assert codes == [200, 200, 200, 200, 429]


# --- Download all my data -------------------------------------------------------------------------

def _seed(db, uid: int, tag: str) -> dict:
    """A bit of everything for one member; returns secret values that must never be exported."""
    u = db.get(User, uid)
    totp = pyotp.random_base32()
    _, hashes = security.new_recovery_codes()
    u.totp_secret, u.totp_enabled, u.recovery_codes = security.encrypt(totp), True, json.dumps(hashes)
    u.ai_api_key = security.encrypt(f"sk-{tag}-personal-openai-key")
    u.notify_ntfy_url = f"https://ntfy.sh/{tag}-bills"
    conn = SyncConnection(user_id=uid, provider="simplefin", name=f"{tag} sync",
                          credentials=security.encrypt({"access_url": f"https://{tag}:pw@bridge/simplefin"}))
    db.add(conn)
    db.flush()
    acct = Account(user_id=uid, name=f"{tag} chequing", currency="CAD", sync_connection_id=conn.id)
    cat = Category(user_id=uid, name=f"{tag} groceries")
    person = Person(user_id=uid, name=f"{tag} roommate")
    db.add_all([acct, cat, person])
    db.flush()
    tx = Transaction(user_id=uid, account_id=acct.id, date=date(2026, 9, 1), amount=Decimal("-42.50"),
                     description=f"{tag} market, \"quoted\"", payee=f"{tag} payee", category_id=cat.id, notes="n")
    db.add(tx)
    db.flush()
    asset = Asset(user_id=uid, name=f"{tag} car")
    plan = RegisteredPlan(user_id=uid, kind="tfsa", year=2026, room=Decimal("7000"))
    sec = Security(user_id=uid, symbol=f"{tag.upper()}Q")
    db.add_all([TransactionSplit(transaction_id=tx.id, category_id=cat.id, amount=Decimal("-20"), note=tag),
                Share(transaction_id=tx.id, person_id=person.id, amount=Decimal("10")),
                AiMerchantSuggestion(user_id=uid, merchant_key=f"{tag} market", category_id=cat.id),
                asset, plan, sec])
    db.flush()
    db.add_all([AssetValue(asset_id=asset.id, date=date(2026, 1, 1), value=Decimal("9000")),
                PlanEntry(plan_id=plan.id, date=date(2026, 2, 1), amount=Decimal("500")),
                SecurityPrice(security_id=sec.id, date=date(2026, 9, 1), close=Decimal("31.5"))])
    db.commit()
    receipts.save(db, uid, tx.id, f"{tag}-receipt.png", b"\x89PNG\r\n\x1a\n" + tag.encode() * 20, "image/png")
    return {"secrets": [u.password_hash, u.totp_secret, totp, u.ai_api_key, f"sk-{tag}-personal-openai-key",
                        conn.credentials, f"https://{tag}:pw@bridge/simplefin", *hashes],
            "tag": tag}


def _export(c) -> zipfile.ZipFile:
    r = c.get("/api/account/export")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    assert "attachment" in r.headers["content-disposition"]
    return zipfile.ZipFile(io.BytesIO(r.content))


def test_export_has_everything_of_mine_and_nothing_else(client):
    admin, sam = setup_household(client)
    with SessionLocal() as db:
        seeds = {admin: _seed(db, admin, "alpha"), sam: _seed(db, sam, "bravo")}
        client.post(f"/api/admin/users/{sam}/password-reset")  # a reset token row exists too
        reset_hash = db.scalar(select(PasswordResetToken.token_hash))
        owned_ids = {uid: {t.name: {tuple(r) for r in db.execute(select(*t.primary_key.columns).where(w))}
                           for t, w in data_export.plan(uid)} for uid in seeds}
    with SessionLocal() as db:  # the fixtures' TOTP makes sign-in need a code; use a bearer token instead
        sam_client = new_client()
        sam_client.headers["Authorization"] = "Bearer " + security.create_token(sam, db.get(User, sam).token_version)
    zips = {admin: _export(client), sam: _export(sam_client)}

    for uid, zf in zips.items():
        other = sam if uid == admin else admin
        me, them = seeds[uid], seeds[other]
        names = zf.namelist()
        assert {"README.txt", "transactions.csv"} <= set(names)
        blob = b"".join(zf.read(n) for n in names).decode("utf-8", "replace")
        # No secrets of anyone, and nothing of the other member's.
        for s in me["secrets"] + them["secrets"] + [reset_hash]:
            assert s not in blob, s[:12]
        assert them["tag"] not in blob and me["tag"] in blob
        for col in data_export.DENY_COLUMNS:
            assert f'"{col}"' not in blob
        for table in data_export.DENY_TABLES:
            assert f"data/{table}.json" not in names

        tables = {n[5:-5]: json.loads(zf.read(n)) for n in names if n.startswith("data/")}
        # Every table with a user_id is discovered, and so are the child tables reached through a parent.
        from app.db import Base
        with_user_id = {t.name for t in Base.metadata.sorted_tables if "user_id" in t.c} - set(data_export.DENY_TABLES)
        assert with_user_id <= set(tables)
        for child in ("asset_values", "plan_entries", "transaction_splits", "shares", "security_prices"):
            assert len(tables[child]) == 1, child
        assert [u["id"] for u in tables["users"]] == [uid] and tables["users"][0]["notify_ntfy_url"]
        for name, rows in tables.items():
            assert all(r.get("user_id", uid) == uid for r in rows), name
            pk = [c.name for c in Base.metadata.tables[name].primary_key.columns]
            got = {tuple(r[c] for c in pk) for r in rows}
            assert got == owned_ids[uid][name], name
            assert not got & owned_ids[other][name], name

        # Receipts: mine only, with the original bytes.
        rec = [n for n in names if n.startswith("receipts/")]
        assert len(rec) == 1 and rec[0].endswith(f"{me['tag']}-receipt.png")
        assert zf.read(rec[0]) == b"\x89PNG\r\n\x1a\n" + me["tag"].encode() * 20
        readme = zf.read("README.txt").decode()
        assert "password hash" in readme and "two-factor" in readme and "provider credentials" in readme

    # transactions.csv is byte for byte what the Transactions export gives.
    assert zips[admin].read("transactions.csv").decode("utf-8") == client.get("/api/transactions/export").text
    rows = list(csv.reader(io.StringIO(zips[sam].read("transactions.csv").decode("utf-8-sig"))))
    assert rows[0][0] == "Date" and rows[1][1] == "bravo chequing" and rows[1][5] == "-42.50"

    exported = events("account.data_exported")
    assert {e.user_id for e in exported} == {admin, sam}
    assert json.loads(exported[0].detail)["receipts"] == 1


def test_export_needs_sign_in(client):
    assert client.get("/api/account/export").status_code == 401


def test_secretish_columns_added_later_are_dropped():
    assert data_export._drop("webhook_secret") and data_export._drop("refresh_token") and data_export._drop("password_hash")
    assert not data_export._drop("import_hash") and not data_export._drop("notify_email")
