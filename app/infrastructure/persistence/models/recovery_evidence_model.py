from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.database import Base


class RecoveryEvidenceModel(Base):
    """Recovery evidence captured during or after protected action execution."""

    __tablename__ = "recovery_evidence"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    evidence_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    action_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False)
    authority_grant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parent_action_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    root_action_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    incident_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_system: Mapped[str] = mapped_column(String(255), nullable=False)
    target_resource: Mapped[str] = mapped_column(String(255), nullable=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    before_state_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    after_state_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_payload_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    response_payload_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    compensation_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    compensation_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="reverse_operation"
    )
    recovery_adapter_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unsupported"
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    dependency_edges: Mapped[str | None] = mapped_column(Text, nullable=True)
    reversibility_classification: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unknown"
    )
    state_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resource_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    recovery_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_hash: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    adapter_capability: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unsupported"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
