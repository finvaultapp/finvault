import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import settings_store
from ..db import get_db
from ..deps import current_user
from ..models import User
from ..security import encrypt
from ..services import ai, audit

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/status")
def status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    target = ai.resolve(db, user)
    server_on = bool(settings_store.get(db, "ai_enabled"))
    personal_allowed = bool(settings_store.get(db, "ai_allow_personal_keys"))
    return {
        "server_enabled": server_on, "personal_allowed": personal_allowed,
        "available": bool(target) or server_on or personal_allowed,
        "ready": bool(target) and user.ai_opt_in, "opted_in": user.ai_opt_in,
        "provider": user.ai_provider, "model": target["model"] if target else None,
        "server_model": settings_store.get(db, "ai_model") if server_on else None,
        "endpoint_is_local": target["local"] if target else ai.is_local_url(settings_store.get(db, "ai_base_url") or ""),
        "personal": {"key_set": bool(user.ai_api_key), "model": user.ai_model},
    }


@router.get("/context-preview")
def context_preview(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Show the exact finance summary that would be sent with an AI question."""
    max_tx = int(settings_store.get(db, "ai_max_transactions") or 300)
    target = ai.resolve(db, user)
    return {
        "model": target["model"] if target else None,
        "provider": target["provider"] if target else None,
        "endpoint_is_local": target["local"] if target else ai.is_local_url(settings_store.get(db, "ai_base_url") or ""),
        "max_transactions": max_tx,
        "data": json.loads(ai.build_context(db, user, max_tx)),
    }


class PersonalIn(BaseModel):
    provider: str = Field(pattern="^(server|openai)$")
    api_key: str | None = Field(default=None, max_length=400)
    model: str | None = Field(default=None, max_length=100)


@router.put("/personal")
def set_personal(body: PersonalIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.provider == "openai" and not settings_store.get(db, "ai_allow_personal_keys"):
        raise HTTPException(403, "Your admin hasn't allowed personal OpenAI keys on this server.")
    if body.api_key:
        key = body.api_key.strip()
        try:
            models = ai.list_openai_models(key)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"Couldn't reach OpenAI: {exc}") from exc
        user.ai_api_key = encrypt(key)
        if not body.model and models and not user.ai_model:
            user.ai_model = models[0]
    if body.model:
        user.ai_model = body.model.strip()
    user.ai_provider = body.provider
    db.commit()
    if body.api_key:
        audit.record(db, "ai.key_connected", request=request, user=user, provider="openai")
    return status(user, db)


@router.get("/personal/models")
def personal_models(user: User = Depends(current_user)):
    key = ai.personal_key(user)
    if not key:
        raise HTTPException(404, "Add your OpenAI API key first.")
    try:
        return {"models": ai.list_openai_models(key)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Couldn't reach OpenAI: {exc}") from exc


@router.delete("/personal")
def remove_personal(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Forget the member's OpenAI key and switch back to the household model."""
    had_key = bool(user.ai_api_key)
    user.ai_api_key, user.ai_model, user.ai_provider = None, None, "server"
    db.commit()
    if had_key:
        audit.record(db, "ai.key_removed", request=request, user=user, provider="openai")
    return status(user, db)


class Msg(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=8000)


class ChatIn(BaseModel):
    messages: list[Msg]


@router.post("/chat")
def chat(body: ChatIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if ai.resolve(db, user) is None:
        raise HTTPException(403, "AI chat isn't set up for your account. Choose a model in Settings.")
    if not user.ai_opt_in:
        raise HTTPException(403, "Turn on AI chat in Settings first. It's off until you choose to share your data with the model.")
    try:
        return {"reply": ai.chat(db, user, [m.model_dump() for m in body.messages])}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Couldn't reach the model: {exc}") from exc
