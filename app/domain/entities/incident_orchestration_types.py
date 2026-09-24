from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class OrchestrationPhase(StrEnum):
    DETECTION = "detection"
    DISCOVERY = "discovery"
    CONTAINMENT = "containment"
    ANALYSIS = "analysis"
    RECOVERY_PLANNING = "recovery_planning"
    RECOVERY_EXECUTION = "recovery_execution"
    VERIFICATION = "verification"
    EVIDENCE_PRESERVATION = "evidence_preservation"
    FORENSICS = "forensics"
    RESOLUTION = "resolution"
    COMPLETED = "completed"
    FAILED = "failed"


class OrchestrationStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class OrchestrationOutcome(StrEnum):
    FULLY_RECOVERED = "fully_recovered"
    PARTIALLY_RECOVERED = "partially_recovered"
    CONTAINED = "contained"
    ESCALATED = "escalated"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class OrchestrationStep:
    """A single step in the incident orchestration workflow."""

    step_id: str
    phase: OrchestrationPhase
    action: str
    description: str
    tenant_id: str
    incident_id: str
    status: OrchestrationStepStatus = OrchestrationStepStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    blocking: bool = True
    retry_count: int = 0
    max_retries: int = 0


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    """Final result of an incident orchestration workflow."""

    orchestration_id: str
    tenant_id: str
    incident_id: str
    status: str
    outcome: OrchestrationOutcome
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    phases_completed: list[str] = field(default_factory=list)
    phases_skipped: list[str] = field(default_factory=list)
    error: str | None = None
    steps_executed: list[str] = field(default_factory=list)
    steps_failed: list[str] = field(default_factory=list)
    verification_passed: bool = False
    evidence_preserved: bool = False
    resilience_score: float = 0.0
    recommendations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IncidentOrchestrationPlan:
    """A plan defining the orchestration workflow for an incident."""

    plan_id: str
    tenant_id: str
    incident_id: str
    root_action_id: str
    agent_id: str
    phases: list[OrchestrationPhase] = field(default_factory=list)
    stop_on_failure: bool = True
    auto_containment: bool = True
    auto_recovery: bool = False
    auto_verification: bool = True
    evidence_preservation: bool = True
    forensic_logging: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "IncidentOrchestrationPlan",
    "OrchestrationOutcome",
    "OrchestrationPhase",
    "OrchestrationResult",
    "OrchestrationStep",
    "OrchestrationStepStatus",
]
