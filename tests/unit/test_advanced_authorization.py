from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.domain.entities.agent import Agent, AgentEnvironment
from app.domain.entities.authority_grant import AuthorityGrant, AuthorityScope, AuthorityStatus
from app.domain.services.advanced_authorization_service import AdvancedAuthorizationService
from app.domain.services.authorization_service import AuthorizationService
from app.domain.services.authority_lineage_service import AuthorityLineageService
from app.domain.services.conditional_runtime_authorization_evaluator import ConditionalRuntimeAuthorizationEvaluator
from app.domain.services.risk_engine import RiskEngine
from app.domain.value_objects.authorization_context import AuthorizationContext
from app.domain.value_objects.authorization_decision import AuthorizationDecision


def _run(coro):
    return asyncio.run(coro)


def _make_settings(**overrides: object) -> object:
    defaults = {
        "authorization_denied_tools": [],
        "authorization_hitl_tools": [],
        "authorization_require_tenant": False,
        "authorization_allowed_services": None,
        "authorization_allowed_actions": None,
        "authorization_allowed_resources": None,
        "authorization_allowed_tasks": None,
        "authorization_expiry_seconds": 3600,
        "authorization_destructive_actions": [],
        "authorization_default_deny": False,
        "authorization_role_actions": {},
        "authorization_time_windows": [],
        "authorization_allowed_ips": [],
        "authorization_denied_ips": [],
        "authorization_max_session_age_seconds": None,
        "authorization_max_concurrent_sessions": None,
        "authorization_risk_threshold": 0.7,
        "authorization_incident_response_actions": ["respond", "recover", "diagnose", "contain"],
        "authorization_recovery_actions": ["recover", "status_check", "monitor"],
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
        "authorized_at": None,
    }
    defaults.update(overrides)
    return AuthorizationContext(**defaults)
# ---------------------------------------------------------------------------
# Feature 1: Task-scoped authorization
# ---------------------------------------------------------------------------


def test_task_scoped_authorization_allows_with_task_id():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
            authorization_allowed_tasks=["task-1"],
        )
    )
    context = _make_context(require_task_scoping=True, task_id="task-1")
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.ALLOW
    assert reason == "Authorized"


def test_task_scoped_authorization_denies_missing_task_id():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
            authorization_allowed_tasks=["task-1"],
        )
    )
    context = _make_context(require_task_scoping=True, task_id=None)
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY
    assert reason == "Missing or unauthorized task"
# ---------------------------------------------------------------------------
# Feature 2: Resource-scoped authorization
# ---------------------------------------------------------------------------


def test_resource_hierarchy_allows_wildcard_match():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
            authorization_allowed_resources=["database:*"],
        )
    )
    context = _make_context(resource="database:users")
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.ALLOW
    assert reason == "Authorized"


def test_resource_hierarchy_denies_no_match():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
            authorization_allowed_resources=["database:*"],
        )
    )
    context = _make_context(resource="api:users")
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY
    assert reason == "Resource does not match allowed hierarchy pattern"


# ---------------------------------------------------------------------------
# Feature 3: Parameter-scoped authorization
# ---------------------------------------------------------------------------


def test_parameter_scoped_allows_valid_hash():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
        )
    )
    context = _make_context(
        parameter_hash="abc123",
        parameter_constraints={"allowed_types": ["abc123", "def456"]},
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.ALLOW
    assert reason == "Authorized"


def test_parameter_scoped_denies_missing_hash():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
        )
    )
    context = _make_context(
        parameter_hash=None,
        parameter_constraints={"allowed_types": ["abc123"]},
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY
    assert reason == "Missing or invalid parameters"
# ---------------------------------------------------------------------------
# Feature 4: Environment-scoped authorization
# ---------------------------------------------------------------------------


def test_destructive_action_requires_hitl_non_production():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
            authorization_destructive_actions=["delete", "drop"],
        )
    )
    context = _make_context(action="delete", environment=AgentEnvironment.STAGING)
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.REQUIRE_HITL
    assert reason == "Action not permitted in current environment"


def test_destructive_action_allows_production():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
            authorization_destructive_actions=["delete", "drop"],
        )
    )
    context = _make_context(action="delete", environment=AgentEnvironment.PRODUCTION)
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.ALLOW
    assert reason == "Authorized"


# ---------------------------------------------------------------------------
# Feature 5: Risk-score-aware authorization
# ---------------------------------------------------------------------------


def test_risk_score_low_allows():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
            authorization_risk_threshold=0.7,
        )
    )
    context = _make_context()
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.ALLOW
    assert reason == "Authorized"


def test_risk_score_medium_requires_hitl():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
            authorization_risk_threshold=0.3,
        )
    )
    context = _make_context(
        agent_history=[{"tool": "search"}, {"tool": "search"}],
        recent_actions=[{"tool": "search", "status": "failed"}],
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.REQUIRE_HITL
    assert "Risk score" in reason


def test_risk_score_high_denies():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
            authorization_risk_threshold=0.7,
        )
    )
    context = _make_context(
        service_id="svc-a",
        action="execute",
        recent_actions=[{"tool": "drop_table", "status": "failed"}] * 5
        + [{"tool": "drop_table", "status": "failed"}] * 5,
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY
    assert "Risk score" in reason
# ---------------------------------------------------------------------------
# Feature 6: Previous-behavior-aware authorization
# ---------------------------------------------------------------------------


def test_previous_behavior_normal_pattern_allows():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
        )
    )
    context = _make_context(
        agent_history=[{"tool": "search", "resource": "db:users"}],
        proposed_tool="search",
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.ALLOW
    assert reason == "Authorized"


def test_previous_behavior_unusual_requires_hitl():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
        )
    )
    context = _make_context(
        agent_history=[{"tool": "search", "resource": "db:users"}],
        proposed_tool="delete",
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.REQUIRE_HITL
    assert "historical patterns" in reason


def test_previous_behavior_unknown_history_fails_closed():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
        )
    )
    context = _make_context(
        agent_history=[],
        proposed_tool="search",
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY
    assert "historical patterns" in reason


# ---------------------------------------------------------------------------
# Feature 7: Dependency-state-aware authorization
# ---------------------------------------------------------------------------


def test_dependency_state_healthy_allows():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
        )
    )
    context = _make_context(dependency_state={"database": "healthy", "cache": "healthy"})
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.ALLOW
    assert reason == "Authorized"


def test_dependency_state_degraded_requires_hitl():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
        )
    )
    context = _make_context(dependency_state={"database": "healthy", "cache": "degraded"})
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.REQUIRE_HITL
    assert "dependency health" in reason


def test_dependency_state_unknown_fails_closed():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
        )
    )
    context = _make_context(dependency_state={"database": "healthy", "cache": "unknown"})
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY
    assert "dependency health" in reason
# ---------------------------------------------------------------------------
# Feature 8: Incident-state-aware authorization
# ---------------------------------------------------------------------------


def test_incident_state_no_incident_allows():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
        )
    )
    context = _make_context(incident_state={})
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.ALLOW
    assert reason == "Authorized"


def test_incident_state_active_restricts():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
        )
    )
    context = _make_context(
        incident_state={"active": True, "severity": "high"},
        action="delete",
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY
    assert reason == "Action restricted during active incident"


def test_incident_state_unknown_high_severity_fails_closed():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
        )
    )
    context = _make_context(incident_state={"active": None, "severity": "high"})
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY
    assert reason == "Action restricted during active incident"


# ---------------------------------------------------------------------------
# Feature 9: Recovery-state-aware authorization
# ---------------------------------------------------------------------------


def test_recovery_state_no_recovery_allows():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
        )
    )
    context = _make_context(recovery_state={})
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.ALLOW
    assert reason == "Authorized"


def test_recovery_state_in_recovery_blocks_mutations():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
        )
    )
    context = _make_context(
        recovery_state={"database:users": "recovering"},
        resource="database:users",
        action="write",
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY
    assert reason == "Action not permitted during resource recovery"


def test_recovery_state_unknown_fails_closed():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
        )
    )
    context = _make_context(
        recovery_state={"database:users": "unknown"},
        resource="database:users",
        action="read",
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY
    assert reason == "Action not permitted during resource recovery"
# ---------------------------------------------------------------------------
# Feature 10: Conditional runtime authorization evaluator
# ---------------------------------------------------------------------------


def test_time_of_day_allows_within_window():
    evaluator = ConditionalRuntimeAuthorizationEvaluator(
        settings=_make_settings(
            authorization_time_windows=[{"start": "00:00", "end": "23:59"}],
        )
    )
    context = _make_context()
    decision, reason = evaluator.evaluate_conditions(context)
    assert decision == AuthorizationDecision.ALLOW


def test_ip_range_allows_permitted_ip():
    evaluator = ConditionalRuntimeAuthorizationEvaluator(
        settings=_make_settings(
            authorization_allowed_ips=["192.168.1.1"],
        )
    )
    context = _make_context(client_ip="192.168.1.1")
    decision, reason = evaluator.evaluate_conditions(context)
    assert decision == AuthorizationDecision.ALLOW


def test_session_age_allows_fresh_session():
    evaluator = ConditionalRuntimeAuthorizationEvaluator(
        settings=_make_settings(
            authorization_max_session_age_seconds=3600,
        )
    )
    context = _make_context(session_created_at=datetime.now(UTC))
    decision, reason = evaluator.evaluate_conditions(context)
    assert decision == AuthorizationDecision.ALLOW


def test_concurrent_sessions_denies_too_many():
    evaluator = ConditionalRuntimeAuthorizationEvaluator(
        settings=_make_settings(
            authorization_max_concurrent_sessions=2,
        )
    )
    context = _make_context(active_sessions=5)
    decision, reason = evaluator.evaluate_conditions(context)
    assert decision == AuthorizationDecision.DENY
    assert "exceeds limit" in reason
# ---------------------------------------------------------------------------
# Feature 11: Just-in-time privilege with automatic expiration
# ---------------------------------------------------------------------------


def test_jit_authority_created_successfully():
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
    assert grant.status == AuthorityStatus.ACTIVE
    assert grant.jit_expires_at is not None


def test_jit_authority_expires():
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo())
    expired_grant = svc.create_jit_authority(
        tenant_id="t1",
        grantor_agent_id="agent-A",
        grantee_agent_id="agent-B",
        scope="read",
        resource="res-1",
        ttl_seconds=-1,
    )
    grant = AuthorityGrant(
        grant_id=expired_grant.grant_id,
        tenant_id=expired_grant.tenant_id,
        grantor_agent_id=expired_grant.grantor_agent_id,
        grantee_agent_id=expired_grant.grantee_agent_id,
        scope=expired_grant.scope,
        resource=expired_grant.resource,
        delegation_depth=0,
        status=AuthorityStatus.ACTIVE,
        is_jit=True,
        jit_expires_at=datetime.now(UTC) - timedelta(seconds=1),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo = MockGrantRepo([grant])
    svc = AuthorityLineageService(MockAgentRepo(), repo)
    expired_count = _run(svc.expire_jit_grants("t1"))
    assert expired_count == 1


def test_jit_delegation_blocked():
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
# Feature 12: One-shot authority with automatic revocation
# ---------------------------------------------------------------------------


def test_one_shot_authority_created_and_consumed():
    grant = AuthorityGrant(
        grant_id="one-shot-1",
        tenant_id="t1",
        grantor_agent_id="agent-A",
        grantee_agent_id="agent-B",
        scope=AuthorityScope.READ,
        resource="res-1",
        delegation_depth=0,
        status=AuthorityStatus.ACTIVE,
        one_shot=True,
        usage_count=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo = MockGrantRepo([grant])
    svc = AuthorityLineageService(MockAgentRepo(), repo)
    result = _run(svc.consume_one_shot("t1", "one-shot-1"))
    assert result is not None
    assert result.status == AuthorityStatus.ONE_SHOT_USED
    assert result.usage_count == 1


def test_one_shot_delegation_blocked():
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


def test_one_shot_reuse_blocked():
    grant = AuthorityGrant(
        grant_id="one-shot-1",
        tenant_id="t1",
        grantor_agent_id="agent-A",
        grantee_agent_id="agent-B",
        scope=AuthorityScope.READ,
        resource="res-1",
        delegation_depth=0,
        status=AuthorityStatus.ACTIVE,
        one_shot=True,
        usage_count=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo = MockGrantRepo([grant])
    svc = AuthorityLineageService(MockAgentRepo(), repo)
    result = _run(svc.consume_one_shot("t1", "one-shot-1"))
    assert result is None
# ---------------------------------------------------------------------------
# Feature 13: Authority chaining with depth limits
# ---------------------------------------------------------------------------


def test_authority_chain_valid():
    grants = [
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
    ]
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo(grants))
    result = _run(svc.validate_chain_consistency("t1", "auth-parent"))
    assert result["consistent"] is True
    assert result["max_depth"] == 1


def test_authority_chain_depth_limit_enforced():
    parent = _make_grant(parent_depth=9)
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo([parent]), max_delegation_depth=9)
    with pytest.raises(ValueError, match="depth"):
        _run(svc.delegate_authority(
            tenant_id="t1",
            parent_grant_id="auth-parent",
            new_grantee_agent_id="agent-C",
            scope="read",
            resource="res-1",
        ))


def test_authority_chain_inconsistent_breaks():
    grants = [
        AuthorityGrant(
            grant_id="auth-parent",
            tenant_id="t1",
            grantor_agent_id="agent-A",
            grantee_agent_id="agent-B",
            scope=AuthorityScope.READ,
            resource="res-1",
            delegation_depth=1,
            status=AuthorityStatus.ACTIVE,
            parent_authority_id="missing-parent",
            root_authority_id="auth-parent",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
    ]
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo(grants))
    result = _run(svc.validate_chain_consistency("t1", "auth-parent"))
    assert result["consistent"] is True
    assert len(result["chain"]) == 1


# ---------------------------------------------------------------------------
# Feature 14: Authority attenuation enforcement
# ---------------------------------------------------------------------------


def test_attenuation_read_within_admin():
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo())
    assert svc._scope_within_parent(AuthorityScope.READ, AuthorityScope.ADMIN)


def test_escalation_admin_within_read_denied():
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo())
    assert not svc._scope_within_parent(AuthorityScope.ADMIN, AuthorityScope.READ)


def test_equal_scope_allowed():
    svc = AuthorityLineageService(MockAgentRepo(), MockGrantRepo())
    assert svc._scope_within_parent(AuthorityScope.WRITE, AuthorityScope.WRITE)


# ---------------------------------------------------------------------------
# Feature 15: Short-lived execution authority with strict TTL enforcement
# ---------------------------------------------------------------------------


def test_authority_ttl_valid():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
        )
    )
    context = _make_context(
        authority_grants=[{
            "grant_id": "g1",
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        }]
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.ALLOW
    assert reason == "Authorized"


def test_authority_ttl_expired_denied():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
        )
    )
    context = _make_context(
        authority_grants=[{
            "grant_id": "g1",
            "expires_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        }]
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY
    assert "expired" in reason.lower()
# ---------------------------------------------------------------------------
# Cross-tenant isolation tests
# ---------------------------------------------------------------------------


def test_cross_tenant_isolation_authority_grants():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
        )
    )
    context = _make_context(
        tenant_id="tenant-a",
        authority_grants=[{
            "grant_id": "g1",
            "tenant_id": "tenant-b",
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        }]
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY
    assert "expired" in reason.lower() or "unknown" in reason.lower()


# ---------------------------------------------------------------------------
# Adversarial input tests
# ---------------------------------------------------------------------------


def test_adversarial_parameter_hash_injection():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
        )
    )
    context = _make_context(
        parameter_hash="../../etc/passwd",
        parameter_constraints={"allowed_types": ["../../etc/passwd"]},
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.ALLOW


def test_adversarial_empty_agent_history_requires_deny():
    service = AuthorizationService(
        settings=_make_settings(
            authorization_require_tenant=False,
        )
    )
    context = _make_context(
        agent_history=[{}],
        proposed_tool="search",
    )
    decision, reason = service.authorize(context)
    assert decision == AuthorizationDecision.DENY


# ---------------------------------------------------------------------------
# Mock repositories for authority lineage tests
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
        filtered = [g for g in self._grants.values() if g.tenant_id == tenant_id and g.grantee_agent_id == grantee_agent_id]
        return filtered, len(filtered)

    async def list_by_grantor(self, tenant_id, grantor_agent_id, **kwargs):
        filtered = [g for g in self._grants.values() if g.tenant_id == tenant_id and g.grantor_agent_id == grantor_agent_id]
        return filtered, len(filtered)

    async def list_descendants(self, tenant_id, root_authority_id, **kwargs):
        filtered = [g for g in self._grants.values() if g.tenant_id == tenant_id and g.root_authority_id == root_authority_id]
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
        filtered = [g for g in self._grants.values() if g.tenant_id == tenant_id and g.grantee_agent_id == agent_id and g.status == AuthorityStatus.ACTIVE]
        if resource:
            filtered = [g for g in filtered if g.resource == resource]
        return filtered

    async def list_by_tenant(self, tenant_id, limit=100, offset=0):
        filtered = [g for g in self._grants.values() if g.tenant_id == tenant_id]
        return filtered, len(filtered)


def _make_grant(
    grantee="agent-B",
    parent_depth=0,
    scope=AuthorityScope.READ,
    status=AuthorityStatus.ACTIVE,
    expires=None,
):
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
