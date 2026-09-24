from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.entities.self_healing_types import (
    HealingAction,
    HealingEvent,
    HealingPolicy,
    HealthCheck,
    HealthCheckType,
    HealthStatus,
)
from app.domain.services.circuit_breaker_service import CircuitBreakerService
from app.domain.services.self_healing_service import SelfHealingService


@pytest.fixture
def circuit_breaker():
    cb = CircuitBreakerService(failure_threshold=2, recovery_timeout_seconds=100.0)
    return cb


@pytest.fixture
def service(circuit_breaker):
    return SelfHealingService(circuit_breaker=circuit_breaker)


@pytest.fixture
def policy():
    return HealingPolicy(
        policy_id="policy-1",
        tenant_id="tenant-1",
        entity_id="agent-1",
        entity_type="agent",
        health_check_type=HealthCheckType.CIRCUIT_STATE,
        threshold=0.5,
        healing_action=None,  # will be set below
        cooldown_seconds=0,
        max_attempts=3,
    )


@pytest.fixture
def policy_circuit():
    from app.domain.entities.self_healing_types import HealingActionType
    return HealingPolicy(
        policy_id="policy-1",
        tenant_id="tenant-1",
        entity_id="agent-1",
        entity_type="agent",
        health_check_type=HealthCheckType.CIRCUIT_STATE,
        threshold=0.5,
        healing_action=HealingActionType.ROLLBACK,
        cooldown_seconds=0,
        max_attempts=3,
    )


@pytest.mark.asyncio
async def test_check_health_healthy_without_circuit_breaker():
    svc = SelfHealingService()
    result = await svc.check_health("tenant-1", "entity-1", "agent")

    assert result["overall_health"] == HealthStatus.HEALTHY.value


@pytest.mark.asyncio
async def test_check_health_with_closed_circuit(circuit_breaker, service):
    result = await service.check_health("tenant-1", "agent-1", "agent")

    assert result["overall_health"] == HealthStatus.HEALTHY.value
    circuit_check = result["checks"].get(HealthCheckType.CIRCUIT_STATE.value)
    assert circuit_check is not None
    assert circuit_check["status"] == HealthStatus.HEALTHY.value


@pytest.mark.asyncio
async def test_check_health_with_open_circuit(circuit_breaker, service):
    for _ in range(3):
        circuit_breaker.record_failure("agent-1")

    result = await service.check_health("tenant-1", "agent-1", "agent")

    assert result["overall_health"] == HealthStatus.UNHEALTHY.value
    circuit_check = result["checks"][HealthCheckType.CIRCUIT_STATE.value]
    assert circuit_check["status"] == HealthStatus.UNHEALTHY.value
    assert circuit_check["value"] == 0.0


@pytest.mark.asyncio
async def test_evaluate_and_heal_triggers_action(
    service, circuit_breaker, policy_circuit
):
    service.register_policy("tenant-1", policy_circuit)

    for _ in range(3):
        circuit_breaker.record_failure("agent-1")

    result = await service.evaluate_and_heal("tenant-1", "agent-1", "agent")

    assert result["healed"] is True
    assert len(result["actions_taken"]) > 0
    assert result["event_id"] is not None


@pytest.mark.asyncio
async def test_evaluate_and_heal_healthy_skips_actions(
    service, circuit_breaker, policy_circuit
):
    service.register_policy("tenant-1", policy_circuit)

    result = await service.evaluate_and_heal("tenant-1", "agent-1", "agent")

    assert result["healed"] is False
    assert len(result["actions_taken"]) == 0


@pytest.mark.asyncio
async def test_evaluate_and_heal_respects_cooldown(
    service, circuit_breaker, policy_circuit
):
    policy_circuit = HealingPolicy(
        policy_id="policy-1",
        tenant_id="tenant-1",
        entity_id="agent-1",
        entity_type="agent",
        health_check_type=HealthCheckType.CIRCUIT_STATE,
        threshold=0.5,
        healing_action=__import__(
            "app.domain.entities.self_healing_types", fromlist=["HealingActionType"]
        ).HealingActionType.ROLLBACK,
        cooldown_seconds=3600,
        max_attempts=3,
    )
    service.register_policy("tenant-1", policy_circuit)

    for _ in range(3):
        circuit_breaker.record_failure("agent-1")

    result1 = await service.evaluate_and_heal("tenant-1", "agent-1", "agent")
    assert result1["healed"] is True

    circuit_breaker.reset("agent-1")

    result2 = await service.evaluate_and_heal("tenant-1", "agent-1", "agent")
    assert result2["healed"] is False
    assert len(result2["actions_taken"]) == 0


@pytest.mark.asyncio
async def test_register_policy_multiple():
    svc = SelfHealingService()
    from app.domain.entities.self_healing_types import HealingActionType

    p1 = HealingPolicy(
        policy_id="p1", tenant_id="t-1", entity_id="e1", entity_type="agent",
        health_check_type=HealthCheckType.HEARTBEAT, threshold=0.5,
        healing_action=HealingActionType.RESTART,
    )
    p2 = HealingPolicy(
        policy_id="p2", tenant_id="t-1", entity_id="e1", entity_type="agent",
        health_check_type=HealthCheckType.LATENCY, threshold=100.0,
        healing_action=HealingActionType.SCALE_OUT,
    )
    svc.register_policy("t-1", p1)
    svc.register_policy("t-1", p2)

    policies = svc._policies.get("t-1:e1", [])
    assert len(policies) == 2


@pytest.mark.asyncio
async def test_register_policy_replaces_existing():
    svc = SelfHealingService()
    from app.domain.entities.self_healing_types import HealingActionType

    p1 = HealingPolicy(
        policy_id="p1", tenant_id="t-1", entity_id="e1", entity_type="agent",
        health_check_type=HealthCheckType.HEARTBEAT, threshold=0.5,
        healing_action=HealingActionType.RESTART,
    )
    p2 = HealingPolicy(
        policy_id="p1", tenant_id="t-1", entity_id="e1", entity_type="agent",
        health_check_type=HealthCheckType.LATENCY, threshold=200.0,
        healing_action=HealingActionType.SCALE_OUT,
    )
    svc.register_policy("t-1", p1)
    svc.register_policy("t-1", p2)

    policies = svc._policies.get("t-1:e1", [])
    assert len(policies) == 1
    assert policies[0].health_check_type == HealthCheckType.LATENCY


@pytest.mark.asyncio
async def test_health_history_and_events_recorded(
    service, circuit_breaker, policy_circuit
):
    service.register_policy("tenant-1", policy_circuit)

    for _ in range(3):
        circuit_breaker.record_failure("agent-1")

    await service.evaluate_and_heal("tenant-1", "agent-1", "agent")

    checks = service.get_health_history("tenant-1", "agent-1")
    assert len(checks) >= 1

    events = service.get_healing_events("tenant-1", "agent-1")
    assert len(events) == 1
    assert events[0].resolved is True


@pytest.mark.asyncio
async def test_disabled_policy_skipped(service, circuit_breaker):
    from app.domain.entities.self_healing_types import HealingActionType

    policy = HealingPolicy(
        policy_id="disabled-policy",
        tenant_id="tenant-1",
        entity_id="agent-1",
        entity_type="agent",
        health_check_type=HealthCheckType.CIRCUIT_STATE,
        threshold=0.5,
        healing_action=HealingActionType.ROLLBACK,
        enabled=False,
        cooldown_seconds=0,
    )
    service.register_policy("tenant-1", policy)

    for _ in range(3):
        circuit_breaker.record_failure("agent-1")

    result = await service.evaluate_and_heal("tenant-1", "agent-1", "agent")

    assert result["healed"] is False
    assert len(result["actions_taken"]) == 0


@pytest.mark.asyncio
async def test_adapter_execute_healing():
    from app.domain.entities.self_healing_types import HealingActionType

    class TestAdapter:
        async def execute_healing(self, tenant_id, entity_id, action, params):
            return {"status": "succeeded", "details": "healed"}

    svc = SelfHealingService(adapter=TestAdapter())
    policy = HealingPolicy(
        policy_id="p1", tenant_id="t-1", entity_id="e1", entity_type="agent",
        health_check_type=HealthCheckType.HEARTBEAT, threshold=0.5,
        healing_action=HealingActionType.RESTART,
    )
    svc.register_policy("t-1", policy)

    action = await svc._execute_healing_action("t-1", "e1", "agent", policy)
    assert action.status == "succeeded"
    assert action.result_details["details"] == "healed"
