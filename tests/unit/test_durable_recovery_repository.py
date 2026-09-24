from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.entities.durable_recovery_types import (
    DurablePlanStatus,
    LockMode,
    OrphanRecord,
    PlanCoordinationState,
    ReconciliationPhase,
    ReconciliationRecord,
    WorkerState,
)
from app.domain.repositories.durable_recovery_repository import (
    RecoveryLeaseRepository,
    RecoveryReconciliationRepository,
    RecoveryWorkerRepository,
)
from app.infrastructure.persistence.repositories.in_memory_durable_recovery_repository import (
    InMemoryDurableRecoveryRepository,
)


class ManualClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock(datetime(2026, 1, 1, tzinfo=UTC))


@pytest.fixture
def repo(clock: ManualClock) -> InMemoryDurableRecoveryRepository:
    return InMemoryDurableRecoveryRepository(clock)


@pytest.mark.asyncio
async def test_lease_acquire_renew_release_and_expiry(
    clock: ManualClock,
    repo: InMemoryDurableRecoveryRepository,
) -> None:
    first = await repo.acquire_lease("tenant-a", "plan-1", "worker-1", ttl_seconds=30)

    assert first.acquired is True
    assert first.lease is not None
    assert first.fencing_token == 1
    assert first.lease.worker_id == "worker-1"

    assert (
        await repo.renew_lease(
            "tenant-a",
            "plan-1",
            first.lease.lease_id,
            "worker-1",
            ttl_seconds=60,
        )
        is True
    )
    renewed = await repo.get_active_lease("tenant-a", "plan-1")
    assert renewed is not None
    assert renewed.lease_ttl_seconds == 60
    assert renewed.renewed_at == clock.value

    clock.advance(61)
    assert await repo.get_active_lease("tenant-a", "plan-1") is None

    reclaimed = await repo.acquire_lease(
        "tenant-a",
        "plan-1",
        "worker-2",
        ttl_seconds=30,
        expected_fencing_token=1,
    )
    assert reclaimed.acquired is True
    assert reclaimed.fencing_token == 2
    assert reclaimed.evicted_worker_id == "worker-1"
    assert await repo.get_fencing_token("tenant-a", "plan-1") == 2

    assert await repo.release_lease("tenant-a", "plan-1", reclaimed.lease_id, "worker-2") is True
    assert await repo.get_active_lease("tenant-a", "plan-1") is None


@pytest.mark.asyncio
async def test_lease_contention_expected_token_and_idempotency(
    repo: InMemoryDurableRecoveryRepository,
) -> None:
    owner = await repo.acquire_lease("tenant-a", "plan-1", "worker-1")
    assert owner.lease is not None

    contender = await repo.acquire_lease(
        "tenant-a",
        "plan-1",
        "worker-2",
        expected_fencing_token=owner.fencing_token,
    )
    assert contender.acquired is False
    assert contender.reason == "lease_already_held"
    assert contender.evicted_worker_id == "worker-1"

    mismatch = await repo.acquire_lease("tenant-a", "plan-1", "worker-1", expected_fencing_token=0)
    assert mismatch.acquired is False
    assert mismatch.reason == "expected_fencing_token_mismatch"

    retry = await repo.acquire_lease("tenant-a", "plan-1", "worker-1")
    assert retry.acquired is True
    assert retry.lease is not None
    assert retry.lease.lease_id == owner.lease.lease_id


@pytest.mark.asyncio
async def test_lease_revoke_and_bump_fence_old_lease(
    repo: InMemoryDurableRecoveryRepository,
) -> None:
    lease = await repo.acquire_lease("tenant-a", "plan-1", "worker-1")
    assert lease.lease is not None

    assert await repo.bump_fencing_token("tenant-a", "plan-1", "stale_worker_detected") == 2
    assert await repo.get_active_lease("tenant-a", "plan-1") is None
    assert await repo.renew_lease("tenant-a", "plan-1", lease.lease.lease_id, "worker-1") is False

    next_lease = await repo.acquire_lease(
        "tenant-a", "plan-1", "worker-2", expected_fencing_token=2
    )
    assert next_lease.acquired is True
    assert next_lease.fencing_token == 3

    assert await repo.revoke_lease("tenant-a", "plan-1", "forced_eviction") is True
    assert await repo.get_fencing_token("tenant-a", "plan-1") == 4
    assert await repo.revoke_lease("tenant-a", "plan-1", "forced_eviction") is False


@pytest.mark.asyncio
async def test_lease_tenant_isolation_and_concurrent_acquire(
    repo: InMemoryDurableRecoveryRepository,
) -> None:
    tenant_a = await repo.acquire_lease("tenant-a", "shared-plan", "worker-a")
    tenant_b = await repo.acquire_lease("tenant-b", "shared-plan", "worker-b")
    assert tenant_a.acquired is True
    assert tenant_b.acquired is True
    assert await repo.get_fencing_token("tenant-a", "shared-plan") == 1
    assert await repo.get_fencing_token("tenant-b", "shared-plan") == 1
    assert (await repo.get_active_lease("tenant-a", "shared-plan")).worker_id == "worker-a"
    assert (await repo.get_active_lease("tenant-b", "shared-plan")).worker_id == "worker-b"

    results = await asyncio.gather(
        *(
            repo.acquire_lease("tenant-c", "concurrent-plan", f"worker-{index}")
            for index in range(20)
        )
    )
    winners = [result for result in results if result.acquired]
    assert len(winners) == 1
    assert all(result.fencing_token == 1 for result in results)
    assert all(result.reason == "lease_already_held" for result in results if not result.acquired)


@pytest.mark.asyncio
async def test_worker_registration_heartbeat_and_stale_detection(
    clock: ManualClock,
    repo: InMemoryDurableRecoveryRepository,
) -> None:
    registered = await repo.register_worker(
        "tenant-a", "plan-1", "worker-1", fencing_token=1, lease_id="lease-1"
    )
    idempotent = await repo.register_worker(
        "tenant-a", "plan-1", "worker-1", fencing_token=1, lease_id="lease-1"
    )
    assert idempotent.acquired_at == registered.acquired_at
    assert idempotent.last_heartbeat == registered.last_heartbeat

    clock.advance(10)
    heartbeat = await repo.update_heartbeat(
        "tenant-a", "plan-1", "worker-1", 1, "lease-1", now=clock.value
    )
    assert heartbeat is not None
    assert heartbeat.last_heartbeat == clock.value

    stale = await repo.detect_stale_workers("tenant-a", "plan-1", 5, now=clock.value)
    assert stale == []
    clock.advance(6)
    stale = await repo.detect_stale_workers("tenant-a", "plan-1", 5, now=clock.value)
    assert [worker.worker_id for worker in stale] == ["worker-1"]

    marked = await repo.mark_stale("tenant-a", "plan-1", "worker-1")
    assert marked is not None
    assert marked.state == WorkerState.STALE
    assert await repo.mark_state("tenant-a", "plan-1", "worker-1", "crashed", "boom") is not None
    crashed = await repo.get_worker("tenant-a", "plan-1", "worker-1")
    assert crashed is not None
    assert crashed.state == WorkerState.CRASHED
    assert crashed.last_error == "boom"


@pytest.mark.asyncio
async def test_worker_fencing_and_tenant_isolation(
    repo: InMemoryDurableRecoveryRepository,
) -> None:
    await repo.register_worker("tenant-a", "plan-1", "worker-1", fencing_token=3)
    await repo.register_worker("tenant-b", "plan-1", "worker-1", fencing_token=1)

    assert await repo.update_heartbeat("tenant-a", "plan-1", "worker-1", 2) is None
    updated = await repo.update_heartbeat("tenant-a", "plan-1", "worker-1", 4)
    assert updated is not None
    assert updated.fencing_token == 4
    assert [worker.tenant_id for worker in await repo.list_workers("tenant-a", "plan-1")] == [
        "tenant-a"
    ]
    assert [worker.tenant_id for worker in await repo.list_workers("tenant-b", "plan-1")] == [
        "tenant-b"
    ]
    assert await repo.remove_worker("tenant-a", "plan-1", "worker-1") is True
    assert await repo.get_worker("tenant-a", "plan-1", "worker-1") is None
    assert await repo.get_worker("tenant-b", "plan-1", "worker-1") is not None


@pytest.mark.asyncio
async def test_reconciliation_idempotency_latest_and_tenant_isolation(
    repo: InMemoryDurableRecoveryRepository,
) -> None:
    reconciled_at = datetime(2026, 1, 1, tzinfo=UTC)
    record = ReconciliationRecord(
        plan_id="plan-1",
        tenant_id="tenant-a",
        reconciliation_id="recon-1",
        fencing_token=1,
        worker_id="worker-1",
        reconciled_at=reconciled_at,
        phase=ReconciliationPhase.CONVERGE,
        converged=True,
        details={"source": "first"},
    )
    saved = await repo.save_reconciliation("tenant-a", "plan-1", record)
    duplicate = await repo.save_reconciliation(
        "tenant-a", "plan-1", replace(record, converged=False)
    )
    assert duplicate == saved
    assert duplicate.converged is True

    later = await repo.save_reconciliation(
        "tenant-a",
        "plan-1",
        replace(
            record,
            reconciliation_id="recon-2",
            reconciled_at=reconciled_at + timedelta(seconds=1),
        ),
    )
    assert (await repo.get_latest_reconciliation("tenant-a", "plan-1")) == later
    assert await repo.get_latest_reconciliation("tenant-b", "plan-1") is None

    with pytest.raises(ValueError, match="tenant or plan"):
        await repo.save_reconciliation("tenant-b", "plan-1", record)


@pytest.mark.asyncio
async def test_orphans_idempotency_listing_clearing_and_steps(
    repo: InMemoryDurableRecoveryRepository,
) -> None:
    detected_at = datetime(2026, 1, 1, tzinfo=UTC)
    orphan = OrphanRecord(
        tenant_id="tenant-a",
        plan_id="plan-1",
        orphan_id="orphan-1",
        action_id="action-1",
        detected_at=detected_at,
        orphan_kind="step",
        details={"owner": "worker-1"},
    )
    saved = await repo.save_orphan("tenant-a", "plan-1", orphan)
    duplicate = await repo.save_orphan(
        "tenant-a", "plan-1", replace(orphan, details={"owner": "worker-2"})
    )
    assert duplicate == saved
    assert duplicate.details == {"owner": "worker-1"}

    assert [item.orphan_id for item in await repo.list_orphans("tenant-a", "plan-1")] == [
        "orphan-1"
    ]
    steps = await repo.list_orphan_steps_for_plan("tenant-a", "plan-1")
    assert steps[0]["orphan_id"] == "orphan-1"
    assert steps[0]["action_id"] == "action-1"
    assert await repo.clear_orphans("tenant-a", "plan-1") == 1
    assert await repo.clear_orphans("tenant-a", "plan-1") == 0
    assert await repo.list_orphans("tenant-b", "plan-1") == []


@pytest.mark.asyncio
async def test_coordination_state_save_get_fencing_and_tenant_isolation(
    repo: InMemoryDurableRecoveryRepository,
) -> None:
    state = PlanCoordinationState(
        plan_id="plan-1",
        tenant_id="tenant-a",
        status=DurablePlanStatus.PENDING,
        fencing_token=0,
        coordinator_worker_id="worker-1",
        active_worker_id="worker-1",
        lease_id="lease-1",
        lock_mode=LockMode.EXCLUSIVE,
        total_steps=2,
    )
    saved = await repo.save_coordination_state("tenant-a", "plan-1", state)
    duplicate = await repo.save_coordination_state("tenant-a", "plan-1", state)
    assert duplicate == saved

    active = await repo.save_coordination_state(
        "tenant-a", "plan-1", replace(state, status=DurablePlanStatus.ACTIVE, fencing_token=1)
    )
    assert active.status == DurablePlanStatus.ACTIVE
    assert active.fencing_token == 1
    assert await repo.get_fencing_token("tenant-a", "plan-1") == 1

    stale = await repo.save_coordination_state(
        "tenant-a", "plan-1", replace(state, status=DurablePlanStatus.FAILED)
    )
    assert stale.fencing_token == 1
    assert stale.status == DurablePlanStatus.ACTIVE

    assert await repo.bump_fencing_token("tenant-a", "plan-1", "crash_detected") == 2
    coordinated = await repo.get_coordination_state("tenant-a", "plan-1")
    assert coordinated is not None
    assert coordinated.fencing_token == 2
    assert await repo.get_coordination_state("tenant-b", "plan-1") is None

    with pytest.raises(ValueError, match="tenant or plan"):
        await repo.save_coordination_state("tenant-b", "plan-1", state)


def test_repository_implements_all_durable_ports() -> None:
    repo = InMemoryDurableRecoveryRepository()
    assert isinstance(
        repo,
        (RecoveryLeaseRepository, RecoveryWorkerRepository, RecoveryReconciliationRepository),
    )
