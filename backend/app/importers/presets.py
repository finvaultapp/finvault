"""Bank export presets.

For Canadian institutions FinVault never connects to the bank. You download a
statement file from online banking yourself and import it. OFX/QFX (the
"Quicken" / "Microsoft Money" / "QuickBooks" download) is an open standard
with stable transaction IDs, so prefer it whenever your bank offers it. CSV
works too; the presets below describe the usual column layouts, and the
import preview lets you fix the mapping if a bank changes its format.

`csv.signature`  normalized header names that must all be present to auto-detect
`csv.map`        role -> normalized header name (or column index for headerless files)
`csv.invert`     True when the file shows purchases as positive numbers
"""

GENERIC_STEPS = [
    "Sign in to online banking on the bank's own website or app.",
    "Open the account, then look for Download, Export, or Download transactions (often near the activity list or under Statements).",
    "Pick the date range. Overlapping ranges are fine; duplicates are skipped.",
    "Choose Quicken (QFX), Money (OFX) or QuickBooks (QBO) if offered. Otherwise choose CSV or Spreadsheet.",
    "Upload the file here and check the preview before importing.",
]

PRESETS: list[dict] = [
    {
        "id": "rbc", "name": "RBC Royal Bank", "country": "CA", "kinds": ["bank", "credit_card"],
        "formats": ["QFX/OFX", "CSV"], "recommended": "ofx",
        "notes": "RBC's CSV puts CAD and USD amounts in separate columns; both are handled.",
        "csv": {
            "signature": ["account type", "transaction date", "description 1", "cad"],
            "map": {"date": "transaction date", "description": "description 1", "description2": "description 2",
                    "amount": "cad", "amount_alt": "usd", "id": "cheque number"},
            "amount_alt_currency": "USD",
        },
    },
    {
        "id": "td", "name": "TD Canada Trust", "country": "CA", "kinds": ["bank", "credit_card"],
        "formats": ["QFX/OFX", "QBO", "CSV"], "recommended": "ofx",
        "notes": "TD's CSV has no header row: date, description, withdrawal, deposit, balance.",
        "csv": {"headerless": True, "map": {"date": 0, "description": 1, "debit": 2, "credit": 3, "balance": 4},
                "date_format": "%m/%d/%Y"},
    },
    {
        "id": "cibc", "name": "CIBC", "country": "CA", "kinds": ["bank", "credit_card"],
        "formats": ["QFX/OFX", "QBO", "CSV"], "recommended": "ofx",
        "notes": "CIBC's CSV has no header row: date (YYYY-MM-DD), description, debit, credit, and card number for credit cards.",
        "csv": {"headerless": True, "map": {"date": 0, "description": 1, "debit": 2, "credit": 3},
                "date_format": "%Y-%m-%d"},
    },
    {
        "id": "bmo", "name": "BMO Bank of Montreal", "country": "CA", "kinds": ["bank"],
        "formats": ["QFX/OFX", "CSV"], "recommended": "ofx",
        "notes": "BMO's bank CSV starts with a few lines of text before the header; they are skipped.",
        "csv": {"signature": ["transaction type", "date posted", "transaction amount", "description"],
                "map": {"date": "date posted", "description": "description", "amount": "transaction amount",
                        "type": "transaction type"},
                "date_format": "%Y%m%d"},
    },
    {
        "id": "bmo_mc", "name": "BMO Mastercard", "country": "CA", "kinds": ["credit_card"],
        "formats": ["QFX/OFX", "CSV"], "recommended": "ofx",
        "notes": "The card CSV lists purchases as positive numbers, so amounts are flipped.",
        "csv": {"signature": ["item", "card", "transaction date", "posting date", "transaction amount"],
                "map": {"date": "transaction date", "description": "description", "amount": "transaction amount"},
                "date_format": "%Y%m%d", "invert": True},
    },
    {
        "id": "scotiabank", "name": "Scotiabank", "country": "CA", "kinds": ["bank", "credit_card"],
        "formats": ["QFX/OFX", "CSV"], "recommended": "ofx",
        "notes": "Scotiabank has used more than one CSV layout. If amounts are all positive, the Type column decides the sign.",
        "csv": {"signature": ["date", "description", "type of transaction", "amount"],
                "map": {"date": "date", "description": "description", "description2": "sub description",
                        "amount": "amount", "type": "type of transaction", "balance": "balance"}},
    },
    {
        "id": "tangerine", "name": "Tangerine", "country": "CA", "kinds": ["bank", "credit_card"],
        "formats": ["QFX/OFX", "CSV"], "recommended": "ofx",
        "notes": "Tangerine's CSV: Date, Transaction, Name, Memo, Amount.",
        "csv": {"signature": ["date", "transaction", "name", "memo", "amount"],
                "map": {"date": "date", "description": "name", "description2": "memo", "amount": "amount",
                        "type": "transaction"},
                "date_format": "%m/%d/%Y"},
    },
    {
        "id": "simplii", "name": "Simplii Financial", "country": "CA", "kinds": ["bank"],
        "formats": ["QFX/OFX", "CSV"], "recommended": "ofx",
        "csv": {"signature": ["date", "transaction details", "funds out", "funds in"],
                "map": {"date": "date", "description": "transaction details", "debit": "funds out", "credit": "funds in"}},
    },
    {
        "id": "eq", "name": "EQ Bank", "country": "CA", "kinds": ["bank"],
        "formats": ["CSV"], "recommended": "csv",
        "notes": "EQ Bank offers CSV exports of account activity.",
        "csv": None,
    },
    {
        "id": "wealthsimple", "name": "Wealthsimple", "country": "CA", "kinds": ["bank", "credit_card", "investment"],
        "formats": ["CSV"], "recommended": "csv",
        "notes": "Wealthsimple provides CSV activity/statement exports. The transaction column is the type; description holds the merchant.",
        "csv": {"signature": ["date", "transaction", "description", "amount", "balance"],
                "map": {"date": "date", "description": "description", "amount": "amount", "type": "transaction",
                        "balance": "balance", "currency": "currency"}},
    },
    {
        "id": "neo", "name": "Neo Financial", "country": "CA", "kinds": ["credit_card", "bank"],
        "formats": ["CSV"], "recommended": "csv",
        "notes": "Neo exports CSV from the web app. Columns are matched automatically; check the sign in the preview.",
        "csv": None,
    },
    {
        "id": "triangle", "name": "Triangle / Canadian Tire Bank", "country": "CA", "kinds": ["credit_card"],
        "formats": ["CSV"], "recommended": "csv",
        "notes": "Download transactions from the Triangle Mastercard site. Card exports usually list purchases as positive; the preview suggests flipping them.",
        "csv": None,
    },
    {
        "id": "rogers", "name": "Rogers Bank", "country": "CA", "kinds": ["credit_card"],
        "formats": ["CSV"], "recommended": "csv",
        "notes": "Rogers card CSV lists purchases as positive and payments as negative, so amounts are flipped. The merchant category is kept as a hint.",
        "csv": {"signature": ["date", "posted date", "merchant name", "amount"],
                "map": {"date": "date", "description": "merchant name", "amount": "amount",
                        "category": "merchant category description", "id": "reference number",
                        "type": "activity type"},
                "invert": True},
    },
    {
        "id": "pc_financial", "name": "PC Financial (PC Optimum Mastercard)", "country": "CA", "kinds": ["credit_card"],
        "formats": ["CSV"], "recommended": "csv",
        "notes": "Export from the PC Financial website. Check the sign in the preview; flip it if purchases show as income.",
        "csv": {"signature": ["description", "type", "card holder name", "date", "amount"],
                "map": {"date": "date", "description": "description", "amount": "amount", "type": "type"}},
    },
    {
        "id": "desjardins", "name": "Desjardins", "country": "CA", "kinds": ["bank", "credit_card"],
        "formats": ["QFX/OFX", "CSV"], "recommended": "ofx",
        "notes": "Desjardins' CSV has many unlabeled columns. Use the OFX/QFX (Quicken/Money) download if you can.",
        "csv": None,
    },
    {
        "id": "national_bank", "name": "National Bank (NBC)", "country": "CA", "kinds": ["bank", "credit_card"],
        "formats": ["QFX/OFX", "CSV"], "recommended": "ofx",
        "notes": "National Bank CSVs may use semicolons and French headers (Débit/Crédit); both are recognised.",
        "csv": None,
    },
    {
        "id": "credit_union", "name": "Credit union (Vancity, Meridian, Coast Capital, and others)", "country": "CA",
        "kinds": ["bank", "credit_card"], "formats": ["QFX/OFX", "CSV"], "recommended": "ofx",
        "notes": "Most credit union banking platforms offer Quicken/Money downloads. Prefer those.",
        "csv": None,
    },
    {
        "id": "amex_ca", "name": "American Express Canada", "country": "CA", "kinds": ["credit_card"],
        "formats": ["QFX/OFX", "CSV"], "recommended": "ofx",
        "notes": "Amex CSVs list charges as positive numbers.",
        "csv": {"signature": ["date", "description", "amount"],
                "map": {"date": "date", "description": "description", "amount": "amount"},
                "invert": True, "weak": True},
    },
    {
        "id": "generic", "name": "Other bank / generic file", "country": None, "kinds": ["bank", "credit_card"],
        "formats": ["QFX/OFX", "QIF", "CSV"], "recommended": "ofx",
        "notes": "Columns are matched by name (English and French). You can change any mapping in the preview.",
        "csv": None,
    },
]

PRESETS_BY_ID = {p["id"]: p for p in PRESETS}


def public_presets() -> list[dict]:
    return [
        {k: v for k, v in p.items() if k != "csv"} | {"has_csv_layout": bool(p.get("csv")), "steps": GENERIC_STEPS}
        for p in PRESETS
    ]
