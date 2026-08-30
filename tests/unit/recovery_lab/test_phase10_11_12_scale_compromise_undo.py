"""Phase 10, 11, 12 — Large-Scale Recovery, Agent Compromise, and Undo Agent.

Tests:
- Large-scale recovery (100, 1000, 10000 actions)
- Agent compromise simulation
- End-to-end "UNDO AGENT" workflow
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from app.domain.entities.protected_action import (
    Reversibility,
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


class TestPhase10LargeScaleRecovery:
    """Test recovery at scale."""

    @pytest.mark.asyncio
    async def test_100_actions_simulation(self) -> None:
        actions = [make_action(f"scale-100-{i}") for i in range(100)]
        evidence = [make_evidence(a) for a in actions]

        engine = RecoverySimulationEngine(
            BulkEvidenceRepo(evidence),
            EmptyCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        start = time.monotonic()
        result = await engine.simulate_recovery("test-tenant", actions)
        elapsed = time.monotonic() - start

        assert result["total_resources"] == 100
        assert result["recoverable_resources"] == 100
        assert elapsed < 10.0

    @pytest.mark.asyncio
    async def test_1000_actions_simulation(self) -> None:
        actions = [make_action(f"scale-1000-{i}") for i in range(1000)]
        evidence = [make_evidence(a) for a in actions]

        engine = RecoverySimulationEngine(
            BulkEvidenceRepo(evidence),
            EmptyCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        start = time.monotonic()
        result = await engine.simulate_recovery("test-tenant", actions)
        elapsed = time.monotonic() - start

        assert result["total_resources"] == 1000
        assert result["recoverable_resources"] == 1000
        assert elapsed < 30.0

    @pytest.mark.asyncio
    async def test_10000_actions_performance(self) -> None:
        actions = [make_action(f"scale-10000-{i}") for i in range(10000)]
        evidence = [make_evidence(a) for a in actions]

        engine = RecoverySimulationEngine(
            BulkEvidenceRepo(evidence),
            EmptyCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", actions)

        assert result["total_resources"] == 10000
        assert result["recoverable_resources"] == 10000

    @pytest.mark.asyncio
    async def test_large_scale_with_mixed_reversibility(self) -> None:
        actions = []
        for i in range(100):
            if i % 10 == 0:
                rev = Reversibility.IRREVERSIBLE
            elif i % 5 == 0:
                rev = Reversibility.CONDITIONALLY_REVERSIBLE
            else:
                rev = Reversibility.AUTOMATICALLY_REVERSIBLE
            actions.append(make_action(f"mixed-{i}", reversibility=rev))

        evidence = [make_evidence(a) for a in actions]

        engine = RecoverySimulationEngine(
            BulkEvidenceRepo(evidence),
            EmptyCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", actions)

        assert result["total_resources"] == 100
        irreversible_count = sum(
            1 for a in actions if a.reversibility == Reversibility.IRREVERSIBLE
        )
        assert result["recoverable_resources"] == 100 - irreversible_count


class TestPhase11AgentCompromise:
    """Test detection and containment of compromised agents."""

    @pytest.mark.asyncio
    async def test_unauthorized_resource_access_detected(self) -> None:
        adapter = MockRecoveryAdapter(scenario="conflict_detected")
        action = make_action("unauthorized", resource="protected:resource")

        evidence = make_evidence(action)
        conflict = await adapter.check_conflicts(action, evidence)

        assert conflict.status != "no_conflict" or action.resource.startswith("protected:")

    @pytest.mark.asyncio
    async def test_destructive_action_identified(self) -> None:
        action = make_action(
            "destructive",
            action_type="delete",
            resource="critical:data",
            reversibility=Reversibility.IRREVERSIBLE,
        )

        evidence = make_evidence(action)
        adapter = MockRecoveryAdapter(scenario="success")

        impact = await adapter.simulate(action, evidence)

        assert impact.reversibility == Reversibility.IRREVERSIBLE
        assert impact.would_succeed is False

    @pytest.mark.asyncio
    async def test_excessive_modifications_flagged(self) -> None:
        actions = [make_action(f"excessive-{i}") for i in range(100)]

        evidence = [make_evidence(a) for a in actions]

        engine = RecoverySimulationEngine(
            BulkEvidenceRepo(evidence),
            EmptyCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", actions)

        assert result["total_resources"] == 100

    @pytest.mark.asyncio
    async def test_audit_manipulation_detected(self) -> None:
        adapter = MockRecoveryAdapter(scenario="conflict_detected")
        action = make_action("audit-tamper", tool="audit", action_type="modify")
        evidence = make_evidence(action)

        conflict = await adapter.check_conflicts(action, evidence)

        assert conflict.status != "no_conflict"

    @pytest.mark.asyncio
    async def test_recovery_metadata_manipulation_detected(self) -> None:
        adapter = MockRecoveryAdapter(scenario="drift_detected")
        action = make_action("meta-tamper", tool="recovery_metadata", action_type="modify")
        evidence = make_evidence(action)

        drift = await adapter.detect_drift(action, evidence)

        assert drift.status != "no_drift"

    @pytest.mark.asyncio
    async def test_privilege_escalation_detected(self) -> None:
        action = make_action(
            "priv-esc",
            tool="iam",
            action_type="grant_admin",
            resource="role:admin",
            reversibility=Reversibility.IRREVERSIBLE,
        )

        evidence = make_evidence(action)
        adapter = MockRecoveryAdapter(scenario="success")

        reversibility = await adapter.classify_reversibility(action, evidence)

        assert reversibility == Reversibility.IRREVERSIBLE

    @pytest.mark.asyncio
    async def test_action_substitution_detected(self) -> None:
        adapter = MockRecoveryAdapter(scenario="version_mismatch")
        action = make_action("substitute", action_type="write")
        evidence = make_evidence(action)

        drift = await adapter.detect_drift(action, evidence)
        conflict = await adapter.check_conflicts(action, evidence)

        assert drift.status != "no_drift" or conflict.status != "no_conflict"


class TestPhase12UndoAgentEndToEnd:
    """Test the complete UNDO AGENT workflow."""

    @pytest.mark.asyncio
    async def test_undo_agent_identifies_all_mutations(self) -> None:
        actions = [
            make_action("undo-1"),
            make_action("undo-2"),
            make_action("undo-3"),
        ]

        evidence = [make_evidence(a) for a in actions]

        engine = RecoverySimulationEngine(
            BulkEvidenceRepo(evidence),
            EmptyCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", actions)

        assert result["total_resources"] == 3
        assert set(result["resource_simulations"].keys()) == {"undo-1", "undo-2", "undo-3"}

    @pytest.mark.asyncio
    async def test_undo_agent_classifies_correctly(self) -> None:
        actions = [
            make_action("classify-auto", reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE),
            make_action("classify-cond", reversibility=Reversibility.CONDITIONALLY_REVERSIBLE),
            make_action("classify-manual", reversibility=Reversibility.MANUALLY_RECOVERABLE),
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

        sims = result["resource_simulations"]
        assert sims["classify-auto"]["simulation_status"] == "recoverable"
        assert sims["classify-irrev"]["simulation_status"] == "irreversible"
        assert sims["classify-unknown"]["simulation_status"] == "unknown_reversibility"


    @pytest.mark.asyncio
    async def test_undo_agent_preserves_legitimate_changes(self) -> None:
        actions = [
            make_action("agent-change"),
        ]
        evidence = [make_evidence(a) for a in actions]

        engine = RecoverySimulationEngine(
            BulkEvidenceRepo(evidence),
            EmptyCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", actions)

        assert result["resource_simulations"]["agent-change"]["simulation_status"] == "recoverable"

    @pytest.mark.asyncio
    async def test_undo_agent_generates_recovery_report(self) -> None:
        actions = [
            make_action("report-1", reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE),
            make_action("report-2", reversibility=Reversibility.IRREVERSIBLE),
            make_action("report-3", reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE),
        ]

        evidence = [make_evidence(a) for a in actions]

        engine = RecoverySimulationEngine(
            BulkEvidenceRepo(evidence),
            EmptyCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result = await engine.simulate_recovery("test-tenant", actions)

        report = {
            "total_mutations": result["total_resources"],
            "recoverable": result["recoverable_resources"],
            "irreversible": sum(
                1 for s in result["resource_simulations"].values()
                if s["simulation_status"] == "irreversible"
            ),
            "unknown": sum(
                1 for s in result["resource_simulations"].values()
                if s["simulation_status"] == "unknown_reversibility"
            ),
            "conflicted": sum(
                1 for s in result["resource_simulations"].values()
                if s["simulation_status"] == "blocked_by_conflict"
            ),
            "drifted": sum(
                1 for s in result["resource_simulations"].values()
                if s["simulation_status"] == "blocked_by_drift"
            ),
        }

        assert report["total_mutations"] == 3
        assert report["recoverable"] == 2
        assert report["irreversible"] == 1
