"""Move a household's history in from another finance app.

Three steps share one plan (built by the wizard from `analyze`):
- `analyze`  what's in the files, with suggested FinVault accounts and categories for each source one;
- `preview`  per account: how many rows are new, which are already here, and the date range;
- `commit`   create what the plan asks for, then insert one import batch per account, so the ordinary
             "Undo import" removes a moved account's history in one step.

Duplicates: every row gets the same hash a statement import would (ledger.plan_import), so moving twice
is safe. Rows that match a transaction already in the account (same amount on the same day, or within
a few days with a matching merchant) are flagged "likely already here" and skipped too, so history that
came in from bank statements isn't doubled. All lookups are dictionary-based: a 20,000-row history is
a linear pass.
"""
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import bindparam, insert, select, update
from sqlalchemy.orm import Session

from ..importers.common import ParsedTxn, normalize_merchant
from ..importers.migrate import CAT_SEP, SOURCE_NAMES, MigrationData, MigTxn, latest_budgets
from ..importers.presets import PRESETS
from ..models import Account, Budget, Category, ImportBatch, Transaction, User
from . import transfers
from .ledger import DEFAULT_CATEGORIES, FRENCH_NAMES, Categorizer, plan_import

LIKELY_WINDOW_DAYS = 3
INSERT_CHUNK = 2000
ACCOUNT_TYPES = {"checking", "savings", "credit_card", "investment", "cash", "loan", "other"}
TRANSFER_NAMES = {"transfer", "transfers", "credit card payment", "credit card payments", "internal transfer",
                  "balance adjustment", "virement", "virements", "paiement de carte de credit"}
_PALETTE = [c for _, _, c in DEFAULT_CATEGORIES]

# Source category names that mean one of FinVault's starting categories.
SYNONYMS = {
    "ready to assign": "Other income", "to be budgeted": "Other income", "income": "Other income",
    "paycheck": "Salary", "paychecks": "Salary", "salary": "Salary", "wages": "Salary", "payroll": "Salary",
    "interest income": "Interest", "interest": "Interest", "dividends & capital gains": "Interest",
    "groceries": "Groceries", "grocery": "Groceries", "food & groceries": "Groceries",
    "restaurants": "Dining out", "restaurants & bars": "Dining out", "dining": "Dining out", "dining out": "Dining out",
    "fast food": "Dining out", "coffee shops": "Dining out", "food & dining": "Dining out", "eating out": "Dining out",
    "rent": "Rent & mortgage", "mortgage": "Rent & mortgage", "mortgage & rent": "Rent & mortgage",
    "rent & mortgage": "Rent & mortgage", "housing": "Rent & mortgage",
    "utilities": "Utilities", "gas & electric": "Utilities", "electricity": "Utilities", "water": "Utilities",
    "hydro": "Utilities", "internet": "Phone & internet", "internet & cable": "Phone & internet",
    "phone": "Phone & internet", "mobile phone": "Phone & internet", "phone & internet": "Phone & internet",
    "public transit": "Transportation", "auto & transport": "Transportation", "transportation": "Transportation",
    "parking": "Transportation", "parking & tolls": "Transportation", "taxi & ride shares": "Transportation",
    "gas": "Fuel", "gas & fuel": "Fuel", "fuel": "Fuel", "auto insurance": "Insurance", "insurance": "Insurance",
    "home insurance": "Insurance", "health": "Health", "medical": "Health", "doctor": "Health", "pharmacy": "Health",
    "dentist": "Health", "health & fitness": "Health", "shopping": "Shopping", "clothing": "Shopping",
    "subscriptions": "Subscriptions", "streaming": "Subscriptions", "entertainment": "Entertainment",
    "entertainment & recreation": "Entertainment", "travel": "Travel", "travel & vacation": "Travel",
    "air travel": "Travel", "hotel": "Travel", "vacation": "Travel", "kids": "Kids & family",
    "childcare": "Kids & family", "child care": "Kids & family", "kids & family": "Kids & family",
    "gifts": "Gifts & donations", "charity": "Gifts & donations", "gifts & donations": "Gifts & donations",
    "charitable donations": "Gifts & donations", "bank fee": "Fees & charges", "fees & charges": "Fees & charges",
    "service fee": "Fees & charges", "atm fee": "Fees & charges", "financial fees": "Fees & charges",
    "financial & legal services": "Fees & charges", "taxes": "Taxes", "federal tax": "Taxes",
    "transfer": "Transfer", "transfers": "Transfer", "credit card payment": "Credit card payment",
    "miscellaneous": "Other", "other": "Other",
}
_FR_TO_EN = {v.lower(): k for k, v in FRENCH_NAMES.items()}

_CA_KEYWORDS = {"rbc": "rbc", "td": "td", "bmo": "bmo", "cibc": "cibc", "scotia": "scotiabank", "scotiabank": "scotiabank",
                "tangerine": "tangerine", "simplii": "simplii", "eq": "eq", "wealthsimple": "wealthsimple", "neo": "neo",
                "triangle": "triangle", "rogers": "rogers", "desjardins": "desjardins", "national": "national_bank",
                "nbc": "national_bank", "vancity": "credit_union", "meridian": "credit_union", "coast": "credit_union",
                "pc": "pc_financial", "amex": "amex_ca"}
_PRESET_NAMES = {p["id"]: p["name"] for p in PRESETS}
_COUNTRY_BY_CURRENCY = {"CAD": "CA", "USD": "US", "GBP": "GB", "BRL": "BR", "MXN": "MX", "AUD": "AU", "JPY": "JP",
                        "CHF": "CH", "INR": "IN"}


class PlanError(ValueError):
    pass


# --- Suggestions ------------------------------------------------------------------------

def _words(name: str) -> list[str]:
    return re.split(r"[^a-z0-9$]+", name.lower())


def guess_type(name: str, balance: Decimal) -> str:
    n = name.lower()
    w = set(_words(name))
    if w & {"visa", "mastercard", "mc", "amex", "card", "credit", "cc"} or "carte de cr" in n:
        return "credit_card"
    if w & {"loan", "mortgage", "loc", "hypotheque", "pret"} or "line of credit" in n:
        return "loan"
    if w & {"rrsp", "tfsa", "fhsa", "resp", "invest", "investment", "investments", "brokerage", "reer", "celi", "rrif"}:
        return "investment"
    if w & {"saving", "savings", "hisa", "epargne", "emergency"} or "high interest" in n:
        return "savings"
    if w & {"cash", "wallet", "petty"}:
        return "cash"
    if balance < 0:
        return "credit_card"
    return "checking"


def guess_currency(name: str, base: str) -> str:
    n = name.upper()
    for code in ("USD", "EUR", "GBP", "CAD", "BRL", "MXN", "AUD", "CHF", "JPY"):
        if re.search(rf"\b{code}\b", n):
            return code
    if "US$" in n or re.search(r"\bU\.?S\.?\b", n):
        return "USD"
    return (base or "CAD").upper()


def guess_bank(name: str) -> str | None:
    for w in _words(name):
        if w in _CA_KEYWORDS:
            return _CA_KEYWORDS[w]
    return None


def suggest_account(name: str, txns: list[MigTxn], base: str, existing: dict[str, Account]) -> dict:
    match = existing.get(name.strip().lower())
    if match:
        return {"action": "map", "account_id": match.id}
    balance = sum((t.amount for t in txns), Decimal(0))
    currency = guess_currency(name, base)
    bank = guess_bank(name)
    country = "CA" if bank or currency == "CAD" else _COUNTRY_BY_CURRENCY.get(currency, "")
    return {"action": "create", "name": name[:120] or "Imported account", "type": guess_type(name, balance),
            "currency": currency, "country": country, "institution": _PRESET_NAMES.get(bank, "") if bank else "",
            "import_preset": bank}


def _is_transfer_name(name: str | None) -> bool:
    return bool(name) and name.strip().lower() in TRANSFER_NAMES


def guess_kind(group: str | None, name: str, amounts: list[Decimal]) -> str:
    if _is_transfer_name(name) or _is_transfer_name(group):
        return "transfer"
    if (group or "").lower() in {"inflow", "income"} or (name or "").lower() in {"ready to assign", "to be budgeted"}:
        return "income"
    positive = sum(1 for a in amounts if a > 0)
    return "income" if amounts and positive / len(amounts) > 0.6 else "expense"


def suggest_category(group: str | None, name: str, cats: list[Category], by_id: dict[int, Category]) -> dict | None:
    """An existing FinVault category for a source one, or None to create it."""
    lname = name.strip().lower()
    lgroup = (group or "").strip().lower()
    same = [c for c in cats if c.name.strip().lower() == lname]
    if lgroup:
        under = [c for c in same if c.parent_id and by_id.get(c.parent_id) and by_id[c.parent_id].name.strip().lower() == lgroup]
        if under:
            return {"action": "map", "category_id": under[0].id}
    if same:
        return {"action": "map", "category_id": same[0].id}
    target = SYNONYMS.get(lname) or SYNONYMS.get(f"{lgroup}: {lname}")
    if target:
        names = {target.lower(), FRENCH_NAMES.get(target, target).lower()}
        hit = next((c for c in cats if c.name.strip().lower() in names), None)
        if hit:
            return {"action": "map", "category_id": hit.id}
    en = _FR_TO_EN.get(lname)
    if en:
        hit = next((c for c in cats if c.name.strip().lower() == en.lower()), None)
        if hit:
            return {"action": "map", "category_id": hit.id}
    return None


def _source_accounts(data: MigrationData) -> dict[str, list[MigTxn]]:
    out: dict[str, list[MigTxn]] = defaultdict(list)
    for t in data.transactions:
        out[t.account or "Imported account"].append(t)
    return out


def _source_categories(data: MigrationData) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for t in data.transactions:
        key = t.category_key
        if not key or t.starting_balance:
            continue
        c = out.get(key)
        if c is None:
            c = out[key] = {"key": key, "group": t.group, "name": t.category, "count": 0, "amounts": []}
        c["count"] += 1
        c["amounts"].append(t.amount)
    for b in data.budgets:
        if b.category_key not in out:
            out[b.category_key] = {"key": b.category_key, "group": b.group, "name": b.category, "count": 0, "amounts": []}
    return out


def analyze(db: Session, user: User, data: MigrationData) -> dict:
    accounts = list(db.scalars(select(Account).where(Account.user_id == user.id, Account.is_archived.is_(False))))
    by_name = {a.name.strip().lower(): a for a in accounts}
    cats = list(db.scalars(select(Category).where(Category.user_id == user.id)))
    cats_by_id = {c.id: c for c in cats}
    acc_out = []
    for name, txns in sorted(_source_accounts(data).items()):
        dates = [t.date for t in txns]
        starting = next((t for t in txns if t.starting_balance), None)
        acc_out.append({
            "source": name, "count": sum(1 for t in txns if not t.starting_balance),
            "date_range": [min(dates).isoformat(), max(dates).isoformat()],
            "uncleared": sum(1 for t in txns if t.cleared is False),
            "transfers": sum(1 for t in txns if t.transfer_to or _is_transfer_name(t.category)),
            "starting_balance": float(starting.amount) if starting else None,
            "suggestion": suggest_account(name, txns, user.base_currency, by_name),
        })
    cat_out = []
    for key, c in sorted(_source_categories(data).items(), key=lambda kv: ((kv[1]["group"] or "~").lower(), kv[1]["name"].lower())):
        kind = guess_kind(c["group"], c["name"], c["amounts"])
        suggestion = suggest_category(c["group"], c["name"], cats, cats_by_id) or {
            "action": "create", "name": c["name"][:80], "kind": kind, "parent": (c["group"] or None)}
        cat_out.append({"key": key, "group": c["group"], "name": c["name"], "count": c["count"], "kind": kind,
                        "total": float(sum(c["amounts"], Decimal(0))), "suggestion": suggestion})
    month, lines = latest_budgets(data.budgets)
    return {
        "source": data.source, "source_name": SOURCE_NAMES.get(data.source, data.source), "files": data.files,
        "total": len(data.transactions), "accounts": acc_out, "categories": cat_out,
        "budgets": {"month": month.isoformat() if month else None, "lines": len(lines),
                    "total": float(sum((b.amount for b in lines), Decimal(0)))},
        "has_cleared": any(t.cleared is not None for t in data.transactions),
        "has_labels": any(t.labels for t in data.transactions),
        "generic": [g.__dict__ for g in data.generic],
        "date_format": data.date_format, "date_format_ambiguous": data.date_format_ambiguous,
        "warnings": data.warnings[:20],
    }


# --- Duplicates ----------------------------------------------------------------------

def _cents(amount) -> int:
    return int((Decimal(amount) * 100).to_integral_value())


def _tokens(text: str) -> set[str]:
    return {w for w in normalize_merchant(text or "").split() if len(w) >= 3}


def _hash_text(t: MigTxn) -> str:
    # The bank's own description when the app kept it, so a statement import of the same line hashes the same.
    return t.original or t.payee


def plan_account(db: Session, account: Account | None, txns: list[MigTxn]) -> list[dict]:
    """Hash and flag duplicates for one FinVault account. `account` None means it will be created."""
    if account is None:
        return [{"txn": t, "hash": None, "duplicate": None} for t in txns]
    parsed = [ParsedTxn(date=t.date, amount=t.amount, description=_hash_text(t)) for t in txns]
    planned = plan_import(db, account, parsed)
    hashes = {p["hash"] for p in planned}
    pool: dict[tuple[int, date], list] = defaultdict(list)
    for tid, d, amount, desc, h in db.execute(
            select(Transaction.id, Transaction.date, Transaction.amount, Transaction.description, Transaction.import_hash)
            .where(Transaction.account_id == account.id)):
        if h and h in hashes:
            continue  # the row an exact duplicate points at
        pool[(_cents(amount), d)].append([desc, False])
    out = []
    for t, p in zip(txns, planned):
        dup = "exact" if p["duplicate"] else None
        if not dup and pool:
            dup = _likely(pool, t)
        out.append({"txn": t, "hash": p["hash"], "duplicate": dup})
    return out


def _likely(pool, t: MigTxn) -> str | None:
    cents = _cents(t.amount)
    same_day = pool.get((cents, t.date))
    if same_day:
        for entry in same_day:
            if not entry[1]:
                entry[1] = True
                return "likely"
    mine = _tokens(t.payee) | _tokens(t.original)
    if not mine:
        return None
    for delta in range(1, LIKELY_WINDOW_DAYS + 1):
        for d in (t.date - timedelta(days=delta), t.date + timedelta(days=delta)):
            for entry in pool.get((cents, d), ()):
                if not entry[1] and mine & _tokens(entry[0]):
                    entry[1] = True
                    return "likely"
    return None


# --- The plan ------------------------------------------------------------------------

@dataclass
class _Target:
    source: str
    account: Account | None
    create: dict | None
    txns: list[MigTxn]
    starting: MigTxn | None
    uncleared_skipped: int


def _targets(db: Session, user: User, data: MigrationData, plan: dict) -> list[_Target]:
    choices = plan.get("accounts") or {}
    include_uncleared = plan.get("include_uncleared", True)
    out = []
    for source, txns in sorted(_source_accounts(data).items()):
        choice = choices.get(source) or {"action": "skip"}
        action = choice.get("action")
        if action == "skip":
            continue
        starting = next((t for t in txns if t.starting_balance), None)
        rows = [t for t in txns if not t.starting_balance]
        kept = rows if include_uncleared else [t for t in rows if t.cleared is not False]
        if action == "map":
            account = db.get(Account, int(choice.get("account_id") or 0))
            if account is None or account.user_id != user.id:
                raise PlanError("Choose a FinVault account for each account you're bringing in.")
            out.append(_Target(source, account, None, kept, starting, len(rows) - len(kept)))
        elif action == "create":
            kind = choice.get("type") if choice.get("type") in ACCOUNT_TYPES else "checking"
            currency = str(choice.get("currency") or user.base_currency or "CAD").upper()[:3]
            if not re.fullmatch(r"[A-Z]{3}", currency):
                raise PlanError("Use a three-letter currency code, like CAD or USD.")
            name = str(choice.get("name") or source).strip()[:120] or "Imported account"
            out.append(_Target(source, None, {
                "name": name, "type": kind, "currency": currency,
                "country": str(choice.get("country") or "").upper()[:2],
                "institution": str(choice.get("institution") or "")[:120],
                "import_preset": choice.get("import_preset") if choice.get("import_preset") in _PRESET_NAMES else None,
            }, kept, starting, len(rows) - len(kept)))
        else:
            raise PlanError("Choose a FinVault account for each account you're bringing in.")
    if not out:
        raise PlanError("Choose at least one account to bring in.")
    return out


def preview(db: Session, user: User, data: MigrationData, plan: dict) -> dict:
    accounts = []
    for tg in _targets(db, user, data, plan):
        planned = plan_account(db, tg.account, tg.txns)
        exact = sum(1 for p in planned if p["duplicate"] == "exact")
        likely = sum(1 for p in planned if p["duplicate"] == "likely")
        dates = [t.date for t in tg.txns]
        accounts.append({
            "source": tg.source, "account_id": tg.account.id if tg.account else None,
            "name": tg.account.name if tg.account else tg.create["name"], "create": tg.account is None,
            "currency": tg.account.currency if tg.account else tg.create["currency"],
            "total": len(planned), "new": len(planned) - exact - likely, "exact_duplicates": exact,
            "likely_duplicates": likely, "uncleared_skipped": tg.uncleared_skipped,
            "date_range": [min(dates).isoformat(), max(dates).isoformat()] if dates else None,
            "duplicates": [{"date": p["txn"].date.isoformat(), "amount": float(p["txn"].amount),
                            "description": p["txn"].payee, "kind": p["duplicate"]}
                           for p in planned if p["duplicate"]][:25],
        })
    return {"accounts": accounts, "new": sum(a["new"] for a in accounts),
            "duplicates": sum(a["exact_duplicates"] + a["likely_duplicates"] for a in accounts)}


def _resolve_categories(db: Session, user: User, data: MigrationData, plan: dict) -> tuple[dict[str, int], int]:
    """Create the categories the plan asks for. Returns (source key -> category id, created count)."""
    choices = plan.get("categories") or {}
    source = _source_categories(data)
    existing = list(db.scalars(select(Category).where(Category.user_id == user.id)))
    owned_ids = {c.id for c in existing}
    parents = {c.name.strip().lower(): c for c in existing if c.parent_id is None}
    children = {(c.parent_id, c.name.strip().lower()): c for c in existing if c.parent_id is not None}
    out: dict[str, int] = {}
    created = 0
    color_i = len(existing)

    def color() -> str:
        nonlocal color_i
        color_i += 1
        return _PALETTE[color_i % len(_PALETTE)]

    for key, info in source.items():
        choice = choices.get(key)
        if not choice:
            choice = {"action": "create", "name": info["name"], "parent": info["group"],
                      "kind": guess_kind(info["group"], info["name"], info["amounts"])}
        action = choice.get("action")
        if action == "skip":
            continue
        if action == "map":
            cid = int(choice.get("category_id") or 0)
            if cid not in owned_ids:
                raise PlanError("Choose a FinVault category for each category you're bringing in, or leave it uncategorized.")
            out[key] = cid
            continue
        kind = choice.get("kind") if choice.get("kind") in {"expense", "income", "transfer"} else "expense"
        name = str(choice.get("name") or info["name"]).strip()[:80] or info["name"][:80]
        parent_name = str(choice.get("parent") or "").strip()[:80]
        parent = None
        if parent_name:
            parent = parents.get(parent_name.lower())
            if parent is None:
                parent = Category(user_id=user.id, name=parent_name, kind=kind, color=color())
                db.add(parent)
                db.flush()
                parents[parent_name.lower()] = parent
                owned_ids.add(parent.id)
                created += 1
        pid = parent.id if parent else None
        hit = children.get((pid, name.lower())) if pid else parents.get(name.lower())
        if hit is None:
            hit = Category(user_id=user.id, name=name, kind=kind, color=parent.color if parent else color(), parent_id=pid)
            db.add(hit)
            db.flush()
            owned_ids.add(hit.id)
            created += 1
            if pid:
                children[(pid, name.lower())] = hit
            else:
                parents[name.lower()] = hit
        out[key] = hit.id
    return out, created


def _create_budgets(db: Session, user: User, data: MigrationData, cat_ids: dict[str, int]) -> tuple[int, int]:
    _, lines = latest_budgets(data.budgets)
    expense = set(db.scalars(select(Category.id).where(Category.user_id == user.id, Category.kind == "expense")))
    sums: Counter = Counter()
    for b in lines:
        cid = cat_ids.get(b.category_key)
        if cid in expense and b.amount > 0:  # FinVault budgets are for spending categories
            sums[cid] += b.amount
    have = set(db.scalars(select(Budget.category_id).where(Budget.user_id == user.id)))
    created = kept = 0
    for cid, amount in sums.items():
        if cid in have:
            kept += 1
            continue
        db.add(Budget(user_id=user.id, category_id=cid, amount=amount))
        created += 1
    return created, kept


def _label_note(notes: str, labels: list[str]) -> str:
    line = "labels: " + ", ".join(labels)
    return f"{notes}\n{line}" if notes else line


def attach_labels(db: Session, user: User, labelled: list[tuple[int, str, list[str]]]) -> int:
    """Keep the source app's labels / tags on the imported transactions.

    `labelled` is [(transaction id, its notes, labels)]. Today labels go into the notes as a
    "labels: a, b" line. When FinVault has a Tag model, replace this body with "get or create each tag,
    link it to the transaction"; nothing else in the move needs to change.
    """
    if not labelled:
        return 0
    table = Transaction.__table__
    stmt = update(table).where(table.c.id == bindparam("tid")).values(notes=bindparam("new_notes"))
    params = [{"tid": tid, "new_notes": _label_note(notes, labels)} for tid, notes, labels in labelled]
    for i in range(0, len(params), INSERT_CHUNK):
        db.connection().execute(stmt, params[i:i + INSERT_CHUNK])
    return len(labelled)


def _pair_transfers(db: Session, user: User, legs: list[tuple[int, int, MigTxn]], source_to_account: dict[str, int]) -> int:
    """Match the two legs of each transfer between moved accounts through transfers.match."""
    incoming: dict[int, list] = defaultdict(list)
    for tid, acc, t in legs:
        if t.amount > 0:
            incoming[_cents(t.amount)].append([tid, acc, t, False])
    pairs: list[tuple[int, int]] = []
    for tid, acc, t in sorted(legs, key=lambda x: x[2].date):
        if t.amount >= 0:
            continue
        want = source_to_account.get(t.transfer_to) if t.transfer_to else None
        best = None
        for entry in incoming.get(-_cents(t.amount), ()):
            if entry[3] or entry[1] == acc or (want and entry[1] != want):
                continue
            if entry[2].transfer_to and source_to_account.get(entry[2].transfer_to) not in (None, acc):
                continue
            gap = abs((entry[2].date - t.date).days)
            if gap <= transfers.WINDOW_DAYS and (best is None or gap < best[0]):
                best = (gap, entry)
        if best:
            best[1][3] = True
            pairs.append((tid, best[1][0]))
    if not pairs:
        return 0
    ids = [i for p in pairs for i in p]
    rows: dict[int, Transaction] = {}
    for i in range(0, len(ids), 900):
        rows.update({r.id: r for r in db.scalars(select(Transaction).where(Transaction.id.in_(ids[i:i + 900]))).unique()})
    for out_id, in_id in pairs:
        transfers.match(db, user, rows[out_id], rows[in_id])
    return len(pairs)


def commit(db: Session, user: User, data: MigrationData, plan: dict) -> dict:
    targets = _targets(db, user, data, plan)
    try:
        cat_ids, categories_created = _resolve_categories(db, user, data, plan)
        cat_kinds = {c.id: c.kind for c in db.scalars(select(Category).where(Category.user_id == user.id))}
        general_transfer, _ = transfers._transfer_categories(db, user.id)
        categorizer = Categorizer(db, user.id)
        label = f"{SOURCE_NAMES.get(data.source, data.source)} · {', '.join(data.files)}"[:255]
        summary, legs, labelled, accounts_created = [], [], [], 0
        source_to_account: dict[str, int] = {}
        for tg in targets:
            account = tg.account
            if account is None:
                account = Account(user_id=user.id, **tg.create)
                if tg.starting:
                    account.opening_balance, account.opening_date = tg.starting.amount, tg.starting.date
                db.add(account)
                db.flush()
                accounts_created += 1
            source_to_account[tg.source] = account.id
            tg.account = account
        for tg in targets:
            account = tg.account
            planned = plan_account(db, account, tg.txns)
            batch = ImportBatch(user_id=user.id, account_id=account.id, filename=label, format=data.source)
            db.add(batch)
            db.flush()
            rows, meta = [], []
            for p in planned:
                if p["duplicate"]:
                    continue
                t: MigTxn = p["txn"]
                cid = cat_ids.get(t.category_key) if t.category_key else None
                payee = t.payee
                is_transfer = bool(t.transfer_to and t.transfer_to in source_to_account) or (
                    cid is not None and cat_kinds.get(cid) == "transfer")
                if t.transfer_to and cid is None:
                    cid = general_transfer
                if cid is None:
                    rule_cat, new_payee, _ = categorizer.apply(t.payee, t.payee, t.amount, account.id)
                    cid, payee = rule_cat, new_payee or t.payee
                rows.append({"user_id": user.id, "account_id": account.id, "date": t.date, "amount": t.amount,
                             "description": t.payee[:500], "payee": payee[:200], "notes": t.notes,
                             "category_id": cid, "import_hash": p["hash"], "import_batch_id": batch.id})
                meta.append((p["hash"], t, is_transfer))
            for i in range(0, len(rows), INSERT_CHUNK):
                db.execute(insert(Transaction), rows[i:i + INSERT_CHUNK])
            if any(m[2] or m[1].labels for m in meta):
                ids = dict(db.execute(select(Transaction.import_hash, Transaction.id)
                                      .where(Transaction.import_batch_id == batch.id)).all())
                for h, t, is_transfer in meta:
                    if is_transfer:
                        legs.append((ids[h], account.id, t))
                    if t.labels:
                        labelled.append((ids[h], t.notes, t.labels))
            batch.imported, batch.skipped = len(rows), len(planned) - len(rows)
            dates = [t.date for t in tg.txns]
            summary.append({"source": tg.source, "account_id": account.id, "name": account.name,
                            "created": tg.create is not None, "batch_id": batch.id, "imported": len(rows),
                            "skipped": len(planned) - len(rows), "uncleared_skipped": tg.uncleared_skipped,
                            "date_range": [min(dates).isoformat(), max(dates).isoformat()] if dates else None})
        db.flush()
        matched = _pair_transfers(db, user, legs, source_to_account)
        labels = attach_labels(db, user, labelled)
        budgets_created = budgets_kept = 0
        if plan.get("create_budgets"):
            budgets_created, budgets_kept = _create_budgets(db, user, data, cat_ids)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"accounts": summary, "imported": sum(a["imported"] for a in summary),
            "skipped": sum(a["skipped"] for a in summary), "accounts_created": accounts_created,
            "categories_created": categories_created, "transfers_matched": matched, "labelled": labels,
            "budgets_created": budgets_created, "budgets_kept": budgets_kept}
