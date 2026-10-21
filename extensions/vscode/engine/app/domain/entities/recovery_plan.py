from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class RecoveryStatus(StrEnum):
    DRAFT = "draft"
    SIMULATED = "simulated"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


class RecoveryOutcome(StrEnum):
    SAFE_AUTOMATIC = "safe_automatic"
    REQUIRES_HUMAN_APPROVAL = "requires_human_approval"
    NOT_REVERSIBLE = "not_reversible"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class RecoveryPlan:
    """Recovery plan for an incident or action."""

    plan_id: str
    tenant_id: str
    incident_action_id: str
    status: RecoveryStatus = RecoveryStatus.DRAFT
    outcome: RecoveryOutcome = RecoveryOutcome.UNKNOWN
    simulation_result: dict[str, Any] = field(default_factory=dict)
    steps: list[dict[str, str]] = field(default_factory=list)
    approved_by: str | None = None
    executed_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    executed_at: datetime | None = None

    # Surgical recovery extensions
    plan_version: str = "1.0"
    plan_hash: str = ""
    topological_order: list[str] = field(default_factory=list)
    dependency_graph_reference: str = ""
    execution_status: str = "pending"
    approval_policy: str = "single_approval"
    approval_threshold: int = 1
    stop_conditions: list[str] = field(default_factory=list)
    compensation_summary: dict[str, Any] = field(default_factory=dict)
    incident_id: str = ""
    root_action_id: str = ""
    affected_action_ids: list[str] = field(default_factory=list)
