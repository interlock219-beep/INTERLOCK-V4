from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.entities.agent import (
    Agent,
    AgentType,
    RegistrationMethod,
    TrustLevel,
)
from app.domain.entities.discovery_event import (
    DiscoverySource,
    DiscoveryStatus,
)
from app.domain.services.discovery_service import DiscoveryService


class StubAgentRepo:
    def __init__(self, existing=None, saved=None) -> None:
        self._existing = existing
        self._saved = saved or []

    async def get_by_agent_id(self, tenant_id, agent_id):
        return self._existing

    async def save(self, agent):
        self._saved.append(agent)
        return agent

    async def list_by_tenant(self, tenant_id, *, limit, offset):
        return [], 0


class StubDiscoveryRepo:
    def __init__(self) -> None:
        self._saved = []

    async def save(self, event):
        self._saved.append(event)
        return event


@pytest.mark.asyncio
async def test_register_agent_new_agent():
    agent_repo = StubAgentRepo(existing=None)
    disc_repo = StubDiscoveryRepo()
    service = DiscoveryService(agent_repo, disc_repo)
    agent, event = await service.register_agent(
        "tenant-1", "agent-1", "Test", DiscoverySource.MANUAL
    )
    assert agent.agent_id == "agent-1"
    assert agent.registration_method == RegistrationMethod.MANUAL
    assert len(disc_repo._saved) == 1


@pytest.mark.asyncio
async def test_register_agent_existing_agent():
    existing = Agent(
        agent_id="agent-1",
        tenant_id="tenant-1",
        name="Existing",
        description="",
        owner_user_id=None,
        agent_type=AgentType.UNKNOWN,
        trust_level=TrustLevel.DISCOVERED,
        registration_method=RegistrationMethod.MANUAL,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    agent_repo = StubAgentRepo(existing=existing)
    disc_repo = StubDiscoveryRepo()
    service = DiscoveryService(agent_repo, disc_repo)
    agent, event = await service.register_agent(
        "tenant-1", "agent-1", "New Name", DiscoverySource.API
    )
    assert agent.agent_id == "agent-1"
    assert agent.name == "Existing"
    assert len(agent_repo._saved) == 0


@pytest.mark.asyncio
async def test_register_agent_unknown_source():
    agent_repo = StubAgentRepo(existing=None)
    disc_repo = StubDiscoveryRepo()
    service = DiscoveryService(agent_repo, disc_repo)
    agent, event = await service.register_agent(
        "tenant-1", "agent-1", "Test", DiscoverySource.CONNECTOR
    )
    assert agent.registration_method == RegistrationMethod.AUTO_DISCOVERED


@pytest.mark.asyncio
async def test_ingest_discovery_event_new():
    agent_repo = StubAgentRepo(existing=None)
    disc_repo = StubDiscoveryRepo()
    service = DiscoveryService(agent_repo, disc_repo)
    event = await service.ingest_discovery_event(
        "tenant-1",
        DiscoverySource.API,
        "resource",
        "res-1",
        finding_severity="high",
    )
    assert event.discovery_status == DiscoveryStatus.DISCOVERED
    assert event.finding_severity == "high"


@pytest.mark.asyncio
async def test_ingest_discovery_event_with_agent():
    agent = Agent(
        agent_id="agent-1",
        tenant_id="tenant-1",
        name="Test",
        description="",
        owner_user_id=None,
        agent_type=AgentType.UNKNOWN,
        trust_level=TrustLevel.VERIFIED,
        registration_method=RegistrationMethod.API,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    agent_repo = StubAgentRepo(existing=agent)
    disc_repo = StubDiscoveryRepo()
    service = DiscoveryService(agent_repo, disc_repo)
    event = await service.ingest_discovery_event(
        "tenant-1",
        DiscoverySource.API,
        "agent",
        "agent-1",
        agent_id="agent-1",
    )
    assert event.discovery_status == DiscoveryStatus.VERIFIED


@pytest.mark.asyncio
async def test_ingest_discovery_event_non_agent():
    agent_repo = StubAgentRepo(existing=None)
    disc_repo = StubDiscoveryRepo()
    service = DiscoveryService(agent_repo, disc_repo)
    event = await service.ingest_discovery_event(
        "tenant-1",
        DiscoverySource.API,
        "resource",
        "res-1",
    )
    assert event.discovery_status == DiscoveryStatus.DISCOVERED
