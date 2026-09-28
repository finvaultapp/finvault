"""Optional AI chat over the user's own data, via any OpenAI-compatible endpoint (Ollama, LM Studio, vLLM...).

Off by default. It needs the admin to enable it server-wide and each user to opt in.
"""
import ipaddress
import json
from datetime import date, timedelta
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import settings_store
from ..models import Account, Category, Transaction, User
from . import reports
from .ledger import account_balances


def is_local_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if host in {"localhost", "ollama", "host.docker.internal"} or host.endswith((".local", ".lan", ".internal", ".home.arpa")):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return "." not in host  # docker service names like "llm"


def build_context(db: Session, user: User, max_tx: int) -> str:
    today = date.today()
    balances = account_balances(db, user.id)
    accounts = [{"name": a.name, "type": a.type, "currency": a.currency, "balance": reports.f2(balances.get(a.id))}
                for a in db.scalars(select(Account).where(Account.user_id == user.id, Account.is_archived.is_(False)))]
    start = date(today.year, today.month, 1) - timedelta(days=150)
    ie = reports.income_expense(db, user, date(start.year, start.month, 1), today)
    budgets = reports.budgets_for_month(db, user, today.year, today.month)
    cats = {c.id: c.name for c in db.scalars(select(Category).where(Category.user_id == user.id))}
    recent = db.scalars(select(Transaction).where(Transaction.user_id == user.id)
                        .order_by(Transaction.date.desc()).limit(max_tx))
    tx = [[t.date.isoformat(), t.account.name, t.description[:80], float(t.amount), cats.get(t.category_id, "")]
          for t in recent]
    ctx = {
        "today": today.isoformat(), "base_currency": user.base_currency, "accounts": accounts,
        "monthly_income_expense": ie["series"], "expense_by_category_last_6_months": ie["expense_by_category"][:15],
        "this_month_budgets": [{k: b[k] for k in ("name", "budget", "spent", "remaining")} for b in budgets["items"]],
        "net_worth": reports.net_worth(db, user, 3)["current"],
        "recent_transactions[date,account,description,amount,category]": tx,
    }
    return json.dumps(ctx, separators=(",", ":"))


SYSTEM = (
    "You are a careful personal-finance assistant inside FinVault, a self-hosted app. Answer using only the JSON data "
    "provided. Amounts are signed: negative means money out. When the data can't answer, say so. Do not give "
    "investment advice or recommend specific securities. Be concise and show the numbers you used."
)


OPENAI_URL = "https://api.openai.com/v1"


def personal_key(user: User) -> str | None:
    from ..security import decrypt
    return decrypt(user.ai_api_key) if user.ai_api_key else None


def resolve(db: Session, user: User) -> dict | None:
    """Which model this member's questions go to, or None when AI isn't available to them."""
    if user.ai_provider == "openai":
        key = personal_key(user)
        if settings_store.get(db, "ai_allow_personal_keys") and key and user.ai_model:
            return {"provider": "openai", "base": OPENAI_URL, "model": user.ai_model, "key": key, "local": False}
        return None
    if settings_store.get(db, "ai_enabled"):
        base = (settings_store.get(db, "ai_base_url") or "").rstrip("/")
        return {"provider": "server", "base": base, "model": settings_store.get(db, "ai_model"),
                "key": settings_store.get(db, "ai_api_key"), "local": is_local_url(base)}
    return None


def list_openai_models(key: str) -> list[str]:
    """Check a personal key and return the chat models it can use."""
    r = httpx.get(f"{OPENAI_URL}/models", headers={"Authorization": f"Bearer {key}"}, timeout=20)
    if r.status_code == 401:
        raise ValueError("OpenAI didn't accept that key. Copy it again from platform.openai.com/api-keys.")
    if r.status_code >= 400:
        raise ValueError(f"OpenAI returned {r.status_code}: {r.text[:160]}")
    skip = ("embedding", "whisper", "tts", "dall-e", "image", "audio", "realtime", "moderation", "transcribe", "search")
    ids = [m["id"] for m in r.json().get("data", [])]
    chat_ids = [i for i in ids if i.startswith(("gpt-", "o", "chatgpt")) and not any(s in i for s in skip)]
    return sorted(chat_ids, reverse=True)


def chat(db: Session, user: User, messages: list[dict]) -> str:
    target = resolve(db, user)
    if target is None:
        raise RuntimeError("No AI model is set up for your account.")
    base, model, key = target["base"], target["model"], target["key"]
    max_tx = int(settings_store.get(db, "ai_max_transactions") or 300)
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM + "\n\nDATA:\n" + build_context(db, user, max_tx)}]
        + [{"role": m["role"], "content": m["content"][:4000]} for m in messages[-12:] if m["role"] in {"user", "assistant"}],
        "stream": False,
    }
    if target["provider"] == "server":
        payload["temperature"] = 0.2  # some OpenAI reasoning models reject a custom temperature
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    r = httpx.post(f"{base}/chat/completions", json=payload, headers=headers, timeout=180)
    if r.status_code >= 400:
        raise RuntimeError(f"The model server returned {r.status_code}: {r.text[:200]}")
    return r.json()["choices"][0]["message"]["content"]
