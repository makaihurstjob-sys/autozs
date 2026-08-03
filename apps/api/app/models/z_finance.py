from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.store_keys import DEFAULT_EBAY_STORE_KEY
from app.models.domain import TimestampMixin


class ZFinanceTransaction(Base, TimestampMixin):
    __tablename__ = "z_finance_transactions"
    __table_args__ = (UniqueConstraint("external_id", name="uq_z_finance_transaction_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(256), index=True)
    account_external_id: Mapped[str] = mapped_column(String(256), index=True)
    classification: Mapped[str] = mapped_column(String(64), index=True)
    direction: Mapped[str] = mapped_column(String(32), default="")
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    pending: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    description: Mapped[str] = mapped_column(String(512), default="")
    supplier_order_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    payout_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    matched_supplier_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_orders.id"), nullable=True, index=True
    )
    matched_payout_id: Mapped[int | None] = mapped_column(
        ForeignKey("z_finance_payouts.id"), nullable=True, index=True
    )
    reconciliation_status: Mapped[str] = mapped_column(String(32), default="needs_review", index=True)
    reconciliation_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ZFinancePayout(Base, TimestampMixin):
    __tablename__ = "z_finance_payouts"
    __table_args__ = (UniqueConstraint("external_id", name="uq_z_finance_payout_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(256), index=True)
    store_key: Mapped[str] = mapped_column(String(128), default=DEFAULT_EBAY_STORE_KEY, index=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    status: Mapped[str] = mapped_column(String(32), default="expected", index=True)
    payout_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    matched_transaction_external_id: Mapped[str | None] = mapped_column(String(256), nullable=True)


class ZFinanceSyncState(Base, TimestampMixin):
    __tablename__ = "z_finance_sync_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), unique=True, default="z_finance")
    cursor: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
