import io
import json
from datetime import date, timedelta

import pyotp

from app.security import decrypt

PW = "correct horse battery"


def register(c, email="a@home.lan", **extra):
    r = c.post("/api/auth/register", json={"email": email, "password": PW, "name": "A", **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_first_user_is_admin_and_registration_is_invite_only(client):
    u = register(client)
    assert u["is_admin"]
    client.post("/api/auth/logout")
    r = client.post("/api/auth/register", json={"email": "b@home.lan", "password": PW})
    assert r.status_code == 403
    # Admin creates an invite, then the second person can join.
    client.post("/api/auth/login", json={"email": "a@home.lan", "password": PW})
    code = client.post("/api/admin/invites", json={"note": "partner"}).json()["code"]
    client.post("/api/auth/logout")
    b = register(client, "b@home.lan", invite_code=code)
    assert not b["is_admin"]
    assert client.get("/api/admin/users").status_code == 403


def test_csrf_header_required(client):
    register(client)
    r = client.post("/api/accounts", json={"name": "X"}, headers={"X-FinVault": ""})
    assert r.status_code == 403


def test_two_factor_login(client):
    register(client)
    setup = client.post("/api/auth/2fa/setup").json()
    code = pyotp.TOTP(setup["secret"]).now()
    rec = client.post("/api/auth/2fa/enable", json={"code": code}).json()["recovery_codes"]
    client.post("/api/auth/logout")
    r = client.post("/api/auth/login", json={"email": "a@home.lan", "password": PW}).json()
    assert r["requires_2fa"]
    assert client.get("/api/auth/me").status_code == 401
    bad = client.post("/api/auth/login/2fa", json={"challenge": r["challenge"], "code": "000000"})
    assert bad.status_code == 401
    ok = client.post("/api/auth/login/2fa", json={"challenge": r["challenge"], "code": rec[0]})
    assert ok.status_code == 200
    assert client.get("/api/auth/me").json()["totp_enabled"]


def test_users_cannot_see_each_others_data(client):
    register(client)
    acct = client.post("/api/accounts", json={"name": "Joint", "currency": "CAD"}).json()
    code = client.post("/api/admin/invites", json={}).json()["code"]
    client.post("/api/auth/logout")
    register(client, "b@home.lan", invite_code=code)
    assert client.get("/api/accounts").json()["items"] == []
    assert client.patch(f"/api/accounts/{acct['id']}", json={"name": "mine"}).status_code == 404


TD = "01/03/2026,SHOPPERS DRUG MART #123,23.10,,1500.00\n01/04/2026,E-TRANSFER FROM JANE,,200.00,1700.00\n01/05/2026,SHOPPERS DRUG MART #456,10.00,,1690.00\n"


def upload(c, path, account_id, text, options=None):
    return c.post(path, data={"account_id": str(account_id), "options": json.dumps(options or {})},
                  files={"file": ("activity.csv", io.BytesIO(text.encode()), "text/csv")})


def test_import_dedupe_rules_and_undo(client):
    register(client)
    acct = client.post("/api/accounts", json={"name": "TD Chequing", "currency": "CAD", "import_preset": "td"}).json()
    cats = {c["name"]: c["id"] for c in client.get("/api/categories").json()}
    prev = upload(client, "/api/imports/preview", acct["id"], TD).json()
    assert prev["new"] == 3 and prev["duplicates"] == 0

    client.post("/api/rules", json={"pattern": "shoppers", "set_category_id": cats["Health"]})
    res = upload(client, "/api/imports/commit", acct["id"], TD).json()
    assert res["imported"] == 3 and res["skipped"] == 0 and "transfers_matched" in res
    again = upload(client, "/api/imports/commit", acct["id"], TD).json()
    assert again["imported"] == 0 and again["skipped"] == 3

    txs = client.get("/api/transactions", params={"q": "shoppers"}).json()
    assert txs["total"] == 2 and all(t["category_name"] == "Health" for t in txs["items"])
    assert client.get("/api/accounts").json()["items"][0]["balance"] == 166.9

    csv_out = client.get("/api/transactions/export", params={"format": "csv"}).text
    assert "SHOPPERS DRUG MART #123" in csv_out
    ofx_out = client.get("/api/transactions/export", params={"format": "ofx"}).text
    assert "<STMTTRN>" in ofx_out

    assert client.delete(f"/api/imports/batches/{res['batch_id']}").json()["removed"] == 3
    assert client.get("/api/transactions").json()["total"] == 0


def test_currency_warning_and_conversion(client):
    register(client)
    client.post("/api/accounts", json={"name": "US Chequing", "currency": "USD", "opening_balance": 100})
    client.post("/api/accounts", json={"name": "Chequing", "currency": "CAD", "opening_balance": 50})
    dash = client.get("/api/reports/dashboard").json()
    assert any(w["pair"] == "USD→CAD" for w in dash["warnings"])
    assert dash["net_worth"]["current"]["net"] == 50.0
    client.post("/api/currency/rates", json={"base": "USD", "quote": "CAD", "rate": 1.4,
                                             "date": (date.today() - timedelta(days=400)).isoformat()})
    dash = client.get("/api/reports/dashboard").json()
    assert dash["warnings"] == []
    assert dash["net_worth"]["current"]["net"] == 190.0 and dash["total_balance"] == 190.0


def test_budgets_recurring_goals_assets(client):
    register(client)
    acct = client.post("/api/accounts", json={"name": "Chequing", "opening_balance": 1000}).json()
    cats = {c["name"]: c["id"] for c in client.get("/api/categories").json()}
    today = date.today()
    client.post("/api/transactions", json={"account_id": acct["id"], "date": today.isoformat(), "amount": -80,
                                           "description": "Metro", "category_id": cats["Groceries"]})
    client.put("/api/budgets", json={"category_id": cats["Groceries"], "amount": 400})
    b = client.get("/api/budgets").json()["items"][0]
    assert b["spent"] == 80 and b["remaining"] == 320

    client.post("/api/recurring", json={"name": "Netflix", "amount": -16.99, "account_id": acct["id"],
                                        "frequency": "monthly", "next_date": (today - timedelta(days=40)).isoformat(),
                                        "auto_post": True})
    rec = client.get("/api/recurring").json()
    assert rec["items"][0]["next_date"] > today.isoformat()
    assert client.get("/api/transactions", params={"q": "netflix"}).json()["total"] == 2

    client.post("/api/goals", json={"name": "Emergency fund", "target_amount": 1000, "saved_amount": 250})
    assert client.get("/api/goals").json()[0]["percent"] == 25.0

    client.post("/api/assets", json={"name": "Car", "kind": "vehicle", "value": 12000})
    client.post("/api/assets", json={"name": "Car loan", "kind": "loan", "value": 5000})
    nw = client.get("/api/reports/net-worth").json()["current"]
    assert nw["liabilities"] == 5000.0

    ie = client.get("/api/reports/income-expense").json()
    assert ie["totals"]["expense"] > 80


def test_canadian_accounts_cannot_sync(client):
    from app import settings_store
    from app.db import SessionLocal
    from app.models import SyncConnection
    from app.security import encrypt
    from app.services import sync as s

    register(client)
    acct = client.post("/api/accounts", json={"name": "RBC", "country": "CA", "currency": "CAD"}).json()
    with SessionLocal() as db:
        settings_store.set(db, "bank_sync_enabled", True)
        conn = SyncConnection(user_id=1, provider="simplefin", credentials=encrypt({"access_url": "https://x"}))
        db.add(conn)
        db.commit()
        from app.models import Account, User
        user = db.get(User, 1)
        try:
            s.link_account(db, user, conn, {"id": "ext1", "currency": "USD"}, db.get(Account, acct["id"]))
            raised = False
        except s.SyncError:
            raised = True
        assert raised
        try:
            s.link_account(db, user, conn, {"id": "ext2", "currency": "CAD"}, None)
            raised = False
        except s.SyncError:
            raised = True
        assert raised
    status = client.get("/api/sync/status").json()
    assert "turned off for Canadian accounts" in status["canada"]


def test_ai_off_by_default(client):
    register(client)
    assert client.get("/api/ai/status").json()["server_enabled"] is False
    r = client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 403


def test_secrets_encrypted_at_rest(client):
    register(client)
    client.post("/api/auth/2fa/setup")
    from app.db import SessionLocal
    from app.models import User
    with SessionLocal() as db:
        u = db.get(User, 1)
        assert u.totp_secret and len(u.totp_secret) > 40 and decrypt(u.totp_secret)


def test_personal_openai_key(client, monkeypatch):
    from app.services import ai as ai_service
    register(client)
    body = {"provider": "openai", "api_key": "sk-test-123"}
    assert client.put("/api/ai/personal", json=body).status_code == 403  # admin hasn't allowed it

    client.patch("/api/admin/settings", json={"ai_allow_personal_keys": True})
    monkeypatch.setattr(ai_service, "list_openai_models", lambda key: ["gpt-test-mini"] if key == "sk-test-123" else [])
    status = client.put("/api/ai/personal", json=body).json()
    assert status["provider"] == "openai" and status["model"] == "gpt-test-mini"
    assert status["personal"]["key_set"] and "sk-test-123" not in str(status)

    from app.db import SessionLocal
    from app.models import User
    with SessionLocal() as db:
        stored = db.get(User, 1).ai_api_key
        assert stored and "sk-test-123" not in stored  # encrypted at rest

    # Still needs the member's own opt-in before any data is sent.
    r = client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 403 and "Turn on" in r.json()["detail"]

    sent = {}

    def fake_post(url, json, headers, timeout):
        sent.update(url=url, auth=headers.get("Authorization"), model=json["model"], has_temp="temperature" in json)

        class R:
            status_code = 200
            def json(self):
                return {"choices": [{"message": {"content": "You spent $0."}}]}
        return R()

    monkeypatch.setattr(ai_service.httpx, "post", fake_post)
    client.patch("/api/auth/me", json={"ai_opt_in": True})
    assert client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "hi"}]}).json()["reply"] == "You spent $0."
    assert sent == {"url": "https://api.openai.com/v1/chat/completions", "auth": "Bearer sk-test-123", "model": "gpt-test-mini", "has_temp": False}

    assert client.delete("/api/ai/personal").json()["personal"]["key_set"] is False
