"""Phase 3: Unit tests for ActionControlService.

Tests cover the protected action evaluation pipeline:
- Tenant identity enforcement
- Agent identity enforcement
- Authorization delegation
- Authority grant validation
- Policy engine integration
- Risk engine integration
- Final allow / deny / require_hitl decisions
"""

from __future__ import annotations

from uuid import UUID

import pytest

from app.domain.models.intent import AgentActionDAG
from app.domain.services.action_control_service import ActionControlService
from app.domain.services.authorization_service import AuthorizationService
from app.domain.value_objects.authorization_context import AuthorizationContext
from app.domain.value_objects.authorization_decision import AuthorizationDecision
from app.domain.value_objects.policy_evaluation_result import PolicyEvaluationResult


class _MockAuthz:
    def __init__(self, decision: AuthorizationDecision, reason: str = "ok") -> None:
        self._decision = decision
        self._reason = reason
        self.called = False

    def authorize(self, context: AuthorizationContext) -> tuple[AuthorizationDecision, str]:
        self.called = True
        return self._decision, self._reason


class _MockPolicy:
    def __init__(self, effect: AuthorizationDecision) -> None:
        self._effect = effect

    def evaluate(self, context: AuthorizationContext) -> PolicyEvaluationResult:
        return PolicyEvaluationResult(
            effect=self._effect,
            rule_id="test-rule" if self._effect != AuthorizationDecision.ALLOW else None,
            rule_version="1" if self._effect != AuthorizationDecision.ALLOW else None,
            reason=(
                "matched"
                if self._effect != AuthorizationDecision.ALLOW
                else "No active policy; default allow"
            ),
        )


class _MockRisk:
    def __init__(self, result: dict | None = None) -> None:
        self._result = result or {
            "score": 0.1,
            "decision": AuthorizationDecision.ALLOW.value,
            "signals": [],
            "explanations": [],
            "timestamp": "2024-01-01T00:00:00+00:00",
        }

    def evaluate(self, context: AuthorizationContext, **kwargs: object) -> dict:
        return self._result


def _make_service(
    authz_decision: AuthorizationDecision = AuthorizationDecision.ALLOW,
    authz_reason: str = "ok",
    policy_effect: AuthorizationDecision = AuthorizationDecision.ALLOW,
    risk_result: dict | None = None,
    require_tenant: bool = False,
) -> ActionControlService:
    settings = type(
        "S",
        (),
        {"authorization_require_tenant": require_tenant},
    )()
    authz = (
        AuthorizationService(settings)
        if require_tenant
        else _MockAuthz(authz_decision, authz_reason)
    )
    policy = _MockPolicy(policy_effect)
    risk = _MockRisk(risk_result)
    return ActionControlService(authz, policy, risk)


def _make_context(
    agent_id: str = "agent-1",
    tenant_id: str | None = "tenant-1",
    proposed_tool: str = "search",
    action: str = "execute",
    resource: str = "res-1",
    service_id: str | None = None,
) -> AuthorizationContext:
    return AuthorizationContext(
        user_id=UUID("12345678-1234-5678-1234-567812345678"),
        agent_id=agent_id,
        proposed_tool=proposed_tool,
        tenant_id=tenant_id,
        action=action,
        resource=resource,
        service_id=service_id,
    )


def _make_action(agent_id: str = "agent-1", tool: str = "search") -> AgentActionDAG:
    return AgentActionDAG(
        user_prompt="test prompt",
        agent_id=agent_id,
        reasoning_step="reasoning",
        proposed_tool=tool,
        tool_arguments={"q": "test"},
        tenant_id="tenant-1",
    )


# ---------------------------------------------------------------------------
# Tenant identity enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tenant_required_when_setting_enabled() -> None:
    service = _make_service(require_tenant=True)
    context = _make_context(tenant_id=None)
    action = _make_action()
    result = service.evaluate_protected_action(context, action)
    assert result["decision"] == AuthorizationDecision.DENY.value
    assert "tenant" in result["reason"].lower()


@pytest.mark.asyncio
async def test_tenant_required_by_default() -> None:
    service = _make_service(require_tenant=True)
    context = _make_context(tenant_id=None)
    action = _make_action()
    grants = [{"grant_id": "g1", "scope": "read", "expires_at": None}]
    result = service.evaluate_protected_action(context, action, authority_grants=grants)
    assert result["decision"] == AuthorizationDecision.DENY.value
    assert "tenant" in result["reason"].lower()


# ---------------------------------------------------------------------------
# Agent identity enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_id_missing_denied() -> None:
    service = _make_service()
    context = _make_context(agent_id="")
    action = _make_action()
    result = service.evaluate_protected_action(context, action)
    assert result["decision"] == AuthorizationDecision.DENY.value
    assert "agent" in result["reason"].lower()


# ---------------------------------------------------------------------------
# Authorization service delegation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authz_deny_short_circuits() -> None:
    service = _make_service(authz_decision=AuthorizationDecision.DENY, authz_reason="blocked")
    context = _make_context()
    action = _make_action()
    result = service.evaluate_protected_action(context, action)
    assert result["decision"] == AuthorizationDecision.DENY.value
    assert "blocked" in result["reason"]


@pytest.mark.asyncio
async def test_authz_require_hitl_short_circuits() -> None:
    service = _make_service(authz_decision=AuthorizationDecision.REQUIRE_HITL)
    context = _make_context()
    action = _make_action()
    result = service.evaluate_protected_action(context, action)
    assert result["decision"] == AuthorizationDecision.REQUIRE_HITL.value


# ---------------------------------------------------------------------------
# Authority grant validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_authority_grants_denied() -> None:
    service = _make_service()
    context = _make_context()
    action = _make_action()
    result = service.evaluate_protected_action(context, action, authority_grants=[])
    assert result["decision"] == AuthorizationDecision.DENY.value
    assert "authority" in result["reason"].lower()


@pytest.mark.asyncio
async def test_valid_authority_grant_allows() -> None:
    service = _make_service(
        authz_decision=AuthorizationDecision.ALLOW,
        risk_result={
            "score": 0.1,
            "decision": AuthorizationDecision.ALLOW.value,
            "signals": [],
            "explanations": [],
            "timestamp": "2024-01-01T00:00:00+00:00",
        },
    )
    context = _make_context()
    action = _make_action()
    grants = [{"grant_id": "g1", "scope": "read", "expires_at": None}]
    result = service.evaluate_protected_action(context, action, authority_grants=grants)
    assert result["decision"] == AuthorizationDecision.ALLOW.value


@pytest.mark.asyncio
async def test_expired_authority_grant_denied() -> None:
    service = _make_service(
        authz_decision=AuthorizationDecision.ALLOW,
        risk_result={
            "score": 0.1,
            "decision": AuthorizationDecision.ALLOW.value,
            "signals": [],
            "explanations": [],
            "timestamp": "2024-01-01T00:00:00+00:00",
        },
    )
    context = _make_context()
    action = _make_action()
    grants = [{"grant_id": "g1", "scope": "read", "expires_at": "2020-01-01T00:00:00+00:00"}]
    result = service.evaluate_protected_action(context, action, authority_grants=grants)
    assert result["decision"] == AuthorizationDecision.DENY.value


# ---------------------------------------------------------------------------
# Policy engine integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_policy_deny_short_circuits() -> None:
    service = _make_service(
        authz_decision=AuthorizationDecision.ALLOW,
        policy_effect=AuthorizationDecision.DENY,
        risk_result={
            "score": 0.1,
            "decision": AuthorizationDecision.ALLOW.value,
            "signals": [],
            "explanations": [],
            "timestamp": "2024-01-01T00:00:00+00:00",
        },
    )
    context = _make_context()
    action = _make_action()
    grants = [{"grant_id": "g1", "scope": "read", "expires_at": None}]
    result = service.evaluate_protected_action(context, action, authority_grants=grants)
    assert result["decision"] == AuthorizationDecision.DENY.value


# ---------------------------------------------------------------------------
# Risk engine integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_risk_deny_blocks_execution() -> None:
    service = _make_service(
        authz_decision=AuthorizationDecision.ALLOW,
        risk_result={
            "score": 0.9,
            "decision": AuthorizationDecision.DENY.value,
            "signals": [{"name": "high_risk", "score": 0.9, "explanation": "suspicious"}],
            "explanations": ["suspicious activity"],
            "timestamp": "2024-01-01T00:00:00+00:00",
        },
    )
    context = _make_context()
    action = _make_action()
    grants = [{"grant_id": "g1", "scope": "read", "expires_at": None}]
    result = service.evaluate_protected_action(context, action, authority_grants=grants)
    assert result["decision"] == AuthorizationDecision.DENY.value
    assert result["risk_score"] == 0.9


@pytest.mark.asyncio
async def test_risk_require_hitl_blocks_execution() -> None:
    service = _make_service(
        authz_decision=AuthorizationDecision.ALLOW,
        risk_result={
            "score": 0.6,
            "decision": AuthorizationDecision.REQUIRE_HITL.value,
            "signals": [{"name": "medium_risk", "score": 0.6, "explanation": "review needed"}],
            "explanations": ["review needed"],
            "timestamp": "2024-01-01T00:00:00+00:00",
        },
    )
    context = _make_context()
    action = _make_action()
    grants = [{"grant_id": "g1", "scope": "read", "expires_at": None}]
    result = service.evaluate_protected_action(context, action, authority_grants=grants)
    assert result["decision"] == AuthorizationDecision.REQUIRE_HITL.value


@pytest.mark.asyncio
async def test_full_allow_pipeline() -> None:
    service = _make_service(
        authz_decision=AuthorizationDecision.ALLOW,
        risk_result={
            "score": 0.05,
            "decision": AuthorizationDecision.ALLOW.value,
            "signals": [],
            "explanations": [],
            "timestamp": "2024-01-01T00:00:00+00:00",
        },
    )
    context = _make_context()
    action = _make_action()
    grants = [{"grant_id": "g1", "scope": "read", "expires_at": None}]
    result = service.evaluate_protected_action(context, action, authority_grants=grants)
    assert result["decision"] == AuthorizationDecision.ALLOW.value
    assert "risk_score" in result
    assert "risk_signals" in result
