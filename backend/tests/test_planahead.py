"""Cash-flow forecast, debt payoff (avalanche, snowball, Canadian mortgage), charge alerts, year in review."""
from datetime import date, timedelta
from decimal import Decimal as D

from app.services import debt, forecast
from app.services.charge_alerts import looks_monthly, price_changed
from tests.test_api import register


def setup(client):
    register(client)
    chq = client.post("/api/accounts", json={"name": "Chequing", "type": "checking", "opening_balance": 5000}).json()
    cats = {c["name"]: c for c in client.get("/api/categories").json()}
    return chq, cats


def tx(client, account, amount, desc, when, category=None):
    r = client.post("/api/transactions", json={"account_id": account["id"], "date": when.isoformat(), "amount": amount,
                                               "description": desc, "category_id": category})
    assert r.status_code == 200, r.text
    return r.json()


# --- Forecast ------------------------------------------------------------------------------

def test_project_and_shortfall_math():
    today = date(2026, 1, 1)
    events = [(date(2026, 1, 3), D("-500")), (date(2026, 1, 5), D("1000"))]
    points = forecast.project(D("600"), D("10"), events, today, 6)
    # Jan 2: 590, Jan 3: 590-10-500=80, Jan 4: 70, Jan 5: 70-10+1000=1060, Jan 6: 1050, Jan 7: 1040
    assert points == [D(590), D(80), D(70), D(1060), D(1050), D(1040)]
    ev = [{"date": "2026-01-03", "amount": D("-500"), "name": "Rent"}]
    sf = forecast.first_shortfall(points, ev, today, D("100"))
    assert sf["date"] == "2026-01-03" and sf["balance"] == 80.0 and sf["bill"]["name"] == "Rent"
    assert forecast.first_shortfall(points, ev, today, D("0")) is None


def test_weekly_median_baseline_ignores_quiet_days_and_one_offs():
    end = date(2026, 3, 31)
    daily = {}
    for w in range(13):
        daily[end - timedelta(days=7 * w)] = D("70")  # one $70 shop a week, six quiet days
    daily[end - timedelta(days=3)] = D("2000")  # a one-off couch
    assert forecast.weekly_baseline(daily, end, end - timedelta(days=200)) == D(10)
    # Only three weeks of history: the older, empty weeks don't count.
    assert forecast.weekly_baseline(daily, end, end - timedelta(days=20)) == D(70) / 7


def test_forecast_endpoint(client):
    chq, cats = setup(client)
    today = date.today()
    for w in range(13):
        tx(client, chq, -70, "LOBLAWS", today - timedelta(days=1 + 7 * w), cats["Groceries"]["id"])
    tx(client, chq, -1800, "LANDLORD", today - timedelta(days=20), cats["Rent & mortgage"]["id"])  # recurring category
    tx(client, chq, -500, "TO SAVINGS", today - timedelta(days=15), cats["Transfer"]["id"])  # transfer kind
    # A $100 dinner split with a friend: only our $50 counts, and it's one week, so the median ignores it.
    dinner = tx(client, chq, -100, "RESTAURANT", today - timedelta(days=9), cats["Dining out"]["id"])
    pid = client.post("/api/people", json={"name": "Sam"}).json()["id"]
    client.put(f"/api/transactions/{dinner['id']}/shares", json={"shares": [{"person_id": pid, "amount": 50}]})
    client.post("/api/recurring", json={"name": "Rent", "amount": -1800, "account_id": chq["id"], "frequency": "monthly",
                                        "category_id": cats["Rent & mortgage"]["id"],
                                        "next_date": (today + timedelta(days=5)).isoformat()})
    client.post("/api/recurring", json={"name": "Payroll", "amount": 2000, "account_id": chq["id"], "frequency": "biweekly",
                                        "category_id": cats["Salary"]["id"],
                                        "next_date": (today + timedelta(days=10)).isoformat()})
    f = client.get("/api/forecast").json()
    a = f["accounts"][0]
    start = 5000 - 13 * 70 - 1800 - 500 - 100
    assert a["balance"] == start
    assert a["daily_spend"] == 10.0
    # Day 5: rent lands before the first paycheque.
    day5 = next(s for s in f["series"] if s["date"] == (today + timedelta(days=5)).isoformat())
    assert day5[f"a{chq['id']}"] == start - 50 - 1800
    assert a["lowest"]["balance"] <= start - 50 - 1800
    w = f["warnings"][0]
    assert w["code"] == "below_cushion" and w["bill"]["name"] == "Rent" and w["date"] == (today + timedelta(days=5)).isoformat()
    # 30-day horizon from first principles.
    from app.services import recurring as rec
    rent_n = paid_n = 0
    d = today + timedelta(days=5)
    while d <= today + timedelta(days=30):
        rent_n += 1
        d = rec.advance(d, "monthly", d.day)
    d = today + timedelta(days=10)
    while d <= today + timedelta(days=30):
        paid_n += 1
        d += timedelta(days=14)
    assert a["horizons"]["30"] == start - 300 - 1800 * rent_n + 2000 * paid_n
    assert f["estimate"] is True and any(u["name"] == "Payroll" for u in f["upcoming"])
    # A cushion above today's balance warns straight away.
    client.put("/api/forecast/settings", json={"cushion": 5000})
    ws = client.get("/api/forecast/warnings").json()
    assert ws["cushion"] == 5000 and ws["warnings"][0]["code"] == "already_below"


# --- Debt payoff ---------------------------------------------------------------------------

def test_single_card_monthly_compounding():
    r = debt.simulate([debt.Debt("a", "Visa", D(1000), D(12), D(0), "card")], D(500), "avalanche", date(2026, 1, 15))
    # Month 1: 1000 + 10.00 - 500 = 510; month 2: 510 + 5.10 - 500 = 15.10; month 3: 15.10 + 0.15 = 15.25 paid.
    assert r["months"] == 3 and r["total_interest"] == 15.25 and r["total_paid"] == 1015.25
    assert r["payoff_month"] == "2026-04"
    assert [m["balances"]["a"] for m in r["schedule"]] == [510.0, 15.1, 0.0]


def test_avalanche_vs_snowball():
    debts = [debt.Debt("small", "Line of credit", D(500), D(5), D(25), "loan"),
             debt.Debt("big", "Card", D(3000), D(20), D(60), "card")]
    av = debt.simulate(debts, D(400), "avalanche")
    sb = debt.simulate(debts, D(400), "snowball")
    assert av["order"] == ["big", "small"] and sb["order"] == ["small", "big"]
    assert av["total_interest"] < sb["total_interest"]
    # Each month pays exactly the budget until the final month.
    assert all(abs(sum(m["payments"].values()) - 400) < 0.005 for m in av["schedule"][:-1])
    assert debt.simulate(debts, D(50), "avalanche")["reason"] == "budget_below_minimums"
    assert debt.simulate([debt.Debt("x", "Card", D(5000), D(24), D(50), "card")], D(50), "snowball")["reason"] == "never_paid_off"


def test_canadian_mortgage_compounds_semi_annually():
    r = debt.monthly_rate(D(5), "mortgage")
    assert abs((1 + r) ** 6 - D("1.025")) < D("1e-20")  # six months compound to exactly APR/2
    assert r < D(5) / 100 / 12
    pay = debt.mortgage_payment(D(500000), D(5), 25)
    assert pay == D("2908.02")  # the figure Canadian lenders quote for $500k at 5%, 25 years
    sim = debt.simulate([debt.Debt("m", "Mortgage", D(500000), D(5), pay, "mortgage")], pay, "avalanche")
    assert sim["feasible"] and 299 <= sim["months"] <= 301
    # The same payment is not enough with monthly compounding at 5% over 25 years.
    us = debt.simulate([debt.Debt("m", "Mortgage", D(500000), D(5), pay, "loan")], pay, "avalanche")
    assert us["months"] > sim["months"]


def test_debt_api(client):
    register(client)
    card = client.post("/api/accounts", json={"name": "Visa", "type": "credit_card", "opening_balance": -2000}).json()
    home = client.post("/api/assets", json={"name": "Home loan", "kind": "mortgage", "value": 300000}).json()
    items = client.get("/api/debts").json()["items"]
    assert {i["id"] for i in items} == {f"account:{card['id']}", f"asset:{home['id']}"}
    assert next(i for i in items if i["source"] == "asset")["kind"] == "mortgage"
    assert client.put(f"/api/debts/account/{card['id']}", json={"apr": 20.99, "min_payment": 60}).status_code == 200
    assert client.put(f"/api/debts/asset/{home['id']}", json={"apr": 4.5, "min_payment": 1700}).status_code == 200
    plan = client.post("/api/debts/plan", json={"budget": 2000, "extra": 200}).json()
    assert plan["minimums"] == 1760 and plan["avalanche"]["feasible"]
    assert plan["avalanche"]["order"][0] == f"account:{card['id']}"
    assert plan["avalanche_extra"]["total_interest"] < plan["avalanche"]["total_interest"]
    assert client.get("/api/debts").json()["budget"] == 2000
    chq = client.post("/api/accounts", json={"name": "Chequing"}).json()
    assert client.put(f"/api/debts/account/{chq['id']}", json={"apr": 1, "min_payment": 1}).status_code == 422
    assert client.get("/api/debts/mortgage-payment", params={"principal": 500000, "apr": 5, "years": 25}).json()["payment"] == 2908.02


# --- Charge alerts -------------------------------------------------------------------------

def test_price_change_threshold():
    assert price_changed(D("-16.49"), D("-18.99"))  # $2.50 > max($1, 5%)
    assert not price_changed(D("-10.99"), D("-11.49"))  # 50 cents is under $1
    assert not price_changed(D("-100"), D("-104.99"))  # 4.99% of $100 is under 5%
    assert price_changed(D("-100"), D("-105.01"))
    assert looks_monthly([date(2026, 1, 3), date(2026, 2, 2)], [D("-9.99"), D("-9.99")])
    assert not looks_monthly([date(2026, 1, 3), date(2026, 1, 10)], [D("-9.99"), D("-9.99")])


def test_charge_alerts(client, monkeypatch):
    from app.services import notify
    chq, cats = setup(client)
    today = date.today()
    subs = cats["Subscriptions"]["id"]
    for months_ago in (5, 4, 3, 2):
        tx(client, chq, -16.49, "NETFLIX.COM", today - timedelta(days=10 + 30 * months_ago), subs)
        tx(client, chq, -10.99, "SPOTIFY", today - timedelta(days=12 + 30 * months_ago), subs)
        tx(client, chq, -80, "COSTCO WHOLESALE", today - timedelta(days=8 + 30 * months_ago), cats["Groceries"]["id"])
    for months_ago, amt in ((5, -90), (4, -120), (3, -75), (2, -110), (1, -95), (0, -140)):
        tx(client, chq, amt, "HYDRO ONE", today - timedelta(days=5 + 30 * months_ago), cats["Utilities"]["id"])
    tx(client, chq, -16.49, "NETFLIX.COM", today - timedelta(days=40), subs)
    tx(client, chq, -18.99, "NETFLIX.COM", today - timedelta(days=10), subs)  # price went up
    tx(client, chq, -11.49, "SPOTIFY", today - timedelta(days=12), subs)  # 50 cents: not worth an alert
    tx(client, chq, -9.99, "CRAVE", today - timedelta(days=50), subs)  # new, monthly-ish
    tx(client, chq, -9.99, "CRAVE", today - timedelta(days=20), subs)
    tx(client, chq, -80, "COSTCO WHOLESALE", today - timedelta(days=38))  # old merchant: never "new"
    tx(client, chq, -80, "COSTCO WHOLESALE", today - timedelta(days=8))
    for name, amt in (("NETFLIX.COM", -16.49), ("SPOTIFY", -10.99), ("HYDRO ONE", -100)):
        client.post("/api/recurring", json={"name": name, "amount": amt, "account_id": chq["id"], "frequency": "monthly",
                                            "next_date": (today + timedelta(days=20)).isoformat(), "category_id": subs})
    client.put("/api/notifications", json={"ntfy_url": "https://ntfy.example/topic"})
    sent = []
    monkeypatch.setattr(notify, "send_ntfy", lambda url, title, body: sent.append((title, body)))

    alerts = client.get("/api/alerts/charges", params={"refresh": True}).json()
    kinds = {(a["kind"], a["name"]) for a in alerts}
    assert ("price_change", "NETFLIX.COM") in kinds
    assert ("new_subscription", "CRAVE") in kinds
    # Small changes, amounts that always vary (hydro) and long-known merchants stay quiet.
    assert not any(n in a["name"] for a in alerts for n in ("SPOTIFY", "COSTCO", "HYDRO"))
    netflix = next(a for a in alerts if a["kind"] == "price_change")
    assert netflix["usual_amount"] == -16.49 and netflix["amount"] == -18.99 and netflix["change"] == 2.5
    assert len(sent) == 2 and any("18.99" in b for _, b in sent)

    # Each alert is sent once, and a dismissed one stays gone.
    client.get("/api/alerts/charges", params={"refresh": True})
    assert len(sent) == 2
    assert client.post(f"/api/alerts/charges/{netflix['id']}/dismiss").status_code == 200
    again = client.get("/api/alerts/charges", params={"refresh": True}).json()
    assert [a["name"] for a in again] == ["CRAVE"]

    # The hourly job runs the same detection for everyone.
    from app.db import SessionLocal
    from app.services import charge_alerts
    with SessionLocal() as db:
        assert charge_alerts.run_all(db) == 0


# --- Year in review ------------------------------------------------------------------------

def test_year_in_review(client):
    chq, cats = setup(client)
    client.patch(f"/api/accounts/{chq['id']}", json={"opening_balance": 0})
    y = date.today().year - 1
    tx(client, chq, -200, "LOBLAWS", date(y - 1, 6, 1), cats["Groceries"]["id"])
    tx(client, chq, 5000, "PAYROLL", date(y, 1, 15), cats["Salary"]["id"])
    tx(client, chq, 5000, "PAYROLL", date(y, 2, 15), cats["Salary"]["id"])
    tx(client, chq, -300, "LOBLAWS", date(y, 1, 20), cats["Groceries"]["id"])
    dinner = tx(client, chq, -100, "RESTAURANT", date(y, 2, 2), cats["Dining out"]["id"])
    pid = client.post("/api/people", json={"name": "Sam"}).json()["id"]
    client.put(f"/api/transactions/{dinner['id']}/shares", json={"shares": [{"person_id": pid, "amount": 50}]})
    pharmacy = tx(client, chq, -150, "SHOPPERS", date(y, 3, 3))
    client.put(f"/api/transactions/{pharmacy['id']}/splits", json={"lines": [
        {"category_id": cats["Health"]["id"], "amount": -100}, {"category_id": cats["Subscriptions"]["id"], "amount": -50}]})
    tx(client, chq, -1000, "TO TFSA", date(y, 4, 1), cats["Transfer"]["id"])
    plan = client.post("/api/plans", json={"kind": "tfsa", "year": y, "room": 7000}).json()
    client.post(f"/api/plans/{plan['id']}/entries", json={"date": f"{y}-04-01", "amount": 3000})

    r = client.get("/api/reports/year-review", params={"year": y}).json()
    assert r["totals"]["income"] == 10000 and r["totals"]["expense"] == 500  # 300 + our 50 + 150
    assert r["totals"]["savings_rate"] == 95.0
    groceries = next(c for c in r["categories"] if c["name"] == "Groceries")
    assert groceries["total"] == 300 and groceries["last_year"] == 200 and groceries["change"] == 100
    assert r["top_merchants"][0]["name"] == "LOBLAWS" and r["top_merchants"][0]["total"] == 300
    assert next(m for m in r["top_merchants"] if m["name"] == "RESTAURANT")["total"] == 50
    assert r["largest_purchases"][0]["amount"] == 300
    assert r["subscriptions"]["total"] == 50
    assert r["biggest_months"][0]["month"] == f"{y}-01"
    assert r["net_worth"]["change"] == 10000 - 300 - 100 - 150 - 1000
    assert r["registered"] == [{"kind": "tfsa", "label": "TFSA", "contributed": 3000, "withdrawn": 0, "room": 7000}]
    assert r["partial"] is False
