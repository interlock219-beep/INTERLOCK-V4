from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.database import Base


class RecoveryExecutionModel(Base):
    """Execution tracking for compensations during recovery operations."""

    __tablename__ = "recovery_executions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    execution_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    plan_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    compensation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_system: Mapped[str] = mapped_column(String(255), nullable=False)
    target_resource: Mapped[str] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    execution_order: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    execution_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    success: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_outcome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verification_passed: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    verification_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
