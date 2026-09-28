"""AI category suggestions and plain-language search. Same gate as chat: a model from ai.resolve() plus opt-in."""
import json
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, owned
from ..importers import normalize_merchant
from ..models import Account, Category, Transaction, User
from ..models_ai import AiMerchantSuggestion
from ..services import ai, ai_tools
from ..services.ledger import Categorizer
from . import categories as categories_router

router = APIRouter(prefix="/api/ai", tags=["ai"])


def ai_target(db: Session, user: User) -> dict:
    target = ai.resolve(db, user)
    if target is None:
        raise HTTPException(403, "AI isn't set up for your account. Choose a model in Settings.")
    if not user.ai_opt_in:
        raise HTTPException(403, "Turn on the AI assistant in Settings first. It's off until you choose to share data with the model.")
    return target


def _cats(db: Session, user: User) -> list[Category]:
    return list(db.scalars(select(Category).where(Category.user_id == user.id).order_by(Category.name)))


def _suggestion_out(t: Transaction, row: AiMerchantSuggestion, by_id: dict[int, Category]) -> dict:
    c = by_id[row.category_id]
    return {"transaction_id": t.id, "category_id": c.id, "category_name": c.name, "category_color": c.color,
            "confidence": round(row.confidence, 2), "merchant": row.merchant_key}


def _cached(db: Session, user: User, keys: set[str]) -> dict[str, AiMerchantSuggestion]:
    if not keys:
        return {}
    rows = db.scalars(select(AiMerchantSuggestion).where(AiMerchantSuggestion.user_id == user.id,
                                                         AiMerchantSuggestion.merchant_key.in_(keys)))
    return {r.merchant_key: r for r in rows}


def _uncategorized(db: Session, user: User, ids: list[int] | None, limit: int) -> list[Transaction]:
    q = select(Transaction).where(Transaction.user_id == user.id, Transaction.category_id.is_(None),
                                  Transaction.transfer_id.is_(None))
    if ids:
        q = q.where(Transaction.id.in_(ids[:200]))
    return list(db.scalars(q.order_by(Transaction.date.desc(), Transaction.id).limit(limit)).unique())


def _unfamiliar(db: Session, user: User, txs: list[Transaction]) -> dict[str, Transaction]:
    """Merchants that rules and remembered history can't place, one sample transaction each."""
    categorizer = Categorizer(db, user.id)
    out: dict[str, Transaction] = {}
    for t in txs:
        key = normalize_merchant(t.description)
        if key and key not in out and categorizer.apply(t.description, t.payee, Decimal(t.amount), t.account_id)[0] is None:
            out[key] = t
    return out


def _visible(txs, cache, by_id) -> list[dict]:
    out = []
    for t in txs:
        row = cache.get(normalize_merchant(t.description))
        if row and row.category_id in by_id and row.status != "rejected":
            out.append(_suggestion_out(t, row, by_id))
    return out


@router.get("/suggestions")
def cached_suggestions(transaction_id: list[int] | None = Query(None), user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    """Suggestions already known for these transactions. Never calls the model."""
    ai_target(db, user)
    txs = _uncategorized(db, user, transaction_id, 200)
    by_id = {c.id: c for c in _cats(db, user)}
    cache = _cached(db, user, {normalize_merchant(t.description) for t in txs} - {""})
    unasked = [k for k in _unfamiliar(db, user, txs) if k not in cache]
    return {"suggestions": _visible(txs, cache, by_id), "unasked": len(unasked)}


class SuggestIn(BaseModel):
    transaction_ids: list[int] | None = Field(default=None, max_length=200)


@router.post("/suggestions")
def suggest(body: SuggestIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Ask the model about uncategorized transactions that rules and history can't place.

    Only unfamiliar merchants without a cached answer are sent, at most 25 per call.
    """
    target = ai_target(db, user)
    cats = _cats(db, user)
    if not cats:
        raise HTTPException(422, "Add some categories first.")
    by_id = {c.id: c for c in cats}
    txs = _uncategorized(db, user, body.transaction_ids, 200)
    unfamiliar = _unfamiliar(db, user, txs)
    cache = _cached(db, user, set(unfamiliar))
    to_send = [(k, t) for k, t in unfamiliar.items() if k not in cache][:ai_tools.MAX_MERCHANTS_PER_CALL]

    sent = 0
    if to_send:
        rate_key = f"suggest:{user.id}"
        if ai_tools.suggest_limit.blocked(rate_key):
            raise HTTPException(429, "That's a lot of AI requests in a short time. Try again in a few minutes.")
        ai_tools.suggest_limit.hit(rate_key)
        payload = ai_tools.build_suggest_payload([(i + 1, t.description, Decimal(t.amount)) for i, (_, t) in enumerate(to_send)],
                                                 [c.name for c in cats])
        try:
            raw = ai_tools.parse_json(ai_tools.complete(target, ai_tools.SUGGEST_SYSTEM, json.dumps(payload, ensure_ascii=False)))
            picked = ai_tools.parse_suggestions(raw, set(range(1, len(to_send) + 1)), {c.name.lower(): c.id for c in cats})
        except ai_tools.ModelError as exc:
            raise HTTPException(502, str(exc)) from exc
        for i, (key, _) in enumerate(to_send, start=1):
            cat_id, conf = picked.get(i, (None, 0.0))
            row = AiMerchantSuggestion(user_id=user.id, merchant_key=key[:200], category_id=cat_id, confidence=conf)
            db.add(row)
            cache[key] = row
        db.commit()
        sent = len(to_send)
    return {"suggestions": _visible(txs, _cached(db, user, {normalize_merchant(t.description) for t in txs} - {""}), by_id),
            "sent": sent, "unasked": len([k for k in unfamiliar if k not in cache])}


class AcceptItem(BaseModel):
    transaction_id: int
    category_id: int


class AcceptIn(BaseModel):
    items: list[AcceptItem] = Field(max_length=500)
    create_rules: bool = False


def _rule_pattern(description: str, key: str) -> str | None:
    words = [w for w in key.lower().split() if len(w) > 1]
    for n in (2, 1):
        pattern = " ".join(words[:n])
        if len(pattern) >= 3 and pattern in description.lower():
            return pattern
    return None


@router.post("/suggestions/accept")
def accept(body: AcceptIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ai_target(db, user)
    updated, rules, keys = 0, 0, {}
    for item in body.items:
        t = owned(db, Transaction, item.transaction_id, user)
        owned(db, Category, item.category_id, user)
        t.category_id = item.category_id
        updated += 1
        key = normalize_merchant(t.description)
        if key:
            keys.setdefault(key, (t, item.category_id))
    for row in _cached(db, user, set(keys)).values():
        row.status = "accepted"
    db.commit()
    applied = 0
    if body.create_rules:
        for key, (t, cat_id) in keys.items():
            pattern = _rule_pattern(t.description, key)
            if not pattern:
                continue
            # Same path as the Rules page, so validation and "apply to the rest" behave identically.
            r = categories_router.create_rule(categories_router.RuleIn(name=pattern, pattern=pattern, set_category_id=cat_id),
                                              apply=True, user=user, db=db)
            rules += 1
            applied += r.get("applied", 0)
    return {"updated": updated, "rules_created": rules, "applied": applied}


class RejectIn(BaseModel):
    transaction_ids: list[int] = Field(max_length=500)


@router.post("/suggestions/reject")
def reject(body: RejectIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ai_target(db, user)
    keys = {normalize_merchant(owned(db, Transaction, i, user).description) for i in body.transaction_ids}
    rows = _cached(db, user, keys - {""})
    for row in rows.values():
        row.status = "rejected"
    db.commit()
    return {"rejected": len(rows)}


class SearchIn(BaseModel):
    question: str = Field(min_length=2, max_length=300)


@router.post("/search")
def plain_search(body: SearchIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Turn a question into the normal /api/transactions filters. The model never sees any transactions."""
    target = ai_target(db, user)
    rate_key = f"search:{user.id}"
    if ai_tools.search_limit.blocked(rate_key):
        raise HTTPException(429, "That's a lot of AI searches in a short time. Try again in a few minutes.")
    ai_tools.search_limit.hit(rate_key)
    cats = _cats(db, user)
    accts = list(db.scalars(select(Account).where(Account.user_id == user.id, Account.is_archived.is_(False))
                            .order_by(Account.name)))
    today = date.today()
    payload = ai_tools.build_search_payload(body.question.strip(), today, [c.name for c in cats], [a.name for a in accts])
    try:
        raw = ai_tools.parse_json(ai_tools.complete(target, ai_tools.SEARCH_SYSTEM, json.dumps(payload, ensure_ascii=False)))
        result = ai_tools.interpret_search(raw, today, {c.name.lower(): c.id for c in cats},
                                           {a.name.lower(): a.id for a in accts})
    except ai_tools.ModelError as exc:
        raise HTTPException(502, f"{exc} Try rephrasing, or use the filters.") from exc
    f = result["filters"]
    if not any([f["start"], f["end"], f["category_id"], f["account_id"], f["min_amount"] is not None,
                f["max_amount"] is not None, f["kind"], f["q"]]):
        raise HTTPException(422, "The model couldn't turn that into filters. Try naming a category, an amount or a time.")
    return result
