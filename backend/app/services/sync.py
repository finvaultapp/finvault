"""Optional bank sync providers. Off unless the admin enables it and credentials exist.

Canadian accounts are never synced. Canadian banks don't offer a regulated open
banking API to consumers yet, and the third-party aggregators that fill the gap
typically need your online-banking password. FinVault refuses to link any
Canadian account (country CA, CAD currency, or a .ca institution) and points
the user to file import instead.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config, settings_store
from ..importers import ParsedTxn, ParseResult
from ..models import Account, SyncConnection, User
from ..security import decrypt_json, encrypt
from .ledger import commit_import
from .net import validate_outbound_url

CANADA_BLOCK_MESSAGE = (
    "Direct bank connections are turned off for Canadian accounts. Download a QFX/OFX, CSV or text-based PDF "
    "export from your bank's website and import it instead. Your banking password never leaves you."
)


class SyncError(Exception):
    pass


def looks_canadian(currency: str | None = None, domain: str | None = None, country: str | None = None) -> bool:
    return (country or "").upper() == "CA" or (currency or "").upper() == "CAD" or (domain or "").lower().endswith(".ca")


def providers_status(db: Session) -> dict:
    enabled = bool(settings_store.get(db, "bank_sync_enabled"))
    return {
        "enabled": enabled,
        "providers": [
            {"id": "gocardless", "name": "GoCardless Bank Account Data", "region": "Europe (PSD2)",
             "available": enabled and bool(config.GOCARDLESS_SECRET_ID and config.GOCARDLESS_SECRET_KEY),
             "needs": "GOCARDLESS_SECRET_ID and GOCARDLESS_SECRET_KEY"},
            {"id": "pluggy", "name": "Pluggy", "region": "Brazil (Open Finance)",
             "available": enabled and bool(config.PLUGGY_CLIENT_ID and config.PLUGGY_CLIENT_SECRET),
             "needs": "PLUGGY_CLIENT_ID and PLUGGY_CLIENT_SECRET"},
            {"id": "simplefin", "name": "SimpleFIN Bridge", "region": "United States",
             "available": enabled and bool(settings_store.get(db, "simplefin_enabled")),
             "needs": "An admin must enable SimpleFIN; each user brings their own setup token"},
        ],
        "canada": CANADA_BLOCK_MESSAGE,
    }


# --- GoCardless (formerly Nordigen) ------------------------------------------

GC_URL = "https://bankaccountdata.gocardless.com/api/v2"


def _gc_token() -> str:
    r = httpx.post(f"{GC_URL}/token/new/", json={"secret_id": config.GOCARDLESS_SECRET_ID,
                                                  "secret_key": config.GOCARDLESS_SECRET_KEY}, timeout=20)
    if r.status_code >= 400:
        raise SyncError(f"GoCardless auth failed ({r.status_code})")
    return r.json()["access"]


def gc_institutions(country: str) -> list[dict]:
    if country.upper() == "CA":
        raise SyncError(CANADA_BLOCK_MESSAGE)
    r = httpx.get(f"{GC_URL}/institutions/", params={"country": country.lower()},
                  headers={"Authorization": f"Bearer {_gc_token()}"}, timeout=20)
    r.raise_for_status()
    return [{"id": i["id"], "name": i["name"], "logo": i.get("logo")} for i in r.json()]


def gc_start(db: Session, user: User, institution_id: str, redirect_url: str) -> tuple[SyncConnection, str]:
    if not redirect_url.startswith(("http://", "https://")):
        raise SyncError("The return address must start with http:// or https://.")
    token = _gc_token()
    r = httpx.post(f"{GC_URL}/requisitions/", headers={"Authorization": f"Bearer {token}"},
                   json={"redirect": redirect_url, "institution_id": institution_id, "user_language": "EN"}, timeout=20)
    if r.status_code >= 400:
        raise SyncError(f"GoCardless could not start the connection: {r.text[:200]}")
    req = r.json()
    conn = SyncConnection(user_id=user.id, provider="gocardless", name=institution_id, status="pending",
                          credentials=encrypt({"requisition_id": req["id"]}))
    db.add(conn)
    db.commit()
    return conn, req["link"]


def _gc_accounts(creds: dict) -> list[dict]:
    token = _gc_token()
    h = {"Authorization": f"Bearer {token}"}
    req = httpx.get(f"{GC_URL}/requisitions/{creds['requisition_id']}/", headers=h, timeout=20).json()
    out = []
    for acc_id in req.get("accounts", []):
        details = httpx.get(f"{GC_URL}/accounts/{acc_id}/details/", headers=h, timeout=20).json().get("account", {})
        out.append({"id": acc_id, "name": details.get("name") or details.get("product") or details.get("iban", acc_id),
                    "currency": details.get("currency"), "domain": None})
    return out


def _gc_transactions(creds: dict, ext_id: str, since: date) -> list[ParsedTxn]:
    h = {"Authorization": f"Bearer {_gc_token()}"}
    r = httpx.get(f"{GC_URL}/accounts/{ext_id}/transactions/", headers=h,
                  params={"date_from": since.isoformat()}, timeout=30)
    if r.status_code >= 400:
        raise SyncError(f"GoCardless transactions failed ({r.status_code})")
    out = []
    for t in r.json().get("transactions", {}).get("booked", []):
        amt = t.get("transactionAmount", {})
        desc = (t.get("remittanceInformationUnstructured") or t.get("creditorName") or t.get("debtorName")
                or " ".join(t.get("remittanceInformationUnstructuredArray", [])) or "Bank transaction")
        out.append(ParsedTxn(date=date.fromisoformat(t.get("bookingDate") or t.get("valueDate")),
                             amount=Decimal(amt.get("amount", "0")), description=desc,
                             payee=t.get("creditorName") or t.get("debtorName") or "",
                             external_id=t.get("transactionId") or t.get("internalTransactionId"),
                             currency=amt.get("currency")))
    return out


# --- Pluggy (Brazil) ----------------------------------------------------------

PLUGGY_URL = "https://api.pluggy.ai"


def _pluggy_key() -> str:
    r = httpx.post(f"{PLUGGY_URL}/auth", json={"clientId": config.PLUGGY_CLIENT_ID,
                                               "clientSecret": config.PLUGGY_CLIENT_SECRET}, timeout=20)
    if r.status_code >= 400:
        raise SyncError(f"Pluggy auth failed ({r.status_code})")
    return r.json()["apiKey"]


def pluggy_connect(db: Session, user: User, item_id: str) -> SyncConnection:
    key = _pluggy_key()
    r = httpx.get(f"{PLUGGY_URL}/items/{item_id}", headers={"X-API-KEY": key}, timeout=20)
    if r.status_code >= 400:
        raise SyncError("Pluggy item not found. Copy the item ID from your Pluggy/MeuPluggy dashboard.")
    item = r.json()
    conn = SyncConnection(user_id=user.id, provider="pluggy", name=(item.get("connector") or {}).get("name", "Pluggy"),
                          status="active", credentials=encrypt({"item_id": item_id}))
    db.add(conn)
    db.commit()
    return conn


def _pluggy_accounts(creds: dict) -> list[dict]:
    key = _pluggy_key()
    r = httpx.get(f"{PLUGGY_URL}/accounts", params={"itemId": creds["item_id"]}, headers={"X-API-KEY": key}, timeout=20)
    r.raise_for_status()
    return [{"id": a["id"], "name": a.get("name", a["id"]), "currency": a.get("currencyCode"), "domain": None}
            for a in r.json().get("results", [])]


def _pluggy_transactions(creds: dict, ext_id: str, since: date) -> list[ParsedTxn]:
    key = _pluggy_key()
    out, page = [], 1
    while True:
        r = httpx.get(f"{PLUGGY_URL}/transactions", headers={"X-API-KEY": key}, timeout=30,
                      params={"accountId": ext_id, "from": since.isoformat(), "page": page, "pageSize": 500})
        r.raise_for_status()
        data = r.json()
        for t in data.get("results", []):
            out.append(ParsedTxn(date=date.fromisoformat(t["date"][:10]), amount=Decimal(str(t["amount"])),
                                 description=t.get("description") or "Transação", external_id=t["id"],
                                 currency=t.get("currencyCode")))
        if page >= data.get("totalPages", 1):
            break
        page += 1
    return out


# --- SimpleFIN ----------------------------------------------------------------

def simplefin_connect(db: Session, user: User, setup_token: str) -> SyncConnection:
    import base64
    try:
        claim_url = base64.b64decode(setup_token.strip()).decode()
    except Exception as exc:  # noqa: BLE001
        raise SyncError("That doesn't look like a SimpleFIN setup token.") from exc
    if not claim_url.startswith("https://"):
        raise SyncError("SimpleFIN setup token must point to an https URL.")
    try:
        claim_url = validate_outbound_url(claim_url, label="SimpleFIN setup token")
    except ValueError as exc:
        raise SyncError(str(exc)) from exc
    r = httpx.post(claim_url, timeout=20)
    if r.status_code >= 400:
        raise SyncError("SimpleFIN rejected the token. Setup tokens can only be claimed once; create a new one.")
    try:
        access_url = validate_outbound_url(r.text.strip(), label="SimpleFIN access URL")
    except ValueError as exc:
        raise SyncError(f"SimpleFIN returned an unsafe access URL: {exc}") from exc
    conn = SyncConnection(user_id=user.id, provider="simplefin", name="SimpleFIN", status="active",
                          credentials=encrypt({"access_url": access_url}))
    db.add(conn)
    db.commit()
    return conn


def _simplefin_get(creds: dict, since: date | None = None) -> dict:
    params = {"start-date": int(datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc).timestamp())} if since else {"balances-only": 1}
    access_url = validate_outbound_url(creds["access_url"], label="SimpleFIN access URL")
    r = httpx.get(f"{access_url}/accounts", params=params, timeout=40)
    if r.status_code >= 400:
        raise SyncError(f"SimpleFIN request failed ({r.status_code})")
    return r.json()


def _simplefin_accounts(creds: dict) -> list[dict]:
    data = _simplefin_get(creds)
    return [{"id": a["id"], "name": a.get("name", a["id"]), "currency": a.get("currency"),
             "domain": (a.get("org") or {}).get("domain")} for a in data.get("accounts", [])]


def _simplefin_transactions(creds: dict, ext_id: str, since: date) -> list[ParsedTxn]:
    data = _simplefin_get(creds, since)
    out = []
    for a in data.get("accounts", []):
        if a["id"] != ext_id:
            continue
        for t in a.get("transactions", []):
            out.append(ParsedTxn(date=datetime.fromtimestamp(int(t["posted"]), tz=timezone.utc).date(),
                                 amount=Decimal(str(t["amount"])), description=t.get("description") or t.get("payee") or "",
                                 payee=t.get("payee") or "", external_id=t.get("id"), currency=a.get("currency")))
    return out


# --- Common -------------------------------------------------------------------

_ACCOUNTS = {"gocardless": _gc_accounts, "pluggy": _pluggy_accounts, "simplefin": _simplefin_accounts}
_TXNS = {"gocardless": _gc_transactions, "pluggy": _pluggy_transactions, "simplefin": _simplefin_transactions}


def remote_accounts(conn: SyncConnection) -> list[dict]:
    accounts = _ACCOUNTS[conn.provider](decrypt_json(conn.credentials))
    for a in accounts:
        a["blocked"] = looks_canadian(a.get("currency"), a.get("domain"))
    return accounts


def link_account(db: Session, user: User, conn: SyncConnection, ext: dict, account: Account | None) -> Account:
    if ext.get("blocked") or looks_canadian(ext.get("currency"), ext.get("domain")):
        raise SyncError(CANADA_BLOCK_MESSAGE)
    if account is None:
        account = Account(user_id=user.id, name=ext.get("name") or "Synced account",
                          currency=(ext.get("currency") or user.base_currency).upper(), country="", institution=conn.name)
        db.add(account)
    elif looks_canadian(account.currency, country=account.country):
        raise SyncError(CANADA_BLOCK_MESSAGE)
    account.sync_connection_id = conn.id
    account.external_id = ext["id"]
    conn.status = "active"
    db.commit()
    return account


def sync_connection(db: Session, conn: SyncConnection, days: int = 90) -> int:
    if not settings_store.get(db, "bank_sync_enabled"):
        raise SyncError("Bank sync is turned off by the admin.")
    user = db.get(User, conn.user_id)
    creds = decrypt_json(conn.credentials)
    total = 0
    try:
        for acct in db.scalars(select(Account).where(Account.sync_connection_id == conn.id)):
            if looks_canadian(acct.currency, country=acct.country):
                continue
            since = (conn.last_synced_at.date() - timedelta(days=7)) if conn.last_synced_at else date.today() - timedelta(days=days)
            txns = _TXNS[conn.provider](creds, acct.external_id, since)
            batch = commit_import(db, user, acct, ParseResult(format=f"sync:{conn.provider}", transactions=txns),
                                  f"{conn.provider} sync")
            total += batch.imported
        from .transfers import auto_match
        auto_match(db, user)
        conn.status, conn.last_error = "active", None
    except (SyncError, httpx.HTTPError, KeyError, ValueError) as exc:
        conn.status, conn.last_error = "error", str(exc)[:500]
        db.commit()
        raise SyncError(str(exc)) from exc
    conn.last_synced_at = datetime.now(timezone.utc)
    db.commit()
    return total
