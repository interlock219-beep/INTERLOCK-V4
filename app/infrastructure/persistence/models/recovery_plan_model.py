from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.database import Base


class RecoveryPlanModel(Base):
    __tablename__ = "recovery_plans"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    plan_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    incident_action_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    simulation_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    executed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Surgical recovery extensions
    plan_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    plan_hash: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    topological_order: Mapped[str | None] = mapped_column(Text, nullable=True)
    dependency_graph_reference: Mapped[str] = mapped_column(
        String(255), nullable=False, default=""
    )
    execution_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    approval_policy: Mapped[str] = mapped_column(
        String(32), nullable=False, default="single_approval"
    )
    approval_threshold: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    stop_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    compensation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    incident_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    root_action_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    affected_action_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
