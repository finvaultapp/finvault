"""Admin-side tables: audit log, backup runs and single sign-on identities."""
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

__all__ = ["AuditEvent", "BackupRun", "OidcIdentity"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AuditEvent(Base):
    """One security-relevant event. `detail` is JSON and never holds passwords, codes or secret values."""
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    event: Mapped[str] = mapped_column(String(60), index=True)
    # Who did it (None for failed sign-ins of unknown people and for background jobs).
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    # Kept as text so the row still says who it was after the member is deleted.
    email: Mapped[str] = mapped_column(String(255), default="")
    # The member the action was done to, when that isn't the actor (admin actions).
    target_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    target_email: Mapped[str] = mapped_column(String(255), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[str] = mapped_column(Text, default="{}")


class BackupRun(Base):
    __tablename__ = "backup_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trigger: Mapped[str] = mapped_column(String(20), default="manual")  # manual | nightly
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | ok | failed
    filename: Mapped[str] = mapped_column(String(200), default="")
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    s3_status: Mapped[str] = mapped_column(String(20), default="off")  # off | ok | failed
    error: Mapped[str] = mapped_column(Text, default="")


class OidcIdentity(Base):
    """Links a provider account (issuer + subject) to a member, so a later email change at the provider can't take over."""
    __tablename__ = "oidc_identities"
    __table_args__ = (UniqueConstraint("issuer", "subject", name="uq_oidc_identity"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    issuer: Mapped[str] = mapped_column(String(300))
    subject: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
