from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.domain.entities.agent import Agent, AgentStatus, AgentType, TrustLevel, RiskClassification, AgentEnvironment, RegistrationMethod
from app.domain.entities.agent_session import AgentSession, AgentSessionStatus
from app.domain.entities.protected_action import ProtectedAction, ActionStatus
from app.domain.entities.surgical_recovery_types import Reversibility
from app.domain.services.identity_anomaly_detection import (
    AnomalyDetectionResult,
    AnomalySeverity,
    AnomalyType,
    IdentityAnomalyDetectionService,
)


def _make_agent(
    agent_id: str = "agent-001",
    tenant_id: str = "tenant-1",
    parent_agent_id: str | None = None,
    model_name: str | None = "gpt-4",
    agent_type: str = "user_agent",
    trust_level: str = "verified",
    status: str = "active",
    connected_tools: list[str] | None = None,
    metadata: dict | None = None,
    created_at: datetime | None = None,
) -> Agent:
    return Agent(
        agent_id=agent_id,
        tenant_id=tenant_id,
        name=f"Agent {agent_id}",
        description="",
        owner_user_id=UUID(int=1),
        parent_agent_id=parent_agent_id,
        agent_type=AgentType(agent_type),
        status=AgentStatus(status),
        trust_level=TrustLevel(trust_level),
        risk_classification=RiskClassification.MEDIUM,
        model_provider="openai",
        model_name=model_name,
        environment=AgentEnvironment.PRODUCTION,
        version="1.0",
        creator="system",
        registration_method=RegistrationMethod.MANUAL,
        root_human_sponsor="user-001",
        connected_tools=connected_tools or [],
        metadata=metadata or {},
        created_at=created_at or datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


class _StubAgentRepo:
    def __init__(self, agents: dict[str, Agent] | None = None) -> None:
        self._agents = agents or {}

    async def get_by_agent_id(self, tenant_id: str, agent_id: str) -> Agent | None:
        agent = self._agents.get(agent_id)
        if agent and agent.tenant_id == tenant_id:
            return agent
        return None

    async def get_by_agent_id_global(self, agent_id: str) -> Agent | None:
        return self._agents.get(agent_id)


class _StubSessionRepo:
    def __init__(self, sessions: list = None) -> None:
        self._sessions = sessions or []

    async def list_by_agent(
        self,
        tenant_id: str,
        agent_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list, int]:
        filtered = [
            s for s in self._sessions
            if s.tenant_id == tenant_id and s.agent_id == agent_id
        ]
        return filtered[offset:offset + limit], len(filtered)


class _StubActionRepo:
    def __init__(self, actions: list = None) -> None:
        self._actions = actions or []

    async def list_by_agent(
        self,
        tenant_id: str,
        agent_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list, int]:
        filtered = [
            a for a in self._actions
            if a.tenant_id == tenant_id and a.agent_id == agent_id
        ]
        return filtered[offset:offset + limit], len(filtered)


def _make_session(
    session_id: str = "session-001",
    tenant_id: str = "tenant-1",
    agent_id: str = "agent-001",
    started_at: datetime | None = None,
    location: dict | None = None,
) -> AgentSession:
    return AgentSession(
        session_id=session_id,
        tenant_id=tenant_id,
        agent_id=agent_id,
        started_at=started_at or datetime.now(UTC),
        ended_at=None,
        status=AgentSessionStatus.ACTIVE,
        correlation_id="corr-001",
        metadata={"location": location} if location else {},
    )


def _make_action(
    action_id: str = "action-001",
    tenant_id: str = "tenant-1",
    agent_id: str = "agent-001",
    action_type: str = "read",
    tool: str = "file_reader",
    resource: str = "/tmp/data.txt",
    created_at: datetime | None = None,
    executed_at: datetime | None = None,
) -> ProtectedAction:
    return ProtectedAction(
        action_id=action_id,
        tenant_id=tenant_id,
        actor_user_id=UUID(int=1),
        agent_id=agent_id,
        authority_grant_id="grant-001",
        tool=tool,
        resource=resource,
        action_type=action_type,
        reversibility=Reversibility.REVERSIBLE,
        status=ActionStatus.EXECUTED,
        created_at=created_at or datetime.now(UTC),
        executed_at=executed_at,
    )


@pytest.fixture
def service():
    agent_repo = _StubAgentRepo()
    session_repo = _StubSessionRepo()
    action_repo = _StubActionRepo()
    return IdentityAnomalyDetectionService(agent_repo, session_repo, action_repo)


@pytest.mark.asyncio
async def test_impossible_travel_detected(service):
    now = datetime.now(UTC)
    agent_repo = service._agent_repo
    agent_repo._agents["agent-001"] = _make_agent("agent-001")

    session_repo = service._session_repo
    session_repo._sessions = [
        _make_session(
            session_id="session-old",
            started_at=now - timedelta(hours=1),
            location={"latitude": 40.7128, "longitude": -74.0060},
        )
    ]

    svc = IdentityAnomalyDetectionService(
        agent_repository=agent_repo,
        session_repository=session_repo,
    )

    anomalies = await svc.detect_anomalies(
        tenant_id="tenant-1",
        agent_id="agent-001",
        current_location={"latitude": 35.6762, "longitude": 139.6503},
    )

    travel_anomalies = [a for a in anomalies if a.anomaly_type == AnomalyType.IMPOSSIBLE_TRAVEL]
    assert len(travel_anomalies) == 1
    result = travel_anomalies[0]
    assert result.severity == AnomalySeverity.CRITICAL
    assert "exceeding max speed" in result.explanation
    assert "distance_km" in result.evidence


@pytest.mark.asyncio
async def test_no_impossible_travel_when_close(service):
    now = datetime.now(UTC)
    agent_repo = service._agent_repo
    agent_repo._agents["agent-001"] = _make_agent("agent-001")

    session_repo = service._session_repo
    session_repo._sessions = [
        _make_session(
            session_id="session-old",
            started_at=now - timedelta(minutes=5),
            location={"latitude": 40.7128, "longitude": -74.0060},
        )
    ]

    svc = IdentityAnomalyDetectionService(
        agent_repository=agent_repo,
        session_repository=session_repo,
    )

    anomalies = await svc.detect_anomalies(
        tenant_id="tenant-1",
        agent_id="agent-001",
        current_location={"latitude": 40.7130, "longitude": -74.0065},
    )

    travel_anomalies = [a for a in anomalies if a.anomaly_type == AnomalyType.IMPOSSIBLE_TRAVEL]
    assert len(travel_anomalies) == 0


@pytest.mark.asyncio
async def test_impossible_delegation_parent_not_found(service):
    agent_repo = service._agent_repo
    agent_repo._agents["agent-002"] = _make_agent(
        "agent-002", parent_agent_id="nonexistent-parent"
    )

    anomalies = await service.detect_anomalies(
        tenant_id="tenant-1",
        agent_id="agent-002",
    )

    delegation_anomalies = [
        a for a in anomalies
        if a.anomaly_type == AnomalyType.IMPOSSIBLE_DELEGATION
    ]
    assert len(delegation_anomalies) == 1
    assert "non-existent parent" in delegation_anomalies[0].explanation


@pytest.mark.asyncio
async def test_impossible_delegation_cross_tenant(service):
    agent_repo = service._agent_repo
    agent_repo._agents["parent-001"] = _make_agent(
        "parent-001", tenant_id="tenant-1"
    )
    agent_repo._agents["child-001"] = _make_agent(
        "child-001", tenant_id="tenant-2", parent_agent_id="parent-001"
    )

    anomalies = await service.detect_anomalies(
        tenant_id="tenant-2",
        agent_id="child-001",
    )

    delegation_anomalies = [
        a for a in anomalies
        if a.anomaly_type == AnomalyType.IMPOSSIBLE_DELEGATION
    ]
    assert len(delegation_anomalies) == 1
    assert "different tenant" in delegation_anomalies[0].explanation


@pytest.mark.asyncio
async def test_impossible_delegation_valid(service):
    agent_repo = service._agent_repo
    agent_repo._agents["parent-001"] = _make_agent(
        "parent-001", tenant_id="tenant-1"
    )
    agent_repo._agents["child-001"] = _make_agent(
        "child-001", tenant_id="tenant-1", parent_agent_id="parent-001"
    )

    anomalies = await service.detect_anomalies(
        tenant_id="tenant-1",
        agent_id="child-001",
    )

    delegation_anomalies = [
        a for a in anomalies
        if a.anomaly_type == AnomalyType.IMPOSSIBLE_DELEGATION
    ]
    assert len(delegation_anomalies) == 0


@pytest.mark.asyncio
async def test_rapid_identity_switching_detection(service):
    action_repo = service._action_repo
    now = datetime.now(UTC)
    actions = [
        _make_action(
            action_id=f"action-{i}",
            created_at=now + timedelta(milliseconds=i * 100),
        )
        for i in range(5)
    ]
    action_repo._actions = actions

    anomalies = await service.detect_anomalies(
        tenant_id="tenant-1",
        agent_id="agent-001",
    )

    switching_anomalies = [
        a for a in anomalies
        if a.anomaly_type == AnomalyType.RAPID_IDENTITY_SWITCHING
    ]
    assert len(switching_anomalies) == 1
    assert "3 actions within" in switching_anomalies[0].explanation


@pytest.mark.asyncio
async def test_impossible_action_sequence_detection(service):
    action_repo = service._action_repo
    now = datetime.now(UTC)
    actions = [
        _make_action(
            action_id=f"action-{i}",
            created_at=now - timedelta(seconds=59 - i),
        )
        for i in range(120)
    ]
    action_repo._actions = actions

    anomalies = await service.detect_anomalies(
        tenant_id="tenant-1",
        agent_id="agent-001",
    )

    sequence_anomalies = [
        a for a in anomalies
        if a.anomaly_type == AnomalyType.IMPOSSIBLE_ACTION_SEQUENCE
    ]
    assert len(sequence_anomalies) == 1
    assert "exceeding limit" in sequence_anomalies[0].explanation


@pytest.mark.asyncio
async def test_unauthorized_child_creation_detection(service):
    action_repo = service._action_repo
    actions = [
        _make_action(
            action_id=f"create-{i}",
            action_type="create_agent",
            executed_at=datetime.now(UTC),
        )
        for i in range(5)
    ]
    action_repo._actions = actions

    anomalies = await service.detect_anomalies(
        tenant_id="tenant-1",
        agent_id="agent-001",
    )

    creation_anomalies = [
        a for a in anomalies
        if a.anomaly_type == AnomalyType.UNAUTHORIZED_CHILD_CREATION
    ]
    assert len(creation_anomalies) == 1
    assert "exceeding limit" in creation_anomalies[0].explanation


@pytest.mark.asyncio
async def test_suspicious_session_pattern_detection(service):
    now = datetime.now(UTC)
    agent_repo = service._agent_repo
    agent_repo._agents["agent-001"] = _make_agent("agent-001")

    session_repo = service._session_repo
    session_repo._sessions = [
        _make_session(
            session_id=f"session-{i}",
            started_at=now - timedelta(seconds=10 - i),
        )
        for i in range(7)
    ]

    svc = IdentityAnomalyDetectionService(
        agent_repository=agent_repo,
        session_repository=session_repo,
    )

    anomalies = await svc.detect_anomalies(
        tenant_id="tenant-1",
        agent_id="agent-001",
    )

    session_anomalies = [
        a for a in anomalies
        if a.anomaly_type == AnomalyType.SUSPICIOUS_SESSION_PATTERN
    ]
    assert len(session_anomalies) == 1
    assert "sessions in under 60 seconds" in session_anomalies[0].explanation


@pytest.mark.asyncio
async def test_anomalous_resource_access_destructive(service):
    anomalies = await service.detect_anomalies(
        tenant_id="tenant-1",
        agent_id="agent-001",
        current_action={
            "resource": "/prod/database.db",
            "tool": "shell",
            "action_type": "rm",
        },
    )

    access_anomalies = [
        a for a in anomalies
        if a.anomaly_type == AnomalyType.ANOMALOUS_RESOURCE_ACCESS
    ]
    assert len(access_anomalies) == 1
    assert "destructive action" in access_anomalies[0].explanation


@pytest.mark.asyncio
async def test_no_anomalies_for_normal_agent(service):
    agent_repo = service._agent_repo
    agent_repo._agents["agent-001"] = _make_agent("agent-001")

    now = datetime.now(UTC)
    session_repo = service._session_repo
    session_repo._sessions = [
        _make_session(
            session_id="session-old",
            started_at=now - timedelta(hours=2),
            location={"latitude": 40.7128, "longitude": -74.0060},
        )
    ]

    action_repo = service._action_repo
    action_repo._actions = [
        _make_action(
            action_id="action-001",
            created_at=now - timedelta(minutes=5),
            action_type="read",
        )
    ]

    anomalies = await service.detect_anomalies(
        tenant_id="tenant-1",
        agent_id="agent-001",
        current_location={"latitude": 40.7130, "longitude": -74.0065},
        current_action={
            "resource": "/tmp/data.txt",
            "tool": "file_reader",
            "action_type": "read",
        },
    )

    assert len(anomalies) == 0


@pytest.mark.asyncio
async def test_identity_impersonation_mismatched_model():
    agent_repo = _StubAgentRepo()
    session_repo = _StubSessionRepo()
    action_repo = _StubActionRepo()

    agent_repo._agents["parent"] = _make_agent(
        "parent", model_name="gpt-4", agent_type="user_agent"
    )
    agent_repo._agents["child"] = _make_agent(
        "child", model_name="claude-3", agent_type="sub_agent",
        parent_agent_id="parent"
    )

    svc = IdentityAnomalyDetectionService(agent_repo, session_repo, action_repo)

    anomalies = await svc.detect_anomalies(
        tenant_id="tenant-1",
        agent_id="child",
    )

    impersonation = [
        a for a in anomalies
        if a.anomaly_type == AnomalyType.IDENTITY_IMPERSONATION
    ]
    assert len(impersonation) == 1
    assert "mismatched identity" in impersonation[0].explanation


def test_configure_detection_thresholds(service):
    service.configure_detection_thresholds(
        max_travel_speed_kmh=500.0,
        max_actions_per_minute=50,
        max_child_creations=2,
        impossible_time_window_seconds=5,
        behavioral_deviation_threshold=3.0,
        geographic_anomaly_threshold=0.9,
    )
    assert service._max_travel_speed_kmh == 500.0
    assert service._max_actions_per_minute == 50
    assert service._max_child_creations_per_session == 2
    assert service._impossible_time_window_seconds == 5
    assert service._behavioral_deviation_threshold == 3.0
    assert service._geographic_anomaly_threshold == 0.9


def test_anomaly_detection_result_fields():
    result = AnomalyDetectionResult(
        anomaly_type=AnomalyType.IMPOSSIBLE_TRAVEL,
        severity=AnomalySeverity.CRITICAL,
        agent_id="agent-001",
        explanation="Test anomaly",
        confidence=0.95,
        evidence={"key": "value"},
    )
    assert result.anomaly_type == AnomalyType.IMPOSSIBLE_TRAVEL
    assert result.severity == AnomalySeverity.CRITICAL
    assert result.agent_id == "agent-001"
    assert result.explanation == "Test anomaly"
    assert result.confidence == 0.95
    assert result.evidence == {"key": "value"}
    assert result.detected_at.tzinfo is not None
