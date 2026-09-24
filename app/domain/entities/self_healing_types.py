from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class HealingActionType(StrEnum):
    """Types of self-healing actions."""

    ROLLBACK = "rollback"
    RESTART = "restart"
    SCALE_OUT = "scale_out"
    SCALE_IN = "scale_in"
    CIRCUIT_BREAK = "circuit_break"
    FAILOVER = "failover"
    QUARANTINE = "quarantine"
    RECOMPUTE = "recompute"
    REFRESH = "refresh"
    NOTIFY = "notify"


class HealthStatus(StrEnum):
    """Overall health status of a monitored entity."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    CRITICAL = "critical"


class HealthCheckType(StrEnum):
    """Types of health checks."""

    HEARTBEAT = "heartbeat"
    STATE_INTEGRITY = "state_integrity"
    LATENCY = "latency"
    ERROR_RATE = "error_rate"
    DEPENDENCY_HEALTH = "dependency_health"
    CIRCUIT_STATE = "circuit_state"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class HealthCheck:
    """A single health check result for a monitored entity."""

    check_id: str
    tenant_id: str
    entity_id: str
    entity_type: str
    check_type: HealthCheckType
    status: HealthStatus
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    value: float = 0.0
    threshold: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    check_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HealingPolicy:
    """Policy defining self-healing behavior for an entity."""

    policy_id: str
    tenant_id: str
    entity_id: str
    entity_type: str
    health_check_type: HealthCheckType
    threshold: float
    healing_action: HealingActionType
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    enabled: bool = True
    cooldown_seconds: int = 60
    max_attempts: int = 3
    action_parameters: dict[str, Any] = field(default_factory=dict)
    conditions: list[str] = field(default_factory=list)
    policy_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HealingAction:
    """A single healing action execution."""

    action_id: str
    tenant_id: str
    entity_id: str
    entity_type: str
    action_type: HealingActionType
    status: str
    triggered_by: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    trigger_check_id: str | None = None
    error: str | None = None
    result_details: dict[str, Any] = field(default_factory=dict)
    action_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HealingEvent:
    """A self-healing event recording detection and response."""

    event_id: str
    tenant_id: str
    entity_id: str
    entity_type: str
    health_status: HealthStatus
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved: bool = False
    resolved_at: datetime | None = None
    triggering_checks: list[str] = field(default_factory=list)
    actions_taken: list[str] = field(default_factory=list)
    recovery_confidence: float = 0.0
    event_metadata: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "HealingActionType",
    "HealthStatus",
    "HealthCheckType",
    "HealthCheck",
    "HealingPolicy",
    "HealingAction",
    "HealingEvent",
]
