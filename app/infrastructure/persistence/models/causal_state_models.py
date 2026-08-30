from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.database import Base


class StateCheckpointModel(Base):
    __tablename__ = "state_checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    checkpoint_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy: Mapped[str] = mapped_column(String(32), nullable=False, default="full_state")
    resource_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recoverable_fields: Mapped[str | None] = mapped_column(Text, nullable=True)
    version_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    etag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transaction_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    snapshot_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    object_generation: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    checkpoint_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    checkpoint_hash: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )


class ResourceVersionModel(Base):
    __tablename__ = "resource_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    change_origin: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    causal_owner: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    state_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    previous_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )


class StateDeltaModel(Base):
    __tablename__ = "state_deltas"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    delta_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    delta_type: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    before_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    after_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    changed_fields: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_fields: Mapped[str | None] = mapped_column(Text, nullable=True)
    removed_fields: Mapped[str | None] = mapped_column(Text, nullable=True)
    before_values: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_values: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_safe_delta: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    delta_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )


class AIChangeSetModel(Base):
    __tablename__ = "ai_changesets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    changeset_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    incident_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False)
    root_action_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    root_cause: Mapped[str] = mapped_column(Text, nullable=False, default="")
    causal_actions: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_resources: Mapped[str | None] = mapped_column(Text, nullable=True)
    before_references: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_references: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_references: Mapped[str | None] = mapped_column(Text, nullable=True)
    dependency_graph: Mapped[str | None] = mapped_column(Text, nullable=True)
    unrelated_mutations: Mapped[str | None] = mapped_column(Text, nullable=True)
    recoverability: Mapped[str | None] = mapped_column(Text, nullable=True)
    conflicts: Mapped[str | None] = mapped_column(Text, nullable=True)
    unknown_areas: Mapped[str | None] = mapped_column(Text, nullable=True)
    direct_changes: Mapped[str | None] = mapped_column(Text, nullable=True)
    indirect_changes: Mapped[str | None] = mapped_column(Text, nullable=True)
    dependent_changes: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_effects: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )


class CausalStateGraphModel(Base):
    __tablename__ = "causal_state_graphs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    graph_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    incident_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    root_action_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    nodes: Mapped[str | None] = mapped_column(Text, nullable=True)
    edges: Mapped[str | None] = mapped_column(Text, nullable=True)
    subgraph_extractions: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )


class RecoveryConfidenceModel(Base):
    __tablename__ = "recovery_confidences"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    confidence_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    plan_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(32), nullable=False, default="insufficient_evidence")
    before_state_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    after_state_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    current_state_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    adapter_support: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version_match: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    drift_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    conflict_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dependency_completeness: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verification_capability: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evidence_completeness: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    factors: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendations: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )


class DurableExecutionStepModel(Base):
    __tablename__ = "durable_execution_steps"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    step_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    plan_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    execution_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    execution_state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    target_system: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    target_resource: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    compensation_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    step_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )


class RecoveryReportModel(Base):
    __tablename__ = "recovery_reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    plan_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    incident_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ai_changes_recovered: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_changes_failed: Mapped[str | None] = mapped_column(Text, nullable=True)
    unrelated_changes_preserved: Mapped[str | None] = mapped_column(Text, nullable=True)
    manual_recovery_required: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual_verification_required"
    )
    confidence_level: Mapped[str] = mapped_column(
        String(32), nullable=False, default="insufficient_evidence"
    )
    resource_results: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
