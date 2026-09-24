from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from app.domain.entities.self_healing_types import HealthStatus


class RecoveryPlatformStatus(StrEnum):
    """Status of a recovery platform operation."""

    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"


class ResilienceMetric(StrEnum):
    """Types of resilience metrics tracked by the platform."""

    RECOVERY_TIME = "recovery_time"
    MEAN_TIME_BETWEEN_FAILURES = "mean_time_between_failures"
    AVAILABILITY = "availability"
    RECOVERY_RATE = "recovery_rate"
    FAILURE_DETECTION_TIME = "failure_detection_time"
    HEALING_SUCCESS_RATE = "healing_success_rate"


@dataclass(frozen=True, slots=True)
class PlatformOperationResult:
    """Result of a unified recovery platform operation."""

    operation_id: str
    tenant_id: str
    status: RecoveryPlatformStatus
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    duration_seconds: float = 0.0
    components_executed: list[str] = field(default_factory=list)
    components_succeeded: list[str] = field(default_factory=list)
    components_failed: list[str] = field(default_factory=list)
    result_data: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    error: str | None = None
    operation_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResilienceMetrics:
    """Aggregated resilience metrics for a tenant."""

    metrics_id: str
    tenant_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    values: dict[str, float] = field(default_factory=dict)
    component_metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    resilience_trend: list[float] = field(default_factory=list)
    metrics_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RecoverySummary:
    """A high-level summary of the recovery state for a tenant."""

    summary_id: str
    tenant_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    active_incidents: list[str] = field(default_factory=list)
    recent_incidents: list[str] = field(default_factory=list)
    containment_events: list[str] = field(default_factory=list)
    recovery_plans: list[str] = field(default_factory=list)
    platform_operations: list[str] = field(default_factory=list)
    chaos_experiments: list[str] = field(default_factory=list)
    healing_events: list[str] = field(default_factory=list)
    overall_health: HealthStatus = HealthStatus.UNKNOWN
    resilience_score: float = 0.0
    summary_metadata: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "RecoveryPlatformStatus",
    "ResilienceMetric",
    "PlatformOperationResult",
    "ResilienceMetrics",
    "RecoverySummary",
]
