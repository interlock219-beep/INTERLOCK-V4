"""Phase 3: Unit tests for RiskEngine.

Tests cover all risk signal checks and score-based decision thresholds:
- Unusual privilege escalation
- Excessive delegation depth
- Expired authority usage
- Repeated authorization failures
- Abnormal action rate
- Unusual tool combinations
- Sensitive action sequences
- Cross-boundary execution
- Suspicious child agent creation
- Score threshold decisions (deny / require_hitl / allow)
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.domain.services.risk_engine import RiskEngine
from app.domain.value_objects.authorization_context import AuthorizationContext
from app.domain.value_objects.authorization_decision import AuthorizationDecision


def _make_context(
    agent_id: str = "agent-1",
    proposed_tool: str = "search",
    action: str = "execute",
    resource: str = "res-1",
    service_id: str | None = None,
    tenant_id: str | None = "tenant-1",
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


def _make_engine() -> RiskEngine:
    return RiskEngine()


# ---------------------------------------------------------------------------
# Unusual privilege escalation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unusual_escalation_admin_delete() -> None:
    engine = _make_engine()
    context = _make_context(action="delete")
    grants = [{"grant_id": "g1", "scope": "admin", "expires_at": None}]
    result = engine.evaluate(context, authority_grants=grants)
    names = [s["name"] for s in result["signals"]]
    assert "unusual_privilege_escalation" in names


@pytest.mark.asyncio
async def test_no_escalation_for_normal_tool() -> None:
    engine = _make_engine()
    context = _make_context(action="read")
    grants = [{"grant_id": "g1", "scope": "admin", "expires_at": None}]
    result = engine.evaluate(context, authority_grants=grants)
    names = [s["name"] for s in result["signals"]]
    assert "unusual_privilege_escalation" not in names


# ---------------------------------------------------------------------------
# Excessive delegation depth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_excessive_depth_triggered() -> None:
    engine = _make_engine()
    context = _make_context()
    grants = [{"grant_id": "g1", "delegation_depth": 7, "expires_at": None}]
    result = engine.evaluate(context, authority_grants=grants)
    names = [s["name"] for s in result["signals"]]
    assert "excessive_delegation_depth" in names


@pytest.mark.asyncio
async def test_depth_within_threshold_no_signal() -> None:
    engine = _make_engine()
    context = _make_context()
    grants = [{"grant_id": "g1", "delegation_depth": 3, "expires_at": None}]
    result = engine.evaluate(context, authority_grants=grants)
    names = [s["name"] for s in result["signals"]]
    assert "excessive_delegation_depth" not in names


# ---------------------------------------------------------------------------
# Expired authority
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_authority_triggered() -> None:
    engine = _make_engine()
    context = _make_context()
    grants = [{"grant_id": "g1", "scope": "read", "expires_at": "2020-01-01T00:00:00+00:00"}]
    result = engine.evaluate(context, authority_grants=grants)
    names = [s["name"] for s in result["signals"]]
    assert "expired_authority_usage" in names


@pytest.mark.asyncio
async def test_valid_authority_no_signal() -> None:
    engine = _make_engine()
    context = _make_context()
    future = datetime.now(UTC).replace(year=datetime.now(UTC).year + 1)
    grants = [{"grant_id": "g1", "scope": "read", "expires_at": future.isoformat()}]
    result = engine.evaluate(context, authority_grants=grants)
    names = [s["name"] for s in result["signals"]]
    assert "expired_authority_usage" not in names


# ---------------------------------------------------------------------------
# Repeated failures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repeated_failures_triggered() -> None:
    engine = _make_engine()
    context = _make_context()
    actions = [{"status": "denied"} for _ in range(5)]
    result = engine.evaluate(context, recent_actions=actions)
    names = [s["name"] for s in result["signals"]]
    assert "repeated_authorization_failures" in names


@pytest.mark.asyncio
async def test_few_failures_no_signal() -> None:
    engine = _make_engine()
    context = _make_context()
    actions = [{"status": "denied"} for _ in range(3)]
    result = engine.evaluate(context, recent_actions=actions)
    names = [s["name"] for s in result["signals"]]
    assert "repeated_authorization_failures" not in names


# ---------------------------------------------------------------------------
# Abnormal rate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_abnormal_rate_triggered() -> None:
    engine = _make_engine()
    context = _make_context()
    actions = [{"status": "allowed"} for _ in range(50)]
    result = engine.evaluate(context, recent_actions=actions)
    names = [s["name"] for s in result["signals"]]
    assert "abnormal_action_rate" in names


@pytest.mark.asyncio
async def test_normal_rate_no_signal() -> None:
    engine = _make_engine()
    context = _make_context()
    actions = [{"status": "allowed"} for _ in range(10)]
    result = engine.evaluate(context, recent_actions=actions)
    names = [s["name"] for s in result["signals"]]
    assert "abnormal_action_rate" not in names


# ---------------------------------------------------------------------------
# Unusual tool combination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unusual_tool_combination_triggered() -> None:
    engine = _make_engine()
    context = _make_context(proposed_tool="delete_data")
    actions = [{"tool": "read_data"}, {"tool": "write_data"}]
    result = engine.evaluate(context, recent_actions=actions)
    names = [s["name"] for s in result["signals"]]
    assert "unusual_tool_resource_combination" in names


@pytest.mark.asyncio
async def test_familiar_tool_no_signal() -> None:
    engine = _make_engine()
    context = _make_context(proposed_tool="read_data")
    actions = [{"tool": "read_data"}]
    result = engine.evaluate(context, recent_actions=actions)
    names = [s["name"] for s in result["signals"]]
    assert "unusual_tool_resource_combination" not in names


# ---------------------------------------------------------------------------
# Sensitive sequences
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sensitive_sequence_triggered() -> None:
    engine = _make_engine()
    context = _make_context()
    actions = [{"tool": "drop_table"}, {"tool": "read"}]
    result = engine.evaluate(context, recent_actions=actions)
    names = [s["name"] for s in result["signals"]]
    assert "sensitive_action_sequence" in names


@pytest.mark.asyncio
async def test_no_sensitive_sequence_no_signal() -> None:
    engine = _make_engine()
    context = _make_context()
    actions = [{"tool": "read"}, {"tool": "write"}]
    result = engine.evaluate(context, recent_actions=actions)
    names = [s["name"] for s in result["signals"]]
    assert "sensitive_action_sequence" not in names


# ---------------------------------------------------------------------------
# Cross-boundary execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_boundary_triggered() -> None:
    engine = _make_engine()
    context = _make_context(service_id="svc-1", action="execute")
    result = engine.evaluate(context)
    names = [s["name"] for s in result["signals"]]
    assert "cross_boundary_attempt" in names


@pytest.mark.asyncio
async def test_no_cross_boundary_no_signal() -> None:
    engine = _make_engine()
    context = _make_context(service_id=None, action="execute")
    result = engine.evaluate(context)
    names = [s["name"] for s in result["signals"]]
    assert "cross_boundary_attempt" not in names


# ---------------------------------------------------------------------------
# Suspicious child agent creation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suspicious_child_creation_triggered() -> None:
    engine = _make_engine()
    context = _make_context()
    history = [
        {"action_type": "create_agent"},
        {"action_type": "create_agent"},
        {"action_type": "create_agent"},
    ]
    result = engine.evaluate(context, agent_history=history)
    names = [s["name"] for s in result["signals"]]
    assert "suspicious_child_agent_creation" in names


@pytest.mark.asyncio
async def test_few_child_creations_no_signal() -> None:
    engine = _make_engine()
    context = _make_context()
    history = [
        {"action_type": "create_agent"},
        {"action_type": "other_action"},
    ]
    result = engine.evaluate(context, agent_history=history)
    names = [s["name"] for s in result["signals"]]
    assert "suspicious_child_agent_creation" not in names


# ---------------------------------------------------------------------------
# Score threshold decisions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_high_risk_score_denies() -> None:
    engine = _make_engine()
    context = _make_context()
    grants = [{"grant_id": "g1", "scope": "admin", "expires_at": "2020-01-01T00:00:00+00:00"}]
    actions = [{"status": "denied"} for _ in range(5)]
    history = [{"action_type": "create_agent"} for _ in range(3)]
    result = engine.evaluate(
        context, authority_grants=grants, recent_actions=actions, agent_history=history
    )
    assert result["decision"] == AuthorizationDecision.DENY.value


@pytest.mark.asyncio
async def test_moderate_risk_score_requires_hitl() -> None:
    engine = _make_engine()
    context = _make_context(action="delete")
    grants = [{"grant_id": "g1", "scope": "admin", "expires_at": None}]
    actions = [{"status": "allowed", "tool": "search"} for _ in range(50)]
    result = engine.evaluate(context, authority_grants=grants, recent_actions=actions)
    assert result["decision"] == AuthorizationDecision.REQUIRE_HITL.value


@pytest.mark.asyncio
async def test_low_risk_score_allows() -> None:
    engine = _make_engine()
    context = _make_context()
    result = engine.evaluate(context)
    assert result["decision"] == AuthorizationDecision.ALLOW.value


@pytest.mark.asyncio
async def test_score_clamped_to_range() -> None:
    engine = _make_engine()
    context = _make_context()
    grants = [{"grant_id": "g1", "scope": "admin", "expires_at": "2020-01-01T00:00:00+00:00"}]
    actions = [{"status": "denied"} for _ in range(5)]
    history = [{"action_type": "create_agent"} for _ in range(3)]
    result = engine.evaluate(
        context, authority_grants=grants, recent_actions=actions, agent_history=history
    )
    assert 0.0 <= result["score"] <= 1.0


@pytest.mark.asyncio
async def test_result_structure() -> None:
    engine = _make_engine()
    context = _make_context()
    result = engine.evaluate(context)
    assert "score" in result
    assert "decision" in result
    assert "signals" in result
    assert "explanations" in result
    assert "timestamp" in result
    assert isinstance(result["signals"], list)
