"""Account-recovery tables: one-time password reset links. Imported at the end of models.py so they're auto-created."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

__all__ = ["PasswordResetToken"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PasswordResetToken(Base):
    """A one-time link to choose a new password.

    Only the SHA-256 of the random token is stored, so a copy of the database can't be used to reset
    anyone's password. `used_at` is set when the link is used, or when it is replaced by a newer link or
    made pointless by a completed reset. `via` is admin | email.
    """
    __tablename__ = "password_reset_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    via: Mapped[str] = mapped_column(String(10), default="admin")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
