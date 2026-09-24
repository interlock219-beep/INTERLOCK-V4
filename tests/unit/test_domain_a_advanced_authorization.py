"""Domain A features 1-15 advanced authorization tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.domain.entities.authority_grant import (
    AuthorityGrant,
    AuthorityScope,
    AuthorityStatus,
)
from app.domain.services.advanced_authorization_service import AdvancedAuthorizationService
from app.domain.services.authorization_service import AuthorizationService
from app.domain.services.authority_lineage_service import AuthorityLineageService
from app.domain.value_objects.authorization_context import AuthorizationContext
from app.domain.value_objects.authorization_decision import AuthorizationDecision


def _make_settings(**overrides: object) -> object:
    defaults = {
        "authorization_denied_tools": [],
        "authorization_hitl_tools": [],
        "authorization_require_tenant": False,
        "authorization_allowed_services": None,
        "authorization_allowed_actions": None,
        "authorization_allowed_resources": None,
        "authorization_expiry_seconds": 3600,
        "authorization_max_delegation_depth": 9,
        "authorization_destructive_actions": ["delete", "drop", "truncate"],
        "authorization_allowed_tasks": None,
        "authorization_incident_response_actions": ["contain", "investigate", "verify"],
        "authorization_recovery_actions": ["recover", "verify", "compensate"],
        "authorization_default_deny": False,
        "authorization_role_actions": None,
        "authorization_risk_threshold": 0.7,
    }
    defaults.update(overrides)

    class _Settings:
        pass

    s = _Settings()
    for key, value in defaults.items():
        setattr(s, key, value)
    return s


def _make_context(**overrides: object) -> AuthorizationContext:
    defaults = {
        "user_id": UUID("12345678-1234-5678-1234-567812345678"),
        "agent_id": "agent-1",
        "proposed_tool": "search",
        "tenant_id": None,
        "action": "execute",
        "resource": "",
        "service_id": None,
        "user_role": None,
        "authorized_at": None,
        "task_id": None,
        "resource_type_hierarchy": None,
        "parameter_hash": None,
        "parameter_constraints": {},
        "environment": None,
        "agent_history": [],
        "dependency_state": {},
        "incident_state": {},
        "recovery_state": {},
        "authority_grants": [],
        "recent_actions": [],
        "risk_threshold": 0.7,
        "jit_ttl_seconds": 300,
        "one_shot": False,
        "require_task_scoping": False,
        "max_delegation_depth": 9,
        "session_id": None,
        "intent_id": None,
        "expected_parameter_hash": None,
        "agent_history_required": False,
    }
    defaults.update(overrides)
    if defaults.get("environment") is None:
        defaults["environment"] = AuthorizationContext.__dataclass_fields__["environment"].default
    return AuthorizationContext(**defaults)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Mock repositories
# ---------------------------------------------------------------------------


class MockAgentRepo:
    def __init__(self, agents=None):
        self._agents = {a.agent_id: a for a in (agents or [])}

    async def get_by_agent_id(self, tenant_id, agent_id):
        agent = self._agents.get(agent_id)
        if agent and agent.tenant_id == tenant_id:
            return agent
        return None

    async def list_by_tenant(self, tenant_id, **kwargs):
        agents = [a for a in self._agents.values() if a.tenant_id == tenant_id]
        return agents, len(agents)


class MockGrantRepo:
    def __init__(self, grants=None):
        self._grants = {g.grant_id: g for g in (grants or [])}

    async def get_by_grant_id(self, tenant_id, grant_id):
        grant = self._grants.get(grant_id)
        if grant and grant.tenant_id == tenant_id:
            return grant
        return None

    async def list_by_grantee(self, tenant_id, grantee_agent_id, **kwargs):
        filtered = [
            g
            for g in self._grants.values()
            if g.tenant_id == tenant_id and g.grantee_agent_id == grantee_agent_id
        ]
        return filtered, len(filtered)

    async def list_by_grantor(self, tenant_id, grantor_agent_id, **kwargs):
        filtered = [
            g
            for g in self._grants.values()
            if g.tenant_id == tenant_id and g.grantor_agent_id == grantor_agent_id
        ]
        return filtered, len(filtered)

    async def list_descendants(self, tenant_id, root_authority_id, **kwargs):
        filtered = [
            g
            for g in self._grants.values()
            if g.tenant_id == tenant_id and g.root_authority_id == root_authority_id
        ]
        return filtered, len(filtered)

    async def list_by_tenant(self, tenant_id, **kwargs):
        filtered = [g for g in self._grants.values() if g.tenant_id == tenant_id]
        return filtered, len(filtered)

    async def save(self, grant):
        self._grants[grant.grant_id] = grant
        return grant

    async def revoke(self, tenant_id, grant_id, revoked_by):
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

    async def get_active_for_agent(self, tenant_id, agent_id, resource=None):
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
# Feature 1: Task scoping
# ---------------------------------------------------------------------------


def test_authorize_includes_task_check() -> None:
    service = AuthorizationService(settings=_make_settings())
    context = _make_context(require_task_scoping=True, task_id="task-1")
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.ALLOW


def test_authorize_denies_missing_task_when_required() -> None:
    service = AuthorizationService(settings=_make_settings())
    context = _make_context(require_task_scoping=True, task_id=None)
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY
    assert reason == "Missing or unauthorized task"


# ---------------------------------------------------------------------------
# Feature 2: Resource wildcard matching
# ---------------------------------------------------------------------------


def test_authorize_resource_wildcard_matching() -> None:
    service = AuthorizationService(
        settings=_make_settings(authorization_allowed_resources=["doc-*"])
    )
    context = _make_context(resource="doc-123")
    decision = service._check_resource_hierarchy(context)
    assert decision == AuthorizationDecision.ALLOW


def test_authorize_denies_non_matching_resource() -> None:
    service = AuthorizationService(
        settings=_make_settings(authorization_allowed_resources=["doc-*"])
    )
    context = _make_context(resource="table-123")
    decision = service._check_resource_hierarchy(context)
    assert decision == AuthorizationDecision.DENY


# ---------------------------------------------------------------------------
# Feature 3: Parameter hash validation
# ---------------------------------------------------------------------------


def test_authorize_parameter_hash_validation() -> None:
    service = AuthorizationService(settings=_make_settings())
    context = _make_context(
        parameter_hash="abc123",
        parameter_constraints={"allowed_types": ["abc123", "def456"]},
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.ALLOW


def test_authorize_denies_invalid_parameters() -> None:
    service = AuthorizationService(settings=_make_settings())
    context = _make_context(
        parameter_hash="invalid",
        parameter_constraints={"allowed_types": ["abc123", "def456"]},
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY
    assert reason == "Missing or invalid parameters"


# ---------------------------------------------------------------------------
# Feature 4: Environment checks
# ---------------------------------------------------------------------------


def test_authorize_environment_production_allows_destructive() -> None:
    from app.domain.value_objects.authorization_context import AgentEnvironment

    service = AuthorizationService(settings=_make_settings())
    context = _make_context(
        action="delete",
        environment=AgentEnvironment.PRODUCTION,
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.ALLOW


def test_authorize_environment_non_production_requires_hitl() -> None:
    from app.domain.value_objects.authorization_context import AgentEnvironment

    service = AuthorizationService(settings=_make_settings())
    context = _make_context(
        action="delete",
        environment=AgentEnvironment.STAGING,
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.REQUIRE_HITL


# ---------------------------------------------------------------------------
# Feature 5: Risk score checks
# ---------------------------------------------------------------------------


def test_authorize_risk_score_low_allows() -> None:
    service = AuthorizationService(settings=_make_settings())
    context = _make_context(
        authority_grants=[],
        agent_history=[],
        recent_actions=[],
        risk_threshold=0.9,
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.ALLOW


def test_authorize_risk_score_high_requires_hitl() -> None:
    service = AuthorizationService(
        settings=_make_settings(authorization_risk_threshold=0.5)
    )
    high_risk_grant = {
        "grant_id": "auth-1",
        "scope": "admin",
        "delegation_depth": 6,
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    }
    context = _make_context(
        action="delete",
        authority_grants=[high_risk_grant],
        agent_history=[],
        recent_actions=[],
        risk_threshold=0.5,
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.REQUIRE_HITL


def test_authorize_risk_score_critical_denies() -> None:
    service = AuthorizationService(
        settings=_make_settings(authorization_risk_threshold=0.3)
    )
    high_risk_grant = {
        "grant_id": "auth-1",
        "scope": "admin",
        "delegation_depth": 10,
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    }
    many_failures = [{"status": "denied"} for _ in range(10)]
    abnormal_actions = [{"tool": "tool-" + str(i)} for i in range(60)]
    from app.domain.value_objects.authorization_context import AgentEnvironment
    context = _make_context(
        action="delete",
        environment=AgentEnvironment.PRODUCTION,
        authority_grants=[high_risk_grant],
        agent_history=[{"action_type": "create_agent"} for _ in range(5)],
        recent_actions=many_failures + abnormal_actions,
        risk_threshold=0.3,
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY


# ---------------------------------------------------------------------------
# Feature 6: Previous behavior checks
# ---------------------------------------------------------------------------


def test_authorize_previous_behavior_normal() -> None:
    service = AuthorizationService(settings=_make_settings())
    context = _make_context(
        agent_history=[
            {"tool": "search", "resource": "doc-1"},
            {"tool": "search", "resource": "doc-2"},
        ],
        proposed_tool="search",
        resource="doc-1",
        agent_history_required=True,
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.ALLOW


def test_authorize_previous_behavior_unusual() -> None:
    service = AuthorizationService(settings=_make_settings())
    context = _make_context(
        agent_history=[
            {"tool": "search", "resource": "doc-1"},
            {"tool": "search", "resource": "doc-2"},
        ],
        proposed_tool="delete",
        resource="doc-1",
        agent_history_required=True,
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.REQUIRE_HITL


def test_authorize_previous_behavior_unknown_history_fail_closed() -> None:
    service = AuthorizationService(settings=_make_settings())
    context = _make_context(
        agent_history=[],
        agent_history_required=True,
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY
    assert reason == "Agent behavior deviates from historical patterns"


# ---------------------------------------------------------------------------
# Feature 7: Dependency state checks
# ---------------------------------------------------------------------------


def test_authorize_dependency_healthy_allows() -> None:
    service = AuthorizationService(settings=_make_settings())
    context = _make_context(dependency_state={"svc-a": "up", "svc-b": "up"})
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.ALLOW


def test_authorize_dependency_degraded_requires_hitl() -> None:
    service = AuthorizationService(settings=_make_settings())
    context = _make_context(dependency_state={"svc-a": "degraded"})
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.REQUIRE_HITL


def test_authorize_dependency_unknown_fail_closed() -> None:
    service = AuthorizationService(settings=_make_settings())
    context = _make_context(dependency_state={"svc-a": "unknown"})
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY


# ---------------------------------------------------------------------------
# Feature 8: Incident state checks
# ---------------------------------------------------------------------------


def test_authorize_incident_active_restricts_actions() -> None:
    service = AuthorizationService(
        settings=_make_settings(
            authorization_incident_response_actions=["contain", "investigate", "verify"]
        )
    )
    from app.domain.value_objects.authorization_context import AgentEnvironment
    context = _make_context(
        action="delete",
        environment=AgentEnvironment.PRODUCTION,
        incident_state={"active": True},
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY


def test_authorize_incident_response_action_allowed() -> None:
    service = AuthorizationService(
        settings=_make_settings(
            authorization_incident_response_actions=["contain", "investigate", "verify"]
        )
    )
    context = _make_context(
        action="contain",
        incident_state={"active": True},
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.ALLOW


def test_authorize_incident_unknown_fail_closed() -> None:
    service = AuthorizationService(settings=_make_settings())
    context = _make_context(
        incident_state={"severity": "high"},
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY


# ---------------------------------------------------------------------------
# Feature 9: Recovery state checks
# ---------------------------------------------------------------------------


def test_authorize_recovery_in_progress_blocks_mutations() -> None:
    service = AuthorizationService(
        settings=_make_settings(
            authorization_recovery_actions=["recover", "verify", "compensate"]
        )
    )
    from app.domain.value_objects.authorization_context import AgentEnvironment
    context = _make_context(
        action="delete",
        resource="res-1",
        environment=AgentEnvironment.PRODUCTION,
        recovery_state={"res-1": "in_progress"},
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY


def test_authorize_recovery_action_allowed() -> None:
    service = AuthorizationService(
        settings=_make_settings(
            authorization_recovery_actions=["recover", "verify", "compensate"]
        )
    )
    from app.domain.value_objects.authorization_context import AgentEnvironment
    context = _make_context(
        action="recover",
        resource="res-1",
        environment=AgentEnvironment.PRODUCTION,
        recovery_state={"res-1": "in_progress"},
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.ALLOW


def test_authorize_recovery_unknown_fail_closed() -> None:
    service = AuthorizationService(settings=_make_settings())
    context = _make_context(
        action="recover",
        resource="res-1",
        recovery_state={"res-1": "unknown"},
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY


# ---------------------------------------------------------------------------
# Feature 11: JIT authority
# ---------------------------------------------------------------------------


def test_jit_authority_created_with_ttl() -> None:
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo())
    grant = svc.create_jit_authority(
        tenant_id="t1",
        grantor_agent_id="agent-A",
        grantee_agent_id="agent-B",
        scope="read",
        resource="res-1",
        ttl_seconds=300,
    )
    assert grant.is_jit is True
    assert grant.jit_expires_at is not None
    assert grant.grant_id.startswith("jit-")


def test_jit_authority_expires_after_ttl() -> None:
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo())
    past = datetime.now(UTC) - timedelta(seconds=10)
    grant = AuthorityGrant(
        grant_id="jit-expired-test",
        tenant_id="t1",
        grantor_agent_id="agent-A",
        grantee_agent_id="agent-B",
        scope=AuthorityScope.READ,
        resource="res-1",
        delegation_depth=0,
        status=AuthorityStatus.ACTIVE,
        is_jit=True,
        jit_created_at=datetime.now(UTC) - timedelta(seconds=20),
        jit_expires_at=past,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    mock_repo = MockGrantRepo([grant])
    svc2 = AuthorityLineageService(MockAgentRepo(), mock_repo)
    result = _run(svc2.expire_jit_grants("t1"))
    assert result == 1


def test_jit_authority_cannot_be_delegated() -> None:
    parent = AuthorityGrant(
        grant_id="jit-parent",
        tenant_id="t1",
        grantor_agent_id="agent-A",
        grantee_agent_id="agent-B",
        scope=AuthorityScope.READ,
        resource="res-1",
        delegation_depth=0,
        status=AuthorityStatus.ACTIVE,
        is_jit=True,
        jit_created_at=datetime.now(UTC),
        jit_expires_at=datetime.now(UTC) + timedelta(seconds=300),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo([parent]))
    with pytest.raises(ValueError, match="JIT authority cannot be delegated"):
        _run(svc.delegate_authority(
            tenant_id="t1",
            parent_grant_id="jit-parent",
            new_grantee_agent_id="agent-C",
            scope="read",
            resource="res-1",
        ))


# ---------------------------------------------------------------------------
# Feature 12: One-shot authority
# ---------------------------------------------------------------------------


def test_one_shot_authority_created() -> None:
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo())
    grant = _run(svc.create_one_shot_authority(
        tenant_id="t1",
        grantor_agent_id="agent-A",
        grantee_agent_id="agent-B",
        scope="read",
        resource="res-1",
    ))
    assert grant.one_shot is True
    assert grant.usage_count == 0


def test_one_shot_authority_revoked_after_use() -> None:
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo())
    grant = _run(svc.create_one_shot_authority(
        tenant_id="t1",
        grantor_agent_id="agent-A",
        grantee_agent_id="agent-B",
        scope="read",
        resource="res-1",
    ))
    mock_repo = MockGrantRepo([grant])
    svc2 = AuthorityLineageService(MockAgentRepo(), mock_repo)
    consumed = _run(svc2.consume_one_shot("t1", grant.grant_id))
    assert consumed is not None
    assert consumed.usage_count == 1
    assert consumed.status == AuthorityStatus.ONE_SHOT_USED


def test_one_shot_authority_cannot_be_delegated() -> None:
    parent = AuthorityGrant(
        grant_id="one-shot-parent",
        tenant_id="t1",
        grantor_agent_id="agent-A",
        grantee_agent_id="agent-B",
        scope=AuthorityScope.READ,
        resource="res-1",
        delegation_depth=0,
        status=AuthorityStatus.ACTIVE,
        one_shot=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo([parent]))
    with pytest.raises(ValueError, match="One-shot authority cannot be delegated"):
        _run(svc.delegate_authority(
            tenant_id="t1",
            parent_grant_id="one-shot-parent",
            new_grantee_agent_id="agent-C",
            scope="read",
            resource="res-1",
        ))


# ---------------------------------------------------------------------------
# Feature 13: Authority chain depth and consistency
# ---------------------------------------------------------------------------


def test_authority_chain_depth_limit_enforced() -> None:
    parent = AuthorityGrant(
        grant_id="auth-deep",
        tenant_id="t1",
        grantor_agent_id="agent-A",
        grantee_agent_id="agent-B",
        scope=AuthorityScope.READ,
        resource="res-1",
        delegation_depth=9,
        status=AuthorityStatus.ACTIVE,
        root_authority_id="auth-deep",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo([parent]))
    with pytest.raises(ValueError, match="Maximum delegation depth"):
        _run(svc.enforce_max_delegation_depth("t1", "auth-deep", "agent-C"))


def test_authority_chain_consistency_validation() -> None:
    root = AuthorityGrant(
        grant_id="auth-root",
        tenant_id="t1",
        grantor_agent_id="root",
        grantee_agent_id="agent-A",
        scope=AuthorityScope.ADMIN,
        resource="res-1",
        delegation_depth=0,
        status=AuthorityStatus.ACTIVE,
        root_authority_id="auth-root",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    child = AuthorityGrant(
        grant_id="auth-child",
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
    )
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo([root, child]))
    result = _run(svc.validate_chain_consistency("t1", "auth-child"))
    assert result["consistent"] is True
    assert result["max_depth"] == 1
    assert len(result["chain"]) == 2


# ---------------------------------------------------------------------------
# Feature 14: Authority attenuation and escalation
# ---------------------------------------------------------------------------


def test_authority_attenuation_allows_equal_or_lesser() -> None:
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo())
    assert svc._scope_within_parent(AuthorityScope.READ, AuthorityScope.READ)
    assert svc._scope_within_parent(AuthorityScope.READ, AuthorityScope.ADMIN)
    assert svc._scope_within_parent(AuthorityScope.WRITE, AuthorityScope.WRITE)


def test_authority_escalation_denied() -> None:
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo())
    assert not svc._scope_within_parent(AuthorityScope.ADMIN, AuthorityScope.READ)
    assert not svc._scope_within_parent(AuthorityScope.CUSTOM, AuthorityScope.READ)


# ---------------------------------------------------------------------------
# Feature 15: Authority TTL enforcement
# ---------------------------------------------------------------------------


def test_authority_ttl_strict_enforcement() -> None:
    service = AuthorizationService(settings=_make_settings())
    context = _make_context(
        authority_grants=[{"grant_id": "auth-1", "expires_at": None}],
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY
    assert "expired" in reason.lower() or "unknown" in reason.lower()


def test_authority_ttl_expired_denies() -> None:
    service = AuthorizationService(settings=_make_settings())
    expired_ts = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    context = _make_context(
        authority_grants=[{"grant_id": "auth-1", "expires_at": expired_ts}],
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY


# ---------------------------------------------------------------------------
# Integration: AdvancedAuthorizationService
# ---------------------------------------------------------------------------


def test_advanced_authorization_service_orchestrates() -> None:
    authz_svc = AuthorizationService(settings=_make_settings())
    mock_repo = MockGrantRepo()
    auth_lineage_svc = AuthorityLineageService(MockAgentRepo(), mock_repo)
    adv_svc = AdvancedAuthorizationService(authz_svc, auth_lineage_svc)

    context = _make_context()
    decision, reason = adv_svc.authorize_with_advanced_checks(context)
    assert decision == AuthorizationDecision.ALLOW
    assert reason == "Authorized"


# ---------------------------------------------------------------------------
# Security: Cross-tenant isolation
# ---------------------------------------------------------------------------


def test_cross_tenant_isolation() -> None:
    service = AuthorizationService(
        settings=_make_settings(authorization_require_tenant=True)
    )
    context = _make_context(tenant_id="tenant-a")
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.ALLOW


def test_authority_chain_cross_tenant_blocked() -> None:
    parent = AuthorityGrant(
        grant_id="auth-parent",
        tenant_id="tenant-a",
        grantor_agent_id="agent-A",
        grantee_agent_id="agent-B",
        scope=AuthorityScope.READ,
        resource="res-1",
        delegation_depth=0,
        status=AuthorityStatus.ACTIVE,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo([parent]))
    with pytest.raises(ValueError, match="not found"):
        _run(svc.get_lineage("tenant-b", "auth-parent"))
