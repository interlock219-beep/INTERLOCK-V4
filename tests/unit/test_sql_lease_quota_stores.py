"""V6 WP-3: shared (cross-process) lease + quota coordination backends.

Contract parity — ``_lease_contract`` is a single assertion body executed
against both the in-memory store and ``SQLPlanLeaseStore``: the SQL backend
must reproduce in-process semantics exactly (no reentrant acquisition,
expiry takeover with monotonic fencing tokens, owner-only renew/release,
released leases invisible to ``get``).

Multi-process drills — separate OS processes sharing one SQLite file prove:
(a) refusal of acquisition while a lease is held, (b) refusal of renewal by
a non-owner and by a stale owner after takeover, (c) expiry takeover with a
fencing token that never goes backwards, and (d) quota-limit enforcement
exactly once under concurrent contention.  These are process-level results
over SQLite — they are **not** a distributed-database (Postgres/Redis)
correctness proof; that remains blocked on authorized infrastructure (G-3).
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.domain.services.distributed_recovery_orchestrator import (
    InMemoryPlanLeaseStore,
)
from app.domain.services.tenant_quota_service import (
    InProcessQuotaCounterStore,
    TenantQuotaPolicy,
    TenantQuotaService,
)
from app.infrastructure.persistence.repositories.sqlalchemy_coordination_stores import (
    SQLPlanLeaseStore,
    SQLQuotaCounterStore,
    build_plan_lease_store,
    build_quota_counter_store,
)
from tests.unit.coordination_store_factories import (
    ManualClock,
    make_sql_lease_store,
    make_sql_quota_store,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# Child exit codes: 0 = behaved as required, 42 = violated the contract.
REQUIRED = 0
VIOLATED = 42
# Quota children exit ``QUOTA_BASE + admitted`` so the parent can sum
# admissions across processes; anything below the base is an error.
QUOTA_BASE = 10
CHILD_TIMEOUT_SECONDS = 180

_CHILD_TRY_ACQUIRE = """
import asyncio, sys
from tests.unit.coordination_store_factories import make_sql_lease_store
store = make_sql_lease_store(sys.argv[1])
lease = asyncio.run(store.try_acquire("plan-mp", "child", 3600))
sys.exit(0 if lease is None else 42)
"""

_CHILD_TRY_RENEW = """
import asyncio, sys
from tests.unit.coordination_store_factories import make_sql_lease_store
store = make_sql_lease_store(sys.argv[1])
lease = asyncio.run(store.renew("plan-mp", sys.argv[2], 3600))
sys.exit(0 if lease is None else 42)
"""

_CHILD_QUOTA_RESERVE = """
import sys
from datetime import UTC, datetime, timedelta
from tests.unit.coordination_store_factories import make_sql_quota_store

db_dir, attempts, limit = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
store = make_sql_quota_store(db_dir)
now = datetime(2026, 3, 1, tzinfo=UTC)
admitted = 0
for _ in range(attempts):
    ok, _count = store.try_reserve_plan("t-mp", now, timedelta(days=1), limit)
    if ok:
        admitted += 1
sys.exit(10 + admitted)
"""


def _run_child(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=CHILD_TIMEOUT_SECONDS,
        check=False,
    )


# ---------------------------------------------------------------------------
# Contract parity: one body, both backends.
# ---------------------------------------------------------------------------


async def _lease_contract_scenario(store: object, clock: ManualClock) -> None:
    # Fresh acquisition starts the fencing chain at 1.
    first = await store.try_acquire("plan-1", "owner-a", 3600)  # type: ignore[attr-defined]
    assert first is not None
    assert first.fencing_token == 1
    assert first.owner == "owner-a"

    # Held: no reentrancy, no takeover by others, no foreign renew.
    assert await store.try_acquire("plan-1", "owner-a", 3600) is None  # type: ignore[attr-defined]
    assert await store.try_acquire("plan-1", "owner-b", 3600) is None  # type: ignore[attr-defined]
    assert await store.renew("plan-1", "owner-b", 3600) is None  # type: ignore[attr-defined]

    # Renewal extends expiry but never moves the fencing token.
    renewed = await store.renew("plan-1", "owner-a", 7200)  # type: ignore[attr-defined]
    assert renewed is not None
    assert renewed.fencing_token == 1
    assert renewed.expires_at > first.expires_at

    # get() sees the held lease (expired or not).
    got = await store.get("plan-1")  # type: ignore[attr-defined]
    assert got is not None
    assert got.owner == "owner-a"
    assert got.fencing_token == 1

    # Release by a non-owner is a no-op.
    await store.release("plan-1", "owner-b")  # type: ignore[attr-defined]
    assert await store.get("plan-1") is not None  # type: ignore[attr-defined]

    # Owner release hides the lease but keeps the tombstone for the token.
    await store.release("plan-1", "owner-a")  # type: ignore[attr-defined]
    assert await store.get("plan-1") is None  # type: ignore[attr-defined]

    # Re-acquisition crosses the tombstone: the token never goes backwards.
    second = await store.try_acquire("plan-1", "owner-b", 3600)  # type: ignore[attr-defined]
    assert second is not None
    assert second.fencing_token == 2

    # Deterministic expiry (manual clock, no sleeps): renewal refuses first,
    # then takeover increments the token past the stale holder.
    clock.advance(3601)
    assert await store.renew("plan-1", "owner-b", 3600) is None  # type: ignore[attr-defined]
    taken = await store.try_acquire("plan-1", "owner-c", 3600)  # type: ignore[attr-defined]
    assert taken is not None
    assert taken.fencing_token == 3
    assert taken.owner == "owner-c"

    # The stale owner cannot renew the taken-over lease.
    assert await store.renew("plan-1", "owner-b", 3600) is None  # type: ignore[attr-defined]
    current = await store.get("plan-1")  # type: ignore[attr-defined]
    assert current is not None
    assert current.owner == "owner-c"
    assert current.fencing_token == 3


def test_lease_contract_memory() -> None:
    clock = ManualClock(datetime(2026, 3, 1, tzinfo=UTC))
    asyncio.run(_lease_contract_scenario(InMemoryPlanLeaseStore(clock=clock), clock))


def test_lease_contract_sql(tmp_path: Path) -> None:
    clock = ManualClock(datetime(2026, 3, 1, tzinfo=UTC))
    asyncio.run(_lease_contract_scenario(make_sql_lease_store(tmp_path, clock=clock), clock))


# ---------------------------------------------------------------------------
# Multi-process drills over one shared SQLite file (no sleeps anywhere:
# process exit is the barrier, injected clocks decide expiry).
# ---------------------------------------------------------------------------


def test_multiprocess_lease_refusal_takeover_and_stale_renew(tmp_path: Path) -> None:
    parent = make_sql_lease_store(tmp_path)
    held = asyncio.run(parent.try_acquire("plan-mp", "parent", 3600))
    assert held is not None
    assert held.fencing_token == 1

    # (a) A second process cannot acquire while the lease is held.
    proc = _run_child(_CHILD_TRY_ACQUIRE, str(tmp_path))
    assert proc.returncode == REQUIRED, (
        f"child acquired a held lease (rc={proc.returncode}) {proc.stderr}"
    )

    # (b) A different owner cannot renew the held lease.
    proc = _run_child(_CHILD_TRY_RENEW, str(tmp_path), "child")
    assert proc.returncode == REQUIRED, (
        f"foreign owner renewed a held lease (rc={proc.returncode}) {proc.stderr}"
    )

    # (c) Expiry takeover decided by an injected future clock — the parent's
    #     real-clock lease (expires real-now+3600) is expired at now+7200.
    future = ManualClock(datetime.now(UTC) + timedelta(seconds=7200))
    parent_f = make_sql_lease_store(tmp_path, clock=future)
    taken = asyncio.run(parent_f.try_acquire("plan-mp", "parent-2", 3600))
    assert taken is not None
    assert taken.owner == "parent-2"
    assert taken.fencing_token == held.fencing_token + 1

    # (d) The original owner — a late-arriving stale worker — cannot renew.
    proc = _run_child(_CHILD_TRY_RENEW, str(tmp_path), "parent")
    assert proc.returncode == REQUIRED, (
        f"stale owner renewed a taken-over lease (rc={proc.returncode}) {proc.stderr}"
    )

    # (e) Children still cannot acquire: parent-2's lease is unexpired even
    #     at the child's real clock (written expires = future clock + 3600).
    proc = _run_child(_CHILD_TRY_ACQUIRE, str(tmp_path))
    assert proc.returncode == REQUIRED, (
        f"child acquired parent-2's lease (rc={proc.returncode}) {proc.stderr}"
    )

    got = asyncio.run(parent_f.get("plan-mp"))
    assert got is not None
    assert got.owner == "parent-2"
    assert got.fencing_token == 2


def test_multiprocess_quota_atomicity_under_contention(tmp_path: Path) -> None:
    # Tables are created by the parent before any child starts, so children
    # only read the schema (no concurrent CREATE races).
    parent = make_sql_quota_store(tmp_path)
    limit, attempts, workers = 12, 5, 4

    procs = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                textwrap.dedent(_CHILD_QUOTA_RESERVE),
                str(tmp_path),
                str(attempts),
                str(limit),
            ],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(workers)
    ]
    codes = [p.wait(timeout=CHILD_TIMEOUT_SECONDS) for p in procs]
    assert all(c >= QUOTA_BASE for c in codes), (
        f"quota child failed: exit codes {codes}"
    )
    admitted_total = sum(c - QUOTA_BASE for c in codes)
    # The limit is enforced exactly once across processes: 4x5 attempts,
    # but only `limit` reservations may ever be admitted.
    assert admitted_total == limit, f"admitted {admitted_total}, expected {limit}"

    final = parent.read_plans_today("t-mp", datetime(2026, 3, 1, tzinfo=UTC), timedelta(days=1))
    assert final == limit


def test_quota_service_over_sql_store(tmp_path: Path) -> None:
    store = make_sql_quota_store(tmp_path)
    service = TenantQuotaService(counter_store=store)
    service.register_policy(TenantQuotaPolicy(tenant_id="t1", max_plans_per_day=1))

    assert service.begin_plan_creation("t1", 1).admitted is True
    assert service.begin_plan_creation("t1", 1).admitted is False
    # The injected SQL store is the counter backend: raw contract reads agree.
    assert store.read_plans_today("t1", datetime.now(UTC), timedelta(days=1)) == 1


def test_build_lease_store_selector(monkeypatch: pytest.MonkeyPatch) -> None:
    # Default (selector unset): in-memory via the process-global singleton.
    monkeypatch.delenv("INTERLOCK_LEASE_BACKEND", raising=False)
    assert isinstance(build_plan_lease_store(), InMemoryPlanLeaseStore)

    # Opt-in sql: the shared plan_leases backend (construction only here —
    # no connection is opened until a store method runs).
    monkeypatch.setenv("INTERLOCK_LEASE_BACKEND", "sql")
    assert isinstance(build_plan_lease_store(), SQLPlanLeaseStore)

    # The runbook's redis value fails loudly (needs authorized infra, G-3);
    # it is never silently degraded to a local backend.
    monkeypatch.setenv("INTERLOCK_LEASE_BACKEND", "redis")
    with pytest.raises(ValueError, match="INTERLOCK_LEASE_BACKEND"):
        build_plan_lease_store()


def test_build_quota_store_selector(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INTERLOCK_QUOTA_BACKEND", raising=False)
    assert isinstance(build_quota_counter_store(), InProcessQuotaCounterStore)

    monkeypatch.setenv("INTERLOCK_QUOTA_BACKEND", "sql")
    assert isinstance(build_quota_counter_store(), SQLQuotaCounterStore)

    monkeypatch.setenv("INTERLOCK_QUOTA_BACKEND", "redis")
    with pytest.raises(ValueError, match="INTERLOCK_QUOTA_BACKEND"):
        build_quota_counter_store()
