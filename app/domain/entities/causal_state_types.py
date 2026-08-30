from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class CheckpointStrategy(StrEnum):
    FULL_STATE = "full_state"
    DELTA = "delta"
    VERSION_REFERENCE = "version_reference"
    ADAPTER_SNAPSHOT = "adapter_snapshot"


class ChangeOrigin(StrEnum):
    HUMAN = "human"
    AI_AGENT = "ai_agent"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class DeltaType(StrEnum):
    FIELD_LEVEL = "field_level"
    RECORD_LEVEL = "record_level"
    VERSION_RESTORE = "version_restore"
    COMPENSATING_OPERATION = "compensating_operation"
    SEMANTIC_COMPENSATION = "semantic_compensation"
    UNKNOWN = "unknown"


class MergeSafety(StrEnum):
    MERGE_SAFE = "merge_safe"
    MERGE_CONDITIONAL = "merge_conditional"
    MERGE_UNSUPPORTED = "merge_unsupported"


class ConfidenceLevel(StrEnum):
    HIGH_CONFIDENCE = "high_confidence"
    MEDIUM_CONFIDENCE = "medium_confidence"
    LOW_CONFIDENCE = "low_confidence"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class CausalRelationType(StrEnum):
    PARENT_CHILD = "parent_child"
    DEPENDENCY = "dependency"
    DELEGATION = "delegation"
    TRIGGERED = "triggered"


class VerificationStatus(StrEnum):
    EXECUTED_AND_VERIFIED = "executed_and_verified"
    EXECUTED_NOT_VERIFIED = "executed_not_verified"
    EXECUTION_FAILED = "execution_failed"
    UNKNOWN_EXTERNAL_OUTCOME = "unknown_external_outcome"
    MANUAL_VERIFICATION_REQUIRED = "manual_verification_required"


@dataclass(frozen=True, slots=True)
class StateCheckpoint:
    """Recovery checkpoint captured before a high-impact action."""

    checkpoint_id: str
    tenant_id: str
    action_id: str
    agent_id: str
    resource_id: str
    resource_type: str
    strategy: CheckpointStrategy
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    resource_version: str | None = None
    state_hash: str | None = None
    recoverable_fields: dict[str, Any] = field(default_factory=dict)
    version_token: str | None = None
    etag: str | None = None
    transaction_id: str | None = None
    snapshot_reference: str | None = None
    object_generation: str | None = None
    config_revision: str | None = None
    checkpoint_metadata: dict[str, Any] = field(default_factory=dict)
    checkpoint_hash: str = ""


@dataclass(frozen=True, slots=True)
class ResourceVersion:
    """A single version in a resource's lineage."""

    version_id: str
    tenant_id: str
    resource_id: str
    resource_type: str
    version_number: int
    change_origin: ChangeOrigin
    causal_owner: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    state_hash: str | None = None
    external_version: str | None = None
    version_token: str | None = None
    action_id: str | None = None
    agent_id: str | None = None
    previous_version_id: str | None = None
    version_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StateDelta:
    """Computed difference between two states."""

    delta_id: str
    tenant_id: str
    resource_id: str
    delta_type: DeltaType
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    before_version_id: str | None = None
    after_version_id: str | None = None
    changed_fields: list[str] = field(default_factory=list)
    added_fields: list[str] = field(default_factory=list)
    removed_fields: list[str] = field(default_factory=list)
    before_values: dict[str, Any] = field(default_factory=dict)
    after_values: dict[str, Any] = field(default_factory=dict)
    is_safe_delta: bool = False
    delta_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConflictMarker:
    """Marks a conflict between AI-caused and unrelated changes."""

    marker_id: str
    tenant_id: str
    resource_id: str
    field_path: str
    conflict_type: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    ai_value: Any = None
    external_value: Any = None
    current_value: Any = None
    resolution: str = "unresolved"
    marker_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AIChangeSet:
    """Reconstructed set of changes caused by an AI agent incident."""

    changeset_id: str
    tenant_id: str
    incident_id: str
    agent_id: str
    root_action_id: str
    correlation_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    root_cause: str = ""
    causal_actions: list[str] = field(default_factory=list)
    affected_resources: list[str] = field(default_factory=list)
    before_references: dict[str, str] = field(default_factory=dict)
    after_references: dict[str, str] = field(default_factory=dict)
    current_references: dict[str, str] = field(default_factory=dict)
    dependency_graph: dict[str, Any] = field(default_factory=dict)
    unrelated_mutations: list[dict[str, Any]] = field(default_factory=list)
    recoverability: dict[str, str] = field(default_factory=dict)
    conflicts: list[ConflictMarker] = field(default_factory=list)
    unknown_areas: list[str] = field(default_factory=list)
    direct_changes: list[str] = field(default_factory=list)
    indirect_changes: list[str] = field(default_factory=list)
    dependent_changes: list[str] = field(default_factory=list)
    external_effects: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RecoveryConfidence:
    """Explainable confidence assessment for a recovery operation."""

    confidence_id: str
    tenant_id: str
    plan_id: str
    level: ConfidenceLevel
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    before_state_available: bool = False
    after_state_available: bool = False
    current_state_available: bool = False
    adapter_support: bool = False
    version_match: bool = False
    drift_detected: bool = False
    conflict_detected: bool = False
    dependency_completeness: bool = False
    verification_capability: bool = False
    evidence_completeness: float = 0.0
    factors: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CausalStateNode:
    """A node in the causal state graph."""

    node_id: str
    node_type: str
    entity_id: str
    tenant_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    state_before: dict[str, Any] | None = None
    state_after: dict[str, Any] | None = None
    version_before: str | None = None
    version_after: str | None = None
    agent_id: str | None = None
    action_id: str | None = None
    resource_id: str | None = None
    node_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CausalStateEdge:
    """An edge in the causal state graph."""

    edge_id: str
    source_node_id: str
    target_node_id: str
    relation_type: CausalRelationType
    tenant_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    edge_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CausalStateGraph:
    """Complete causal state graph for an incident."""

    graph_id: str
    tenant_id: str
    incident_id: str
    root_action_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    nodes: list[CausalStateNode] = field(default_factory=list)
    edges: list[CausalStateEdge] = field(default_factory=list)
    subgraph_extractions: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RecoveryReport:
    """Final recovery report after execution and verification."""

    report_id: str
    tenant_id: str
    plan_id: str
    incident_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    ai_changes_recovered: list[str] = field(default_factory=list)
    ai_changes_failed: list[str] = field(default_factory=list)
    unrelated_changes_preserved: list[str] = field(default_factory=list)
    manual_recovery_required: list[str] = field(default_factory=list)
    verification_status: VerificationStatus = VerificationStatus.MANUAL_VERIFICATION_REQUIRED
    confidence_level: ConfidenceLevel = ConfidenceLevel.INSUFFICIENT_EVIDENCE
    resource_results: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DurableExecutionStep:
    """Durable step tracking for resumable distributed execution."""

    step_id: str
    plan_id: str
    action_id: str
    execution_order: int
    tenant_id: str
    execution_state: str = "pending"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    idempotency_key: str = ""
    target_system: str = ""
    target_resource: str = ""
    compensation_payload: dict[str, Any] = field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    verification_passed: bool = False
    retry_count: int = 0
    max_retries: int = 3
    step_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AdapterCapabilityDeclaration:
    """Declares what capabilities an adapter supports."""

    adapter_name: str
    adapter_type: str
    can_capture_before_state: bool = False
    can_capture_after_state: bool = False
    can_read_current_state: bool = False
    can_compute_delta: bool = False
    can_detect_drift: bool = False
    can_simulate: bool = False
    can_compensate: bool = False
    can_verify: bool = False
    supports_idempotency: bool = False
    supports_versioning: bool = False
    supports_safe_merge: bool = False
    merge_safety: MergeSafety = MergeSafety.MERGE_UNSUPPORTED
    declared_capabilities: list[str] = field(default_factory=list)
