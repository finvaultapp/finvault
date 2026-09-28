from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .db import get_db
from .models import User
from .security import decode_token

COOKIE_NAME = "fv_session"


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:]
    payload = decode_token(token) if token else None
    if not payload:
        raise HTTPException(401, "Not signed in")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active or user.token_version != payload.get("tv"):
        raise HTTPException(401, "Session expired")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Admins only")
    return user


def owned(db: Session, model, obj_id: int, user: User):
    """Fetch a row that belongs to the user, or 404. Keeps household members' data separate."""
    obj = db.get(model, obj_id)
    if obj is None or getattr(obj, "user_id", None) != user.id:
        raise HTTPException(404, f"{model.__name__} not found")
    return obj
