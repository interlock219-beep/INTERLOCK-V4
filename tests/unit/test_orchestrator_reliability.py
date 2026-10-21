"""Interlock V5 — distributed orchestrator reliability tests.

Covers the plan-lease coordination contract (acquire/conflict/expiry
takeover/fencing tokens/renewal loss), capability gating of adapter claims,
and evidence-faithful action reconstruction.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.domain.entities.causal_state_types import DurableExecutionStep
from app.domain.entities.protected_action import ProtectedAction
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


class _Clock:
    """Controllable clock for lease-expiry tests."""

    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def _make_action(action_id: str, tenant_id: str = "test-tenant") -> ProtectedAction:
    return ProtectedAction(
        action_id=action_id,
        tenant_id=tenant_id,
        actor_user_id=None,
        agent_id="agent-1",
        authority_grant_id=None,
        tool="database",
        resource="record:1",
        action_type="insert",
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
        before_state_ref="state:before:123",
    )


def _make_evidence(
    action_id: str,
    tenant_id: str = "test-tenant",
    before_state_reference: str | None = "state:before:123",
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
        target_system="mock",
        target_resource="record:1",
        action_type="insert",
        before_state_reference=before_state_reference,
        after_state_reference="state:after:456",
        compensation_payload={"op": "restore"},
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
        self._by_action = {e.action_id: e for e in evidence_list}

    async def get_by_action_id(
        self, tenant_id: str, action_id: str
    ) -> RecoveryEvidence | None:
        ev = self._by_action.get(action_id)
        if ev and ev.tenant_id == tenant_id:
            return ev
        return None


class _ExecutionRepo:
    def __init__(self) -> None:
        self._steps: dict[str, DurableExecutionStep] = {}

    async def save(
        self, step: DurableExecutionStep, expected_fencing_token: int | None = None
    ) -> DurableExecutionStep:
        # V6 fencing contract: reject writes older than the stored fence.
        fences: dict[str, int] = getattr(self, "_fences", {})
        self._fences = fences
        enforce_write_fence(
            fences.get(step.step_id, 0), expected_fencing_token, step.step_id
        )
        if expected_fencing_token is not None:
            fences[step.step_id] = expected_fencing_token
        self._steps[step.step_id] = step
        return step

    async def list_by_plan(
        self, tenant_id: str, plan_id: str, limit: int = 500, offset: int = 0
    ) -> tuple[list[DurableExecutionStep], int]:
        # Real suspension point so concurrent plan submissions interleave.
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

    def plan_states(self, plan_id: str) -> list[str]:
        return sorted(
            s.execution_state
            for s in self._steps.values()
            if s.plan_id == plan_id
        )


def _refusing_adapter(*verdicts: str):
    """An adapter that explicitly refuses steps with the given verdicts."""

    class _Refusing(MockRecoveryAdapter):
        def __init__(self) -> None:
            super().__init__(scenario="success")
            self.claimed_steps: list[str] = []

        async def can_recover(self, action: ProtectedAction) -> str:
            return verdicts[0]

        async def detect_drift(self, action, evidence, current_state=None):
            self.claimed_steps.append(action.action_id)
            return await super().detect_drift(action, evidence, current_state)

    return _Refusing()


class _RenewFailingStore(InMemoryPlanLeaseStore):
    """Lease store whose renewals always fail (simulates takeover mid-run)."""

    async def renew(self, plan_id, owner, ttl_seconds):
        return None


async def _build_orchestrator(
    adapters=None, lease_store=None, n_actions: int = 2
):
    actions = [_make_action(f"a{i}") for i in range(n_actions)]
    evidence = [_make_evidence(f"a{i}") for i in range(n_actions)]
    orchestrator = DistributedRecoveryOrchestrator(
        _EvidenceRepo(evidence),
        _ExecutionRepo(),
        adapters if adapters is not None else [MockRecoveryAdapter(scenario="success")],
        lease_store=lease_store,
    )
    await orchestrator.create_durable_plan(
        "test-tenant", "plan-1", actions, [a.action_id for a in actions]
    )
    return orchestrator


# ---------------------------------------------------------------------------
# Plan lease store contract
# ---------------------------------------------------------------------------


async def test_lease_store_acquire_conflict_and_release():
    clock = _Clock()
    store = InMemoryPlanLeaseStore(clock=clock)

    lease = await store.try_acquire("plan-1", "orch-a", 60)
    assert lease is not None
    assert lease.fencing_token == 1
    assert lease.owner == "orch-a"

    # Held by orch-a: anyone else (and orch-a itself) is rejected.
    assert await store.try_acquire("plan-1", "orch-b", 60) is None
    assert await store.try_acquire("plan-1", "orch-a", 60) is None

    # Only the owner may renew; release only drops the owner's lease.
    assert await store.renew("plan-1", "orch-b", 60) is None
    renewed = await store.renew("plan-1", "orch-a", 60)
    assert renewed is not None
    assert await store.release("plan-1", "orch-b") is None
    assert (await store.get("plan-1")) is not None

    # After release the plan is acquirable again (token keeps counting).
    await store.release("plan-1", "orch-a")
    assert await store.get("plan-1") is None
    again = await store.try_acquire("plan-1", "orch-b", 60)
    assert again is not None
    assert again.fencing_token == 2


async def test_lease_store_expiry_takeover_increments_fencing_token():
    clock = _Clock()
    store = InMemoryPlanLeaseStore(clock=clock)

    first = await store.try_acquire("plan-1", "orch-crashed", 30)
    assert first.fencing_token == 1

    clock.advance(31)  # the owner crashed and the lease expired

    # A late renewal from the crashed owner must fail.
    assert await store.renew("plan-1", "orch-crashed", 30) is None

    takeover = await store.try_acquire("plan-1", "orch-b", 30)
    assert takeover is not None
    assert takeover.owner == "orch-b"
    assert takeover.fencing_token == 2


async def test_lease_store_distinct_plans_independent():
    store = InMemoryPlanLeaseStore()
    assert await store.try_acquire("plan-1", "orch-a", 60) is not None
    assert await store.try_acquire("plan-2", "orch-b", 60) is not None
    assert (await store.get("plan-1")).owner == "orch-a"
    assert (await store.get("plan-2")).owner == "orch-b"


# ---------------------------------------------------------------------------
# Orchestrator lease integration
# ---------------------------------------------------------------------------


async def test_concurrent_plan_submissions_collapse_to_already_running():
    orchestrator = await _build_orchestrator()

    results = await asyncio.gather(
        orchestrator.execute_durable_plan("test-tenant", "plan-1"),
        orchestrator.execute_durable_plan("test-tenant", "plan-1"),
    )
    statuses = sorted(r["status"] for r in results)
    assert statuses == ["already_running", "completed"]


async def test_preheld_lease_blocks_execution():
    store = InMemoryPlanLeaseStore()
    await store.try_acquire("plan-1", "another-instance", 300)
    orchestrator = await _build_orchestrator(lease_store=store)

    result = await orchestrator.execute_durable_plan("test-tenant", "plan-1")
    assert result["status"] == "already_running"
    # Nothing ran.
    assert orchestrator._execution_repo.plan_states("plan-1") == [
        ExecutionState.PENDING.value
    ] * 2


async def test_expired_lease_is_taken_over_with_fencing():
    clock = _Clock()
    store = InMemoryPlanLeaseStore(clock=clock)
    abandoned = await store.try_acquire("plan-1", "orch-crashed", 60)
    assert abandoned.fencing_token == 1

    clock.advance(61)  # crashed instance never renewed

    orchestrator = await _build_orchestrator(lease_store=store)
    result = await orchestrator.execute_durable_plan("test-tenant", "plan-1")

    assert result["status"] == "completed"
    assert result["completed"] == 2
    # Takeover is visible through the incremented fencing token.
    assert result["fencing_token"] == 2
    # The lease is released after execution.
    assert await store.get("plan-1") is None


async def test_renewal_loss_aborts_plan_execution():
    store = _RenewFailingStore()
    orchestrator = await _build_orchestrator(lease_store=store)

    result = await orchestrator.execute_durable_plan("test-tenant", "plan-1")

    assert result["status"] == "lease_lost"
    assert "lease" in result["stop_reason"].lower()
    # No step was executed under a lost lease.
    assert orchestrator._execution_repo.plan_states("plan-1") == [
        ExecutionState.PENDING.value
    ] * 2
    # The orchestrator still released its (now meaningless) lease.
    assert await store.get("plan-1") is None


async def test_lease_released_after_normal_completion():
    store = InMemoryPlanLeaseStore()
    orchestrator = await _build_orchestrator(lease_store=store)

    first = await orchestrator.execute_durable_plan("test-tenant", "plan-1")
    assert first["status"] == "completed"
    assert first["fencing_token"] == 1
    assert await store.get("plan-1") is None

    # A second run re-acquires the lease and marks steps already completed.
    second = await orchestrator.execute_durable_plan("test-tenant", "plan-1")
    assert second["status"] == "completed"
    assert second["fencing_token"] == 2


# ---------------------------------------------------------------------------
# Capability gating
# ---------------------------------------------------------------------------


async def test_unsupporting_adapter_never_claims_the_step():
    refusing = _refusing_adapter("unsupported")
    orchestrator = await _build_orchestrator(
        adapters=[refusing, MockRecoveryAdapter(scenario="success")]
    )

    result = await orchestrator.execute_durable_plan("test-tenant", "plan-1")
    assert result["status"] == "completed"
    # The refusing adapter was asked but never got as far as drift/claiming.
    assert refusing.claimed_steps == []


async def test_all_refusing_adapters_require_manual_action():
    for verdict in ("unsupported", "irreversible", "requires_approval"):
        refusing = _refusing_adapter(verdict)
        orchestrator = await _build_orchestrator(adapters=[refusing])

        result = await orchestrator.execute_durable_plan("test-tenant", "plan-1")
        assert result["status"] == "partial"
        assert result["manual_required"] == 2
        assert refusing.claimed_steps == []
        states = orchestrator._execution_repo.plan_states("plan-1")
        assert states == [ExecutionState.REQUIRES_MANUAL_ACTION.value] * 2


async def test_unknown_verdict_stays_eligible():
    """An 'unknown' can_recover verdict does not block claiming: the adapter's
    own fail-closed guards decide during execution."""
    orchestrator = await _build_orchestrator(
        adapters=[_refusing_adapter("unknown")]
    )
    result = await orchestrator.execute_durable_plan("test-tenant", "plan-1")
    assert result["status"] == "completed"


async def test_step_action_reconstructed_from_evidence():
    """Steps are replayed with evidence-derived action_type/before_state_ref so
    adapter capability checks see the captured reversibility context."""
    actions = [_make_action("a0")]
    evidence = [_make_evidence("a0")]
    orchestrator = DistributedRecoveryOrchestrator(
        _EvidenceRepo(evidence), _ExecutionRepo(), [MockRecoveryAdapter(scenario="success")]
    )
    await orchestrator.create_durable_plan("test-tenant", "plan-1", actions, ["a0"])

    captured: list[ProtectedAction] = []

    class _Spy(MockRecoveryAdapter):
        async def detect_drift(self, action, evidence, current_state=None):
            captured.append(action)
            return await super().detect_drift(action, evidence, current_state)

    orchestrator._adapters = [_Spy(scenario="success")]
    result = await orchestrator.execute_durable_plan("test-tenant", "plan-1")

    assert result["status"] == "completed"
    assert len(captured) == 1
    replayed = captured[0]
    assert replayed.before_state_ref == "state:before:123"
    assert replayed.action_type == "insert"
    assert replayed.tool == "mock"


# ---------------------------------------------------------------------------
# Release-gate audit regressions (V5 audit Phase 2 findings, Phase 4 fixes)
# ---------------------------------------------------------------------------


async def test_default_lease_store_shared_across_instances():
    """Orchestrators constructed without an explicit store must share one
    process-wide lease space.

    Production API routes build a fresh orchestrator per request; a
    per-instance default store gave each request its own lease space, so two
    concurrent requests could execute the same plan through independent
    (vacuous) single-executor guarantees.
    """
    gate = asyncio.Event()

    class _BlockingAdapter(MockRecoveryAdapter):
        def __init__(self, scenario: str) -> None:
            super().__init__(scenario=scenario)
            self.entered = asyncio.Event()

        async def execute_compensation(self, compensation, idempotency_key):
            self.entered.set()
            await gate.wait()
            return await super().execute_compensation(
                compensation, idempotency_key
            )

    blocker = _BlockingAdapter("success")
    orch_a = await _build_orchestrator(adapters=[blocker])
    orch_b = await _build_orchestrator(
        adapters=[MockRecoveryAdapter(scenario="success")]
    )

    task = asyncio.create_task(
        orch_a.execute_durable_plan("test-tenant", "plan-1")
    )
    try:
        await asyncio.wait_for(blocker.entered.wait(), timeout=5)
        # orch_b is a different orchestrator instance (as in a second HTTP
        # request) but must see the same lease space.
        result_b = await orch_b.execute_durable_plan("test-tenant", "plan-1")
        assert result_b["status"] == "already_running"
    finally:
        gate.set()
        first = await asyncio.wait_for(task, timeout=5)

    assert first["status"] == "completed"


async def test_resume_plan_enforces_plan_lease():
    """resume_plan must participate in the plan-lease contract: while another
    instance holds the lease, resume must collapse to ``already_running``
    instead of double-executing compensations alongside the lease holder."""
    store = InMemoryPlanLeaseStore()
    await store.try_acquire("plan-1", "another-instance", 300)
    orchestrator = await _build_orchestrator(lease_store=store)

    result = await orchestrator.resume_plan("test-tenant", "plan-1")

    assert result["status"] == "already_running"
    # Nothing ran while another instance holds the lease.
    assert orchestrator._execution_repo.plan_states("plan-1") == [
        ExecutionState.PENDING.value
    ] * 2


async def test_resume_renewal_loss_aborts_resume():
    """Resume renews the lease at step boundaries exactly like execute: a
    renewal failure (expired/taken-over lease) aborts before the next step."""
    store = _RenewFailingStore()
    orchestrator = await _build_orchestrator(lease_store=store)

    result = await orchestrator.resume_plan("test-tenant", "plan-1")

    assert result["status"] == "lease_lost"
    assert orchestrator._execution_repo.plan_states("plan-1") == [
        ExecutionState.PENDING.value
    ] * 2


async def test_execute_phase_error_does_not_fall_through_to_next_adapter():
    """An exception raised inside an adapter's execute/verify phase must fail
    the step, never fall through to the next registered adapter: a
    fall-through lets a second adapter re-apply a compensation the first one
    already executed (double compensation)."""

    class _ExplodingVerify(MockRecoveryAdapter):
        async def verify(self, compensation):
            raise TypeError("verify protocol mismatch")

    class _Counting(MockRecoveryAdapter):
        def __init__(self, scenario: str) -> None:
            super().__init__(scenario=scenario)
            self.execute_calls = 0

        async def execute_compensation(self, compensation, idempotency_key):
            self.execute_calls += 1
            return await super().execute_compensation(
                compensation, idempotency_key
            )

    first = _ExplodingVerify("success")
    second = _Counting("success")
    orchestrator = await _build_orchestrator(adapters=[first, second])

    result = await orchestrator.execute_durable_plan("test-tenant", "plan-1")

    assert result["status"] == "stopped"
    assert result["failed"] == 1
    assert "verify protocol mismatch" in str(result["execution_results"])
    # The second adapter must never run a compensation for a step the first
    # adapter already executed.
    assert second.execute_calls == 0
    states = orchestrator._execution_repo.plan_states("plan-1")
    assert ExecutionState.FAILED.value in states


async def test_external_outcome_verification_consults_all_adapters():
    """Resume-time verification must consult every registered adapter and
    accept any positive verdict — the adapter that can verify the payload may
    not be first in registration order.  Previously the first adapter's verdict
    was returned unconditionally (false negatives on multi-adapter sets)."""

    class _SaysNo(MockRecoveryAdapter):
        async def verify(self, compensation):
            return VerificationResult(
                action_id=compensation.action_id,
                verified=False,
                details={"reason": "foreign payload"},
            )

    class _SaysYes(MockRecoveryAdapter):
        async def verify(self, compensation):
            return VerificationResult(
                action_id=compensation.action_id,
                verified=True,
                details={"reason": "matches recorded evidence"},
            )

    orchestrator = await _build_orchestrator(
        adapters=[_SaysNo("success"), _SaysYes("success")]
    )

    # Mark the first step as an unknown external outcome awaiting resume-time
    # verification.
    repo = orchestrator._execution_repo
    step_key = next(
        k for k, s in repo._steps.items() if s.action_id == "a0"
    )
    step = repo._steps[step_key]
    repo._steps[step_key] = replace(
        step, execution_state=ExecutionState.UNKNOWN_EXTERNAL_OUTCOME.value
    )

    result = await orchestrator.resume_plan("test-tenant", "plan-1")

    assert result["verification_results"]["a0"] == "verified"
    # The verified step is not re-executed on resume.
    assert "a0" not in result["execution_results"]
    assert result["status"] == "completed"
