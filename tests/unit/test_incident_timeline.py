from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.entities.containment_event import (
    ContainmentEvent,
    ContainmentMode,
    ContainmentStatus,
)
from app.domain.entities.discovery_event import (
    DiscoveryEvent,
    DiscoverySource,
    DiscoveryStatus,
)
from app.domain.entities.incident_timeline_event import (
    IncidentTimelineEvent,
    TimelineEventType,
)
from app.domain.entities.protected_action import (
    ActionStatus,
    ProtectedAction,
)
from app.domain.entities.recovery_plan import (
    RecoveryOutcome,
    RecoveryPlan,
    RecoveryStatus,
)
from app.domain.services.incident_timeline_service import (
    IncidentTimelineService,
    _format_event,
)


class StubDiscoveryRepo:
    def __init__(self, events):
        self._events = events

    async def list_by_agent(self, tenant_id, agent_id, *, limit, offset):
        return self._events, len(self._events)


class StubActionRepo:
    def __init__(self, actions):
        self._actions = actions

    async def list_by_agent(self, tenant_id, agent_id, *, limit, offset):
        return self._actions, len(self._actions)


class StubContainmentRepo:
    def __init__(self, events):
        self._events = events

    async def list_by_agent(self, tenant_id, agent_id, *, limit, offset):
        return self._events, len(self._events)


class StubRecoveryRepo:
    def __init__(self, plans):
        self._plans = plans

    async def list_by_incident(self, tenant_id, incident_id, *, limit, offset):
        return self._plans, len(self._plans)


def make_discovery_event(**kwargs):
    defaults = {
        "discovery_id": f"disc-{uuid4().hex[:12]}",
        "tenant_id": "tenant-1",
        "source": DiscoverySource.API,
        "discovery_status": DiscoveryStatus.DISCOVERED,
        "agent_id": "agent-1",
        "resource_type": "agent",
        "resource_id": "agent-1",
        "resource_metadata": {},
        "finding_severity": "info",
        "finding_message": "test",
        "created_at": datetime.now(UTC),
    }
    defaults.update(kwargs)
    return DiscoveryEvent(**defaults)


def make_action(**kwargs):
    defaults = {
        "action_id": f"act-{uuid4().hex[:12]}",
        "tenant_id": "tenant-1",
        "agent_id": "agent-1",
        "actor_user_id": None,
        "authority_grant_id": None,
        "tool": "tool",
        "resource": "res",
        "action_type": "read",
        "status": ActionStatus.PENDING,
        "decision_reason": "ok",
        "risk_score": 0.1,
        "created_at": datetime.now(UTC),
        "evaluated_at": None,
        "executed_at": None,
        "parent_action_id": None,
        "correlation_id": None,
        "before_state_ref": None,
        "after_state_ref": None,
    }
    defaults.update(kwargs)
    return ProtectedAction(**defaults)


def make_containment(**kwargs):
    defaults = {
        "containment_id": f"cnt-{uuid4().hex[:12]}",
        "tenant_id": "tenant-1",
        "target_agent_id": "agent-1",
        "target_authority_id": None,
        "mode": ContainmentMode.QUARANTINE,
        "status": ContainmentStatus.PENDING,
        "initiated_by": "system",
        "authorized_by": "admin",
        "reason": "test",
        "affected_agent_ids": [],
        "affected_authority_ids": [],
        "affected_session_ids": [],
        "affected_token_ids": [],
        "affected_action_ids": [],
        "dry_run": False,
        "result_details": {},
        "created_at": datetime.now(UTC),
        "completed_at": None,
    }
    defaults.update(kwargs)
    return ContainmentEvent(**defaults)


def make_recovery_plan(**kwargs):
    defaults = {
        "plan_id": f"plan-{uuid4().hex[:12]}",
        "tenant_id": "tenant-1",
        "incident_id": "inc-1",
        "incident_action_id": "act-1",
        "status": RecoveryStatus.DRAFT,
        "outcome": RecoveryOutcome.UNKNOWN,
        "approved_by": None,
        "executed_by": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "executed_at": None,
    }
    defaults.update(kwargs)
    return RecoveryPlan(**defaults)


@pytest.mark.asyncio
async def test_get_timeline_empty():
    service = IncidentTimelineService(
        StubDiscoveryRepo([]),
        StubActionRepo([]),
        StubContainmentRepo([]),
        StubRecoveryRepo([]),
    )
    events = await service.get_timeline("tenant-1", "agent-1")
    assert events == []


@pytest.mark.asyncio
async def test_get_timeline_with_discovery():
    disc = make_discovery_event()
    service = IncidentTimelineService(
        StubDiscoveryRepo([disc]),
        StubActionRepo([]),
        StubContainmentRepo([]),
        StubRecoveryRepo([]),
    )
    events = await service.get_timeline("tenant-1", "agent-1")
    assert len(events) == 1
    assert events[0].event_type == TimelineEventType.DISCOVERY


@pytest.mark.asyncio
async def test_get_timeline_with_action_evaluated_and_executed():
    created = datetime.now(UTC)
    evaluated = created.replace(microsecond=created.microsecond + 1)
    action = make_action(
        evaluated_at=evaluated,
        executed_at=evaluated,
        status=ActionStatus.DENIED,
        created_at=created,
    )
    service = IncidentTimelineService(
        StubDiscoveryRepo([]),
        StubActionRepo([action]),
        StubContainmentRepo([]),
        StubRecoveryRepo([]),
    )
    events = await service.get_timeline("tenant-1", "agent-1")
    assert len(events) == 2
    assert events[0].event_type == TimelineEventType.ACTION_EVALUATED
    assert events[1].event_type == TimelineEventType.ACTION_EXECUTED


@pytest.mark.asyncio
async def test_get_timeline_with_containment():
    cnt = make_containment(completed_at=datetime.now(UTC))
    service = IncidentTimelineService(
        StubDiscoveryRepo([]),
        StubActionRepo([]),
        StubContainmentRepo([cnt]),
        StubRecoveryRepo([]),
    )
    events = await service.get_timeline("tenant-1", "agent-1")
    assert len(events) == 2


@pytest.mark.asyncio
async def test_get_timeline_with_recovery_plan():
    plan = make_recovery_plan(
        status=RecoveryStatus.SIMULATED,
        approved_by="admin",
        executed_at=datetime.now(UTC),
    )
    service = IncidentTimelineService(
        StubDiscoveryRepo([]),
        StubActionRepo([]),
        StubContainmentRepo([]),
        StubRecoveryRepo([plan]),
    )
    events = await service.get_timeline("tenant-1", "agent-1")
    assert len(events) == 3


@pytest.mark.asyncio
async def test_format_event():
    event = IncidentTimelineEvent(
        event_id="evt-1",
        event_type=TimelineEventType.DISCOVERY,
        timestamp=datetime.now(UTC),
        actor="system",
        description="test",
        severity="info",
        details={},
        correlation_id="corr-1",
        tenant_id="tenant-1",
        agent_ids=["agent-1"],
    )
    result = _format_event(event)
    assert result["event_id"] == "evt-1"
    assert result["event_type"] == "discovery"
    assert "timestamp" in result
