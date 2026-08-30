"""Phase 4, 5, 6 — Complex Causal Recovery, Conflicts, and Partial Failure.

Tests:
- Chained dependencies (A -> B -> C -> D)
- Branching scenarios
- Conflict detection (human modifies same resource)
- Partial failure during recovery
- Recovery state classification accuracy
"""

from __future__ import annotations

import pytest

from app.domain.entities.causal_state_types import (
    CheckpointStrategy,
    StateCheckpoint,
)
from app.domain.entities.protected_action import (
    Reversibility,
)
from app.domain.entities.surgical_recovery_types import (
    ConflictStatus,
    DriftStatus,
    ExecutionState,
    RecoveryEvidence,
)
from app.domain.services.recovery_simulation_engine import RecoverySimulationEngine
from app.infrastructure.recovery.mock_adapter import MockRecoveryAdapter
from tests.unit.recovery_lab.factories import make_action, make_evidence


class MockEvidenceRepo:
    def __init__(self, evidence_list: list[RecoveryEvidence]) -> None:
        self._evidence = {e.action_id: e for e in evidence_list}

    async def get_by_action_id(
        self, tenant_id: str, action_id: str
    ) -> RecoveryEvidence | None:
        ev = self._evidence.get(action_id)
        if ev and ev.tenant_id == tenant_id:
            return ev
        return None

    async def get_by_evidence_id(
        self, tenant_id: str, evidence_id: str
    ) -> RecoveryEvidence | None:
        for ev in self._evidence.values():
            if ev.evidence_id == evidence_id and ev.tenant_id == tenant_id:
                return ev
        return None

    async def list_by_incident(
        self, tenant_id: str, incident_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[RecoveryEvidence], int]:
        items = [
            e for e in self._evidence.values()
            if e.tenant_id == tenant_id and e.incident_id == incident_id
        ]
        return items[offset:offset + limit], len(items)

    async def list_by_root_action(
        self, tenant_id: str, root_action_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[RecoveryEvidence], int]:
        items = [
            e for e in self._evidence.values()
            if e.tenant_id == tenant_id and e.root_action_id == root_action_id
        ]
        return items[offset:offset + limit], len(items)

    async def save(self, evidence: RecoveryEvidence) -> RecoveryEvidence:
        self._evidence[evidence.action_id] = evidence
        return evidence


class MockCheckpointRepo:
    def __init__(self, checkpoints: list[StateCheckpoint] | None = None) -> None:
        self._items: dict[str, StateCheckpoint] = {
            cp.checkpoint_id: cp for cp in (checkpoints or [])
        }

    async def get_by_checkpoint_id(
        self, tenant_id: str, checkpoint_id: str
    ) -> StateCheckpoint | None:
        cp = self._items.get(checkpoint_id)
        if cp and cp.tenant_id == tenant_id:
            return cp
        return None

    async def get_by_action_id(
        self, tenant_id: str, action_id: str
    ) -> StateCheckpoint | None:
        for cp in self._items.values():
            if cp.tenant_id == tenant_id and cp.action_id == action_id:
                return cp
        return None

    async def list_by_resource(
        self, tenant_id: str, resource_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[StateCheckpoint], int]:
        items = [
            cp for cp in self._items.values()
            if cp.tenant_id == tenant_id and cp.resource_id == resource_id
        ]
        return items[offset:offset + limit], len(items)

    async def save(self, checkpoint: StateCheckpoint) -> StateCheckpoint:
        self._items[checkpoint.checkpoint_id] = checkpoint
        return checkpoint


class TestPhase4ChainedDependencies:
    """Test recovery of chained dependencies A -> B -> C -> D."""

    @pytest.mark.asyncio
    async def test_linear_chain_simulation(self) -> None:
        actions = [
            make_action("a", parent_action_id=None),
            make_action("b", parent_action_id="a"),
            make_action("c", parent_action_id="b"),
            make_action("d", parent_action_id="c"),
        ]
        evidence = [make_evidence(a) for a in actions]
        checkpoints = [
            StateCheckpoint(
                checkpoint_id=f"cp-{a.action_id}",
                tenant_id="test-tenant",
                action_id=a.action_id,
                agent_id="agent-1",
                resource_id=a.resource,
                resource_type="database_record",
                strategy=CheckpointStrategy.FULL_STATE,
                recoverable_fields={"value": a.action_id},
                checkpoint_hash=f"hash-{a.action_id}",
            )
            for a in actions
        ]

        engine = RecoverySimulationEngine(
            MockEvidenceRepo(evidence),
            MockCheckpointRepo(checkpoints),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", actions)

        assert result["total_resources"] == 4
        assert result["recoverable_resources"] == 4
        assert result["approval_requirement"] == "safe_for_automatic"

    @pytest.mark.asyncio
    async def test_chain_with_irreversible_leaf(self) -> None:
        actions = [
            make_action("a", parent_action_id=None),
            make_action("b", parent_action_id="a"),
            make_action("c", parent_action_id="b"),
            make_action("d", parent_action_id="c", reversibility=Reversibility.IRREVERSIBLE),
        ]
        evidence = [make_evidence(a) for a in actions]

        engine = RecoverySimulationEngine(
            MockEvidenceRepo(evidence),
            MockCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", actions)

        assert result["total_resources"] == 4
        d_sim = result["resource_simulations"]["d"]
        assert d_sim["simulation_status"] == "irreversible"


class TestPhase4Branching:
    """Test recovery with branching scenarios."""

    @pytest.mark.asyncio
    async def test_branching_all_recoverable(self) -> None:
        actions = [
            make_action("root", parent_action_id=None),
            make_action("branch_a", parent_action_id="root"),
            make_action("branch_b", parent_action_id="root"),
            make_action("branch_c", parent_action_id="root"),
        ]
        evidence = [make_evidence(a) for a in actions]

        engine = RecoverySimulationEngine(
            MockEvidenceRepo(evidence),
            MockCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", actions)

        assert result["total_resources"] == 4
        assert result["recoverable_resources"] == 4

    @pytest.mark.asyncio
    async def test_branching_one_irreversible(self) -> None:
        actions = [
            make_action("root", parent_action_id=None),
            make_action("branch_a", parent_action_id="root"),
            make_action(
                "branch_b",
                parent_action_id="root",
                reversibility=Reversibility.IRREVERSIBLE,
            ),
            make_action("branch_c", parent_action_id="root"),
        ]
        evidence = [make_evidence(a) for a in actions]

        engine = RecoverySimulationEngine(
            MockEvidenceRepo(evidence),
            MockCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", actions)

        assert result["total_resources"] == 4
        assert result["recoverable_resources"] == 3
        assert result["resource_simulations"]["branch_b"]["simulation_status"] == "irreversible"


class TestPhase5ConflictScenarios:
    """Test conflict detection and handling."""

    @pytest.mark.asyncio
    async def test_conflict_detected_blocks_recovery(self) -> None:
        action = make_action("conflict-action")
        evidence = make_evidence(action)

        engine = RecoverySimulationEngine(
            MockEvidenceRepo([evidence]),
            MockCheckpointRepo(),
            [MockRecoveryAdapter(scenario="conflict_detected")],
        )

        result = await engine.simulate_recovery("test-tenant", [action])

        sim = result["resource_simulations"]["conflict-action"]
        assert sim["simulation_status"] == "blocked_by_conflict"
        assert sim["conflict_status"] == ConflictStatus.CONFLICT_DETECTED.value

    @pytest.mark.asyncio
    async def test_drift_detected_blocks_recovery(self) -> None:
        action = make_action("drift-action")
        evidence = make_evidence(action)

        engine = RecoverySimulationEngine(
            MockEvidenceRepo([evidence]),
            MockCheckpointRepo(),
            [MockRecoveryAdapter(scenario="drift_detected")],
        )

        result = await engine.simulate_recovery("test-tenant", [action])

        sim = result["resource_simulations"]["drift-action"]
        assert sim["simulation_status"] == "blocked_by_drift"
        assert sim["drift_status"] == DriftStatus.DRIFT_DETECTED.value

    @pytest.mark.asyncio
    async def test_version_mismatch_detected(self) -> None:
        action = make_action("version-action")
        evidence = make_evidence(action)

        engine = RecoverySimulationEngine(
            MockEvidenceRepo([evidence]),
            MockCheckpointRepo(),
            [MockRecoveryAdapter(scenario="version_mismatch")],
        )

        result = await engine.simulate_recovery("test-tenant", [action])

        sim = result["resource_simulations"]["version-action"]
        assert sim["simulation_status"] in ("blocked_by_drift", "blocked_by_conflict")


class TestPhase6PartialFailure:
    """Test partial failure scenarios during recovery."""

    @pytest.mark.asyncio
    async def test_mixed_success_and_failure(self) -> None:
        actions = [
            make_action("success-1"),
            make_action("success-2"),
            make_action("fail-1", reversibility=Reversibility.IRREVERSIBLE),
            make_action("success-3"),
        ]
        evidence = [make_evidence(a) for a in actions]

        engine = RecoverySimulationEngine(
            MockEvidenceRepo(evidence),
            MockCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", actions)

        assert result["total_resources"] == 4
        assert result["recoverable_resources"] == 3
        assert result["resource_simulations"]["fail-1"]["simulation_status"] == "irreversible"

    @pytest.mark.asyncio
    async def test_adapter_execution_failure(self) -> None:
        adapter = MockRecoveryAdapter(scenario="execute_fail")
        action = make_action("exec-fail")
        evidence = make_evidence(action)

        result = await adapter.execute_compensation(
            evidence.compensation_payload and type("Compensation", (), {
                "action_id": "exec-fail",
                "idempotency_key": "idem-exec-fail",
            })(),
            "idem-exec-fail",
        )

        assert result.success is False
        assert result.execution_state == ExecutionState.FAILED

    @pytest.mark.asyncio
    async def test_no_fake_success_reported(self) -> None:
        adapter = MockRecoveryAdapter(scenario="execute_fail")

        result = await adapter.execute_compensation(
            type(
                "Comp",
                (),
                {"action_id": "no-fake-success", "idempotency_key": "idem-no-fake-success"},
            )(),
            "idem-no-fake-success",
        )

        assert result.success is False
        assert result.error is not None
        assert "Mock" in result.error or "mock" in result.error.lower()

    @pytest.mark.asyncio
    async def test_idempotency_key_mismatch_fails(self) -> None:
        adapter = MockRecoveryAdapter()
        result = await adapter.execute_compensation(
            type("Comp", (), {"action_id": "idem-test", "idempotency_key": "correct-key"})(),
            "wrong-key",
        )

        assert result.success is False
        assert result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT
        assert "Idempotency" in result.error

    @pytest.mark.asyncio
    async def test_recovery_state_classification_accuracy(self) -> None:
        test_cases = [
            ("success", "recoverable", Reversibility.AUTOMATICALLY_REVERSIBLE),
            ("drift_detected", "blocked_by_drift", Reversibility.AUTOMATICALLY_REVERSIBLE),
            ("conflict_detected", "blocked_by_conflict", Reversibility.AUTOMATICALLY_REVERSIBLE),
        ]

        for scenario, expected_status, reversibility in test_cases:
            action = make_action(f"classify-{scenario}", reversibility=reversibility)
            evidence = make_evidence(action)

            engine = RecoverySimulationEngine(
                MockEvidenceRepo([evidence]),
                MockCheckpointRepo(),
                [MockRecoveryAdapter(scenario=scenario)],
            )

            result = await engine.simulate_recovery("test-tenant", [action])
            sim = result["resource_simulations"][f"classify-{scenario}"]

            assert sim["simulation_status"] == expected_status


class TestPhase6RecoveryStates:
    """Verify all recovery states are correctly classified."""

    @pytest.mark.asyncio
    async def test_recovered_state(self) -> None:
        action = make_action("recovered", reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE)
        evidence = make_evidence(action)

        engine = RecoverySimulationEngine(
            MockEvidenceRepo([evidence]),
            MockCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", [action])
        assert result["resource_simulations"]["recovered"]["simulation_status"] == "recoverable"

    @pytest.mark.asyncio
    async def test_partially_recovered_state(self) -> None:
        actions = [
            make_action("ok-1", reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE),
            make_action("fail-1", reversibility=Reversibility.IRREVERSIBLE),
        ]
        evidence = [make_evidence(a) for a in actions]

        engine = RecoverySimulationEngine(
            MockEvidenceRepo(evidence),
            MockCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", actions)
        assert result["recoverable_resources"] == 1
        assert result["total_resources"] == 2

    @pytest.mark.asyncio
    async def test_requires_human_action_state(self) -> None:
        action = make_action("manual", reversibility=Reversibility.MANUALLY_RECOVERABLE)
        evidence = make_evidence(action)

        engine = RecoverySimulationEngine(
            MockEvidenceRepo([evidence]),
            MockCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", [action])
        sim = result["resource_simulations"]["manual"]
        assert sim["simulation_status"] in ("unknown", "manual_recovery_required")

    @pytest.mark.asyncio
    async def test_not_reversible_state(self) -> None:
        action = make_action("irreversible", reversibility=Reversibility.IRREVERSIBLE)
        evidence = make_evidence(action)

        engine = RecoverySimulationEngine(
            MockEvidenceRepo([evidence]),
            MockCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", [action])
        sim = result["resource_simulations"]["irreversible"]
        assert sim["simulation_status"] == "irreversible"

    @pytest.mark.asyncio
    async def test_unknown_state(self) -> None:
        action = make_action("unknown", reversibility=Reversibility.UNKNOWN)
        evidence = make_evidence(action)

        engine = RecoverySimulationEngine(
            MockEvidenceRepo([evidence]),
            MockCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", [action])
        sim = result["resource_simulations"]["unknown"]
        assert sim["simulation_status"] == "unknown_reversibility"
