"""Phase 18: Cascade containment security unit tests.

Tests verify that containment operations correctly quarantine agents,
propagate to children, revoke active grants, respect dry-run mode,
and compute accurate blast radius scores.
"""

from __future__ import annotations

import pytest

from app.domain.entities.agent import Agent, AgentStatus, AgentType, RiskClassification
from app.domain.entities.authority_grant import AuthorityGrant, AuthorityScope, AuthorityStatus
from app.domain.entities.containment_event import (
    ContainmentEvent,
    ContainmentMode,
    ContainmentStatus,
)
from app.domain.services.cascade_containment_service import CascadeContainmentService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent(
    agent_id: str,
    tenant_id: str = "test-tenant",
    parent_agent_id: str | None = None,
    status: AgentStatus = AgentStatus.ACTIVE,
    risk: RiskClassification = RiskClassification.MEDIUM,
) -> Agent:
    return Agent(
        agent_id=agent_id,
        tenant_id=tenant_id,
        name=agent_id,
        description="",
        agent_type=AgentType.SERVICE_AGENT,
        status=status,
        risk_classification=risk,
        parent_agent_id=parent_agent_id,
    )


def _make_grant(
    grant_id: str,
    tenant_id: str = "test-tenant",
    grantee_agent_id: str = "target",
    status: AuthorityStatus = AuthorityStatus.ACTIVE,
    scope: AuthorityScope = AuthorityScope.READ,
    delegation_depth: int = 0,
) -> AuthorityGrant:
    return AuthorityGrant(
        grant_id=grant_id,
        tenant_id=tenant_id,
        grantor_agent_id="grantor",
        grantee_agent_id=grantee_agent_id,
        scope=scope,
        resource="res",
        status=status,
        delegation_depth=delegation_depth,
    )


class MockAgentRepo:
    def __init__(self, agents: list[Agent]) -> None:
        self._agents = {a.agent_id: a for a in agents}
        self._statuses: dict[str, AgentStatus] = {}

    async def get_by_agent_id(self, tenant_id: str, agent_id: str) -> Agent | None:
        agent = self._agents.get(agent_id)
        if agent and agent.tenant_id == tenant_id:
            if agent_id in self._statuses:
                agent = Agent(
                    agent_id=agent.agent_id,
                    tenant_id=agent.tenant_id,
                    name=agent.name,
                    description=agent.description,
                    agent_type=agent.agent_type,
                    status=self._statuses[agent_id],
                    trust_level=agent.trust_level,
                    model_provider=agent.model_provider,
                    model_name=agent.model_name,
                    risk_classification=agent.risk_classification,
                    expires_at=agent.expires_at,
                    last_activity_at=agent.last_activity_at,
                    connected_tools=agent.connected_tools,
                    metadata=agent.metadata,
                    parent_agent_id=agent.parent_agent_id,
                )
            return agent
        return None

    async def list_by_tenant(self, tenant_id: str, **kwargs: object) -> tuple[list[Agent], int]:
        agents = [a for a in self._agents.values() if a.tenant_id == tenant_id]
        return agents, len(agents)

    async def update_status(
        self, tenant_id: str, agent_id: str, status: AgentStatus
    ) -> Agent | None:
        agent = await self.get_by_agent_id(tenant_id, agent_id)
        if agent is None:
            return None
        self._statuses[agent_id] = status
        return await self.get_by_agent_id(tenant_id, agent_id)

    async def save(self, agent: Agent) -> Agent:
        self._agents[agent.agent_id] = agent
        return agent

    async def delete(self, tenant_id: str, agent_id: str) -> bool:
        if agent_id in self._agents:
            del self._agents[agent_id]
            return True
        return False

    async def exists(self, tenant_id: str, agent_id: str) -> bool:
        return agent_id in self._agents


class MockGrantRepo:
    def __init__(self, grants: list[AuthorityGrant]) -> None:
        self._grants = {g.grant_id: g for g in grants}
        self._statuses: dict[str, AuthorityStatus] = {}

    async def get_by_grant_id(self, tenant_id: str, grant_id: str) -> AuthorityGrant | None:
        grant = self._grants.get(grant_id)
        if grant and grant.tenant_id == tenant_id:
            if grant_id in self._statuses:
                grant = AuthorityGrant(
                    grant_id=grant.grant_id,
                    tenant_id=grant.tenant_id,
                    grantor_agent_id=grant.grantor_agent_id,
                    grantee_agent_id=grant.grantee_agent_id,
                    scope=grant.scope,
                    resource=grant.resource,
                    conditions=grant.conditions,
                    expires_at=grant.expires_at,
                    delegation_depth=grant.delegation_depth,
                    parent_authority_id=grant.parent_authority_id,
                    root_authority_id=grant.root_authority_id,
                    status=self._statuses[grant_id],
                    revoked_at=grant.revoked_at,
                    revoked_by=grant.revoked_by,
                    metadata=grant.metadata,
                )
            return grant
        return None

    async def list_by_grantee(
        self, tenant_id: str, grantee_agent_id: str, **kwargs: object
    ) -> tuple[list[AuthorityGrant], int]:
        filtered = [
            g for g in self._grants.values()
            if g.tenant_id == tenant_id and g.grantee_agent_id == grantee_agent_id
        ]
        return filtered, len(filtered)

    async def list_by_grantor(
        self, tenant_id: str, grantor_agent_id: str, **kwargs: object
    ) -> tuple[list[AuthorityGrant], int]:
        filtered = [
            g for g in self._grants.values()
            if g.tenant_id == tenant_id and g.grantor_agent_id == grantor_agent_id
        ]
        return filtered, len(filtered)

    async def revoke(self, tenant_id: str, grant_id: str, revoked_by: str) -> AuthorityGrant | None:
        grant = await self.get_by_grant_id(tenant_id, grant_id)
        if grant is None:
            return None
        self._statuses[grant_id] = AuthorityStatus.REVOKED
        return await self.get_by_grant_id(tenant_id, grant_id)

    async def save(self, grant: AuthorityGrant) -> AuthorityGrant:
        self._grants[grant.grant_id] = grant
        return grant


class MockContainmentRepo:
    def __init__(self) -> None:
        self._events: dict[str, ContainmentEvent] = {}

    async def get_by_containment_id(
        self, tenant_id: str, containment_id: str
    ) -> ContainmentEvent | None:
        return self._events.get(containment_id)

    async def list_by_agent(
        self, tenant_id: str, target_agent_id: str, **kwargs: object
    ) -> tuple[list[ContainmentEvent], int]:
        filtered = [
            e for e in self._events.values()
            if e.tenant_id == tenant_id and e.target_agent_id == target_agent_id
        ]
        return filtered, len(filtered)

    async def save(self, event: ContainmentEvent) -> ContainmentEvent:
        self._events[event.containment_id] = event
        return event

    async def update_status(
        self,
        tenant_id: str,
        containment_id: str,
        status: ContainmentStatus,
        result_details: dict[str, str] | None = None,
    ) -> ContainmentEvent | None:
        event = self._events.get(containment_id)
        if event is None:
            return None
        event = ContainmentEvent(
            containment_id=event.containment_id,
            tenant_id=event.tenant_id,
            target_agent_id=event.target_agent_id,
            target_authority_id=event.target_authority_id,
            mode=event.mode,
            status=status,
            initiated_by=event.initiated_by,
            authorized_by=event.authorized_by,
            reason=event.reason,
            affected_agent_ids=event.affected_agent_ids,
            affected_authority_ids=event.affected_authority_ids,
            dry_run=event.dry_run,
            result_details=result_details or event.result_details,
            created_at=event.created_at,
            completed_at=event.completed_at,
        )
        self._events[containment_id] = event
        return event


def _make_service(agents: list[Agent], grants: list[AuthorityGrant]) -> CascadeContainmentService:
    agent_repo = MockAgentRepo(agents)
    grant_repo = MockGrantRepo(grants)
    containment_repo = MockContainmentRepo()
    return CascadeContainmentService(agent_repo, grant_repo, containment_repo)


# ---------------------------------------------------------------------------
# Containment of quarantined agent doesn't double-quarantine
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quarantined_agent_containment_no_double_quarantine() -> None:
    agent = _make_agent("agent-q", status=AgentStatus.QUARANTINED)
    service = _make_service([agent], [])

    event = await service.contain_authority_tree(
        tenant_id="test-tenant",
        target_agent_id="agent-q",
        mode=ContainmentMode.QUARANTINE,
        initiated_by="tester",
        authorized_by="tester",
        reason="already quarantined",
    )
    assert event.status == ContainmentStatus.COMPLETED
    assert event.target_agent_id == "agent-q"


# ---------------------------------------------------------------------------
# Containment propagates to child agents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_containment_propagates_to_child_agents() -> None:
    parent = _make_agent("parent-agent")
    child = _make_agent("child-agent", parent_agent_id="parent-agent")
    service = _make_service([parent, child], [])

    event = await service.contain_authority_tree(
        tenant_id="test-tenant",
        target_agent_id="parent-agent",
        mode=ContainmentMode.QUARANTINE,
        initiated_by="tester",
        authorized_by="tester",
        reason="propagate test",
    )
    assert "child-agent" in event.affected_agent_ids


# ---------------------------------------------------------------------------
# Containment revokes all active grants
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_containment_revokes_active_grants() -> None:
    agent = _make_agent("agent-grants")
    grants = [
        _make_grant("grant-1", grantee_agent_id="agent-grants"),
        _make_grant("grant-2", grantee_agent_id="agent-grants"),
        _make_grant("grant-3", grantee_agent_id="agent-grants", status=AuthorityStatus.REVOKED),
    ]
    service = _make_service([agent], grants)

    event = await service.contain_authority_tree(
        tenant_id="test-tenant",
        target_agent_id="agent-grants",
        mode=ContainmentMode.QUARANTINE,
        initiated_by="tester",
        authorized_by="tester",
        reason="revoke grants test",
    )
    assert "grant-1" in event.affected_authority_ids
    assert "grant-2" in event.affected_authority_ids
    assert "grant-3" not in event.affected_authority_ids


# ---------------------------------------------------------------------------
# Dry-run doesn't modify state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_does_not_modify_state() -> None:
    agent = _make_agent("agent-dry")
    grants = [_make_grant("grant-dry", grantee_agent_id="agent-dry")]
    service = _make_service([agent], grants)

    event = await service.contain_authority_tree(
        tenant_id="test-tenant",
        target_agent_id="agent-dry",
        mode=ContainmentMode.QUARANTINE,
        initiated_by="tester",
        authorized_by="tester",
        reason="dry run test",
        dry_run=True,
    )
    assert event.dry_run is True
    assert event.status == ContainmentStatus.PENDING
    assert len(event.affected_agent_ids) == 0
    assert len(event.affected_authority_ids) == 0


# ---------------------------------------------------------------------------
# Blast radius calculation accuracy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blast_radius_calculation_accuracy() -> None:
    agent = _make_agent("blast-agent", risk=RiskClassification.HIGH)
    child = _make_agent(
        "blast-child", parent_agent_id="blast-agent", risk=RiskClassification.CRITICAL,
    )
    grants = [
        _make_grant("bg-1", grantee_agent_id="blast-agent", scope=AuthorityScope.ADMIN),
        _make_grant("bg-2", grantee_agent_id="blast-agent", scope=AuthorityScope.READ),
        _make_grant(
            "bg-3", grantee_agent_id="blast-agent", scope=AuthorityScope.EXECUTE,
            delegation_depth=5,
        ),
    ]
    service = _make_service([agent, child], grants)

    result = await service.get_blast_radius("test-tenant", "blast-agent")
    assert result["agent_id"] == "blast-agent"
    assert result["direct_authorities"] == 3
    assert "blast-child" in result["child_agents"]
    assert result["child_agents_count"] == 1
    assert 0.0 <= result["blast_radius_score"] <= 1.0
