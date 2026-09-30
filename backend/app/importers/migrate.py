"""Parsers for a one-time move from another finance app (YNAB, Actual Budget, Mint, Monarch Money, other CSV).

Unlike a bank statement, an app export covers many accounts at once, carries the app's own categories
(sometimes grouped), and marks transfers between accounts. Everything here is pure parsing: the files
become `MigTxn` rows and `MigBudget` lines; services/migrate.py turns them into FinVault data.

Formats, and how sure we are of them:
- YNAB (current web app): Register.csv + Budget.csv, usually zipped. Columns Account, Flag, Date, Payee,
  Category Group/Category, Category Group, Category, Memo, Outflow, Inflow, Cleared. Well known.
- YNAB 4 (desktop): Register with Master Category / Sub Category and C/U/R cleared flags. Well known.
- Mint: transactions.csv with Date, Description, Original Description, Amount, Transaction Type,
  Category, Account Name, Labels, Notes. Amounts are positive; Transaction Type says debit/credit. Well known.
- Monarch Money: Date, Merchant, Category, Account, Original Statement, Notes, Amount, Tags. Signed amounts.
  Fairly well known; column order has changed between versions, so columns are matched by name.
- Actual Budget: the transaction list's CSV export (Account, Date, Payee, Notes, Category, Amount, Cleared).
  Best guess; a full Actual export (a zip holding db.sqlite) is refused with a pointer to the CSV export.
- Anything else: the statement importer's column matcher (importers/csvfile.py), one account per file.
"""
import csv
import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from .common import DATE_FORMATS, _AMBIGUOUS, _clean_date, decode_bytes, normalize_header, parse_amount
from .csvfile import parse_csv

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # all files of one move together
MAX_UNZIPPED_BYTES = 120 * 1024 * 1024
SOURCES = ("ynab", "actual", "mint", "monarch", "generic")
SOURCE_NAMES = {"ynab": "YNAB", "actual": "Actual Budget", "mint": "Mint", "monarch": "Monarch Money",
                "generic": "Other app"}
CAT_SEP = "\u001f"  # between group and name in a category key

# YNAB's "money to assign" pseudo-categories: income that hasn't been given a job yet.
YNAB_INFLOW = {"inflow: ready to assign", "inflow: to be budgeted", "ready to assign", "to be budgeted",
               "to be assigned"}
TRANSFER_RE = re.compile(r"^\s*transfer\s*:\s*(.+?)\s*$", re.I)
STARTING_BALANCE = {"starting balance", "solde initial", "opening balance"}


@dataclass
class MigTxn:
    account: str
    date: date
    amount: Decimal
    payee: str
    notes: str = ""
    group: str | None = None
    category: str | None = None
    transfer_to: str | None = None  # source account name on the other side, when the app says so
    cleared: bool | None = None  # None: the app doesn't say
    labels: list[str] = field(default_factory=list)
    starting_balance: bool = False
    original: str = ""  # the bank's own description, when the app kept it

    @property
    def category_key(self) -> str | None:
        if not self.category:
            return None
        return f"{self.group}{CAT_SEP}{self.category}" if self.group else self.category


@dataclass
class MigBudget:
    month: date
    group: str | None
    category: str
    amount: Decimal

    @property
    def category_key(self) -> str:
        return f"{self.group}{CAT_SEP}{self.category}" if self.group else self.category


@dataclass
class GenericFile:
    filename: str
    columns: list[str]
    mapping: dict
    sample_rows: list[list[str]]
    date_format: str | None
    date_format_ambiguous: bool
    inverted: bool
    warnings: list[str]
    count: int


@dataclass
class MigrationData:
    source: str
    files: list[str] = field(default_factory=list)
    transactions: list[MigTxn] = field(default_factory=list)
    budgets: list[MigBudget] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    generic: list[GenericFile] = field(default_factory=list)
    date_format: str | None = None
    date_format_ambiguous: bool = False
    skipped_rows: int = 0


# --- Files in, CSV texts out -------------------------------------------------------

def expand_files(files: list[tuple[str, bytes]]) -> list[tuple[str, str]]:
    """Unzip archives and decode text. Returns [(name, text)] for every CSV-like file."""
    total = sum(len(raw) for _, raw in files)
    if total > MAX_UPLOAD_BYTES:
        raise ValueError("These files are larger than 50 MB together.")
    out: list[tuple[str, str]] = []
    for name, raw in files:
        if raw[:4] == b"PK\x03\x04" or (name or "").lower().endswith(".zip"):
            out.extend(_unzip(raw))
        elif (name or "").lower().endswith((".sqlite", ".db")) or raw[:16] == b"SQLite format 3\x00":
            raise ValueError("That is an app database, not an export. In Actual Budget, open All accounts and use Export to save the transactions as CSV.")
        else:
            out.append((name or "upload.csv", decode_bytes(raw)))
    if not out:
        raise ValueError("No CSV files were found. Upload the CSV export, or the zip that holds it.")
    return out


def _unzip(raw: bytes) -> list[tuple[str, str]]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ValueError("That zip file could not be opened.") from exc
    out, size = [], 0
    with zf:
        members = [m for m in zf.infolist() if not m.is_dir() and "__MACOSX" not in m.filename]
        names = [m.filename.rsplit("/", 1)[-1].lower() for m in members]
        if any(n in {"db.sqlite", "metadata.json"} for n in names) and not any(n.endswith(".csv") for n in names):
            raise ValueError("That is an app database, not an export. In Actual Budget, open All accounts and use Export to save the transactions as CSV.")
        for m, short in zip(members, names):
            if not short.endswith((".csv", ".tsv", ".txt")):
                continue
            size += m.file_size
            if size > MAX_UNZIPPED_BYTES:
                raise ValueError("The zip holds more than 120 MB of files.")
            try:
                data = zf.read(m)
            except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError) as exc:
                # A damaged, encrypted or wrongly sized member (sizes are enforced: a member that inflates past
                # its stated size fails its CRC check here instead of filling memory).
                raise ValueError("That zip file could not be opened.") from exc
            out.append((m.filename.rsplit("/", 1)[-1], decode_bytes(data)))
    return out


def _rows(text: str) -> tuple[list[str], list[list[str]]]:
    sample = text[:4000]
    delim = max([",", ";", "\t"], key=lambda d: sample.splitlines()[0].count(d) if sample.splitlines() else 0)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        return [], []
    return [normalize_header(h) for h in rows[0]], rows[1:]


def detect_kind(headers: list[str]) -> str:
    """ynab | ynab_budget | actual | mint | monarch | generic, from a file's header row."""
    h = set(headers)
    if {"outflow", "inflow"} <= h and "account" in h:
        return "ynab"
    if "month" in h and ({"budgeted", "assigned"} & h) and ({"category", "sub category"} & h):
        return "ynab_budget"
    if {"transaction type", "account name"} <= h and ("original description" in h or "labels" in h):
        return "mint"
    if {"merchant", "account", "amount"} <= h and ("original statement" in h or "tags" in h):
        return "monarch"
    if {"account", "payee", "amount", "date"} <= h and ("notes" in h or "cleared" in h):
        return "actual"
    return "generic"


# --- Dates: detect once per file on the distinct values (a long history repeats dates) ----------

def detect_dates(values: set[str], preferred: str | None = None) -> tuple[str | None, bool]:
    vals = [_clean_date(v) for v in values if v and v.strip()]
    if not vals:
        return None, False
    fits = list(DATE_FORMATS)
    for v in vals:
        fits = [f for f in fits if _strp(v, f)]
        if not fits:
            return None, False
    choice = preferred if preferred in fits else fits[0]
    ambiguous = not preferred and any(a in fits and b in fits for a, b in _AMBIGUOUS)
    return choice, ambiguous


def _strp(v: str, fmt: str) -> date | None:
    try:
        return datetime.strptime(v, fmt).date()
    except ValueError:
        return None


class _DateReader:
    def __init__(self, values: set[str], preferred: str | None):
        self.format, self.ambiguous = detect_dates(values, preferred)
        self.cache: dict[str, date | None] = {}

    def __call__(self, value: str) -> date | None:
        if value not in self.cache:
            self.cache[value] = _strp(_clean_date(value), self.format) if self.format else None
        return self.cache[value]


# --- Per-source parsers ----------------------------------------------------------------

def _cell(row: list[str], idx: dict[str, int], *names: str) -> str:
    for n in names:
        i = idx.get(n)
        if i is not None and i < len(row):
            v = row[i].strip()
            if v:
                return v
    return ""


def _split_labels(value: str) -> list[str]:
    return [x.strip() for x in re.split(r"[,;|]", value or "") if x.strip()]


def _parse_register(kind: str, headers: list[str], rows: list[list[str]], data: MigrationData,
                    date_format: str | None) -> None:
    idx = {h: i for i, h in enumerate(headers)}
    read_date = _DateReader({r[idx["date"]] for r in rows if idx["date"] < len(r)}, date_format)
    if read_date.format is None:
        data.warnings.append("Could not recognise the date format.")
        data.skipped_rows += len(rows)
        return
    data.date_format = data.date_format or read_date.format
    data.date_format_ambiguous = data.date_format_ambiguous or read_date.ambiguous
    parse = {"ynab": _ynab_row, "mint": _mint_row, "monarch": _monarch_row, "actual": _actual_row}[kind]
    append = data.transactions.append
    for r in rows:
        when = read_date(_cell(r, idx, "date"))
        txn = parse(r, idx) if when else None
        if txn is None:
            data.skipped_rows += 1
            continue
        txn.date = when
        append(txn)


def _ynab_row(r, idx) -> MigTxn | None:
    out_, in_ = parse_amount(_cell(r, idx, "outflow")), parse_amount(_cell(r, idx, "inflow"))
    if out_ is None and in_ is None:
        return None
    amount = (in_ or Decimal(0)) - (out_ or Decimal(0))
    payee = _cell(r, idx, "payee")
    group = _cell(r, idx, "category group", "master category") or None
    name = _cell(r, idx, "category", "sub category") or None
    combined = _cell(r, idx, "category group category")
    if group and name and name.lower().startswith(group.lower() + ":"):
        name = name.split(":", 1)[1].strip() or None  # YNAB 4 writes "Master: Sub" in Category
    if not name and combined:
        group, _, name = combined.partition(":")
        group, name = (group.strip() or None), (name.strip() or group.strip())
    if name and (f"{group}: {name}".lower() in YNAB_INFLOW or name.lower() in YNAB_INFLOW):
        group, name = "Inflow", "Ready to Assign"
    transfer = TRANSFER_RE.match(payee)
    cleared_raw = _cell(r, idx, "cleared").lower()
    cleared = None if not cleared_raw else cleared_raw in {"cleared", "reconciled", "c", "r"}
    flag = _cell(r, idx, "flag")
    return MigTxn(
        account=_cell(r, idx, "account"), date=date.min, amount=amount, payee=payee or "(no payee)",
        notes=_cell(r, idx, "memo"), group=None if transfer else group, category=None if transfer else name,
        transfer_to=transfer.group(1) if transfer else None, cleared=cleared,
        labels=[f"flag {flag.lower()}"] if flag else [], starting_balance=payee.lower() in STARTING_BALANCE,
    )


def _mint_row(r, idx) -> MigTxn | None:
    amount = parse_amount(_cell(r, idx, "amount"))
    if amount is None:
        return None
    kind = _cell(r, idx, "transaction type").lower()
    amount = -abs(amount) if kind == "debit" else abs(amount) if kind == "credit" else amount
    category = _cell(r, idx, "category") or None
    if category and category.lower() == "uncategorized":
        category = None
    return MigTxn(
        account=_cell(r, idx, "account name"), date=date.min, amount=amount,
        payee=_cell(r, idx, "description", "original description") or "(no description)",
        notes=_cell(r, idx, "notes"), category=category, labels=_split_labels(_cell(r, idx, "labels")),
        original=_cell(r, idx, "original description"),
    )


def _monarch_row(r, idx) -> MigTxn | None:
    amount = parse_amount(_cell(r, idx, "amount"))
    if amount is None:
        return None
    category = _cell(r, idx, "category") or None
    if category and category.lower() == "uncategorized":
        category = None
    return MigTxn(
        account=_cell(r, idx, "account"), date=date.min, amount=amount,
        payee=_cell(r, idx, "merchant", "original statement") or "(no description)",
        notes=_cell(r, idx, "notes"), category=category, labels=_split_labels(_cell(r, idx, "tags")),
        original=_cell(r, idx, "original statement"),
    )


def _actual_row(r, idx) -> MigTxn | None:
    amount = parse_amount(_cell(r, idx, "split amount", "amount"))
    if amount is None:
        return None
    payee = _cell(r, idx, "payee")
    transfer = TRANSFER_RE.match(payee)
    cleared_raw = _cell(r, idx, "cleared", "reconciled").lower()
    cleared = None if not cleared_raw else cleared_raw in {"cleared", "reconciled", "true", "yes", "1"}
    category = _cell(r, idx, "category") or None
    group = _cell(r, idx, "category group", "group") or None
    return MigTxn(
        account=_cell(r, idx, "account"), date=date.min, amount=amount, payee=payee or "(no payee)",
        notes=_cell(r, idx, "notes"), group=group, category=None if transfer else category,
        transfer_to=transfer.group(1) if transfer else None, cleared=cleared,
        starting_balance=payee.lower() in STARTING_BALANCE,
    )


def _parse_ynab_budget(headers, rows, data: MigrationData) -> None:
    idx = {h: i for i, h in enumerate(headers)}
    months: dict[str, date | None] = {}
    for r in rows:
        raw_month = _cell(r, idx, "month")
        if raw_month not in months:
            months[raw_month] = _month(raw_month)
        month = months[raw_month]
        amount = parse_amount(_cell(r, idx, "budgeted", "assigned"))
        group = _cell(r, idx, "category group", "master category") or None
        name = _cell(r, idx, "category", "sub category")
        if group and name.lower().startswith(group.lower() + ":"):
            name = name.split(":", 1)[1].strip()
        if not month or amount is None or not name:
            continue
        data.budgets.append(MigBudget(month=month, group=group, category=name, amount=amount))


def _month(value: str) -> date | None:
    v = value.strip()
    for fmt in ("%b %Y", "%B %Y", "%Y-%m", "%m/%Y", "%Y/%m"):
        try:
            return datetime.strptime(v, fmt).date().replace(day=1)
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(v, fmt).date().replace(day=1)
        except ValueError:
            pass
    return None


def _parse_generic(name: str, text: str, data: MigrationData, options: dict, date_format: str | None) -> None:
    opts = (options or {}).get(name) or {}
    result = parse_csv(text, mapping=opts.get("mapping") or None, date_format=date_format or opts.get("date_format"),
                       invert=opts.get("invert"))
    account = re.sub(r"\.(csv|tsv|txt)$", "", name, flags=re.I).strip() or name
    for t in result.transactions:
        data.transactions.append(MigTxn(
            account=account, date=t.date, amount=Decimal(t.amount), payee=t.description,
            category=t.bank_category or None, notes=t.memo if t.memo and t.memo != t.description else ""))
    data.generic.append(GenericFile(
        filename=name, columns=result.columns, mapping=result.mapping, sample_rows=result.sample_rows[:5],
        date_format=result.date_format, date_format_ambiguous=result.date_format_ambiguous,
        inverted=result.inverted, warnings=result.warnings[:10], count=len(result.transactions)))
    if result.date_format_ambiguous:
        data.date_format_ambiguous = True
    data.date_format = data.date_format or result.date_format


def parse_migration(files: list[tuple[str, bytes]], *, source: str | None = None, date_format: str | None = None,
                    generic: dict | None = None) -> MigrationData:
    """Parse one move's files. `source` forces a format; otherwise each file's header decides."""
    texts = expand_files(files)
    parsed = []
    for name, text in texts:
        headers, rows = _rows(text)
        if not headers:
            continue
        kind = detect_kind(headers)
        if source == "generic" and kind != "ynab_budget":
            kind = "generic"
        parsed.append((name, text, headers, rows, kind))
    kinds = [k for *_, k in parsed if k not in {"ynab_budget", "generic"}]
    chosen = source if source in SOURCES else (max(set(kinds), key=kinds.count) if kinds else "generic")
    data = MigrationData(source=chosen)
    for name, text, headers, rows, kind in parsed:
        data.files.append(name)
        if kind == "ynab_budget":
            _parse_ynab_budget(headers, rows, data)
        elif kind == "generic":
            _parse_generic(name, text, data, generic or {}, date_format)
        else:
            _parse_register(kind, headers, rows, data, date_format)
    if not data.transactions:
        data.warnings.append("No transactions were found in these files.")
    if data.skipped_rows:
        data.warnings.append("Some rows were skipped because their date or amount could not be read.")
    if data.date_format_ambiguous:
        data.warnings.append("Dates could be month-first or day-first. Assumed month/day/year; change it if that is wrong.")
    return data


def latest_budgets(budgets: list[MigBudget]) -> tuple[date | None, list[MigBudget]]:
    """The most recent month that has any money budgeted, and its non-zero lines."""
    months = sorted({b.month for b in budgets if b.amount}, reverse=True)
    if not months:
        return None, []
    return months[0], [b for b in budgets if b.month == months[0] and b.amount]
