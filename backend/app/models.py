"""Database models. Amounts are signed: negative means money leaving an account."""
import warnings
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, exc,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# SQLite stores Numeric as text/float; SQLAlchemy converts back to Decimal for us.
warnings.filterwarnings("ignore", category=exc.SAWarning, message=".*Decimal objects natively.*")

Money = Numeric(18, 4)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    base_currency: Mapped[str] = mapped_column(String(3), default="CAD")
    totp_secret: Mapped[str | None] = mapped_column(Text, nullable=True)  # encrypted
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    recovery_codes: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of hashes
    ai_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    # 'server' uses the household model; 'openai' uses the member's own OpenAI API key.
    ai_provider: Mapped[str] = mapped_column(String(20), default="server", server_default="server")
    ai_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)  # encrypted
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    locale: Mapped[str] = mapped_column(String(5), default="en", server_default="en")
    notify_ntfy_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    notify_email: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    notify_hide_amounts: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)  # JSON encoded


class Invite(Base):
    __tablename__ = "invites"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    note: Mapped[str] = mapped_column(String(200), default="")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    used_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SyncConnection(Base):
    __tablename__ = "sync_connections"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(30))  # gocardless | pluggy | simplefin
    name: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending | active | error
    credentials: Mapped[str] = mapped_column(Text, default="")  # encrypted JSON
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    institution: Mapped[str] = mapped_column(String(120), default="")
    # checking | savings | credit_card | investment | cash | loan | other
    type: Mapped[str] = mapped_column(String(20), default="checking")
    currency: Mapped[str] = mapped_column(String(3), default="CAD")
    country: Mapped[str] = mapped_column(String(2), default="CA")
    opening_balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    opening_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    import_preset: Mapped[str | None] = mapped_column(String(40), nullable=True)
    watch_folder: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    sync_connection_id: Mapped[int | None] = mapped_column(
        ForeignKey("sync_connections.id", ondelete="SET NULL"), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(10), default="expense")  # expense | income | transfer
    color: Mapped[str] = mapped_column(String(9), default="#7c8a96")
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    # medical | childcare | donations | moving | home_office | other_deductible
    tax_tag: Mapped[str | None] = mapped_column(String(20), nullable=True)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(255), default="")
    format: Mapped[str] = mapped_column(String(20), default="")
    preset: Mapped[str | None] = mapped_column(String(40), nullable=True)
    imported: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("account_id", "import_hash", name="uq_tx_account_hash"),
        UniqueConstraint("recurring_id", "date", name="uq_tx_recurring_date"),
        Index("ix_tx_user_date_id", "user_id", "date", "id"),
        Index("ix_tx_user_account_date", "user_id", "account_id", "date"),
        Index("ix_tx_user_category_date", "user_id", "category_id", "date"),
        Index("ix_tx_account_external_id", "account_id", "external_id"),
        Index("ix_tx_import_batch", "import_batch_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    description: Mapped[str] = mapped_column(String(500), default="")
    payee: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True)
    import_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True)
    recurring_id: Mapped[int | None] = mapped_column(ForeignKey("recurring.id", ondelete="SET NULL"), nullable=True)
    tax_tag: Mapped[str | None] = mapped_column(String(20), nullable=True)  # overrides the category's tag; 'none' excludes
    transfer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # the matching leg of a transfer
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    account: Mapped[Account] = relationship(lazy="joined")
    category: Mapped[Category | None] = relationship(lazy="joined")


class Rule(Base):
    __tablename__ = "rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    priority: Mapped[int] = mapped_column(Integer, default=100)
    match_field: Mapped[str] = mapped_column(String(20), default="description")  # description | payee
    match_type: Mapped[str] = mapped_column(String(20), default="contains")  # contains | equals | starts_with | regex
    pattern: Mapped[str] = mapped_column(String(300))
    amount_min: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    amount_max: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True)
    set_category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), nullable=True)
    set_payee: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("user_id", "category_id", name="uq_budget_category"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    amount: Mapped[Decimal] = mapped_column(Money)  # monthly, in the user's base currency


class Recurring(Base):
    __tablename__ = "recurring"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    amount: Mapped[Decimal] = mapped_column(Money)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    frequency: Mapped[str] = mapped_column(String(12), default="monthly")  # weekly|biweekly|monthly|quarterly|yearly
    next_date: Mapped[date] = mapped_column(Date)
    anchor_day: Mapped[int | None] = mapped_column(Integer, nullable=True)  # keeps "the 31st" from drifting
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    auto_post: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    remind_days: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = no reminder
    last_reminded_for: Mapped[date | None] = mapped_column(Date, nullable=True)


class Goal(Base):
    __tablename__ = "goals"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    target_amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3), default="CAD")
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    saved_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))  # used when no account is linked
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    # real_estate | vehicle | investment | retirement | cash | valuables | other | mortgage | loan | other_debt
    kind: Mapped[str] = mapped_column(String(20), default="other")
    is_liability: Mapped[bool] = mapped_column(Boolean, default=False)
    currency: Mapped[str] = mapped_column(String(3), default="CAD")
    notes: Mapped[str] = mapped_column(Text, default="")
    values: Mapped[list["AssetValue"]] = relationship(
        cascade="all, delete-orphan", order_by="AssetValue.date", lazy="selectin")


class AssetValue(Base):
    __tablename__ = "asset_values"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    value: Mapped[Decimal] = mapped_column(Money)


class ExchangeRate(Base):
    """1 unit of `base` equals `rate` units of `quote` on `date`. Shared by everyone on the server."""
    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("base", "quote", "date", name="uq_rate"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    base: Mapped[str] = mapped_column(String(3), index=True)
    quote: Mapped[str] = mapped_column(String(3), index=True)
    date: Mapped[date] = mapped_column(Date)
    rate: Mapped[Decimal] = mapped_column(Numeric(20, 10))
    source: Mapped[str] = mapped_column(String(20), default="manual")


# --- Registered accounts (TFSA / RRSP / FHSA) ------------------------------------

class RegisteredPlan(Base):
    """Contribution room for one plan and tax year, as the member copied it from CRA My Account."""
    __tablename__ = "registered_plans"
    __table_args__ = (UniqueConstraint("user_id", "kind", "year", name="uq_plan_year"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # tfsa | rrsp | fhsa
    year: Mapped[int] = mapped_column(Integer)
    room: Mapped[Decimal] = mapped_column(Money)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class PlanEntry(Base):
    """A contribution (positive) or withdrawal (negative) recorded by hand."""
    __tablename__ = "plan_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("registered_plans.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Money)
    note: Mapped[str] = mapped_column(String(200), default="")


# --- Splits and shared expenses ------------------------------------------------------

class TransactionSplit(Base):
    """Part of a transaction assigned to its own category. Amounts are signed like the transaction."""
    __tablename__ = "transaction_splits"
    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    note: Mapped[str] = mapped_column(String(200), default="")


class Person(Base):
    """Someone you share costs with (a partner, roommate, friend)."""
    __tablename__ = "people"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class Share(Base):
    """The part of a transaction another person owes you (positive) or you owe them (negative)."""
    __tablename__ = "shares"
    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)


class Settlement(Base):
    """A payment between you and a person. Positive: they paid you. Negative: you paid them."""
    __tablename__ = "settlements"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Money)
    note: Mapped[str] = mapped_column(String(200), default="")
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True)


# --- Receipts ----------------------------------------------------------------------

class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(80))
    size: Mapped[int] = mapped_column(Integer)
    stored_name: Mapped[str] = mapped_column(String(80))  # random name on disk, never the user's filename
    ocr_status: Mapped[str] = mapped_column(String(12), default="none")  # none | pending | done | failed
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
