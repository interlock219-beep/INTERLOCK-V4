"""Tests for RecoverySimulationEngine, RecoveryConfidenceModel, and adapter capabilities."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from app.domain.entities.causal_state_types import (
    CheckpointStrategy,
    ConfidenceLevel,
    MergeSafety,
    StateCheckpoint,
)
from app.domain.entities.protected_action import (
    ActionStatus,
    ProtectedAction,
    Reversibility,
)
from app.domain.entities.surgical_recovery_types import (
    AdapterCapability,
    CompensationType,
    DriftStatus,
    RecoveryAdapterType,
    RecoveryEvidence,
)
from app.domain.services.recovery_confidence_model import RecoveryConfidenceModel
from app.domain.services.recovery_simulation_engine import RecoverySimulationEngine
from app.infrastructure.recovery.mock_adapter import MockRecoveryAdapter


def _make_action(
    action_id: str,
    tenant_id: str = "test-tenant",
    reversibility: Reversibility = Reversibility.AUTOMATICALLY_REVERSIBLE,
    before_state_ref: str | None = "state:before:123",
    resource: str = "record:1",
) -> ProtectedAction:
    return ProtectedAction(
        action_id=action_id,
        tenant_id=tenant_id,
        actor_user_id=uuid4(),
        agent_id="agent-1",
        authority_grant_id=None,
        tool="database",
        resource=resource,
        action_type="insert",
        reversibility=reversibility,
        parent_action_id=None,
        before_state_ref=before_state_ref,
        after_state_ref="state:after:456" if before_state_ref else None,
        status=ActionStatus.EXECUTED,
    )


def _make_evidence(
    action_id: str,
    tenant_id: str = "test-tenant",
    before_ref: str | None = "state:before:123",
    after_ref: str | None = "state:after:456",
    target_system: str = "database",
    target_resource: str = "record:1",
    reversibility: Reversibility = Reversibility.AUTOMATICALLY_REVERSIBLE,
    state_version: str | None = "v1",
    resource_version: str | None = "v1",
) -> RecoveryEvidence:
    return RecoveryEvidence(
        evidence_id=f"ev-{action_id}",
        action_id=action_id,
        tenant_id=tenant_id,
        agent_id="agent-1",
        authority_grant_id=None,
        parent_action_id=None,
        root_action_id=action_id,
        correlation_id="corr-1",
        incident_id="inc-1",
        target_system=target_system,
        target_resource=target_resource,
        action_type="insert",
        before_state_reference=before_ref,
        after_state_reference=after_ref,
        compensation_payload={"op": "restore"},
        compensation_type=CompensationType.REVERSE_OPERATION,
        recovery_adapter_type=RecoveryAdapterType.DATABASE_RECORD,
        idempotency_key=f"idem-{action_id}",
        dependency_edges=[],
        reversibility_classification=reversibility,
        state_version=state_version,
        resource_version=resource_version,
        evidence_hash=f"hash-{action_id}",
        adapter_capability=AdapterCapability.REFERENCE_IMPLEMENTATION,
    )


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


class MockConfidenceRepo:
    def __init__(self) -> None:
        self._items: dict[str, Any] = {}

    async def get_by_confidence_id(
        self, tenant_id: str, confidence_id: str
    ) -> Any | None:
        c = self._items.get(confidence_id)
        if c and c.tenant_id == tenant_id:
            return c
        return None

    async def get_by_plan(self, tenant_id: str, plan_id: str) -> Any | None:
        for c in self._items.values():
            if c.tenant_id == tenant_id and c.plan_id == plan_id:
                return c
        return None

    async def save(self, confidence: Any) -> Any:
        self._items[confidence.confidence_id] = confidence
        return confidence


class TestRecoverySimulationEngine:
    @pytest.mark.asyncio
    async def test_simulate_recoverable_action(self) -> None:
        action = _make_action("root")
        evidence = [_make_evidence("root")]
        cp = StateCheckpoint(
            checkpoint_id="cp-1",
            tenant_id="test-tenant",
            action_id="root",
            agent_id="agent-1",
            resource_id="record:1",
            resource_type="database_record",
            strategy=CheckpointStrategy.FULL_STATE,
            recoverable_fields={"role": "viewer"},
            checkpoint_hash="hash",
        )
        evidence_repo = MockEvidenceRepo(evidence)
        checkpoint_repo = MockCheckpointRepo([cp])
        adapter = MockRecoveryAdapter(scenario="success")
        engine = RecoverySimulationEngine(evidence_repo, checkpoint_repo, [adapter])

        result = await engine.simulate_recovery("test-tenant", [action])

        assert result["dry_run"] is True
        assert result["total_resources"] == 1
        assert result["recoverable_resources"] == 1
        sim = result["resource_simulations"]["root"]
        assert sim["simulation_status"] == "recoverable"
        assert sim["proposed_recovery"] == "restore_before_state"

    @pytest.mark.asyncio
    async def test_simulate_irreversible_action(self) -> None:
        action = _make_action("root", reversibility=Reversibility.IRREVERSIBLE)
        evidence = [_make_evidence("root", reversibility=Reversibility.IRREVERSIBLE)]
        evidence_repo = MockEvidenceRepo(evidence)
        checkpoint_repo = MockCheckpointRepo()
        engine = RecoverySimulationEngine(evidence_repo, checkpoint_repo, [])

        result = await engine.simulate_recovery("test-tenant", [action])

        sim = result["resource_simulations"]["root"]
        assert sim["simulation_status"] == "irreversible"
        assert sim["approval_requirement"] == "irreversible"

    @pytest.mark.asyncio
    async def test_simulate_unknown_reversibility(self) -> None:
        action = _make_action("root", reversibility=Reversibility.UNKNOWN)
        evidence = [_make_evidence("root", reversibility=Reversibility.UNKNOWN)]
        evidence_repo = MockEvidenceRepo(evidence)
        checkpoint_repo = MockCheckpointRepo()
        engine = RecoverySimulationEngine(evidence_repo, checkpoint_repo, [])

        result = await engine.simulate_recovery("test-tenant", [action])

        sim = result["resource_simulations"]["root"]
        assert sim["simulation_status"] == "unknown_reversibility"

    @pytest.mark.asyncio
    async def test_simulate_no_evidence(self) -> None:
        action = _make_action("root")
        evidence_repo = MockEvidenceRepo([])
        checkpoint_repo = MockCheckpointRepo()
        engine = RecoverySimulationEngine(evidence_repo, checkpoint_repo, [])

        result = await engine.simulate_recovery("test-tenant", [action])

        sim = result["resource_simulations"]["root"]
        assert sim["simulation_status"] == "no_evidence"

    @pytest.mark.asyncio
    async def test_simulate_drift_blocks_recovery(self) -> None:
        action = _make_action("root")
        evidence = [_make_evidence("root")]
        evidence_repo = MockEvidenceRepo(evidence)
        checkpoint_repo = MockCheckpointRepo()
        adapter = MockRecoveryAdapter(scenario="drift_detected")
        engine = RecoverySimulationEngine(evidence_repo, checkpoint_repo, [adapter])

        result = await engine.simulate_recovery("test-tenant", [action])

        sim = result["resource_simulations"]["root"]
        assert sim["simulation_status"] == "blocked_by_drift"
        assert sim["drift_status"] == DriftStatus.DRIFT_DETECTED.value

    @pytest.mark.asyncio
    async def test_simulate_conflict_blocks_recovery(self) -> None:
        action = _make_action("root")
        evidence = [_make_evidence("root")]
        evidence_repo = MockEvidenceRepo(evidence)
        checkpoint_repo = MockCheckpointRepo()
        adapter = MockRecoveryAdapter(scenario="conflict_detected")
        engine = RecoverySimulationEngine(evidence_repo, checkpoint_repo, [adapter])

        result = await engine.simulate_recovery("test-tenant", [action])

        sim = result["resource_simulations"]["root"]
        assert sim["simulation_status"] == "blocked_by_conflict"

    @pytest.mark.asyncio
    async def test_simulate_multiple_resources(self) -> None:
        action1 = _make_action("root", resource="record:1")
        action2 = _make_action("child", resource="record:2")
        evidence = [_make_evidence("root"), _make_evidence("child")]
        evidence_repo = MockEvidenceRepo(evidence)
        checkpoint_repo = MockCheckpointRepo()
        adapter = MockRecoveryAdapter(scenario="success")
        engine = RecoverySimulationEngine(evidence_repo, checkpoint_repo, [adapter])

        result = await engine.simulate_recovery("test-tenant", [action1, action2])

        assert result["total_resources"] == 2
        assert result["recoverable_resources"] == 2
        assert result["approval_requirement"] == "safe_for_automatic"

    @pytest.mark.asyncio
    async def test_simulate_never_mutates_state(self) -> None:
        action = _make_action("root")
        evidence = [_make_evidence("root")]
        evidence_repo = MockEvidenceRepo(evidence)
        checkpoint_repo = MockCheckpointRepo()
        adapter = MockRecoveryAdapter(scenario="success")
        engine = RecoverySimulationEngine(evidence_repo, checkpoint_repo, [adapter])

        await engine.simulate_recovery("test-tenant", [action])

        assert adapter._scenario == "success"


class TestRecoveryConfidenceModel:
    @pytest.mark.asyncio
    async def test_high_confidence(self) -> None:
        actions = [_make_action("a1"), _make_action("a2")]
        evidence = [_make_evidence("a1"), _make_evidence("a2")]
        evidence_repo = MockEvidenceRepo(evidence)
        confidence_repo = MockConfidenceRepo()
        model = RecoveryConfidenceModel(confidence_repo, evidence_repo)

        result = await model.assess_confidence("test-tenant", "plan-1", actions)

        assert result.level == ConfidenceLevel.HIGH_CONFIDENCE
        assert result.before_state_available is True
        assert result.after_state_available is True
        assert result.adapter_support is True
        assert result.evidence_completeness == 1.0

    @pytest.mark.asyncio
    async def test_low_confidence_with_irreversible(self) -> None:
        actions = [
            _make_action("a1", reversibility=Reversibility.IRREVERSIBLE),
            _make_action("a2"),
        ]
        evidence = [
            _make_evidence("a1", reversibility=Reversibility.IRREVERSIBLE),
            _make_evidence("a2"),
        ]
        evidence_repo = MockEvidenceRepo(evidence)
        confidence_repo = MockConfidenceRepo()
        model = RecoveryConfidenceModel(confidence_repo, evidence_repo)

        result = await model.assess_confidence("test-tenant", "plan-1", actions)

        assert result.level in (
            ConfidenceLevel.LOW_CONFIDENCE,
            ConfidenceLevel.INSUFFICIENT_EVIDENCE,
        )
        assert any("irreversible" in f.lower() for f in result.factors)

    @pytest.mark.asyncio
    async def test_insufficient_evidence_no_evidence(self) -> None:
        actions = [_make_action("a1"), _make_action("a2")]
        evidence_repo = MockEvidenceRepo([])
        confidence_repo = MockConfidenceRepo()
        model = RecoveryConfidenceModel(confidence_repo, evidence_repo)

        result = await model.assess_confidence("test-tenant", "plan-1", actions)

        assert result.level == ConfidenceLevel.INSUFFICIENT_EVIDENCE
        assert result.evidence_completeness == 0.0

    @pytest.mark.asyncio
    async def test_confidence_explains_why(self) -> None:
        actions = [_make_action("a1")]
        evidence = [_make_evidence("a1")]
        evidence_repo = MockEvidenceRepo(evidence)
        confidence_repo = MockConfidenceRepo()
        model = RecoveryConfidenceModel(confidence_repo, evidence_repo)

        result = await model.assess_confidence("test-tenant", "plan-1", actions)

        assert len(result.factors) > 0
        assert any("before_state" in f for f in result.factors)

    @pytest.mark.asyncio
    async def test_confidence_with_recommendations(self) -> None:
        actions = [_make_action("a1", before_state_ref=None)]
        evidence = [_make_evidence("a1", before_ref=None)]
        evidence_repo = MockEvidenceRepo(evidence)
        confidence_repo = MockConfidenceRepo()
        model = RecoveryConfidenceModel(confidence_repo, evidence_repo)

        result = await model.assess_confidence("test-tenant", "plan-1", actions)

        assert len(result.recommendations) > 0

    @pytest.mark.asyncio
    async def test_empty_actions_insufficient(self) -> None:
        evidence_repo = MockEvidenceRepo([])
        confidence_repo = MockConfidenceRepo()
        model = RecoveryConfidenceModel(confidence_repo, evidence_repo)

        result = await model.assess_confidence("test-tenant", "plan-1", [])

        assert result.level == ConfidenceLevel.INSUFFICIENT_EVIDENCE


class TestAdapterCapabilityDeclarations:
    @pytest.mark.asyncio
    async def test_mock_adapter_declares_full_capabilities(self) -> None:
        adapter = MockRecoveryAdapter()
        decl = await adapter.declare_capabilities()

        assert decl.adapter_name == "mock"
        assert decl.can_capture_before_state is True
        assert decl.can_simulate is True
        assert decl.can_compensate is True
        assert decl.can_verify is True
        assert decl.supports_idempotency is True
        assert decl.supports_safe_merge is True
        assert decl.merge_safety == MergeSafety.MERGE_SAFE

    @pytest.mark.asyncio
    async def test_database_adapter_declares_capabilities(self) -> None:
        from app.infrastructure.recovery.database_record_adapter import DatabaseRecordAdapter

        adapter = DatabaseRecordAdapter()
        decl = await adapter.declare_capabilities()

        assert decl.adapter_name == "database_record"
        assert decl.can_compensate is True
        assert decl.can_verify is True
        assert decl.supports_safe_merge is False
        assert decl.merge_safety == MergeSafety.MERGE_CONDITIONAL

    @pytest.mark.asyncio
    async def test_config_adapter_declares_limited_capabilities(self) -> None:
        from app.infrastructure.recovery.config_rollback_adapter import ConfigRollbackAdapter

        adapter = ConfigRollbackAdapter()
        decl = await adapter.declare_capabilities()

        assert decl.adapter_name == "config_rollback"
        assert decl.can_read_current_state is False
        assert decl.can_detect_drift is False
        assert decl.merge_safety == MergeSafety.MERGE_UNSUPPORTED

    @pytest.mark.asyncio
    async def test_file_adapter_declares_capabilities(self) -> None:
        from app.infrastructure.recovery.file_version_adapter import FileVersionAdapter

        adapter = FileVersionAdapter()
        decl = await adapter.declare_capabilities()

        assert decl.adapter_name == "file_version"
        assert decl.can_compensate is True
        assert decl.supports_versioning is True
        assert decl.merge_safety == MergeSafety.MERGE_UNSUPPORTED
