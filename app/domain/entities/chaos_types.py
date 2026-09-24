from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class ChaosType(StrEnum):
    """Types of chaos experiments."""

    PROCESS_KILL = "process_kill"
    NETWORK_LATENCY = "network_latency"
    NETWORK_PARTITION = "network_partition"
    DISK_FULL = "disk_full"
    CPU_STARVATION = "cpu_starvation"
    MEMORY_PRESSURE = "memory_pressure"
    CLOCK_SKEW = "clock_skew"
    DEPENDENCY_FAILURE = "dependency_failure"
    CUSTOM = "custom"


class ScenarioStatus(StrEnum):
    """Lifecycle status of a chaos scenario."""

    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExperimentStatus(StrEnum):
    """Status of a chaos experiment execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPED = "stopped"
    SKIPPED = "skipped"


class FaultInjectionStrategy(StrEnum):
    """How faults are injected into the system."""

    DIRECT = "direct"
    PROXY = "proxy"
    API = "api"
    SCRIPT = "script"


@dataclass(frozen=True, slots=True)
class ChaosFault:
    """A single fault to inject during a chaos experiment."""

    fault_id: str
    fault_type: ChaosType
    target_resource: str
    tenant_id: str
    parameters: dict[str, Any] = field(default_factory=dict)
    injection_strategy: FaultInjectionStrategy = FaultInjectionStrategy.DIRECT
    duration_seconds: int = 30
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ChaosExperiment:
    """A single experiment within a chaos scenario."""

    experiment_id: str
    tenant_id: str
    scenario_id: str
    name: str
    fault: ChaosFault
    status: ExperimentStatus = ExperimentStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    steady_state_before: dict[str, Any] = field(default_factory=dict)
    steady_state_after: dict[str, Any] = field(default_factory=dict)
    hypothesized_impact: str = ""
    actual_impact: str = ""
    rollback_instructions: list[str] = field(default_factory=list)
    experiment_metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ChaosScenario:
    """A collection of chaos experiments that model a failure scenario."""

    scenario_id: str
    tenant_id: str
    name: str
    scenario_type: ChaosType
    status: ScenarioStatus = ScenarioStatus.DRAFT
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    description: str = ""
    hypothesis: str = ""
    experiments: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    abort_conditions: list[str] = field(default_factory=list)
    steady_state_criteria: list[str] = field(default_factory=list)
    recovery_plan_id: str | None = None
    scenario_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ChaosResult:
    """Result of a chaos experiment run."""

    result_id: str
    tenant_id: str
    experiment_id: str
    scenario_id: str
    status: ExperimentStatus
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    hypothesized_impact: str = ""
    actual_impact: str = ""
    steady_state_verified_before: bool = False
    steady_state_verified_after: bool = False
    metrics: dict[str, Any] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)
    error: str | None = None
    result_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DigitalTwin:
    """A digital twin representing a system component for simulation."""

    twin_id: str
    tenant_id: str
    entity_id: str
    entity_type: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    current_state: dict[str, Any] = field(default_factory=dict)
    state_history: list[dict[str, Any]] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    resilience_characteristics: dict[str, Any] = field(default_factory=dict)
    twin_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SimulationScenario:
    """A simulation scenario for digital twin testing."""

    scenario_id: str
    tenant_id: str
    name: str
    twin_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    description: str = ""
    initial_conditions: dict[str, Any] = field(default_factory=dict)
    injected_events: list[dict[str, Any]] = field(default_factory=list)
    expected_outcomes: list[str] = field(default_factory=list)
    expected_failures: list[str] = field(default_factory=list)
    scenario_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """Result of running a digital twin simulation."""

    result_id: str
    tenant_id: str
    scenario_id: str
    twin_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    predicted_outcome: str = ""
    actual_outcome: str = ""
    predictions_matched: bool = False
    resilience_score: float = 0.0
    predicted_failure_points: list[str] = field(default_factory=list)
    actual_failure_points: list[str] = field(default_factory=list)
    mitigation_recommendations: list[str] = field(default_factory=list)
    simulation_metrics: dict[str, Any] = field(default_factory=dict)
    result_metadata: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "ChaosType",
    "ScenarioStatus",
    "ExperimentStatus",
    "FaultInjectionStrategy",
    "ChaosFault",
    "ChaosExperiment",
    "ChaosScenario",
    "ChaosResult",
    "DigitalTwin",
    "SimulationScenario",
    "SimulationResult",
]
