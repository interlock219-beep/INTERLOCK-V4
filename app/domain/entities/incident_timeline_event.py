from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class TimelineEventType(StrEnum):
    """Categorizes events in an incident timeline."""

    DISCOVERY = "discovery"
    ACTION_EVALUATED = "action_evaluated"
    ACTION_EXECUTED = "action_executed"
    CONTAINMENT_INITIATED = "containment_initiated"
    CONTAINMENT_COMPLETED = "containment_completed"
    RECOVERY_PLAN_CREATED = "recovery_plan_created"
    RECOVERY_PLAN_SIMULATED = "recovery_plan_simulated"
    RECOVERY_PLAN_APPROVED = "recovery_plan_approved"
    RECOVERY_PLAN_EXECUTED = "recovery_plan_executed"
    RECOVERY_PLAN_COMPLETED = "recovery_plan_completed"


@dataclass(frozen=True, slots=True)
class IncidentTimelineEvent:
    """A single immutable event in an incident timeline.

    Events are aggregated from discovery, action, containment, and recovery
    subsystems to give responders a unified, ordered audit trail.
    """

    event_id: str
    event_type: TimelineEventType
    timestamp: datetime
    actor: str
    description: str
    details: dict[str, str] = field(default_factory=dict)
    correlation_id: str | None = None
    severity: str = "info"
    tenant_id: str = ""
    agent_ids: list[str] = field(default_factory=list)
