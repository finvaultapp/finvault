"""Tags: free-form labels on transactions. Names are trimmed, single-spaced and unique per member ignoring case."""
import re
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Tag, TransactionTag, User

MAX_TAG = 80


def clean_name(name: str | None) -> str:
    return re.sub(r"\s+", " ", name or "").strip()[:MAX_TAG]


def find(db: Session, user: User, name: str) -> Tag | None:
    name = clean_name(name)
    if not name:
        return None
    return db.scalar(select(Tag).where(Tag.user_id == user.id, func.lower(Tag.name) == name.lower()))


def get_or_create(db: Session, user: User, name: str) -> Tag:
    name = clean_name(name)
    if not name:
        raise HTTPException(422, "Give the tag a name.")
    tag = find(db, user, name)
    if tag is None:
        tag = Tag(user_id=user.id, name=name)
        db.add(tag)
        db.flush()
    return tag


def owned_tag(db: Session, user: User, tag_id: int) -> Tag:
    tag = db.get(Tag, tag_id)
    if tag is None or tag.user_id != user.id:
        raise HTTPException(404, "Tag not found.")
    return tag


def names_by_transaction(db: Session, tx_ids: list[int]) -> dict[int, list[dict]]:
    """{transaction_id: [{id, name}, ...]} sorted by name, in chunks so SQLite's variable limit is safe."""
    out: dict[int, list[dict]] = defaultdict(list)
    for i in range(0, len(tx_ids), 900):
        chunk = tx_ids[i:i + 900]
        rows = db.execute(select(TransactionTag.transaction_id, Tag.id, Tag.name)
                          .join(Tag, Tag.id == TransactionTag.tag_id)
                          .where(TransactionTag.transaction_id.in_(chunk)).order_by(func.lower(Tag.name)))
        for tx_id, tid, name in rows:
            out[tx_id].append({"id": tid, "name": name})
    return out


def add_tags(db: Session, items: list[dict]) -> list[dict]:
    """Add a "tags" list to transaction dicts (from tx_out) without one query per row."""
    by_tx = names_by_transaction(db, [i["id"] for i in items])
    for i in items:
        i["tags"] = by_tx.get(i["id"], [])
    return items
