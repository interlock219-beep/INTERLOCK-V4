from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class Reversibility(StrEnum):
    """Fine-grained reversibility classifications for protected actions.

    Backward-compatible: legacy values ``reversible`` and
    ``reversible_with_approval`` are preserved as aliases and normalised
    to the new canonical values at the persistence boundary.
    """

    AUTOMATICALLY_REVERSIBLE = "automatically_reversible"
    CONDITIONALLY_REVERSIBLE = "conditionally_reversible"
    MANUALLY_RECOVERABLE = "manually_recoverable"
    IRREVERSIBLE = "irreversible"
    UNKNOWN = "unknown"

    # Legacy aliases kept for backward compatibility with existing data.
    REVERSIBLE = "reversible"
    REVERSIBLE_WITH_APPROVAL = "reversible_with_approval"

    # Additional legacy values for migration compatibility.
    LEGACY_REVERSIBLE = "reversible"
    LEGACY_REVERSIBLE_WITH_APPROVAL = "reversible_with_approval"

    @classmethod
    def normalize(cls, value: str | Reversibility) -> Reversibility:
        """Map legacy string values to their canonical equivalents."""
        if isinstance(value, Reversibility):
            if value in (cls.REVERSIBLE, cls.LEGACY_REVERSIBLE):
                return cls.AUTOMATICALLY_REVERSIBLE
            if value in (cls.REVERSIBLE_WITH_APPROVAL, cls.LEGACY_REVERSIBLE_WITH_APPROVAL):
                return cls.CONDITIONALLY_REVERSIBLE
            return value
        legacy_map = {
            "reversible": cls.AUTOMATICALLY_REVERSIBLE,
            "reversible_with_approval": cls.CONDITIONALLY_REVERSIBLE,
        }
        mapped = legacy_map.get(value)
        if mapped is not None:
            return mapped
        return cls(value)

    @classmethod
    def is_auto_reversible(cls, value: str | Reversibility) -> bool:
        n = cls.normalize(value)
        return n == cls.AUTOMATICALLY_REVERSIBLE

    @classmethod
    def is_conditional(cls, value: str | Reversibility) -> bool:
        n = cls.normalize(value)
        return n == cls.CONDITIONALLY_REVERSIBLE

    @classmethod
    def is_manual(cls, value: str | Reversibility) -> bool:
        n = cls.normalize(value)
        return n == cls.MANUALLY_RECOVERABLE

    @classmethod
    def blocks_automatic_execution(cls, value: str | Reversibility) -> bool:
        n = cls.normalize(value)
        return n in (
            cls.MANUALLY_RECOVERABLE,
            cls.IRREVERSIBLE,
            cls.UNKNOWN,
        )


class DriftStatus(StrEnum):
    NO_DRIFT = "no_drift"
    DRIFT_DETECTED = "drift_detected"
    CONCURRENT_MUTATION = "concurrent_mutation"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    RESOURCE_MISSING = "resource_missing"
    VERSION_MISMATCH = "version_mismatch"
    PRECONDITION_FAILED = "precondition_failed"


class ConflictStatus(StrEnum):
    NO_CONFLICT = "no_conflict"
    CONFLICT_DETECTED = "conflict_detected"
    CONCURRENT_MUTATION = "concurrent_mutation"
    VERSION_MISMATCH = "version_mismatch"
    RESOURCE_MISSING = "resource_missing"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    PRECONDITION_FAILED = "precondition_failed"


class ExecutionState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL_SUCCESS = "partial_success"
    BLOCKED_BY_CONFLICT = "blocked_by_conflict"
    BLOCKED_BY_DRIFT = "blocked_by_drift"
    STOPPED = "stopped"
    REQUIRES_MANUAL_ACTION = "requires_manual_action"
    UNKNOWN_EXTERNAL_OUTCOME = "unknown_external_outcome"


class RecoveryAdapterType(StrEnum):
    DATABASE_SQL = "database_sql"
    DATABASE_RECORD = "database_record"
    HTTP_REST = "http_rest"
    EVENT_MESSAGE = "event_message"
    CONFIG_ROLLBACK = "config_rollback"
    FILE_VERSION = "file_version"
    IAM = "iam"
    MOCK = "mock"
    STUB = "stub"
    UNSUPPORTED = "unsupported"


class AdapterCapability(StrEnum):
    PRODUCTION_VALIDATED = "production_validated"
    REFERENCE_IMPLEMENTATION = "reference_implementation"
    SIMULATION_CAPABLE = "simulation_capable"
    MOCK = "mock"
    STUB = "stub"
    UNSUPPORTED = "unsupported"


class CompensationType(StrEnum):
    REVERSE_OPERATION = "reverse_operation"
    COMPENSATING_EVENT = "compensating_event"
    STATE_TRANSITION = "state_transition"
    DELETION = "deletion"
    DEACTIVATION = "deactivation"
    CUSTOM = "custom"


class SimulationLimitation(StrEnum):
    SIMULATION_LIMITED = "simulation_limited"
    SIMULATION_COMPLETE = "simulation_complete"
    SIMULATION_NOT_AVAILABLE = "simulation_not_available"


class StopCondition(StrEnum):
    ON_FIRST_FAILURE = "on_first_failure"
    ON_BLOCKING_CONFLICT = "on_blocking_conflict"
    ON_BLOCKING_DRIFT = "on_blocking_drift"
    CONTINUE_ON_FAILURE = "continue_on_failure"
    REQUIRE_ALL_APPROVED = "require_all_approved"


class ApprovalPolicyType(StrEnum):
    SINGLE_APPROVAL = "single_approval"
    DUAL_APPROVAL = "dual_approval"
    M_OF_N = "m_of_n"


@dataclass(frozen=True, slots=True)
class RecoveryEvidence:
    """Immutable recovery evidence captured for a protected action."""

    evidence_id: str
    action_id: str
    tenant_id: str
    agent_id: str
    authority_grant_id: str | None
    parent_action_id: str | None
    root_action_id: str | None
    correlation_id: str
    incident_id: str | None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    target_system: str = ""
    target_resource: str = ""
    action_type: str = ""

    before_state_reference: str | None = None
    after_state_reference: str | None = None

    request_payload_reference: str | None = None
    response_payload_reference: str | None = None

    compensation_payload: dict[str, Any] = field(default_factory=dict)
    compensation_type: CompensationType = CompensationType.CUSTOM
    recovery_adapter_type: RecoveryAdapterType = RecoveryAdapterType.UNSUPPORTED

    idempotency_key: str = ""
    dependency_edges: list[str] = field(default_factory=list)

    reversibility_classification: Reversibility = Reversibility.UNKNOWN

    state_version: str | None = None
    state_hash: str | None = None
    resource_version: str | None = None

    verification_requirements: list[str] = field(default_factory=list)
    recovery_metadata: dict[str, Any] = field(default_factory=dict)

    evidence_hash: str = ""
    adapter_capability: AdapterCapability = AdapterCapability.UNSUPPORTED


@dataclass(frozen=True, slots=True)
class PreconditionResult:
    """Result of checking recovery preconditions."""

    satisfied: bool
    failed_checks: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DriftResult:
    """Result of drift detection for a resource."""

    status: DriftStatus
    details: dict[str, Any] = field(default_factory=dict)
    current_version: str | None = None
    evidence_version: str | None = None
    current_state: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ConflictResult:
    """Result of conflict detection."""

    status: ConflictStatus
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RollbackImpact:
    """Simulation result describing the impact of a compensation."""

    action_id: str
    reversibility: Reversibility
    would_succeed: bool
    drift_status: DriftStatus
    conflict_status: ConflictStatus
    compensation_operation: str
    compensation_payload: dict[str, Any]
    external_api_calls: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    simulation_limitation: SimulationLimitation | None = None
    expected_after_state: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class CompensationAction:
    """A concrete compensation action ready for execution."""

    action_id: str
    incident_action_id: str
    compensation_type: CompensationType
    compensation_payload: dict[str, Any]
    idempotency_key: str
    target_system: str
    target_resource: str
    execution_order: int
    reversibility: Reversibility
    drift_status: DriftStatus
    conflict_status: ConflictStatus
    verification_requirements: list[str]
    dependency_edges: list[str]
    plan_id: str = ""
    skip_reason: str | None = None


@dataclass(frozen=True, slots=True)
class CompensationResult:
    """Result of executing a compensation."""

    action_id: str
    success: bool
    execution_state: ExecutionState
    idempotency_key: str
    details: dict[str, Any] = field(default_factory=dict)
    external_outcome: str = ""
    verification_passed: bool = False
    verification_details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Result of verifying a completed compensation."""

    action_id: str
    verified: bool
    details: dict[str, Any] = field(default_factory=dict)
    drift_status: DriftStatus = DriftStatus.NO_DRIFT


@dataclass(frozen=True, slots=True)
class RecoveryExecution:
    """Record of a single compensation execution within a recovery plan."""

    execution_id: str
    plan_id: str
    action_id: str
    tenant_id: str
    compensation_type: CompensationType
    target_system: str
    target_resource: str = ""
    idempotency_key: str = ""
    execution_order: int = 0
    execution_state: ExecutionState = ExecutionState.PENDING
    success: bool = False
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    external_outcome: str = ""
    verification_passed: bool = False
    verification_details: dict[str, Any] = field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    executed_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
