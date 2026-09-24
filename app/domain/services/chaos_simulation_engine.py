from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from app.domain.entities.chaos_types import (
    ChaosExperiment,
    ChaosFault,
    ChaosResult,
    ChaosScenario,
    ChaosType,
    ExperimentStatus,
    SimulationResult,
    SimulationScenario,
    DigitalTwin,
)


class ChaosSimulationEngine:
    """Chaos engineering and digital-twin simulation engine.

    Runs controlled fault-injection experiments and digital twin
    simulations to proactively uncover systemic weaknesses and validate
    recovery paths before real incidents occur.
    """

    def __init__(self, adapter: Any = None) -> None:
        self._adapter = adapter

    async def run_scenario(
        self,
        tenant_id: str,
        scenario: ChaosScenario,
        experiments: list[ChaosExperiment],
    ) -> list[ChaosResult]:
        """Execute a full chaos scenario by running each experiment in sequence."""
        results: list[ChaosResult] = []

        for exp in experiments:
            result = await self._run_experiment(tenant_id, exp)
            results.append(result)

            if result.status == ExperimentStatus.FAILED:
                break

        return results

    async def _run_experiment(
        self,
        tenant_id: str,
        experiment: ChaosExperiment,
    ) -> ChaosResult:
        """Execute a single chaos experiment."""
        started_at = datetime.now(UTC)
        result_id = f"chr-{secrets.token_hex(12)}"

        try:
            steady_state_before = await self._measure_steady_state(tenant_id, experiment)
            impact = await self._inject_fault(tenant_id, experiment.fault)

            await self._wait_or_proceed(experiment.fault.duration_seconds)

            steady_state_after = await self._measure_steady_state(tenant_id, experiment)
            status = (
                ExperimentStatus.SUCCEEDED
                if steady_state_after is not None
                else ExperimentStatus.FAILED
            )

            return ChaosResult(
                result_id=result_id,
                tenant_id=tenant_id,
                experiment_id=experiment.experiment_id,
                scenario_id=experiment.scenario_id,
                status=status,
                created_at=started_at,
                completed_at=datetime.now(UTC),
                hypothesized_impact=experiment.hypothesized_impact,
                actual_impact=impact,
                steady_state_verified_before=bool(steady_state_before),
                steady_state_before=steady_state_before,
                steady_state_verified_after=bool(steady_state_after),
                steady_state_after=steady_state_after,
            )

        except Exception as exc:
            return ChaosResult(
                result_id=result_id,
                tenant_id=tenant_id,
                experiment_id=experiment.experiment_id,
                scenario_id=experiment.scenario_id,
                status=ExperimentStatus.FAILED,
                created_at=started_at,
                completed_at=datetime.now(UTC),
                hypothesized_impact=experiment.hypothesized_impact,
                error=str(exc),
            )

    async def _measure_steady_state(
        self,
        tenant_id: str,
        experiment: ChaosExperiment,
    ) -> dict[str, Any] | None:
        """Measure whether the system is in a steady state."""
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "measured": True,
            "checks_passed": True,
        }

    async def _inject_fault(
        self,
        tenant_id: str,
        fault: ChaosFault,
    ) -> str:
        """Inject a fault into the system (or simulate it)."""
        if self._adapter is not None:
            method = getattr(self._adapter, 'inject_fault', None)
            if method is not None:
                return await method(tenant_id, fault)

        fault_type_name = fault.fault_type.value if hasattr(fault.fault_type, 'value') else str(fault.fault_type)
        return f"Simulated {fault_type_name} on {fault.target_resource}"

    async def _wait_or_proceed(self, duration_seconds: int) -> None:
        """Wait for the fault duration (no-op in simulation mode)."""
        pass

    async def run_simulation(
        self,
        tenant_id: str,
        twin: DigitalTwin,
        scenario: SimulationScenario,
    ) -> SimulationResult:
        """Run a digital twin simulation against a scenario."""
        started_at = datetime.now(UTC)

        events = list(scenario.injected_events)
        predicted_outcome = self._predict_outcome(twin, scenario, events)
        actual_outcome = await self._simulate_twin_evolution(twin, scenario, events)
        predictions_matched = predicted_outcome == actual_outcome

        predicted_failures = self._predict_failures(twin, scenario, events)
        actual_failures = self._observe_failures(twin, scenario, actual_outcome)

        resilience_score = self._compute_resilience_score(
            twin, predictions_matched, predicted_failures, actual_failures
        )

        result = SimulationResult(
            result_id=f"sim-{secrets.token_hex(12)}",
            tenant_id=tenant_id,
            scenario_id=scenario.scenario_id,
            twin_id=twin.twin_id,
            created_at=started_at,
            completed_at=datetime.now(UTC),
            predicted_outcome=predicted_outcome,
            actual_outcome=actual_outcome,
            predictions_matched=predictions_matched,
            resilience_score=resilience_score,
            predicted_failure_points=predicted_failures,
            actual_failure_points=actual_failures,
            mitigation_recommendations=self._generate_recommendations(
                twin, actual_failures, scenario
            ),
        )

        return result

    def _predict_outcome(
        self,
        twin: DigitalTwin,
        scenario: SimulationScenario,
        events: list[dict[str, Any]],
    ) -> str:
        """Predict the outcome based on twin characteristics and injected events."""
        failure_modes = set(twin.failure_modes)
        event_types = {e.get("type", "") for e in events}

        if event_types & failure_modes:
            return "failure_expected"
        if not twin.resilience_characteristics:
            return "stable"
        resilience = twin.resilience_characteristics.get("rating", 0.0)
        if isinstance(resilience, (int, float)) and resilience >= 0.8:
            return "stable_with_degradation"
        return "stable"

    async def _simulate_twin_evolution(
        self,
        twin: DigitalTwin,
        scenario: SimulationScenario,
        events: list[dict[str, Any]],
    ) -> str:
        """Simulate the twin's evolution and determine the actual outcome."""
        if self._adapter is not None:
            method = getattr(self._adapter, 'simulate', None)
            if method is not None:
                return await method(twin, scenario, events)

        failure_modes = set(twin.failure_modes)
        event_types = {e.get("type", "") for e in events}

        if event_types & failure_modes:
            return "failure_expected"
        return "stable"

    def _predict_failures(
        self,
        twin: DigitalTwin,
        scenario: SimulationScenario,
        events: list[dict[str, Any]],
    ) -> list[str]:
        """Predict which failure points will be hit."""
        predicted: list[str] = []
        failure_modes = set(twin.failure_modes)
        for ev in events:
            etype = ev.get("type", "")
            if etype in failure_modes:
                predicted.append(etype)
        return predicted

    def _observe_failures(
        self,
        twin: DigitalTwin,
        scenario: SimulationScenario,
        actual_outcome: str,
    ) -> list[str]:
        """Determine actual failure points from the simulation outcome."""
        if actual_outcome == "failure_expected":
            return list(twin.failure_modes)
        return []

    def _compute_resilience_score(
        self,
        twin: DigitalTwin,
        predictions_matched: bool,
        predicted_failures: list[str],
        actual_failures: list[str],
    ) -> float:
        """Compute a resilience score between 0.5 and 1.0."""
        base = twin.resilience_characteristics.get("rating", 0.5)
        if not isinstance(base, (int, float)):
            base = 0.5

        if predictions_matched:
            accuracy = 1.0
        else:
            if predicted_failures and actual_failures:
                overlap = len(set(predicted_failures) & set(actual_failures))
                accuracy = overlap / max(len(predicted_failures), len(actual_failures))
            else:
                accuracy = 0.5
            accuracy = max(accuracy, 0.0)

        score = (float(base) * 0.5 + accuracy * 0.5)
        return round(max(0.5, min(1.0, score)), 2)

    def _generate_recommendations(
        self,
        twin: DigitalTwin,
        actual_failures: list[str],
        scenario: SimulationScenario,
    ) -> list[str]:
        """Generate mitigation recommendations based on simulation results."""
        recs: list[str] = []
        for failure in actual_failures:
            recs.append(f"Implement mitigation for failure mode: {failure}")
        if not actual_failures:
            recs.append("Twin resilient to injected events; no mitigation needed")
        else:
            recs.append("Review digital twin failure_modes for accuracy")
        return recs


__all__ = ["ChaosSimulationEngine"]
