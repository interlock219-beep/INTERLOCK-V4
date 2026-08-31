from __future__ import annotations

import contextlib
import hashlib
import json
import secrets
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any

from app.domain.entities.protected_action import ProtectedAction, Reversibility
from app.domain.entities.recovery_plan import RecoveryOutcome, RecoveryPlan, RecoveryStatus
from app.domain.entities.surgical_recovery_types import (
    ConflictStatus,
    DriftStatus,
    ExecutionState,
    StopCondition,
)
from app.domain.repositories.containment_repository import RecoveryPlanRepository
from app.domain.repositories.protected_action_repository import ProtectedActionRepository
from app.domain.services.recovery_adapter import RecoveryAdapter
from app.infrastructure.observability.metrics import metrics


class RecoveryPlanningService:
    """Recovery planner that generates executable recovery plans.

    Supports both the legacy adapter interface (via :class:`RecoveryAdapter`)
    and the new Protocol-based :class:`CompensatingActionAdapter` surface.
    """

    def __init__(
        self,
        action_repository: ProtectedActionRepository,
        plan_repository: RecoveryPlanRepository,
        adapters: list[RecoveryAdapter] | None = None,
    ) -> None:
        self._action_repo = action_repository
        self._plan_repo = plan_repository
        self._adapters = adapters or []

    async def create_plan(
        self,
        tenant_id: str,
        incident_action_id: str,
        recovery_steps: list[dict[str, str]] | None = None,
    ) -> RecoveryPlan:
        action = await self._action_repo.get_by_action_id(tenant_id, incident_action_id)
        if action is None:
            raise ValueError("Incident action not found")
        descendants, _ = await self._action_repo.list_descendants(
            tenant_id, incident_action_id, limit=1000, offset=0
        )
        reversibility = self._classify_reversibility(action, descendants)
        outcome = self._determine_outcome(reversibility, recovery_steps or [])
        plan_id = f"plan-{secrets.token_hex(12)}"

        affected = [action] + descendants
        topological_order = self._compute_topological_order(affected)
        plan_hash = self._compute_plan_hash(plan_id, incident_action_id, topological_order)
        stop_conditions = self._determine_stop_conditions(affected)

        plan = RecoveryPlan(
            plan_id=plan_id,
            tenant_id=tenant_id,
            incident_action_id=incident_action_id,
            status=RecoveryStatus.DRAFT,
            outcome=outcome,
            simulation_result={},
            steps=recovery_steps or [],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            plan_version="1.0",
            plan_hash=plan_hash,
            topological_order=topological_order,
            dependency_graph_reference=f"graph:{incident_action_id}",
            execution_status="pending",
            approval_policy="single_approval",
            approval_threshold=1,
            stop_conditions=stop_conditions,
            incident_id=incident_action_id,
            root_action_id=incident_action_id,
            affected_action_ids=[a.action_id for a in affected],
        )
        return await self._plan_repo.save(plan)

    async def simulate_plan(
        self, tenant_id: str, plan_id: str
    ) -> dict[str, Any]:
        plan = await self._plan_repo.get_by_plan_id(tenant_id, plan_id)
        if plan is None:
            raise ValueError("Recovery plan not found")
        action = await self._action_repo.get_by_action_id(tenant_id, plan.incident_action_id)
        if action is None:
            raise ValueError("Incident action not found")
        descendants, _ = await self._action_repo.list_descendants(
            tenant_id, plan.incident_action_id, limit=1000, offset=0
        )
        affected = [action] + descendants

        # Use new Protocol-based simulation when available
        simulation_results: dict[str, dict[str, Any]] = {}
        compensation_summary: dict[str, Any] = {}
        for a in affected:
            result = await self._simulate_with_protocol_adapters(a)
            if result:
                simulation_results[a.action_id] = result
                compensation_summary[a.action_id] = {
                    "reversibility": result.get("reversibility", "unknown"),
                    "would_succeed": result.get("would_succeed", False),
                    "drift_status": result.get("drift_status", "unknown"),
                }

        irreversible = [
            a.action_id
            for a in affected
            if Reversibility.normalize(a.reversibility) == Reversibility.IRREVERSIBLE
        ]
        needs_approval = [
            a.action_id
            for a in affected
            if Reversibility.blocks_automatic_execution(a.reversibility)
        ]

        adapter_results: dict[str, dict[str, Any]] = {}
        for a in affected:
            adapter_result = await self._preview_with_adapters(a)
            if adapter_result:
                adapter_results[a.action_id] = adapter_result

        simulation: dict[str, Any] = {
            "plan_id": plan_id,
            "affected_actions_count": len(affected),
            "irreversible_actions": irreversible,
            "approval_required_actions": needs_approval,
            "recovery_order": [a.action_id for a in affected],
            "topological_order": plan.topological_order,
            "estimated_blast_radius": len(affected),
            "connector_availability": "unknown",
            "warnings": [],
            "adapter_results": adapter_results,
            "surgical_simulation_results": simulation_results,
        }
        if irreversible:
            simulation["warnings"].append(
                f"{len(irreversible)} irreversible actions cannot be automatically reversed"
            )
        if needs_approval:
            simulation["warnings"].append(
                f"{len(needs_approval)} actions require human approval before recovery"
            )

        simulated_outcome = self._determine_outcome_from_simulation(
            simulation_results, irreversible, needs_approval, plan.outcome
        )

        plan = RecoveryPlan(
            plan_id=plan.plan_id,
            tenant_id=plan.tenant_id,
            incident_action_id=plan.incident_action_id,
            status=RecoveryStatus.SIMULATED,
            outcome=simulated_outcome,
            simulation_result=simulation,
            steps=plan.steps,
            approved_by=plan.approved_by,
            executed_by=plan.executed_by,
            created_at=plan.created_at,
            updated_at=datetime.now(UTC),
            executed_at=plan.executed_at,
            plan_version="1.0",
            plan_hash=plan.plan_hash,
            topological_order=plan.topological_order,
            dependency_graph_reference=plan.dependency_graph_reference,
            execution_status="simulated",
            approval_policy=plan.approval_policy,
            approval_threshold=plan.approval_threshold,
            stop_conditions=plan.stop_conditions,
            compensation_summary=compensation_summary,
            incident_id=plan.incident_id,
            root_action_id=plan.root_action_id,
            affected_action_ids=plan.affected_action_ids,
        )
        await self._plan_repo.save(plan)
        return simulation

    async def execute_plan(
        self, tenant_id: str, plan_id: str, executed_by: str
    ) -> RecoveryPlan:
        plan = await self._plan_repo.get_by_plan_id(tenant_id, plan_id)
        if plan is None:
            raise ValueError("Recovery plan not found")
        if plan.outcome == RecoveryOutcome.NOT_REVERSIBLE:
            raise ValueError("Cannot execute plan with irreversible actions")
        if plan.outcome == RecoveryOutcome.UNKNOWN:
            raise ValueError("Cannot execute plan with UNKNOWN reversibility — fail closed")
        irreversible = list(plan.simulation_result.get("irreversible_actions", []))
        if irreversible:
            raise ValueError(f"Cannot execute plan with irreversible actions: {irreversible}")
        if plan.status == RecoveryStatus.SIMULATED:
            if not executed_by:
                raise ValueError(
                    "Recovery plan must be explicitly approved before execution"
                )
            plan_approved_by = executed_by
        elif plan.status == RecoveryStatus.APPROVED:
            plan_approved_by = plan.approved_by or executed_by
        else:
            raise ValueError(
                f"Plan status '{plan.status.value}' does not allow execution"
            )

        action = await self._action_repo.get_by_action_id(tenant_id, plan.incident_action_id)
        if action is None:
            raise ValueError("Incident action not found")
        descendants, _ = await self._action_repo.list_descendants(
            tenant_id, plan.incident_action_id, limit=1000, offset=0
        )
        affected = [action] + descendants
        # Execute in topological order (children before parents)
        ordered = self._order_actions_by_topological(affected, plan.topological_order)

        execution_results: dict[str, dict[str, Any]] = {}
        execution_states: dict[str, str] = {}

        for a in ordered:
            result = await self._execute_with_protocol_adapters(a, plan_approved_by)
            if result:
                execution_results[a.action_id] = result
                execution_states[a.action_id] = result.get("execution_state", "succeeded")
                if result.get("execution_state") in (
                    "failed", "blocked_by_conflict", "blocked_by_drift"
                ):
                    stop_conditions = set(
                        self._normalize_stop_conditions(plan.stop_conditions)
                    )
                    if StopCondition.ON_FIRST_FAILURE in stop_conditions:
                        break
                    if (
                        StopCondition.ON_BLOCKING_CONFLICT in stop_conditions
                        and result.get("execution_state") == "blocked_by_conflict"
                    ):
                        break
                    if (
                        StopCondition.ON_BLOCKING_DRIFT in stop_conditions
                        and result.get("execution_state") == "blocked_by_drift"
                    ):
                        break

        all_succeeded = all(
            result.get("execution_state") in ("succeeded", "unknown_external_outcome")
            and result.get("verification_passed") is True
            for result in execution_results.values()
        ) if execution_results else False

        plan = RecoveryPlan(
            plan_id=plan.plan_id,
            tenant_id=plan.tenant_id,
            incident_action_id=plan.incident_action_id,
            status=RecoveryStatus.EXECUTING,
            outcome=RecoveryOutcome.SAFE_AUTOMATIC if all_succeeded else RecoveryOutcome.UNKNOWN,
            simulation_result=plan.simulation_result,
            steps=plan.steps,
            approved_by=plan_approved_by,
            executed_by=executed_by,
            created_at=plan.created_at,
            updated_at=datetime.now(UTC),
            executed_at=None,
            plan_version="1.0",
            plan_hash=plan.plan_hash,
            topological_order=plan.topological_order,
            dependency_graph_reference=plan.dependency_graph_reference,
            execution_status="executing",
            approval_policy=plan.approval_policy,
            approval_threshold=plan.approval_threshold,
            stop_conditions=plan.stop_conditions,
            compensation_summary=plan.compensation_summary,
            incident_id=plan.incident_id,
            root_action_id=plan.root_action_id,
            affected_action_ids=plan.affected_action_ids,
        )
        plan = await self._plan_repo.save(plan)

        updated_simulation = dict(plan.simulation_result)
        updated_simulation["execution_results"] = execution_results

        plan = RecoveryPlan(
            plan_id=plan.plan_id,
            tenant_id=plan.tenant_id,
            incident_action_id=plan.incident_action_id,
            status=RecoveryStatus.COMPLETED,
            outcome=RecoveryOutcome.SAFE_AUTOMATIC if all_succeeded else RecoveryOutcome.UNKNOWN,
            simulation_result=updated_simulation,
            steps=plan.steps,
            approved_by=plan_approved_by,
            executed_by=executed_by,
            created_at=plan.created_at,
            updated_at=datetime.now(UTC),
            executed_at=datetime.now(UTC),
            plan_version="1.0",
            plan_hash=plan.plan_hash,
            topological_order=plan.topological_order,
            dependency_graph_reference=plan.dependency_graph_reference,
            execution_status="completed",
            approval_policy=plan.approval_policy,
            approval_threshold=plan.approval_threshold,
            stop_conditions=plan.stop_conditions,
            compensation_summary=plan.compensation_summary,
            incident_id=plan.incident_id,
            root_action_id=plan.root_action_id,
            affected_action_ids=plan.affected_action_ids,
        )
        return await self._plan_repo.save(plan)

    async def _simulate_with_protocol_adapters(
        self, action: ProtectedAction
    ) -> dict[str, Any] | None:
        """Use the new Protocol-based adapter methods for detailed simulation."""
        for adapter in self._adapters:
            try:
                if not hasattr(adapter, "capture_recovery_evidence"):
                    continue
                evidence = await adapter.capture_recovery_evidence(action)
                reversibility = await adapter.classify_reversibility(action, evidence)
                impact = await adapter.simulate(action, evidence)
                drift = await adapter.detect_drift(action, evidence)
                conflict = await adapter.check_conflicts(action, evidence)
                precond = await adapter.check_preconditions(action)
                return {
                    "adapter": getattr(adapter, "adapter_name", adapter.__class__.__name__),
                    "reversibility": reversibility.value,
                    "would_succeed": impact.would_succeed,
                    "drift_status": drift.status.value,
                    "conflict_status": conflict.status.value,
                    "preconditions_satisfied": precond.satisfied,
                    "warnings": impact.warnings,
                    "simulation_limitation": (
                        impact.simulation_limitation.value
                        if impact.simulation_limitation
                        else None
                    ),
                    "compensation_operation": impact.compensation_operation,
                    "expected_after_state": impact.expected_after_state,
                }
            except (AttributeError, TypeError):
                continue
            except Exception as exc:
                return {
                    "adapter": getattr(adapter, "adapter_name", adapter.__class__.__name__),
                    "error": str(exc),
                    "would_succeed": False,
                }
        return None

    async def _execute_with_protocol_adapters(
        self, action: ProtectedAction, approved_by: str
    ) -> dict[str, Any] | None:
        """Use the new Protocol-based adapter methods for compensation execution."""
        for adapter in self._adapters:
            try:
                if not hasattr(adapter, "capture_recovery_evidence"):
                    continue
                evidence = await adapter.capture_recovery_evidence(action)
                reversibility = await adapter.classify_reversibility(action, evidence)

                if reversibility == Reversibility.IRREVERSIBLE:
                    return {
                        "adapter": getattr(adapter, "adapter_name", adapter.__class__.__name__),
                        "execution_state": ExecutionState.BLOCKED_BY_CONFLICT.value,
                        "success": False,
                        "error": "Action is irreversible",
                    }

                precond = await adapter.check_preconditions(action)
                if not precond.satisfied:
                    return {
                        "adapter": getattr(adapter, "adapter_name", adapter.__class__.__name__),
                        "execution_state": ExecutionState.BLOCKED_BY_CONFLICT.value,
                        "success": False,
                        "error": f"Preconditions not satisfied: {precond.failed_checks}",
                    }

                drift = await adapter.detect_drift(action, evidence)
                if drift.status != DriftStatus.NO_DRIFT:
                    return {
                        "adapter": getattr(adapter, "adapter_name", adapter.__class__.__name__),
                        "execution_state": ExecutionState.BLOCKED_BY_DRIFT.value,
                        "success": False,
                        "error": f"Drift detected: {drift.status.value}",
                    }

                conflict = await adapter.check_conflicts(action, evidence)
                if conflict.status != ConflictStatus.NO_CONFLICT:
                    return {
                        "adapter": getattr(adapter, "adapter_name", adapter.__class__.__name__),
                        "execution_state": ExecutionState.BLOCKED_BY_CONFLICT.value,
                        "success": False,
                        "error": f"Conflict detected: {conflict.status.value}",
                    }

                compensation = await adapter.generate_compensation(action, evidence)
                metrics.increment_recovery_adapter_call(adapter.__class__.__name__)
                result = await adapter.execute_compensation(compensation, evidence.idempotency_key)
                verification = await adapter.verify(compensation)

                return {
                    "adapter": getattr(adapter, "adapter_name", adapter.__class__.__name__),
                    "execution_state": result.execution_state.value,
                    "success": result.success,
                    "external_outcome": result.external_outcome,
                    "verification_passed": verification.verified,
                    "compensation_type": compensation.compensation_type.value,
                    "idempotency_key": result.idempotency_key,
                }
            except (AttributeError, TypeError):
                continue
            except Exception as exc:
                return {
                    "adapter": getattr(adapter, "adapter_name", adapter.__class__.__name__),
                    "execution_state": ExecutionState.FAILED.value,
                    "success": False,
                    "error": str(exc),
                }
        return None

    async def _preview_with_adapters(
        self, action: ProtectedAction
    ) -> dict[str, Any] | None:
        for adapter in self._adapters:
            capability = await adapter.can_recover(action)
            if capability in ("reversible", "reversible_with_approval"):
                metrics.increment_recovery_adapter_call(adapter.__class__.__name__)
                return await adapter.preview_recovery(action)
        return None

    @staticmethod
    def _compute_topological_order(affected: list[ProtectedAction]) -> list[str]:
        """Compute topological order: children before parents (leaf-first).

        Uses post-order traversal: leaf nodes (no children in the affected set)
        are emitted first, then their parents once all children are emitted.
        """
        if not affected:
            return []
        id_to_parent: dict[str, str | None] = {}
        child_counts: dict[str, int] = defaultdict(int)
        children: dict[str, list[str]] = defaultdict(list)
        for a in affected:
            id_to_parent[a.action_id] = a.parent_action_id
            if a.parent_action_id:
                child_counts[a.parent_action_id] += 1
                children[a.parent_action_id].append(a.action_id)

        queue: deque[str] = deque()
        for a in affected:
            if child_counts.get(a.action_id, 0) == 0:
                queue.append(a.action_id)

        order: list[str] = []
        visited: set[str] = set()
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            order.append(current)
            parent = id_to_parent.get(current)
            if parent is not None and parent in id_to_parent:
                child_counts[parent] -= 1
                if child_counts[parent] == 0:
                    queue.append(parent)

        for a in affected:
            if a.action_id not in visited:
                order.append(a.action_id)

        return order

    @staticmethod
    def _order_actions_by_topological(
        affected: list[ProtectedAction], topo_order: list[str]
    ) -> list[ProtectedAction]:
        """Order actions by topological order, falling back to input order."""
        order_map = {aid: idx for idx, aid in enumerate(topo_order)}
        sorted_actions = sorted(
            affected,
            key=lambda a: order_map.get(a.action_id, len(order_map)),
        )
        return sorted_actions

    @staticmethod
    def _compute_plan_hash(
        plan_id: str, incident_action_id: str, topological_order: list[str]
    ) -> str:
        payload = f"{incident_action_id}:{json.dumps(topological_order, sort_keys=True)}"
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _determine_stop_conditions(affected: list[ProtectedAction]) -> list[str]:
        """Determine stop conditions based on affected actions."""
        has_irreversible = any(
            Reversibility.normalize(a.reversibility) == Reversibility.IRREVERSIBLE
            for a in affected
        )
        stop_conditions = [StopCondition.ON_FIRST_FAILURE.value]
        if has_irreversible:
            stop_conditions.append(StopCondition.ON_BLOCKING_CONFLICT.value)
        return stop_conditions

    @staticmethod
    def _classify_reversibility(
        action: ProtectedAction, descendants: list[ProtectedAction]
    ) -> Reversibility:
        all_actions = [action] + descendants
        if any(
            Reversibility.normalize(a.reversibility) == Reversibility.IRREVERSIBLE
            for a in all_actions
        ):
            return Reversibility.IRREVERSIBLE
        if any(
            Reversibility.normalize(a.reversibility) == Reversibility.CONDITIONALLY_REVERSIBLE
            for a in all_actions
        ):
            return Reversibility.CONDITIONALLY_REVERSIBLE
        if all(
            Reversibility.normalize(a.reversibility) == Reversibility.AUTOMATICALLY_REVERSIBLE
            for a in all_actions
        ):
            return Reversibility.AUTOMATICALLY_REVERSIBLE
        if any(
            Reversibility.normalize(a.reversibility) == Reversibility.MANUALLY_RECOVERABLE
            for a in all_actions
        ):
            return Reversibility.MANUALLY_RECOVERABLE
        return Reversibility.UNKNOWN

    @staticmethod
    def _determine_outcome(
        reversibility: Reversibility, steps: list[dict[str, str]]
    ) -> RecoveryOutcome:
        n = Reversibility.normalize(reversibility)
        if n == Reversibility.IRREVERSIBLE:
            return RecoveryOutcome.NOT_REVERSIBLE
        if n == Reversibility.UNKNOWN:
            return RecoveryOutcome.UNKNOWN
        if n == Reversibility.MANUALLY_RECOVERABLE:
            return RecoveryOutcome.REQUIRES_HUMAN_APPROVAL
        if any(step.get("requires_approval", "").lower() == "true" for step in steps):
            return RecoveryOutcome.REQUIRES_HUMAN_APPROVAL
        if Reversibility.is_conditional(n):
            return RecoveryOutcome.REQUIRES_HUMAN_APPROVAL
        return RecoveryOutcome.SAFE_AUTOMATIC

    @staticmethod
    def _normalize_stop_conditions(stop_conditions: list[str]) -> list[StopCondition]:
        """Normalize stop condition strings to StopCondition enum values."""
        normalized: list[StopCondition] = []
        for sc in stop_conditions:
            with contextlib.suppress(ValueError):
                normalized.append(StopCondition(sc))
        return normalized

    @staticmethod
    def _determine_outcome_from_simulation(
        simulation_results: dict[str, dict[str, Any]],
        irreversible: list[str],
        needs_approval: list[str],
        fallback_outcome: RecoveryOutcome,
    ) -> RecoveryOutcome:
        if irreversible:
            return RecoveryOutcome.NOT_REVERSIBLE
        if needs_approval:
            return RecoveryOutcome.REQUIRES_HUMAN_APPROVAL
        if simulation_results:
            reversibilities = [
                Reversibility.normalize(result.get("reversibility", "unknown"))
                for result in simulation_results.values()
            ]
            if any(r == Reversibility.UNKNOWN for r in reversibilities):
                return RecoveryOutcome.UNKNOWN
            if any(r == Reversibility.IRREVERSIBLE for r in reversibilities):
                return RecoveryOutcome.NOT_REVERSIBLE
            if any(r == Reversibility.MANUALLY_RECOVERABLE for r in reversibilities):
                return RecoveryOutcome.REQUIRES_HUMAN_APPROVAL
            return RecoveryOutcome.SAFE_AUTOMATIC
        return fallback_outcome
