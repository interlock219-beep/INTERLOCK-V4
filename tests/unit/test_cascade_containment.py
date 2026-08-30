from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from app.domain.entities.agent import (
    Agent,
    AgentType,
    TrustLevel,
)
from app.domain.entities.authority_grant import (
    AuthorityGrant,
    AuthorityScope,
    AuthorityStatus,
)
from app.domain.entities.containment_event import (
    ContainmentMode,
    ContainmentStatus,
)
from app.domain.entities.execution_token import (
    ExecutionToken,
    TokenStatus,
)
from app.domain.entities.protected_action import (
    ActionStatus,
    ProtectedAction,
)
from app.domain.services.cascade_containment_service import CascadeContainmentService


class StubAgentRepo:
    def __init__(self, agent, children=None):
        self._agent = agent
        self._children = children or []
        self.status_updates = []

    async def get_by_agent_id(self, tenant_id, agent_id):
        return self._agent

    async def update_status(self, tenant_id, agent_id, status):
        self.status_updates.append((agent_id, status))

    async def list_by_tenant(self, tenant_id, *, limit, offset):
        return self._children, len(self._children)


class StubGrantRepo:
    def __init__(self, grants):
        self._grants = grants
        self.revoked = []

    async def list_by_grantee(self, tenant_id, grantee_id, *, limit, offset):
        result = [g for g in self._grants if g.grantee_agent_id == grantee_id]
        return result, len(result)

    async def revoke(self, tenant_id, grant_id, initiated_by):
        self.revoked.append(grant_id)


class StubContainmentRepo:
    def __init__(self) -> None:
        self._saved = []

    async def save(self, event):
        self._saved.append(event)
        return event


class StubTokenRepo:
    def __init__(self, tokens):
        self._tokens = tokens
        self.revoked = []

    async def list_by_agent(self, tenant_id, agent_id, *, status, limit, offset):
        result = [t for t in self._tokens if t.agent_id == agent_id and t.status == status]
        return result, len(result)

    async def revoke(self, tenant_id, token_id):
        self.revoked.append(token_id)


class StubActionRepo:
    def __init__(self, actions):
        self._actions = actions
        self.updated = []

    async def list_by_agent(self, tenant_id, agent_id, *, limit, offset):
        result = [a for a in self._actions if a.agent_id == agent_id]
        return result, len(result)

    async def update_status(self, tenant_id, action_id, status):
        self.updated.append((action_id, status))


def make_agent(agent_id, owner_user_id=None, parent_agent_id=None):
    return Agent(
        agent_id=agent_id,
        tenant_id="tenant-1",
        name=agent_id,
        description="",
        owner_user_id=owner_user_id,
        parent_agent_id=parent_agent_id,
        agent_type=AgentType.UNKNOWN,
        trust_level=TrustLevel.DISCOVERED,
        registration_method=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def make_grant(grant_id, grantee_id, status=AuthorityStatus.ACTIVE):
    return AuthorityGrant(
        grant_id=grant_id,
        tenant_id="tenant-1",
        grantor_agent_id="grantor-1",
        grantee_agent_id=grantee_id,
        resource="resource",
        scope=AuthorityScope.READ,
        status=status,
        delegation_depth=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_contain_authority_tree_dry_run():
    agent = make_agent("agent-1")
    agent_repo = StubAgentRepo(agent)
    grant_repo = StubGrantRepo([])
    containment_repo = StubContainmentRepo()
    service = CascadeContainmentService(agent_repo, grant_repo, containment_repo)
    event = await service.contain_authority_tree(
        "tenant-1", "agent-1", ContainmentMode.QUARANTINE,
        "system", "admin", dry_run=True,
    )
    assert event.status == ContainmentStatus.PENDING
    assert event.dry_run is True
    assert len(containment_repo._saved) == 1


@pytest.mark.asyncio
async def test_contain_authority_tree_with_grants_and_children():
    agent = make_agent("agent-1")
    child = make_agent("agent-2", owner_user_id="user-1", parent_agent_id="agent-1")
    grant = make_grant("grant-1", "agent-1")
    child_grant = make_grant("grant-2", "agent-2")
    agent_repo = StubAgentRepo(agent, children=[child])
    grant_repo = StubGrantRepo([grant, child_grant])
    containment_repo = StubContainmentRepo()
    service = CascadeContainmentService(agent_repo, grant_repo, containment_repo)
    event = await service.contain_authority_tree(
        "tenant-1", "agent-1", ContainmentMode.QUARANTINE,
        "system", "admin",
    )
    assert "agent-1" in event.affected_agent_ids
    assert "agent-2" in event.affected_agent_ids
    assert "grant-1" in event.affected_authority_ids
    assert "grant-2" in event.affected_authority_ids


@pytest.mark.asyncio
async def test_contain_authority_tree_missing_agent():
    agent_repo = StubAgentRepo(None)
    grant_repo = StubGrantRepo([])
    containment_repo = StubContainmentRepo()
    service = CascadeContainmentService(agent_repo, grant_repo, containment_repo)
    with pytest.raises(ValueError, match="Target agent not found"):
        await service.contain_authority_tree(
            "tenant-1", "missing", ContainmentMode.QUARANTINE,
            "system", "admin",
        )


@pytest.mark.asyncio
async def test_contain_execution_tokens_dry_run():
    token = ExecutionToken(
        token_id="token-1",
        tenant_id="tenant-1",
        agent_id="agent-1",
        authority_grant_id=None,
        jti="jti-1",
        tool="tool",
        status=TokenStatus.ACTIVE,
        issued_at=datetime.now(UTC),
        expires_at=datetime.now(UTC),
    )
    token_repo = StubTokenRepo([token])
    service = CascadeContainmentService(
        MagicMock(), MagicMock(), MagicMock(),
        token_repository=token_repo,
    )
    revoked = await service.contain_execution_tokens("tenant-1", "agent-1", dry_run=True)
    assert revoked == ["token-1"]
    assert len(token_repo.revoked) == 0


@pytest.mark.asyncio
async def test_contain_pending_actions():
    action = ProtectedAction(
        action_id="act-1",
        tenant_id="tenant-1",
        agent_id="agent-1",
        actor_user_id=None,
        authority_grant_id=None,
        tool="tool",
        resource="res",
        action_type="read",
        status=ActionStatus.PENDING,
        decision_reason="",
        risk_score=0.0,
        created_at=datetime.now(UTC),
        evaluated_at=None,
        executed_at=None,
        parent_action_id=None,
        correlation_id=None,
        before_state_ref=None,
        after_state_ref=None,
    )
    action_repo = StubActionRepo([action])
    service = CascadeContainmentService(
        MagicMock(), MagicMock(), MagicMock(),
        action_repository=action_repo,
    )
    contained = await service.contain_pending_actions("tenant-1", "agent-1")
    assert contained == ["act-1"]
    assert len(action_repo.updated) == 1


@pytest.mark.asyncio
async def test_get_blast_radius():
    agent = make_agent("agent-1", owner_user_id="user-1")
    grant = make_grant("grant-1", "agent-1")
    agent_repo = StubAgentRepo(agent)
    grant_repo = StubGrantRepo([grant])
    token_repo = StubTokenRepo([])
    action_repo = StubActionRepo([])
    service = CascadeContainmentService(
        agent_repo, grant_repo, MagicMock(),
        action_repository=action_repo,
        token_repository=token_repo,
    )
    result = await service.get_blast_radius("tenant-1", "agent-1")
    assert result["agent_id"] == "agent-1"
    assert result["direct_authorities"] == 1


@pytest.mark.asyncio
async def test_get_blast_radius_missing_agent():
    agent_repo = StubAgentRepo(None)
    grant_repo = StubGrantRepo([])
    service = CascadeContainmentService(agent_repo, grant_repo, MagicMock())
    with pytest.raises(ValueError, match="Agent not found"):
        await service.get_blast_radius("tenant-1", "missing")


def test_compute_blast_radius():
    grants = [make_grant("grant-1", "agent-1")]
    descendants = [make_agent("child-1")]
    score = CascadeContainmentService._compute_blast_radius(grants, descendants)
    assert score > 0.0
