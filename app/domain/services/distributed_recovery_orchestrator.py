from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any, Protocol

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
from app.domain.repositories.causal_state_repositories import (
    DurableExecutionRepository,
    StaleFencingTokenError,
)
from app.domain.repositories.recovery_evidence_repository import RecoveryEvidenceRepository
from app.domain.services.recovery_adapter import RecoveryAdapter


@dataclass(frozen=True)
class PlanLease:
    """Exclusive execution lease for one recovery plan."""

    plan_id: str
    owner: str
    fencing_token: int
    acquired_at: datetime
    expires_at: datetime


# Sentinel expiry for released leases (tombstones keep fencing tokens monotonic).
_RELEASED_AT = datetime(1970, 1, 1, tzinfo=UTC)


class PlanLeaseStore(Protocol):
    """Coordination store for single-executor plan execution.

    A multi-instance deployment must back this protocol with a shared
    coordinator (database row with conditional updates, Redis SET NX PX, ...);
    :class:`InMemoryPlanLeaseStore` provides identical semantics for a single
    process and is the default.
    """

    async def try_acquire(
        self, plan_id: str, owner: str, ttl_seconds: float
    ) -> PlanLease | None:
        """Acquire the plan lease, or ``None`` when it is held elsewhere."""

    async def renew(
        self, plan_id: str, owner: str, ttl_seconds: float
    ) -> PlanLease | None:
        """Extend an owned, unexpired lease; ``None`` when lost or taken over."""

    async def release(self, plan_id: str, owner: str) -> None:
        """Release an owned lease (no-op when owned by someone else)."""

    async def get(self, plan_id: str) -> PlanLease | None:
        """Return the current lease for a plan (expired or not)."""


class InMemoryPlanLeaseStore:
    """Process-local lease store with expiry takeover and fencing tokens.

    Semantics (identical to a shared-coordinator implementation):

    - ``try_acquire`` fails while an unexpired lease is held by any owner
      (including this one — no reentrant execution).
    - An expired lease (crashed executor) can be taken over; the fencing
      token increments so a late-arriving old executor can be identified.
    - ``renew`` only succeeds for the current, unexpired owner.
    """

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._leases: dict[str, PlanLease] = {}
        self._lock = Lock()

    def _expired(self, lease: PlanLease) -> bool:
        return self._clock() >= lease.expires_at

    async def try_acquire(
        self, plan_id: str, owner: str, ttl_seconds: float
    ) -> PlanLease | None:
        with self._lock:
            existing = self._leases.get(plan_id)
            if existing is not None and not self._expired(existing):
                return None
            now = self._clock()
            lease = PlanLease(
                plan_id=plan_id,
                owner=owner,
                fencing_token=(existing.fencing_token + 1) if existing else 1,
                acquired_at=now,
                expires_at=now + timedelta(seconds=ttl_seconds),
            )
            self._leases[plan_id] = lease
            return lease

    async def renew(
        self, plan_id: str, owner: str, ttl_seconds: float
    ) -> PlanLease | None:
        with self._lock:
            existing = self._leases.get(plan_id)
            if (
                existing is None
                or existing.owner != owner
                or self._expired(existing)
            ):
                return None
            now = self._clock()
            lease = replace(existing, expires_at=now + timedelta(seconds=ttl_seconds))
            self._leases[plan_id] = lease
            return lease

    async def release(self, plan_id: str, owner: str) -> None:
        with self._lock:
            existing = self._leases.get(plan_id)
            if existing is not None and existing.owner == owner:
                # Keep the lease as an expired tombstone so the fencing token
                # never repeats for a plan.
                self._leases[plan_id] = replace(
                    existing, owner="", expires_at=_RELEASED_AT
                )

    async def get(self, plan_id: str) -> PlanLease | None:
        with self._lock:
            lease = self._leases.get(plan_id)
            if lease is None or lease.owner == "":
                return None
            return lease


_DEFAULT_LEASE_STORE: PlanLeaseStore | None = None
_DEFAULT_LEASE_STORE_LOCK = Lock()


def _default_lease_store() -> PlanLeaseStore:
    """Return the process-wide default plan-lease store.

    API routes construct a fresh orchestrator per request; a per-instance
    default store would give every request its own lease space, making the
    single-executor guarantee vacuous (two concurrent requests could execute
    the same plan through independent stores).  The default is therefore one
    shared in-memory store per process.  It is still process-local: multi-
    instance deployments need a shared lease backend (tracked in
    ``INTERLOCK_V5_PRODUCTION_GAP_MATRIX.md``).  Tests and simulators that
    need isolation pass ``lease_store`` explicitly.
    """
    global _DEFAULT_LEASE_STORE
    if _DEFAULT_LEASE_STORE is None:
        with _DEFAULT_LEASE_STORE_LOCK:
            if _DEFAULT_LEASE_STORE is None:
                _DEFAULT_LEASE_STORE = InMemoryPlanLeaseStore()
    return _DEFAULT_LEASE_STORE


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
        *,
        lease_store: PlanLeaseStore | None = None,
        lease_ttl_seconds: float = 300.0,
    ) -> None:
        self._evidence_repo = evidence_repository
        self._execution_repo = execution_repository
        self._adapters = adapters or []
        self._instance_id = f"orch-{secrets.token_hex(8)}"
        # Default: the process-wide shared store (see _default_lease_store);
        # per-instance stores made lease semantics vacuous for per-request
        # orchestrator construction.
        self._lease_store: PlanLeaseStore = lease_store or _default_lease_store()
        self._lease_ttl_seconds = lease_ttl_seconds

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
                    evidence.idempotency_key if evidence else f"idem-{action.action_id}"
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
        """Execute a durable recovery plan with interruption survival.

        A plan lease (TTL + fencing token) guarantees single-executor
        semantics: concurrent submissions collapse to ``already_running``, and
        a lease abandoned by a crashed orchestrator instance expires and can
        be taken over by another instance.
        """
        lease = await self._lease_store.try_acquire(
            plan_id, self._instance_id, self._lease_ttl_seconds
        )
        if lease is None:
            return {
                "plan_id": plan_id,
                "status": "already_running",
                "message": "Recovery plan is already being executed",
            }
        try:
            result = await self._do_execute_durable_plan(
                tenant_id, plan_id, stop_conditions, lease=lease
            )
            result["fencing_token"] = lease.fencing_token
            return result
        finally:
            await self._lease_store.release(plan_id, self._instance_id)

    async def _do_execute_durable_plan(
        self,
        tenant_id: str,
        plan_id: str,
        stop_conditions: list[str] | None = None,
        lease: PlanLease | None = None,
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
        # Steps counted as completed whose independent verification did NOT
        # pass. A plan may only claim EXECUTED_AND_VERIFIED when zero such
        # steps exist (V6 WP-7: verifier failure must never be reported as
        # a verified success).
        unverified_count = 0
        stopped = False
        stop_reason = ""

        for step in steps:
            if lease is not None:
                # Step boundaries are natural heartbeats: a lease that can no
                # longer be renewed means another instance took over (fencing).
                renewed = await self._lease_store.renew(
                    plan_id, self._instance_id, self._lease_ttl_seconds
                )
                if renewed is None:
                    return {
                        "plan_id": plan_id,
                        "status": "lease_lost",
                        "stop_reason": (
                            "Execution lease expired and could not be renewed; "
                            "another orchestrator instance may have taken over"
                        ),
                        "total_steps": len(steps),
                        "completed": completed_count,
                        "failed": failed_count,
                        "blocked": blocked_count,
                        "manual_required": manual_count,
                        "execution_results": execution_results,
                        "verification_status": (
                            VerificationStatus.EXECUTED_NOT_VERIFIED.value
                            if completed_count > 0
                            else VerificationStatus.EXECUTION_FAILED.value
                        ),
                    }
                # The renewed lease is authoritative for this step boundary.
                lease = renewed

            if step.execution_state == ExecutionState.SUCCEEDED.value:
                completed_count += 1
                if not step.verification_passed:
                    unverified_count += 1
                execution_results[step.action_id] = {
                    "state": step.execution_state,
                    "verification_passed": step.verification_passed,
                    "already_completed": True,
                }
                continue

            result = await self._execute_single_step(
                tenant_id,
                step,
                fencing_token=lease.fencing_token if lease is not None else None,
            )
            if result.get("lease_lost"):
                # Rejected stale write: this instance no longer holds write
                # authority. Distinct concurrency outcome — never counted as
                # completed or persisted.
                execution_results[step.action_id] = result
                return {
                    "plan_id": plan_id,
                    "status": "lease_lost",
                    "stop_reason": (
                        "Durable step write rejected by a newer fencing token: "
                        "another orchestrator instance advanced the write fence; "
                        "this instance stopped without claiming the step as persisted"
                    ),
                    "total_steps": len(steps),
                    "completed": completed_count,
                    "failed": failed_count,
                    "blocked": blocked_count,
                    "manual_required": manual_count,
                    "execution_results": execution_results,
                    "verification_status": (
                        VerificationStatus.EXECUTED_NOT_VERIFIED.value
                        if completed_count > 0
                        else VerificationStatus.EXECUTION_FAILED.value
                    ),
                }
            execution_results[step.action_id] = result

            state = result.get("execution_state", "")
            if state == ExecutionState.SUCCEEDED.value:
                completed_count += 1
                if not result.get("verification_passed"):
                    unverified_count += 1
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
        # Verified claim requires BOTH full execution and independent
        # verification of every completed step (fail closed on any gap).
        verified_every_step = all_succeeded and unverified_count == 0

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
                if verified_every_step
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
        """Resume an interrupted recovery plan under the plan lease.

        1. Load durable execution state.
        2. Verify previous steps.
        3. Reconcile ambiguous outcomes.
        4. Never blindly repeat an unsafe external action.
        5. Continue only when safe.

        Resume honours the same single-executor lease contract as execute:
        a resume while another instance (or an in-flight execute of the same
        plan) holds the lease collapses to ``already_running`` instead of
        running compensations concurrently with the lease holder.
        """
        lease = await self._lease_store.try_acquire(
            plan_id, self._instance_id, self._lease_ttl_seconds
        )
        if lease is None:
            return {
                "plan_id": plan_id,
                "status": "already_running",
                "message": "Recovery plan is already being executed or resumed",
            }
        try:
            result = await self._do_resume_plan(
                tenant_id, plan_id, stop_conditions
            )
            result["fencing_token"] = lease.fencing_token
            return result
        finally:
            await self._lease_store.release(plan_id, self._instance_id)

    async def _do_resume_plan(
        self,
        tenant_id: str,
        plan_id: str,
        stop_conditions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Resume an interrupted recovery plan (caller must hold the lease)."""
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

            # Step boundaries are heartbeats, exactly like execute: a lease
            # that can no longer be renewed means another instance took over.
            renewed = await self._lease_store.renew(
                plan_id, self._instance_id, self._lease_ttl_seconds
            )
            if renewed is None:
                return {
                    "plan_id": plan_id,
                    "status": "lease_lost",
                    "stop_reason": (
                        "Execution lease expired and could not be renewed; "
                        "another orchestrator instance may have taken over"
                    ),
                    "total_steps": len(steps),
                    "completed": completed_count,
                    "failed": failed_count,
                    "verification_results": verification_results,
                    "execution_results": execution_results,
                    "resumed_at": datetime.now(UTC).isoformat(),
                }

            result = await self._execute_single_step(
                tenant_id, step, fencing_token=renewed.fencing_token
            )
            if result.get("lease_lost"):
                # Rejected stale write during resume: same distinct outcome
                # as execute — stop without claiming persistence.
                execution_results[step.action_id] = result
                return {
                    "plan_id": plan_id,
                    "status": "lease_lost",
                    "stop_reason": (
                        "Durable step write rejected by a newer fencing token: "
                        "another orchestrator instance advanced the write fence; "
                        "this instance stopped without claiming the step as persisted"
                    ),
                    "total_steps": len(steps),
                    "completed": completed_count,
                    "failed": failed_count,
                    "verification_results": verification_results,
                    "execution_results": execution_results,
                    "resumed_at": datetime.now(UTC).isoformat(),
                }
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
        self,
        tenant_id: str,
        step: DurableExecutionStep,
        fencing_token: int | None = None,
    ) -> dict[str, Any]:
        """Execute one durable step, fenced at the durable write boundary.

        A :class:`StaleFencingTokenError` escaping the step body means a
        newer fencing token already advanced the stored write fence: this
        instance lost write authority. The result is reported as
        ``lease_lost`` with ``persistence="rejected_stale_write"`` — never
        as successful persistence.
        """
        try:
            return await self._run_single_step(tenant_id, step, fencing_token)
        except StaleFencingTokenError as exc:
            return {
                "action_id": step.action_id,
                "execution_state": step.execution_state,
                "success": False,
                "lease_lost": True,
                "persistence": "rejected_stale_write",
                "error": f"Durable step write rejected by fencing token: {exc}",
            }

    async def _run_single_step(
        self,
        tenant_id: str,
        step: DurableExecutionStep,
        fencing_token: int | None = None,
    ) -> dict[str, Any]:
        """Execute a single durable step with idempotency and verification."""
        evidence = await self._evidence_repo.get_by_action_id(tenant_id, step.action_id)
        if evidence is None:
            await self._update_step_state(
                step,
                ExecutionState.REQUIRES_MANUAL_ACTION.value,
                error="No evidence available for step",
                fencing_token=fencing_token,
            )
            return {
                "action_id": step.action_id,
                "execution_state": ExecutionState.REQUIRES_MANUAL_ACTION.value,
                "success": False,
                "error": "No evidence available",
            }

        # Reconstruct the action with the captured evidence references so
        # adapter capability checks (``can_recover``/``supports``) see the same
        # reversibility context the evidence was captured under.
        action = ProtectedAction(
            action_id=step.action_id,
            tenant_id=tenant_id,
            actor_user_id=None,
            agent_id="",
            authority_grant_id=None,
            tool=step.target_system,
            resource=step.target_resource,
            action_type=evidence.action_type or "",
            before_state_ref=evidence.before_state_reference,
        )

        for adapter in self._adapters:
            try:
                if not hasattr(adapter, "capture_recovery_evidence"):
                    continue

                # Capability gating: adapters that explicitly refuse this
                # action (unsupported / irreversible / requires approval) may
                # not claim the step.  "unknown" stays eligible — the adapter's
                # own fail-closed guards decide during execution.
                can_recover = getattr(adapter, "can_recover", None)
                if can_recover is not None:
                    try:
                        verdict = await can_recover(action)
                    except (AttributeError, TypeError):
                        verdict = None
                    if verdict in ("unsupported", "irreversible", "requires_approval"):
                        continue

                drift = await adapter.detect_drift(action, evidence)
                if drift.status not in (DriftStatus.NO_DRIFT, DriftStatus.INSUFFICIENT_EVIDENCE):
                    await self._update_step_state(
                        step,
                        ExecutionState.BLOCKED_BY_DRIFT.value,
                        error=f"Drift: {drift.status.value}",
                        fencing_token=fencing_token,
                    )
                    return {
                        "action_id": step.action_id,
                        "execution_state": ExecutionState.BLOCKED_BY_DRIFT.value,
                        "success": False,
                        "error": f"Drift detected: {drift.status.value}",
                    }

                conflict = await adapter.check_conflicts(action, evidence)
                if conflict.status not in (
                    ConflictStatus.NO_CONFLICT,
                    ConflictStatus.INSUFFICIENT_EVIDENCE,
                ):
                    await self._update_step_state(
                        step,
                        ExecutionState.BLOCKED_BY_CONFLICT.value,
                        error=f"Conflict: {conflict.status.value}",
                        fencing_token=fencing_token,
                    )
                    return {
                        "action_id": step.action_id,
                        "execution_state": ExecutionState.BLOCKED_BY_CONFLICT.value,
                        "success": False,
                        "error": f"Conflict detected: {conflict.status.value}",
                    }

                compensation = await adapter.generate_compensation(action, evidence)

                # Execution phase: once this adapter claims the step, failures
                # must NOT fall through to the next adapter — a fall-through
                # would let a second adapter re-apply a compensation the first
                # one may already have executed (double compensation).
                try:
                    result = await adapter.execute_compensation(
                        compensation, step.idempotency_key
                    )
                    verify_fn = getattr(adapter, "verify", None)
                    verification = (
                        await verify_fn(compensation) if verify_fn is not None else None
                    )
                    new_state = result.execution_state.value
                    verification_passed = (
                        bool(verification.verified) if verification is not None else False
                    )
                    result_error = result.error
                    result_success = result.success
                except Exception as exc:
                    await self._update_step_state(
                        step,
                        ExecutionState.FAILED.value,
                        error=str(exc),
                        fencing_token=fencing_token,
                    )
                    return {
                        "action_id": step.action_id,
                        "execution_state": ExecutionState.FAILED.value,
                        "success": False,
                        "error": (
                            f"Adapter execution/verification failed in "
                            f"{type(adapter).__name__}: {exc}"
                        ),
                    }

                await self._update_step_state(
                    step,
                    new_state,
                    error=result_error,
                    verification_passed=verification_passed,
                    fencing_token=fencing_token,
                )

                return {
                    "action_id": step.action_id,
                    "execution_state": new_state,
                    "success": result_success,
                    "verification_passed": verification_passed,
                    "idempotency_key": step.idempotency_key,
                }
            except StaleFencingTokenError:
                # Fencing rejection must surface to _execute_single_step as
                # a distinct outcome, not be misreported as a step failure.
                raise
            except (AttributeError, TypeError):
                continue
            except Exception as exc:
                await self._update_step_state(
                    step,
                    ExecutionState.FAILED.value,
                    error=str(exc),
                    fencing_token=fencing_token,
                )
                return {
                    "action_id": step.action_id,
                    "execution_state": ExecutionState.FAILED.value,
                    "success": False,
                    "error": str(exc),
                }

        await self._update_step_state(
            step,
            ExecutionState.REQUIRES_MANUAL_ACTION.value,
            error="No adapter could execute this step",
            fencing_token=fencing_token,
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
        fencing_token: int | None = None,
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
        await self._execution_repo.save(
            updated, expected_fencing_token=fencing_token
        )

    async def _verify_external_outcome(self, tenant_id: str, step: DurableExecutionStep) -> bool:
        """Verify the outcome of a step with unknown external outcome.

        Every registered adapter is consulted and any positive verdict counts:
        the adapter that can actually verify this step's payload may not be
        first in registration order.  Adapters that raise are treated as
        "no verdict" (they are skipped, not trusted).
        """
        evidence = await self._evidence_repo.get_by_action_id(tenant_id, step.action_id)
        if evidence is None:
            return False

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

        for adapter in self._adapters:
            verify_fn = getattr(adapter, "verify", None)
            if verify_fn is None:
                continue
            try:
                result = await verify_fn(compensation)
            except (AttributeError, TypeError):
                continue
            except Exception:  # noqa: S112 - a raising verifier yields no
                # verdict and must never be trusted; continue to the remaining
                # registered adapters instead of aborting verification.
                continue
            if getattr(result, "verified", False):
                return True

        return False
