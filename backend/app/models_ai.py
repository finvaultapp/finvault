"""Tables for the AI helpers (category suggestions). Imported at the end of models.py so they're auto-created."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

__all__ = ["AiMerchantSuggestion"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AiMerchantSuggestion(Base):
    """One model answer per member and normalized merchant, so the same merchant is never sent twice.

    category_id is empty when the model had no valid answer; status is new | accepted | rejected.
    """
    __tablename__ = "ai_merchant_suggestions"
    __table_args__ = (UniqueConstraint("user_id", "merchant_key", name="uq_ai_merchant"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    merchant_key: Mapped[str] = mapped_column(String(200))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(10), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
