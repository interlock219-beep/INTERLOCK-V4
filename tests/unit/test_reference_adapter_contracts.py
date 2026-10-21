"""Direct contract tests for the three reference recovery adapters.

R3 (Phase 3 remediation): `FileVersionAdapter`, `DatabaseRecordAdapter`, and
`ConfigRollbackAdapter` were declared in the capability matrix with no direct
adapter tests (only orchestrator-level coverage). These tests pin their
honesty contracts: reference implementations must refuse execution honestly
(`REQUIRES_MANUAL_ACTION`), never self-certify verification, and refuse
idempotency-key mismatches.
"""

from __future__ import annotations

import pytest

from app.domain.entities.protected_action import ActionStatus, ProtectedAction, Reversibility
from app.domain.entities.surgical_recovery_types import (
    DriftStatus,
    ExecutionState,
)
from app.infrastructure.recovery.config_rollback_adapter import ConfigRollbackAdapter
from app.infrastructure.recovery.database_record_adapter import DatabaseRecordAdapter
from app.infrastructure.recovery.file_version_adapter import FileVersionAdapter


def _make_action(
    action_id: str = "act-ref-1",
    reversibility: Reversibility = Reversibility.AUTOMATICALLY_REVERSIBLE,
    before_state_ref: str | None = "state:before:1",
    after_state_ref: str | None = "state:after:2",
    policy_version: str = "v1",
) -> ProtectedAction:
    return ProtectedAction(
        action_id=action_id,
        tenant_id="test-tenant",
        agent_id="agent-test",
        actor_user_id=None,
        authority_grant_id=None,
        tool="reference",
        resource="table:widgets",
        action_type="modify",
        risk_score=0.5,
        policy_version=policy_version,
        correlation_id="corr-1",
        parent_action_id=None,
        workflow_id=None,
        reversibility=reversibility,
        before_state_ref=before_state_ref,
        after_state_ref=after_state_ref,
        tool_arguments={},
        status=ActionStatus.EXECUTED,
        decision_reason="test",
        evaluated_at=None,
        executed_at=None,
        created_at=None,
    )


REFERENCE_ADAPTERS = [
    ("file_version", FileVersionAdapter),
    ("database_record", DatabaseRecordAdapter),
    ("config_rollback", ConfigRollbackAdapter),
]


class TestReferenceAdapterHonestyContracts:
    """Shared honesty contracts for all three reference implementations."""

    @pytest.mark.parametrize("name,adapter_cls", REFERENCE_ADAPTERS)
    @pytest.mark.asyncio
    async def test_execute_compensation_refuses_honestly(
        self, name: str, adapter_cls: type
    ) -> None:
        """A reference adapter must never claim a success it cannot perform."""
        adapter = adapter_cls()
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(
            compensation, idempotency_key=compensation.idempotency_key
        )
        assert result.success is False
        assert result.execution_state == ExecutionState.REQUIRES_MANUAL_ACTION
        assert "reference implementation" in (result.error or "")

    @pytest.mark.parametrize("name,adapter_cls", REFERENCE_ADAPTERS)
    @pytest.mark.asyncio
    async def test_verify_never_self_certifies(self, name: str, adapter_cls: type) -> None:
        adapter = adapter_cls()
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        compensation = await adapter.generate_compensation(action, evidence)
        verification = await adapter.verify(compensation)
        assert verification.verified is False

    @pytest.mark.parametrize("name,adapter_cls", REFERENCE_ADAPTERS)
    @pytest.mark.asyncio
    async def test_idempotency_key_mismatch_refused(
        self, name: str, adapter_cls: type
    ) -> None:
        adapter = adapter_cls()
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(
            compensation, idempotency_key="idem-tampered"
        )
        assert result.success is False
        assert result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT

    @pytest.mark.parametrize("name,adapter_cls", REFERENCE_ADAPTERS)
    @pytest.mark.asyncio
    async def test_precondition_missing_before_state_ref_fails(
        self, name: str, adapter_cls: type
    ) -> None:
        adapter = adapter_cls()
        action = _make_action(before_state_ref=None)
        precondition = await adapter.check_preconditions(action)
        assert precondition.satisfied is False
        assert "missing_before_state_ref" in precondition.failed_checks

    @pytest.mark.parametrize("name,adapter_cls", REFERENCE_ADAPTERS)
    @pytest.mark.asyncio
    async def test_can_recover_irreversible_is_explicit(
        self, name: str, adapter_cls: type
    ) -> None:
        adapter = adapter_cls()
        action = _make_action(reversibility=Reversibility.IRREVERSIBLE)
        assert await adapter.can_recover(action) == "irreversible"

    @pytest.mark.parametrize("name,adapter_cls", REFERENCE_ADAPTERS)
    @pytest.mark.asyncio
    async def test_declare_capabilities_matches_implementation(
        self, name: str, adapter_cls: type
    ) -> None:
        """Declared capabilities must not overclaim what execute/verify do."""
        adapter = adapter_cls()
        caps = await adapter.declare_capabilities()
        assert caps.adapter_name == name
        assert caps.can_compensate is True  # compensation pipeline is real
        assert caps.supports_idempotency is True


class TestDatabaseRecordAdapterDrift:
    """The database_record reference declares drift detection — pin its logic."""

    @pytest.mark.asyncio
    async def test_version_mismatch_detected(self) -> None:
        adapter = DatabaseRecordAdapter()
        action = _make_action(policy_version="v1")
        evidence = await adapter.capture_recovery_evidence(action)
        drift = await adapter.detect_drift(action, evidence, current_state={"version": "v2"})
        assert drift.status == DriftStatus.VERSION_MISMATCH

    @pytest.mark.asyncio
    async def test_drift_marker_detected(self) -> None:
        adapter = DatabaseRecordAdapter()
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        drift = await adapter.detect_drift(
            action, evidence, current_state={"_drift_marker": True}
        )
        assert drift.status == DriftStatus.DRIFT_DETECTED

    @pytest.mark.asyncio
    async def test_matching_state_no_drift(self) -> None:
        adapter = DatabaseRecordAdapter()
        action = _make_action(policy_version="v1")
        evidence = await adapter.capture_recovery_evidence(action)
        drift = await adapter.detect_drift(action, evidence, current_state={"version": "v1"})
        assert drift.status == DriftStatus.NO_DRIFT

    @pytest.mark.asyncio
    async def test_missing_current_state_is_insufficient_evidence(self) -> None:
        """Absence of current state must not be reported as 'no drift'."""
        adapter = DatabaseRecordAdapter()
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        drift = await adapter.detect_drift(action, evidence, current_state=None)
        assert drift.status == DriftStatus.INSUFFICIENT_EVIDENCE


class TestFileVersionAdapterSimulation:
    @pytest.mark.asyncio
    async def test_simulate_with_before_state_succeeds_cleanly(self) -> None:
        adapter = FileVersionAdapter()
        action = _make_action()
        evidence = await adapter.capture_recovery_evidence(action)
        impact = await adapter.simulate(action, evidence)
        assert impact.warnings == []
        assert impact.would_succeed is True

    @pytest.mark.asyncio
    async def test_simulate_without_before_state_warns(self) -> None:
        """Synthetic before-state fallback is disclosed via warnings."""
        import dataclasses

        adapter = FileVersionAdapter()
        action = _make_action(before_state_ref=None)
        evidence = await adapter.capture_recovery_evidence(action)
        # capture synthesizes a fallback reference; simulate must warn when the
        # evidence carries none.
        evidence = dataclasses.replace(evidence, before_state_reference=None)
        impact = await adapter.simulate(action, evidence)
        assert any("No before-state reference" in w for w in impact.warnings)
        assert impact.would_succeed is False

    @pytest.mark.asyncio
    async def test_preview_marks_mock(self) -> None:
        adapter = FileVersionAdapter()
        preview = await adapter.preview_recovery(_make_action())
        assert preview["mock"] is True
        assert preview["reversible"] is True


class TestConfigRollbackAdapterPreview:
    @pytest.mark.asyncio
    async def test_execute_recovery_reports_failure_not_success(self) -> None:
        """Legacy execute_recovery must not claim restoration it cannot do."""
        adapter = ConfigRollbackAdapter()
        outcome = await adapter.execute_recovery(_make_action(), approved_by="tester")
        assert outcome["status"] == "failed"
        assert outcome["success"] is False
