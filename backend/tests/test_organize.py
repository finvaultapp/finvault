"""Budget rollover, tags and the Payees page."""
import csv
import io
import json
from datetime import date
from decimal import Decimal

from app.services.rollover import MAX_MONTHS, carry_forward, month_index, walk_start
from tests.test_api import TD, register, upload


def setup(client):
    register(client)
    chq = client.post("/api/accounts", json={"name": "Chequing", "opening_balance": 5000}).json()
    cats = {c["name"]: c for c in client.get("/api/categories").json()}
    return chq, cats


def tx(client, account, amount, desc, when, category=None):
    r = client.post("/api/transactions", json={"account_id": account["id"], "date": when.isoformat(), "amount": amount,
                                               "description": desc, "category_id": category})
    assert r.status_code == 200, r.text
    return r.json()


# --- Rollover math ---------------------------------------------------------------

D = Decimal


def test_carry_forward_leftovers_only():
    # 100 a month: spend 60 (40 left), nothing (140 left), 300 (overspent: carry resets to 0)
    assert carry_forward(D(100), [D(60)], "carry") == D(40)
    assert carry_forward(D(100), [D(60), D(0)], "carry") == D(140)
    assert carry_forward(D(100), [D(60), D(0), D(300)], "carry") == D(0)
    # After an overspent month the next leftovers start from zero again.
    assert carry_forward(D(100), [D(60), D(0), D(300), D(70)], "carry") == D(30)


def test_carry_forward_with_overspending():
    assert carry_forward(D(100), [D(60), D(0), D(300)], "carry_all") == D(-60)
    # The debt keeps shrinking the following months until it's paid back.
    assert carry_forward(D(100), [D(60), D(0), D(300), D(70)], "carry_all") == D(-30)
    assert carry_forward(D(100), [D(60), D(0), D(300), D(70), D(0)], "carry_all") == D(70)


def test_carry_forward_no_spending_and_off():
    assert carry_forward(D(250), [D(0)] * 3, "carry") == D(750)
    assert carry_forward(D(250), [D(0)] * 3, "carry_all") == D(750)
    assert carry_forward(D(250), [], "carry_all") == D(0)
    assert carry_forward(D(250), [D(0)] * 3, "off") == D(0)
    # Refunds (negative spending) add to what's left.
    assert carry_forward(D(100), [D(-20)], "carry") == D(120)


def test_walk_is_capped():
    target = month_index(2026, 4)
    assert walk_start(target, date(2026, 1, 1)) == month_index(2026, 1)
    assert walk_start(target, date(2019, 1, 1)) == target - MAX_MONTHS
    assert walk_start(target, None) == target - MAX_MONTHS


def _budget(client, month):
    return {i["name"]: i for i in client.get(f"/api/budgets?month={month}").json()["items"]}


def test_budget_rollover_api(client):
    chq, cats = setup(client)
    groc = cats["Groceries"]["id"]
    client.put("/api/budgets", json={"category_id": groc, "amount": 100})
    bid = _budget(client, "2026-04")["Groceries"]["id"]
    # January: a $120 shop, half of it shared with Jordan, so $60 is ours (effective_lines).
    jan = tx(client, chq, -120, "FARM BOY", date(2026, 1, 10), groc)
    jordan = client.post("/api/people", json={"name": "Jordan"}).json()
    client.put(f"/api/transactions/{jan['id']}/shares", json={"shares": [{"person_id": jordan["id"], "amount": 60}]})
    # February: nothing. March: $300 over two lines, one of them a split with another category.
    tx(client, chq, -250, "LOBLAWS", date(2026, 3, 5), groc)
    split = tx(client, chq, -80, "COSTCO", date(2026, 3, 20), groc)
    client.put(f"/api/transactions/{split['id']}/splits", json={"lines": [
        {"category_id": groc, "amount": -50}, {"category_id": cats["Shopping"]["id"], "amount": -30}]})
    # April: $10 so far.
    tx(client, chq, -10, "LOBLAWS", date(2026, 4, 2), groc)

    off = _budget(client, "2026-04")["Groceries"]
    assert off["rollover"] == "off" and off["carried"] == 0 and off["available"] == 100 and off["remaining"] == 90

    r = client.put(f"/api/budgets/{bid}/rollover", json={"mode": "carry", "start": "2026-01"})
    assert r.status_code == 200 and r.json()["rollover_start"] == "2026-01"
    assert _budget(client, "2026-01")["Groceries"]["carried"] == 0
    assert _budget(client, "2026-02")["Groceries"]["carried"] == 40
    feb = _budget(client, "2026-02")["Groceries"]
    assert feb["available"] == 140 and feb["spent"] == 0 and feb["remaining"] == 140
    mar = _budget(client, "2026-03")["Groceries"]
    assert mar["carried"] == 140 and mar["available"] == 240 and mar["spent"] == 300 and mar["remaining"] == -60
    assert mar["percent"] == 125.0
    apr = _budget(client, "2026-04")["Groceries"]
    assert apr["carried"] == 0 and apr["available"] == 100 and apr["remaining"] == 90

    client.put(f"/api/budgets/{bid}/rollover", json={"mode": "carry_all", "start": "2026-01"})
    apr = client.get("/api/budgets?month=2026-04").json()
    item = apr["items"][0]
    assert item["carried"] == -60 and item["available"] == 40 and item["remaining"] == 30
    assert apr["total_carried"] == -60 and apr["total_available"] == 40 and apr["total_budget"] == 100

    # A later start month ignores older history: only March counts (100 - 300).
    client.put(f"/api/budgets/{bid}/rollover", json={"mode": "carry_all", "start": "2026-03"})
    assert _budget(client, "2026-04")["Groceries"]["carried"] == -200
    assert _budget(client, "2026-02")["Groceries"]["carried"] == 0  # before the start month
    # Overspending carried in can use up the whole month (April: 100 - 200 - 10 = -110 carries on).
    may = _budget(client, "2026-05")["Groceries"]
    assert may["carried"] == -110 and may["available"] == -10 and may["remaining"] == -10
    assert may["percent"] == 110.0  # already over by 10 of the 100 limit before spending anything

    # The dashboard's budgets carry the same numbers.
    dash = client.get("/api/reports/dashboard?month=2026-04").json()
    assert dash["budgets"]["items"][0]["carried"] == -200

    bad = client.put(f"/api/budgets/{bid}/rollover", json={"mode": "carry", "start": "2026-13"})
    assert bad.status_code == 422
    client.put(f"/api/budgets/{bid}/rollover", json={"mode": "off"})
    assert _budget(client, "2026-04")["Groceries"]["carried"] == 0


def test_rollover_counts_subcategories(client):
    chq, cats = setup(client)
    food = cats["Groceries"]["id"]
    sub = client.post("/api/categories", json={"name": "Bakery", "kind": "expense", "parent_id": food}).json()
    client.put("/api/budgets", json={"category_id": food, "amount": 200})
    bid = _budget(client, "2026-02")["Groceries"]["id"]
    tx(client, chq, -150, "BAKERY", date(2026, 1, 3), sub["id"])
    client.put(f"/api/budgets/{bid}/rollover", json={"mode": "carry", "start": "2026-01"})
    assert _budget(client, "2026-02")["Groceries"]["carried"] == 50


# --- Tags ------------------------------------------------------------------------

def test_tags_on_transactions_filters_export_and_report(client):
    chq, cats = setup(client)
    hotel = tx(client, chq, -400, "HOTEL", date(2026, 7, 2), cats["Travel"]["id"])
    dinner = tx(client, chq, -100, "BISTRO", date(2026, 7, 3), cats["Dining out"]["id"])
    refund = tx(client, chq, 50, "HOTEL REFUND", date(2026, 7, 9), cats["Travel"]["id"])
    other = tx(client, chq, -20, "HARDWARE", date(2026, 7, 4), cats["Shopping"]["id"])

    r = client.put(f"/api/transactions/{hotel['id']}/tags", json={"names": ["Vacation 2026", " vacation  2026 ", "tax-2026"]})
    assert [t["name"] for t in r.json()["tags"]] == ["tax-2026", "Vacation 2026"]  # same name once, ignoring case
    tags = {t["name"]: t for t in client.get("/api/tags").json()}
    vac = tags["Vacation 2026"]
    assert vac["count"] == 1

    # Bulk add and remove.
    r = client.post("/api/tags/bulk", json={"ids": [dinner["id"], refund["id"], hotel["id"]], "action": "add", "tag_id": vac["id"]})
    assert r.json()["updated"] == 2
    r = client.post("/api/tags/bulk", json={"ids": [other["id"]], "action": "add", "name": "reno"})
    assert r.json()["updated"] == 1 and r.json()["tag"]["name"] == "reno"
    r = client.post("/api/tags/bulk", json={"ids": [hotel["id"]], "action": "remove", "name": "TAX-2026"})
    assert r.json()["updated"] == 1

    # Filter (and the list shows tags).
    listed = client.get(f"/api/transactions?tag_id={vac['id']}").json()
    assert listed["total"] == 3 and all(any(t["name"] == "Vacation 2026" for t in i["tags"]) for i in listed["items"])
    both = client.get(f"/api/transactions?tag_id={vac['id']}&tag_id={tags['tax-2026']['id']}").json()
    assert both["total"] == 3

    # A share and a split: only my part counts in the report.
    jordan = client.post("/api/people", json={"name": "Jordan"}).json()
    client.put(f"/api/transactions/{dinner['id']}/shares", json={"shares": [{"person_id": jordan["id"], "amount": 50}]})
    client.put(f"/api/transactions/{hotel['id']}/splits", json={"lines": [
        {"category_id": cats["Travel"]["id"], "amount": -300}, {"category_id": cats["Dining out"]["id"], "amount": -100}]})
    rep = client.get("/api/reports/tags?start=2026-07-01&end=2026-07-31").json()
    by = {i["name"]: i for i in rep["items"]}
    # 400 hotel (split across two expense categories) + 50 (my half of dinner) - 50 refund in Travel.
    assert by["Vacation 2026"]["expense"] == 400 and by["Vacation 2026"]["income"] == 0
    assert by["Vacation 2026"]["net"] == -400 and by["Vacation 2026"]["count"] == 3
    assert by["reno"]["expense"] == 20
    assert "tax-2026" not in by  # no tagged transactions left in range

    # Export: CSV has a Tags column, JSON a tags list.
    text = client.get(f"/api/transactions/export?format=csv&tag_id={vac['id']}").text.lstrip("﻿")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) == 3 and all(row["Tags"] == "Vacation 2026" for row in rows)
    data = json.loads(client.get("/api/transactions/export?format=json").text)
    assert {t["name"] for d in data for t in d["tags"]} == {"Vacation 2026", "reno"}


def test_tag_rename_merge_delete(client):
    chq, cats = setup(client)
    a = tx(client, chq, -10, "A", date(2026, 5, 1))
    b = tx(client, chq, -20, "B", date(2026, 5, 2))
    client.put(f"/api/transactions/{a['id']}/tags", json={"names": ["reno", "house"]})
    client.put(f"/api/transactions/{b['id']}/tags", json={"names": ["Renovation"]})
    tags = {t["name"]: t for t in client.get("/api/tags").json()}
    assert client.patch(f"/api/tags/{tags['house']['id']}", json={"name": "RENO"}).status_code == 409
    client.patch(f"/api/tags/{tags['house']['id']}", json={"name": "Home"})
    rule = client.post("/api/rules", json={"pattern": "b", "match_type": "equals", "set_tag_id": tags["Renovation"]["id"]}).json()
    r = client.post("/api/tags/merge", json={"source_ids": [tags["Renovation"]["id"]], "target_id": tags["reno"]["id"]}).json()
    assert r["merged"] == 1 and r["moved"] == 1 and r["tag"]["count"] == 2
    names = {t["name"]: t["count"] for t in client.get("/api/tags").json()}
    assert names == {"Home": 1, "reno": 2}
    rules = client.get("/api/rules").json()
    assert rules[0]["id"] == rule["id"] and rules[0]["set_tag_id"] == tags["reno"]["id"]
    client.delete(f"/api/tags/{tags['reno']['id']}")
    assert client.get("/api/rules").json() == []  # a tag-only rule has nothing left to do
    assert client.get("/api/transactions?q=A").json()["items"][0]["tags"] == [{"id": tags["house"]["id"], "name": "Home"}]
    assert client.delete("/api/tags/99999").status_code == 404


def test_rules_add_tags_on_import(client):
    register(client)
    acct = client.post("/api/accounts", json={"name": "TD", "currency": "CAD", "import_preset": "td"}).json()
    cats = {c["name"]: c["id"] for c in client.get("/api/categories").json()}
    # A category rule and a tag-only rule both match; the tag-only rule doesn't block the category.
    client.post("/api/rules", json={"pattern": "shoppers", "set_tag": "pharmacy", "priority": 1})
    client.post("/api/rules", json={"pattern": "shoppers", "set_category_id": cats["Health"]})
    assert client.post("/api/rules", json={"pattern": "x"}).status_code == 422
    upload(client, "/api/imports/commit", acct["id"], TD)
    items = client.get("/api/transactions?q=shoppers").json()["items"]
    assert len(items) == 2
    assert all(i["category_id"] == cats["Health"] and [t["name"] for t in i["tags"]] == ["pharmacy"] for i in items)
    # Running rules again doesn't double-tag.
    client.post("/api/rules/apply", json={"only_uncategorized": False})
    assert client.get("/api/tags").json()[0]["count"] == 2


# --- Payees ----------------------------------------------------------------------

def test_payees_group_rename_rule_and_default_category(client):
    register(client)
    acct = client.post("/api/accounts", json={"name": "TD", "currency": "CAD", "import_preset": "td"}).json()
    cats = {c["name"]: c["id"] for c in client.get("/api/categories").json()}
    upload(client, "/api/imports/commit", acct["id"], TD)
    tx(client, acct, -5, "TIM HORTONS #0042", date(2026, 1, 8))
    tx(client, acct, -6, "TIMS 0099", date(2026, 1, 9))

    page = client.get("/api/payees").json()
    by = {i["key"]: i for i in page["items"]}
    shoppers = by["SHOPPERS DRUG MART"]
    assert shoppers["count"] == 2 and shoppers["total"] == -33.1 and shoppers["last_seen"] == "2026-01-05"
    assert page["items"][0]["key"] == "SHOPPERS DRUG MART"  # most transactions first
    assert shoppers["rule"] is None

    # Rename + a rule for future imports.
    r = client.post("/api/payees/rename", json={"keys": ["SHOPPERS DRUG MART"], "payee": "Shoppers", "create_rule": True}).json()
    assert r == {"updated": 2, "rules": 1}
    rules = client.get("/api/rules").json()
    assert rules[0]["match_type"] == "merchant" and rules[0]["set_payee"] == "Shoppers"
    # Default category: updates the same rule and sorts the uncategorized ones.
    r = client.put("/api/payees/category", json={"keys": ["SHOPPERS DRUG MART"], "category_id": cats["Health"]}).json()
    assert r["updated"] == 2 and r["rules"] == [rules[0]["id"]]
    assert len(client.get("/api/rules").json()) == 1
    shoppers = next(i for i in client.get("/api/payees?q=shoppers").json()["items"])
    assert shoppers["payee"] == "Shoppers" and shoppers["usual_category"]["id"] == cats["Health"]
    assert shoppers["rule"]["category_name"] == "Health" and shoppers["renamed"]

    # Future imports pick it up (a new store number is the same merchant).
    upload(client, "/api/imports/commit", acct["id"], "02/03/2026,SHOPPERS DRUG MART #999,12.00,,1500.00\n")
    new = client.get("/api/transactions?q=%23999").json()["items"][0]
    assert new["payee"] == "Shoppers" and new["category_id"] == cats["Health"]

    # Merge two messy keys into one payee.
    r = client.post("/api/payees/rename", json={"keys": ["TIM HORTONS", "TIMS"], "payee": "Tim Hortons"}).json()
    assert r["updated"] == 2 and r["rules"] == 0
    names = {i["key"]: i["payee"] for i in client.get("/api/payees").json()["items"]}
    assert names["TIM HORTONS"] == names["TIMS"] == "Tim Hortons"

    # Search, sort, paging.
    assert {i["key"] for i in client.get("/api/payees?q=tim").json()["items"]} == {"TIM HORTONS", "TIMS"}
    first = client.get("/api/payees?sort=name&page_size=2").json()
    assert first["total"] == 4 and len(first["items"]) == 2
    second = client.get("/api/payees?sort=name&page_size=2&page=2").json()
    assert [i["payee"] for i in first["items"] + second["items"]] == sorted(
        [i["payee"] for i in first["items"] + second["items"]], key=str.lower)
    big = client.get("/api/payees?sort=-total").json()["items"]
    assert big[0]["key"] == "E TRANSFER FROM JANE"
    detail = client.get("/api/payees/transactions?key=shoppers drug mart").json()
    assert detail["total"] == 3

    # Clearing the default category keeps the rule (it still renames) but drops the category.
    client.put("/api/payees/category", json={"keys": ["SHOPPERS DRUG MART"], "category_id": None})
    rule = client.get("/api/rules").json()[0]
    assert rule["set_category_id"] is None and rule["set_payee"] == "Shoppers"
    assert client.post("/api/payees/rename", json={"keys": ["X"], "payee": "  "}).status_code == 422
