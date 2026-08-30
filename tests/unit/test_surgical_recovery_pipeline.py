"""Phase 19: Surgical rollback & causal recovery engine — pipeline unit tests.

Tests verify topological ordering, plan hashing, stop-condition handling,
Protocol-based adapter simulation, Protocol-based compensation execution,
fail-closed behaviour on UNKNOWN, and repository round-trips.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from app.domain.entities.protected_action import (
    ActionStatus,
    ProtectedAction,
    Reversibility,
)
from app.domain.entities.recovery_plan import (
    RecoveryOutcome,
    RecoveryPlan,
    RecoveryStatus,
)
from app.domain.entities.surgical_recovery_types import (
    AdapterCapability,
    CompensationType,
    ConflictStatus,
    DriftStatus,
    ExecutionState,
    RecoveryAdapterType,
    SimulationLimitation,
)
from app.domain.services.recovery_adapter import RecoveryAdapter
from app.domain.services.recovery_planning_service import RecoveryPlanningService
from app.infrastructure.recovery.mock_adapter import MockRecoveryAdapter

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_action(
    action_id: str,
    tenant_id: str = "test-tenant",
    parent_action_id: str | None = None,
    reversibility: Reversibility = Reversibility.AUTOMATICALLY_REVERSIBLE,
    before_state_ref: str | None = "state:before:123",
) -> ProtectedAction:
    return ProtectedAction(
        action_id=action_id,
        tenant_id=tenant_id,
        actor_user_id=uuid4(),
        agent_id="agent-1",
        authority_grant_id=None,
        tool="database",
        resource=f"record:{action_id}",
        action_type="insert",
        reversibility=reversibility,
        parent_action_id=parent_action_id,
        before_state_ref=before_state_ref,
        after_state_ref="state:after:456" if before_state_ref else None,
        status=ActionStatus.EXECUTED,
    )


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

    async def update_status(
        self,
        tenant_id: str,
        action_id: str,
        status: ActionStatus,
        reason: str = "",
    ) -> ProtectedAction | None:
        return None


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
            if p.tenant_id == tenant_id
            and p.incident_action_id == incident_action_id
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


# ---------------------------------------------------------------------------
# Topological ordering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_topological_order_children_before_parents() -> None:
    root = _make_action("root", reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE)
    child1 = _make_action("child1", parent_action_id="root")
    child2 = _make_action("child2", parent_action_id="child1")
    repo = MockActionRepo([root, child1, child2])
    plan_repo = MockPlanRepo([])
    service = RecoveryPlanningService(repo, plan_repo)

    plan = await service.create_plan("test-tenant", "root")
    assert len(plan.topological_order) == 3
    assert plan.topological_order.index("child2") < plan.topological_order.index("child1")
    assert plan.topological_order.index("child1") < plan.topological_order.index("root")


# ---------------------------------------------------------------------------
# Plan hashing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_hash_is_deterministic() -> None:
    root = _make_action("root")
    repo = MockActionRepo([root])
    plan_repo = MockPlanRepo([])
    service = RecoveryPlanningService(repo, plan_repo)

    plan1 = await service.create_plan("test-tenant", "root")
    plan2 = await service.create_plan("test-tenant", "root")
    assert plan1.plan_hash == plan2.plan_hash
    assert len(plan1.plan_hash) == 64


# ---------------------------------------------------------------------------
# Stop conditions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_conditions_include_on_first_failure() -> None:
    root = _make_action("root")
    repo = MockActionRepo([root])
    plan_repo = MockPlanRepo([])
    service = RecoveryPlanningService(repo, plan_repo)

    plan = await service.create_plan("test-tenant", "root")
    assert "on_first_failure" in plan.stop_conditions


@pytest.mark.asyncio
async def test_stop_conditions_include_blocking_conflict_for_irreversible() -> None:
    root = _make_action("root", reversibility=Reversibility.IRREVERSIBLE)
    repo = MockActionRepo([root])
    plan_repo = MockPlanRepo([])
    service = RecoveryPlanningService(repo, plan_repo)

    plan = await service.create_plan("test-tenant", "root")
    assert "on_blocking_conflict" in plan.stop_conditions


@pytest.mark.asyncio
async def test_stop_conditions_for_conditionally_reversible() -> None:
    root = _make_action("root", reversibility=Reversibility.CONDITIONALLY_REVERSIBLE)
    repo = MockActionRepo([root])
    plan_repo = MockPlanRepo([])
    service = RecoveryPlanningService(repo, plan_repo)

    plan = await service.create_plan("test-tenant", "root")
    assert "on_first_failure" in plan.stop_conditions
    assert "on_blocking_conflict" not in plan.stop_conditions


# ---------------------------------------------------------------------------
# Protocol-based adapter simulation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_protocol_simulation_captures_surgical_details() -> None:
    root = _make_action("root", reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE)
    repo = MockActionRepo([root])
    plan_repo = MockPlanRepo([])
    adapter = MockRecoveryAdapter(scenario="success")
    service = RecoveryPlanningService(repo, plan_repo, adapters=[adapter])

    plan = await service.create_plan("test-tenant", "root")
    simulation = await service.simulate_plan("test-tenant", plan.plan_id)

    assert "surgical_simulation_results" in simulation
    sim_result = simulation["surgical_simulation_results"]["root"]
    assert sim_result["reversibility"] == "automatically_reversible"
    assert sim_result["would_succeed"] is True
    assert sim_result["drift_status"] == "no_drift"
    assert sim_result["conflict_status"] == "no_conflict"
    assert sim_result["preconditions_satisfied"] is True


@pytest.mark.asyncio
async def test_protocol_simulation_fail_closed_on_error() -> None:
    root = _make_action("root", reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE)
    repo = MockActionRepo([root])
    plan_repo = MockPlanRepo([])
    adapter = MockRecoveryAdapter(scenario="force_fail")
    service = RecoveryPlanningService(repo, plan_repo, adapters=[adapter])

    plan = await service.create_plan("test-tenant", "root")
    simulation = await service.simulate_plan("test-tenant", plan.plan_id)

    sim_result = simulation["surgical_simulation_results"]["root"]
    assert sim_result["would_succeed"] is False


# ---------------------------------------------------------------------------
# Protocol-based compensation execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_protocol_execution_produces_compensation() -> None:
    root = _make_action("root", reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE)
    repo = MockActionRepo([root])
    plan_repo = MockPlanRepo([])
    adapter = MockRecoveryAdapter(scenario="success")
    service = RecoveryPlanningService(repo, plan_repo, adapters=[adapter])

    plan = await service.create_plan("test-tenant", "root")
    await service.simulate_plan("test-tenant", plan.plan_id)
    executed = await service.execute_plan("test-tenant", plan.plan_id, "approver-1")

    assert executed.status == RecoveryStatus.COMPLETED
    sim_result = executed.simulation_result.get("execution_results", {})
    assert "root" in sim_result
    assert sim_result["root"]["success"] is True
    assert sim_result["root"]["execution_state"] == ExecutionState.SUCCEEDED.value


@pytest.mark.asyncio
async def test_protocol_execution_handles_failure_and_stop_condition() -> None:
    root = _make_action("root", reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE)
    child = _make_action("child", parent_action_id="root")
    repo = MockActionRepo([root, child])
    plan_repo = MockPlanRepo([])
    adapter = MockRecoveryAdapter(scenario="execute_fail")
    service = RecoveryPlanningService(repo, plan_repo, adapters=[adapter])

    plan = await service.create_plan("test-tenant", "root")
    await service.simulate_plan("test-tenant", plan.plan_id)
    executed = await service.execute_plan("test-tenant", plan.plan_id, "approver-1")

    execution_results = executed.simulation_result.get("execution_results", {})
    first_action = next(iter(execution_results))
    assert execution_results[first_action]["success"] is False
    assert execution_results[first_action]["execution_state"] == ExecutionState.FAILED.value


@pytest.mark.asyncio
async def test_execute_plan_fails_for_irreversible() -> None:
    root = _make_action("root", reversibility=Reversibility.IRREVERSIBLE)
    repo = MockActionRepo([root])
    plan_repo = MockPlanRepo([])
    service = RecoveryPlanningService(repo, plan_repo)

    plan = await service.create_plan("test-tenant", "root")
    with pytest.raises(ValueError, match="irreversible"):
        await service.execute_plan("test-tenant", plan.plan_id, "admin")


@pytest.mark.asyncio
async def test_execute_draft_plan_fails() -> None:
    root = _make_action("root", reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE)
    repo = MockActionRepo([root])
    plan_repo = MockPlanRepo([])
    service = RecoveryPlanningService(repo, plan_repo)

    plan = await service.create_plan("test-tenant", "root")
    with pytest.raises(ValueError, match="does not allow execution"):
        await service.execute_plan("test-tenant", plan.plan_id, "admin")


@pytest.mark.asyncio
async def test_execute_simulated_plan_without_approver_fails() -> None:
    root = _make_action("root", reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE)
    repo = MockActionRepo([root])
    plan_repo = MockPlanRepo([])
    service = RecoveryPlanningService(repo, plan_repo)

    plan = await service.create_plan("test-tenant", "root")
    await service.simulate_plan("test-tenant", plan.plan_id)

    with pytest.raises(ValueError, match="explicitly approved"):
        await service.execute_plan("test-tenant", plan.plan_id, "")


# ---------------------------------------------------------------------------
# Mock adapter scenario behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_adapter_drift_scenario() -> None:
    root = _make_action(
        "root", reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE
    )
    repo = MockActionRepo([root])
    plan_repo = MockPlanRepo([])
    adapter = MockRecoveryAdapter(scenario="drift_detected")
    service = RecoveryPlanningService(repo, plan_repo, adapters=[adapter])

    plan = await service.create_plan("test-tenant", "root")
    simulation = await service.simulate_plan("test-tenant", plan.plan_id)

    sim_result = simulation["surgical_simulation_results"]["root"]
    assert sim_result["drift_status"] == DriftStatus.DRIFT_DETECTED.value


@pytest.mark.asyncio
async def test_mock_adapter_conflict_scenario() -> None:
    root = _make_action(
        "root", reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE
    )
    repo = MockActionRepo([root])
    plan_repo = MockPlanRepo([])
    adapter = MockRecoveryAdapter(scenario="conflict_detected")
    service = RecoveryPlanningService(repo, plan_repo, adapters=[adapter])

    plan = await service.create_plan("test-tenant", "root")
    simulation = await service.simulate_plan("test-tenant", plan.plan_id)

    sim_result = simulation["surgical_simulation_results"]["root"]
    assert sim_result["conflict_status"] != ConflictStatus.NO_CONFLICT.value


# ---------------------------------------------------------------------------
# Fail-closed on UNKNOWN reversibility
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_reversibility_fails_closed() -> None:
    root = _make_action("root", reversibility=Reversibility.UNKNOWN, before_state_ref=None)
    repo = MockActionRepo([root])
    plan_repo = MockPlanRepo([])
    adapter = MockRecoveryAdapter(scenario="unknown_reversibility")
    service = RecoveryPlanningService(repo, plan_repo, adapters=[adapter])

    plan = await service.create_plan("test-tenant", "root")
    assert plan.outcome == RecoveryOutcome.UNKNOWN
    with pytest.raises(ValueError, match="UNKNOWN"):
        await service.execute_plan("test-tenant", plan.plan_id, "admin")


# ---------------------------------------------------------------------------
# Repository round-trip: RecoveryEvidence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_evidence_repository_round_trip(db_session: Any) -> None:
    from app.domain.entities.surgical_recovery_types import (
        RecoveryEvidence as RecoveryEvidenceEntity,
    )
    from app.infrastructure.persistence.repositories.sqlalchemy_recovery_evidence_repository import (  # noqa: E501
        SQLAlchemyRecoveryEvidenceRepository,
    )

    repo = SQLAlchemyRecoveryEvidenceRepository(db_session)
    evidence = RecoveryEvidenceEntity(
        evidence_id="ev-test-1",
        action_id="act-test-1",
        tenant_id="tenant-test",
        agent_id="agent-1",
        authority_grant_id=None,
        parent_action_id=None,
        root_action_id="act-test-1",
        correlation_id="corr-1",
        incident_id="inc-1",
        target_system="database",
        target_resource="record:123",
        action_type="insert",
        before_state_reference="state:before:123",
        after_state_reference="state:after:456",
        compensation_payload={"op": "restore"},
        compensation_type=CompensationType.REVERSE_OPERATION,
        recovery_adapter_type=RecoveryAdapterType.DATABASE_RECORD,
        idempotency_key="idem-1",
        dependency_edges=[],
        reversibility_classification=Reversibility.AUTOMATICALLY_REVERSIBLE,
        verification_requirements=["record_exists"],
        evidence_hash="hash-abc",
        adapter_capability=AdapterCapability.REFERENCE_IMPLEMENTATION,
    )

    saved = await repo.save(evidence)
    assert saved.evidence_id == "ev-test-1"

    fetched = await repo.get_by_evidence_id("tenant-test", "ev-test-1")
    assert fetched is not None
    assert fetched.action_id == "act-test-1"
    assert fetched.compensation_type == CompensationType.REVERSE_OPERATION
    assert fetched.reversibility_classification == Reversibility.AUTOMATICALLY_REVERSIBLE

    by_action = await repo.get_by_action_id("tenant-test", "act-test-1")
    assert by_action is not None
    assert by_action.evidence_id == "ev-test-1"

    listed, total = await repo.list_by_incident("tenant-test", "inc-1")
    assert total == 1
    assert len(listed) == 1


@pytest.mark.asyncio
async def test_recovery_evidence_tenant_isolation(db_session: Any) -> None:
    from app.domain.entities.surgical_recovery_types import (
        RecoveryEvidence as RecoveryEvidenceEntity,
    )
    from app.infrastructure.persistence.repositories.sqlalchemy_recovery_evidence_repository import (  # noqa: E501
        SQLAlchemyRecoveryEvidenceRepository,
    )

    repo = SQLAlchemyRecoveryEvidenceRepository(db_session)
    evidence = RecoveryEvidenceEntity(
        evidence_id="ev-tenant-iso",
        action_id="act-iso",
        tenant_id="tenant-a",
        agent_id="agent-1",
        authority_grant_id=None,
        parent_action_id=None,
        root_action_id="act-iso",
        correlation_id="corr",
        incident_id="inc-1",
        target_system="database",
        target_resource="record:x",
        action_type="insert",
        before_state_reference="state:before",
        after_state_reference="state:after",
        compensation_payload={},
        compensation_type=CompensationType.REVERSE_OPERATION,
        recovery_adapter_type=RecoveryAdapterType.DATABASE_RECORD,
        idempotency_key="idem-iso",
        dependency_edges=[],
        reversibility_classification=Reversibility.AUTOMATICALLY_REVERSIBLE,
    )

    await repo.save(evidence)

    fetched = await repo.get_by_evidence_id("tenant-b", "ev-tenant-iso")
    assert fetched is None


# ---------------------------------------------------------------------------
# Repository round-trip: RecoveryExecution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_execution_repository_round_trip(db_session: Any) -> None:
    from app.domain.entities.surgical_recovery_types import (
        RecoveryExecution as RecoveryExecutionEntity,
    )
    from app.infrastructure.persistence.repositories.sqlalchemy_recovery_execution_repository import (  # noqa: E501
        SQLAlchemyRecoveryExecutionRepository,
    )

    repo = SQLAlchemyRecoveryExecutionRepository(db_session)
    execution = RecoveryExecutionEntity(
        execution_id="exec-test-1",
        plan_id="plan-test-1",
        action_id="act-test-1",
        tenant_id="tenant-test",
        compensation_type=CompensationType.REVERSE_OPERATION,
        target_system="database",
        target_resource="record:123",
        idempotency_key="idem-1",
        execution_order=1,
        execution_state=ExecutionState.SUCCEEDED,
        success=True,
        error=None,
        details={"result": "restored"},
        external_outcome="restored",
        verification_passed=True,
        verification_details={},
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        executed_by="approver-1",
    )

    saved = await repo.save(execution)
    assert saved.execution_id == "exec-test-1"

    fetched = await repo.get_by_execution_id("tenant-test", "exec-test-1")
    assert fetched is not None
    assert fetched.action_id == "act-test-1"
    assert fetched.compensation_type == CompensationType.REVERSE_OPERATION
    assert fetched.execution_state == ExecutionState.SUCCEEDED
    assert fetched.success is True

    listed, total = await repo.list_by_plan("tenant-test", "plan-test-1")
    assert total == 1
    assert len(listed) == 1

    by_action, total_by_action = await repo.list_by_action("tenant-test", "act-test-1")
    assert total_by_action == 1
    assert len(by_action) == 1


# ---------------------------------------------------------------------------
# Mock adapter interface compliance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_adapter_implements_full_protocol() -> None:
    adapter = MockRecoveryAdapter(scenario="success")
    assert adapter.adapter_name == "mock"
    assert adapter.adapter_type == "mock"
    assert adapter.capability == AdapterCapability.MOCK

    action = _make_action("mock-action")
    supported = await adapter.supports(action)
    assert supported is True

    evidence = await adapter.capture_recovery_evidence(action)
    assert evidence.evidence_id == "ev-mock-action"
    assert evidence.adapter_capability == AdapterCapability.MOCK
    assert evidence.recovery_adapter_type == RecoveryAdapterType.MOCK

    reversibility = await adapter.classify_reversibility(action, evidence)
    assert reversibility == Reversibility.AUTOMATICALLY_REVERSIBLE

    impact = await adapter.simulate(action, evidence)
    assert impact.would_succeed is True
    assert impact.simulation_limitation == SimulationLimitation.SIMULATION_COMPLETE

    precond = await adapter.check_preconditions(action)
    assert precond.satisfied is True

    drift = await adapter.detect_drift(action, evidence)
    assert drift.status == DriftStatus.NO_DRIFT

    conflict = await adapter.check_conflicts(action, evidence)
    assert conflict.status == ConflictStatus.NO_CONFLICT

    compensation = await adapter.generate_compensation(action, evidence)
    assert compensation.compensation_type == CompensationType.REVERSE_OPERATION

    result = await adapter.execute_compensation(compensation, "idem-mock-action")
    assert result.success is True
    assert result.execution_state == ExecutionState.SUCCEEDED

    verification = await adapter.verify(compensation)
    assert verification.verified is False


@pytest.mark.asyncio
async def test_mock_adapter_scenario_execution_failure() -> None:
    adapter = MockRecoveryAdapter(scenario="execute_fail")
    action = _make_action("mock-fail")
    evidence = await adapter.capture_recovery_evidence(action)
    compensation = await adapter.generate_compensation(action, evidence)
    result = await adapter.execute_compensation(compensation, "idem-mock-fail")
    assert result.success is False
    assert result.execution_state == ExecutionState.FAILED


@pytest.mark.asyncio
async def test_mock_adapter_scenario_drift_blocks_execution() -> None:
    adapter = MockRecoveryAdapter(scenario="drift_detected")
    action = _make_action("mock-drift")
    evidence = await adapter.capture_recovery_evidence(action)
    compensation = await adapter.generate_compensation(action, evidence)
    result = await adapter.execute_compensation(compensation, "idem-mock-drift")
    assert result.execution_state == ExecutionState.BLOCKED_BY_DRIFT


@pytest.mark.asyncio
async def test_mock_adapter_scenario_conflict_blocks_execution() -> None:
    adapter = MockRecoveryAdapter(scenario="conflict_detected")
    action = _make_action("mock-conflict")
    evidence = await adapter.capture_recovery_evidence(action)
    compensation = await adapter.generate_compensation(action, evidence)
    result = await adapter.execute_compensation(compensation, "idem-mock-conflict")
    assert result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT


# ---------------------------------------------------------------------------
# RecoveryAdapter base class compliance via legacy adapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_adapter_base_class_wraps_legacy_adapter() -> None:
    from app.infrastructure.recovery.database_record_adapter import DatabaseRecordAdapter

    adapter = DatabaseRecordAdapter()
    assert issubclass(DatabaseRecordAdapter, RecoveryAdapter)

    action = _make_action("db-action")
    evidence = await adapter.capture_recovery_evidence(action)
    assert evidence.evidence_id == "ev-db-action"

    reversibility = await adapter.classify_reversibility(action, evidence)
    assert reversibility == Reversibility.AUTOMATICALLY_REVERSIBLE

    impact = await adapter.simulate(action, evidence)
    assert impact.reversibility == Reversibility.AUTOMATICALLY_REVERSIBLE
    assert impact.compensation_operation == "restore_record"
    assert impact.would_succeed is False
    assert impact.drift_status == DriftStatus.INSUFFICIENT_EVIDENCE

    compensation = await adapter.generate_compensation(action, evidence)
    result = await adapter.execute_compensation(compensation, "idem-db-action")
    assert result.success is False
    assert result.execution_state == ExecutionState.REQUIRES_MANUAL_ACTION
    assert result.external_outcome == "reference_adapter_not_implemented"

    verification = await adapter.verify(compensation)
    assert verification.verified is False


# ---------------------------------------------------------------------------
# Compensation summary in simulation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_simulation_populates_compensation_summary() -> None:
    root = _make_action("root", reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE)
    repo = MockActionRepo([root])
    plan_repo = MockPlanRepo([])
    adapter = MockRecoveryAdapter(scenario="success")
    service = RecoveryPlanningService(repo, plan_repo, adapters=[adapter])

    plan = await service.create_plan("test-tenant", "root")
    await service.simulate_plan("test-tenant", plan.plan_id)

    saved = await plan_repo.get_by_plan_id("test-tenant", plan.plan_id)
    assert saved is not None
    summary = saved.compensation_summary
    assert "root" in summary
    assert summary["root"]["reversibility"] == "automatically_reversible"
    assert summary["root"]["would_succeed"] is True
