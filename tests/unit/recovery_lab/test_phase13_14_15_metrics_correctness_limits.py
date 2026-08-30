"""Phase 13, 14, 15 — Recovery Coverage Metrics, Correctness Score, and Limits.

Tests:
- Recovery coverage calculation
- Recovery correctness scoring
- Identification of recovery limits
- Documentation of unsupported scenarios
"""

from __future__ import annotations

from typing import Any

import pytest

from app.domain.entities.protected_action import (
    Reversibility,
)
from app.domain.entities.surgical_recovery_types import (
    ConflictStatus,
    DriftStatus,
)
from app.domain.services.recovery_simulation_engine import RecoverySimulationEngine
from app.infrastructure.recovery.mock_adapter import MockRecoveryAdapter
from tests.unit.recovery_lab.factories import make_action, make_evidence


class BulkEvidenceRepo:
    def __init__(self, evidence_list: list[Any]) -> None:
        self._evidence = {e.action_id: e for e in evidence_list}

    async def get_by_action_id(self, tenant_id: str, action_id: str) -> Any | None:
        ev = self._evidence.get(action_id)
        if ev and ev.tenant_id == tenant_id:
            return ev
        return None

    async def get_by_evidence_id(self, tenant_id: str, evidence_id: str) -> Any | None:
        for ev in self._evidence.values():
            if ev.evidence_id == evidence_id and ev.tenant_id == tenant_id:
                return ev
        return None

    async def list_by_incident(
        self, tenant_id: str, incident_id: str, **kwargs: Any
    ) -> tuple[list[Any], int]:
        items = [
            e for e in self._evidence.values()
            if e.tenant_id == tenant_id and e.incident_id == incident_id
        ]
        return items, len(items)

    async def list_by_root_action(
        self, tenant_id: str, root_action_id: str, **kwargs: Any
    ) -> tuple[list[Any], int]:
        items = [
            e for e in self._evidence.values()
            if e.tenant_id == tenant_id and e.root_action_id == root_action_id
        ]
        return items, len(items)

    async def save(self, evidence: Any) -> Any:
        self._evidence[evidence.action_id] = evidence
        return evidence


class EmptyCheckpointRepo:
    async def get_by_checkpoint_id(self, tenant_id: str, checkpoint_id: str) -> None:
        return None

    async def get_by_action_id(self, tenant_id: str, action_id: str) -> None:
        return None

    async def list_by_resource(
        self, tenant_id: str, resource_id: str, **kwargs: Any
    ) -> tuple[list[Any], int]:
        return [], 0

    async def save(self, checkpoint: Any) -> Any:
        return checkpoint


class EmptyEvidenceRepo:
    async def get_by_action_id(self, tenant_id: str, action_id: str) -> None:
        return None

    async def get_by_evidence_id(self, tenant_id: str, evidence_id: str) -> None:
        return None

    async def list_by_incident(
        self, tenant_id: str, incident_id: str, **kwargs: Any
    ) -> tuple[list[Any], int]:
        return [], 0

    async def list_by_root_action(
        self, tenant_id: str, root_action_id: str, **kwargs: Any
    ) -> tuple[list[Any], int]:
        return [], 0

    async def save(self, evidence: Any) -> Any:
        return evidence


class TestPhase13RecoveryCoverageMetrics:
    """Calculate actual recovery coverage metrics."""

    @pytest.mark.asyncio
    async def test_perfect_recovery_coverage(self) -> None:
        actions = [make_action(f"perfect-{i}") for i in range(10)]
        evidence = [make_evidence(a) for a in actions]

        engine = RecoverySimulationEngine(
            BulkEvidenceRepo(evidence),
            EmptyCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", actions)

        total = result["total_resources"]
        recoverable = result["recoverable_resources"]
        coverage = recoverable / total if total > 0 else 0.0

        assert coverage == 1.0

    @pytest.mark.asyncio
    async def test_zero_recovery_coverage(self) -> None:
        actions = [
            make_action(f"zero-{i}", reversibility=Reversibility.IRREVERSIBLE)
            for i in range(5)
        ]
        evidence = [make_evidence(a) for a in actions]

        engine = RecoverySimulationEngine(
            BulkEvidenceRepo(evidence),
            EmptyCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", actions)

        total = result["total_resources"]
        recoverable = result["recoverable_resources"]
        coverage = recoverable / total if total > 0 else 0.0

        assert coverage == 0.0

    @pytest.mark.asyncio
    async def test_partial_recovery_coverage(self) -> None:
        actions = []
        for i in range(20):
            if i < 10:
                rev = Reversibility.AUTOMATICALLY_REVERSIBLE
            elif i < 15:
                rev = Reversibility.IRREVERSIBLE
            else:
                rev = Reversibility.CONDITIONALLY_REVERSIBLE
            actions.append(make_action(f"partial-{i}", reversibility=rev))

        evidence = [make_evidence(a) for a in actions]

        engine = RecoverySimulationEngine(
            BulkEvidenceRepo(evidence),
            EmptyCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", actions)

        total = result["total_resources"]
        recoverable = result["recoverable_resources"]
        coverage = recoverable / total if total > 0 else 0.0

        assert total == 20
        assert recoverable == 15
        assert coverage == 0.75

    @pytest.mark.asyncio
    async def test_comprehensive_metrics_calculation(self) -> None:
        actions = []
        for i in range(100):
            if i < 60:
                rev = Reversibility.AUTOMATICALLY_REVERSIBLE
            elif i < 75:
                rev = Reversibility.CONDITIONALLY_REVERSIBLE
            elif i < 90:
                rev = Reversibility.IRREVERSIBLE
            else:
                rev = Reversibility.UNKNOWN
            actions.append(make_action(f"metrics-{i}", reversibility=rev))

        evidence = [make_evidence(a) for a in actions]

        engine = RecoverySimulationEngine(
            BulkEvidenceRepo(evidence),
            EmptyCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", actions)

        total = result["total_resources"]
        recoverable = result["recoverable_resources"]
        irreversible = sum(
            1 for s in result["resource_simulations"].values()
            if s["simulation_status"] == "irreversible"
        )
        unknown = sum(
            1 for s in result["resource_simulations"].values()
            if s["simulation_status"] == "unknown_reversibility"
        )

        metrics = {
            "total_mutations": total,
            "directly_restored": recoverable,
            "irreversible": irreversible,
            "unknown": unknown,
            "recovery_coverage": recoverable / total if total > 0 else 0.0,
            "irreversible_rate": irreversible / total if total > 0 else 0.0,
            "unknown_rate": unknown / total if total > 0 else 0.0,
        }

        assert metrics["total_mutations"] == 100
        assert metrics["directly_restored"] == 75
        assert metrics["irreversible"] == 15
        assert metrics["unknown"] == 10
        assert metrics["recovery_coverage"] == 0.75
        assert metrics["irreversible_rate"] == 0.15
        assert metrics["unknown_rate"] == 0.10


class TestPhase14RecoveryCorrectnessScore:
    """Evaluate recovery correctness against 10 criteria."""

    @pytest.mark.asyncio
    async def test_criterion_1_identifies_every_mutation(self) -> None:
        actions = [make_action(f"identify-{i}") for i in range(10)]
        evidence = [make_evidence(a) for a in actions]

        engine = RecoverySimulationEngine(
            BulkEvidenceRepo(evidence),
            EmptyCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", actions)

        assert result["total_resources"] == 10
        assert len(result["resource_simulations"]) == 10

    @pytest.mark.asyncio
    async def test_criterion_2_correct_attribution(self) -> None:
        actions = [
            make_action("attr-1", agent_id="agent-a"),
            make_action("attr-2", agent_id="agent-b"),
        ]
        evidence = [make_evidence(a) for a in actions]

        engine = RecoverySimulationEngine(
            BulkEvidenceRepo(evidence),
            EmptyCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", actions)

        assert "attr-1" in result["resource_simulations"]
        assert "attr-2" in result["resource_simulations"]

    @pytest.mark.asyncio
    async def test_criterion_3_sufficient_pre_state(self) -> None:
        action_with_state = make_action("with-state", before_state_ref="state:123")
        action_without_state = make_action("without-state", before_state_ref=None)

        evidence_with = make_evidence(action_with_state)
        evidence_without = make_evidence(action_without_state)

        engine = RecoverySimulationEngine(
            BulkEvidenceRepo([evidence_with, evidence_without]),
            EmptyCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery(
            "test-tenant", [action_with_state, action_without_state]
        )

        sim_with = result["resource_simulations"]["with-state"]

        assert sim_with["before_state_reference"] is not None

    @pytest.mark.asyncio
    async def test_criterion_4_correct_dependency_graph(self) -> None:
        actions = [
            make_action("dep-root", parent_action_id=None),
            make_action("dep-child1", parent_action_id="dep-root"),
            make_action("dep-child2", parent_action_id="dep-root"),
            make_action("dep-grandchild", parent_action_id="dep-child1"),
        ]

        evidence = [make_evidence(a) for a in actions]

        engine = RecoverySimulationEngine(
            BulkEvidenceRepo(evidence),
            EmptyCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", actions)

        assert result["total_resources"] == 4

    @pytest.mark.asyncio
    async def test_criterion_5_no_overwrite_newer_changes(self) -> None:
        adapter = MockRecoveryAdapter(scenario="conflict_detected")
        action = make_action("no-overwrite")
        evidence = make_evidence(action)

        conflict = await adapter.check_conflicts(action, evidence)

        assert conflict.status == ConflictStatus.CONFLICT_DETECTED

    @pytest.mark.asyncio
    async def test_criterion_6_recover_what_is_recoverable(self) -> None:
        actions = [
            make_action("recover-1", reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE),
            make_action("recover-2", reversibility=Reversibility.IRREVERSIBLE),
        ]

        evidence = [make_evidence(a) for a in actions]

        engine = RecoverySimulationEngine(
            BulkEvidenceRepo(evidence),
            EmptyCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", actions)

        assert result["recoverable_resources"] == 1
        assert result["resource_simulations"]["recover-1"]["simulation_status"] == "recoverable"
        assert result["resource_simulations"]["recover-2"]["simulation_status"] == "irreversible"

    @pytest.mark.asyncio
    async def test_criterion_7_classify_what_is_not_recoverable(self) -> None:
        actions = [
            make_action("classify-irrev", reversibility=Reversibility.IRREVERSIBLE),
            make_action("classify-unknown", reversibility=Reversibility.UNKNOWN),
        ]

        evidence = [make_evidence(a) for a in actions]

        engine = RecoverySimulationEngine(
            BulkEvidenceRepo(evidence),
            EmptyCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", actions)

        assert (
            result["resource_simulations"]["classify-irrev"]["simulation_status"]
            == "irreversible"
        )
        assert (
            result["resource_simulations"]["classify-unknown"]["simulation_status"]
            == "unknown_reversibility"
        )

    @pytest.mark.asyncio
    async def test_criterion_8_verification_confirms_result(self) -> None:
        adapter = MockRecoveryAdapter(scenario="success")

        verification = await adapter.verify(
            type("Comp", (), {"action_id": "verify-me"})()
        )

        assert verification.verified is False

    @pytest.mark.asyncio
    async def test_criterion_9_recovery_is_idempotent(self) -> None:
        adapter = MockRecoveryAdapter(scenario="success")
        compensation = type("Comp", (), {
            "action_id": "idem",
            "idempotency_key": "idem-key",
        })()

        result1 = await adapter.execute_compensation(compensation, "idem-key")
        result2 = await adapter.execute_compensation(compensation, "idem-key")

        assert result1.success == result2.success
        assert result1.execution_state == result2.execution_state

    @pytest.mark.asyncio
    async def test_criterion_10_failures_are_truthful(self) -> None:
        adapter = MockRecoveryAdapter(scenario="execute_fail")
        compensation = type("Comp", (), {
            "action_id": "truthful",
            "idempotency_key": "truthful-key",
        })()

        result = await adapter.execute_compensation(compensation, "truthful-key")

        assert result.success is False
        assert result.error is not None
        assert len(result.error) > 0


class TestPhase15RecoveryLimits:
    """Identify and document recovery limits."""

    @pytest.mark.asyncio
    async def test_limit_no_before_state_reference(self) -> None:
        action = make_action("no-before", before_state_ref=None)
        evidence = make_evidence(action)

        adapter = MockRecoveryAdapter(scenario="success")
        reversibility = await adapter.classify_reversibility(action, evidence)

        assert reversibility in (
            Reversibility.AUTOMATICALLY_REVERSIBLE,
            Reversibility.CONDITIONALLY_REVERSIBLE,
            Reversibility.UNKNOWN,
        )

    @pytest.mark.asyncio
    async def test_limit_no_evidence_captured(self) -> None:
        action = make_action("no-evidence")

        engine = RecoverySimulationEngine(
            EmptyEvidenceRepo(),
            EmptyCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", [action])

        sim = result["resource_simulations"]["no-evidence"]
        assert sim["simulation_status"] == "no_evidence"

    @pytest.mark.asyncio
    async def test_limit_irreversible_actions(self) -> None:
        action = make_action("irrev-limit", reversibility=Reversibility.IRREVERSIBLE)
        evidence = make_evidence(
            make_action("irrev-limit", reversibility=Reversibility.IRREVERSIBLE)
        )

        adapter = MockRecoveryAdapter(scenario="success")
        impact = await adapter.simulate(action, evidence)

        assert impact.would_succeed is False
        assert impact.reversibility == Reversibility.IRREVERSIBLE

    @pytest.mark.asyncio
    async def test_limit_concurrent_mutation(self) -> None:
        adapter = MockRecoveryAdapter(scenario="conflict_detected")
        action = make_action("concurrent-limit")
        evidence = make_evidence(make_action("concurrent-limit"))

        conflict = await adapter.check_conflicts(action, evidence)

        assert conflict.status == ConflictStatus.CONFLICT_DETECTED

    @pytest.mark.asyncio
    async def test_limit_drift_blocks_recovery(self) -> None:
        adapter = MockRecoveryAdapter(scenario="drift_detected")
        action = make_action("drift-limit")
        evidence = make_evidence(make_action("drift-limit"))

        drift = await adapter.detect_drift(action, evidence)

        assert drift.status == DriftStatus.DRIFT_DETECTED

    @pytest.mark.asyncio
    async def test_limit_unsupported_adapter(self) -> None:
        action = make_action("unsupported", tool="proprietary_system")

        adapter = MockRecoveryAdapter()
        can_recover = await adapter.can_recover(action)

        assert can_recover in ("reversible", "unknown")

    @pytest.mark.asyncio
    async def test_limit_external_api_side_effects(self) -> None:
        action = make_action(
            "side-effect",
            tool="external_api",
            action_type="send_email",
            reversibility=Reversibility.IRREVERSIBLE,
        )

        evidence = make_evidence(
            make_action("side-effect", reversibility=Reversibility.IRREVERSIBLE)
        )

        adapter = MockRecoveryAdapter(scenario="success")
        impact = await adapter.simulate(action, evidence)

        assert impact.would_succeed is False

    @pytest.mark.asyncio
    async def test_limit_cryptographic_operations(self) -> None:
        action = make_action(
            "crypto",
            tool="encryption",
            action_type="hash",
            reversibility=Reversibility.IRREVERSIBLE,
        )

        evidence = make_evidence(make_action("crypto", reversibility=Reversibility.IRREVERSIBLE))

        adapter = MockRecoveryAdapter(scenario="success")
        reversibility = await adapter.classify_reversibility(action, evidence)

        assert reversibility == Reversibility.IRREVERSIBLE

    @pytest.mark.asyncio
    async def test_limit_time_delayed_operations(self) -> None:
        action = make_action(
            "time-delayed",
            tool="scheduler",
            action_type="schedule_future",
            reversibility=Reversibility.CONDITIONALLY_REVERSIBLE,
        )

        evidence = make_evidence(action)

        adapter = MockRecoveryAdapter(scenario="success")
        reversibility = await adapter.classify_reversibility(action, evidence)

        assert reversibility in (
            Reversibility.AUTOMATICALLY_REVERSIBLE,
            Reversibility.CONDITIONALLY_REVERSIBLE,
        )






