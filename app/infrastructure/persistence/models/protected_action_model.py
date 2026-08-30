from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.database import Base


class ProtectedActionModel(Base):
    __tablename__ = "protected_actions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    action_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    authority_grant_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    tool: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    resource: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    policy_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    parent_action_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    workflow_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    reversibility: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    before_state_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    after_state_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tool_arguments: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    decision_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Surgical recovery extensions
    workflow_step: Mapped[int] = mapped_column(Integer(), nullable=True)
    execution_depth: Mapped[int] = mapped_column(Integer(), nullable=True)
    requires_approval: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, server_default="0"
    )
    approval_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recovery_plan_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
