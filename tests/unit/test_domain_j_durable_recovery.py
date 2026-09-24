from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.domain.entities.durable_recovery_types import (
    DurablePlanStatus,
    FencingBumpReason,
    LeaseAcquisitionResult,
    LockMode,
    OrphanRecord,
    PlanCoordinationState,
    ReconciliationPhase,
    ReconciliationRecord,
    RecoveryLease,
    WorkerRecord,
    WorkerState,
)
from app.infrastructure.persistence.repositories.in_memory_durable_recovery_repository import (
    InMemoryDurableRecoveryRepository,
)


class MutableClock:
    def __init__(self, initial: datetime):
        self._value = initial

    def __call__(self) -> datetime:
        return self._value

    def advance(self, seconds: int) -> None:
        self._value += timedelta(seconds=seconds)


def make_repo(clock: MutableClock | None = None) -> InMemoryDurableRecoveryRepository:
    if clock is not None:
        return InMemoryDurableRecoveryRepository(clock=clock)
    base = datetime.now(UTC)
    return InMemoryDurableRecoveryRepository(clock=lambda: base)


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Feature 73 - Lease management, fencing tokens, heartbeats, stale detection
# ---------------------------------------------------------------------------


class TestFeature73_LeaseManagement:
    def test_acquire_lease_returns_acquired(self):
        repo = make_repo()
        result = run_async(repo.acquire_lease("t1", "p1", "w1", ttl_seconds=60))
        assert result is not None
        assert result.acquired is True
        assert result.lease is not None
        assert result.fencing_token > 0

    def test_acquire_lease_sets_metadata(self):
        repo = make_repo()
        result = run_async(
            repo.acquire_lease(
                "t1", "p1", "w1", ttl_seconds=60, reason="initial_acquisition"
            )
        )
        assert result.lease.lease_metadata.get("reason") == "initial_acquisition"

    def test_renew_lease_extends_expiry(self):
        base = datetime.now(UTC)
        clock = MutableClock(base)
        repo = InMemoryDurableRecoveryRepository(clock=clock)
        acq = run_async(repo.acquire_lease("t1", "p1", "w1", ttl_seconds=60))
        assert acq.acquired is True
        clock.advance(30)
        renewed = run_async(repo.renew_lease("t1", "p1", acq.lease.lease_id, "w1", ttl_seconds=60))
        assert renewed is True

    def test_release_lease_removes_lease(self):
        repo = make_repo()
        acq = run_async(repo.acquire_lease("t1", "p1", "w1", ttl_seconds=60))
        assert acq.acquired is True
        released = run_async(repo.release_lease("t1", "p1", acq.lease.lease_id, "w1"))
        assert released is True
        lease = run_async(repo.get_active_lease("t1", "p1"))
        assert lease is None

    def test_lease_expiry_blocks_reacquire(self):
        base = datetime.now(UTC)
        clock = MutableClock(base)
        repo = InMemoryDurableRecoveryRepository(clock=clock)
        acq = run_async(repo.acquire_lease("t1", "p1", "w1", ttl_seconds=60))
        assert acq.acquired is True
        clock.advance(61)
        acq2 = run_async(repo.acquire_lease("t1", "p1", "w2", ttl_seconds=60))
        assert acq2.acquired is True
        assert acq2.evicted_worker_id == "w1"

    def test_fencing_token_monotonically_increases(self):
        repo = make_repo()
        r1 = run_async(repo.acquire_lease("t1", "p1", "w1", ttl_seconds=60))
        assert r1.acquired is True
        run_async(repo.release_lease("t1", "p1", r1.lease.lease_id, "w1"))
        r2 = run_async(repo.acquire_lease("t1", "p1", "w2", ttl_seconds=60))
        assert r2.acquired is True
        assert r2.fencing_token > r1.fencing_token

    def test_bump_fencing_token_increases(self):
        repo = make_repo()
        run_async(repo.acquire_lease("t1", "p1", "w1", ttl_seconds=60))
        token1 = run_async(repo.get_fencing_token("t1", "p1"))
        bumped = run_async(
            repo.bump_fencing_token(
                "t1", "p1", FencingBumpReason.STALE_WORKER_DETECTED
            )
        )
        token2 = run_async(repo.get_fencing_token("t1", "p1"))
        assert bumped == token1 + 1
        assert token2 == token1 + 1

    def test_revoke_lease_advances_fencing_token(self):
        repo = make_repo()
        r1 = run_async(repo.acquire_lease("t1", "p1", "w1", ttl_seconds=60))
        assert r1.acquired is True
        revoked = run_async(repo.revoke_lease("t1", "p1", "forced_eviction"))
        assert revoked is True
        token = run_async(repo.get_fencing_token("t1", "p1"))
        assert token == r1.fencing_token + 1

    def test_worker_heartbeat_updates_timestamp(self):
        base = datetime.now(UTC)
        clock = MutableClock(base)
        repo = InMemoryDurableRecoveryRepository(clock=clock)
        reg = run_async(repo.register_worker("t1", "p1", "w1", fencing_token=1, lease_id="l1"))
        assert reg.last_heartbeat == base
        clock.advance(10)
        updated = run_async(repo.update_heartbeat("t1", "p1", "w1", 1, lease_id="l1"))
        assert updated is not None
        assert updated.last_heartbeat == base + timedelta(seconds=10)

    def test_stale_worker_detection(self):
        base = datetime.now(UTC)
        clock = MutableClock(base)
        repo = InMemoryDurableRecoveryRepository(clock=clock)
        run_async(repo.register_worker("t1", "p1", "w1", fencing_token=1))
        clock.advance(120)
        stale = run_async(repo.detect_stale_workers("t1", "p1", stale_threshold_seconds=60))
        assert len(stale) == 1
        assert stale[0].worker_id == "w1"

    def test_mark_stale_transitions_state(self):
        repo = make_repo()
        run_async(repo.register_worker("t1", "p1", "w1", fencing_token=1))
        marked = run_async(repo.mark_stale("t1", "p1", "w1"))
        assert marked is not None
        assert marked.state == WorkerState.STALE

    def test_worker_record_is_stale_method(self):
        base = datetime.now(UTC)
        worker = WorkerRecord(
            plan_id="p1", tenant_id="t1", worker_id="w1",
            state=WorkerState.ACTIVE, fencing_token=1,
            last_heartbeat=base - timedelta(seconds=120),
        )
        assert worker.is_stale(threshold_seconds=60, now=base + timedelta(seconds=1)) is True
        fresh = WorkerRecord(
            plan_id="p1", tenant_id="t1", worker_id="w1",
            state=WorkerState.ACTIVE, fencing_token=1,
            last_heartbeat=base - timedelta(seconds=10),
        )
        assert fresh.is_stale(threshold_seconds=60, now=base + timedelta(seconds=1)) is False

    def test_tenant_isolation_leases(self):
        repo = make_repo()
        r1 = run_async(repo.acquire_lease("t1", "p1", "w1", ttl_seconds=60))
        r2 = run_async(repo.acquire_lease("t2", "p1", "w1", ttl_seconds=60))
        assert r1.acquired is True
        assert r2.acquired is True
        assert r1.lease.tenant_id == "t1"
        assert r2.lease.tenant_id == "t2"

    def test_tenant_isolation_workers(self):
        repo = make_repo()
        run_async(repo.register_worker("t1", "p1", "w1", fencing_token=1))
        run_async(repo.register_worker("t2", "p1", "w1", fencing_token=1))
        workers_t1 = run_async(repo.list_workers("t1", "p1"))
        workers_t2 = run_async(repo.list_workers("t2", "p1"))
        assert len(workers_t1) == 1
        assert len(workers_t2) == 1
        assert workers_t1[0].tenant_id == "t1"
        assert workers_t2[0].tenant_id == "t2"


# ---------------------------------------------------------------------------
# Feature 74 - Reconciliation, orphan detection, crash resume, safe convergence
# ---------------------------------------------------------------------------


class TestFeature74_ReconciliationAndOrphans:
    def test_save_and_get_reconciliation(self):
        repo = make_repo()
        record = ReconciliationRecord(
            plan_id="p1", tenant_id="t1", reconciliation_id="r1",
            fencing_token=1, worker_id="w1",
            reconciled_at=datetime.now(UTC), phase=ReconciliationPhase.CONVERGE,
            converged=True, divergence_count=0,
        )
        saved = run_async(repo.save_reconciliation("t1", "p1", record))
        assert saved.reconciliation_id == "r1"
        latest = run_async(repo.get_latest_reconciliation("t1", "p1"))
        assert latest is not None
        assert latest.reconciliation_id == "r1"

    def test_save_orphan_and_list(self):
        repo = make_repo()
        orphan = OrphanRecord(
            tenant_id="t1", plan_id="p1", orphan_id="o1",
            action_id="a1", detected_at=datetime.now(UTC),
            orphan_kind="step",
        )
        saved = run_async(repo.save_orphan("t1", "p1", orphan))
        assert saved.orphan_id == "o1"
        orphans = run_async(repo.list_orphans("t1", "p1"))
        assert len(orphans) == 1

    def test_clear_orphans(self):
        repo = make_repo()
        orphan = OrphanRecord(
            tenant_id="t1", plan_id="p1", orphan_id="o1",
            action_id="a1", detected_at=datetime.now(UTC),
            orphan_kind="step",
        )
        run_async(repo.save_orphan("t1", "p1", orphan))
        cleared = run_async(repo.clear_orphans("t1", "p1"))
        assert cleared == 1
        orphans = run_async(repo.list_orphans("t1", "p1"))
        assert len(orphans) == 0

    def test_coordination_state_persists(self):
        repo = make_repo()
        state = PlanCoordinationState(
            plan_id="p1", tenant_id="t1",
            status=DurablePlanStatus.ACTIVE, fencing_token=5,
            coordinator_worker_id="w1", active_worker_id="w1",
            completed_steps=2, total_steps=5,
        )
        saved = run_async(repo.save_coordination_state("t1", "p1", state))
        assert saved.fencing_token == 5
        loaded = run_async(repo.get_coordination_state("t1", "p1"))
        assert loaded is not None
        assert loaded.status == DurablePlanStatus.ACTIVE

    def test_coordination_state_tenant_isolation(self):
        repo = make_repo()
        state_t1 = PlanCoordinationState(
            plan_id="p1", tenant_id="t1", status=DurablePlanStatus.ACTIVE
        )
        state_t2 = PlanCoordinationState(
            plan_id="p1", tenant_id="t2", status=DurablePlanStatus.PENDING
        )
        run_async(repo.save_coordination_state("t1", "p1", state_t1))
        run_async(repo.save_coordination_state("t2", "p1", state_t2))
        loaded_t1 = run_async(repo.get_coordination_state("t1", "p1"))
        loaded_t2 = run_async(repo.get_coordination_state("t2", "p1"))
        assert loaded_t1.status == DurablePlanStatus.ACTIVE
        assert loaded_t2.status == DurablePlanStatus.PENDING

    def test_orphan_steps_for_plan(self):
        repo = make_repo()
        orphan = OrphanRecord(
            tenant_id="t1", plan_id="p1", orphan_id="o1",
            action_id="a1", detected_at=datetime.now(UTC),
            orphan_kind="step", details={"step_id": "step-1"},
        )
        run_async(repo.save_orphan("t1", "p1", orphan))
        steps = run_async(repo.list_orphan_steps_for_plan("t1", "p1"))
        assert len(steps) == 1
        assert steps[0]["orphan_id"] == "o1"

    def test_crash_resume_coordination_state(self):
        repo = make_repo()
        state = PlanCoordinationState(
            plan_id="p1", tenant_id="t1",
            status=DurablePlanStatus.PAUSED, fencing_token=3,
            completed_steps=2, total_steps=5,
        )
        run_async(repo.save_coordination_state("t1", "p1", state))
        loaded = run_async(repo.get_coordination_state("t1", "p1"))
        assert loaded.status == DurablePlanStatus.PAUSED
        assert loaded.completed_steps == 2
        assert loaded.total_steps == 5

    def test_safe_convergence_reconciliation(self):
        repo = make_repo()
        rec = ReconciliationRecord(
            plan_id="p1", tenant_id="t1", reconciliation_id="r1",
            fencing_token=1, worker_id="w1",
            reconciled_at=datetime.now(UTC), phase=ReconciliationPhase.VERIFY,
            converged=True, divergence_count=0,
        )
        run_async(repo.save_reconciliation("t1", "p1", rec))
        latest = run_async(repo.get_latest_reconciliation("t1", "p1"))
        assert latest.converged is True
        assert latest.divergence_count == 0


# ---------------------------------------------------------------------------
# Feature 75 - Cross-adapter execution/verification separation, safety envelope
# ---------------------------------------------------------------------------


class TestFeature75_SafetyEnvelope:
    def test_recovery_lease_is_expired_method(self):
        now = datetime.now(UTC)
        lease = RecoveryLease(
            plan_id="p1", tenant_id="t1", worker_id="w1",
            lease_id="l1", fencing_token=1,
            acquired_at=now, expires_at=now - timedelta(seconds=1),
            renewed_at=now, lease_ttl_seconds=60,
        )
        assert lease.is_expired(now=now) is True
        active = RecoveryLease(
            plan_id="p1", tenant_id="t1", worker_id="w1",
            lease_id="l1", fencing_token=1,
            acquired_at=now, expires_at=now + timedelta(seconds=60),
            renewed_at=now, lease_ttl_seconds=60,
        )
        assert active.is_expired(now=now) is False

    def test_recovery_lease_ownership(self):
        now = datetime.now(UTC)
        lease = RecoveryLease(
            plan_id="p1", tenant_id="t1", worker_id="w1",
            lease_id="l1", fencing_token=1,
            acquired_at=now, expires_at=now + timedelta(seconds=60),
            renewed_at=now, lease_ttl_seconds=60,
        )
        assert lease.is_owned_by("t1", "w1") is True
        assert lease.is_owned_by("t2", "w1") is False
        assert lease.is_owned_by("t1", "w2") is False

    def test_plan_coordination_state_with_status(self):
        state = PlanCoordinationState(
            plan_id="p1", tenant_id="t1", status=DurablePlanStatus.PENDING
        )
        updated = state.with_status(DurablePlanStatus.ACTIVE, fencing_token=10)
        assert updated.status == DurablePlanStatus.ACTIVE
        assert updated.fencing_token == 10
        assert updated.plan_id == "p1"

    def test_worker_state_enum_values(self):
        assert WorkerState.ACTIVE.value == "active"
        assert WorkerState.STALE.value == "stale"
        assert WorkerState.CRASHED.value == "crashed"
        assert WorkerState.OFFLINE.value == "offline"

    def test_durable_plan_status_enum_values(self):
        assert DurablePlanStatus.PENDING.value == "pending"
        assert DurablePlanStatus.ACTIVE.value == "active"
        assert DurablePlanStatus.FAILED.value == "failed"
        assert DurablePlanStatus.STALE.value == "stale"

    def test_fencing_bump_reason_enum_values(self):
        assert FencingBumpReason.INITIAL_ACQUISITION.value == "initial_acquisition"
        assert FencingBumpReason.STALE_WORKER_DETECTED.value == "stale_worker_detected"
        assert FencingBumpReason.ORPHAN_RECLAIM.value == "orphan_reclaim"

    def test_lock_mode_enum_values(self):
        assert LockMode.EXCLUSIVE.value == "exclusive"
        assert LockMode.SHARED.value == "shared"

    def test_reconciliation_phase_enum_values(self):
        assert ReconciliationPhase.LOAD.value == "load"
        assert ReconciliationPhase.CONVERGE.value == "converge"
        assert ReconciliationPhase.VERIFY.value == "verify"

    def test_lease_acquisition_result_failure(self):
        result = LeaseAcquisitionResult(acquired=False, lease=None, reason="test", fencing_token=0)
        assert result.acquired is False
        assert result.lease is None

    def test_orphan_record_details(self):
        orphan = OrphanRecord(
            tenant_id="t1", plan_id="p1", orphan_id="o1",
            action_id="a1", detected_at=datetime.now(UTC),
            orphan_kind="step", details={"step_id": "step-1"},
        )
        assert orphan.details["step_id"] == "step-1"

    def test_multiple_workers_per_plan(self):
        repo = make_repo()
        run_async(repo.register_worker("t1", "p1", "w1", fencing_token=1))
        run_async(repo.register_worker("t1", "p1", "w2", fencing_token=1))
        workers = run_async(repo.list_workers("t1", "p1"))
        assert len(workers) == 2
        ids = {w.worker_id for w in workers}
        assert ids == {"w1", "w2"}

    def test_remove_worker(self):
        repo = make_repo()
        run_async(repo.register_worker("t1", "p1", "w1", fencing_token=1))
        removed = run_async(repo.remove_worker("t1", "p1", "w1"))
        assert removed is True
        workers = run_async(repo.list_workers("t1", "p1"))
        assert len(workers) == 0

    def test_expected_fencing_token_mismatch(self):
        repo = make_repo()
        r1 = run_async(repo.acquire_lease("t1", "p1", "w1", ttl_seconds=60))
        assert r1.acquired is True
        r2 = run_async(
            repo.acquire_lease(
                "t1", "p1", "w2", ttl_seconds=60, expected_fencing_token=999
            )
        )
        assert r2.acquired is False
        assert r2.reason == "expected_fencing_token_mismatch"

    def test_stale_worker_no_false_positive(self):
        base = datetime.now(UTC)
        repo = InMemoryDurableRecoveryRepository(clock=lambda: base)
        run_async(repo.register_worker("t1", "p1", "w1", fencing_token=1))
        stale = run_async(repo.detect_stale_workers("t1", "p1", stale_threshold_seconds=120))
        assert len(stale) == 0

    def test_coordination_state_reject_stale_fencing_token(self):
        repo = make_repo()
        state_new = PlanCoordinationState(
            plan_id="p1", tenant_id="t1", status=DurablePlanStatus.ACTIVE, fencing_token=5
        )
        state_old = PlanCoordinationState(
            plan_id="p1", tenant_id="t1", status=DurablePlanStatus.FAILED, fencing_token=3
        )
        run_async(repo.save_coordination_state("t1", "p1", state_new))
        result = run_async(repo.save_coordination_state("t1", "p1", state_old))
        assert result.fencing_token == 5
        assert result.status == DurablePlanStatus.ACTIVE

    def test_reconciliation_immutability(self):
        repo = make_repo()
        rec = ReconciliationRecord(
            plan_id="p1", tenant_id="t1", reconciliation_id="r1",
            fencing_token=1, worker_id="w1",
            reconciled_at=datetime.now(UTC), phase=ReconciliationPhase.LOAD,
            converged=False, divergence_count=2,
        )
        saved = run_async(repo.save_reconciliation("t1", "p1", rec))
        assert saved.divergence_count == 2
        latest = run_async(repo.get_latest_reconciliation("t1", "p1"))
        assert latest.divergence_count == 2
