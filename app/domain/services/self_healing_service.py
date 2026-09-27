from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any, cast

from app.domain.entities.self_healing_types import (
    HealingAction,
    HealingEvent,
    HealingPolicy,
    HealthCheck,
    HealthCheckType,
    HealthStatus,
)
from app.domain.services.circuit_breaker_service import CircuitBreakerService


class SelfHealingService:
    """Self-healing and resilience service.

    Monitors entity health through configurable health checks, evaluates
    healing policies, and triggers automated remediation actions when
    thresholds are breached.

    Integrates with ``CircuitBreakerService`` for circuit-level health
    signals and supports pluggable adapters for actual healing execution.
    """

    def __init__(
        self,
        circuit_breaker: CircuitBreakerService | None = None,
        adapter: Any = None,
    ) -> None:
        self._circuit_breaker = circuit_breaker
        self._adapter = adapter
        self._policies: dict[str, list[HealingPolicy]] = {}
        self._events: dict[str, list[HealingEvent]] = {}
        self._actions: dict[str, list[HealingAction]] = {}
        self._checks: dict[str, list[HealthCheck]] = {}
        self._cooldowns: dict[str, float] = {}

    async def check_health(
        self,
        tenant_id: str,
        entity_id: str,
        entity_type: str,
        check_types: list[HealthCheckType] | None = None,
    ) -> dict[str, Any]:
        """Perform health checks for a monitored entity."""
        checks_to_run = check_types or list(HealthCheckType)
        results: dict[str, Any] = {}

        for check_type in checks_to_run:
            check = await self._perform_check(tenant_id, entity_id, entity_type, check_type)
            self._record_check(tenant_id, entity_id, check)
            results[check_type.value] = {
                "status": check.status.value,
                "value": check.value,
                "threshold": check.threshold,
            }

        overall = self._compute_overall_health(results)

        return {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "overall_health": overall,
            "checks": results,
        }

    async def _perform_check(
        self,
        tenant_id: str,
        entity_id: str,
        entity_type: str,
        check_type: HealthCheckType,
    ) -> HealthCheck:
        """Perform a single health check."""
        check_id = f"check-{secrets.token_hex(12)}"
        now = datetime.now(UTC)

        if check_type == HealthCheckType.CIRCUIT_STATE and self._circuit_breaker is not None:
            state = self._circuit_breaker.get_state(entity_id)
            status_value = state.get("state", "closed")
            is_healthy = status_value == "closed"
            status = HealthStatus.HEALTHY if is_healthy else HealthStatus.UNHEALTHY
            value = 1.0 if is_healthy else 0.0
            return HealthCheck(
                check_id=check_id,
                tenant_id=tenant_id,
                entity_id=entity_id,
                entity_type=entity_type,
                check_type=check_type,
                status=status,
                created_at=now,
                value=value,
                threshold=0.5,
                details=state,
            )

        if self._adapter is not None:
            method = getattr(self._adapter, "health_check", None)
            if method is not None:
                result = await method(tenant_id, entity_id, check_type)
                return HealthCheck(
                    check_id=check_id,
                    tenant_id=tenant_id,
                    entity_id=entity_id,
                    entity_type=entity_type,
                    check_type=check_type,
                    status=HealthStatus(result.get("status", HealthStatus.UNKNOWN.value)),
                    created_at=now,
                    value=result.get("value", 0.0),
                    threshold=result.get("threshold", 0.0),
                    details=result,
                )

        return HealthCheck(
            check_id=check_id,
            tenant_id=tenant_id,
            entity_id=entity_id,
            entity_type=entity_type,
            check_type=check_type,
            status=HealthStatus.HEALTHY,
            created_at=now,
            value=1.0,
            threshold=0.5,
            details={"source": "default_healthy"},
        )

    def _compute_overall_health(self, check_results: dict[str, Any]) -> HealthStatus:
        """Compute overall health from individual check results."""
        if not check_results:
            return HealthStatus.UNKNOWN

        statuses = [r["status"] for r in check_results.values()]
        if all(s == HealthStatus.HEALTHY.value for s in statuses):
            return HealthStatus.HEALTHY
        if any(s == HealthStatus.CRITICAL.value for s in statuses):
            return HealthStatus.CRITICAL
        if any(s == HealthStatus.UNHEALTHY.value for s in statuses):
            return HealthStatus.UNHEALTHY
        if any(s == HealthStatus.DEGRADED.value for s in statuses):
            return HealthStatus.DEGRADED
        return HealthStatus.UNKNOWN

    def _record_check(self, tenant_id: str, entity_id: str, check: HealthCheck) -> None:
        """Record a health check result."""
        key = f"{tenant_id}:{entity_id}"
        if key not in self._checks:
            self._checks[key] = []
        self._checks[key] = [check]

    def register_policy(self, tenant_id: str, policy: HealingPolicy) -> None:
        """Register a healing policy."""
        key = f"{tenant_id}:{policy.entity_id}"
        if key not in self._policies:
            self._policies[key] = []
        self._policies[key] = [p for p in self._policies[key] if p.policy_id != policy.policy_id]
        self._policies[key].append(policy)

    async def evaluate_and_heal(
        self,
        tenant_id: str,
        entity_id: str,
        entity_type: str,
    ) -> dict[str, Any]:
        """Evaluate health and trigger healing if needed."""
        key = f"{tenant_id}:{entity_id}"
        policies = self._policies.get(key, [])

        health_result = await self.check_health(tenant_id, entity_id, entity_type)
        overall_raw = health_result["overall_health"]
        overall = (
            HealthStatus(overall_raw) if not isinstance(overall_raw, HealthStatus) else overall_raw
        )

        actions_taken: list[str] = []
        healed = False
        triggered_policy_ids: list[str] = []

        if overall != HealthStatus.HEALTHY:
            for policy in policies:
                if not policy.enabled:
                    continue
                check_result = health_result["checks"].get(policy.health_check_type.value)
                if check_result is None:
                    continue
                if not self._check_threshold_breached(policy, check_result):
                    continue
                if self._is_in_cooldown(policy):
                    continue

                triggered_policy_ids.append(policy.policy_id)
                action = await self._execute_healing_action(
                    tenant_id, entity_id, entity_type, policy
                )
                actions_taken.append(action.action_id)

                if action.status == "succeeded":
                    healed = True
                    self._set_cooldown(policy)
                elif action.status == "failed":
                    break

        event = HealingEvent(
            event_id=f"hev-{secrets.token_hex(12)}",
            tenant_id=tenant_id,
            entity_id=entity_id,
            entity_type=entity_type,
            health_status=overall,
            triggering_checks=triggered_policy_ids,
            actions_taken=actions_taken,
            recovery_confidence=1.0 if healed else 0.0,
        )

        self._record_event(tenant_id, entity_id, event)

        return {
            "health_status": overall,
            "healed": healed,
            "actions_taken": actions_taken,
            "event_id": event.event_id,
        }

    def _check_threshold_breached(
        self,
        policy: HealingPolicy,
        check_result: dict[str, Any],
    ) -> bool:
        """Determine whether a health check has breached the policy threshold."""
        if not check_result:
            return False
        value = check_result.get("value", 0.0)
        threshold = policy.threshold
        is_unhealthy = check_result.get("status") != HealthStatus.HEALTHY.value

        if is_unhealthy:
            return True
        return cast(float, value) < threshold

    def _is_in_cooldown(self, policy: HealingPolicy) -> bool:
        """Check if a policy is in cooldown period."""
        if policy.cooldown_seconds <= 0:
            return False
        key = f"{policy.tenant_id}:{policy.entity_id}:{policy.policy_id}"
        last = self._cooldowns.get(key, 0.0)
        elapsed = datetime.now(UTC).timestamp() - last
        return elapsed < policy.cooldown_seconds

    def _set_cooldown(self, policy: HealingPolicy) -> None:
        """Set cooldown timestamp for a policy."""
        key = f"{policy.tenant_id}:{policy.entity_id}:{policy.policy_id}"
        self._cooldowns[key] = datetime.now(UTC).timestamp()

    async def _execute_healing_action(
        self,
        tenant_id: str,
        entity_id: str,
        entity_type: str,
        policy: HealingPolicy,
    ) -> HealingAction:
        """Execute a healing action based on a policy."""
        action_id = f"heal-{secrets.token_hex(12)}"
        started_at = datetime.now(UTC)

        action = HealingAction(
            action_id=action_id,
            tenant_id=tenant_id,
            entity_id=entity_id,
            entity_type=entity_type,
            action_type=policy.healing_action,
            status="pending",
            triggered_by=policy.policy_id,
            started_at=started_at,
        )

        try:
            if self._adapter is not None:
                method = getattr(self._adapter, "execute_healing", None)
                if method is not None:
                    result = await method(
                        tenant_id,
                        entity_id,
                        policy.healing_action.value,
                        policy.action_parameters,
                    )
                    action = HealingAction(
                        action_id=action_id,
                        tenant_id=action.tenant_id,
                        entity_id=action.entity_id,
                        entity_type=action.entity_type,
                        action_type=action.action_type,
                        status=result.get("status", "succeeded"),
                        triggered_by=action.triggered_by,
                        started_at=started_at,
                        completed_at=datetime.now(UTC),
                        result_details=result,
                    )
                else:
                    action = HealingAction(
                        action_id=action_id,
                        tenant_id=action.tenant_id,
                        entity_id=action.entity_id,
                        entity_type=action.entity_type,
                        action_type=action.action_type,
                        status="succeeded",
                        triggered_by=action.triggered_by,
                        started_at=started_at,
                        completed_at=datetime.now(UTC),
                        result_details={"simulated": True},
                    )
            else:
                action = HealingAction(
                    action_id=action_id,
                    tenant_id=action.tenant_id,
                    entity_id=action.entity_id,
                    entity_type=action.entity_type,
                    action_type=action.action_type,
                    status="succeeded",
                    triggered_by=action.triggered_by,
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    result_details={"simulated": True},
                )
        except Exception as exc:
            action = HealingAction(
                action_id=action_id,
                tenant_id=action.tenant_id,
                entity_id=action.entity_id,
                entity_type=action.entity_type,
                action_type=action.action_type,
                status="failed",
                triggered_by=action.triggered_by,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                error=str(exc),
            )

        key = f"{tenant_id}:{entity_id}"
        if key not in self._actions:
            self._actions[key] = []
        self._actions[key].append(action)
        return action

    def _record_event(self, tenant_id: str, entity_id: str, event: HealingEvent) -> None:
        """Record a healing event."""
        key = f"{tenant_id}:{entity_id}"
        if key not in self._events:
            self._events[key] = []
        self._events[key].append(event)

    def get_health_history(self, tenant_id: str, entity_id: str) -> list[HealthCheck]:
        """Retrieve recorded health checks for an entity."""
        return self._checks.get(f"{tenant_id}:{entity_id}", [])

    def get_healing_events(self, tenant_id: str, entity_id: str) -> list[HealingEvent]:
        """Retrieve recorded healing events for an entity."""
        return self._events.get(f"{tenant_id}:{entity_id}", [])

    def get_healing_actions(self, tenant_id: str, entity_id: str) -> list[HealingAction]:
        """Retrieve recorded healing actions for an entity."""
        return self._actions.get(f"{tenant_id}:{entity_id}", [])


__all__ = ["SelfHealingService"]
