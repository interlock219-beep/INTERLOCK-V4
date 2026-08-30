"""Tests for DistributedRecoveryOrchestrator and ContinuousVerificationService."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.domain.entities.causal_state_types import (
    DurableExecutionStep,
    RecoveryReport,
    VerificationStatus,
)
from app.domain.entities.protected_action import (
    ActionStatus,
    ProtectedAction,
    Reversibility,
)
from app.domain.entities.surgical_recovery_types import (
    AdapterCapability,
    CompensationType,
    ExecutionState,
    RecoveryAdapterType,
    RecoveryEvidence,
)
from app.domain.services.continuous_verification_service import (
    ContinuousVerificationService,
)
from app.domain.services.distributed_recovery_orchestrator import (
    DistributedRecoveryOrchestrator,
)
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
    target_system: str = "mock",
    target_resource: str = "record:1",
    reversibility: Reversibility = Reversibility.AUTOMATICALLY_REVERSIBLE,
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
        before_state_reference="state:before:123",
        after_state_reference="state:after:456",
        compensation_payload={"op": "restore"},
        compensation_type=CompensationType.REVERSE_OPERATION,
        recovery_adapter_type=RecoveryAdapterType.MOCK,
        idempotency_key=f"idem-{action_id}",
        dependency_edges=[],
        reversibility_classification=reversibility,
        evidence_hash=f"hash-{action_id}",
        adapter_capability=AdapterCapability.MOCK,
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


class MockDurableExecutionRepo:
    def __init__(self, steps: list[DurableExecutionStep] | None = None) -> None:
        self._steps: dict[str, DurableExecutionStep] = {
            s.step_id: s for s in (steps or [])
        }

    async def get_by_step_id(
        self, tenant_id: str, step_id: str
    ) -> DurableExecutionStep | None:
        s = self._steps.get(step_id)
        if s and s.tenant_id == tenant_id:
            return s
        return None

    async def list_by_plan(
        self, tenant_id: str, plan_id: str, limit: int = 500, offset: int = 0
    ) -> tuple[list[DurableExecutionStep], int]:
        items = sorted(
            [
                s for s in self._steps.values()
                if s.tenant_id == tenant_id and s.plan_id == plan_id
            ],
            key=lambda s: s.execution_order,
        )
        return items[offset:offset + limit], len(items)

    async def save(self, step: DurableExecutionStep) -> DurableExecutionStep:
        self._steps[step.step_id] = step
        return step


class MockReportRepo:
    def __init__(self) -> None:
        self._items: dict[str, RecoveryReport] = {}

    async def get_by_report_id(
        self, tenant_id: str, report_id: str
    ) -> RecoveryReport | None:
        r = self._items.get(report_id)
        if r and r.tenant_id == tenant_id:
            return r
        return None

    async def get_by_plan(self, tenant_id: str, plan_id: str) -> RecoveryReport | None:
        for r in self._items.values():
            if r.tenant_id == tenant_id and r.plan_id == plan_id:
                return r
        return None

    async def get_by_incident(
        self, tenant_id: str, incident_id: str
    ) -> RecoveryReport | None:
        for r in self._items.values():
            if r.tenant_id == tenant_id and r.incident_id == incident_id:
                return r
        return None

    async def save(self, report: RecoveryReport) -> RecoveryReport:
        self._items[report.report_id] = report
        return report


class TestDistributedRecoveryOrchestrator:
    @pytest.mark.asyncio
    async def test_create_durable_plan(self) -> None:
        actions = [_make_action("a1"), _make_action("a2")]
        evidence = [_make_evidence("a1"), _make_evidence("a2")]
        evidence_repo = MockEvidenceRepo(evidence)
        execution_repo = MockDurableExecutionRepo()
        adapter = MockRecoveryAdapter(scenario="success")
        orchestrator = DistributedRecoveryOrchestrator(
            evidence_repo, execution_repo, [adapter]
        )

        steps = await orchestrator.create_durable_plan(
            "test-tenant", "plan-1", actions, ["a1", "a2"]
        )

        assert len(steps) == 2
        assert all(s.plan_id == "plan-1" for s in steps)
        assert steps[0].execution_order <= steps[1].execution_order

    @pytest.mark.asyncio
    async def test_execute_durable_plan_success(self) -> None:
        actions = [_make_action("a1"), _make_action("a2")]
        evidence = [_make_evidence("a1"), _make_evidence("a2")]
        evidence_repo = MockEvidenceRepo(evidence)
        execution_repo = MockDurableExecutionRepo()
        adapter = MockRecoveryAdapter(scenario="success")
        orchestrator = DistributedRecoveryOrchestrator(
            evidence_repo, execution_repo, [adapter]
        )

        await orchestrator.create_durable_plan(
            "test-tenant", "plan-1", actions, ["a1", "a2"]
        )
        result = await orchestrator.execute_durable_plan("test-tenant", "plan-1")

        assert result["status"] == "completed"
        assert result["completed"] == 2
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_execute_durable_plan_stops_on_failure(self) -> None:
        actions = [_make_action("a1"), _make_action("a2")]
        evidence = [_make_evidence("a1"), _make_evidence("a2")]
        evidence_repo = MockEvidenceRepo(evidence)
        execution_repo = MockDurableExecutionRepo()
        adapter = MockRecoveryAdapter(scenario="execute_fail")
        orchestrator = DistributedRecoveryOrchestrator(
            evidence_repo, execution_repo, [adapter]
        )

        await orchestrator.create_durable_plan(
            "test-tenant", "plan-1", actions, ["a1", "a2"]
        )
        result = await orchestrator.execute_durable_plan("test-tenant", "plan-1")

        assert result["status"] == "stopped"
        assert result["failed"] == 1
        assert "Stopped on first failure" in result["stop_reason"]

    @pytest.mark.asyncio
    async def test_execute_durable_plan_drift_blocks(self) -> None:
        actions = [_make_action("a1")]
        evidence = [_make_evidence("a1")]
        evidence_repo = MockEvidenceRepo(evidence)
        execution_repo = MockDurableExecutionRepo()
        adapter = MockRecoveryAdapter(scenario="drift_detected")
        orchestrator = DistributedRecoveryOrchestrator(
            evidence_repo, execution_repo, [adapter]
        )

        await orchestrator.create_durable_plan(
            "test-tenant", "plan-1", actions, ["a1"]
        )
        result = await orchestrator.execute_durable_plan(
            "test-tenant", "plan-1",
            stop_conditions=["on_first_failure", "on_blocking_drift"],
        )

        assert result["blocked"] == 1
        assert result["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_execute_no_steps(self) -> None:
        evidence_repo = MockEvidenceRepo([])
        execution_repo = MockDurableExecutionRepo()
        orchestrator = DistributedRecoveryOrchestrator(
            evidence_repo, execution_repo, []
        )

        result = await orchestrator.execute_durable_plan("test-tenant", "plan-1")

        assert result["status"] == "no_steps"

    @pytest.mark.asyncio
    async def test_resume_plan(self) -> None:
        actions = [_make_action("a1"), _make_action("a2")]
        evidence = [_make_evidence("a1"), _make_evidence("a2")]
        evidence_repo = MockEvidenceRepo(evidence)
        execution_repo = MockDurableExecutionRepo()
        adapter = MockRecoveryAdapter(scenario="success")
        orchestrator = DistributedRecoveryOrchestrator(
            evidence_repo, execution_repo, [adapter]
        )

        await orchestrator.create_durable_plan(
            "test-tenant", "plan-1", actions, ["a1", "a2"]
        )
        result = await orchestrator.resume_plan("test-tenant", "plan-1")

        assert result["status"] == "completed"
        assert result["completed"] == 2

    @pytest.mark.asyncio
    async def test_tenant_isolation_in_steps(self) -> None:
        actions = [_make_action("a1", tenant_id="tenant-a")]
        evidence = [_make_evidence("a1", tenant_id="tenant-a")]
        evidence_repo = MockEvidenceRepo(evidence)
        execution_repo = MockDurableExecutionRepo()
        adapter = MockRecoveryAdapter(scenario="success")
        orchestrator = DistributedRecoveryOrchestrator(
            evidence_repo, execution_repo, [adapter]
        )

        await orchestrator.create_durable_plan(
            "tenant-a", "plan-1", actions, ["a1"]
        )
        steps, total = await execution_repo.list_by_plan("tenant-b", "plan-1")

        assert total == 0


class TestContinuousVerificationService:
    @pytest.mark.asyncio
    async def test_verify_all_succeeded_and_verified(self) -> None:
        evidence = [_make_evidence("a1"), _make_evidence("a2")]
        evidence_repo = MockEvidenceRepo(evidence)
        execution_repo = MockDurableExecutionRepo([
            DurableExecutionStep(
                step_id="step-1",
                plan_id="plan-1",
                action_id="a1",
                execution_order=0,
                tenant_id="test-tenant",
                execution_state=ExecutionState.SUCCEEDED.value,
                verification_passed=True,
                idempotency_key="idem-a1",
            ),
            DurableExecutionStep(
                step_id="step-2",
                plan_id="plan-1",
                action_id="a2",
                execution_order=1,
                tenant_id="test-tenant",
                execution_state=ExecutionState.SUCCEEDED.value,
                verification_passed=True,
                idempotency_key="idem-a2",
            ),
        ])
        report_repo = MockReportRepo()
        adapter = MockRecoveryAdapter(scenario="success")
        service = ContinuousVerificationService(
            evidence_repo, execution_repo, report_repo, [adapter]
        )

        report = await service.verify_recovery("test-tenant", "plan-1", "inc-1")

        assert report.verification_status == VerificationStatus.EXECUTED_AND_VERIFIED
        assert len(report.ai_changes_recovered) == 2
        assert len(report.ai_changes_failed) == 0

    @pytest.mark.asyncio
    async def test_verify_with_failures(self) -> None:
        evidence = [_make_evidence("a1"), _make_evidence("a2")]
        evidence_repo = MockEvidenceRepo(evidence)
        execution_repo = MockDurableExecutionRepo([
            DurableExecutionStep(
                step_id="step-1",
                plan_id="plan-1",
                action_id="a1",
                execution_order=0,
                tenant_id="test-tenant",
                execution_state=ExecutionState.SUCCEEDED.value,
                verification_passed=True,
                idempotency_key="idem-a1",
            ),
            DurableExecutionStep(
                step_id="step-2",
                plan_id="plan-1",
                action_id="a2",
                execution_order=1,
                tenant_id="test-tenant",
                execution_state=ExecutionState.FAILED.value,
                error="Execution failed",
                idempotency_key="idem-a2",
            ),
        ])
        report_repo = MockReportRepo()
        service = ContinuousVerificationService(
            evidence_repo, execution_repo, report_repo, []
        )

        report = await service.verify_recovery("test-tenant", "plan-1", "inc-1")

        assert len(report.ai_changes_recovered) == 1
        assert len(report.ai_changes_failed) == 1
        assert len(report.limitations) > 0

    @pytest.mark.asyncio
    async def test_verify_with_manual_required(self) -> None:
        evidence = [_make_evidence("a1")]
        evidence_repo = MockEvidenceRepo(evidence)
        execution_repo = MockDurableExecutionRepo([
            DurableExecutionStep(
                step_id="step-1",
                plan_id="plan-1",
                action_id="a1",
                execution_order=0,
                tenant_id="test-tenant",
                execution_state=ExecutionState.REQUIRES_MANUAL_ACTION.value,
                idempotency_key="idem-a1",
            ),
        ])
        report_repo = MockReportRepo()
        service = ContinuousVerificationService(
            evidence_repo, execution_repo, report_repo, []
        )

        report = await service.verify_recovery("test-tenant", "plan-1", "inc-1")

        assert len(report.manual_recovery_required) == 1
        assert (
            report.verification_status
            == VerificationStatus.MANUAL_VERIFICATION_REQUIRED
        )

    @pytest.mark.asyncio
    async def test_verify_with_unknown_outcome(self) -> None:
        evidence = [_make_evidence("a1")]
        evidence_repo = MockEvidenceRepo(evidence)
        execution_repo = MockDurableExecutionRepo([
            DurableExecutionStep(
                step_id="step-1",
                plan_id="plan-1",
                action_id="a1",
                execution_order=0,
                tenant_id="test-tenant",
                execution_state=ExecutionState.UNKNOWN_EXTERNAL_OUTCOME.value,
                idempotency_key="idem-a1",
            ),
        ])
        report_repo = MockReportRepo()
        service = ContinuousVerificationService(
            evidence_repo, execution_repo, report_repo, []
        )

        report = await service.verify_recovery("test-tenant", "plan-1", "inc-1")

        assert len(report.manual_recovery_required) == 1
        assert any(
            "unknown external outcome" in lim.lower()
            for lim in report.limitations
        )

    @pytest.mark.asyncio
    async def test_verify_single_action(self) -> None:
        evidence = [_make_evidence("a1")]
        evidence_repo = MockEvidenceRepo(evidence)
        execution_repo = MockDurableExecutionRepo()
        report_repo = MockReportRepo()
        adapter = MockRecoveryAdapter(scenario="success")
        service = ContinuousVerificationService(
            evidence_repo, execution_repo, report_repo, [adapter]
        )

        result = await service.verify_single_action("test-tenant", "a1")

        assert result["verified"] is False
        assert result["status"] == VerificationStatus.EXECUTED_NOT_VERIFIED.value

    @pytest.mark.asyncio
    async def test_verify_single_action_no_evidence(self) -> None:
        evidence_repo = MockEvidenceRepo([])
        execution_repo = MockDurableExecutionRepo()
        report_repo = MockReportRepo()
        service = ContinuousVerificationService(
            evidence_repo, execution_repo, report_repo, []
        )

        result = await service.verify_single_action("test-tenant", "a1")

        assert result["verified"] is False
        assert "No evidence" in result["reason"]

    @pytest.mark.asyncio
    async def test_report_contains_limitations(self) -> None:
        evidence = [_make_evidence("a1")]
        evidence_repo = MockEvidenceRepo(evidence)
        execution_repo = MockDurableExecutionRepo([
            DurableExecutionStep(
                step_id="step-1",
                plan_id="plan-1",
                action_id="a1",
                execution_order=0,
                tenant_id="test-tenant",
                execution_state=ExecutionState.BLOCKED_BY_DRIFT.value,
                error="Drift detected",
                idempotency_key="idem-a1",
            ),
        ])
        report_repo = MockReportRepo()
        service = ContinuousVerificationService(
            evidence_repo, execution_repo, report_repo, []
        )

        report = await service.verify_recovery("test-tenant", "plan-1", "inc-1")

        assert len(report.limitations) > 0
        assert any("drift" in lim.lower() for lim in report.limitations)
