"""Core bookkeeping: default categories, balances, categorization rules and imports."""
import hashlib
import re
from collections import Counter
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..importers import ParsedTxn, ParseResult, normalize_merchant
from ..models import Account, Category, ImportBatch, Rule, Transaction, User

DEFAULT_CATEGORIES = [
    ("Salary", "income", "#3f8f5f"), ("Other income", "income", "#5fa37a"), ("Interest", "income", "#7bb68f"),
    ("Groceries", "expense", "#c77d3a"), ("Dining out", "expense", "#d2553f"), ("Rent & mortgage", "expense", "#8a5a44"),
    ("Utilities", "expense", "#6a7f9a"), ("Phone & internet", "expense", "#5a7aa6"), ("Transportation", "expense", "#4f8a96"),
    ("Fuel", "expense", "#3f7580"), ("Insurance", "expense", "#7a6a9a"), ("Health", "expense", "#b0577a"),
    ("Shopping", "expense", "#6E8B3D"), ("Subscriptions", "expense", "#8d6fb0"), ("Entertainment", "expense", "#c26a8a"),
    ("Travel", "expense", "#3f8fa8"), ("Kids & family", "expense", "#b08a3f"), ("Gifts & donations", "expense", "#9a8a5a"),
    ("Fees & charges", "expense", "#8a4a4a"), ("Taxes", "expense", "#6a6a6a"), ("Other", "expense", "#7c8a96"),
    ("Transfer", "transfer", "#8a96a0"), ("Credit card payment", "transfer", "#96a0aa"),
]


FRENCH_NAMES = {
    "Salary": "Salaire", "Other income": "Autres revenus", "Interest": "Intérêts", "Groceries": "Épicerie",
    "Dining out": "Restaurants", "Rent & mortgage": "Loyer et hypothèque", "Utilities": "Services publics",
    "Phone & internet": "Téléphone et Internet", "Transportation": "Transport", "Fuel": "Essence",
    "Insurance": "Assurances", "Health": "Santé", "Shopping": "Magasinage", "Subscriptions": "Abonnements",
    "Entertainment": "Loisirs", "Travel": "Voyages", "Kids & family": "Enfants et famille",
    "Gifts & donations": "Cadeaux et dons", "Fees & charges": "Frais bancaires", "Taxes": "Impôts", "Other": "Autre",
    "Transfer": "Virement", "Credit card payment": "Paiement de carte de crédit", "Reimbursement": "Remboursement",
}
# Suggested tax tags for the default categories (members can change them on the Tax time page).
DEFAULT_TAX_TAGS = {"Health": "medical", "Gifts & donations": "donations"}


def seed_categories(db: Session, user: User) -> None:
    french = (user.locale or "en") == "fr"
    for name, kind, color in DEFAULT_CATEGORIES:
        db.add(Category(user_id=user.id, name=FRENCH_NAMES.get(name, name) if french else name, kind=kind, color=color,
                        tax_tag=DEFAULT_TAX_TAGS.get(name)))


def account_balances(db: Session, user_id: int, on: date | None = None) -> dict[int, Decimal]:
    q = select(Transaction.account_id, func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.user_id == user_id)
    if on:
        q = q.where(Transaction.date <= on)
    sums = {aid: Decimal(str(total)) for aid, total in db.execute(q.group_by(Transaction.account_id))}
    out = {}
    for acct in db.scalars(select(Account).where(Account.user_id == user_id)):
        opening = Decimal(acct.opening_balance or 0)
        if on and acct.opening_date and acct.opening_date > on:
            opening = Decimal(0)
        out[acct.id] = opening + sums.get(acct.id, Decimal(0))
    return out


# --- Rules --------------------------------------------------------------------

def rule_matches(rule: Rule, description: str, payee: str, amount: Decimal, account_id: int | None) -> bool:
    if not rule.is_active:
        return False
    if rule.account_id and rule.account_id != account_id:
        return False
    if rule.amount_min is not None and amount < Decimal(rule.amount_min):
        return False
    if rule.amount_max is not None and amount > Decimal(rule.amount_max):
        return False
    text = (payee if rule.match_field == "payee" else description) or ""
    pattern = rule.pattern or ""
    if rule.match_type == "regex":
        try:
            return re.search(pattern, text, re.I) is not None
        except re.error:
            return False
    t, p = text.lower(), pattern.lower()
    if rule.match_type == "equals":
        return t.strip() == p.strip()
    if rule.match_type == "starts_with":
        return t.startswith(p)
    return p in t


class Categorizer:
    """Rules first (by priority), then 'same merchant as last time' from history."""

    def __init__(self, db: Session, user_id: int):
        self.rules = list(db.scalars(select(Rule).where(Rule.user_id == user_id, Rule.is_active.is_(True))
                                     .order_by(Rule.priority, Rule.id)))
        self.history: dict[str, int] = {}
        rows = db.execute(select(Transaction.description, Transaction.category_id)
                          .where(Transaction.user_id == user_id, Transaction.category_id.is_not(None))
                          .order_by(Transaction.date)).all()
        votes: dict[str, Counter] = {}
        for desc, cat in rows:
            key = normalize_merchant(desc)
            if key:
                votes.setdefault(key, Counter())[cat] += 1
        self.votes = votes
        self.history = {k: c.most_common(1)[0][0] for k, c in votes.items()}

    def suggest(self, description: str, amount: Decimal, kinds: dict[int, str], limit: int = 3) -> list[int]:
        """Likely categories for an uncategorized line: same merchant, then similar merchants, then usual ones."""
        want = "income" if amount > 0 else "expense"
        key = normalize_merchant(description)
        first = key.split(" ")[0] if key else ""
        score: Counter = Counter()
        for k, c in self.votes.items():
            weight = 10 if k == key else 3 if first and k.split(" ")[0] == first else 0
            if weight:
                for cat, n in c.items():
                    score[cat] += weight * n
        for c in self.votes.values():
            for cat, n in c.items():
                score[cat] += n * 0.01
        out = [cat for cat, _ in score.most_common() if kinds.get(cat) == want]
        return out[:limit]

    def apply(self, description: str, payee: str, amount: Decimal, account_id: int | None):
        """Return (category_id, new_payee, source)."""
        for r in self.rules:
            if rule_matches(r, description, payee, amount, account_id):
                return r.set_category_id, r.set_payee, f"rule:{r.id}"
        key = normalize_merchant(description)
        if key and key in self.history:
            return self.history[key], None, "history"
        return None, None, None


# --- Imports ------------------------------------------------------------------

def tx_hash(account_id: int, t: ParsedTxn, occurrence: int) -> str:
    key = f"{account_id}|{t.date.isoformat()}|{Decimal(t.amount):.2f}|{normalize_merchant(t.description)}|{occurrence}"
    return hashlib.sha256(key.encode()).hexdigest()


def plan_import(db: Session, account: Account, parsed: list[ParsedTxn]) -> list[dict]:
    """Work out hashes and duplicates without writing anything."""
    existing_hashes = set(db.scalars(select(Transaction.import_hash).where(
        Transaction.account_id == account.id, Transaction.import_hash.is_not(None))))
    existing_ids = set(db.scalars(select(Transaction.external_id).where(
        Transaction.account_id == account.id, Transaction.external_id.is_not(None))))
    seen: Counter = Counter()
    planned = []
    for t in parsed:
        base = (t.date, f"{Decimal(t.amount):.2f}", normalize_merchant(t.description))
        occurrence = seen[base]
        seen[base] += 1
        h = tx_hash(account.id, t, occurrence)
        dup = h in existing_hashes or (t.external_id is not None and t.external_id in existing_ids)
        planned.append({"txn": t, "hash": h, "duplicate": dup})
    return planned


def commit_import(db: Session, user: User, account: Account, result: ParseResult, filename: str) -> ImportBatch:
    planned = plan_import(db, account, result.transactions)
    batch = ImportBatch(user_id=user.id, account_id=account.id, filename=filename[:255],
                        format=result.format, preset=result.preset)
    db.add(batch)
    db.flush()
    cat = Categorizer(db, user.id)
    imported = skipped = 0
    for p in planned:
        if p["duplicate"]:
            skipped += 1
            continue
        t: ParsedTxn = p["txn"]
        category_id, new_payee, _ = cat.apply(t.description, t.payee, t.amount, account.id)
        db.add(Transaction(
            user_id=user.id, account_id=account.id, date=t.date, amount=t.amount,
            description=t.description[:500], payee=(new_payee or t.payee or "")[:200],
            category_id=category_id, import_hash=p["hash"], external_id=t.external_id, import_batch_id=batch.id,
        ))
        imported += 1
    batch.imported, batch.skipped = imported, skipped
    if result.preset and not account.import_preset:
        account.import_preset = result.preset
    db.commit()
    return batch


def apply_rules_to_existing(db: Session, user: User, only_uncategorized: bool = True) -> int:
    cat = Categorizer(db, user.id)
    cat.history = {}  # rules only: re-running history on itself adds nothing
    q = select(Transaction).where(Transaction.user_id == user.id)
    if only_uncategorized:
        q = q.where(Transaction.category_id.is_(None))
    changed = 0
    for tx in db.scalars(q):
        category_id, new_payee, _ = cat.apply(tx.description, tx.payee, Decimal(tx.amount), tx.account_id)
        if category_id and category_id != tx.category_id:
            tx.category_id = category_id
            changed += 1
        if new_payee and new_payee != tx.payee:
            tx.payee = new_payee
    db.commit()
    return changed
