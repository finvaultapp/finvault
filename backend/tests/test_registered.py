"""TFSA / FHSA / RRSP statements: plan detection, line types, parsers, counting, next-year estimates.

Every sample below is made up for these tests ("SAMPLE", "Test Person", round numbers). None comes from a
real statement; the Wealthsimple and Questrade layouts are best guesses matched by header names.
"""
import io
import json
import zipfile
from datetime import date
from decimal import Decimal

import pytest

from app.importers import parse_file
from app.importers.registered import classify, is_spousal, suggest_kind
from app.services import registered as reg

from .test_api import PW, register
from .test_importers import positioned_pdf, table_pdf


def D(x):
    return Decimal(str(x))


# --- Which plan -----------------------------------------------------------------------------------

@pytest.mark.parametrize("text,kind", [
    ("Wealthsimple TFSA", "tfsa"), ("Tax-Free Savings Account", "tfsa"), ("CELI Desjardins", "tfsa"),
    ("Compte d'épargne libre d'impôt", "tfsa"), ("My FHSA", "fhsa"), ("CELIAPP", "fhsa"),
    ("First Home Savings Account", "fhsa"), ("Questrade RRSP", "rrsp"), ("REER collectif", "rrsp"),
    ("Spousal RRSP", "rrsp"), ("REER de conjoint", "rrsp"), ("RRIF", None), ("FERR Banque Nationale", None),
    ("RRSP to RRIF conversion", None), ("Joint chequing", None), ("Emergency savings", None),
    ("Individual LIRA", None), ("Family RESP", None),
])
def test_suggest_kind_from_names(text, kind):
    assert suggest_kind(text) == kind


def test_suggest_kind_from_statement_text_and_spousal():
    fhsa_text = ("SAMPLE First Home Savings Account (FHSA) statement. Activity: RRSP to FHSA transfer 5,000.00. "
                 "Contribution 2,000.00. FHSA participation room is shown in CRA My Account.")
    assert suggest_kind(fhsa_text) == "fhsa"
    assert suggest_kind("Relevé CELIAPP - transfert du REER au CELIAPP") == "fhsa"
    assert is_spousal("Spousal RRSP") and is_spousal("REER de conjoint") and not is_spousal("Individual RRSP")


# --- What each line is ----------------------------------------------------------------------------

@pytest.mark.parametrize("kind,amount,types,desc,move", [
    # Statement type codes
    ("tfsa", 500, ["CONT"], "Contribution", "contribution"),
    ("tfsa", -200, ["WD"], "Withdrawal", "withdrawal"),
    ("tfsa", 3000, ["TFI"], "", "transfer_in"),
    ("tfsa", -3000, ["TFO"], "", "transfer_out"),
    ("tfsa", 12.5, ["DIV"], "XEQT dividend", "growth"),
    ("tfsa", 1.1, ["INT"], "", "growth"),
    ("tfsa", -4.99, ["FEE"], "", "fee"),
    ("tfsa", -1000, ["BUY"], "XEQT - iShares", "trade"),
    ("tfsa", 950, ["SELL"], "VFV", "trade"),
    ("rrsp", 2000, ["CON"], "", "contribution"),
    # English words
    ("tfsa", 100, [], "Contribution - pre-authorized", "contribution"),
    ("tfsa", -50, [], "Withdrawal to chequing", "withdrawal"),
    ("tfsa", 4000, ["Transfer"], "Institutional transfer from Other Bank", "transfer_in"),
    ("tfsa", -4000, [], "Institutional transfer to Other Bank", "transfer_out"),
    ("tfsa", 1000, ["Transfer"], "Internal transfer from Cash account", "contribution"),
    ("tfsa", -1000, [], "Internal transfer to Cash account", "withdrawal"),
    ("tfsa", 2500, ["Transfer in"], "", "transfer_in"),
    ("tfsa", -2500, ["Transfer out"], "", "transfer_out"),
    ("tfsa", 3.21, [], "Interest paid", "growth"),
    ("tfsa", 8.0, [], "Dividend XEQT", "growth"),
    ("tfsa", -9.0, [], "Monthly account fee", "fee"),
    ("tfsa", -100, [], "Buy 4 shares XEQT", "trade"),
    ("fhsa", 5000, [], "RRSP to FHSA transfer", "rrsp_to_fhsa"),
    ("fhsa", 5000, ["TRFIN"], "Transfer from RRSP", "rrsp_to_fhsa"),
    ("rrsp", -5000, [], "RRSP to FHSA transfer", "transfer_out"),
    # French words
    ("tfsa", 500, ["Cotisation"], "", "contribution"),
    ("tfsa", -200, [], "Retrait au compte chèques", "withdrawal"),
    ("tfsa", 1500, [], "Transfert institutionnel entrant", "transfer_in"),
    ("tfsa", -1500, ["Transfert sortant"], "", "transfer_out"),
    ("tfsa", 2.5, [], "Intérêts créditeurs", "growth"),
    ("tfsa", 7.0, ["Dividende"], "", "growth"),
    ("tfsa", -3.0, [], "Frais d'administration", "fee"),
    ("tfsa", -800, ["Achat"], "", "trade"),
    ("tfsa", 820, ["Vente"], "", "trade"),
    ("fhsa", 3000, [], "Transfert du REER au CELIAPP", "rrsp_to_fhsa"),
    ("tfsa", 250, [], "Virement interne du compte chèques", "contribution"),
    # Bank TFSA savings accounts: no type column, money in / out by sign
    ("tfsa", 300, [], "INTERAC E-TRANSFER FROM T PERSON", "contribution"),
    ("tfsa", -75, [], "TRANSFER TO CHEQUING", "withdrawal"),
    ("tfsa", 300, ["DEBIT"], "ONLINE TRANSFER", "contribution"),
    ("tfsa", 0, [], "Statement message", "other"),
])
def test_classify_english_and_french(kind, amount, types, desc, move):
    assert classify(kind, D(amount), types, desc) == move


def test_classify_strict_brokerage_lines_never_guess_from_the_sign():
    assert classify("tfsa", D(10), ["Corporate actions"], "Name change", strict=True) == "other"
    assert classify("tfsa", D(10), ["Corporate actions"], "Name change") == "contribution"


# --- Parsers ---------------------------------------------------------------------------------------

def p(name, text, **kw):
    return parse_file(name, text.encode("utf-8"), **kw)


def moves(r, kind):
    from app.importers.registered import classify_result
    classify_result(r, kind)
    return [t.plan_move for t in r.transactions]


OFX_TFSA = """OFXHEADER:100
DATA:OFXSGML
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><CURDEF>CAD
<BANKACCTFROM><BANKID>999<ACCTID>SAMPLE-TFSA-001<ACCTTYPE>SAVINGS</BANKACCTFROM>
<BANKTRANLIST>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260105<TRNAMT>1000.00<FITID>S1<NAME>TRANSFER FROM CHEQUING</STMTTRN>
<STMTTRN><TRNTYPE>INT<DTPOSTED>20260131<TRNAMT>2.15<FITID>S2<NAME>INTEREST</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260210<TRNAMT>-250.00<FITID>S3<NAME>TRANSFER TO CHEQUING</STMTTRN>
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
"""


def test_ofx_bank_tfsa_savings():
    r = p("tangerine-tfsa-sample.qfx", OFX_TFSA)
    assert [t.type_text for t in r.transactions] == ["CREDIT", "INT", "DEBIT"]
    assert moves(r, "tfsa") == ["contribution", "growth", "withdrawal"]
    assert r.kind_hint == "tfsa"  # from the file name


def test_qif_bank_tfsa():
    qif = "!Type:Bank\nD01/05/2026\nT500.00\nPDEPOSIT\n^\nD01/31/2026\nT1.05\nPINTEREST\n^\nD02/02/2026\nT-100.00\nPWITHDRAWAL\n^\n"
    r = p("sample.qif", qif)
    assert moves(r, "tfsa") == ["contribution", "growth", "withdrawal"]


def test_csv_preset_tangerine_tfsa_and_french_type_column():
    csv_text = ("Date,Transaction,Name,Memo,Amount\n"
                "01/05/2026,DEPOSIT,SAMPLE TRANSFER IN,From chequing,1500.00\n"
                "01/31/2026,OTHER,INTEREST PAID,,3.10\n"
                "02/15/2026,WITHDRAWAL,SAMPLE TRANSFER OUT,To chequing,-400.00\n")
    r = p("tfsa.csv", csv_text)
    assert r.preset == "tangerine"
    assert moves(r, "tfsa") == ["contribution", "growth", "withdrawal"]
    fr = ("Date;Type;Description;Montant\n"
          "2026-01-05;Cotisation;Virement SAMPLE;1000,00\n"
          "2026-01-31;Intérêts;Intérêts créditeurs;2,50\n"
          "2026-02-20;Retrait;Retrait SAMPLE;-300,00\n"
          "2026-03-01;Frais;Frais mensuels;-1,00\n")
    r = p("celi.csv", fr)
    assert [t.type_text for t in r.transactions] == ["Cotisation", "Intérêts", "Retrait", "Frais"]
    assert moves(r, "tfsa") == ["contribution", "growth", "withdrawal", "fee"]


def test_generic_brokerage_csv_with_a_mapped_type_column():
    text = ("Posted,Kind,Details,Value\n"
            "2026-01-02,CONT,Contribution,2000.00\n"
            "2026-01-03,BUY,SAMPLE ETF,-1990.00\n"
            "2026-03-31,DIV,SAMPLE ETF,11.20\n")
    r = p("broker.csv", text, mapping={"date": 0, "type": 1, "description": 2, "amount": 3})
    assert moves(r, "fhsa") == ["contribution", "trade", "growth"]


WS_STATEMENT_CSV = ("date,transaction,description,amount,balance,currency\n"
                    "2026-01-05,CONT,Contribution (executed at 2026-01-05),6000.00,6000.00,CAD\n"
                    "2026-01-06,BUY,XEQT - iShares Core Equity ETF: Bought 200.0000 shares (executed at 2026-01-06),-5980.00,20.00,CAD\n"
                    "2026-03-28,DIV,XEQT - iShares Core Equity ETF: Cash dividend distribution,24.10,44.10,CAD\n"
                    "2026-04-02,WD,Withdrawal,-500.00,-455.90,CAD\n")


def test_wealthsimple_monthly_statement_csv():
    r = p("TFSA-monthly-statement-transactions-SAMPLE-2026-04-01.csv", WS_STATEMENT_CSV)
    assert r.preset == "wealthsimple"
    assert moves(r, "tfsa") == ["contribution", "trade", "growth", "withdrawal"]
    assert r.kind_hint == "tfsa"


WS_ACTIVITY = ("transaction_date,settlement_date,account_id,account_type,activity_type,activity_sub_type,direction,"
               "symbol,name,currency,quantity,unit_price,commission,net_cash_amount\n"
               "2026-01-03,2026-01-03,SAMPLE-1,FHSA,Deposit,,,,,CAD,,,,8000.00\n"
               "2026-01-04,2026-01-05,SAMPLE-1,FHSA,Trade,BUY,,VEQT,Vanguard All-Equity ETF,CAD,100,40.00,0,-4000.00\n"
               "2026-02-10,2026-02-10,SAMPLE-1,FHSA,Institutional transfer,,,,,CAD,,,,5000.00\n"
               "2026-03-15,2026-03-15,SAMPLE-1,FHSA,Internal transfer,,,,,CAD,,,,1000.00\n"
               "2026-03-31,2026-03-31,SAMPLE-1,FHSA,Dividend,,,VEQT,Vanguard All-Equity ETF,CAD,,,,9.50\n"
               "2026-04-01,2026-04-01,SAMPLE-1,FHSA,Corporate action,NAME_CHANGE,,VEQT,,CAD,,,,0.00\n"
               "2026-04-02,2026-04-02,SAMPLE-2,TFSA,Deposit,,,,,CAD,,,,700.00\n")


def test_wealthsimple_activity_export_keeps_this_plans_lines():
    r = p("activities-export-SAMPLE.csv", WS_ACTIVITY, registered_kind="fhsa")
    assert r.layout == "Wealthsimple activity"
    assert [t.amount for t in r.transactions] == [D(8000), D(-4000), D(5000), D(1000), D("9.5"), D(0)]
    assert moves(r, "fhsa") == ["contribution", "trade", "transfer_in", "contribution", "growth", "other"]
    assert "Lines for other accounts in this file were left out." in r.warnings
    # Without a plan on the account, nothing is dropped but the member is warned, and the file names its plan.
    r = p("activities-export-SAMPLE.csv", WS_ACTIVITY)
    assert len(r.transactions) == 7 and r.kind_hint is None
    assert p("fhsa-only.csv", WS_ACTIVITY.rsplit("2026-04-02", 1)[0]).kind_hint == "fhsa"
    assert any("more than one account" in w for w in r.warnings)


QUESTRADE = ("Transaction Date,Settlement Date,Action,Symbol,Description,Quantity,Price,Gross Amount,Commission,"
             "Net Amount,Currency,Account #,Activity Type,Account Type\n"
             "2026-01-02 12:00:00 AM,2026-01-02 12:00:00 AM,CON,,CONTRIBUTION SAMPLE,0,0,0,0,7000.00,CAD,00000001,Deposits,Individual TFSA\n"
             "2026-01-05 12:00:00 AM,2026-01-07 12:00:00 AM,Buy,XEQT.TO,ISHARES CORE EQUITY ETF SAMPLE,100,30.00,-3000.00,-4.95,-3004.95,CAD,00000001,Trades,Individual TFSA\n"
             "2026-02-01 12:00:00 AM,2026-02-01 12:00:00 AM,,,INTEREST SAMPLE,0,0,0,0,0.42,CAD,00000001,Interest,Individual TFSA\n"
             "2026-02-15 12:00:00 AM,2026-02-15 12:00:00 AM,FCH,,ECN FEE SAMPLE,0,0,0,0,-0.35,CAD,00000001,Fees and rebates,Individual TFSA\n"
             "2026-03-20 12:00:00 AM,2026-03-20 12:00:00 AM,DIV,VFV.TO,VANGUARD S&P 500 SAMPLE,0,0,0,0,5.10,CAD,00000001,Dividends,Individual TFSA\n"
             "2026-03-25 12:00:00 AM,2026-03-25 12:00:00 AM,DIV,VTI,VANGUARD TOTAL MKT SAMPLE,0,0,0,0,3.00,USD,00000001,Dividends,Individual TFSA\n"
             "2026-04-10 12:00:00 AM,2026-04-10 12:00:00 AM,WDR,,WITHDRAWAL SAMPLE,0,0,0,0,-1000.00,CAD,00000001,Withdrawals,Individual TFSA\n"
             "2026-04-11 12:00:00 AM,2026-04-11 12:00:00 AM,TF6,,TRANSFER SAMPLE,0,0,0,0,-12.00,CAD,00000001,Transfers,Individual TFSA\n")


def test_questrade_activity_export():
    r = p("Activities_for_SAMPLE.csv", QUESTRADE, account_currency="CAD")
    assert r.layout == "Questrade activity"
    assert [t.date for t in r.transactions][:2] == [date(2026, 1, 2), date(2026, 1, 5)]
    assert [t.amount for t in r.transactions] == [D(7000), D("-3004.95"), D("0.42"), D("-0.35"), D("5.10"),
                                                  D(-1000), D(-12)]
    assert moves(r, "tfsa") == ["contribution", "trade", "growth", "fee", "growth", "withdrawal", "other"]
    assert any("another currency" in w for w in r.warnings)  # the USD dividend is left out of a CAD account
    assert r.kind_hint == "tfsa"


def test_spousal_rrsp_questrade_file_is_flagged():
    text = QUESTRADE.replace("Individual TFSA", "Spousal RRSP")
    r = p("Activities_for_SAMPLE.csv", text, account_currency="CAD")
    assert r.kind_hint == "rrsp" and r.spousal


def test_wealthsimple_monthly_statement_pdf():
    # Best-guess layout: Date | Transaction | Description | Charged | Credit | Balance, codes like CONT and BUY.
    C, CR, B = 400, 480, 560
    raw = table_pdf([
        [(40, "Wealthsimple SAMPLE ONLY - not a real statement")],
        [(40, "Tax-Free Savings Account (TFSA) - Test Person")],
        [(40, "Statement period Jan 1, 2026 to Jan 31, 2026")],
        [(40, "Opening balance"), (B, "0.00", "r")],
        [(40, "Closing balance"), (B, "1,013.05", "r")],
        [(40, "Date"), (110, "Transaction"), (200, "Description"), (C, "Charged", "r"), (CR, "Credit", "r"), (B, "Balance", "r")],
        [(40, "2026-01-05"), (110, "CONT"), (200, "Contribution"), (CR, "2,000.00", "r"), (B, "2,000.00", "r")],
        [(40, "2026-01-06"), (110, "BUY"), (200, "XEQT Bought 30 shares"), (C, "990.00", "r"), (B, "1,010.00", "r")],
        [(40, "2026-01-30"), (110, "DIV"), (200, "XEQT Dividend"), (CR, "3.05", "r"), (B, "1,013.05", "r")],
    ])
    r = parse_file("statement.pdf", raw)
    assert [t.amount for t in r.transactions] == [D(2000), D(-990), D("3.05")]
    assert [t.type_text for t in r.transactions] == ["CONT", "BUY", "DIV"]
    assert r.transactions[0].description == "Contribution"
    assert moves(r, "tfsa") == ["contribution", "trade", "growth"]
    assert r.kind_hint == "tfsa"


def test_bank_tfsa_pdf_statement_by_sign_and_wording():
    W, DP, B = 330, 420, 560
    raw = table_pdf([
        [(40, "SAMPLE BANK - TFSA SAVINGS - not a real statement")],
        [(40, "Statement period Feb 1, 2026 to Feb 28, 2026")],
        [(40, "Opening balance"), (B, "1,000.00", "r")],
        [(40, "Closing balance"), (B, "1,452.40", "r")],
        [(40, "Date"), (90, "Description"), (W, "Withdrawals", "r"), (DP, "Deposits", "r"), (B, "Balance", "r")],
        [(40, "Feb 03"), (90, "TRANSFER FROM CHEQUING"), (DP, "500.00", "r"), (B, "1,500.00", "r")],
        [(40, "Feb 14"), (90, "TRANSFER TO CHEQUING"), (W, "50.00", "r"), (B, "1,450.00", "r")],
        [(40, "Feb 28"), (90, "INTEREST"), (DP, "2.40", "r"), (B, "1,452.40", "r")],
    ])
    r = parse_file("estatement.pdf", raw)
    assert [t.amount for t in r.transactions] == [D(500), D(-50), D("2.40")]
    assert moves(r, "tfsa") == ["contribution", "withdrawal", "growth"]
    assert r.kind_hint == "tfsa"


# --- Next year's room (estimates) ---------------------------------------------------------------

def test_tfsa_estimate_with_withdrawals_and_known_or_unknown_limit():
    e = reg.tfsa_estimate(2025, D(7000), used=D(5000), withdrawn=D(2000))
    assert e["code"] == "tfsa_next" and e["year"] == 2026 and e["amount"] == 2000 + 2000 + 7000
    e = reg.tfsa_estimate(2026, D(20000), used=D(6000), withdrawn=D(1500))  # 2027's limit isn't announced yet
    assert e["code"] == "tfsa_next_partial" and e["amount"] == 14000 + 1500
    assert reg.tfsa_estimate(2026, None, D(0), D(0))["code"] == "needs_room"
    assert reg.TFSA_LIMITS[2015] == 10000 and reg.TFSA_LIMITS[2019] == 6000 and 2027 not in reg.TFSA_LIMITS


def test_fhsa_estimate_carry_forward_lifetime_and_opening_year():
    # Nothing contributed on $16,000 of room: carry-forward is capped at $8,000.
    e = reg.fhsa_estimate(2024, D(16000), used=D(0), lifetime=D(8000), opened=2023)
    assert e["amount"] == 16000 and e["carry"] == 8000 and e["lifetime_left"] == 32000
    # Some unused room carries forward in full when it's under the cap.
    e = reg.fhsa_estimate(2024, D(8000), used=D(5000), lifetime=D(5000), opened=2024)
    assert e["amount"] == 11000 and e["carry"] == 3000
    # The $40,000 lifetime limit wins.
    e = reg.fhsa_estimate(2027, D(16000), used=D(8000), lifetime=D(36000), opened=2023)
    assert e["amount"] == 4000 and e["lifetime_left"] == 4000
    e = reg.fhsa_estimate(2028, D(8000), used=D(8000), lifetime=D(40000), opened=2023)
    assert e["amount"] == 0
    # Over-contributed: nothing carries, next year is the plain $8,000.
    assert reg.fhsa_estimate(2025, D(8000), used=D(9000), lifetime=D(9000), opened=2025)["amount"] == 8000
    # 15-year limit from the year the first FHSA was opened.
    assert not reg.fhsa_estimate(2030, D(8000), D(0), D(0), opened=2023)["closing_soon"]
    assert reg.fhsa_estimate(2036, D(8000), D(0), D(0), opened=2023)["closing_soon"]
    assert reg.fhsa_estimate(2038, D(8000), D(0), D(0), opened=2023)["code"] == "fhsa_closed"


# --- Through the API ------------------------------------------------------------------------------

def upload(c, account_id, name, text, options=None, step="commit"):
    files = {"file": (name, io.BytesIO(text.encode("utf-8")), "text/csv")}
    data = {"account_id": str(account_id)}
    if options is not None:
        data["options"] = json.dumps(options)
    r = c.post(f"/api/imports/{step}", data=data, files=files)
    assert r.status_code == 200, r.text
    return r.json()


def plan_of(c, kind, year):
    return next(p for p in c.get("/api/plans").json() if p["kind"] == kind and p["year"] == year)


def test_import_into_a_tfsa_counts_by_type_and_makes_a_plan_with_no_room(client):
    register(client)
    acct = client.post("/api/accounts", json={"name": "Wealthsimple TFSA", "type": "investment"}).json()
    assert client.get("/api/accounts").json()["items"][0]["registered_suggestion"] == "tfsa"
    client.patch(f"/api/accounts/{acct['id']}", json={"registered_kind": "tfsa"})

    prev = upload(client, acct["id"], "ws.csv", WS_STATEMENT_CSV, step="preview")
    assert prev["registered_kind"] == "tfsa" and prev["suggested_kind"] is None
    assert [r["plan_move"] for r in prev["rows"]] == ["contribution", "trade", "growth", "withdrawal"]

    done = upload(client, acct["id"], "ws.csv", WS_STATEMENT_CSV)
    assert done["imported"] == 4
    year = done["registered"]["years"][0]
    assert done["registered"]["kind"] == "tfsa" and year["year"] == 2026 and year["room_missing"]
    assert year["contribution"] == {"n": 1, "amount": 6000.0} and year["withdrawal"] == {"n": 1, "amount": 500.0}
    assert year["not_counted"] == 2

    p26 = plan_of(client, "tfsa", 2026)
    assert p26["room"] is None and not p26["room_set"] and p26["remaining"] is None
    assert p26["contributed"] == 6000 and p26["withdrawn"] == 500
    assert p26["by_type"]["growth"] == 24.1 and p26["lines"]["trade"] == 1
    assert [a["name"] for a in p26["accounts"]] == ["Wealthsimple TFSA"]
    assert {"code": "needs_room", "level": "info", "year": 2026} in p26["warnings"]
    assert p26["estimate"]["code"] == "needs_room"

    # The member enters CRA's figure; the counts and the estimate follow.
    client.patch(f"/api/plans/{p26['id']}", json={"kind": "tfsa", "year": 2026, "room": 10000, "account_id": None})
    p26 = plan_of(client, "tfsa", 2026)
    assert p26["remaining"] == 4000 and p26["room_set"]
    assert p26["estimate"]["code"] == "tfsa_next_partial" and p26["estimate"]["amount"] == 4000 + 500

    # Re-importing the same file adds nothing and counts nothing twice.
    again = upload(client, acct["id"], "ws.csv", WS_STATEMENT_CSV)
    assert again["imported"] == 0 and again["skipped"] == 4
    assert plan_of(client, "tfsa", 2026)["contributed"] == 6000

    # Fixing a type later in the transaction editor changes the counts.
    txs = client.get("/api/transactions", params={"account_id": acct["id"]}).json()["items"]
    wd = next(t for t in txs if t["plan_move"] == "withdrawal")
    assert wd["registered_kind"] == "tfsa"
    r = client.patch(f"/api/transactions/{wd['id']}", json={"plan_move": "transfer_out"})
    assert r.status_code == 200 and r.json()["plan_move"] == "transfer_out"
    p26 = plan_of(client, "tfsa", 2026)
    assert p26["withdrawn"] == 0 and p26["by_type"]["transfer_out"] == 500
    assert client.patch(f"/api/transactions/{wd['id']}", json={"plan_move": "bogus"}).status_code == 422


def test_preview_choices_are_kept_when_importing(client):
    register(client)
    acct = client.post("/api/accounts", json={"name": "Savings", "registered_kind": "tfsa"}).json()
    text = "Date,Description,Amount\n2026-05-01,SAMPLE TRANSFER FROM OTHER BANK,3000.00\n2026-05-02,SAMPLE DEPOSIT,100.00\n"
    prev = upload(client, acct["id"], "s.csv", text, step="preview")
    assert [r["plan_move"] for r in prev["rows"]] == ["contribution", "contribution"]
    upload(client, acct["id"], "s.csv", text, options={"plan_moves": {"0": "transfer_in", "1": "nonsense"}})
    p = plan_of(client, "tfsa", 2026)
    assert p["contributed"] == 100 and p["by_type"]["transfer_in"] == 3000


def test_fhsa_import_counts_rrsp_transfer_and_estimates_next_year(client):
    register(client)
    acct = client.post("/api/accounts", json={"name": "FHSA", "registered_kind": "fhsa"}).json()
    client.post("/api/plans", json={"kind": "fhsa", "year": 2025, "room": 8000, "account_id": None})
    client.post(f"/api/plans/{plan_of(client, 'fhsa', 2025)['id']}/entries",
                json={"date": "2025-06-01", "amount": 8000, "note": "at another bank"})
    text = ("Date,Description,Amount\n2026-01-10,RRSP to FHSA transfer,5000.00\n2026-02-01,Contribution,2000.00\n"
            "2026-03-31,Interest,4.00\n")
    done = upload(client, acct["id"], "fhsa.csv", text)
    assert done["registered"]["years"][0]["rrsp_to_fhsa"] == {"n": 1, "amount": 5000.0}
    p = plan_of(client, "fhsa", 2026)
    assert p["contributed"] == 7000 and p["by_type"]["rrsp_to_fhsa"] == 5000 and p["by_type"]["growth"] == 4
    client.patch(f"/api/plans/{p['id']}", json={"kind": "fhsa", "year": 2026, "room": 8000, "account_id": None})
    e = plan_of(client, "fhsa", 2026)["estimate"]
    # 1,000 unused carries; lifetime so far 15,000; opened 2025 (the earliest FHSA year).
    assert e["code"] == "fhsa_next" and e["amount"] == 9000 and e["lifetime"] == 15000 and e["opened"] == 2025


def test_plan_with_no_room_and_legacy_untyped_lines(client):
    register(client)
    r = client.post("/api/plans", json={"kind": "rrsp", "year": 2026})
    assert r.status_code == 200 and r.json()["room"] is None and r.json()["percent"] is None
    assert r.json()["estimate"] is None  # RRSP: no projection
    # An ordinary linked account (not marked registered) keeps today's rule: money in counts.
    acct = client.post("/api/accounts", json={"name": "Old link"}).json()
    client.post("/api/transactions", json={"account_id": acct["id"], "date": "2026-02-01", "amount": 1500,
                                           "description": "deposit"})
    client.patch(f"/api/plans/{r.json()['id']}", json={"kind": "rrsp", "year": 2026, "room": 1000,
                                                       "account_id": acct["id"]})
    p = plan_of(client, "rrsp", 2026)
    assert p["contributed"] == 1500 and p["untyped"] == 1
    assert p["warnings"][0]["code"] == "rrsp_in_buffer"


def test_marking_an_account_types_its_history_and_makes_plans(client):
    register(client)
    acct = client.post("/api/accounts", json={"name": "Savings"}).json()
    for d, amt, desc in (("2025-03-01", 1000, "TRANSFER FROM CHEQUING"), ("2025-12-31", 3.5, "INTEREST"),
                         ("2026-01-15", -200, "TRANSFER TO CHEQUING")):
        client.post("/api/transactions", json={"account_id": acct["id"], "date": d, "amount": amt, "description": desc})
    r = client.patch(f"/api/accounts/{acct['id']}", json={"registered_kind": "tfsa"})
    assert r.json()["typed"] == 3
    assert plan_of(client, "tfsa", 2025)["contributed"] == 1000
    assert plan_of(client, "tfsa", 2025)["by_type"]["growth"] == 3.5
    assert plan_of(client, "tfsa", 2026)["withdrawn"] == 200
    # A line added by hand later gets a type too.
    t = client.post("/api/transactions", json={"account_id": acct["id"], "date": "2026-02-01", "amount": 50,
                                               "description": "Contribution"}).json()
    assert t["plan_move"] == "contribution"
    assert client.patch(f"/api/accounts/{acct['id']}", json={"registered_kind": "rrif"}).status_code == 422


def test_members_cannot_see_or_touch_each_others_registered_data(client):
    register(client)
    acct = client.post("/api/accounts", json={"name": "A TFSA", "registered_kind": "tfsa"}).json()
    upload(client, acct["id"], "ws.csv", WS_STATEMENT_CSV)
    tx = client.get("/api/transactions").json()["items"][0]
    plan = plan_of(client, "tfsa", 2026)
    code = client.post("/api/admin/invites", json={}).json()["code"]
    client.post("/api/auth/logout")
    register(client, "b@home.lan", invite_code=code)

    assert client.get("/api/plans").json() == []
    assert client.patch(f"/api/transactions/{tx['id']}", json={"plan_move": "fee"}).status_code == 404
    assert client.patch(f"/api/accounts/{acct['id']}", json={"registered_kind": "rrsp"}).status_code == 404
    assert client.patch(f"/api/plans/{plan['id']}", json={"kind": "tfsa", "year": 2026, "room": 1}).status_code == 404
    files = {"file": ("ws.csv", io.BytesIO(WS_STATEMENT_CSV.encode()), "text/csv")}
    assert client.post("/api/imports/preview", data={"account_id": str(acct["id"])}, files=files).status_code == 404
    # B's own TFSA in the same year is a separate plan that doesn't see A's lines.
    mine = client.post("/api/accounts", json={"name": "B TFSA", "registered_kind": "tfsa"}).json()
    upload(client, mine["id"], "s.csv", "Date,Description,Amount\n2026-07-01,Contribution,100.00\n")
    assert [p["contributed"] for p in client.get("/api/plans").json()] == [100]

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "a@home.lan", "password": PW})
    assert plan_of(client, "tfsa", 2026)["contributed"] == 6000
    assert client.get("/api/transactions", params={"account_id": acct["id"]}).json()["items"][0]["plan_move"]


def test_data_export_carries_the_new_columns(client):
    register(client)
    acct = client.post("/api/accounts", json={"name": "A TFSA", "registered_kind": "tfsa"}).json()
    upload(client, acct["id"], "ws.csv", WS_STATEMENT_CSV)
    zf = zipfile.ZipFile(io.BytesIO(client.get("/api/account/export").content))
    tables = {n[5:-5]: json.loads(zf.read(n)) for n in zf.namelist() if n.startswith("data/")}
    assert tables["accounts"][0]["registered_kind"] == "tfsa"
    assert {t["plan_move"] for t in tables["transactions"]} == {"contribution", "trade", "growth", "withdrawal"}
    assert tables["registered_plans"][0]["room_set"] is False


def test_startup_migration_adds_the_new_columns_to_an_older_database(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, inspect, text

    from app import db as dbmod
    old = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with old.begin() as conn:
        conn.execute(text("CREATE TABLE registered_plans (id INTEGER PRIMARY KEY, user_id INTEGER, kind VARCHAR(10), "
                          "year INTEGER, room NUMERIC(18, 4), account_id INTEGER, notes TEXT)"))
        conn.execute(text("CREATE TABLE accounts (id INTEGER PRIMARY KEY, user_id INTEGER, name VARCHAR(120))"))
        conn.execute(text("INSERT INTO registered_plans (user_id, kind, year, room, notes) "
                          "VALUES (1, 'tfsa', 2025, 7000, '')"))
    monkeypatch.setattr(dbmod, "engine", old)
    dbmod.add_missing_columns()
    cols = {t: {c["name"] for c in inspect(old).get_columns(t)} for t in ("registered_plans", "accounts")}
    assert "room_set" in cols["registered_plans"] and "registered_kind" in cols["accounts"]
    with old.begin() as conn:
        assert str(conn.execute(text("SELECT room_set FROM registered_plans")).scalar()) in ("1", "True")
    old.dispose()
