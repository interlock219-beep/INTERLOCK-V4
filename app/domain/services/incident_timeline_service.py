from __future__ import annotations

from typing import Any

from app.domain.entities.incident_timeline_event import (
    IncidentTimelineEvent,
    TimelineEventType,
)
from app.domain.entities.protected_action import ActionStatus
from app.domain.entities.recovery_plan import RecoveryStatus
from app.domain.repositories.containment_repository import (
    ContainmentRepository,
    RecoveryPlanRepository,
)
from app.domain.repositories.discovery_event_repository import DiscoveryEventRepository
from app.domain.repositories.protected_action_repository import ProtectedActionRepository


class IncidentTimelineService:
    """Aggregates events from multiple subsystems into a unified timeline.

    Events are sourced from discovery, protected-action, containment, and
    recovery-plan repositories, then ordered chronologically.
    """

    def __init__(
        self,
        discovery_repo: DiscoveryEventRepository,
        action_repo: ProtectedActionRepository,
        containment_repo: ContainmentRepository,
        recovery_repo: RecoveryPlanRepository,
    ) -> None:
        self._discovery_repo = discovery_repo
        self._action_repo = action_repo
        self._containment_repo = containment_repo
        self._recovery_repo = recovery_repo

    async def get_timeline(
        self,
        tenant_id: str,
        incident_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[IncidentTimelineEvent]:
        """Return a chronologically-ordered timeline for the given incident.

        ``incident_id`` is treated as an agent_id that was compromised, contained,
        or quarantined.  The method collects discovery events, protected actions,
        containment events, and recovery plans that reference that agent.
        """
        events: list[IncidentTimelineEvent] = []

        discovery_events, _ = await self._discovery_repo.list_by_agent(
            tenant_id, incident_id, limit=limit, offset=offset
        )
        for de in discovery_events:
            events.append(
                IncidentTimelineEvent(
                    event_id=de.discovery_id,
                    event_type=TimelineEventType.DISCOVERY,
                    timestamp=de.created_at,
                    actor="system",
                    description=(
                        f"Agent {de.agent_id or de.resource_id} "
                        f"discovered via {de.source.value}"
                    ),
                    details={
                        "discovery_status": de.discovery_status.value,
                        "finding_severity": de.finding_severity,
                    },
                    correlation_id=de.discovery_id,
                    severity=de.finding_severity,
                    tenant_id=de.tenant_id,
                    agent_ids=[de.agent_id] if de.agent_id else [],
                )
            )

        actions, _ = await self._action_repo.list_by_agent(
            tenant_id, incident_id, limit=limit, offset=offset
        )
        for act in actions:
            if act.evaluated_at and act.evaluated_at > act.created_at:
                events.append(
                    IncidentTimelineEvent(
                        event_id=act.action_id,
                        event_type=TimelineEventType.ACTION_EVALUATED,
                        timestamp=act.evaluated_at,
                        actor=act.agent_id,
                        description=f"Action {act.tool} on {act.resource} evaluated",
                        details={
                            "status": act.status.value,
                            "decision_reason": act.decision_reason,
                            "risk_score": str(act.risk_score),
                        },
                        correlation_id=act.correlation_id or act.action_id,
                        severity="high" if act.status == ActionStatus.DENIED else "info",
                        tenant_id=act.tenant_id,
                        agent_ids=[act.agent_id],
                    )
                )
            if act.executed_at and act.executed_at >= (act.evaluated_at or act.created_at):
                events.append(
                    IncidentTimelineEvent(
                        event_id=f"{act.action_id}-exec",
                        event_type=TimelineEventType.ACTION_EXECUTED,
                        timestamp=act.executed_at,
                        actor=act.agent_id,
                        description=f"Action {act.tool} on {act.resource} executed",
                        details={
                            "action_id": act.action_id,
                            "tool": act.tool,
                            "resource": act.resource,
                        },
                        correlation_id=act.correlation_id or act.action_id,
                        severity="info",
                        tenant_id=act.tenant_id,
                        agent_ids=[act.agent_id],
                    )
                )

        containment_events, _ = await self._containment_repo.list_by_agent(
            tenant_id, incident_id, limit=limit, offset=offset
        )
        for ce in containment_events:
            events.append(
                IncidentTimelineEvent(
                    event_id=ce.containment_id,
                    event_type=TimelineEventType.CONTAINMENT_INITIATED,
                    timestamp=ce.created_at,
                    actor=ce.initiated_by,
                    description=(
                        f"Containment initiated for {ce.target_agent_id} "
                        f"mode={ce.mode.value}"
                    ),
                    details={
                        "containment_id": ce.containment_id,
                        "mode": ce.mode.value,
                        "status": ce.status.value,
                    },
                    correlation_id=ce.containment_id,
                    severity="critical",
                    tenant_id=ce.tenant_id,
                    agent_ids=ce.affected_agent_ids,
                )
            )
            if ce.completed_at:
                events.append(
                    IncidentTimelineEvent(
                        event_id=f"{ce.containment_id}-completed",
                        event_type=TimelineEventType.CONTAINMENT_COMPLETED,
                        timestamp=ce.completed_at,
                        actor=ce.initiated_by,
                        description=f"Containment {ce.containment_id} completed",
                        details={"status": ce.status.value},
                        correlation_id=ce.containment_id,
                        severity="high",
                        tenant_id=ce.tenant_id,
                        agent_ids=ce.affected_agent_ids,
                    )
                )

        recovery_plans, rp_total = await self._recovery_repo.list_by_incident(
            tenant_id, incident_id, limit=limit, offset=offset
        )
        for rp in recovery_plans:
            events.append(
                IncidentTimelineEvent(
                    event_id=rp.plan_id,
                    event_type=TimelineEventType.RECOVERY_PLAN_CREATED,
                    timestamp=rp.created_at,
                    actor=rp.approved_by or "system",
                    description=f"Recovery plan {rp.plan_id} created",
                    details={
                        "outcome": rp.outcome.value,
                        "status": rp.status.value,
                    },
                    correlation_id=rp.plan_id,
                    severity="info",
                    tenant_id=rp.tenant_id,
                    agent_ids=[],
                )
            )
            if rp.status == RecoveryStatus.SIMULATED:
                events.append(
                    IncidentTimelineEvent(
                        event_id=f"{rp.plan_id}-simulated",
                        event_type=TimelineEventType.RECOVERY_PLAN_SIMULATED,
                        timestamp=rp.updated_at,
                        actor="system",
                        description=f"Recovery plan {rp.plan_id} simulated",
                        details={"outcome": rp.outcome.value},
                        correlation_id=rp.plan_id,
                        severity="info",
                        tenant_id=rp.tenant_id,
                        agent_ids=[],
                    )
                )
            if rp.status == RecoveryStatus.APPROVED and rp.approved_by:
                events.append(
                    IncidentTimelineEvent(
                        event_id=f"{rp.plan_id}-approved",
                        event_type=TimelineEventType.RECOVERY_PLAN_APPROVED,
                        timestamp=rp.updated_at,
                        actor=rp.approved_by,
                        description=f"Recovery plan {rp.plan_id} approved by {rp.approved_by}",
                        details={"approved_by": rp.approved_by},
                        correlation_id=rp.plan_id,
                        severity="high",
                        tenant_id=rp.tenant_id,
                        agent_ids=[],
                    )
                )
            if rp.executed_at:
                events.append(
                    IncidentTimelineEvent(
                        event_id=f"{rp.plan_id}-executed",
                        event_type=TimelineEventType.RECOVERY_PLAN_EXECUTED,
                        timestamp=rp.executed_at,
                        actor=rp.executed_by or "system",
                        description=f"Recovery plan {rp.plan_id} executed",
                        details={"executed_by": rp.executed_by or "system"},
                        correlation_id=rp.plan_id,
                        severity="high",
                        tenant_id=rp.tenant_id,
                        agent_ids=[],
                    )
                )

        events.sort(key=lambda e: e.timestamp)
        return events


def _format_event(event: IncidentTimelineEvent) -> dict[str, Any]:
    """Convert a timeline event to a serialisable dict."""
    return {
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "timestamp": event.timestamp.isoformat(),
        "actor": event.actor,
        "description": event.description,
        "severity": event.severity,
        "details": event.details,
        "correlation_id": event.correlation_id,
        "tenant_id": event.tenant_id,
        "agent_ids": event.agent_ids,
    }
