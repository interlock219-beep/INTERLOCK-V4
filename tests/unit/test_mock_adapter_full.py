"""Tests for MockRecoveryAdapter covering all scenarios and branches."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.domain.entities.protected_action import (
    ActionStatus,
    ProtectedAction,
    Reversibility,
)
from app.domain.entities.surgical_recovery_types import (
    ConflictStatus,
    DriftStatus,
    ExecutionState,
    RecoveryEvidence,
    SimulationLimitation,
)
from app.infrastructure.recovery.mock_adapter import MockRecoveryAdapter


def _make_action(
    action_id: str = "act-1",
    reversibility: Reversibility = Reversibility.AUTOMATICALLY_REVERSIBLE,
    before_state_ref: str | None = "state:before:123",
    after_state_ref: str | None = "state:after:456",
    resource: str = "record:1",
    tool_arguments: dict | None = None,
) -> ProtectedAction:
    return ProtectedAction(
        action_id=action_id,
        tenant_id="test-tenant",
        actor_user_id=uuid4(),
        agent_id="agent-1",
        authority_grant_id=None,
        tool="database",
        resource=resource,
        action_type="insert",
        reversibility=reversibility,
        parent_action_id=None,
        correlation_id="corr-1",
        tool_arguments=tool_arguments if tool_arguments is not None else {"key": "value"},
        before_state_ref=before_state_ref,
        after_state_ref=after_state_ref,
        policy_version="v1",
        status=ActionStatus.EXECUTED,
    )


class TestMockAdapterCanRecover:
    @pytest.mark.asyncio
    async def test_can_recover_irreversible(self):
        adapter = MockRecoveryAdapter()
        action = _make_action(reversibility=Reversibility.IRREVERSIBLE)
        result = await adapter.can_recover(action)
        assert result == "irreversible"

    @pytest.mark.asyncio
    async def test_can_recover_manually_recoverable(self):
        adapter = MockRecoveryAdapter()
        action = _make_action(reversibility=Reversibility.MANUALLY_RECOVERABLE)
        result = await adapter.can_recover(action)
        assert result == "requires_approval"

    @pytest.mark.asyncio
    async def test_can_recover_reversible_with_before_state(self):
        adapter = MockRecoveryAdapter()
        action = _make_action(reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE)
        result = await adapter.can_recover(action)
        assert result == "reversible"

    @pytest.mark.asyncio
    async def test_can_recover_unknown_without_before_state(self):
        adapter = MockRecoveryAdapter()
        action = _make_action(
            reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
            before_state_ref=None,
        )
        result = await adapter.can_recover(action)
        assert result == "unknown"


class TestMockAdapterCaptureEvidence:
    @pytest.mark.asyncio
    async def test_capture_evidence_with_before_state(self):
        adapter = MockRecoveryAdapter()
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        assert evidence.evidence_id == "ev-act-1"
        assert evidence.action_id == "act-1"
        assert evidence.before_state_reference == "state:before:123"
        assert evidence.after_state_reference == "state:after:456"
        assert evidence.tenant_id == "test-tenant"
        assert evidence.agent_id == "agent-1"

    @pytest.mark.asyncio
    async def test_capture_evidence_without_before_state(self):
        adapter = MockRecoveryAdapter()
        action = _make_action(before_state_ref=None, after_state_ref=None)
        evidence = await adapter.capture_recovery_evidence(action)
        assert evidence.before_state_reference == "mock:act-1:before"
        assert evidence.after_state_reference == "mock:act-1:after"

    @pytest.mark.asyncio
    async def test_capture_evidence_computes_hash(self):
        adapter = MockRecoveryAdapter()
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        assert evidence.evidence_hash is not None
        assert len(evidence.evidence_hash) == 64

    @pytest.mark.asyncio
    async def test_capture_evidence_with_parent_action(self):
        adapter = MockRecoveryAdapter()
        action = _make_action()
        action = ProtectedAction(
            action_id="act-1",
            tenant_id="test-tenant",
            actor_user_id=uuid4(),
            agent_id="agent-1",
            authority_grant_id=None,
            tool="database",
            resource="record:1",
            action_type="insert",
            reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
            parent_action_id="parent-1",
            correlation_id="corr-1",
            tool_arguments={"key": "value"},
            before_state_ref="state:before:123",
            after_state_ref="state:after:456",
            policy_version="v1",
            status=ActionStatus.EXECUTED,
        )
        evidence = await adapter.capture_recovery_evidence(action)
        assert evidence.parent_action_id == "parent-1"
        assert evidence.root_action_id == "parent-1"


class TestMockAdapterClassifyReversibility:
    @pytest.mark.asyncio
    async def test_classify_irreversible(self):
        adapter = MockRecoveryAdapter()
        action = _make_action(reversibility=Reversibility.IRREVERSIBLE)
        evidence = await adapter.capture_recovery_evidence(action)
        result = await adapter.classify_reversibility(action, evidence)
        assert result == Reversibility.IRREVERSIBLE

    @pytest.mark.asyncio
    async def test_classify_unknown_reversibility_scenario(self):
        adapter = MockRecoveryAdapter(scenario="unknown_reversibility")
        action = _make_action(reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE)
        evidence = await adapter.capture_recovery_evidence(action)
        result = await adapter.classify_reversibility(action, evidence)
        assert result == Reversibility.UNKNOWN

    @pytest.mark.asyncio
    async def test_classify_automatic_with_before_state(self):
        adapter = MockRecoveryAdapter()
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        result = await adapter.classify_reversibility(action, evidence)
        assert result == Reversibility.AUTOMATICALLY_REVERSIBLE

    @pytest.mark.asyncio
    async def test_classify_conditional_without_before_state(self):
        adapter = MockRecoveryAdapter()
        action = _make_action(before_state_ref=None, after_state_ref=None)
        evidence = await adapter.capture_recovery_evidence(action)
        evidence = RecoveryEvidence(
            evidence_id=evidence.evidence_id,
            action_id=evidence.action_id,
            tenant_id=evidence.tenant_id,
            agent_id=evidence.agent_id,
            authority_grant_id=evidence.authority_grant_id,
            parent_action_id=evidence.parent_action_id,
            root_action_id=evidence.root_action_id,
            correlation_id=evidence.correlation_id,
            incident_id=evidence.incident_id,
            target_system=evidence.target_system,
            target_resource=evidence.target_resource,
            action_type=evidence.action_type,
            before_state_reference=None,
            after_state_reference=evidence.after_state_reference,
            compensation_payload=evidence.compensation_payload,
            compensation_type=evidence.compensation_type,
            recovery_adapter_type=evidence.recovery_adapter_type,
            idempotency_key=evidence.idempotency_key,
            dependency_edges=evidence.dependency_edges,
            reversibility_classification=Reversibility.UNKNOWN,
        )
        result = await adapter.classify_reversibility(action, evidence)
        assert result == Reversibility.CONDITIONALLY_REVERSIBLE


class TestMockAdapterSimulate:
    @pytest.mark.asyncio
    async def test_simulate_success(self):
        adapter = MockRecoveryAdapter()
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        result = await adapter.simulate(action, evidence)
        assert result.would_succeed is True
        assert result.simulation_limitation == SimulationLimitation.SIMULATION_COMPLETE

    @pytest.mark.asyncio
    async def test_simulate_irreversible_fails(self):
        adapter = MockRecoveryAdapter()
        action = _make_action(reversibility=Reversibility.IRREVERSIBLE)
        evidence = await adapter.capture_recovery_evidence(action)
        result = await adapter.simulate(action, evidence)
        assert result.would_succeed is False
        assert result.simulation_limitation == SimulationLimitation.SIMULATION_LIMITED

    @pytest.mark.asyncio
    async def test_simulate_force_fail_scenario(self):
        adapter = MockRecoveryAdapter(scenario="force_fail")
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        result = await adapter.simulate(action, evidence)
        assert result.would_succeed is False

    @pytest.mark.asyncio
    async def test_simulate_unknown_reversibility_warning(self):
        adapter = MockRecoveryAdapter(scenario="unknown_reversibility")
        action = _make_action(before_state_ref="state:before:123")
        evidence = await adapter.capture_recovery_evidence(action)
        result = await adapter.simulate(action, evidence)
        assert any("UNKNOWN" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_simulate_no_before_state_warning(self):
        adapter = MockRecoveryAdapter()
        action = _make_action(
            before_state_ref=None,
            after_state_ref="state:after:455",
        )
        evidence = await adapter.capture_recovery_evidence(action)
        evidence = RecoveryEvidence(
            evidence_id=evidence.evidence_id,
            action_id=evidence.action_id,
            tenant_id=evidence.tenant_id,
            agent_id=evidence.agent_id,
            authority_grant_id=evidence.authority_grant_id,
            parent_action_id=evidence.parent_action_id,
            root_action_id=evidence.root_action_id,
            correlation_id=evidence.correlation_id,
            incident_id=evidence.incident_id,
            target_system=evidence.target_system,
            target_resource=evidence.target_resource,
            action_type=evidence.action_type,
            before_state_reference=None,
            after_state_reference=evidence.after_state_reference,
            compensation_payload=evidence.compensation_payload,
            compensation_type=evidence.compensation_type,
            recovery_adapter_type=evidence.recovery_adapter_type,
            idempotency_key=evidence.idempotency_key,
            dependency_edges=evidence.dependency_edges,
            reversibility_classification=Reversibility.UNKNOWN,
        )
        result = await adapter.simulate(action, evidence)
        assert any("No before-state" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_simulate_drift_blocks(self):
        adapter = MockRecoveryAdapter(scenario="drift_detected")
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        result = await adapter.simulate(action, evidence)
        assert result.would_succeed is False
        assert result.drift_status == DriftStatus.DRIFT_DETECTED

    @pytest.mark.asyncio
    async def test_simulate_conflict_blocks(self):
        adapter = MockRecoveryAdapter(scenario="conflict_detected")
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        result = await adapter.simulate(action, evidence)
        assert result.would_succeed is False
        assert result.conflict_status == ConflictStatus.CONFLICT_DETECTED

    @pytest.mark.asyncio
    async def test_simulate_version_mismatch(self):
        adapter = MockRecoveryAdapter(scenario="version_mismatch")
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        result = await adapter.simulate(action, evidence)
        assert result.would_succeed is False


class TestMockAdapterCheckPreconditions:
    @pytest.mark.asyncio
    async def test_preconditions_satisfied(self):
        adapter = MockRecoveryAdapter()
        action = _make_action()
        result = await adapter.check_preconditions(action)
        assert result.satisfied is True

    @pytest.mark.asyncio
    async def test_preconditions_with_current_state(self):
        adapter = MockRecoveryAdapter()
        action = _make_action()
        result = await adapter.check_preconditions(action, current_state={"key": "val"})
        assert result.satisfied is True


class TestMockAdapterDetectDrift:
    @pytest.mark.asyncio
    async def test_no_drift(self):
        adapter = MockRecoveryAdapter()
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        result = await adapter.detect_drift(action, evidence)
        assert result.status == DriftStatus.NO_DRIFT

    @pytest.mark.asyncio
    async def test_drift_detected_scenario(self):
        adapter = MockRecoveryAdapter(scenario="drift_detected")
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        result = await adapter.detect_drift(action, evidence)
        assert result.status == DriftStatus.DRIFT_DETECTED
        assert "drift" in result.details["reason"].lower()

    @pytest.mark.asyncio
    async def test_version_mismatch_scenario(self):
        adapter = MockRecoveryAdapter(scenario="version_mismatch")
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        result = await adapter.detect_drift(action, evidence)
        assert result.status == DriftStatus.VERSION_MISMATCH

    @pytest.mark.asyncio
    async def test_detect_drift_with_current_state(self):
        adapter = MockRecoveryAdapter()
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        current = {"field": "value"}
        result = await adapter.detect_drift(action, evidence, current_state=current)
        assert result.current_state == current


class TestMockAdapterCheckConflicts:
    @pytest.mark.asyncio
    async def test_no_conflict(self):
        adapter = MockRecoveryAdapter()
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        result = await adapter.check_conflicts(action, evidence)
        assert result.status == ConflictStatus.NO_CONFLICT

    @pytest.mark.asyncio
    async def test_conflict_detected_scenario(self):
        adapter = MockRecoveryAdapter(scenario="conflict_detected")
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        result = await adapter.check_conflicts(action, evidence)
        assert result.status == ConflictStatus.CONFLICT_DETECTED

    @pytest.mark.asyncio
    async def test_conflict_version_mismatch(self):
        adapter = MockRecoveryAdapter(scenario="version_mismatch")
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        result = await adapter.check_conflicts(action, evidence)
        assert result.status == ConflictStatus.VERSION_MISMATCH

    @pytest.mark.asyncio
    async def test_check_conflicts_with_current_state(self):
        adapter = MockRecoveryAdapter()
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        result = await adapter.check_conflicts(action, evidence, current_state={"k": "v"})
        assert result.status == ConflictStatus.NO_CONFLICT


class TestMockAdapterGenerateCompensation:
    @pytest.mark.asyncio
    async def test_generate_compensation(self):
        adapter = MockRecoveryAdapter()
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        result = await adapter.generate_compensation(action, evidence)
        assert result.action_id == "act-1"
        assert result.compensation_payload == {"operation": "mock_revert", "target": "record:1"}
        assert result.target_system == "mock"
        assert result.target_resource == "record:1"


class TestMockAdapterExecuteCompensation:
    @pytest.mark.asyncio
    async def test_execute_success(self):
        adapter = MockRecoveryAdapter()
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        comp = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(comp, comp.idempotency_key)
        assert result.success is False
        assert result.execution_state == ExecutionState.REQUIRES_MANUAL_ACTION

    @pytest.mark.asyncio
    async def test_execute_idempotency_mismatch(self):
        adapter = MockRecoveryAdapter()
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        comp = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(comp, "wrong-key")
        assert result.success is False
        assert result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT
        assert "mismatch" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_force_fail(self):
        adapter = MockRecoveryAdapter(scenario="execute_fail")
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        comp = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(comp, comp.idempotency_key)
        assert result.success is False
        assert result.execution_state == ExecutionState.FAILED

    @pytest.mark.asyncio
    async def test_execute_blocked_by_drift(self):
        adapter = MockRecoveryAdapter(scenario="drift_detected")
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        comp = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(comp, comp.idempotency_key)
        assert result.success is False
        assert result.execution_state == ExecutionState.BLOCKED_BY_DRIFT

    @pytest.mark.asyncio
    async def test_execute_blocked_by_conflict(self):
        adapter = MockRecoveryAdapter(scenario="conflict_detected")
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        comp = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(comp, comp.idempotency_key)
        assert result.success is False
        assert result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT

    @pytest.mark.asyncio
    async def test_execute_returns_external_outcome(self):
        adapter = MockRecoveryAdapter()
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        comp = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(comp, comp.idempotency_key)
        assert result.external_outcome == "mock_not_implemented"


class TestMockAdapterVerify:
    @pytest.mark.asyncio
    async def test_verify_success(self):
        adapter = MockRecoveryAdapter()
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        comp = await adapter.generate_compensation(action, evidence)
        result = await adapter.verify(comp)
        assert result.verified is False
        assert result.action_id == "act-1"


class TestMockAdapterPreviewRecovery:
    @pytest.mark.asyncio
    async def test_preview_recovery(self):
        adapter = MockRecoveryAdapter()
        action = _make_action()
        result = await adapter.preview_recovery(action)
        assert result["adapter"] == "mock"
        assert result["action_id"] == "act-1"
        assert result["reversible"] is True
        assert result["mock"] is True

    @pytest.mark.asyncio
    async def test_preview_recovery_conditional(self):
        adapter = MockRecoveryAdapter()
        action = _make_action(reversibility=Reversibility.CONDITIONALLY_REVERSIBLE)
        result = await adapter.preview_recovery(action)
        assert result["requires_approval"] is True

    @pytest.mark.asyncio
    async def test_preview_recovery_without_before_state(self):
        adapter = MockRecoveryAdapter()
        action = _make_action(before_state_ref=None)
        result = await adapter.preview_recovery(action)
        assert result["reversible"] is False


class TestMockAdapterExecuteRecovery:
    @pytest.mark.asyncio
    async def test_execute_recovery(self):
        adapter = MockRecoveryAdapter()
        action = _make_action()
        result = await adapter.execute_recovery(action, "user@example.com")
        assert result["adapter"] == "mock"
        assert result["action_id"] == "act-1"
        assert result["status"] == "restored"
        assert result["mock"] is True
        assert result["executed_by"] == "user@example.com"
        assert result["before_state_ref"] == "state:before:123"
