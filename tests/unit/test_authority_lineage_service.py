"""Phase 4: Unit tests for AuthorityLineageService.

Tests cover authority grant creation, delegation with lineage,
revocation, lineage traversal, blast-radius affected-resource
computation, and delegation validation.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.entities.agent import Agent, AgentStatus, RiskClassification
from app.domain.entities.authority_grant import (
    AuthorityGrant,
    AuthorityScope,
    AuthorityStatus,
)
from app.domain.services.authority_lineage_service import AuthorityLineageService


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Mock repositories
# ---------------------------------------------------------------------------


class MockAgentRepo:
    def __init__(self, agents: list[Agent] | None = None) -> None:
        self._agents = {a.agent_id: a for a in (agents or [])}

    async def get_by_agent_id(self, tenant_id: str, agent_id: str) -> Agent | None:
        agent = self._agents.get(agent_id)
        if agent and agent.tenant_id == tenant_id:
            return agent
        return None

    async def list_by_tenant(
        self, tenant_id: str, **kwargs: object
    ) -> tuple[list[Agent], int]:
        agents = [a for a in self._agents.values() if a.tenant_id == tenant_id]
        return agents, len(agents)


class MockGrantRepo:
    def __init__(self, grants: list[AuthorityGrant] | None = None) -> None:
        self._grants = {g.grant_id: g for g in (grants or [])}

    async def get_by_grant_id(self, tenant_id: str, grant_id: str) -> AuthorityGrant | None:
        grant = self._grants.get(grant_id)
        if grant and grant.tenant_id == tenant_id:
            return grant
        return None

    async def list_by_grantee(
        self, tenant_id: str, grantee_agent_id: str, **kwargs: object
    ) -> tuple[list[AuthorityGrant], int]:
        filtered = [
            g
            for g in self._grants.values()
            if g.tenant_id == tenant_id and g.grantee_agent_id == grantee_agent_id
        ]
        return filtered, len(filtered)

    async def list_by_grantor(
        self, tenant_id: str, grantor_agent_id: str, **kwargs: object
    ) -> tuple[list[AuthorityGrant], int]:
        filtered = [
            g
            for g in self._grants.values()
            if g.tenant_id == tenant_id and g.grantor_agent_id == grantor_agent_id
        ]
        return filtered, len(filtered)

    async def list_descendants(
        self, tenant_id: str, root_authority_id: str, **kwargs: object
    ) -> tuple[list[AuthorityGrant], int]:
        filtered = [
            g
            for g in self._grants.values()
            if g.tenant_id == tenant_id and g.root_authority_id == root_authority_id
        ]
        return filtered, len(filtered)

    async def save(self, grant: AuthorityGrant) -> AuthorityGrant:
        self._grants[grant.grant_id] = grant
        return grant

    async def revoke(
        self, tenant_id: str, grant_id: str, revoked_by: str
    ) -> AuthorityGrant | None:
        grant = self._grants.get(grant_id)
        if grant is None or grant.tenant_id != tenant_id:
            return None
        revoked = AuthorityGrant(
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
            status=AuthorityStatus.REVOKED,
            revoked_at=datetime.now(UTC),
            revoked_by=revoked_by,
            metadata=grant.metadata,
            created_at=grant.created_at,
            updated_at=datetime.now(UTC),
        )
        self._grants[grant_id] = revoked
        return revoked

    async def get_active_for_agent(
        self, tenant_id: str, agent_id: str, resource: str | None = None
    ) -> list[AuthorityGrant]:
        filtered = [
            g
            for g in self._grants.values()
            if g.tenant_id == tenant_id
            and g.grantee_agent_id == agent_id
            and g.status == AuthorityStatus.ACTIVE
        ]
        if resource:
            filtered = [g for g in filtered if g.resource == resource]
        return filtered


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def svc() -> AuthorityLineageService:
    return AuthorityLineageService(MockAgentRepo(), MockGrantRepo())


# ---------------------------------------------------------------------------
# create_authority
# ---------------------------------------------------------------------------


def test_create_authority_basic() -> None:
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo())
    grant = svc.create_authority(
        tenant_id="t1",
        grantor_agent_id="agent-A",
        grantee_agent_id="agent-B",
        scope="read",
        resource="res-1",
    )
    assert grant.tenant_id == "t1"
    assert grant.grantor_agent_id == "agent-A"
    assert grant.grantee_agent_id == "agent-B"
    assert grant.scope == AuthorityScope.READ
    assert grant.resource == "res-1"
    assert grant.status == AuthorityStatus.ACTIVE
    assert grant.delegation_depth == 0
    assert grant.conditions == {}
    assert grant.expires_at is None
    assert grant.parent_authority_id is None
    assert grant.root_authority_id is None


def test_create_authority_with_all_fields() -> None:
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo())
    now = datetime.now(UTC)
    grant = svc.create_authority(
        tenant_id="t1",
        grantor_agent_id="agent-A",
        grantee_agent_id="agent-B",
        scope=AuthorityScope.WRITE,
        resource="res-1",
        conditions={"region": "us-east"},
        expires_at=now,
        parent_authority_id="auth-parent",
        root_authority_id="auth-root",
        delegation_depth=3,
        metadata={"key": "val"},
    )
    assert grant.scope == AuthorityScope.WRITE
    assert grant.conditions == {"region": "us-east"}
    assert grant.expires_at == now
    assert grant.parent_authority_id == "auth-parent"
    assert grant.root_authority_id == "auth-root"
    assert grant.delegation_depth == 3
    assert grant.metadata == {"key": "val"}


# ---------------------------------------------------------------------------
# delegate_authority
# ---------------------------------------------------------------------------


def _make_grant(
    grantee: str = "agent-B",
    parent_depth: int = 0,
    scope: AuthorityScope = AuthorityScope.READ,
    status: AuthorityStatus = AuthorityStatus.ACTIVE,
    expires: datetime | None = None,
) -> AuthorityGrant:
    return AuthorityGrant(
        grant_id="auth-parent",
        tenant_id="t1",
        grantor_agent_id="agent-A",
        grantee_agent_id=grantee,
        scope=scope,
        resource="res-1",
        delegation_depth=parent_depth,
        status=status,
        expires_at=expires,
        root_authority_id="auth-root",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_delegate_authority_success() -> None:
    parent = _make_grant(grantee="agent-B", parent_depth=0)
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo([parent]))
    result = _run(svc.delegate_authority(
        tenant_id="t1",
        parent_grant_id="auth-parent",
        new_grantee_agent_id="agent-C",
        scope="read",
        resource="res-1",
    ))
    assert result.grantor_agent_id == "agent-B"
    assert result.grantee_agent_id == "agent-C"
    assert result.delegation_depth == 1
    assert result.root_authority_id == "auth-root"
    assert result.parent_authority_id == "auth-parent"


def test_delegate_authority_parent_not_found() -> None:
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo())
    with pytest.raises(ValueError, match="Parent authority grant not found"):
        _run(svc.delegate_authority(
            tenant_id="t1",
            parent_grant_id="missing",
            new_grantee_agent_id="agent-C",
            scope="read",
            resource="res-1",
        ))


def test_delegate_authority_parent_not_active() -> None:
    parent = _make_grant(status=AuthorityStatus.REVOKED)
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo([parent]))
    with pytest.raises(ValueError, match="not active"):
        _run(svc.delegate_authority(
            tenant_id="t1",
            parent_grant_id="auth-parent",
            new_grantee_agent_id="agent-C",
            scope="read",
            resource="res-1",
        ))


def test_delegate_authority_parent_expired() -> None:
    expired = datetime.now(UTC) - timedelta(hours=1)
    parent = _make_grant(expires=expired)
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo([parent]))
    with pytest.raises(ValueError, match="expired"):
        _run(svc.delegate_authority(
            tenant_id="t1",
            parent_grant_id="auth-parent",
            new_grantee_agent_id="agent-C",
            scope="read",
            resource="res-1",
        ))


def test_delegate_authority_max_depth() -> None:
    parent = _make_grant(parent_depth=9)
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo([parent]))
    with pytest.raises(ValueError, match="depth"):
        _run(svc.delegate_authority(
            tenant_id="t1",
            parent_grant_id="auth-parent",
            new_grantee_agent_id="agent-C",
            scope="read",
            resource="res-1",
        ))


def test_delegate_authority_scope_exceeds_parent() -> None:
    parent = _make_grant(scope=AuthorityScope.READ)
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo([parent]))
    with pytest.raises(ValueError, match="scope exceeds"):
        _run(svc.delegate_authority(
            tenant_id="t1",
            parent_grant_id="auth-parent",
            new_grantee_agent_id="agent-C",
            scope="admin",
            resource="res-1",
        ))


def test_delegate_authority_circular() -> None:
    # agent-A -> agent-B -> agent-A (circular)
    parents = [
        AuthorityGrant(
            grant_id="auth-1",
            tenant_id="t1",
            grantor_agent_id="agent-A",
            grantee_agent_id="agent-B",
            scope=AuthorityScope.ADMIN,
            resource="res-1",
            delegation_depth=0,
            status=AuthorityStatus.ACTIVE,
            root_authority_id="auth-1",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        AuthorityGrant(
            grant_id="auth-2",
            tenant_id="t1",
            grantor_agent_id="agent-B",
            grantee_agent_id="agent-A",
            scope=AuthorityScope.READ,
            resource="res-1",
            delegation_depth=1,
            status=AuthorityStatus.ACTIVE,
            parent_authority_id="auth-1",
            root_authority_id="auth-1",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
    ]
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo(parents))
    # Now try to delegate from auth-2 (grantor agent-B) back to agent-A
    with pytest.raises(ValueError, match="Circular"):
        _run(svc.delegate_authority(
            tenant_id="t1",
            parent_grant_id="auth-2",
            new_grantee_agent_id="agent-B",
            scope="read",
            resource="res-1",
        ))


# ---------------------------------------------------------------------------
# revoke_authority
# ---------------------------------------------------------------------------


def test_revoke_authority_success() -> None:
    parent = _make_grant()
    mock_repo = MockGrantRepo([parent])
    svc = AuthorityLineageService(MockAgentRepo(), mock_repo)
    result = _run(svc.revoke_authority("t1", "auth-parent", "admin-user"))
    assert result is not None
    assert result.status == AuthorityStatus.REVOKED
    assert result.revoked_by == "admin-user"


def test_revoke_authority_not_found() -> None:
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo())
    result = _run(svc.revoke_authority("t1", "missing", "admin-user"))
    assert result is None


# ---------------------------------------------------------------------------
# get_lineage
# ---------------------------------------------------------------------------


def test_get_lineage_not_found() -> None:
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo())
    with pytest.raises(ValueError, match="not found"):
        _run(svc.get_lineage("t1", "missing"))


def test_get_lineage_no_ancestors() -> None:
    grant = _make_grant()
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo([grant]))
    result = _run(svc.get_lineage("t1", "auth-parent"))
    assert result["ancestors"] == []
    assert result["descendants_count"] == 1


def test_get_lineage_with_ancestors_and_descendants() -> None:
    ancestors = [
        AuthorityGrant(
            grant_id="auth-root",
            tenant_id="t1",
            grantor_agent_id="root-agent",
            grantee_agent_id="agent-A",
            scope=AuthorityScope.ADMIN,
            resource="res-1",
            delegation_depth=0,
            status=AuthorityStatus.ACTIVE,
            root_authority_id="auth-root",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        AuthorityGrant(
            grant_id="auth-parent",
            tenant_id="t1",
            grantor_agent_id="agent-A",
            grantee_agent_id="agent-B",
            scope=AuthorityScope.READ,
            resource="res-1",
            delegation_depth=1,
            status=AuthorityStatus.ACTIVE,
            parent_authority_id="auth-root",
            root_authority_id="auth-root",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        AuthorityGrant(
            grant_id="auth-child",
            tenant_id="t1",
            grantor_agent_id="agent-B",
            grantee_agent_id="agent-C",
            scope=AuthorityScope.READ,
            resource="res-1",
            delegation_depth=2,
            status=AuthorityStatus.ACTIVE,
            parent_authority_id="auth-parent",
            root_authority_id="auth-root",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
    ]
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo(ancestors))
    result = _run(svc.get_lineage("t1", "auth-child"))
    assert len(result["ancestors"]) == 2
    assert result["ancestors"][0]["grant_id"] == "auth-parent"
    assert result["ancestors"][1]["grant_id"] == "auth-root"
    assert result["descendants_count"] == 3


# ---------------------------------------------------------------------------
# get_affected_resources
# ---------------------------------------------------------------------------


def test_get_affected_resources_not_found() -> None:
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo())
    with pytest.raises(ValueError, match="not found"):
        _run(svc.get_affected_resources("t1", "missing"))


def test_get_affected_resources() -> None:
    grant = AuthorityGrant(
        grant_id="auth-root",
        tenant_id="t1",
        grantor_agent_id="root-agent",
        grantee_agent_id="agent-A",
        scope=AuthorityScope.ADMIN,
        resource="res-1",
        delegation_depth=0,
        status=AuthorityStatus.ACTIVE,
        root_authority_id="auth-root",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    child_grant = AuthorityGrant(
        grant_id="auth-child",
        tenant_id="t1",
        grantor_agent_id="agent-A",
        grantee_agent_id="agent-B",
        scope=AuthorityScope.READ,
        resource="res-2",
        delegation_depth=1,
        status=AuthorityStatus.ACTIVE,
        parent_authority_id="auth-root",
        root_authority_id="auth-root",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo([grant, child_grant]))
    result = _run(svc.get_affected_resources("t1", "auth-root"))
    assert result["root_authority_id"] == "auth-root"
    assert "res-1" in result["resources"]
    assert "res-2" in result["resources"]
    assert result["total_affected_agents"] == 2


# ---------------------------------------------------------------------------
# validate_delegation
# ---------------------------------------------------------------------------


def _make_agent(
    agent_id: str = "agent-A",
    status: AgentStatus = AgentStatus.ACTIVE,
    risk: RiskClassification = RiskClassification.MEDIUM,
) -> Agent:
    return Agent(
        agent_id=agent_id,
        tenant_id="t1",
        name=agent_id,
        agent_type="service_agent",
        status=status,
        risk_classification=risk,
    )


def test_validate_delegation_agent_not_found() -> None:
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo())
    result = _run(svc.validate_delegation(
        tenant_id="t1",
        grantor_agent_id="missing",
        grantee_agent_id="agent-B",
        resource="res-1",
        scope=AuthorityScope.READ,
    ))
    assert result.value == "deny"


def test_validate_delegation_agent_suspended() -> None:
    agent = _make_agent(status=AgentStatus.SUSPENDED)
    svc = AuthorityLineageService(MockAgentRepo([agent]), MockGrantRepo())
    result = _run(svc.validate_delegation(
        tenant_id="t1",
        grantor_agent_id="agent-A",
        grantee_agent_id="agent-B",
        resource="res-1",
        scope=AuthorityScope.READ,
    ))
    assert result.value == "deny"


def test_validate_delegation_high_risk_agent() -> None:
    agent = _make_agent(risk=RiskClassification.HIGH)
    svc = AuthorityLineageService(MockAgentRepo([agent]), MockGrantRepo())
    result = _run(svc.validate_delegation(
        tenant_id="t1",
        grantor_agent_id="agent-A",
        grantee_agent_id="agent-B",
        resource="res-1",
        scope=AuthorityScope.READ,
    ))
    assert result.value == "require_hitl"


def test_validate_delegation_critical_risk_agent() -> None:
    agent = _make_agent(risk=RiskClassification.CRITICAL)
    svc = AuthorityLineageService(MockAgentRepo([agent]), MockGrantRepo())
    result = _run(svc.validate_delegation(
        tenant_id="t1",
        grantor_agent_id="agent-A",
        grantee_agent_id="agent-B",
        resource="res-1",
        scope=AuthorityScope.READ,
    ))
    assert result.value == "require_hitl"


def test_validate_delegation_no_active_grants() -> None:
    agent = _make_agent()
    svc = AuthorityLineageService(MockAgentRepo([agent]), MockGrantRepo())
    result = _run(svc.validate_delegation(
        tenant_id="t1",
        grantor_agent_id="agent-A",
        grantee_agent_id="agent-B",
        resource="res-1",
        scope=AuthorityScope.READ,
    ))
    assert result.value == "deny"


def test_validate_delegation_scope_exceeds_grant() -> None:
    agent = _make_agent()
    grant = AuthorityGrant(
        grant_id="auth-1",
        tenant_id="t1",
        grantor_agent_id="agent-A",
        grantee_agent_id="agent-B",
        scope=AuthorityScope.READ,
        resource="res-1",
        delegation_depth=0,
        status=AuthorityStatus.ACTIVE,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    svc = AuthorityLineageService(MockAgentRepo([agent]), MockGrantRepo([grant]))
    # Request admin scope but grant only has read
    result = _run(svc.validate_delegation(
        tenant_id="t1",
        grantor_agent_id="agent-A",
        grantee_agent_id="agent-B",
        resource="res-1",
        scope=AuthorityScope.ADMIN,
    ))
    assert result.value == "deny"


def test_validate_delegation_allowed() -> None:
    agent = _make_agent()
    grant = AuthorityGrant(
        grant_id="auth-1",
        tenant_id="t1",
        grantor_agent_id="root-agent",
        grantee_agent_id="agent-A",
        scope=AuthorityScope.ADMIN,
        resource="res-1",
        delegation_depth=0,
        status=AuthorityStatus.ACTIVE,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    svc = AuthorityLineageService(MockAgentRepo([agent]), MockGrantRepo([grant]))
    # Grant has admin scope, request read - within parent
    result = _run(svc.validate_delegation(
        tenant_id="t1",
        grantor_agent_id="agent-A",
        grantee_agent_id="agent-B",
        resource="res-1",
        scope=AuthorityScope.READ,
    ))
    assert result.value == "allow"


# ---------------------------------------------------------------------------
# _scope_within_parent
# ---------------------------------------------------------------------------


def test_scope_within_parent_read_within_admin() -> None:
    assert AuthorityLineageService._scope_within_parent(
        AuthorityScope.READ, AuthorityScope.ADMIN
    )


def test_scope_within_parent_admin_exceeds_read() -> None:
    assert not AuthorityLineageService._scope_within_parent(
        AuthorityScope.ADMIN, AuthorityScope.READ
    )


def test_scope_within_parent_equal() -> None:
    assert AuthorityLineageService._scope_within_parent(
        AuthorityScope.WRITE, AuthorityScope.WRITE
    )


def test_scope_within_parent_custom_exceeds_all() -> None:
    assert not AuthorityLineageService._scope_within_parent(
        AuthorityScope.CUSTOM, AuthorityScope.READ
    )
