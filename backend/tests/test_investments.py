"""Investment holdings. Every sample file below is made up for the tests (fake accounts, round numbers)."""
import io
import json
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.importers.holdings import classify_type, parse_investment_file
from app.services import invest

PW = "correct horse battery"

# --- Synthetic sample files ---------------------------------------------------------

WS_HOLDINGS = """Account Name,Account Type,Account Classification,Account Number,Symbol,Exchange,MIC,Name,Security Type,Quantity,Position Direction,Market Price,Market Price Currency,Book Value (CAD),Book Value Currency (CAD),Book Value (Market),Book Value Currency (Market),Market Value,Market Value Currency,Market Unrealized Returns,Market Unrealized Returns Currency
Sample TFSA,TFSA,Self-directed,TEST-0001,XEQT,TSX,XTSE,Example All-Equity ETF Portfolio,EXCHANGE_TRADED_FUND,100.0000,LONG,30.00,CAD,2500.00,CAD,2500.00,CAD,3000.00,CAD,500.00,CAD
Sample TFSA,TFSA,Self-directed,TEST-0001,ZAG,TSX,XTSE,Example Aggregate Bond Index ETF,EXCHANGE_TRADED_FUND,50.0000,LONG,14.00,CAD,750.00,CAD,750.00,CAD,700.00,CAD,-50.00,CAD
Sample Cash,Non-registered,Self-directed,TEST-0002,VFV,TSX,XTSE,Example S&P 500 Index ETF,EXCHANGE_TRADED_FUND,10.0000,LONG,120.00,CAD,1000.00,CAD,1000.00,CAD,1200.00,CAD,200.00,CAD

"As of 2026-09-01 00:00 GMT-04:00"
"""

WS_ACTIVITY = """transaction_date,settlement_date,account_id,account_type,activity_type,activity_sub_type,direction,symbol,name,currency,quantity,unit_price,commission,net_cash_amount
2026-01-05,2026-01-06,TEST-0002,Non-registered,Trade,BUY,LONG,XEQT,Example All-Equity ETF Portfolio,CAD,100,25.00,0,-2500.00
2026-02-10,2026-02-11,TEST-0002,Non-registered,MoneyMovement,EFT,,,,CAD,,,,5000.00
2026-03-31,2026-03-31,TEST-0002,Non-registered,Dividend,,,XEQT,Example All-Equity ETF Portfolio,CAD,,,,42.50
2026-04-15,2026-04-16,TEST-0002,Non-registered,Trade,SELL,LONG,XEQT,Example All-Equity ETF Portfolio,CAD,40,30.00,0,1200.00
"""

WS_STATEMENT = """date,transaction,description,amount,balance,currency
2026-01-05,BUY,"XEQT - Example All-Equity ETF Portfolio: Bought 10.0000 shares (executed at 2026-01-05)",-250.00,750.00,CAD
2026-01-20,CONT,Contribution (executed at 2026-01-20),1000.00,1750.00,CAD
2026-03-28,DIV,"XEQT - Example All-Equity ETF Portfolio: Cash dividend distribution, received on 2026-03-28",4.25,1754.25,CAD
2026-04-02,SELL,"XEQT - Example All-Equity ETF Portfolio: Sold 5.0000 shares (executed at 2026-04-02)",140.00,1894.25,CAD
"""

QUESTRADE = """Transaction Date,Settlement Date,Action,Symbol,Description,Quantity,Price,Gross Amount,Commission,Net Amount,Currency,Account #,Activity Type,Account Type
2026-01-08 12:00:00 AM,2026-01-09 12:00:00 AM,Buy,VCN.TO,EXAMPLE FTSE CANADA ALL CAP INDEX ETF,200.00000,40.00000000,-8000.00,-9.95,-8009.95,CAD,00000000,Trades,Individual margin
2026-01-15 12:00:00 AM,2026-01-15 12:00:00 AM,CON,,CONT 2026,0.00000,0.00000000,0.00,0.00,10000.00,CAD,00000000,Deposits,Individual margin
2026-03-31 12:00:00 AM,2026-03-31 12:00:00 AM,DIV,VCN.TO,EXAMPLE FTSE CANADA ALL CAP INDEX ETF CASH DIV ON 200 SHS,0.00000,0.00000000,0.00,0.00,50.00,CAD,00000000,Dividends,Individual margin
2026-03-31 12:00:00 AM,2026-03-31 12:00:00 AM,REI,VCN.TO,EXAMPLE FTSE CANADA ALL CAP INDEX ETF REIN @ 41.6667,1.00000,41.66670000,0.00,0.00,0.00,CAD,00000000,Dividends,Individual margin
2026-05-01 12:00:00 AM,2026-05-02 12:00:00 AM,Sell,VCN.TO,EXAMPLE FTSE CANADA ALL CAP INDEX ETF,-50.00000,45.00000000,2250.00,-9.95,2240.05,CAD,00000000,Trades,Individual margin
2026-06-30 12:00:00 AM,2026-06-30 12:00:00 AM,FCH,,EXAMPLE ACCOUNT FEE,0.00000,0.00000000,0.00,0.00,-25.00,CAD,00000000,Fees and rebates,Individual margin
"""

GENERIC_FR = """Date;Type;Symbole;Quantité;Prix;Montant;Devise
2026-02-01;Achat;XBB;10;28,50;285,00;CAD
2026-03-01;Dividende;XBB;;;3,10;CAD
2026-04-01;Fractionnement;XBB;;;;CAD
2026-05-01;Vente;XBB;4;29,00;116,00;CAD
"""

GENERIC_EN = """date,type,symbol,quantity,price,amount
01/10/2026,buy,ABC,10,5.00,50.00
02/10/2026,split,ABC,,,
03/10/2026,sell,ABC,5,6.00,30.00
"""


def _parse(text, name="export.csv", source=None):
    return parse_investment_file(name, text.encode(), source)


# --- Parsers ------------------------------------------------------------------------

def test_wealthsimple_holdings_export():
    r = _parse(WS_HOLDINGS)
    assert r.source == "wealthsimple_holdings" and r.kind == "holdings"
    assert r.as_of == date(2026, 9, 1)
    assert [h.symbol for h in r.holdings] == ["XEQT", "ZAG", "VFV"]
    x = r.holdings[0]
    assert x.quantity == Decimal("100") and x.cost_basis == Decimal("2500.00") and x.price == Decimal("30.00")
    assert x.exchange == "TSX" and x.price_currency == "CAD"
    assert {h.account_label for h in r.holdings} == {"Sample TFSA", "Sample Cash"}


def test_wealthsimple_activity_export():
    r = _parse(WS_ACTIVITY)
    assert r.source == "wealthsimple_activity"
    kinds = [(a.kind, a.symbol, a.quantity, a.amount) for a in r.activities]
    assert kinds == [("buy", "XEQT", Decimal("100"), Decimal("2500.00")), ("dividend", "XEQT", Decimal(0), Decimal("42.50")),
                     ("sell", "XEQT", Decimal("40"), Decimal("1200.00"))]
    assert r.skipped == 1  # the EFT deposit stays with the account's transactions


def test_wealthsimple_statement_reads_description():
    r = _parse(WS_STATEMENT)
    assert r.source == "wealthsimple_statement"
    assert [(a.kind, a.symbol, a.quantity) for a in r.activities] == [
        ("buy", "XEQT", Decimal("10.0000")), ("dividend", "XEQT", Decimal(0)), ("sell", "XEQT", Decimal("5.0000"))]
    assert r.activities[0].amount == Decimal("250.00") and r.activities[0].price == Decimal("25")
    assert r.activities[0].name == "Example All-Equity ETF Portfolio"
    assert r.skipped_types == {"CONT": 1}


def test_questrade_activity():
    r = _parse(QUESTRADE)
    assert r.source == "questrade"
    got = [(a.kind, a.symbol, a.exchange, a.quantity, a.amount, a.commission) for a in r.activities]
    assert got[0] == ("buy", "VCN", "TSX", Decimal("200.00000"), Decimal("8000.00"), Decimal("9.95"))
    assert got[1][:2] == ("dividend", "VCN") and got[1][4] == Decimal("50.00")
    assert got[2][0] == "reinvested_dividend" and got[2][3] == Decimal("1.00000")
    assert got[3] == ("sell", "VCN", "TSX", Decimal("50.00000"), Decimal("2250.00"), Decimal("9.95"))
    assert got[4][0] == "fee" and got[4][4] == Decimal("25.00")
    assert r.skipped == 1  # the contribution


def test_generic_french_and_english():
    fr = _parse(GENERIC_FR)
    assert fr.source == "generic"
    assert [a.kind for a in fr.activities] == ["buy", "dividend", "sell"]
    assert fr.activities[0].price == Decimal("28.50") and fr.activities[0].amount == Decimal("285.00")
    assert any("split without a ratio" in w for w in fr.warnings)  # never guessed
    en = _parse(GENERIC_EN)
    assert [a.kind for a in en.activities] == ["buy", "sell"]
    assert en.activities[0].date == date(2026, 1, 10)


def test_classify_type_is_tolerant():
    assert classify_type("Reinvested dividend") == ("reinvested_dividend", True)
    assert classify_type("MARKET BUY") == ("buy", True)
    assert classify_type("Contribution") == (None, True)
    assert classify_type("something odd")[1] is False


def test_rejects_non_csv():
    with pytest.raises(ValueError):
        parse_investment_file("statement.pdf", b"%PDF-1.7 binary")


# --- ACB engine ---------------------------------------------------------------------

class A:
    """Stand-in activity for the pure cost engine."""
    def __init__(self, kind, qty=0, amount=0, commission=0, ratio=None, d=date(2026, 1, 1)):
        self.id, self.kind, self.quantity, self.amount, self.commission = None, kind, Decimal(str(qty)), Decimal(str(amount)), Decimal(str(commission))
        self.split_ratio = Decimal(str(ratio)) if ratio else None
        self.date = d


def run(*acts):
    s = invest.CostState()
    for a in acts:
        invest.apply_activity(s, a, a.amount, a.commission, ledger=True)
    return s


def test_average_cost_method():
    s = run(A("buy", 100, 1000, 10), A("buy", 50, 600))
    assert s.quantity == 150 and s.cost == Decimal("1610")
    s = run(A("buy", 100, 1000, 10), A("buy", 50, 600), A("sell", 60, 900, 10))
    # ACB per unit 10.7333...; 60 units carry 644.00 of cost; proceeds 890 -> gain 246
    date_, proceeds, cost_sold, gain = s.realized[0]
    assert proceeds == Decimal("890") and round(cost_sold, 2) == Decimal("644.00") and round(gain, 2) == Decimal("246.00")
    assert s.quantity == 90 and round(s.cost, 2) == Decimal("966.00")


def test_split_roc_and_reinvested_distributions():
    s = run(A("buy", 10, 100), A("split", ratio=2), A("reinvested_dividend", 1, 6), A("return_of_capital", amount=10))
    assert s.quantity == 21 and s.cost == Decimal("96")
    phantom = run(A("buy", 10, 100), A("reinvested_dividend", 0, 5))  # notional distribution: cost up, no units
    assert phantom.quantity == 10 and phantom.cost == Decimal("105")
    over = run(A("buy", 1, 10), A("return_of_capital", amount=15))
    assert over.cost == 0 and over.realized[-1][3] == Decimal("5")  # ROC beyond ACB is a gain


def test_stooq_parser_and_symbols():
    ok = "Symbol,Date,Time,Open,High,Low,Close,Volume\nXEQT.CA,2026-09-25,22:00:00,30.1,30.5,30.0,30.42,12345\n"
    assert invest.StooqProvider.parse(ok) == (date(2026, 9, 25), Decimal("30.42"))
    nd = "Symbol,Date,Time,Open,High,Low,Close,Volume\nNOPE.CA,N/D,N/D,N/D,N/D,N/D,N/D,N/D\n"
    assert invest.StooqProvider.parse(nd) is None
    p = invest.StooqProvider()
    from app.models_invest import Security
    assert p.symbol_for(Security(symbol="XEQT", exchange="TSX", currency="CAD")) == "xeqt.ca"
    assert p.symbol_for(Security(symbol="VTI", exchange="NYSE", currency="USD")) == "vti.us"
    assert p.symbol_for(Security(symbol="ZZZ", exchange="", currency="CAD", price_symbol="zzz.ca")) == "zzz.ca"


# --- API ----------------------------------------------------------------------------

def register(c, email="a@home.lan", **extra):
    r = c.post("/api/auth/register", json={"email": email, "password": PW, "name": "A", **extra})
    assert r.status_code == 200, r.text


def upload(c, path, account_id, text, options=None, name="export.csv"):
    return c.post(path, data={"account_id": str(account_id), "options": json.dumps(options or {})},
                  files={"file": (name, io.BytesIO(text.encode()), "text/csv")})


def _acct(c, **kw):
    body = {"name": "Sample TFSA", "type": "investment", "currency": "CAD"} | kw
    return c.post("/api/accounts", json=body).json()["id"]


def test_holdings_import_values_and_net_worth(client):
    register(client)
    tfsa = _acct(client)
    prev = upload(client, "/api/invest/import/preview", tfsa, WS_HOLDINGS).json()
    assert prev["kind"] == "holdings" and prev["account_labels"] == ["Sample Cash", "Sample TFSA"]
    # Several accounts in one file: the member must pick one.
    assert upload(client, "/api/invest/import/commit", tfsa, WS_HOLDINGS).status_code == 422
    r = upload(client, "/api/invest/import/commit", tfsa, WS_HOLDINGS,
               {"account_label": "Sample TFSA", "as_of": date.today().isoformat()}).json()
    assert r["imported"] == 2
    client.post("/api/transactions", json={"account_id": tfsa, "date": date.today().isoformat(), "amount": 100, "description": "Cash"})

    ov = client.get("/api/invest/overview").json()
    acct = ov["accounts"][0]
    assert acct["registration"] == "tfsa"  # from the account name
    assert acct["cash"] == 100.0 and acct["holdings_value"] == 3700.0 and acct["total"] == 3800.0
    xeqt = next(p for p in acct["positions"] if p["symbol"] == "XEQT")
    assert xeqt["gain"] == 500.0 and xeqt["gain_pct"] == 20.0 and xeqt["price_age_days"] == 0
    assert xeqt["avg_cost"] == 25.0 and xeqt["asset_class"] == "equity"
    zag = next(p for p in acct["positions"] if p["symbol"] == "ZAG")
    assert zag["asset_class"] == "fixed_income" and zag["gain"] == -50.0
    classes = {x["key"]: x["value"] for x in ov["allocation"]["by_class"]}
    assert classes == {"equity": 3000.0, "fixed_income": 700.0, "cash": 100.0}
    assert ov["totals"]["gain"] == 450.0 and ov["totals"]["total"] == 3800.0

    accounts = client.get("/api/accounts").json()["items"]
    assert accounts[0]["balance"] == 3800.0 and accounts[0]["cash_balance"] == 100.0
    nw = client.get("/api/reports/net-worth").json()
    assert nw["current"]["net"] == 3800.0 and nw["price_warnings"] == []
    dash = client.get("/api/reports/dashboard").json()
    assert dash["total_balance"] == 3800.0

    # A manual price wins and moves the value.
    sec_id = xeqt["security_id"]
    client.post(f"/api/invest/securities/{sec_id}/prices", json={"close": 32, "date": date.today().isoformat()})
    assert client.get("/api/reports/net-worth").json()["current"]["net"] == 4000.0

    # Undo removes the snapshots again.
    imp = client.get("/api/invest/imports").json()[0]
    assert client.delete(f"/api/invest/imports/{imp['id']}").json()["removed"] == 2
    assert client.get("/api/reports/net-worth").json()["current"]["net"] == 100.0


def test_activity_import_dividends_acb_and_dedupe(client):
    register(client)
    acct = _acct(client, name="Sample margin")
    r = upload(client, "/api/invest/import/commit", acct, QUESTRADE).json()
    assert r["imported"] == 5 and r["skipped"] == 1
    again = upload(client, "/api/invest/import/preview", acct, QUESTRADE).json()
    assert again["duplicates"] == 5 and again["new"] == 0

    ov = client.get("/api/invest/overview").json()
    a = ov["accounts"][0]
    assert a["registration"] == "non_registered"
    vcn = a["positions"][0]
    assert vcn["quantity"] == 151.0
    # No price yet: counted at cost and flagged, never guessed.
    assert vcn["valued_at_cost"] and ov["price_warnings"][0]["symbol"] == "VCN"
    # The REI row has a matching cash dividend, so it isn't counted twice.
    assert ov["totals"]["dividends_ytd"] == 50.0 if date.today().year == 2026 else True

    acb = client.get(f"/api/invest/acb/{acct}?year=2026").json()
    row = acb["items"][0]
    # ACB: 8000 + 9.95 + 41.6667 = 8051.6167 for 201 units; selling 50 removes 2002.89
    assert row["units"] == 151.0 and row["acb"] == pytest.approx(6048.73, abs=0.01)
    assert row["realized_gain_year"] == pytest.approx(2240.05 - 2002.89, abs=0.01)
    assert "not tax advice" in acb["note"]

    client.put(f"/api/invest/accounts/{acct}/registration", json={"registration": "rrsp"})
    assert client.get(f"/api/invest/acb/{acct}").json()["items"] == []


def test_usd_holding_without_rate_warns(client):
    register(client)
    acct = _acct(client, name="Sample RRSP")
    client.put("/api/invest/holdings", json={"account_id": acct, "symbol": "VTI", "exchange": "NYSE", "quantity": 10,
                                            "cost_basis": 2000, "price": 250, "as_of": date.today().isoformat()})
    nw = client.get("/api/reports/net-worth").json()
    assert nw["current"]["net"] == 0.0
    assert [w["pair"] for w in nw["warnings"]] == ["USD→CAD"]
    ov = client.get("/api/invest/overview").json()
    assert ov["accounts"][0]["positions"][0]["market_value"] is None
    assert ov["warnings"][0]["pair"] == "USD→CAD"
    client.post("/api/currency/rates", json={"base": "USD", "quote": "CAD", "rate": 1.4, "date": (date.today() - timedelta(days=400)).isoformat()})
    assert client.get("/api/reports/net-worth").json()["current"]["net"] == 3500.0
    # Past months before the snapshot don't show holdings that nothing says existed then.
    assert client.get("/api/reports/net-worth").json()["series"][0]["net"] == 0.0


def test_position_from_activity_history(client):
    register(client)
    acct = _acct(client, name="Sample FHSA")
    client.post("/api/invest/activities", json={"account_id": acct, "date": "2026-01-10", "kind": "buy", "symbol": "XEQT",
                                               "exchange": "TSX", "quantity": 10, "price": 25})
    sec = client.get("/api/invest/securities").json()[0]
    client.post(f"/api/invest/securities/{sec['id']}/prices", json={"close": 30, "date": "2026-02-01"})
    client.post("/api/invest/activities", json={"account_id": acct, "date": "2026-03-01", "kind": "split", "security_id": sec["id"],
                                               "split_ratio": 2})
    ov = client.get("/api/invest/overview").json()
    pos = ov["accounts"][0]["positions"][0]
    assert pos["quantity"] == 20.0 and pos["cost"] == 250.0 and pos["price_date"] == "2026-02-01"
    assert client.post("/api/invest/activities", json={"account_id": acct, "date": "2026-03-01", "kind": "buy",
                                                      "symbol": "XEQT"}).status_code == 422


def test_price_fetch_is_off_by_default_and_keeps_last_price(client, monkeypatch):
    register(client)
    acct = _acct(client)
    client.put("/api/invest/holdings", json={"account_id": acct, "symbol": "XEQT", "exchange": "TSX", "quantity": 1,
                                            "cost_basis": 25, "price": 30, "as_of": "2026-01-02"})
    assert client.post("/api/invest/prices/fetch").status_code == 403
    assert client.get("/api/admin/settings").json()["prices_fetch_enabled"] is False
    client.patch("/api/admin/settings", json={"prices_fetch_enabled": True})

    sent = []

    def fake_fetch(self, symbol):
        sent.append(symbol)
        return (date(2026, 9, 25), Decimal("31.50"))
    monkeypatch.setattr(invest.StooqProvider, "fetch", fake_fetch)
    r = client.post("/api/invest/prices/fetch").json()
    assert r["updated"] == 1 and sent == ["xeqt.ca"]  # only the ticker is sent

    def broken(self, symbol):
        raise ConnectionError("offline")
    monkeypatch.setattr(invest.StooqProvider, "fetch", broken)
    r = client.post("/api/invest/prices/fetch").json()
    assert r["failed"] == ["XEQT"]
    sec = client.get("/api/invest/securities").json()[0]
    assert sec["price"] == 31.5 and sec["price_date"] == "2026-09-25" and "Couldn't reach" in sec["last_fetch_error"]


def test_members_cannot_see_each_others_holdings(client):
    register(client)
    acct = _acct(client)
    client.put("/api/invest/holdings", json={"account_id": acct, "symbol": "XEQT", "quantity": 1, "cost_basis": 25})
    sec_id = client.get("/api/invest/securities").json()[0]["id"]
    code = client.post("/api/admin/invites", json={}).json()["code"]
    client.post("/api/auth/logout")
    register(client, "b@home.lan", invite_code=code)
    assert client.get("/api/invest/securities").json() == []
    assert client.get("/api/invest/overview").json()["accounts"] == []
    assert client.post(f"/api/invest/securities/{sec_id}/prices", json={"close": 1}).status_code == 404
    assert client.put("/api/invest/holdings", json={"account_id": acct, "symbol": "X", "quantity": 1}).status_code == 404
