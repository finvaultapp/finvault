"""Investment holdings: securities, daily prices, positions and investment activity.

Everything here belongs to one member (user_id), like the rest of FinVault's data, so a
household member never sees which securities another member holds.

How a position is worked out (see services/invest.py):
- A `Holding` row is a snapshot: "on `as_of` this account held `quantity` units with this
  book cost". It comes from a holdings export or manual entry.
- `InvestmentActivity` rows (buys, sells, reinvested dividends, splits...) dated after the
  snapshot are applied on top of it. With no snapshot, the position is built from activity alone.
- The account's cash stays in ordinary transactions; activity never creates transactions.
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import Money, utcnow

Qty = Numeric(24, 8)
Price = Numeric(24, 8)

ASSET_CLASSES = ("equity", "fixed_income", "cash", "balanced", "real_estate", "commodity", "crypto", "other")
ACTIVITY_KINDS = ("buy", "sell", "dividend", "distribution", "reinvested_dividend", "fee", "split", "return_of_capital")
REGISTRATIONS = ("non_registered", "tfsa", "rrsp", "fhsa", "resp", "rrif", "lira", "other")

__all__ = ["Security", "SecurityPrice", "Holding", "InvestmentActivity", "InvestImport", "InvestAccountInfo",
           "ASSET_CLASSES", "ACTIVITY_KINDS", "REGISTRATIONS"]


class Security(Base):
    __tablename__ = "securities"
    __table_args__ = (UniqueConstraint("user_id", "symbol", "exchange", name="uq_security_symbol"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(30))  # upper case, e.g. XEQT
    exchange: Mapped[str] = mapped_column(String(20), default="")  # TSX, NYSE, NASDAQ... or ""
    name: Mapped[str] = mapped_column(String(200), default="")
    currency: Mapped[str] = mapped_column(String(3), default="CAD")  # the currency it trades in
    asset_class: Mapped[str] = mapped_column(String(20), default="equity")
    price_symbol: Mapped[str | None] = mapped_column(String(40), nullable=True)  # override for the price source
    last_fetch_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    last_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SecurityPrice(Base):
    """Closing price of one unit, in the security's currency."""
    __tablename__ = "security_prices"
    __table_args__ = (UniqueConstraint("security_id", "date", name="uq_security_price_day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    close: Mapped[Decimal] = mapped_column(Price)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | import | stooq


class InvestImport(Base):
    """One imported holdings or activity file, so it can be undone."""
    __tablename__ = "invest_imports"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(255), default="")
    source: Mapped[str] = mapped_column(String(40), default="")  # wealthsimple_activity | questrade | generic ...
    kind: Mapped[str] = mapped_column(String(12), default="activity")  # activity | holdings
    imported: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Holding(Base):
    """A position snapshot: quantity and book cost (in the account's currency) on `as_of`."""
    __tablename__ = "holdings"
    __table_args__ = (UniqueConstraint("account_id", "security_id", name="uq_holding_account_security"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id", ondelete="CASCADE"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Qty)
    cost_basis: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    as_of: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | import
    import_id: Mapped[int | None] = mapped_column(ForeignKey("invest_imports.id", ondelete="SET NULL"), nullable=True)


class InvestmentActivity(Base):
    """A buy, sell, dividend, distribution, reinvested dividend, fee, split or return of capital.

    `quantity`, `amount` and `commission` are stored as positive numbers; `kind` gives the direction.
    `amount` is the gross value in `currency` (normally the account's currency): for a buy,
    quantity x price; for a dividend, the cash received. For a split, `split_ratio` is new units
    per old unit (2 for a 2-for-1 split).
    """
    __tablename__ = "investment_activities"
    __table_args__ = (UniqueConstraint("account_id", "import_hash", name="uq_invest_activity_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    security_id: Mapped[int | None] = mapped_column(ForeignKey("securities.id", ondelete="CASCADE"), nullable=True, index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(24))
    quantity: Mapped[Decimal] = mapped_column(Qty, default=Decimal("0"))
    price: Mapped[Decimal | None] = mapped_column(Price, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    commission: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="CAD")
    split_ratio: Mapped[Decimal | None] = mapped_column(Price, nullable=True)
    description: Mapped[str] = mapped_column(String(500), default="")
    import_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    import_id: Mapped[int | None] = mapped_column(ForeignKey("invest_imports.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InvestAccountInfo(Base):
    """Tax treatment of an investment account. ACB is only tracked for non-registered accounts."""
    __tablename__ = "invest_account_info"
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True)
    registration: Mapped[str] = mapped_column(String(20), default="non_registered")
    notes: Mapped[str] = mapped_column(Text, default="")
