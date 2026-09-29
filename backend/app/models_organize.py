"""Models for organizing transactions: free-form tags (many per transaction), separate from categories."""
from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

__all__ = ["Tag", "TransactionTag"]


class Tag(Base):
    """A household label such as "vacation 2026" or "reno". Names are unique per member, ignoring case."""
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_tag_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))


class TransactionTag(Base):
    __tablename__ = "transaction_tags"
    __table_args__ = (Index("ix_transaction_tags_tag", "tag_id"),)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
