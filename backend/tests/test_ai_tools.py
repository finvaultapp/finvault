import json
from datetime import date

import pytest

from app.services import ai as ai_service
from app.services import ai_tools

from .test_api import register


class FakeModel:
    """Stands in for httpx.post to the model server; records every payload."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, url, json, headers, timeout):
        self.calls.append({"url": url, "json": json, "headers": headers})
        reply = self.replies.pop(0) if self.replies else "{}"
        status = 200
        if isinstance(reply, tuple):
            status, reply = reply

        class R:
            status_code = status
            text = reply if isinstance(reply, str) else ""

            def json(self_inner):
                return {"choices": [{"message": {"content": reply}}]}
        return R()

    def sent(self, i=-1):
        return json.loads(self.calls[i]["json"]["messages"][1]["content"])


@pytest.fixture(autouse=True)
def _reset_limits():
    ai_tools.suggest_limit.hits.clear()
    ai_tools.search_limit.hits.clear()


def setup_household(client, opt_in=True):
    register(client)
    client.patch("/api/admin/settings", json={"ai_enabled": True, "ai_base_url": "http://ollama:11434/v1", "ai_model": "llama3.1"})
    if opt_in:
        client.patch("/api/auth/me", json={"ai_opt_in": True})
    acct = client.post("/api/accounts", json={"name": "RBC Chequing", "currency": "CAD"}).json()
    cats = {c["name"]: c["id"] for c in client.get("/api/categories").json()}
    return acct, cats


def add_tx(client, acct, desc, amount, day="2026-05-02", category_id=None):
    return client.post("/api/transactions", json={"account_id": acct["id"], "date": day, "amount": amount,
                                                  "description": desc, "category_id": category_id}).json()


def test_suggestions_valid_json_cache_accept_and_rule(client, monkeypatch):
    acct, cats = setup_household(client)
    known = add_tx(client, acct, "LOBLAWS 1234 TORONTO", -80, category_id=cats["Groceries"])
    a = add_tx(client, acct, "FARM BOY #0417 OTTAWA 4520-1111-2222-3333", -54.20)
    b = add_tx(client, acct, "MYSTERY SHOP", -12)
    same_as_known = add_tx(client, acct, "LOBLAWS 9999 TORONTO", -30)  # history already places it
    notes_secret = "account 12345678"
    client.patch(f"/api/transactions/{a['id']}", json={"notes": notes_secret, "payee": "Farm Boy"})

    fake = FakeModel([json.dumps({"suggestions": [
        {"id": 1, "category": "Groceries", "confidence": 0.93},
        {"id": 2, "category": "Crypto moonshots", "confidence": 0.99},  # not a real category: dropped
    ]})])
    monkeypatch.setattr(ai_service.httpx, "post", fake)
    r = client.post("/api/ai/suggestions", json={}).json()
    assert r["sent"] == 2
    assert [(s["transaction_id"], s["category_name"]) for s in r["suggestions"]] == [(a["id"], "Groceries")]

    # Exactly the allowed fields go out: descriptions (long digit runs masked), direction, size, category names.
    call = fake.calls[0]
    assert call["url"] == "http://ollama:11434/v1/chat/completions"
    assert call["json"]["temperature"] == 0 and call["json"]["model"] == "llama3.1"
    body = fake.sent(0)
    assert set(body) == {"categories", "items"}
    assert body["categories"] == sorted(cats)
    for item in body["items"]:
        assert set(item) == {"id", "description", "direction", "amount"}
    by_desc = {i["description"]: i for i in body["items"]}
    assert set(by_desc) == {"FARM BOY # OTTAWA #", "MYSTERY SHOP"}
    assert by_desc["MYSTERY SHOP"] == {"id": 2, "description": "MYSTERY SHOP", "direction": "out", "amount": 12.0}
    raw = json.dumps(call["json"])
    for leaked in ("4520", "1111", "0417", notes_secret, "Farm Boy", "RBC", "LOBLAWS", "80"):
        assert leaked not in raw, leaked
    assert same_as_known["id"] not in [s["transaction_id"] for s in r["suggestions"]]

    # Cached per merchant: a second run (and a new line from the same merchant) sends nothing.
    c = add_tx(client, acct, "FARM BOY #0999 OTTAWA", -20)
    r2 = client.post("/api/ai/suggestions", json={}).json()
    assert r2["sent"] == 0 and len(fake.calls) == 1
    assert {s["transaction_id"] for s in r2["suggestions"]} == {a["id"], c["id"]}
    assert client.get("/api/ai/suggestions", params={"transaction_id": [c["id"]]}).json()["suggestions"][0]["category_id"] == cats["Groceries"]

    # Accept with a rule: the rule catches the other Farm Boy line too.
    res = client.post("/api/ai/suggestions/accept", json={"items": [{"transaction_id": a["id"], "category_id": cats["Groceries"]}],
                                                          "create_rules": True}).json()
    assert res == {"updated": 1, "rules_created": 1, "applied": 1}
    rules = client.get("/api/rules").json()
    assert rules[0]["pattern"] == "farm boy" and rules[0]["set_category_id"] == cats["Groceries"]
    uncategorized = client.get("/api/transactions", params={"uncategorized": True}).json()["items"]
    assert {t["id"] for t in uncategorized} == {b["id"], same_as_known["id"]}


def test_reject_hides_suggestion(client, monkeypatch):
    acct, cats = setup_household(client)
    t = add_tx(client, acct, "CORNER STORE", -5)
    assert client.get("/api/ai/suggestions").json() == {"suggestions": [], "unasked": 1}
    monkeypatch.setattr(ai_service.httpx, "post", FakeModel(['{"suggestions":[{"id":1,"category":"groceries","confidence":"high"}]}']))
    s = client.post("/api/ai/suggestions", json={"transaction_ids": [t["id"]]}).json()["suggestions"]
    assert s[0]["category_name"] == "Groceries" and s[0]["confidence"] == 0.5  # case-insensitive name, bad confidence
    assert client.post("/api/ai/suggestions/reject", json={"transaction_ids": [t["id"]]}).json() == {"rejected": 1}
    assert client.get("/api/ai/suggestions").json()["suggestions"] == []


def test_suggestions_invalid_json(client, monkeypatch):
    acct, _ = setup_household(client)
    add_tx(client, acct, "SOMEWHERE NEW", -9)
    fake = FakeModel(["Sure! Groceries, probably.", "```json\n[{\"id\": 1, \"category\": \"Shopping\"}]\n```"])
    monkeypatch.setattr(ai_service.httpx, "post", fake)
    r = client.post("/api/ai/suggestions", json={})
    assert r.status_code == 502 and "valid JSON" in r.json()["detail"]
    # Nothing was cached, so a later try asks again; fenced JSON arrays are fine.
    r = client.post("/api/ai/suggestions", json={}).json()
    assert r["sent"] == 1 and r["suggestions"][0]["category_name"] == "Shopping"


def test_retries_without_optional_params(client, monkeypatch):
    acct, _ = setup_household(client)
    add_tx(client, acct, "NEW PLACE", -9)
    fake = FakeModel([(400, "unsupported parameter: response_format"), '{"suggestions": []}'])
    monkeypatch.setattr(ai_service.httpx, "post", fake)
    assert client.post("/api/ai/suggestions", json={}).status_code == 200
    assert "response_format" in fake.calls[0]["json"] and "response_format" not in fake.calls[1]["json"]
    assert "temperature" not in fake.calls[1]["json"]


def test_personal_openai_key_gets_no_temperature(client, monkeypatch):
    register(client)
    client.patch("/api/admin/settings", json={"ai_allow_personal_keys": True})
    monkeypatch.setattr(ai_service, "list_openai_models", lambda key: ["o4-mini"])
    client.put("/api/ai/personal", json={"provider": "openai", "api_key": "sk-test-9"})
    client.patch("/api/auth/me", json={"ai_opt_in": True})
    fake = FakeModel(['{"period": "this_year", "kind": "expense"}'])
    monkeypatch.setattr(ai_service.httpx, "post", fake)
    r = client.post("/api/ai/search", json={"question": "what did I spend this year"}).json()
    assert r["filters"]["start"] == f"{date.today().year}-01-01" and r["filters"]["kind"] == "expense"
    call = fake.calls[0]
    assert call["url"] == "https://api.openai.com/v1/chat/completions" and "temperature" not in call["json"]
    assert call["headers"]["Authorization"] == "Bearer sk-test-9"


def test_gates_ai_off_and_opt_in_off(client, monkeypatch):
    register(client)
    fake = FakeModel([])
    monkeypatch.setattr(ai_service.httpx, "post", fake)
    for method, path, body in (("post", "/api/ai/suggestions", {}), ("get", "/api/ai/suggestions", None),
                               ("post", "/api/ai/search", {"question": "groceries"}),
                               ("post", "/api/ai/suggestions/accept", {"items": []})):
        r = client.request(method.upper(), path, json=body)
        assert r.status_code == 403 and "isn't set up" in r.json()["detail"], path
    client.patch("/api/admin/settings", json={"ai_enabled": True})
    r = client.post("/api/ai/search", json={"question": "groceries"})
    assert r.status_code == 403 and "Turn on" in r.json()["detail"]
    r = client.post("/api/ai/suggestions", json={})
    assert r.status_code == 403
    assert fake.calls == []


def test_suggest_rate_limit(client, monkeypatch):
    acct, _ = setup_household(client)
    monkeypatch.setattr(ai_tools.suggest_limit, "limit", 1)
    monkeypatch.setattr(ai_service.httpx, "post", FakeModel(['{"suggestions":[]}', '{"suggestions":[]}']))
    add_tx(client, acct, "PLACE ONE", -1)
    assert client.post("/api/ai/suggestions", json={}).status_code == 200
    add_tx(client, acct, "PLACE TWO", -1)
    assert client.post("/api/ai/suggestions", json={}).status_code == 429


def test_plain_search(client, monkeypatch):
    acct, cats = setup_household(client)
    client.post("/api/accounts", json={"name": "Visa Infinite", "currency": "CAD"})
    reply = {"season": "spring", "which": "last", "categories": ["Dining out", "Takeout Heaven"], "accounts": ["rbc chequing"],
             "min_amount": "$50", "max_amount": None, "kind": "expense", "text": None, "surprise": "ignored"}
    fake = FakeModel([json.dumps(reply)])
    monkeypatch.setattr(ai_service.httpx, "post", fake)
    r = client.post("/api/ai/search", json={"question": "restaurants over $50 last spring on my chequing"})
    assert r.status_code == 200, r.text
    out = r.json()
    f = out["filters"]
    y = date.today().year if date.today() > date(date.today().year, 6, 20) else date.today().year - 1
    assert (f["start"], f["end"]) == (f"{y}-03-20", f"{y}-06-20")
    assert f["category_id"] == [cats["Dining out"]] and f["account_id"] == [acct["id"]]
    assert f["min_amount"] == 50 and f["max_amount"] is None and f["kind"] == "expense" and f["q"] is None
    assert out["unmatched"]["categories"] == ["Takeout Heaven"]
    assert set(f) == {"start", "end", "category_id", "account_id", "min_amount", "max_amount", "kind", "q"}

    body = fake.sent(0)
    assert set(body) == {"today", "question", "categories", "accounts"}
    assert body["today"] == date.today().isoformat() and body["accounts"] == ["RBC Chequing", "Visa Infinite"]

    # The filters work as-is on the normal endpoint.
    add_tx(client, acct, "BISTRO", -75, day=f"{y}-04-10", category_id=cats["Dining out"])
    add_tx(client, acct, "CAFE", -20, day=f"{y}-04-11", category_id=cats["Dining out"])
    params = {k: v for k, v in f.items() if v not in (None, [])}
    assert [t["description"] for t in client.get("/api/transactions", params=params).json()["items"]] == ["BISTRO"]


def test_plain_search_garbage_and_empty(client, monkeypatch):
    setup_household(client)
    monkeypatch.setattr(ai_service.httpx, "post", FakeModel(["I think you mean restaurants", '{"categories": ["Nope"]}', json.dumps(["not", "an", "object"])]))
    r = client.post("/api/ai/search", json={"question": "restaurants"})
    assert r.status_code == 502 and "valid JSON" in r.json()["detail"]
    r = client.post("/api/ai/search", json={"question": "restaurants"})
    assert r.status_code == 422
    r = client.post("/api/ai/search", json={"question": "restaurants"})
    assert r.status_code == 502


def test_model_unreachable(client, monkeypatch):
    setup_household(client)

    def boom(*a, **k):
        raise ai_tools.httpx.ConnectError("refused")
    monkeypatch.setattr(ai_service.httpx, "post", boom)
    r = client.post("/api/ai/search", json={"question": "groceries"})
    assert r.status_code == 502 and "Couldn't reach" in r.json()["detail"]


def test_date_resolution_canadian_calendar():
    d = date(2026, 4, 15)  # a Wednesday, in spring
    r = ai_tools.resolve_dates
    assert r({"season": "spring", "which": "last"}, d)[:2] == (date(2025, 3, 20), date(2025, 6, 20))
    assert r({"season": "spring"}, d)[:2] == (date(2026, 3, 20), date(2026, 6, 20))
    assert r({"season": "winter", "which": "last"}, d)[:2] == (date(2025, 12, 21), date(2026, 3, 19))
    assert r({"season": "autumn", "year": 2024}, d)[:2] == (date(2024, 9, 23), date(2024, 12, 20))
    assert r({"period": "this_week"}, d)[:2] == (date(2026, 4, 12), date(2026, 4, 18))  # Sunday to Saturday
    assert r({"period": "last_quarter"}, d)[:2] == (date(2026, 1, 1), date(2026, 3, 31))
    assert r({"period": "last_month"}, date(2026, 1, 10))[:2] == (date(2025, 12, 1), date(2025, 12, 31))
    assert r({"month": 12}, d)[:2] == (date(2025, 12, 1), date(2025, 12, 31))
    assert r({"month": 4, "which": "last"}, d)[:2] == (date(2025, 4, 1), date(2025, 4, 30))
    assert r({"last_n_days": 7}, d)[:2] == (date(2026, 4, 9), d)
    assert r({"year": 2025}, d)[:2] == (date(2025, 1, 1), date(2025, 12, 31))
    assert r({"date_from": "2026-02-01", "date_to": "2026-01-01"}, d)[:2] == (date(2026, 1, 1), date(2026, 2, 1))
    assert r({"date_from": "yesterday-ish"}, d)[:2] == (None, None)
    # Relative wording from the model always wins over dates it tried to compute itself.
    assert r({"period": "this_year", "date_from": "1999-01-01"}, d)[:2] == (date(2026, 1, 1), date(2026, 12, 31))
