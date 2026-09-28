"""Models for the planning features: forecast settings, debt details and recurring-charge alerts."""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

__all__ = ["PlanPrefs", "DebtSetting", "ChargeAlert"]

_Money = Numeric(18, 4)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PlanPrefs(Base):
    """One row per member: the low-balance cushion for the forecast and the last debt budget they tried."""
    __tablename__ = "plan_prefs"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    cushion: Mapped[Decimal] = mapped_column(_Money, default=Decimal("0"))
    debt_budget: Mapped[Decimal | None] = mapped_column(_Money, nullable=True)


class DebtSetting(Base):
    """APR and minimum payment for one debt. A debt is a credit card / loan account or a liability asset."""
    __tablename__ = "debt_settings"
    __table_args__ = (UniqueConstraint("user_id", "source", "ref_id", name="uq_debt_setting"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(10))  # account | asset
    ref_id: Mapped[int] = mapped_column(Integer)
    apr: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0"))  # percent, e.g. 19.99
    min_payment: Mapped[Decimal] = mapped_column(_Money, default=Decimal("0"))
    kind: Mapped[str | None] = mapped_column(String(10), nullable=True)  # card | loan | mortgage (None = guess)


class ChargeAlert(Base):
    """A price change on a recurring charge, or a new charge that looks like a subscription."""
    __tablename__ = "charge_alerts"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_charge_alert"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # price_change | new_subscription
    key: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(200), default="")
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True)
    recurring_id: Mapped[int | None] = mapped_column(ForeignKey("recurring.id", ondelete="SET NULL"), nullable=True)
    usual_amount: Mapped[Decimal | None] = mapped_column(_Money, nullable=True)
    amount: Mapped[Decimal] = mapped_column(_Money)
    last_date: Mapped[date] = mapped_column(Date)
    hits: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
