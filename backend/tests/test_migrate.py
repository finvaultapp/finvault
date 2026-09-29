"""Move from another app: parsers, account and category mapping, transfers, dedupe and a long history.

Every sample below is made up: invented payees, round amounts, and "Maple Leaf" / "Sample" account names.
"""
import io
import json
import time
import zipfile
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.db import SessionLocal
from app.importers.migrate import CAT_SEP, detect_kind, parse_migration
from app.models import Budget

from .test_api import register

YNAB_REGISTER = """﻿"Account","Flag","Date","Payee","Category Group/Category","Category Group","Category","Memo","Outflow","Inflow","Cleared"
"Sample Chequing","","09/01/2026","Starting Balance","Inflow: Ready to Assign","Inflow","Ready to Assign","","$0.00","$1,000.00","Reconciled"
"Sample Chequing","","09/02/2026","Fictional Grocer","Everyday: Groceries","Everyday","Groceries","weekly shop","$82.50","$0.00","Cleared"
"Sample Chequing","Red","09/03/2026","Made-up Cafe","Everyday: Coffee","Everyday","Coffee","","$4.25","$0.00","Uncleared"
"Sample Chequing","","09/05/2026","Transfer : Maple Leaf Visa","","","","card payment","$200.00","$0.00","Cleared"
"Maple Leaf Visa","","09/05/2026","Transfer : Sample Chequing","","","","card payment","$0.00","$200.00","Cleared"
"Maple Leaf Visa","","09/06/2026","Pretend Hardware","Home: Repairs","Home","Repairs","","$45.00","$0.00","Cleared"
"Sample Chequing","","09/15/2026","Example Employer","Inflow: Ready to Assign","Inflow","Ready to Assign","","$0.00","$2,500.00","Cleared"
"""

YNAB_BUDGET = """"Month","Category Group/Category","Category Group","Category","Assigned","Activity","Available"
"Aug 2026","Everyday: Groceries","Everyday","Groceries","$400.00","-$380.00","$20.00"
"Sep 2026","Everyday: Groceries","Everyday","Groceries","$450.00","-$82.50","$367.50"
"Sep 2026","Everyday: Coffee","Everyday","Coffee","$30.00","-$4.25","$25.75"
"Sep 2026","Home: Repairs","Home","Repairs","$0.00","-$45.00","-$45.00"
"""

YNAB4_REGISTER = """Account,Flag,Check Number,Date,Payee,Category,Master Category,Sub Category,Memo,Outflow,Inflow,Cleared,Running Balance
Old Savings,,,2019-03-01,Invented Bakery,Food: Treats,Food,Treats,,$6.00,$0.00,C,-$6.00
Old Savings,,,2019-03-02,Sample Payroll,Income: Available this month,Income,Available this month,,$0.00,$100.00,U,$94.00
"""

MINT = """"Date","Description","Original Description","Amount","Transaction Type","Category","Account Name","Labels","Notes"
"8/03/2021","Imaginary Pizza","IMAGINARY PIZZA #0042 TORONTO ON","23.40","debit","Restaurants","Sample Chequing","Date night, Shared",""
"8/04/2021","Example Payroll","EXAMPLE PAYROLL DEP","1500.00","credit","Paycheck","Sample Chequing","",""
"8/06/2021","Credit Card Payment","PAYMENT - THANK YOU","300.00","debit","Credit Card Payment","Sample Chequing","",""
"8/07/2021","Credit Card Payment","PAYMENT RECEIVED","300.00","credit","Credit Card Payment","Maple Leaf Mastercard","",""
"8/09/2021","Fake Books","FAKE BOOKS ONLINE","12.00","debit","Uncategorized","Maple Leaf Mastercard","Gift","for Sam"
"""

MONARCH = """Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags
2024-05-01,Invented Gym,Fitness,Sample TFSA Savings,INVENTED GYM MONTHLY,,-40.00,Health
2024-05-02,Example Payroll,Paychecks,Sample Chequing,EXAMPLE PAYROLL,,2000.00,
2024-05-03,Transfer,Transfer,Sample Chequing,TFR TO SAVINGS,,-250.00,
2024-05-03,Transfer,Transfer,Sample TFSA Savings,TFR FROM CHQ,,250.00,
"""

ACTUAL = """Account,Date,Payee,Notes,Category,Amount,Cleared
Sample Chequing,2025-01-10,Pretend Market,,Food,-55.10,Cleared
Sample Chequing,2025-01-11,Transfer: Sample Savings,,,-100.00,Cleared
Sample Savings,2025-01-11,Transfer: Sample Chequing,,,100.00,Cleared
Sample Chequing,2025-01-12,Made-up Utility,,Bills,-80.00,Not cleared
"""

GENERIC = """When,What,Value,Kind
2023-02-01,Invented Store,-19.99,Shopping
2023-02-03,Sample Refund,5.00,Shopping
"""


def files(*items):
    return [("files", (name, body.encode("utf-8") if isinstance(body, str) else body, "text/csv")) for name, body in items]


def zipped(**members) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in members.items():
            zf.writestr(name, text)
    return buf.getvalue()


def post(client, step, upload, **options):
    return client.post(f"/api/migrate/{step}", files=upload, data={"options": json.dumps(options)})


def default_plan(analysis, **extra):
    return {"accounts": {a["source"]: a["suggestion"] for a in analysis["accounts"]},
            "categories": {c["key"]: c["suggestion"] for c in analysis["categories"]}, **extra}


# --- Parsers ------------------------------------------------------------------------

def test_ynab_register_and_budget_from_zip():
    raw = zipped(**{"Sample Budget as of 2026-09-20 - Register.csv": YNAB_REGISTER,
                    "Sample Budget as of 2026-09-20 - Budget.csv": YNAB_BUDGET})
    data = parse_migration([("Sample Budget.zip", raw)])
    assert data.source == "ynab"
    assert len(data.transactions) == 7 and len(data.budgets) == 4
    grocer = next(t for t in data.transactions if t.payee == "Fictional Grocer")
    assert grocer.amount == Decimal("-82.50") and grocer.group == "Everyday" and grocer.category == "Groceries"
    assert grocer.date == date(2026, 9, 2) and grocer.cleared is True and grocer.notes == "weekly shop"
    cafe = next(t for t in data.transactions if t.payee == "Made-up Cafe")
    assert cafe.cleared is False and cafe.labels == ["flag red"]
    transfer = next(t for t in data.transactions if t.account == "Sample Chequing" and t.transfer_to)
    assert transfer.transfer_to == "Maple Leaf Visa" and transfer.category is None and transfer.amount == Decimal("-200")
    start = next(t for t in data.transactions if t.starting_balance)
    assert start.amount == Decimal("1000")
    salary = next(t for t in data.transactions if t.payee == "Example Employer")
    assert salary.category_key == f"Inflow{CAT_SEP}Ready to Assign"


def test_ynab4_master_and_sub_categories():
    data = parse_migration([("Register.csv", YNAB4_REGISTER.encode())])
    assert data.source == "ynab"
    treat, pay = data.transactions
    assert (treat.group, treat.category, treat.amount, treat.cleared) == ("Food", "Treats", Decimal("-6.00"), True)
    assert pay.cleared is False and pay.date == date(2019, 3, 2)


def test_mint_debit_credit_and_labels():
    data = parse_migration([("transactions.csv", MINT.encode())])
    assert data.source == "mint"
    pizza = data.transactions[0]
    assert pizza.amount == Decimal("-23.40") and pizza.labels == ["Date night", "Shared"]
    assert pizza.original.startswith("IMAGINARY PIZZA") and pizza.category == "Restaurants"
    assert data.transactions[1].amount == Decimal("1500.00")
    assert data.transactions[4].category is None  # "Uncategorized" is no category


def test_monarch_signed_amounts_and_tags():
    data = parse_migration([("monarch.csv", MONARCH.encode())])
    assert data.source == "monarch"
    gym = data.transactions[0]
    assert gym.amount == Decimal("-40.00") and gym.labels == ["Health"] and gym.account == "Sample TFSA Savings"


def test_actual_budget_csv_and_database_refused():
    data = parse_migration([("actual.csv", ACTUAL.encode())])
    assert data.source == "actual"
    assert data.transactions[1].transfer_to == "Sample Savings"
    assert data.transactions[3].cleared is False
    raw = zipped(**{"db.sqlite": "SQLite format 3", "metadata.json": "{}"})
    try:
        parse_migration([("My-Budget.zip", raw)])
        raise AssertionError("expected a refusal")
    except ValueError as exc:
        assert "Export" in str(exc)


def test_generic_file_uses_the_column_mapper():
    data = parse_migration([("Sample Chequing.csv", GENERIC.encode())],
                           generic={"Sample Chequing.csv": {"mapping": {"date": 0, "description": 1, "amount": 2, "category": 3}}})
    assert data.source == "generic"
    assert [t.amount for t in data.transactions] == [Decimal("-19.99"), Decimal("5.00")]
    assert data.transactions[0].account == "Sample Chequing" and data.transactions[0].category == "Shopping"
    assert len(data.generic[0].columns) == 4 and data.generic[0].count == 2
    # Headers the matcher knows need no mapping at all.
    auto = parse_migration([("Other.csv", b"Date,Description,Amount,Category\n2023-03-01,Sample Shop,-5.00,Fun\n")])
    assert auto.source == "generic" and auto.transactions[0].category == "Fun"
    assert auto.generic[0].columns == ["Date", "Description", "Amount", "Category"]


def test_account_suggestions():
    from app.services.migrate import suggest_account
    usd = suggest_account("RBC USD Savings", [], "CAD", {})
    assert (usd["type"], usd["currency"], usd["country"], usd["institution"], usd["import_preset"]) == (
        "savings", "USD", "CA", "RBC Royal Bank", "rbc")  # a Canadian bank's USD account is still Canadian
    assert suggest_account("Brokerage USD", [], "CAD", {})["country"] == "US"
    assert suggest_account("Sample TFSA", [], "CAD", {})["type"] == "investment"
    assert suggest_account("Household Mortgage", [], "CAD", {})["type"] == "loan"
    assert suggest_account("Wallet", [], "CAD", {})["type"] == "cash"


def test_detect_kind():
    assert detect_kind(["account", "flag", "date", "payee", "outflow", "inflow"]) == "ynab"
    assert detect_kind(["when", "what", "value"]) == "generic"


# --- The wizard over the API -----------------------------------------------------------

def test_ynab_move_accounts_categories_transfers_budgets_and_undo(client):
    register(client)
    client.post("/api/accounts", json={"name": "Sample Chequing", "currency": "CAD"})
    upload = files(("Register.csv", YNAB_REGISTER), ("Budget.csv", YNAB_BUDGET))
    a = post(client, "analyze", upload).json()
    assert a["source"] == "ynab" and a["budgets"]["month"] == "2026-09-01" and a["budgets"]["lines"] == 2
    accts = {x["source"]: x for x in a["accounts"]}
    assert accts["Sample Chequing"]["suggestion"]["action"] == "map"  # same name as an existing account
    visa = accts["Maple Leaf Visa"]["suggestion"]
    assert visa == {"action": "create", "name": "Maple Leaf Visa", "type": "credit_card", "currency": "CAD",
                    "country": "CA", "institution": "", "import_preset": None}
    cats = {x["key"]: x for x in a["categories"]}
    assert cats[f"Everyday{CAT_SEP}Groceries"]["suggestion"]["action"] == "map"  # FinVault's own Groceries
    assert cats[f"Everyday{CAT_SEP}Coffee"]["suggestion"] == {"action": "create", "name": "Coffee", "kind": "expense",
                                                              "parent": "Everyday"}
    assert cats[f"Inflow{CAT_SEP}Ready to Assign"]["kind"] == "income"

    plan = default_plan(a, create_budgets=True, include_uncleared=False)
    pv = post(client, "preview", upload, plan=plan).json()
    chq = next(x for x in pv["accounts"] if x["source"] == "Sample Chequing")
    assert chq["total"] == 3 and chq["uncleared_skipped"] == 1 and chq["new"] == 3  # starting balance isn't a row

    done = post(client, "commit", upload, plan=plan).json()
    assert done["imported"] == 5 and done["accounts_created"] == 1 and done["transfers_matched"] == 1
    assert done["budgets_created"] == 2  # Groceries (FinVault's own) and Coffee; Repairs had nothing assigned
    categories = client.get("/api/categories").json()
    everyday = next(c for c in categories if c["name"] == "Everyday")
    coffee = next(c for c in categories if c["name"] == "Coffee")
    assert coffee["parent_id"] == everyday["id"] and everyday["parent_id"] is None
    txs = client.get("/api/transactions").json()
    items = txs["items"] if isinstance(txs, dict) else txs
    legs = [t for t in items if abs(t["amount"]) == 200]
    assert len(legs) == 2 and all(t["transfer_id"] for t in legs)
    visa_acct = next(x for x in client.get("/api/accounts").json()["items"] if x["name"] == "Maple Leaf Visa")
    assert visa_acct["type"] == "credit_card" and visa_acct["country"] == "CA"

    # Re-running the same move adds nothing.
    again = post(client, "preview", upload, plan=default_plan(post(client, "analyze", upload).json(),
                                                                 include_uncleared=False)).json()
    assert again["new"] == 0
    # Undo is the ordinary per-batch undo.
    for acc in done["accounts"]:
        assert client.delete(f"/api/imports/batches/{acc['batch_id']}").status_code == 200
    items = client.get("/api/transactions").json()
    assert (items["items"] if isinstance(items, dict) else items) == []


def test_budgets_from_latest_month(client):
    register(client)
    upload = files(("Register.csv", YNAB_REGISTER), ("Budget.csv", YNAB_BUDGET))
    a = post(client, "analyze", upload).json()
    done = post(client, "commit", upload, plan=default_plan(a, create_budgets=True)).json()
    assert done["budgets_created"] == 2
    with SessionLocal() as db:
        assert sorted(b.amount for b in db.scalars(select(Budget))) == [Decimal("30"), Decimal("450")]
    again = post(client, "commit", upload, plan=default_plan(post(client, "analyze", upload).json(), create_budgets=True))
    assert again.json()["budgets_kept"] == 2 and again.json()["imported"] == 0


def test_mint_labels_go_to_notes_and_card_payment_pairs(client):
    register(client)
    upload = files(("transactions.csv", MINT))
    a = post(client, "analyze", upload).json()
    assert a["source"] == "mint" and a["has_labels"]
    cats = {x["name"]: x for x in a["categories"]}
    assert cats["Credit Card Payment"]["suggestion"]["action"] == "map"
    assert cats["Paycheck"]["suggestion"]["action"] == "map"  # -> Salary
    card = next(x for x in a["accounts"] if x["source"] == "Maple Leaf Mastercard")
    assert card["suggestion"]["type"] == "credit_card"
    done = post(client, "commit", upload, plan=default_plan(a)).json()
    assert done["imported"] == 5 and done["transfers_matched"] == 1 and done["labelled"] == 2
    txs = client.get("/api/transactions").json()
    items = txs["items"] if isinstance(txs, dict) else txs
    pizza = next(t for t in items if t["description"] == "Imaginary Pizza")
    assert pizza["notes"] == "labels: Date night, Shared"
    book = next(t for t in items if t["description"] == "Fake Books")
    assert book["notes"] == "for Sam\nlabels: Gift"


def test_monarch_and_actual_transfers_pair(client):
    register(client)
    for name, body, expect in (("monarch.csv", MONARCH, 4), ("actual.csv", ACTUAL, 4)):
        upload = files((name, body))
        a = post(client, "analyze", upload).json()
        done = post(client, "commit", upload, plan=default_plan(a)).json()
        assert done["imported"] == expect and done["transfers_matched"] == 1, (name, done)
    accounts = {x["name"]: x for x in client.get("/api/accounts").json()["items"]}
    assert accounts["Sample TFSA Savings"]["type"] == "investment"
    assert accounts["Sample Savings"]["type"] == "savings"


def test_skipped_accounts_and_categories(client):
    register(client)
    upload = files(("Register.csv", YNAB_REGISTER))
    a = post(client, "analyze", upload).json()
    plan = default_plan(a)
    plan["accounts"]["Maple Leaf Visa"] = {"action": "skip"}
    plan["categories"][f"Everyday{CAT_SEP}Coffee"] = {"action": "skip"}
    done = post(client, "commit", upload, plan=plan).json()
    assert [x["source"] for x in done["accounts"]] == ["Sample Chequing"] and done["transfers_matched"] == 0
    names = {c["name"] for c in client.get("/api/categories").json()}
    assert "Coffee" not in names and "Everyday" not in names  # no empty parent for a skipped child
    bad = post(client, "commit", upload, plan={"accounts": {"Sample Chequing": {"action": "map", "account_id": 999}}})
    assert bad.status_code == 422


def test_statement_history_is_not_doubled(client):
    """A bank statement imported first, then the app history covering the same days."""
    register(client)
    acct = client.post("/api/accounts", json={"name": "Everyday", "currency": "CAD"}).json()
    statement = "Date,Description,Amount\n2021-08-03,IMAGINARY PIZZA #0042 TORONTO ON,-23.40\n2021-08-05,EXAMPLE PAYROLL DEP,1500.00\n"
    r = client.post("/api/imports/commit", data={"account_id": acct["id"]},
                    files={"file": ("stmt.csv", statement.encode(), "text/csv")})
    assert r.json()["imported"] == 2
    upload = files(("transactions.csv", MINT))
    a = post(client, "analyze", upload).json()
    plan = default_plan(a)
    plan["accounts"]["Sample Chequing"] = {"action": "map", "account_id": acct["id"]}
    pv = post(client, "preview", upload, plan=plan).json()
    chq = next(x for x in pv["accounts"] if x["source"] == "Sample Chequing")
    # Pizza: same bank text and day -> exact. Payroll: same amount a day apart, same merchant -> likely.
    assert chq["exact_duplicates"] == 1 and chq["likely_duplicates"] == 1 and chq["new"] == 1
    done = post(client, "commit", upload, plan=plan).json()
    chq = next(x for x in done["accounts"] if x["source"] == "Sample Chequing")
    assert chq["imported"] == 1 and chq["skipped"] == 2


def test_bad_uploads(client):
    register(client)
    r = post(client, "analyze", files(("empty.csv", "")))
    assert r.status_code == 200 and r.json()["total"] == 0
    r = client.post("/api/migrate/analyze", files=files(("x.csv", GENERIC)), data={"options": "{nope"})
    assert r.status_code == 422


# --- A long history -----------------------------------------------------------------------

def test_twenty_thousand_rows_in_a_few_seconds(client):
    register(client)
    lines = ['"Account","Flag","Date","Payee","Category Group/Category","Category Group","Category","Memo","Outflow","Inflow","Cleared"']
    start = date(2014, 1, 1)
    payees = ["Fictional Grocer", "Made-up Cafe", "Pretend Transit", "Sample Pharmacy", "Invented Diner"]
    groups = [("Everyday", "Groceries"), ("Everyday", "Coffee"), ("Travel", "Transit"), ("Health", "Pharmacy"),
              ("Everyday", "Dining")]
    n = 0
    day = 0
    while n < 20000:
        d = (start + timedelta(days=day)).strftime("%m/%d/%Y")
        for i in range(5):
            g, c = groups[i]
            lines.append(f'"Sample Chequing","","{d}","{payees[i]}","{g}: {c}","{g}","{c}","","${5 + (n % 97)}.{n % 100:02d}","$0.00","Cleared"')
            n += 1
        if day % 30 == 0:
            lines.append(f'"Sample Chequing","","{d}","Transfer : Sample Savings","","","","","$100.00","$0.00","Cleared"')
            lines.append(f'"Sample Savings","","{d}","Transfer : Sample Chequing","","","","","$0.00","$100.00","Cleared"')
            n += 2
        day += 1
    upload = files(("Register.csv", "\n".join(lines)))
    t0 = time.perf_counter()
    a = post(client, "analyze", upload).json()
    plan = default_plan(a)
    done = post(client, "commit", upload, plan=plan).json()
    first = time.perf_counter() - t0
    assert done["imported"] >= 20000 and done["transfers_matched"] > 100
    t1 = time.perf_counter()
    pv = post(client, "preview", upload, plan=default_plan(post(client, "analyze", upload).json())).json()
    second = time.perf_counter() - t1
    assert pv["new"] == 0 and pv["duplicates"] == done["imported"]
    assert first < 15 and second < 10, (first, second)
    print(f"20k move: analyze+commit {first:.2f}s, re-run analyze+preview {second:.2f}s")
