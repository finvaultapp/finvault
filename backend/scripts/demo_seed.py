"""Fill an EMPTY FinVault database with a synthetic demo household.

    python -m scripts.demo_seed            (from the backend folder)

Everything here is made up. Sign in as demo@finvault.local / demo-password-123.
"""
import random
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.importers import ParsedTxn, ParseResult  # noqa: E402
from app.models import (Account, Asset, AssetValue, Budget, Category, ExchangeRate, Goal, Recurring, Rule,  # noqa: E402
                        User)
from app.security import hash_password  # noqa: E402
from app.services.ledger import commit_import, seed_categories  # noqa: E402

random.seed(7)
TODAY = date.today()
START = (TODAY.replace(day=1) - timedelta(days=170)).replace(day=1)


def days():
    d = START
    while d <= TODAY:
        yield d
        d += timedelta(days=1)


def main():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    if db.scalar(select(func.count(User.id))):
        print("Database already has users; refusing to add demo data.")
        return
    u = User(email="demo@finvault.local", name="Alex Demo", password_hash=hash_password("demo-password-123"),
             is_admin=True, base_currency="CAD")
    db.add(u)
    db.flush()
    seed_categories(db, u)
    db.flush()
    cat = {c.name: c.id for c in db.scalars(select(Category).where(Category.user_id == u.id))}

    chq = Account(user_id=u.id, name="Joint Chequing", institution="TD Canada Trust", type="checking", currency="CAD",
                  country="CA", opening_balance=Decimal("4200"), import_preset="td")
    visa = Account(user_id=u.id, name="Cash Back Visa", institution="RBC Royal Bank", type="credit_card", currency="CAD",
                   country="CA", opening_balance=Decimal("-640"), import_preset="rbc")
    sav = Account(user_id=u.id, name="Emergency Savings", institution="Tangerine", type="savings", currency="CAD",
                  country="CA", opening_balance=Decimal("9800"), import_preset="tangerine")
    usd = Account(user_id=u.id, name="USD Account", institution="Wealthsimple", type="checking", currency="USD",
                  country="CA", opening_balance=Decimal("1500"), import_preset="wealthsimple")
    db.add_all([chq, visa, sav, usd])
    db.flush()

    rules = [("PAYROLL", "Salary", "Northwind Payroll"), ("LOBLAWS", "Groceries", "Loblaws"), ("METRO", "Groceries", "Metro"),
             ("NO FRILLS", "Groceries", "No Frills"), ("NETFLIX", "Subscriptions", "Netflix"), ("SPOTIFY", "Subscriptions", "Spotify"),
             ("HYDRO", "Utilities", "Toronto Hydro"), ("ROGERS", "Phone & internet", "Rogers"), ("PETRO", "Fuel", "Petro-Canada"),
             ("TTC", "Transportation", "TTC"), ("RENT", "Rent & mortgage", "Rent"), ("SHOPPERS", "Health", "Shoppers Drug Mart"),
             ("PAYMENT - THANK YOU", "Credit card payment", None), ("TRANSFER TO SAVINGS", "Transfer", None),
             ("INTEREST", "Interest", None)]
    for i, (pattern, c, payee) in enumerate(rules):
        db.add(Rule(user_id=u.id, pattern=pattern.lower(), set_category_id=cat[c], set_payee=payee, priority=10 + i))
    db.flush()

    chq_tx, visa_tx, sav_tx, usd_tx = [], [], [], []
    for d in days():
        if d.weekday() == 4 and (d - START).days % 14 < 7:
            chq_tx.append(("NORTHWIND PAYROLL DEP", Decimal("2875.40"), d))
        if d.day == 1:
            chq_tx.append(("E-TRANSFER RENT 1204 MAPLE", Decimal("-2150.00"), d))
            chq_tx.append(("TRANSFER TO SAVINGS", Decimal("-400.00"), d))
            sav_tx.append(("TRANSFER FROM CHEQUING", Decimal("400.00"), d))
        if d.day == 18:
            chq_tx.append(("TORONTO HYDRO ELECTRIC", -Decimal(random.randint(8200, 12900)) / 100, d))
        if d.day == 22:
            chq_tx.append(("RBC VISA PAYMENT - THANK YOU", Decimal("-1350.00"), d))
            visa_tx.append(("PAYMENT - THANK YOU", Decimal("1350.00"), d))
        if d.day == 28:
            sav_tx.append(("INTEREST PAID", Decimal(random.randint(1800, 2600)) / 100, d))
        if d.day == 12:
            visa_tx.append(("ROGERS WIRELESS", Decimal("-95.00"), d))
        if d.day == 5:
            visa_tx.append(("NETFLIX.COM", Decimal("-20.99"), d))
        if d.day == 9:
            visa_tx.append(("SPOTIFY P1A2B3", Decimal("-11.99"), d))
        if d.weekday() == 5:
            store = random.choice(["LOBLAWS #1123", "METRO 0442", "NO FRILLS 3321"])
            visa_tx.append((store, -Decimal(random.randint(9500, 21500)) / 100, d))
        if random.random() < 0.28:
            place = random.choice(["TIM HORTONS #4410", "PIZZA NOVA 118", "SUSHI MOTO", "A&W 2231", "PAI THAI", "STARBUCKS 7712"])
            visa_tx.append((place, -Decimal(random.randint(700, 6800)) / 100, d))
        if d.weekday() == 2 and random.random() < 0.6:
            visa_tx.append(("PETRO-CANADA 88231", -Decimal(random.randint(4800, 7900)) / 100, d))
        if random.random() < 0.07:
            visa_tx.append((random.choice(["AMAZON.CA MKTPLACE", "CANADIAN TIRE #221", "WINNERS 419", "IKEA ETOBICOKE"]),
                            -Decimal(random.randint(1900, 18900)) / 100, d))
        if random.random() < 0.05:
            visa_tx.append(("SHOPPERS DRUG MART #0921", -Decimal(random.randint(900, 5400)) / 100, d))
        if d.day == 15 and d.month % 2 == 0:
            usd_tx.append(("AIRBNB US", -Decimal(random.randint(18000, 32000)) / 100, d))
        if d.day == 3:
            usd_tx.append(("FREELANCE INVOICE US CLIENT", Decimal("650.00"), d))

    for acct, rows in [(chq, chq_tx), (visa, visa_tx), (sav, sav_tx), (usd, usd_tx)]:
        # Leave this month's dining uncategorized so the "needs a category" callout has something to show.
        txns = [ParsedTxn(date=d, amount=a, description=desc) for desc, a, d in rows]
        commit_import(db, u, acct, ParseResult(format="demo", transactions=txns), f"{acct.institution} demo export")

    # Categorize older dining the way a person would, so "remembered merchant" works on new imports.
    from app.models import Transaction
    for t in db.scalars(select(Transaction).where(Transaction.user_id == u.id, Transaction.category_id.is_(None))):
        name = t.description
        if t.date >= TODAY.replace(day=1) and random.random() < 0.6:
            continue
        if any(x in name for x in ["TIM HORTONS", "PIZZA", "SUSHI", "A&W", "PAI THAI", "STARBUCKS"]):
            t.category_id = cat["Dining out"]
        elif any(x in name for x in ["AMAZON", "CANADIAN TIRE", "WINNERS", "IKEA"]):
            t.category_id = cat["Shopping"]
        elif "AIRBNB" in name:
            t.category_id = cat["Travel"]
        elif "FREELANCE" in name:
            t.category_id = cat["Other income"]
        elif "TRANSFER FROM" in name:
            t.category_id = cat["Transfer"]

    for c, amt in [("Groceries", 900), ("Dining out", 350), ("Fuel", 260), ("Subscriptions", 40), ("Shopping", 300), ("Utilities", 140)]:
        db.add(Budget(user_id=u.id, category_id=cat[c], amount=Decimal(amt)))
    db.add(Goal(user_id=u.id, name="Emergency fund", target_amount=Decimal("20000"), currency="CAD", account_id=sav.id,
                target_date=date(TODAY.year + 1, 6, 30)))
    db.add(Goal(user_id=u.id, name="Summer trip to Portugal", target_amount=Decimal("6000"), currency="CAD",
                saved_amount=Decimal("2350"), target_date=date(TODAY.year + 1, 5, 1)))
    db.add(Recurring(user_id=u.id, account_id=visa.id, name="Netflix", amount=Decimal("-20.99"), category_id=cat["Subscriptions"],
                     frequency="monthly", next_date=(TODAY.replace(day=1) + timedelta(days=35)).replace(day=5), anchor_day=5))
    db.add(Recurring(user_id=u.id, account_id=chq.id, name="Rent", amount=Decimal("-2150"), category_id=cat["Rent & mortgage"],
                     frequency="monthly", next_date=(TODAY.replace(day=1) + timedelta(days=35)).replace(day=1), anchor_day=1))
    car = Asset(user_id=u.id, name="2019 Mazda CX-5", kind="vehicle", currency="CAD")
    car.values = [AssetValue(date=START, value=Decimal("24500")), AssetValue(date=TODAY - timedelta(days=20), value=Decimal("22800"))]
    rrsp = Asset(user_id=u.id, name="RRSP", kind="retirement", currency="CAD")
    rrsp.values = [AssetValue(date=START, value=Decimal("31200")), AssetValue(date=TODAY - timedelta(days=60), value=Decimal("34050")),
                   AssetValue(date=TODAY - timedelta(days=5), value=Decimal("35610"))]
    loan = Asset(user_id=u.id, name="Car loan", kind="loan", is_liability=True, currency="CAD")
    loan.values = [AssetValue(date=START, value=Decimal("12400")), AssetValue(date=TODAY - timedelta(days=10), value=Decimal("10150"))]
    db.add_all([car, rrsp, loan])
    db.add(ExchangeRate(base="USD", quote="CAD", date=START, rate=Decimal("1.3650"), source="manual"))
    db.commit()
    print("Demo household created. Sign in as demo@finvault.local / demo-password-123")


if __name__ == "__main__":
    main()
