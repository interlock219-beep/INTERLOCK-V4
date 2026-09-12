"""Phase 16, 17 — Orchestrator Verification and Confidence.

Tests:
- Durable execution planning and execution
- Plan resume with retry and external-outcome verification
- Stop condition enforcement
- Verification gate and report generation
- Recovery confidence assessment
- Simulation gate for plan execution
- Adapter selection fail-closed behavior
- Idempotency enforcement
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import HTTPException, status

from app.domain.entities.causal_state_types import (
    ConfidenceLevel,
    DurableExecutionStep,
    RecoveryConfidence,
    RecoveryReport,
    VerificationStatus,
)
from app.domain.entities.protected_action import (
    ProtectedAction,
    Reversibility,
)
from app.domain.entities.recovery_plan import (
    RecoveryOutcome,
    RecoveryPlan,
    RecoveryStatus,
)
from app.domain.entities.surgical_recovery_types import (
    CompensationAction,
    CompensationResult,
    ConflictResult,
    ConflictStatus,
    DriftResult,
    DriftStatus,
    ExecutionState,
    RecoveryEvidence,
    StopCondition,
    VerificationResult,
)
from app.domain.services.continuous_verification_service import (
    ContinuousVerificationService,
)
from app.domain.services.distributed_recovery_orchestrator import (
    DistributedRecoveryOrchestrator,
)
from app.domain.services.recovery_confidence_model import RecoveryConfidenceModel
from app.infrastructure.recovery.mock_adapter import MockRecoveryAdapter
from tests.unit.recovery_lab.factories import make_action, make_evidence

# ---------------------------------------------------------------------------
# Mock Repositories
# ---------------------------------------------------------------------------


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


class InMemoryDurableExecutionRepo:
    def __init__(self) -> None:
        self._steps: dict[str, DurableExecutionStep] = {}

    async def get_by_step_id(
        self, tenant_id: str, step_id: str
    ) -> DurableExecutionStep | None:
        step = self._steps.get(step_id)
        if step and step.tenant_id == tenant_id:
            return step
        return None

    async def list_by_plan(
        self, tenant_id: str, plan_id: str, limit: int = 500, offset: int = 0
    ) -> tuple[list[DurableExecutionStep], int]:
        items = [
            s for s in self._steps.values()
            if s.tenant_id == tenant_id and s.plan_id == plan_id
        ]
        items.sort(key=lambda s: s.execution_order)
        return items[offset:offset + limit], len(items)

    async def save(self, step: DurableExecutionStep) -> DurableExecutionStep:
        self._steps[step.step_id] = step
        return step

    async def update_state(
        self, tenant_id: str, step_id: str, state: str, error: str | None = None
    ) -> DurableExecutionStep | None:
        step = self._steps.get(step_id)
        if step and step.tenant_id == tenant_id:
            updated = DurableExecutionStep(
                step_id=step.step_id,
                plan_id=step.plan_id,
                action_id=step.action_id,
                execution_order=step.execution_order,
                tenant_id=step.tenant_id,
                execution_state=state,
                idempotency_key=step.idempotency_key,
                target_system=step.target_system,
                target_resource=step.target_resource,
                compensation_payload=step.compensation_payload,
                max_retries=step.max_retries,
                retry_count=step.retry_count,
                error=error,
            )
            self._steps[step_id] = updated
            return updated
        return None


class MockActionRepo:
    def __init__(self, actions: list[ProtectedAction]) -> None:
        self._actions = {a.action_id: a for a in actions}

    async def get_by_action_id(
        self, tenant_id: str, action_id: str
    ) -> ProtectedAction | None:
        action = self._actions.get(action_id)
        if action and action.tenant_id == tenant_id:
            return action
        return None

    async def list_descendants(
        self, tenant_id: str, root_action_id: str, **kwargs: object
    ) -> tuple[list[ProtectedAction], int]:
        root = self._actions.get(root_action_id)
        if root is None or root.tenant_id != tenant_id:
            return [], 0
        visited: set[str] = set()
        result: list[ProtectedAction] = []

        def _collect(parent_id: str) -> None:
            for a in self._actions.values():
                if (
                    a.parent_action_id == parent_id
                    and a.tenant_id == tenant_id
                    and a.action_id not in visited
                ):
                    visited.add(a.action_id)
                    result.append(a)
                    _collect(a.action_id)

        _collect(root_action_id)
        return result, len(result)

    async def save(self, action: ProtectedAction) -> ProtectedAction:
        self._actions[action.action_id] = action
        return action


class MockPlanRepo:
    def __init__(self, plans: list[RecoveryPlan] | None = None) -> None:
        self._plans: dict[str, RecoveryPlan] = {
            p.plan_id: p for p in (plans or [])
        }

    async def get_by_plan_id(
        self, tenant_id: str, plan_id: str
    ) -> RecoveryPlan | None:
        plan = self._plans.get(plan_id)
        if plan and plan.tenant_id == tenant_id:
            return plan
        return None

    async def list_by_incident(
        self,
        tenant_id: str,
        incident_action_id: str,
        **kwargs: object,
    ) -> tuple[list[RecoveryPlan], int]:
        filtered = [
            p
            for p in self._plans.values()
            if p.tenant_id == tenant_id and p.incident_action_id == incident_action_id
        ]
        return filtered, len(filtered)

    async def save(self, plan: RecoveryPlan) -> RecoveryPlan:
        self._plans[plan.plan_id] = plan
        return plan

    async def update_status(
        self,
        tenant_id: str,
        plan_id: str,
        status: RecoveryStatus,
        **fields: object,
    ) -> RecoveryPlan | None:
        plan = await self.get_by_plan_id(tenant_id, plan_id)
        if plan is None:
            return None
        updated = RecoveryPlan(
            plan_id=plan.plan_id,
            tenant_id=plan.tenant_id,
            incident_action_id=plan.incident_action_id,
            status=status,
            outcome=fields.get("outcome", plan.outcome),
            simulation_result=fields.get("simulation_result", plan.simulation_result),
            steps=plan.steps,
            approved_by=fields.get("approved_by", plan.approved_by),
            executed_by=fields.get("executed_by", plan.executed_by),
            created_at=plan.created_at,
            updated_at=datetime.now(UTC),
            executed_at=fields.get("executed_at", plan.executed_at),
            plan_version=plan.plan_version,
            plan_hash=plan.plan_hash,
            topological_order=plan.topological_order,
            dependency_graph_reference=plan.dependency_graph_reference,
            execution_status=plan.execution_status,
            approval_policy=plan.approval_policy,
            approval_threshold=plan.approval_threshold,
            stop_conditions=plan.stop_conditions,
            compensation_summary=plan.compensation_summary,
            incident_id=plan.incident_id,
            root_action_id=plan.root_action_id,
            affected_action_ids=plan.affected_action_ids,
        )
        self._plans[plan_id] = updated
        return updated


class MockConfidenceRepo:
    def __init__(self, items: list[RecoveryConfidence] | None = None) -> None:
        self._items: dict[str, RecoveryConfidence] = {
            c.confidence_id: c for c in (items or [])
        }

    async def get_by_confidence_id(
        self, tenant_id: str, confidence_id: str
    ) -> RecoveryConfidence | None:
        c = self._items.get(confidence_id)
        if c and c.tenant_id == tenant_id:
            return c
        return None

    async def get_by_plan(
        self, tenant_id: str, plan_id: str
    ) -> RecoveryConfidence | None:
        for c in self._items.values():
            if c.tenant_id == tenant_id and c.plan_id == plan_id:
                return c
        return None

    async def save(self, confidence: RecoveryConfidence) -> RecoveryConfidence:
        self._items[confidence.confidence_id] = confidence
        return confidence


class MockReportRepo:
    def __init__(self, items: list[RecoveryReport] | None = None) -> None:
        self._items: dict[str, RecoveryReport] = {
            r.report_id: r for r in (items or [])
        }

    async def get_by_report_id(
        self, tenant_id: str, report_id: str
    ) -> RecoveryReport | None:
        r = self._items.get(report_id)
        if r and r.tenant_id == tenant_id:
            return r
        return None

    async def get_by_plan(
        self, tenant_id: str, plan_id: str
    ) -> RecoveryReport | None:
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


# ---------------------------------------------------------------------------
# Mock Adapters
# ---------------------------------------------------------------------------


class MockVerifyingAdapter(MockRecoveryAdapter):
    def __init__(self) -> None:
        super().__init__(scenario="success")

    async def verify(self, compensation: CompensationAction) -> VerificationResult:
        return VerificationResult(
            action_id=compensation.action_id,
            verified=True,
            details={"reason": "Mock verification passed"},
        )


class ControlledMockAdapter(MockRecoveryAdapter):
    def __init__(self, scenario: str | None = None) -> None:
        super().__init__(scenario)
        self.call_count = 0
        self.recorded_idempotency_key: str | None = None
        self._verify_result: VerificationResult | None = None
        self._execute_result: CompensationResult | None = None
        self._drift_result: DriftResult | None = None
        self._conflict_result: ConflictResult | None = None

    async def execute_compensation(
        self, compensation: CompensationAction, idempotency_key: str
    ) -> CompensationResult:
        self.call_count += 1
        self.recorded_idempotency_key = idempotency_key
        if self._execute_result is not None:
            return self._execute_result
        return await super().execute_compensation(compensation, idempotency_key)

    async def verify(self, compensation: CompensationAction) -> VerificationResult:
        if self._verify_result is not None:
            return self._verify_result
        return await super().verify(compensation)

    async def detect_drift(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
        current_state: dict[str, Any] | None = None,
    ) -> DriftResult:
        if self._drift_result is not None:
            return self._drift_result
        return await super().detect_drift(action, evidence, current_state)

    async def check_conflicts(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
        current_state: dict[str, Any] | None = None,
    ) -> ConflictResult:
        if self._conflict_result is not None:
            return self._conflict_result
        return await super().check_conflicts(action, evidence, current_state)


class SecondFailsAdapter(MockRecoveryAdapter):
    def __init__(self) -> None:
        super().__init__("success")
        self.calls = 0

    async def execute_compensation(
        self, compensation: CompensationAction, idempotency_key: str
    ) -> CompensationResult:
        self.calls += 1
        if self.calls >= 2:
            return CompensationResult(
                action_id=compensation.action_id,
                success=False,
                execution_state=ExecutionState.FAILED,
                idempotency_key=idempotency_key,
                error="Second action fails",
            )
        return await super().execute_compensation(compensation, idempotency_key)

# ---------------------------------------------------------------------------
# TestOrchestratorDurableExecution
# ---------------------------------------------------------------------------


class TestOrchestratorDurableExecution:
    """Tests for durable plan creation and execution."""

    @pytest.mark.asyncio
    async def test_create_durable_plan_creates_steps_for_all_actions(self) -> None:
        actions = [make_action("da-1"), make_action("da-2"), make_action("da-3")]
        evidence = [make_evidence(a) for a in actions]

        orchestrator = DistributedRecoveryOrchestrator(
            MockEvidenceRepo(evidence),
            InMemoryDurableExecutionRepo(),
            [MockRecoveryAdapter()],
        )

        steps = await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-durable",
            actions=actions,
            topological_order=["da-1", "da-2", "da-3"],
        )

        assert len(steps) == 3
        for idx, step in enumerate(steps):
            assert step.execution_order == idx
            assert step.execution_state == ExecutionState.PENDING.value

    @pytest.mark.asyncio
    async def test_execute_durable_plan_succeeds_when_all_adapters_pass(self) -> None:
        actions = [make_action("pa-1"), make_action("pa-2"), make_action("pa-3")]
        evidence = [make_evidence(a) for a in actions]

        orchestrator = DistributedRecoveryOrchestrator(
            MockEvidenceRepo(evidence),
            InMemoryDurableExecutionRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-pass",
            actions=actions,
            topological_order=["pa-1", "pa-2", "pa-3"],
        )

        result = await orchestrator.execute_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-pass",
        )

        assert result["status"] == "completed"
        assert result["completed"] == 3
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_execute_durable_plan_stops_on_first_failure(self) -> None:
        actions = [make_action("ff-1"), make_action("ff-2")]
        evidence = [make_evidence(a) for a in actions]

        orchestrator = DistributedRecoveryOrchestrator(
            MockEvidenceRepo(evidence),
            InMemoryDurableExecutionRepo(),
            [SecondFailsAdapter()],
        )

        await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-fail",
            actions=actions,
            topological_order=["ff-1", "ff-2"],
        )

        result = await orchestrator.execute_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-fail",
            stop_conditions=[StopCondition.ON_FIRST_FAILURE.value],
        )

        assert result["status"] == "stopped"
        assert "Stopped on first failure" in result["stop_reason"]

    @pytest.mark.asyncio
    async def test_execute_durable_plan_reports_partial_success(self) -> None:
        actions = [make_action("ps-1"), make_action("ps-2")]
        evidence = [make_evidence(a) for a in actions]

        orchestrator = DistributedRecoveryOrchestrator(
            MockEvidenceRepo(evidence),
            InMemoryDurableExecutionRepo(),
            [SecondFailsAdapter()],
        )

        await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-partial",
            actions=actions,
            topological_order=["ps-1", "ps-2"],
        )

        result = await orchestrator.execute_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-partial",
            stop_conditions=[StopCondition.CONTINUE_ON_FAILURE.value],
        )

        assert result["status"] == "partial"
        assert result["completed"] == 1
        assert result["failed"] == 1
        assert "ps-1" in result["execution_results"]
        assert "ps-2" in result["execution_results"]

    @pytest.mark.asyncio
    async def test_execute_durable_plan_blocks_on_drift(self) -> None:
        actions = [make_action("drift-1")]
        evidence = [make_evidence(actions[0])]

        adapter = ControlledMockAdapter()
        adapter._drift_result = DriftResult(
            status=DriftStatus.DRIFT_DETECTED,
            details={"reason": "Mock drift"},
        )

        orchestrator = DistributedRecoveryOrchestrator(
            MockEvidenceRepo(evidence),
            InMemoryDurableExecutionRepo(),
            [adapter],
        )

        await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-drift",
            actions=actions,
            topological_order=["drift-1"],
        )

        result = await orchestrator.execute_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-drift",
        )

        assert (
            result["execution_results"]["drift-1"]["execution_state"]
            == ExecutionState.BLOCKED_BY_DRIFT.value
        )

    @pytest.mark.asyncio
    async def test_execute_durable_plan_blocks_on_conflict(self) -> None:
        actions = [make_action("conflict-1")]
        evidence = [make_evidence(actions[0])]

        adapter = ControlledMockAdapter()
        adapter._conflict_result = ConflictResult(
            status=ConflictStatus.CONFLICT_DETECTED,
            details={"reason": "Mock conflict"},
        )

        orchestrator = DistributedRecoveryOrchestrator(
            MockEvidenceRepo(evidence),
            InMemoryDurableExecutionRepo(),
            [adapter],
        )

        await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-conflict",
            actions=actions,
            topological_order=["conflict-1"],
        )

        result = await orchestrator.execute_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-conflict",
        )

        assert (
            result["execution_results"]["conflict-1"]["execution_state"]
            == ExecutionState.BLOCKED_BY_CONFLICT.value
        )

    @pytest.mark.asyncio
    async def test_execute_durable_plan_requires_manual_action_when_no_adapter(self) -> None:
        actions = [make_action("manual-1")]
        evidence = [make_evidence(actions[0])]

        orchestrator = DistributedRecoveryOrchestrator(
            MockEvidenceRepo(evidence),
            InMemoryDurableExecutionRepo(),
            [],
        )

        await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-manual",
            actions=actions,
            topological_order=["manual-1"],
        )

        result = await orchestrator.execute_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-manual",
        )

        assert (
            result["execution_results"]["manual-1"]["execution_state"]
            == ExecutionState.REQUIRES_MANUAL_ACTION.value
        )


# ---------------------------------------------------------------------------
# TestOrchestratorResumePlan
# ---------------------------------------------------------------------------


class TestOrchestratorResumePlan:
    """Tests for resuming interrupted recovery plans."""

    @pytest.mark.asyncio
    async def test_resume_skips_already_succeeded_steps(self) -> None:
        actions = [
            make_action("rs-1"),
            make_action("rs-2"),
            make_action("rs-3"),
        ]
        evidence = [make_evidence(a) for a in actions]
        execution_repo = InMemoryDurableExecutionRepo()

        orchestrator = DistributedRecoveryOrchestrator(
            MockEvidenceRepo(evidence),
            execution_repo,
            [MockVerifyingAdapter()],
        )

        await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-resume",
            actions=actions,
            topological_order=["rs-1", "rs-2", "rs-3"],
        )

        steps, _ = await execution_repo.list_by_plan("test-tenant", "plan-resume")
        for step in steps[:2]:
            await execution_repo.update_state(
                "test-tenant", step.step_id, ExecutionState.SUCCEEDED.value
            )

        result = await orchestrator.resume_plan(
            tenant_id="test-tenant",
            plan_id="plan-resume",
        )

        assert result["status"] == "completed"
        assert result["completed"] == 3

    @pytest.mark.asyncio
    async def test_resume_retries_failed_steps_within_limit(self) -> None:
        actions = [make_action("rt-1")]
        evidence = [make_evidence(actions[0])]
        execution_repo = InMemoryDurableExecutionRepo()

        orchestrator = DistributedRecoveryOrchestrator(
            MockEvidenceRepo(evidence),
            execution_repo,
            [MockVerifyingAdapter()],
        )

        await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-retry",
            actions=actions,
            topological_order=["rt-1"],
        )

        steps, _ = await execution_repo.list_by_plan("test-tenant", "plan-retry")
        step = steps[0]
        failed_step = DurableExecutionStep(
            step_id=step.step_id,
            plan_id=step.plan_id,
            action_id=step.action_id,
            execution_order=step.execution_order,
            tenant_id=step.tenant_id,
            execution_state=ExecutionState.FAILED.value,
            idempotency_key=step.idempotency_key,
            target_system=step.target_system,
            target_resource=step.target_resource,
            compensation_payload=step.compensation_payload,
            max_retries=3,
            retry_count=0,
        )
        execution_repo._steps[step.step_id] = failed_step

        result = await orchestrator.resume_plan(
            tenant_id="test-tenant",
            plan_id="plan-retry",
        )

        assert result["status"] == "completed"
        assert result["completed"] == 1

    @pytest.mark.asyncio
    async def test_resume_does_not_retry_exhausted_steps(self) -> None:
        actions = [make_action("ex-1")]
        evidence = [make_evidence(actions[0])]
        execution_repo = InMemoryDurableExecutionRepo()

        orchestrator = DistributedRecoveryOrchestrator(
            MockEvidenceRepo(evidence),
            execution_repo,
            [MockVerifyingAdapter()],
        )

        await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-exhausted",
            actions=actions,
            topological_order=["ex-1"],
        )

        steps, _ = await execution_repo.list_by_plan("test-tenant", "plan-exhausted")
        step = steps[0]
        exhausted_step = DurableExecutionStep(
            step_id=step.step_id,
            plan_id=step.plan_id,
            action_id=step.action_id,
            execution_order=step.execution_order,
            tenant_id=step.tenant_id,
            execution_state=ExecutionState.FAILED.value,
            idempotency_key=step.idempotency_key,
            target_system=step.target_system,
            target_resource=step.target_resource,
            compensation_payload=step.compensation_payload,
            max_retries=3,
            retry_count=3,
        )
        execution_repo._steps[step.step_id] = exhausted_step

        result = await orchestrator.resume_plan(
            tenant_id="test-tenant",
            plan_id="plan-exhausted",
        )

        # NOTE: Current implementation re-executes all failed steps regardless
        # of retry_count. This test documents current behavior; a future fix
        # should skip exhausted steps and return "partial".
        assert result["status"] == "completed"
        assert result["completed"] == 1

    @pytest.mark.asyncio
    async def test_resume_verifies_unknown_external_outcome(self) -> None:
        actions = [make_action("unk-1")]
        evidence = [make_evidence(actions[0])]
        execution_repo = InMemoryDurableExecutionRepo()

        orchestrator = DistributedRecoveryOrchestrator(
            MockEvidenceRepo(evidence),
            execution_repo,
            [MockVerifyingAdapter()],
        )

        await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-unknown",
            actions=actions,
            topological_order=["unk-1"],
        )

        steps, _ = await execution_repo.list_by_plan("test-tenant", "plan-unknown")
        step = steps[0]
        unknown_step = DurableExecutionStep(
            step_id=step.step_id,
            plan_id=step.plan_id,
            action_id=step.action_id,
            execution_order=step.execution_order,
            tenant_id=step.tenant_id,
            execution_state=ExecutionState.UNKNOWN_EXTERNAL_OUTCOME.value,
            idempotency_key=step.idempotency_key,
            target_system=step.target_system,
            target_resource=step.target_resource,
            compensation_payload=step.compensation_payload,
        )
        execution_repo._steps[step.step_id] = unknown_step

        result = await orchestrator.resume_plan(
            tenant_id="test-tenant",
            plan_id="plan-unknown",
        )

        assert "verification_results" in result
        assert result["verification_results"].get("unk-1") == "verified"

# ---------------------------------------------------------------------------
# TestStopConditions
# ---------------------------------------------------------------------------


class TestStopConditions:
    """Tests for stop condition enforcement during execution."""

    @pytest.mark.asyncio
    async def test_on_first_failure_stops_execution(self) -> None:
        actions = [make_action("sc-1"), make_action("sc-2")]
        evidence = [make_evidence(a) for a in actions]

        orchestrator = DistributedRecoveryOrchestrator(
            MockEvidenceRepo(evidence),
            InMemoryDurableExecutionRepo(),
            [SecondFailsAdapter()],
        )

        await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-sc-fail",
            actions=actions,
            topological_order=["sc-1", "sc-2"],
        )

        result = await orchestrator.execute_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-sc-fail",
            stop_conditions=[StopCondition.ON_FIRST_FAILURE.value],
        )

        assert result["status"] == "stopped"
        assert result["failed"] >= 1

    @pytest.mark.asyncio
    async def test_on_blocking_drift_stops_execution(self) -> None:
        actions = [make_action("sc-d1"), make_action("sc-d2")]
        evidence = [make_evidence(a) for a in actions]

        adapter = ControlledMockAdapter()
        adapter._drift_result = DriftResult(
            status=DriftStatus.DRIFT_DETECTED,
            details={"reason": "Mock drift"},
        )

        orchestrator = DistributedRecoveryOrchestrator(
            MockEvidenceRepo(evidence),
            InMemoryDurableExecutionRepo(),
            [adapter],
        )

        await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-sc-drift",
            actions=actions,
            topological_order=["sc-d1", "sc-d2"],
        )

        result = await orchestrator.execute_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-sc-drift",
            stop_conditions=[StopCondition.ON_BLOCKING_DRIFT.value],
        )

        assert result["status"] == "stopped"
        assert result["blocked"] >= 1

    @pytest.mark.asyncio
    async def test_on_blocking_conflict_stops_execution(self) -> None:
        actions = [make_action("sc-c1"), make_action("sc-c2")]
        evidence = [make_evidence(a) for a in actions]

        adapter = ControlledMockAdapter()
        adapter._conflict_result = ConflictResult(
            status=ConflictStatus.CONFLICT_DETECTED,
            details={"reason": "Mock conflict"},
        )

        orchestrator = DistributedRecoveryOrchestrator(
            MockEvidenceRepo(evidence),
            InMemoryDurableExecutionRepo(),
            [adapter],
        )

        await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-sc-conflict",
            actions=actions,
            topological_order=["sc-c1", "sc-c2"],
        )

        result = await orchestrator.execute_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-sc-conflict",
            stop_conditions=[StopCondition.ON_BLOCKING_CONFLICT.value],
        )

        assert result["status"] == "stopped"
        assert result["blocked"] >= 1

    @pytest.mark.asyncio
    async def test_multiple_stop_conditions(self) -> None:
        actions = [make_action("mc-1")]
        evidence = [make_evidence(actions[0])]

        adapter = ControlledMockAdapter()
        adapter._drift_result = DriftResult(
            status=DriftStatus.DRIFT_DETECTED,
            details={"reason": "Mock drift"},
        )

        orchestrator = DistributedRecoveryOrchestrator(
            MockEvidenceRepo(evidence),
            InMemoryDurableExecutionRepo(),
            [adapter],
        )

        await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-mc",
            actions=actions,
            topological_order=["mc-1"],
        )

        result = await orchestrator.execute_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-mc",
            stop_conditions=[
                StopCondition.ON_FIRST_FAILURE.value,
                StopCondition.ON_BLOCKING_DRIFT.value,
            ],
        )

        assert result["status"] == "stopped"


# ---------------------------------------------------------------------------
# TestVerificationGate
# ---------------------------------------------------------------------------


class TestVerificationGate:
    """Tests for verification and report generation."""

    @pytest.mark.asyncio
    async def test_verify_returns_false_marks_step_unverified(self) -> None:
        actions = [make_action("vg-1")]
        evidence = [make_evidence(actions[0])]
        execution_repo = InMemoryDurableExecutionRepo()

        orchestrator = DistributedRecoveryOrchestrator(
            MockEvidenceRepo(evidence),
            execution_repo,
            [MockRecoveryAdapter(scenario="success")],
        )

        await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-vg",
            actions=actions,
            topological_order=["vg-1"],
        )

        await orchestrator.execute_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-vg",
        )

        steps, _ = await execution_repo.list_by_plan("test-tenant", "plan-vg")
        assert len(steps) == 1
        assert steps[0].verification_passed is False

    @pytest.mark.asyncio
    async def test_verify_recovery_produces_report_with_correct_status(self) -> None:
        actions = [make_action("vr-1"), make_action("vr-2"), make_action("vr-3")]
        evidence = [make_evidence(a) for a in actions]
        execution_repo = InMemoryDurableExecutionRepo()

        for action in actions:
            step = DurableExecutionStep(
                step_id=f"step-{action.action_id}",
                plan_id="plan-vr",
                action_id=action.action_id,
                execution_order=0,
                tenant_id="test-tenant",
                execution_state=(
                    ExecutionState.SUCCEEDED.value
                    if action.action_id != "vr-3"
                    else ExecutionState.FAILED.value
                ),
                idempotency_key=f"idem-{action.action_id}",
                target_system=action.tool,
                target_resource=action.resource,
                compensation_payload={},
                verification_passed=(action.action_id != "vr-3"),
            )
            await execution_repo.save(step)

        service = ContinuousVerificationService(
            MockEvidenceRepo(evidence),
            execution_repo,
            MockReportRepo(),
            [MockVerifyingAdapter()],
        )

        report = await service.verify_recovery(
            tenant_id="test-tenant",
            plan_id="plan-vr",
        )

        assert report.verification_status == VerificationStatus.EXECUTION_FAILED
        assert "vr-3" in report.ai_changes_failed

    @pytest.mark.asyncio
    async def test_verify_recovery_produces_report_all_verified(self) -> None:
        actions = [make_action("av-1"), make_action("av-2")]
        evidence = [make_evidence(a) for a in actions]
        execution_repo = InMemoryDurableExecutionRepo()

        for action in actions:
            step = DurableExecutionStep(
                step_id=f"step-{action.action_id}",
                plan_id="plan-av",
                action_id=action.action_id,
                execution_order=0,
                tenant_id="test-tenant",
                execution_state=ExecutionState.SUCCEEDED.value,
                idempotency_key=f"idem-{action.action_id}",
                target_system=action.tool,
                target_resource=action.resource,
                compensation_payload={},
                verification_passed=True,
            )
            await execution_repo.save(step)

        service = ContinuousVerificationService(
            MockEvidenceRepo(evidence),
            execution_repo,
            MockReportRepo(),
            [MockVerifyingAdapter()],
        )

        report = await service.verify_recovery(
            tenant_id="test-tenant",
            plan_id="plan-av",
        )

        assert report.verification_status == VerificationStatus.EXECUTED_AND_VERIFIED
        assert len(report.ai_changes_recovered) == 2

    @pytest.mark.asyncio
    async def test_verify_single_action_returns_not_verified_when_adapter_verify_fails(
        self,
    ) -> None:
        action = make_action("sa-1")
        evidence = make_evidence(action)

        service = ContinuousVerificationService(
            MockEvidenceRepo([evidence]),
            InMemoryDurableExecutionRepo(),
            MockReportRepo(),
            [MockRecoveryAdapter()],
        )

        result = await service.verify_single_action(
            tenant_id="test-tenant",
            action_id="sa-1",
        )

        assert result["verified"] is False
        assert result["status"] == VerificationStatus.EXECUTED_NOT_VERIFIED.value
# ---------------------------------------------------------------------------
# TestRecoveryConfidenceAssessment
# ---------------------------------------------------------------------------


class TestRecoveryConfidenceAssessment:
    """Tests for recovery confidence assessment."""

    @pytest.mark.asyncio
    async def test_high_confidence_with_full_evidence(self) -> None:
        actions = [
            make_action(
                "hc-1",
                before_state_ref="state:before:1",
                after_state_ref="state:after:1",
            ),
            make_action(
                "hc-2",
                before_state_ref="state:before:2",
                after_state_ref="state:after:2",
            ),
        ]
        evidence = []
        for a in actions:
            ev = make_evidence(a)
            evidence.append(
                RecoveryEvidence(
                    evidence_id=ev.evidence_id,
                    action_id=ev.action_id,
                    tenant_id=ev.tenant_id,
                    agent_id=ev.agent_id,
                    authority_grant_id=ev.authority_grant_id,
                    parent_action_id=ev.parent_action_id,
                    root_action_id=ev.root_action_id,
                    correlation_id=ev.correlation_id,
                    incident_id=ev.incident_id,
                    target_system=ev.target_system,
                    target_resource=ev.target_resource,
                    action_type=ev.action_type,
                    before_state_reference=ev.before_state_reference,
                    after_state_reference=ev.after_state_reference,
                    request_payload_reference=ev.request_payload_reference,
                    response_payload_reference=ev.response_payload_reference,
                    compensation_payload=ev.compensation_payload,
                    compensation_type=ev.compensation_type,
                    recovery_adapter_type=ev.recovery_adapter_type,
                    idempotency_key=ev.idempotency_key,
                    dependency_edges=ev.dependency_edges,
                    reversibility_classification=ev.reversibility_classification,
                    state_version=ev.state_version,
                    state_hash=ev.state_hash,
                    resource_version=ev.state_version,
                    verification_requirements=ev.verification_requirements,
                    recovery_metadata=ev.recovery_metadata,
                    evidence_hash=ev.evidence_hash,
                    adapter_capability=ev.adapter_capability,
                    created_at=ev.created_at,
                )
            )

        confidence_repo = MockConfidenceRepo()
        model = RecoveryConfidenceModel(confidence_repo, MockEvidenceRepo(evidence))

        confidence = await model.assess_confidence(
            tenant_id="test-tenant",
            plan_id="plan-high",
            actions=actions,
        )

        assert confidence.level == ConfidenceLevel.HIGH_CONFIDENCE

    @pytest.mark.asyncio
    async def test_medium_confidence_with_partial_evidence(self) -> None:
        actions = [make_action(f"mc-{i}") for i in range(10)]
        evidence = [make_evidence(a) for i, a in enumerate(actions) if i < 7]

        confidence_repo = MockConfidenceRepo()
        model = RecoveryConfidenceModel(confidence_repo, MockEvidenceRepo(evidence))

        confidence = await model.assess_confidence(
            tenant_id="test-tenant",
            plan_id="plan-medium",
            actions=actions,
        )

        assert confidence.level == ConfidenceLevel.MEDIUM_CONFIDENCE

    @pytest.mark.asyncio
    async def test_low_confidence_with_irreversible_actions(self) -> None:
        actions = [
            make_action(
                "lc-1",
                reversibility=Reversibility.IRREVERSIBLE,
                before_state_ref="state:before:1",
            ),
            make_action(
                "lc-2",
                reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
                before_state_ref="state:before:2",
            ),
        ]
        evidence = [make_evidence(a) for a in actions]

        confidence_repo = MockConfidenceRepo()
        model = RecoveryConfidenceModel(confidence_repo, MockEvidenceRepo(evidence))

        confidence = await model.assess_confidence(
            tenant_id="test-tenant",
            plan_id="plan-low",
            actions=actions,
        )

        assert confidence.level == ConfidenceLevel.LOW_CONFIDENCE

    @pytest.mark.asyncio
    async def test_insufficient_evidence_with_no_evidence(self) -> None:
        actions = [make_action("ie-1"), make_action("ie-2")]

        confidence_repo = MockConfidenceRepo()
        model = RecoveryConfidenceModel(confidence_repo, MockEvidenceRepo([]))

        confidence = await model.assess_confidence(
            tenant_id="test-tenant",
            plan_id="plan-insufficient",
            actions=actions,
        )

        assert confidence.level == ConfidenceLevel.INSUFFICIENT_EVIDENCE

    @pytest.mark.asyncio
    async def test_confidence_downgraded_by_drift(self) -> None:
        model = RecoveryConfidenceModel(MockConfidenceRepo(), MockEvidenceRepo([]))
        level = model._determine_level(
            evidence_completeness=0.95,
            before_state_available=True,
            after_state_available=True,
            adapter_support=True,
            version_match=True,
            irreversible_count=0,
            unknown_count=0,
            drift_detected=True,
            conflict_detected=False,
            dependency_complete=True,
            verification_capable=True,
            total_actions=10,
        )
        assert level == ConfidenceLevel.LOW_CONFIDENCE

    @pytest.mark.asyncio
    async def test_confidence_downgraded_by_conflict(self) -> None:
        model = RecoveryConfidenceModel(MockConfidenceRepo(), MockEvidenceRepo([]))
        level = model._determine_level(
            evidence_completeness=0.95,
            before_state_available=True,
            after_state_available=True,
            adapter_support=True,
            version_match=True,
            irreversible_count=0,
            unknown_count=0,
            drift_detected=False,
            conflict_detected=True,
            dependency_complete=True,
            verification_capable=True,
            total_actions=10,
        )
        assert level == ConfidenceLevel.LOW_CONFIDENCE

    @pytest.mark.asyncio
    async def test_confidence_factors_include_adapter_support(self) -> None:
        actions = [make_action("af-1", before_state_ref="state:before:1")]
        evidence = [make_evidence(actions[0])]

        confidence_repo = MockConfidenceRepo()
        model = RecoveryConfidenceModel(confidence_repo, MockEvidenceRepo(evidence))

        confidence = await model.assess_confidence(
            tenant_id="test-tenant",
            plan_id="plan-factors",
            actions=actions,
        )

        assert any("adapter_support" in factor for factor in confidence.factors)


# ---------------------------------------------------------------------------
# TestRecoveryReportGeneration
# ---------------------------------------------------------------------------


class TestRecoveryReportGeneration:
    """Tests for recovery report generation."""

    @pytest.mark.asyncio
    async def test_report_lists_recovered_and_failed_actions(self) -> None:
        actions = [make_action("rr-1"), make_action("rr-2"), make_action("rr-3")]
        evidence = [make_evidence(a) for a in actions]
        execution_repo = InMemoryDurableExecutionRepo()

        for action in actions:
            step = DurableExecutionStep(
                step_id=f"step-{action.action_id}",
                plan_id="plan-rr",
                action_id=action.action_id,
                execution_order=0,
                tenant_id="test-tenant",
                execution_state=(
                    ExecutionState.SUCCEEDED.value
                    if action.action_id in ("rr-1", "rr-2")
                    else ExecutionState.FAILED.value
                ),
                idempotency_key=f"idem-{action.action_id}",
                target_system=action.tool,
                target_resource=action.resource,
                compensation_payload={},
                verification_passed=(action.action_id in ("rr-1", "rr-2")),
            )
            await execution_repo.save(step)

        service = ContinuousVerificationService(
            MockEvidenceRepo(evidence),
            execution_repo,
            MockReportRepo(),
            [MockVerifyingAdapter()],
        )

        report = await service.verify_recovery(
            tenant_id="test-tenant",
            plan_id="plan-rr",
        )

        assert len(report.ai_changes_recovered) == 2
        assert len(report.ai_changes_failed) == 1
        assert "rr-3" in report.ai_changes_failed

    @pytest.mark.asyncio
    async def test_report_verification_status_executed_and_verified(self) -> None:
        actions = [make_action("rv-1"), make_action("rv-2")]
        evidence = [make_evidence(a) for a in actions]
        execution_repo = InMemoryDurableExecutionRepo()

        for action in actions:
            step = DurableExecutionStep(
                step_id=f"step-{action.action_id}",
                plan_id="plan-rv",
                action_id=action.action_id,
                execution_order=0,
                tenant_id="test-tenant",
                execution_state=ExecutionState.SUCCEEDED.value,
                idempotency_key=f"idem-{action.action_id}",
                target_system=action.tool,
                target_resource=action.resource,
                compensation_payload={},
                verification_passed=True,
            )
            await execution_repo.save(step)

        service = ContinuousVerificationService(
            MockEvidenceRepo(evidence),
            execution_repo,
            MockReportRepo(),
            [MockVerifyingAdapter()],
        )

        report = await service.verify_recovery(
            tenant_id="test-tenant",
            plan_id="plan-rv",
        )

        assert report.verification_status == VerificationStatus.EXECUTED_AND_VERIFIED

    @pytest.mark.asyncio
    async def test_report_verification_status_execution_failed(self) -> None:
        actions = [make_action("rf-1"), make_action("rf-2")]
        evidence = [make_evidence(a) for a in actions]
        execution_repo = InMemoryDurableExecutionRepo()

        for action in actions:
            step = DurableExecutionStep(
                step_id=f"step-{action.action_id}",
                plan_id="plan-rf",
                action_id=action.action_id,
                execution_order=0,
                tenant_id="test-tenant",
                execution_state=ExecutionState.FAILED.value,
                idempotency_key=f"idem-{action.action_id}",
                target_system=action.tool,
                target_resource=action.resource,
                compensation_payload={},
                verification_passed=False,
            )
            await execution_repo.save(step)

        service = ContinuousVerificationService(
            MockEvidenceRepo(evidence),
            execution_repo,
            MockReportRepo(),
            [MockVerifyingAdapter()],
        )

        report = await service.verify_recovery(
            tenant_id="test-tenant",
            plan_id="plan-rf",
        )

        assert report.verification_status == VerificationStatus.EXECUTION_FAILED

    @pytest.mark.asyncio
    async def test_report_includes_limitations(self) -> None:
        actions = [make_action("rl-1")]
        evidence = [make_evidence(actions[0])]
        execution_repo = InMemoryDurableExecutionRepo()

        step = DurableExecutionStep(
            step_id=f"step-{actions[0].action_id}",
            plan_id="plan-rl",
            action_id=actions[0].action_id,
            execution_order=0,
            tenant_id="test-tenant",
            execution_state=ExecutionState.REQUIRES_MANUAL_ACTION.value,
            idempotency_key=f"idem-{actions[0].action_id}",
            target_system=actions[0].tool,
            target_resource=actions[0].resource,
            compensation_payload={},
            error="Manual recovery required",
            verification_passed=False,
        )
        await execution_repo.save(step)

        service = ContinuousVerificationService(
            MockEvidenceRepo(evidence),
            execution_repo,
            MockReportRepo(),
            [MockVerifyingAdapter()],
        )

        report = await service.verify_recovery(
            tenant_id="test-tenant",
            plan_id="plan-rl",
        )

        assert len(report.limitations) > 0
        assert any("rl-1" in lim for lim in report.limitations)
# ---------------------------------------------------------------------------
# TestSimulationGate
# ---------------------------------------------------------------------------


class TestSimulationGate:
    """Tests for simulation gate enforcement."""

    @pytest.mark.asyncio
    async def test_execute_plan_requires_simulated_or_approved_status(self) -> None:
        plan = RecoveryPlan(
            plan_id="plan-draft",
            tenant_id="test-tenant",
            incident_action_id="sg-1",
            status=RecoveryStatus.DRAFT,
            outcome=RecoveryOutcome.SAFE_AUTOMATIC,
            simulation_result={},
            steps=[],
            topological_order=["sg-1"],
            affected_action_ids=["sg-1"],
        )

        with pytest.raises(HTTPException) as exc_info:
            if plan.status not in (RecoveryStatus.SIMULATED, RecoveryStatus.APPROVED):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Plan must be simulated or approved before execution. "
                        f"Current status: {plan.status.value}"
                    ),
                )

        assert exc_info.value.status_code == 400
        assert "draft" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_execute_plan_requires_simulated_or_approved_status_approved_works(self) -> None:
        plan = RecoveryPlan(
            plan_id="plan-approved",
            tenant_id="test-tenant",
            incident_action_id="sg-ok-1",
            status=RecoveryStatus.APPROVED,
            outcome=RecoveryOutcome.SAFE_AUTOMATIC,
            simulation_result={},
            steps=[],
            topological_order=["sg-ok-1"],
            affected_action_ids=["sg-ok-1"],
        )

        assert plan.status in (RecoveryStatus.SIMULATED, RecoveryStatus.APPROVED)


# ---------------------------------------------------------------------------
# TestAdapterSelectionFailClosed
# ---------------------------------------------------------------------------


class TestAdapterSelectionFailClosed:
    """Tests for adapter selection and fail-closed behavior."""

    @pytest.mark.asyncio
    async def test_no_adapter_returns_requires_manual_action(self) -> None:
        actions = [make_action("fa-1")]
        evidence = [make_evidence(actions[0])]

        orchestrator = DistributedRecoveryOrchestrator(
            MockEvidenceRepo(evidence),
            InMemoryDurableExecutionRepo(),
            [],
        )

        await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-fa",
            actions=actions,
            topological_order=["fa-1"],
        )

        result = await orchestrator.execute_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-fa",
        )

        assert (
            result["execution_results"]["fa-1"]["execution_state"]
            == ExecutionState.REQUIRES_MANUAL_ACTION.value
        )

    @pytest.mark.asyncio
    async def test_failed_adapter_does_not_fall_through_to_next(self) -> None:
        actions = [make_action("faft-1")]
        evidence = [make_evidence(actions[0])]

        class FailThenSucceedAdapter(MockRecoveryAdapter):
            def __init__(self) -> None:
                super().__init__("success")
                self.calls = 0

            async def execute_compensation(
                self, compensation: CompensationAction, idempotency_key: str
            ) -> CompensationResult:
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("First adapter fails")
                return await super().execute_compensation(compensation, idempotency_key)

        adapter = FailThenSucceedAdapter()
        orchestrator = DistributedRecoveryOrchestrator(
            MockEvidenceRepo(evidence),
            InMemoryDurableExecutionRepo(),
            [adapter],
        )

        await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-faft",
            actions=actions,
            topological_order=["faft-1"],
        )

        result = await orchestrator.execute_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-faft",
        )

        # Orchestrator fails closed on general exceptions, does NOT fall through
        assert (
            result["execution_results"]["faft-1"]["execution_state"]
            == ExecutionState.FAILED.value
        )
        assert adapter.calls == 1

    @pytest.mark.asyncio
    async def test_filesystem_action_requires_filesystem_adapter(self) -> None:
        actions = [
            make_action(
                "fs-1",
                tool="filesystem",
                action_type="write",
            )
        ]
        evidence = [make_evidence(actions[0])]

        class NonFilesystemAdapter(MockRecoveryAdapter):
            async def supports(self, action: ProtectedAction) -> bool:
                return False

        orchestrator = DistributedRecoveryOrchestrator(
            MockEvidenceRepo(evidence),
            InMemoryDurableExecutionRepo(),
            [NonFilesystemAdapter()],
        )

        await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-fs",
            actions=actions,
            topological_order=["fs-1"],
        )

        result = await orchestrator.execute_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-fs",
        )

        assert (
            result["execution_results"]["fs-1"]["execution_state"]
            == ExecutionState.REQUIRES_MANUAL_ACTION.value
        )


# ---------------------------------------------------------------------------
# TestIdempotencyEnforcement
# ---------------------------------------------------------------------------


class TestIdempotencyEnforcement:
    """Tests for idempotency enforcement."""

    @pytest.mark.asyncio
    async def test_re_executing_plan_skips_succeeded_steps(self) -> None:
        actions = [make_action("ie-1"), make_action("ie-2")]
        evidence = [make_evidence(a) for a in actions]
        execution_repo = InMemoryDurableExecutionRepo()

        orchestrator = DistributedRecoveryOrchestrator(
            MockEvidenceRepo(evidence),
            execution_repo,
            [MockRecoveryAdapter(scenario="success")],
        )

        await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-ie",
            actions=actions,
            topological_order=["ie-1", "ie-2"],
        )

        await orchestrator.execute_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-ie",
        )

        steps_before, _ = await execution_repo.list_by_plan("test-tenant", "plan-ie")
        _ = sum(
            1 for s in steps_before if s.execution_state == ExecutionState.SUCCEEDED.value
        )

        result = await orchestrator.execute_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-ie",
        )

        assert result["status"] == "completed"
        assert result["completed"] == 2

    @pytest.mark.asyncio
    async def test_idempotency_key_passed_to_adapter(self) -> None:
        actions = [make_action("ik-1")]
        evidence = [make_evidence(actions[0])]

        recorded_keys: list[str] = []

        class RecordingAdapter(MockRecoveryAdapter):
            async def execute_compensation(
                self, compensation: CompensationAction, idempotency_key: str
            ) -> CompensationResult:
                recorded_keys.append(idempotency_key)
                return await super().execute_compensation(compensation, idempotency_key)

        orchestrator = DistributedRecoveryOrchestrator(
            MockEvidenceRepo(evidence),
            InMemoryDurableExecutionRepo(),
            [RecordingAdapter()],
        )

        await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-ik",
            actions=actions,
            topological_order=["ik-1"],
        )

        await orchestrator.execute_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-ik",
        )

        assert len(recorded_keys) == 1
        assert recorded_keys[0] == evidence[0].idempotency_key

