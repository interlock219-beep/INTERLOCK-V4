"""Phase 18: Recovery adapter security unit tests.

Tests verify that recovery planning operations enforce tenant isolation,
do not modify state during preview, and require approval for risky actions.
"""

from __future__ import annotations

from datetime import UTC, datetime
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
from app.domain.services.recovery_planning_service import RecoveryPlanningService

# ---------------------------------------------------------------------------
# Helpers / mocks
# ---------------------------------------------------------------------------


class MockActionRepo:
    def __init__(self, actions: list[ProtectedAction]) -> None:
        self._actions = {a.action_id: a for a in actions}

    async def get_by_action_id(self, tenant_id: str, action_id: str) -> ProtectedAction | None:
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
        children = [
            a for a in self._actions.values()
            if a.parent_action_id == root_action_id and a.tenant_id == tenant_id
        ]
        return children, len(children)

    async def save(self, action: ProtectedAction) -> ProtectedAction:
        self._actions[action.action_id] = action
        return action

    async def update_status(
        self, tenant_id: str, action_id: str, status: ActionStatus, reason: str = ""
    ) -> ProtectedAction | None:
        action = self._actions.get(action_id)
        if action is None or action.tenant_id != tenant_id:
            return None
        action = ProtectedAction(
            action_id=action.action_id,
            tenant_id=action.tenant_id,
            actor_user_id=action.actor_user_id,
            agent_id=action.agent_id,
            authority_grant_id=action.authority_grant_id,
            tool=action.tool,
            resource=action.resource,
            action_type=action.action_type,
            risk_score=action.risk_score,
            policy_version=action.policy_version,
            correlation_id=action.correlation_id,
            parent_action_id=action.parent_action_id,
            workflow_id=action.workflow_id,
            reversibility=action.reversibility,
            before_state_ref=action.before_state_ref,
            after_state_ref=action.after_state_ref,
            tool_arguments=action.tool_arguments,
            status=status,
            decision_reason=reason or action.decision_reason,
            evaluated_at=action.evaluated_at,
            executed_at=action.executed_at,
            created_at=action.created_at,
        )
        self._actions[action_id] = action
        return action


class MockRecoveryRepo:
    def __init__(self, plans: list[RecoveryPlan] | None = None) -> None:
        self._plans: dict[str, RecoveryPlan] = {p.plan_id: p for p in (plans or [])}

    async def get_by_plan_id(self, tenant_id: str, plan_id: str) -> RecoveryPlan | None:
        plan = self._plans.get(plan_id)
        if plan and plan.tenant_id == tenant_id:
            return plan
        return None

    async def list_by_incident(
        self, tenant_id: str, incident_action_id: str, **kwargs: object
    ) -> tuple[list[RecoveryPlan], int]:
        filtered = [
            p for p in self._plans.values()
            if p.tenant_id == tenant_id and p.incident_action_id == incident_action_id
        ]
        return filtered, len(filtered)

    async def save(self, plan: RecoveryPlan) -> RecoveryPlan:
        self._plans[plan.plan_id] = plan
        return plan

    async def update_status(
        self, tenant_id: str, plan_id: str, status: RecoveryStatus, **fields: object
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
        )
        self._plans[plan_id] = updated
        return updated


def _make_action(
    action_id: str,
    tenant_id: str = "test-tenant",
    parent_action_id: str | None = None,
    reversibility: Reversibility = Reversibility.REVERSIBLE,
) -> ProtectedAction:
    return ProtectedAction(
        action_id=action_id,
        tenant_id=tenant_id,
        actor_user_id=uuid4(),
        agent_id="agent-1",
        authority_grant_id=None,
        tool="search",
        resource="res",
        action_type="query",
        reversibility=reversibility,
        parent_action_id=parent_action_id,
        status=ActionStatus.PENDING,
    )


# ---------------------------------------------------------------------------
# Adapter cannot recover actions from another tenant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adapter_cannot_recover_other_tenant_actions() -> None:
    action = _make_action("act-tenant", tenant_id="tenant-a")
    action_repo = MockActionRepo([action])
    recovery_repo = MockRecoveryRepo([])
    service = RecoveryPlanningService(action_repo, recovery_repo)

    with pytest.raises(ValueError, match="not found"):
        await service.create_plan("tenant-b", "act-tenant")


# ---------------------------------------------------------------------------
# Adapter preview doesn't modify state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adapter_preview_does_not_modify_state() -> None:
    action = _make_action("act-preview", reversibility=Reversibility.REVERSIBLE)
    action_repo = MockActionRepo([action])
    recovery_repo = MockRecoveryRepo([])
    service = RecoveryPlanningService(action_repo, recovery_repo)

    plan = await service.create_plan("test-tenant", "act-preview")
    assert plan.status == RecoveryStatus.DRAFT

    simulation = await service.simulate_plan("test-tenant", plan.plan_id)
    assert "affected_actions_count" in simulation
    assert "irreversible_actions" in simulation

    updated_plan = await recovery_repo.get_by_plan_id("test-tenant", plan.plan_id)
    assert updated_plan is not None
    assert updated_plan.status == RecoveryStatus.SIMULATED


# ---------------------------------------------------------------------------
# Adapter execution requires approval for risky actions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adapter_execution_requires_approval_for_risky_actions() -> None:
    action = _make_action("act-risky", reversibility=Reversibility.IRREVERSIBLE)
    action_repo = MockActionRepo([action])
    recovery_repo = MockRecoveryRepo([])
    service = RecoveryPlanningService(action_repo, recovery_repo)

    plan = await service.create_plan("test-tenant", "act-risky")
    assert plan.outcome == RecoveryOutcome.NOT_REVERSIBLE

    with pytest.raises(ValueError, match="irreversible"):
        await service.execute_plan("test-tenant", plan.plan_id, "admin")


# ---------------------------------------------------------------------------
# Recovery plan approval enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_simulated_plan_executes_with_approver() -> None:
    action = _make_action("act-sim-approve", reversibility=Reversibility.REVERSIBLE)
    action_repo = MockActionRepo([action])
    recovery_repo = MockRecoveryRepo([])
    service = RecoveryPlanningService(action_repo, recovery_repo)

    plan = await service.create_plan("test-tenant", "act-sim-approve")
    await service.simulate_plan("test-tenant", plan.plan_id)

    executed = await service.execute_plan("test-tenant", plan.plan_id, "approver-human")
    assert executed.status == RecoveryStatus.COMPLETED
    assert executed.approved_by == "approver-human"
    assert executed.executed_by == "approver-human"


@pytest.mark.asyncio
async def test_simulated_plan_rejected_without_approver() -> None:
    action = _make_action("act-sim-no-approve", reversibility=Reversibility.REVERSIBLE)
    action_repo = MockActionRepo([action])
    recovery_repo = MockRecoveryRepo([])
    service = RecoveryPlanningService(action_repo, recovery_repo)

    plan = await service.create_plan("test-tenant", "act-sim-no-approve")
    await service.simulate_plan("test-tenant", plan.plan_id)

    with pytest.raises(ValueError, match="explicitly approved"):
        await service.execute_plan("test-tenant", plan.plan_id, "")


@pytest.mark.asyncio
async def test_draft_plan_cannot_execute() -> None:
    action = _make_action("act-draft", reversibility=Reversibility.REVERSIBLE)
    action_repo = MockActionRepo([action])
    recovery_repo = MockRecoveryRepo([])
    service = RecoveryPlanningService(action_repo, recovery_repo)

    plan = await service.create_plan("test-tenant", "act-draft")

    with pytest.raises(ValueError, match="does not allow execution"):
        await service.execute_plan("test-tenant", plan.plan_id, "admin")


@pytest.mark.asyncio
async def test_approved_plan_executes() -> None:
    action = _make_action("act-approved", reversibility=Reversibility.REVERSIBLE)
    action_repo = MockActionRepo([action])
    recovery_repo = MockRecoveryRepo([])
    service = RecoveryPlanningService(action_repo, recovery_repo)

    plan = RecoveryPlan(
        plan_id="plan-approved",
        tenant_id="test-tenant",
        incident_action_id="act-approved",
        status=RecoveryStatus.APPROVED,
        outcome=RecoveryOutcome.SAFE_AUTOMATIC,
        simulation_result={},
        steps=[],
        approved_by="pre-approver",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await recovery_repo.save(plan)

    executed = await service.execute_plan("test-tenant", "plan-approved", "executor")
    assert executed.status == RecoveryStatus.COMPLETED
    assert executed.approved_by == "pre-approver"
    assert executed.executed_by == "executor"
