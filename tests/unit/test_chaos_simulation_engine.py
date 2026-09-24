from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.entities.chaos_types import (
    ChaosExperiment,
    ChaosFault,
    ChaosScenario,
    ChaosType,
    DigitalTwin,
    ExperimentStatus,
    FaultInjectionStrategy,
    ScenarioStatus,
    SimulationResult,
    SimulationScenario,
)
from app.domain.services.chaos_simulation_engine import ChaosSimulationEngine


@pytest.fixture
def engine():
    return ChaosSimulationEngine()


@pytest.fixture
def scenario():
    return ChaosScenario(
        scenario_id="scenario-1",
        tenant_id="tenant-1",
        name="Database failure scenario",
        scenario_type=ChaosType.DEPENDENCY_FAILURE,
        status=ScenarioStatus.ACTIVE,
        description="Simulate database connection loss",
        hypothesis="System should failover to secondary without data loss",
    )


def _make_experiment(scenario_id: str = "scenario-1") -> ChaosExperiment:
    return ChaosExperiment(
        experiment_id="exp-1",
        tenant_id="tenant-1",
        scenario_id=scenario_id,
        name="DB connection kill",
        fault=ChaosFault(
            fault_id="fault-1",
            fault_type=ChaosType.PROCESS_KILL,
            target_resource="db-primary",
            tenant_id="tenant-1",
            parameters={"duration": 30},
        ),
        hypothesized_impact="Temporary connection loss, automatic failover",
    )


@pytest.mark.asyncio
async def test_run_scenario_single_experiment_succeeds(engine, scenario):
    exp = _make_experiment(scenario.scenario_id)
    results = await engine.run_scenario("tenant-1", scenario, [exp])

    assert len(results) == 1
    assert results[0].status == ExperimentStatus.SUCCEEDED
    assert results[0].steady_state_verified_before is True
    assert results[0].steady_state_verified_after is True
    assert "Simulated" in results[0].actual_impact


@pytest.mark.asyncio
async def test_run_scenario_stops_on_failure(engine, scenario):
    failing_exp = ChaosExperiment(
        experiment_id="exp-fail",
        tenant_id="tenant-1",
        scenario_id=scenario.scenario_id,
        name="Failing experiment",
        fault=ChaosFault(
            fault_id="fault-fail",
            fault_type=ChaosType.CUSTOM,
            target_resource="test-resource",
            tenant_id="tenant-1",
            parameters={},
        ),
        hypothesized_impact="Should fail",
    )

    class FailingEngine(ChaosSimulationEngine):
        async def _inject_fault(self, tenant_id, fault):
            raise RuntimeError("Injection failed")

    failing_engine = FailingEngine()
    results = await failing_engine.run_scenario("tenant-1", scenario, [failing_exp])

    assert len(results) == 1
    assert results[0].status == ExperimentStatus.FAILED
    assert results[0].error is not None
    assert "Injection failed" in results[0].error


@pytest.mark.asyncio
async def test_run_simulation_stable_system(engine):
    twin = DigitalTwin(
        twin_id="twin-1",
        tenant_id="tenant-1",
        entity_id="agent-1",
        entity_type="agent",
        current_state={"status": "healthy"},
        failure_modes=["network_partition"],
        dependencies=["dep-1"],
        resilience_characteristics={"rating": 0.9},
    )

    scenario = SimulationScenario(
        scenario_id="sim-1",
        tenant_id="tenant-1",
        name="Latency spike simulation",
        twin_id=twin.twin_id,
        description="Test resilience to latency",
        initial_conditions={"state": "healthy"},
        injected_events=[{"type": "network_latency", "severity": "medium"}],
        expected_outcomes=["stable_with_degradation"],
    )

    result = await engine.run_simulation("tenant-1", twin, scenario)

    assert result.predicted_outcome == "stable_with_degradation"
    assert result.actual_outcome == "stable"
    assert result.predictions_matched is False
    assert 0.5 <= result.resilience_score <= 1.0


@pytest.mark.asyncio
async def test_run_simulation_failure_detected(engine):
    twin = DigitalTwin(
        twin_id="twin-1",
        tenant_id="tenant-1",
        entity_id="agent-1",
        entity_type="agent",
        current_state={"status": "healthy"},
        failure_modes=["network_partition"],
        dependencies=["dep-1"],
        resilience_characteristics={"rating": 0.5},
    )

    scenario = SimulationScenario(
        scenario_id="sim-1",
        tenant_id="tenant-1",
        name="Network partition simulation",
        twin_id=twin.twin_id,
        description="Test resilience to network partition",
        initial_conditions={"state": "healthy"},
        injected_events=[{"type": "network_partition", "severity": "high"}],
        expected_outcomes=["failure_expected"],
    )

    result = await engine.run_simulation("tenant-1", twin, scenario)

    assert result.predicted_outcome == "failure_expected"
    assert result.actual_outcome == "failure_expected"
    assert result.predictions_matched is True
    assert "network_partition" in result.predicted_failure_points
    assert "network_partition" in result.actual_failure_points


@pytest.mark.asyncio
async def test_run_simulation_no_failure_modes(engine):
    twin = DigitalTwin(
        twin_id="twin-1",
        tenant_id="tenant-1",
        entity_id="agent-1",
        entity_type="agent",
        current_state={"status": "healthy"},
        failure_modes=[],
        dependencies=[],
        resilience_characteristics={"rating": 0.95},
    )

    scenario = SimulationScenario(
        scenario_id="sim-1",
        tenant_id="tenant-1",
        name="No failure simulation",
        twin_id=twin.twin_id,
        description="Steady state test",
        initial_conditions={"state": "healthy"},
        injected_events=[{"type": "cpu_stress", "severity": "low"}],
        expected_outcomes=["stable"],
    )

    result = await engine.run_simulation("tenant-1", twin, scenario)

    assert result.predicted_outcome == "stable_with_degradation"
    assert result.actual_outcome == "stable"
    assert result.predictions_matched is False
    assert len(result.actual_failure_points) == 0


@pytest.mark.asyncio
async def test_inject_fault_with_adapter(engine):
    class TestAdapter:
        async def inject_fault(self, tenant_id, fault):
            return f"Injected {fault.fault_type.value} into {fault.target_resource}"

        async def simulate(self, twin, scenario, events):
            return "custom_outcome"

    engine_with_adapter = ChaosSimulationEngine(adapter=TestAdapter())
    exp = _make_experiment()
    results = await engine_with_adapter.run_scenario(
        "tenant-1", ChaosScenario(
            scenario_id="scenario-1",
            tenant_id="tenant-1",
            name="Test",
            scenario_type=ChaosType.CUSTOM,
        ),
        [exp]
    )

    assert results[0].actual_impact == "Injected process_kill into db-primary"


@pytest.mark.asyncio
async def test_run_simulation_with_adapter(engine):
    class TestAdapter:
        async def simulate(self, twin, scenario, events):
            return "failure_expected"

    engine_with_adapter = ChaosSimulationEngine(adapter=TestAdapter())

    twin = DigitalTwin(
        twin_id="twin-1",
        tenant_id="tenant-1",
        entity_id="agent-1",
        entity_type="agent",
        current_state={"status": "healthy"},
        failure_modes=["dependency_failure"],
        dependencies=["dep-1"],
        resilience_characteristics={"rating": 0.5},
    )

    scenario = SimulationScenario(
        scenario_id="sim-1",
        tenant_id="tenant-1",
        name="Adapter simulation",
        twin_id=twin.twin_id,
        injected_events=[{"type": "network_partition"}],
    )

    result = await engine_with_adapter.run_simulation("tenant-1", twin, scenario)

    assert result.actual_outcome == "failure_expected"


@pytest.mark.asyncio
async def test_resilience_score_bounds(engine):
    twin = DigitalTwin(
        twin_id="twin-1",
        tenant_id="tenant-1",
        entity_id="agent-1",
        entity_type="agent",
        current_state={"status": "healthy"},
        failure_modes=["network_partition"],
        dependencies=[],
        resilience_characteristics={"rating": 0.0},
    )

    scenario = SimulationScenario(
        scenario_id="sim-1",
        tenant_id="tenant-1",
        name="Low resilience test",
        twin_id=twin.twin_id,
        injected_events=[{"type": "network_partition"}],
    )

    result = await engine.run_simulation("tenant-1", twin, scenario)

    assert result.resilience_score >= 0.5
    assert result.resilience_score <= 1.0


@pytest.mark.asyncio
async def test_recommendations_generated(engine):
    twin = DigitalTwin(
        twin_id="twin-1",
        tenant_id="tenant-1",
        entity_id="agent-1",
        entity_type="agent",
        current_state={"status": "healthy"},
        failure_modes=["network_partition"],
        dependencies=[],
        resilience_characteristics={"rating": 0.5},
    )

    scenario = SimulationScenario(
        scenario_id="sim-1",
        tenant_id="tenant-1",
        name="Recommendation test",
        twin_id=twin.twin_id,
        injected_events=[{"type": "network_partition"}],
    )

    result = await engine.run_simulation("tenant-1", twin, scenario)

    assert len(result.mitigation_recommendations) > 0
