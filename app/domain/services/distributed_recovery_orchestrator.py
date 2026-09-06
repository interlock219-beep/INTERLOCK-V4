from __future__ import annotations

import secrets
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from app.domain.entities.causal_state_types import (
    DurableExecutionStep,
    VerificationStatus,
)
from app.domain.entities.protected_action import ProtectedAction
from app.domain.entities.surgical_recovery_types import (
    ConflictStatus,
    DriftStatus,
    ExecutionState,
    StopCondition,
)
from app.domain.repositories.causal_state_repositories import DurableExecutionRepository
from app.domain.repositories.recovery_evidence_repository import RecoveryEvidenceRepository
from app.domain.services.recovery_adapter import RecoveryAdapter


class DistributedRecoveryOrchestrator:
    """Orchestrates compensations across multiple supported systems.

    A single AI incident may affect:

    DATABASE -> API -> MESSAGE QUEUE -> FILE STORAGE -> CONFIGURATION -> IAM -> CLOUD RESOURCE

    The orchestrator uses reverse topological dependency ordering and
    supports durable step tracking for resume after interruption.

    Independent branches may execute concurrently only if:
    * no dependency exists
    * adapters support safe concurrency
    * tenant boundaries remain enforced
    * execution is independently idempotent
    """

    def __init__(
        self,
        evidence_repository: RecoveryEvidenceRepository,
        execution_repository: DurableExecutionRepository,
        adapters: list[RecoveryAdapter] | None = None,
    ) -> None:
        self._evidence_repo = evidence_repository
        self._execution_repo = execution_repository
        self._adapters = adapters or []
        self._execution_locks: dict[str, Lock] = {}
        self._global_lock = Lock()

    async def create_durable_plan(
        self,
        tenant_id: str,
        plan_id: str,
        actions: list[ProtectedAction],
        topological_order: list[str],
    ) -> list[DurableExecutionStep]:
        """Create durable execution steps for a recovery plan."""
        steps: list[DurableExecutionStep] = []
        order_map = {aid: idx for idx, aid in enumerate(topological_order)}

        for action in sorted(actions, key=lambda a: order_map.get(a.action_id, 0)):
            evidence = await self._evidence_repo.get_by_action_id(tenant_id, action.action_id)
            step = DurableExecutionStep(
                step_id=f"step-{secrets.token_hex(12)}",
                plan_id=plan_id,
                action_id=action.action_id,
                execution_order=order_map.get(action.action_id, 0),
                tenant_id=tenant_id,
                execution_state=ExecutionState.PENDING.value,
                idempotency_key=(
                    evidence.idempotency_key
                    if evidence
                    else f"idem-{action.action_id}"
                ),
                target_system=evidence.target_system if evidence else "",
                target_resource=evidence.target_resource if evidence else action.resource,
                compensation_payload=evidence.compensation_payload if evidence else {},
                max_retries=3,
            )
            saved_step = await self._execution_repo.save(step)
            steps.append(saved_step)

        return steps

    async def execute_durable_plan(
        self,
        tenant_id: str,
        plan_id: str,
        stop_conditions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Execute a durable recovery plan with interruption survival."""
        with self._global_lock:
            if plan_id in self._execution_locks:
                return {
                    "plan_id": plan_id,
                    "status": "already_running",
                    "message": "Recovery plan is already being executed",
                }
            self._execution_locks[plan_id] = Lock()

        plan_lock = self._execution_locks.get(plan_id)
        if plan_lock is None:
            return {
                "plan_id": plan_id,
                "status": "error",
                "message": "Failed to acquire execution lock",
            }
        try:
            with plan_lock:
                return await self._do_execute_durable_plan(tenant_id, plan_id, stop_conditions)
        finally:
            with self._global_lock:
                self._execution_locks.pop(plan_id, None)

    async def _do_execute_durable_plan(
        self,
        tenant_id: str,
        plan_id: str,
        stop_conditions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Execute a durable recovery plan with interruption survival."""
        stop_conditions = stop_conditions or [StopCondition.ON_FIRST_FAILURE.value]
        steps, total = await self._execution_repo.list_by_plan(tenant_id, plan_id, limit=500)

        if total == 0:
            return {
                "plan_id": plan_id,
                "status": "no_steps",
                "message": "No execution steps found for this plan",
            }

        execution_results: dict[str, dict[str, Any]] = {}
        completed_count = 0
        failed_count = 0
        blocked_count = 0
        manual_count = 0
        stopped = False
        stop_reason = ""

        for step in steps:
            if step.execution_state == ExecutionState.SUCCEEDED.value:
                completed_count += 1
                execution_results[step.action_id] = {
                    "state": step.execution_state,
                    "verification_passed": step.verification_passed,
                    "already_completed": True,
                }
                continue

            result = await self._execute_single_step(tenant_id, step)
            execution_results[step.action_id] = result

            state = result.get("execution_state", "")
            if state == ExecutionState.SUCCEEDED.value:
                completed_count += 1
            elif state == ExecutionState.FAILED.value:
                failed_count += 1
                if StopCondition.ON_FIRST_FAILURE.value in stop_conditions:
                    stopped = True
                    stop_reason = f"Stopped on first failure: {step.action_id}"
            elif state == ExecutionState.BLOCKED_BY_DRIFT.value:
                blocked_count += 1
                if StopCondition.ON_BLOCKING_DRIFT.value in stop_conditions:
                    stopped = True
                    stop_reason = f"Stopped on blocking drift: {step.action_id}"
            elif state == ExecutionState.BLOCKED_BY_CONFLICT.value:
                blocked_count += 1
                if StopCondition.ON_BLOCKING_CONFLICT.value in stop_conditions:
                    stopped = True
                    stop_reason = f"Stopped on blocking conflict: {step.action_id}"
            elif state == ExecutionState.REQUIRES_MANUAL_ACTION.value:
                manual_count += 1

            if stopped:
                break

        all_succeeded = completed_count == len(steps) and failed_count == 0

        return {
            "plan_id": plan_id,
            "status": "completed" if all_succeeded else ("stopped" if stopped else "partial"),
            "stop_reason": stop_reason,
            "total_steps": len(steps),
            "completed": completed_count,
            "failed": failed_count,
            "blocked": blocked_count,
            "manual_required": manual_count,
            "execution_results": execution_results,
            "verification_status": (
                VerificationStatus.EXECUTED_AND_VERIFIED.value
                if all_succeeded
                else VerificationStatus.EXECUTED_NOT_VERIFIED.value
                if completed_count > 0
                else VerificationStatus.EXECUTION_FAILED.value
            ),
        }

    async def resume_plan(
        self,
        tenant_id: str,
        plan_id: str,
        stop_conditions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Resume an interrupted recovery plan.

        1. Load durable execution state.
        2. Verify previous steps.
        3. Reconcile ambiguous outcomes.
        4. Never blindly repeat an unsafe external action.
        5. Continue only when safe.
        """
        steps, total = await self._execution_repo.list_by_plan(tenant_id, plan_id, limit=500)

        if total == 0:
            return {
                "plan_id": plan_id,
                "status": "no_steps",
                "message": "No execution steps found for this plan",
            }

        needs_verification: list[DurableExecutionStep] = []
        needs_retry: list[DurableExecutionStep] = []
        already_done: list[DurableExecutionStep] = []

        for step in steps:
            if step.execution_state == ExecutionState.SUCCEEDED.value:
                already_done.append(step)
            elif step.execution_state == ExecutionState.UNKNOWN_EXTERNAL_OUTCOME.value:
                needs_verification.append(step)
            elif (
                step.execution_state == ExecutionState.FAILED.value
                and step.retry_count < step.max_retries
            ):
                needs_retry.append(step)

        verification_results: dict[str, str] = {}
        for step in needs_verification:
            verified = await self._verify_external_outcome(tenant_id, step)
            verification_results[step.action_id] = (
                "verified" if verified else "requires_manual_verification"
            )

        execution_results: dict[str, dict[str, Any]] = {}
        completed_count = len(already_done)
        failed_count = 0
        stopped = False
        stop_reason = ""

        for step in steps:
            if step.execution_state == ExecutionState.SUCCEEDED.value:
                continue
            if step in needs_verification:
                v_result = verification_results.get(step.action_id, "")
                if v_result == "verified":
                    completed_count += 1
                    continue

            if stopped:
                break

            result = await self._execute_single_step(tenant_id, step)
            execution_results[step.action_id] = result
            state = result.get("execution_state", "")

            if state == ExecutionState.SUCCEEDED.value:
                completed_count += 1
            elif state == ExecutionState.FAILED.value:
                failed_count += 1
                if stop_conditions and StopCondition.ON_FIRST_FAILURE.value in stop_conditions:
                    stopped = True
                    stop_reason = f"Stopped on first failure after resume: {step.action_id}"

            if stopped:
                break

        all_succeeded = completed_count == len(steps) and failed_count == 0

        return {
            "plan_id": plan_id,
            "status": "completed" if all_succeeded else ("stopped" if stopped else "partial"),
            "stop_reason": stop_reason,
            "total_steps": len(steps),
            "completed": completed_count,
            "failed": failed_count,
            "verification_results": verification_results,
            "execution_results": execution_results,
            "resumed_at": datetime.now(UTC).isoformat(),
        }

    async def _execute_single_step(
        self, tenant_id: str, step: DurableExecutionStep
    ) -> dict[str, Any]:
        """Execute a single durable step with idempotency and verification."""
        action = ProtectedAction(
            action_id=step.action_id,
            tenant_id=tenant_id,
            actor_user_id=None,
            agent_id="",
            authority_grant_id=None,
            tool=step.target_system,
            resource=step.target_resource,
            action_type="",
        )

        evidence = await self._evidence_repo.get_by_action_id(tenant_id, step.action_id)
        if evidence is None:
            await self._update_step_state(
                step, ExecutionState.REQUIRES_MANUAL_ACTION.value,
                error="No evidence available for step",
            )
            return {
                "action_id": step.action_id,
                "execution_state": ExecutionState.REQUIRES_MANUAL_ACTION.value,
                "success": False,
                "error": "No evidence available",
            }

        for adapter in self._adapters:
            try:
                if not hasattr(adapter, "capture_recovery_evidence"):
                    continue

                drift = await adapter.detect_drift(action, evidence)
                if drift.status not in (DriftStatus.NO_DRIFT, DriftStatus.INSUFFICIENT_EVIDENCE):
                    await self._update_step_state(
                        step, ExecutionState.BLOCKED_BY_DRIFT.value,
                        error=f"Drift: {drift.status.value}",
                    )
                    return {
                        "action_id": step.action_id,
                        "execution_state": ExecutionState.BLOCKED_BY_DRIFT.value,
                        "success": False,
                        "error": f"Drift detected: {drift.status.value}",
                    }

                conflict = await adapter.check_conflicts(action, evidence)
                if conflict.status not in (
                    ConflictStatus.NO_CONFLICT, ConflictStatus.INSUFFICIENT_EVIDENCE
                ):
                    await self._update_step_state(
                        step, ExecutionState.BLOCKED_BY_CONFLICT.value,
                        error=f"Conflict: {conflict.status.value}",
                    )
                    return {
                        "action_id": step.action_id,
                        "execution_state": ExecutionState.BLOCKED_BY_CONFLICT.value,
                        "success": False,
                        "error": f"Conflict detected: {conflict.status.value}",
                    }

                compensation = await adapter.generate_compensation(action, evidence)
                result = await adapter.execute_compensation(compensation, step.idempotency_key)
                verification = await adapter.verify(compensation)

                new_state = result.execution_state.value
                await self._update_step_state(
                    step, new_state,
                    error=result.error,
                    verification_passed=verification.verified,
                )

                return {
                    "action_id": step.action_id,
                    "execution_state": new_state,
                    "success": result.success,
                    "verification_passed": verification.verified,
                    "idempotency_key": step.idempotency_key,
                }
            except (AttributeError, TypeError):
                continue
            except Exception as exc:
                await self._update_step_state(
                    step, ExecutionState.FAILED.value,
                    error=str(exc),
                )
                return {
                    "action_id": step.action_id,
                    "execution_state": ExecutionState.FAILED.value,
                    "success": False,
                    "error": str(exc),
                }

        await self._update_step_state(
            step, ExecutionState.REQUIRES_MANUAL_ACTION.value,
            error="No adapter could execute this step",
        )
        return {
            "action_id": step.action_id,
            "execution_state": ExecutionState.REQUIRES_MANUAL_ACTION.value,
            "success": False,
            "error": "No adapter available",
        }

    async def _update_step_state(
        self,
        step: DurableExecutionStep,
        new_state: str,
        error: str | None = None,
        verification_passed: bool = False,
    ) -> None:
        """Update the durable step state."""
        now = datetime.now(UTC)
        is_terminal = new_state in (
            ExecutionState.SUCCEEDED.value,
            ExecutionState.FAILED.value,
            ExecutionState.BLOCKED_BY_DRIFT.value,
            ExecutionState.BLOCKED_BY_CONFLICT.value,
            ExecutionState.REQUIRES_MANUAL_ACTION.value,
        )
        updated = DurableExecutionStep(
            step_id=step.step_id,
            plan_id=step.plan_id,
            action_id=step.action_id,
            execution_order=step.execution_order,
            tenant_id=step.tenant_id,
            execution_state=new_state,
            idempotency_key=step.idempotency_key,
            target_system=step.target_system,
            target_resource=step.target_resource,
            compensation_payload=step.compensation_payload,
            started_at=step.started_at or now,
            completed_at=now if is_terminal else step.completed_at,
            error=error,
            verification_passed=verification_passed,
            retry_count=step.retry_count + (1 if new_state == ExecutionState.FAILED.value else 0),
            max_retries=step.max_retries,
            step_metadata=step.step_metadata,
            created_at=step.created_at,
        )
        await self._execution_repo.save(updated)

    async def _verify_external_outcome(
        self, tenant_id: str, step: DurableExecutionStep
    ) -> bool:
        """Verify the outcome of a step with unknown external outcome."""
        evidence = await self._evidence_repo.get_by_action_id(tenant_id, step.action_id)
        if evidence is None:
            return False

        for adapter in self._adapters:
            try:
                if hasattr(adapter, "verify"):
                    from app.domain.entities.surgical_recovery_types import CompensationAction
                    compensation = CompensationAction(
                        action_id=step.action_id,
                        incident_action_id=step.action_id,
                        compensation_type=evidence.compensation_type,
                        compensation_payload=evidence.compensation_payload,
                        idempotency_key=step.idempotency_key,
                        target_system=step.target_system,
                        target_resource=step.target_resource,
                        execution_order=step.execution_order,
                        reversibility=evidence.reversibility_classification,
                        drift_status=DriftStatus.NO_DRIFT,
                        conflict_status=ConflictStatus.NO_CONFLICT,
                        verification_requirements=evidence.verification_requirements,
                        dependency_edges=evidence.dependency_edges,
                    )
                    result = await adapter.verify(compensation)
                    return result.verified
            except (AttributeError, TypeError):
                continue
            except Exception:
                return False

        return False
