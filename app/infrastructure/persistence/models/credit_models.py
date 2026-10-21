"""Persistence models for the recovery-credit system.

Three tables, all tenant-scoped via ``tenant_id`` (the product's organization
key — there is no separate organization table):

- ``credit_wallets``      one row per tenant; the server-controlled balance.
- ``credit_ledger``       append-only audit trail of every credit movement;
                          ``idempotency_key`` is UNIQUE so duplicate webhook
                          events and retried executions cannot double-charge.
- ``credit_reservations`` holds placed around executions in flight.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.database import Base


class CreditWalletModel(Base):
    __tablename__ = "credit_wallets"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    allocated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consumed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_enforced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    plan_tier: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    plan_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    subscription_id: Mapped[UUID | None] = mapped_column(nullable=True)
    provider_subscription_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CreditLedgerModel(Base):
    __tablename__ = "credit_ledger"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # UNIQUE is the double-charge firewall: allocations are keyed by billing
    # period, consumptions by the recovery plan that earned them.
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    recovery_plan_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subscription_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class CreditReservationModel(Base):
    __tablename__ = "credit_reservations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    recovery_plan_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
