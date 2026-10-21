"""Shared coordination tables (V6 WP-3).

Back the cross-process ``PlanLeaseStore`` and ``QuotaCounterStore``
implementations (runbook §6/§7): one row per plan for the exclusive
executor lease with its monotonic fencing token, and one row per tenant for
the windowed quota counters.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.database import Base


class PlanLeaseModel(Base):
    """Exclusive execution lease for one recovery plan."""

    __tablename__ = "plan_leases"

    plan_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # "" marks a released tombstone (keeps the fencing token monotonic).
    owner: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    fencing_token: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class QuotaCounterModel(Base):
    """Per-tenant daily plan count and active-compensation slots."""

    __tablename__ = "quota_counters"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plans_today: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    day_window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    active_compensations: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
