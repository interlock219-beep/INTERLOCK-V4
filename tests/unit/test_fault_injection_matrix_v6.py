"""INTERLOCK V6 — WP-7: deterministic fault-injection matrix (PILLAR 7).

Mission text quoted verbatim (PILLAR 7 — FAILURE INJECTION AND RECOVERY
PROVABILITY):

    Create a systematic fault-injection framework for disposable test
    environments.

    Inject:
    - Process crashes at every orchestration transition.
    - Network timeouts and connection resets.
    - Duplicate, delayed, and reordered requests.
    - Lease expiration and stale-worker races.
    - Storage corruption and unavailable evidence.
    - Partial writes and rollback failures.
    - Disk exhaustion and permission changes.
    - Concurrent user modifications.
    - Dependency and service outages.
    - Malicious adapter responses.
    - Verifier failures.
    - Key rotation and expired credentials.

    For every scenario, assert:
    1. The resulting resource state.
    2. Whether recovery is complete, partial, failed, or uncertain.
    3. Whether unrelated user data remains intact.
    4. Whether retry is safe.
    5. Whether evidence accurately reflects what occurred.
    6. Whether the system refuses unsupported guarantees.

    Use deterministic fault injection wherever possible. Minimize flaky
    timing-based tests.

Scope of this matrix: process-crash injection at every in-process
orchestration transition (plan load, lease heartbeat, evidence lookup,
drift check, execution phase, verification phase, durable write, mid-plan
heartbeat), duplicate/delayed/reordered plan requests, and verifier
failures — including the plan-level verdict claims that must never
overstate what independent verification actually proved.

Explicitly BLOCKED (not simulated, never faked): network resets, disk
exhaustion, permission changes, key rotation, and host/dependency outages
require live infrastructure (Postgres/Redis/KMS/SIEM) that this run is not
authorized to install. They are recorded as BLOCKED in the release gap
assessment.

Determinism contract: every fault is a one-shot ``InjectedCrash`` raised at
an exact call counter — no sleeps, no timers, no wall-clock dependence
(only ``asyncio.Event`` gates for concurrency ordering). The full matrix is
replayed three times into canonical snapshots (ids, timestamps, fencing
tokens excluded) and asserted byte-identical as JSON.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import replace
from typing import Any

import pytest

from app.application.dto.auth import UserResponse
from app.domain.entities.causal_state_types import (
    DurableExecutionStep,
    VerificationStatus,
)
from app.domain.entities.protected_action import ProtectedAction
from app.domain.entities.recovery_plan import (
    RecoveryOutcome,
    RecoveryPlan,
    RecoveryStatus,
)
from app.domain.entities.surgical_recovery_types import (
    AdapterCapability,
    CompensationType,
    ExecutionState,
    RecoveryAdapterType,
    RecoveryEvidence,
    Reversibility,
    VerificationResult,
)
from app.domain.repositories.causal_state_repositories import enforce_write_fence
from app.domain.services.distributed_recovery_orchestrator import (
    DistributedRecoveryOrchestrator,
    InMemoryPlanLeaseStore,
)
from app.infrastructure.recovery.mock_adapter import MockRecoveryAdapter
from app.presentation.api.v1.routes.surgical_recovery import execute_recovery_plan

TENANT = "tenant-wp7"
PLAN = "plan-wp7"
PLAN_B = "plan-bystander-wp7"


# ---------------------------------------------------------------------------
# Deterministic fault primitives
# ---------------------------------------------------------------------------


class InjectedCrash(RuntimeError):
    """One-shot deterministic fault raised at an exact call site."""


class _Fault:
    """Wrap an async callable so call number ``fail_on`` raises exactly once.

    Deterministic: counts calls, no timers, no randomness. After the fault
    fires (or if the call index differs) the original callable runs
    unchanged, modelling a process that died once and was restarted.
    """

    def __init__(self, fn: Any, message: str, fail_on: int = 1) -> None:
        self._fn = fn
        self._message = message
        self._fail_on = fail_on
        self.calls = 0

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        if self.calls == self._fail_on:
            raise InjectedCrash(self._message)
        return await self._fn(*args, **kwargs)


# ---------------------------------------------------------------------------
# Test doubles (in-memory, fencing-aware — same contracts as production)
# ---------------------------------------------------------------------------


def _make_action(
    action_id: str,
    tenant_id: str = TENANT,
    parent_action_id: str | None = None,
) -> ProtectedAction:
    return ProtectedAction(
        action_id=action_id,
        tenant_id=tenant_id,
        actor_user_id=None,
        agent_id="agent-wp7",
        authority_grant_id=None,
        tool="database",
        resource=f"record:{action_id}",
        action_type="insert",
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
        before_state_ref=f"state:before:{action_id}",
        parent_action_id=parent_action_id,
    )


def _make_evidence(action_id: str, tenant_id: str = TENANT) -> RecoveryEvidence:
    return RecoveryEvidence(
        evidence_id=f"ev-{action_id}",
        action_id=action_id,
        tenant_id=tenant_id,
        agent_id="agent-wp7",
        authority_grant_id=None,
        parent_action_id=None,
        root_action_id=action_id,
        correlation_id="corr-wp7",
        incident_id="inc-wp7",
        target_system="mock",
        target_resource=f"record:{action_id}",
        action_type="insert",
        before_state_reference=f"state:before:{action_id}",
        after_state_reference=f"state:after:{action_id}",
        compensation_payload={"op": "restore", "target": action_id},
        compensation_type=CompensationType.REVERSE_OPERATION,
        recovery_adapter_type=RecoveryAdapterType.MOCK,
        idempotency_key=f"idem-{action_id}",
        dependency_edges=[],
        reversibility_classification=Reversibility.AUTOMATICALLY_REVERSIBLE,
        evidence_hash=f"hash-{action_id}",
        adapter_capability=AdapterCapability.MOCK,
    )


class _EvidenceRepo:
    def __init__(self, evidence_list: list[RecoveryEvidence]) -> None:
        self._by_action = {(e.tenant_id, e.action_id): e for e in evidence_list}

    async def get_by_action_id(
        self, tenant_id: str, action_id: str
    ) -> RecoveryEvidence | None:
        return self._by_action.get((tenant_id, action_id))

    def seal(self) -> list[tuple[str, str, str]]:
        """Canonical, time-free fingerprint of every stored evidence row."""
        return sorted(
            (e.evidence_id, e.action_id, e.evidence_hash)
            for e in self._by_action.values()
        )


class _ExecutionRepo:
    """In-memory durable execution store with the production write fence."""

    def __init__(self) -> None:
        self._steps: dict[str, DurableExecutionStep] = {}
        self._fences: dict[str, int] = {}

    async def save(
        self, step: DurableExecutionStep, expected_fencing_token: int | None = None
    ) -> DurableExecutionStep:
        enforce_write_fence(
            self._fences.get(step.step_id, 0), expected_fencing_token, step.step_id
        )
        if expected_fencing_token is not None:
            self._fences[step.step_id] = expected_fencing_token
        self._steps[step.step_id] = step
        return step

    async def list_by_plan(
        self, tenant_id: str, plan_id: str, limit: int = 500, offset: int = 0
    ) -> tuple[list[DurableExecutionStep], int]:
        # Real suspension point so concurrent submissions interleave.
        await asyncio.sleep(0)
        items = sorted(
            [
                s
                for s in self._steps.values()
                if s.tenant_id == tenant_id and s.plan_id == plan_id
            ],
            key=lambda s: s.execution_order,
        )
        return items[offset : offset + limit], len(items)

    def steps_for(self, plan_id: str) -> dict[str, DurableExecutionStep]:
        return {s.action_id: s for s in self._steps.values() if s.plan_id == plan_id}


class _RecordingAdapter(MockRecoveryAdapter):
    """Scenario-success mock with an execution ledger and fault hooks.

    - ``exec_attempts`` records EVERY ``execute_compensation`` invocation
      (including the one a fault aborts) so "no duplicate destructive
      actions" is counted from real invocations, not inferred.
    - Fault hooks raise ``InjectedCrash`` on an exact call index of a named
      adapter transition (drift / conflict / execute / verify).
    - Optional ``gate``/``entered`` events order concurrent requests without
      sleeps.
    """

    def __init__(
        self,
        scenario: str = "success",
        gate: asyncio.Event | None = None,
        entered: asyncio.Event | None = None,
    ) -> None:
        super().__init__(scenario=scenario)
        self.exec_attempts: list[tuple[str, str]] = []
        self._fault_specs: dict[str, tuple[str, int]] = {}
        self._fault_calls: dict[str, int] = {}
        self._gate = gate
        self._entered = entered

    def arm_fault(self, method: str, message: str, fail_on: int = 1) -> None:
        self._fault_specs[method] = (message, fail_on)

    async def _maybe_fault(self, method: str) -> None:
        self._fault_calls[method] = self._fault_calls.get(method, 0) + 1
        spec = self._fault_specs.get(method)
        if spec is not None and self._fault_calls[method] == spec[1]:
            raise InjectedCrash(spec[0])

    async def execute_compensation(self, compensation: Any, idempotency_key: str) -> Any:
        self.exec_attempts.append((compensation.action_id, idempotency_key))
        if self._entered is not None:
            self._entered.set()
        if self._gate is not None:
            await self._gate.wait()
        await self._maybe_fault("execute_compensation")
        return await super().execute_compensation(compensation, idempotency_key)

    async def detect_drift(self, action: Any, evidence: Any, current_state: Any = None):
        await self._maybe_fault("detect_drift")
        return await super().detect_drift(action, evidence, current_state)

    async def check_conflicts(self, action: Any, evidence: Any, current_state: Any = None):
        await self._maybe_fault("check_conflicts")
        return await super().check_conflicts(action, evidence, current_state)

    async def verify(self, compensation: Any) -> VerificationResult:
        await self._maybe_fault("verify")
        return await super().verify(compensation)


class _VerifyingAdapter(_RecordingAdapter):
    """Adapter whose independent verification genuinely passes."""

    async def verify(self, compensation: Any) -> VerificationResult:
        await self._maybe_fault("verify")
        return VerificationResult(
            action_id=compensation.action_id,
            verified=True,
            details={"reason": "independent re-check passed"},
        )


# ---------------------------------------------------------------------------
# Disposable environment
# ---------------------------------------------------------------------------


class _Env:
    """Two-step plan + a never-touched bystander plan in memory."""

    plan_actions = {PLAN: ["a0", "a1"], PLAN_B: ["bz"]}

    def __init__(self, adapter: _RecordingAdapter | None = None) -> None:
        self.adapter = adapter or _RecordingAdapter()
        self.actions = [_make_action("a0"), _make_action("a1"), _make_action("bz")]
        self.ev_repo = _EvidenceRepo(
            [_make_evidence(aid) for aid in ("a0", "a1", "bz")]
        )
        self.exec_repo = _ExecutionRepo()
        self.lease = InMemoryPlanLeaseStore()
        self.orch = DistributedRecoveryOrchestrator(
            self.ev_repo,
            self.exec_repo,
            [self.adapter],
            lease_store=self.lease,
        )


async def _make_env(adapter: _RecordingAdapter | None = None) -> _Env:
    env = _Env(adapter)
    a_by_id = {a.action_id: a for a in env.actions}
    await env.orch.create_durable_plan(
        TENANT, PLAN, [a_by_id["a0"], a_by_id["a1"]], ["a0", "a1"]
    )
    await env.orch.create_durable_plan(TENANT, PLAN_B, [a_by_id["bz"]], ["bz"])
    return env


def _attempt_counts(env: _Env, plan_id: str = PLAN) -> dict[str, int]:
    counts = dict.fromkeys(_Env.plan_actions[plan_id], 0)
    for action_id, _key in env.adapter.exec_attempts:
        if action_id in counts:
            counts[action_id] += 1
    return counts


def _snap(
    env: _Env, *, result: dict[str, Any] | None = None, raised: BaseException | None = None
) -> dict[str, Any]:
    """Canonical, time-free snapshot of an outcome (for determinism checks)."""
    steps = env.exec_repo.steps_for(PLAN)
    bsteps = env.exec_repo.steps_for(PLAN_B)
    return {
        "raised": type(raised).__name__ if raised is not None else None,
        "status": result.get("status") if result else None,
        "verification_status": result.get("verification_status") if result else None,
        "completed": result.get("completed") if result else None,
        "failed": result.get("failed") if result else None,
        "states": {aid: steps[aid].execution_state for aid in sorted(steps)},
        "step_errors": {aid: steps[aid].error for aid in sorted(steps)},
        "step_retry_counts": {aid: steps[aid].retry_count for aid in sorted(steps)},
        "step_verification_passed": {
            aid: steps[aid].verification_passed for aid in sorted(steps)
        },
        "bystander_states": {
            aid: bsteps[aid].execution_state for aid in sorted(bsteps)
        },
        "exec_attempts": _attempt_counts(env),
        "idempotency_keys": {
            aid: sorted({k for a, k in env.adapter.exec_attempts if a == aid})
            for aid in sorted(_Env.plan_actions[PLAN])
        },
        "evidence_seal": env.ev_repo.seal(),
    }


# ---------------------------------------------------------------------------
# Crash matrix: one row per orchestration transition
# ---------------------------------------------------------------------------
#
# Each row prescribes, for a one-shot crash at that transition:
#   raises         — the fault escapes execute_durable_plan (process died)
#                    vs. is recorded as a step failure (fault contained)
#   status         — honest plan verdict when a dict is returned
#   verification   — honest plan-level verification claim (never overstated)
#   states         — durable step states right after the crash (P1)
#   attempts       — execute_compensation invocations after the crash
#   resume_attempts— invocations after resume completes (P4: exactly-once)
#
_PENDING = ExecutionState.PENDING.value
_SUCCEEDED = ExecutionState.SUCCEEDED.value
_FAILED = ExecutionState.FAILED.value

_CRASH_POINTS: list[dict[str, Any]] = [
    {
        "name": "list_load",
        "raises": True,
        "status": None,
        "verification": None,
        "states": {"a0": _PENDING, "a1": _PENDING},
        "attempts": {"a0": 0, "a1": 0},
        "resume_attempts": {"a0": 1, "a1": 1},
    },
    {
        "name": "lease_heartbeat_first",
        "raises": True,
        "status": None,
        "verification": None,
        "states": {"a0": _PENDING, "a1": _PENDING},
        "attempts": {"a0": 0, "a1": 0},
        "resume_attempts": {"a0": 1, "a1": 1},
    },
    {
        "name": "evidence_load",
        "raises": True,
        "status": None,
        "verification": None,
        "states": {"a0": _PENDING, "a1": _PENDING},
        "attempts": {"a0": 0, "a1": 0},
        "resume_attempts": {"a0": 1, "a1": 1},
    },
    {
        # Crash AFTER step a0 committed, at the next step boundary: the
        # durable record must keep a0=SUCCEEDED and resume must not
        # re-execute a0 (no duplicate destructive action).
        "name": "lease_heartbeat_between_steps",
        "raises": True,
        "status": None,
        "verification": None,
        "states": {"a0": _SUCCEEDED, "a1": _PENDING},
        "attempts": {"a0": 1, "a1": 0},
        "resume_attempts": {"a0": 1, "a1": 1},
    },
    {
        "name": "drift_check",
        "raises": False,
        "status": "stopped",
        "verification": VerificationStatus.EXECUTION_FAILED.value,
        "states": {"a0": _FAILED, "a1": _PENDING},
        "attempts": {"a0": 0, "a1": 0},
        "resume_attempts": {"a0": 1, "a1": 1},
    },
    {
        "name": "execute_phase",
        "raises": False,
        "status": "stopped",
        "verification": VerificationStatus.EXECUTION_FAILED.value,
        "states": {"a0": _FAILED, "a1": _PENDING},
        "attempts": {"a0": 1, "a1": 0},
        "resume_attempts": {"a0": 2, "a1": 1},
    },
    {
        "name": "verify_phase",
        "raises": False,
        "status": "stopped",
        "verification": VerificationStatus.EXECUTION_FAILED.value,
        "states": {"a0": _FAILED, "a1": _PENDING},
        "attempts": {"a0": 1, "a1": 0},
        "resume_attempts": {"a0": 2, "a1": 1},
    },
    {
        # The durable write itself fails once: execution must fail closed
        # (FAILED recorded by the fallback write), never "succeeded".
        "name": "durable_write",
        "raises": False,
        "status": "stopped",
        "verification": VerificationStatus.EXECUTION_FAILED.value,
        "states": {"a0": _FAILED, "a1": _PENDING},
        "attempts": {"a0": 1, "a1": 0},
        "resume_attempts": {"a0": 2, "a1": 1},
    },
]


def _arm(env: _Env, name: str) -> str:
    """Install the one-shot fault for a matrix point; returns its message."""
    msg = f"{name}: injected one-shot crash"
    if name == "list_load":
        env.exec_repo.list_by_plan = _Fault(env.exec_repo.list_by_plan, msg, fail_on=1)
    elif name == "lease_heartbeat_first":
        env.lease.renew = _Fault(env.lease.renew, msg, fail_on=1)
    elif name == "lease_heartbeat_between_steps":
        env.lease.renew = _Fault(env.lease.renew, msg, fail_on=2)
    elif name == "evidence_load":
        env.ev_repo.get_by_action_id = _Fault(env.ev_repo.get_by_action_id, msg, fail_on=1)
    elif name == "drift_check":
        env.adapter.arm_fault("detect_drift", msg, fail_on=1)
    elif name == "execute_phase":
        env.adapter.arm_fault("execute_compensation", msg, fail_on=1)
    elif name == "verify_phase":
        env.adapter.arm_fault("verify", msg, fail_on=1)
    elif name == "durable_write":
        env.exec_repo.save = _Fault(env.exec_repo.save, msg, fail_on=1)
    else:  # pragma: no cover - guard against table/selector drift
        raise AssertionError(f"unknown crash point: {name}")
    return msg


async def _execute_catching(env: _Env) -> tuple[dict[str, Any] | None, InjectedCrash | None]:
    try:
        return await env.orch.execute_durable_plan(TENANT, PLAN), None
    except InjectedCrash as exc:  # noqa: PERF203 - the matrix under test
        return None, exc


# ---------------------------------------------------------------------------
# The matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "point", _CRASH_POINTS, ids=[p["name"] for p in _CRASH_POINTS]
)
async def test_crash_at_orchestration_transition_recovers_honestly(point: dict[str, Any]):
    """One-shot crash at every transition → honest durable state, safe retry."""
    env = await _make_env()
    msg = _arm(env, point["name"])
    evidence_before = env.ev_repo.seal()

    result, raised = await _execute_catching(env)

    # P2: honest verdict at the crash boundary — an escaping crash yields no
    # result dict at all (no invented success), a contained fault yields a
    # verdict that never claims more than happened.
    if point["raises"]:
        assert raised is not None
        assert msg in str(raised)
        assert result is None
    else:
        assert raised is None
        assert result is not None
        assert result["status"] == point["status"]
        assert result["verification_status"] == point["verification"]

    # P1: resulting resource (durable step) state matches the matrix.
    steps = env.exec_repo.steps_for(PLAN)
    assert {aid: steps[aid].execution_state for aid in sorted(steps)} == point["states"]
    assert _attempt_counts(env) == point["attempts"]

    # P5: evidence accurately reflects what occurred — the failed step
    # carries the injected fault, and no evidence row was mutated.
    if not point["raises"]:
        assert steps["a0"].error is not None
        assert point["name"] in steps["a0"].error
    assert env.ev_repo.seal() == evidence_before

    # P3: unrelated user data (bystander plan) remains untouched.
    bystander = env.exec_repo.steps_for(PLAN_B)
    assert {aid: s.execution_state for aid, s in bystander.items()} == {"bz": _PENDING}
    assert _attempt_counts(env, PLAN_B) == {"bz": 0}

    # Retry precondition: a crash or stop must never leak the plan lease.
    assert await env.lease.get(PLAN) is None

    # P4: retry (resume) is safe and completes the plan exactly once per
    # step — same idempotency keys, no duplicated destructive actions.
    resumed = await env.orch.resume_plan(TENANT, PLAN)
    assert resumed["status"] == "completed"
    final = env.exec_repo.steps_for(PLAN)
    assert {aid: s.execution_state for aid, s in final.items()} == {
        "a0": _SUCCEEDED,
        "a1": _SUCCEEDED,
    }
    assert _attempt_counts(env) == point["resume_attempts"]
    for aid in ("a0", "a1"):
        keys = {k for a, k in env.adapter.exec_attempts if a == aid}
        assert keys == {f"idem-{aid}"}

    # P6: the system refuses unsupported guarantees — resume must never
    # report "executed_and_verified" while the mock verifier fails every
    # independent verification (steps stay verification_passed=False).
    assert resumed.get("verification_status") != (
        VerificationStatus.EXECUTED_AND_VERIFIED.value
    )
    assert final["a0"].verification_passed is False

    # P3 (after resume) + P5 (after resume): bystander and evidence intact.
    assert _attempt_counts(env, PLAN_B) == {"bz": 0}
    assert env.ev_repo.seal() == evidence_before


async def test_crash_matrix_is_deterministic_across_three_runs():
    """WP-7 acceptance: the full matrix is byte-identical across 3 runs."""
    runs: list[str] = []
    for _ in range(3):
        run: list[dict[str, Any]] = []
        for point in _CRASH_POINTS:
            env = await _make_env()
            _arm(env, point["name"])
            result, raised = await _execute_catching(env)
            after_crash = _snap(env, result=result, raised=raised)
            resumed = await env.orch.resume_plan(TENANT, PLAN)
            after_resume = _snap(env, result=resumed)
            run.append(
                {
                    "point": point["name"],
                    "after_crash": after_crash,
                    "after_resume": after_resume,
                }
            )
        runs.append(json.dumps(run, sort_keys=True))
    assert runs[0] == runs[1] == runs[2]


# ---------------------------------------------------------------------------
# Duplicate, delayed, and reordered requests
# ---------------------------------------------------------------------------


async def test_duplicate_execute_requests_collapse_to_single_execution():
    gate = asyncio.Event()
    entered = asyncio.Event()
    env = await _make_env(adapter=_RecordingAdapter(gate=gate, entered=entered))

    first_task = asyncio.create_task(env.orch.execute_durable_plan(TENANT, PLAN))
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        # Deterministic interleaving: the lease is held, so the duplicate
        # request must collapse without touching any step.
        duplicate = await env.orch.execute_durable_plan(TENANT, PLAN)
        assert duplicate["status"] == "already_running"
        assert _attempt_counts(env) == {"a0": 1, "a1": 0}
    finally:
        gate.set()
        first = await asyncio.wait_for(first_task, timeout=5)

    assert first["status"] == "completed"
    # Exactly one execution per step despite the duplicate request.
    assert _attempt_counts(env) == {"a0": 1, "a1": 1}
    assert first["verification_status"] != (
        VerificationStatus.EXECUTED_AND_VERIFIED.value
    )
    assert _attempt_counts(env, PLAN_B) == {"bz": 0}


async def test_delayed_duplicate_execute_after_crash_does_not_double_execute():
    env = await _make_env()
    _arm(env, "list_load")

    _result, raised = await _execute_catching(env)
    assert raised is not None  # the original request "died"

    # The client's delayed duplicate retry arrives after the crash.
    retry = await env.orch.execute_durable_plan(TENANT, PLAN)
    assert retry["status"] == "completed"
    assert retry["verification_status"] != (
        VerificationStatus.EXECUTED_AND_VERIFIED.value
    )

    # A laggy resume arrives afterwards too: already-completed steps are
    # skipped, still with no re-execution.
    laggy = await env.orch.resume_plan(TENANT, PLAN)
    assert laggy["status"] == "completed"

    assert _attempt_counts(env) == {"a0": 1, "a1": 1}
    steps = env.exec_repo.steps_for(PLAN)
    assert {aid: s.execution_state for aid, s in steps.items()} == {
        "a0": _SUCCEEDED,
        "a1": _SUCCEEDED,
    }
    assert _attempt_counts(env, PLAN_B) == {"bz": 0}


async def test_reordered_resume_arriving_before_execute_runs_plan_exactly_once():
    env = await _make_env()

    # Resume (the "reordered" request) arrives before the original execute.
    resumed = await env.orch.resume_plan(TENANT, PLAN)
    assert resumed["status"] == "completed"
    assert _attempt_counts(env) == {"a0": 1, "a1": 1}

    # The original execute arrives late: it must observe completed steps and
    # execute nothing.
    late = await env.orch.execute_durable_plan(TENANT, PLAN)
    assert late["status"] == "completed"
    assert late["execution_results"]["a0"]["already_completed"] is True
    assert late["verification_status"] != (
        VerificationStatus.EXECUTED_AND_VERIFIED.value
    )
    assert _attempt_counts(env) == {"a0": 1, "a1": 1}


async def test_crash_then_concurrent_duplicate_and_resume_execute_once():
    gate = asyncio.Event()
    entered = asyncio.Event()
    env = await _make_env(adapter=_RecordingAdapter(gate=gate, entered=entered))
    _arm(env, "list_load")

    _result, raised = await _execute_catching(env)
    assert raised is not None

    resume_task = asyncio.create_task(env.orch.resume_plan(TENANT, PLAN))
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        # While the resume holds the lease, a concurrent duplicate execute
        # must collapse instead of racing the compensation.
        duplicate = await env.orch.execute_durable_plan(TENANT, PLAN)
        assert duplicate["status"] == "already_running"
    finally:
        gate.set()
        resumed = await asyncio.wait_for(resume_task, timeout=5)

    assert resumed["status"] == "completed"
    assert _attempt_counts(env) == {"a0": 1, "a1": 1}
    assert _attempt_counts(env, PLAN_B) == {"bz": 0}


# ---------------------------------------------------------------------------
# Verifier failures — plan-level claims must match what verification proved
# ---------------------------------------------------------------------------


async def test_execute_never_claims_verified_when_adapter_verification_fails():
    """P6 (verifier failure): the default mock verifier fails every check.

    Execution may complete, but the plan-level verdict must then be
    EXECUTED_NOT_VERIFIED — never EXECUTED_AND_VERIFIED.
    """
    env = await _make_env()  # MockRecoveryAdapter.verify() always returns False

    result = await env.orch.execute_durable_plan(TENANT, PLAN)

    assert result["status"] == "completed"
    assert result["completed"] == 2
    steps = env.exec_repo.steps_for(PLAN)
    assert all(s.verification_passed is False for s in steps.values())
    assert result["verification_status"] == (
        VerificationStatus.EXECUTED_NOT_VERIFIED.value
    )
    assert result["verification_status"] != (
        VerificationStatus.EXECUTED_AND_VERIFIED.value
    )


async def test_execute_claims_verified_only_when_adapter_verification_passes():
    """Guard: a genuinely verifying adapter still earns the verified claim."""
    env = await _make_env(adapter=_VerifyingAdapter())

    result = await env.orch.execute_durable_plan(TENANT, PLAN)

    assert result["status"] == "completed"
    steps = env.exec_repo.steps_for(PLAN)
    assert all(s.verification_passed is True for s in steps.values())
    assert result["verification_status"] == (
        VerificationStatus.EXECUTED_AND_VERIFIED.value
    )


async def test_verifier_crash_fails_the_step_closed_then_resume_reports_unverified():
    """Verifier crashes and verifier denials both stay fail-closed."""
    env = await _make_env()
    _arm(env, "verify_phase")

    first = await env.orch.execute_durable_plan(TENANT, PLAN)
    assert first["status"] == "stopped"
    assert first["verification_status"] == (
        VerificationStatus.EXECUTION_FAILED.value
    )
    steps = env.exec_repo.steps_for(PLAN)
    assert steps["a0"].execution_state == _FAILED
    assert "verify_phase" in (steps["a0"].error or "")

    resumed = await env.orch.resume_plan(TENANT, PLAN)
    assert resumed["status"] == "completed"
    # The mock verifier still fails every independent re-check, so no
    # resume-side claim may say the run was verified.
    assert resumed.get("verification_status") != (
        VerificationStatus.EXECUTED_AND_VERIFIED.value
    )
    assert _attempt_counts(env) == {"a0": 2, "a1": 1}


# ---------------------------------------------------------------------------
# Route-level honesty: SAFE_AUTOMATIC requires a verified plan
# ---------------------------------------------------------------------------


class _RoutePlanRepo:
    """RecoveryPlanRepository double with enum round-trip (as SQL does)."""

    def __init__(self, plans: list[RecoveryPlan]) -> None:
        self._plans = {p.plan_id: p for p in plans}

    async def get_by_plan_id(self, tenant_id: str, plan_id: str) -> RecoveryPlan | None:
        plan = self._plans.get(plan_id)
        if plan is not None and plan.tenant_id == tenant_id:
            return plan
        return None

    async def update_status(
        self, tenant_id: str, plan_id: str, status: RecoveryStatus, **fields: Any
    ) -> RecoveryPlan | None:
        plan = await self.get_by_plan_id(tenant_id, plan_id)
        if plan is None:
            return None
        outcome = fields.get("outcome", plan.outcome)
        if not isinstance(outcome, RecoveryOutcome):
            outcome = RecoveryOutcome(outcome)
        updated = replace(
            plan,
            status=status,
            outcome=outcome,
            simulation_result=fields.get("simulation_result", plan.simulation_result),
            executed_by=fields.get("executed_by", plan.executed_by),
            execution_status=fields.get("execution_status", plan.execution_status),
        )
        self._plans[plan_id] = updated
        return updated


class _RouteActionRepo:
    """ProtectedActionRepository double (get + descendants)."""

    def __init__(self, actions: list[ProtectedAction]) -> None:
        self._actions = {a.action_id: a for a in actions}

    async def get_by_action_id(
        self, tenant_id: str, action_id: str
    ) -> ProtectedAction | None:
        action = self._actions.get(action_id)
        if action is not None and action.tenant_id == tenant_id:
            return action
        return None

    async def list_descendants(
        self, tenant_id: str, root_action_id: str, **kwargs: Any
    ) -> tuple[list[ProtectedAction], int]:
        result = [
            a
            for a in self._actions.values()
            if a.parent_action_id == root_action_id and a.tenant_id == tenant_id
        ]
        return result, len(result)


async def _call_execute_route(adapters: list[Any]) -> Any:
    a0 = _make_action("a0")
    a1 = replace(_make_action("a1"), parent_action_id="a0")
    plan = RecoveryPlan(
        plan_id=PLAN,
        tenant_id=TENANT,
        incident_action_id="a0",
        status=RecoveryStatus.APPROVED,
        topological_order=["a0", "a1"],
    )
    user = UserResponse(
        id=uuid.uuid4(),
        email="wp7-route@test.com",
        is_active=True,
        role="admin",
        tenant_id=TENANT,
    )
    return await execute_recovery_plan(
        plan_id=PLAN,
        _authorized=user,
        current_user=user,
        plan_repo=_RoutePlanRepo([plan]),
        action_repo=_RouteActionRepo([a0, a1]),
        evidence_repo=_EvidenceRepo([_make_evidence("a0"), _make_evidence("a1")]),
        execution_repo=_ExecutionRepo(),
        adapters=adapters,
    )


async def test_route_execute_never_promotes_unverified_execution_to_safe_automatic():
    """P6 at the API boundary: completed-but-unverified ≠ SAFE_AUTOMATIC.

    The default mock adapter executes every compensation but fails every
    independent verification; the route must record outcome=unknown (honest
    uncertainty), not safe_automatic (a promise it cannot support).
    """
    response = await _call_execute_route(adapters=[MockRecoveryAdapter(scenario="success")])

    assert response.status == RecoveryStatus.COMPLETED.value
    assert response.outcome == RecoveryOutcome.UNKNOWN.value
    assert response.outcome != RecoveryOutcome.SAFE_AUTOMATIC.value


async def test_route_execute_promotes_fully_verified_execution_to_safe_automatic():
    """Guard: a completed, independently verified run still earns the claim."""
    response = await _call_execute_route(adapters=[_VerifyingAdapter()])

    assert response.status == RecoveryStatus.COMPLETED.value
    assert response.outcome == RecoveryOutcome.SAFE_AUTOMATIC.value
