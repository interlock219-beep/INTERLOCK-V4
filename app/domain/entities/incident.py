from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class IncidentStatus(StrEnum):
    DETECTED = "detected"
    CONTAINED = "contained"
    INVESTIGATING = "investigating"
    ROLLBACK_PLANNED = "rollback_planned"
    ROLLING_BACK = "rolling_back"
    VERIFYING = "verifying"
    RESOLVED = "resolved"
    PARTIALLY_RECOVERED = "partially_recovered"
    RECOVERY_FAILED = "recovery_failed"
    REQUIRES_HUMAN = "requires_human"


class IncidentSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class Incident:
    """Durable incident record for AI-agent security events."""

    incident_id: str
    tenant_id: str
    agent_id: str
    severity: IncidentSeverity = IncidentSeverity.MEDIUM
    status: IncidentStatus = IncidentStatus.DETECTED
    trigger: str = ""
    session_ids: list[str] = field(default_factory=list)
    affected_action_ids: list[str] = field(default_factory=list)
    affected_resources: list[str] = field(default_factory=list)
    blast_radius: dict[str, Any] = field(default_factory=dict)
    containment_state: dict[str, Any] = field(default_factory=dict)
    rollback_state: dict[str, Any] = field(default_factory=dict)
    verification_state: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
