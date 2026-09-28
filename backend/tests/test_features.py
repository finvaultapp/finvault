"""Registered plans, tax helper, splits and sharing, transfer matching, folder import, receipts, reminders."""
import io
from datetime import date, timedelta

from tests.test_api import PW, register


def setup_basic(client):
    register(client)
    chq = client.post("/api/accounts", json={"name": "Chequing", "opening_balance": 5000}).json()
    card = client.post("/api/accounts", json={"name": "Visa", "type": "credit_card"}).json()
    cats = {c["name"]: c for c in client.get("/api/categories").json()}
    return chq, card, cats


def tx(client, account, amount, desc, when=None, category=None):
    return client.post("/api/transactions", json={"account_id": account["id"], "date": (when or date.today()).isoformat(),
                                                   "amount": amount, "description": desc, "category_id": category}).json()


def test_tfsa_room_and_warnings(client):
    chq, _, cats = setup_basic(client)
    tfsa = client.post("/api/accounts", json={"name": "TFSA", "type": "investment"}).json()
    year = date.today().year
    plan = client.post("/api/plans", json={"kind": "tfsa", "year": year, "room": 7000, "account_id": tfsa["id"]}).json()
    assert plan["remaining"] == 7000
    tx(client, tfsa, 5000, "Contribution", date(year, 1, 15))
    tx(client, tfsa, 12.5, "Interest", date(year, 2, 1), cats["Interest"]["id"])  # growth, not a contribution
    plan = client.post(f"/api/plans/{plan['id']}/entries", json={"date": f"{year}-03-01", "amount": 2500, "note": "at other bank"}).json()
    assert plan["contributed"] == 7500 and plan["remaining"] == -500
    assert any(w["level"] == "danger" for w in plan["warnings"])
    tx(client, tfsa, -1000, "Withdrawal", date(year, 4, 1))
    plan = client.get("/api/plans").json()[0]
    assert plan["withdrawn"] == 1000
    assert any(w["code"] == "tfsa_withdrawn" and w["year"] == year + 1 for w in plan["warnings"])
    dup = client.post("/api/plans", json={"kind": "tfsa", "year": year, "room": 1})
    assert dup.status_code == 409


def test_rrsp_buffer(client):
    setup_basic(client)
    plan = client.post("/api/plans", json={"kind": "rrsp", "year": 2026, "room": 10000}).json()
    plan = client.post(f"/api/plans/{plan['id']}/entries", json={"date": "2026-02-01", "amount": 11500}).json()
    assert [w["level"] for w in plan["warnings"]] == ["warn"]
    plan = client.post(f"/api/plans/{plan['id']}/entries", json={"date": "2026-02-02", "amount": 1000}).json()
    assert [w["level"] for w in plan["warnings"]] == ["danger"]


def test_splits_and_tax_summary(client):
    chq, _, cats = setup_basic(client)
    year = date.today().year
    client.put(f"/api/categories/{cats['Health']['id']}/tax-tag", json={"tax_tag": "medical"})
    t = tx(client, chq, -150, "SHOPPERS DRUG MART", date(year, 1, 10))
    r = client.put(f"/api/transactions/{t['id']}/splits", json={"lines": [
        {"category_id": cats["Health"]["id"], "amount": -100, "note": "prescription"},
        {"category_id": cats["Shopping"]["id"], "amount": -50}]})
    assert r.status_code == 200 and len(r.json()["splits"]) == 2
    bad = client.put(f"/api/transactions/{t['id']}/splits", json={"lines": [{"amount": -10}, {"amount": -20}]})
    assert bad.status_code == 422
    donation = tx(client, chq, -75, "RED CROSS", date(year, 2, 1), cats["Gifts & donations"]["id"])
    client.put(f"/api/transactions/{donation['id']}/tax-tag", json={"tax_tag": "donations"})
    s = client.get("/api/tax/summary", params={"year": year}).json()
    groups = {g["tag"]: g for g in s["groups"]}
    assert groups["medical"]["total"] == 100 and groups["donations"]["total"] == 75
    csv_text = client.get("/api/tax/export", params={"year": year}).text
    assert "prescription" in csv_text and "RED CROSS" in csv_text

    ie = client.get("/api/reports/income-expense", params={"start": f"{year}-01-01"}).json()
    by = {c["name"]: c["total"] for c in ie["expense_by_category"]}
    assert by["Health"] == 100 and by["Shopping"] == 50


def test_shared_expense_and_settle_up(client):
    chq, _, cats = setup_basic(client)
    jordan = client.post("/api/people", json={"name": "Jordan"}).json()
    dinner = tx(client, chq, -120, "PAI THAI", category=cats["Dining out"]["id"])
    client.put(f"/api/transactions/{dinner['id']}/shares", json={"shares": [{"person_id": jordan["id"], "amount": 60}]})
    people = client.get("/api/people").json()["people"]
    assert people[0]["balance"] == 60 and people[0]["status"] == "owes you"
    month = date.today().strftime("%Y-%m")
    dash = client.get("/api/reports/dashboard", params={"month": month}).json()
    dining = next(s for s in dash["spending"] if s["name"] == "Dining out")
    assert dining["total"] == 60  # only your half counts as your spending

    payback = tx(client, chq, 60, "E-TRANSFER FROM JORDAN")
    r = client.post(f"/api/people/{jordan['id']}/settle", json={"amount": 60, "date": date.today().isoformat(),
                                                                   "transaction_id": payback["id"]}).json()
    assert r["people"][0]["balance"] == 0
    dash = client.get("/api/reports/dashboard", params={"month": month}).json()
    assert dash["this_month"]["income"] == 0  # the payback is a reimbursement, not income
    activity = client.get(f"/api/people/{jordan['id']}/activity").json()["items"]
    assert {i["kind"] for i in activity} == {"share", "settlement"}


TD = ("09/10/2026,RBC VISA PAYMENT,500.00,,1000.00\n"
      "09/12/2026,LOBLAWS,80.00,,920.00\n")
RBC = ('"Account Type","Account Number","Transaction Date","Cheque Number","Description 1","Description 2","CAD$","USD$"\n'
       'Visa,4500,9/11/2026,,"PAYMENT - THANK YOU","",500.00,\n'
       'Visa,4500,9/13/2026,,"TIM HORTONS","",-3.45,\n')


def upload(client, account_id, text, name="a.csv"):
    return client.post("/api/imports/commit", data={"account_id": str(account_id), "options": "{}"},
                       files={"file": (name, io.BytesIO(text.encode()), "text/csv")}).json()


def test_transfer_matching_on_import(client):
    chq, card, cats = setup_basic(client)
    upload(client, chq["id"], TD)
    r = upload(client, card["id"], RBC)
    assert r["transfers_matched"] == 1
    txs = client.get("/api/transactions", params={"q": "payment"}).json()["items"]
    assert len(txs) == 2 and all(t["transfer_id"] for t in txs)
    assert all(t["category_name"] == "Credit card payment" for t in txs)
    ie = client.get("/api/reports/income-expense", params={"start": "2026-09-01", "end": "2026-09-30"}).json()
    assert ie["totals"]["expense"] == 83.45 and ie["totals"]["income"] == 0

    # Unmatch, then the pair shows up again as a suggestion.
    client.delete(f"/api/transfers/{txs[0]['id']}")
    sugg = client.get("/api/transfers/suggestions").json()
    assert len(sugg) == 1 and sugg[0]["out"]["amount"] == -500


def test_watched_folder_import(client, monkeypatch, tmp_path):
    from app import config
    monkeypatch.setattr(config, "IMPORT_WATCH_DIR", tmp_path)
    chq, _, _ = setup_basic(client)
    assert client.put(f"/api/inbox/accounts/{chq['id']}", json={"watch": True}).status_code == 403
    client.patch("/api/admin/settings", json={"folder_import_enabled": True})
    status = client.put(f"/api/inbox/accounts/{chq['id']}", json={"watch": True}).json()
    folder = tmp_path / status["accounts"][0]["folder"]
    assert folder.is_dir()
    good, bad = folder / "sept.csv", folder / "broken.csv"
    good.write_text(TD)
    bad.write_text("nothing,useful\n")
    import os
    import time
    old = time.time() - 600
    for f in (good, bad):
        os.utime(f, (old, old))  # pretend the files finished copying a while ago
    assert client.post("/api/inbox/scan").json()["imported"] == 2
    assert list((folder / "imported").iterdir()) and list((folder / "failed").glob("*.txt"))
    assert not good.exists() and not bad.exists()


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def test_receipts(client):
    from app.db import SessionLocal
    from app.models import Attachment
    from app.services import receipts

    chq, _, _ = setup_basic(client)
    t = tx(client, chq, -42, "HARDWARE STORE")
    up = client.post(f"/api/transactions/{t['id']}/attachments", files={"file": ("receipt.png", io.BytesIO(PNG), "image/png")})
    assert up.status_code == 200, up.text
    a = up.json()
    assert a["content_type"] == "image/png" and a["ocr_status"] == "none"
    f = client.get(a["url"])
    assert f.status_code == 200 and f.content == PNG and "sandbox" in f.headers["content-security-policy"]
    fake = client.post(f"/api/transactions/{t['id']}/attachments", files={"file": ("x.png", io.BytesIO(b"<script>"), "image/png")})
    assert fake.status_code == 422
    row = client.get("/api/transactions").json()["items"][0]
    assert row["attachments"] == 1
    with SessionLocal() as db:
        path = receipts.file_path(db.get(Attachment, a["id"]))
        assert path.exists()
    assert client.delete(f"/api/transactions/{t['id']}").json()["ok"]
    assert not path.exists()


def test_receipt_total_guess():
    from app.services.receipts import guess_total
    assert guess_total("LOBLAWS\nMILK 4.99\nSUBTOTAL 40.00\nHST 2.10\nTOTAL 42.10\n") == 42.10
    assert guess_total("Montant total 19,99") == 19.99


def test_bill_reminders(client, monkeypatch):
    from app.db import SessionLocal
    from app.services import notify
    chq, _, _ = setup_basic(client)
    assert client.put("/api/notifications", json={"ntfy_url": "http://127.0.0.1/secret-topic"}).status_code == 422
    client.put("/api/notifications", json={"ntfy_url": "https://ntfy.example/secret-topic"})
    rec = client.post("/api/recurring", json={"name": "Rent", "amount": -2150, "account_id": chq["id"], "frequency": "monthly",
                                              "next_date": (date.today() + timedelta(days=2)).isoformat()}).json()
    client.put(f"/api/recurring/{rec['id']}/reminder", json={"remind_days": 3})
    sent = []
    monkeypatch.setattr(notify, "send_ntfy", lambda url, title, body: sent.append((url, body)))
    with SessionLocal() as db:
        assert notify.send_due_reminders(db) == 1
        assert notify.send_due_reminders(db) == 0  # once per occurrence
    assert "Rent" in sent[0][1] and "2,150.00" in sent[0][1]
    cal = client.get("/api/bills/calendar", params={"month": (date.today() + timedelta(days=2)).strftime("%Y-%m")}).json()
    assert any(i["name"] == "Rent" for i in cal["items"])
    assert client.post("/api/notifications/test").json()["sent"] == ["ntfy"]


def test_locale_preference(client):
    register(client)
    assert client.patch("/api/auth/me", json={"locale": "fr"}).json()["locale"] == "fr"
    assert client.patch("/api/auth/me", json={"locale": "de"}).status_code == 422


def test_french_signup_gets_french_categories(client):
    r = client.post("/api/auth/register", json={"email": "f@home.lan", "password": PW, "locale": "fr"})
    assert r.json()["locale"] == "fr"
    names = {c["name"] for c in client.get("/api/categories").json()}
    assert {"Épicerie", "Virement", "Paiement de carte de crédit"} <= names
