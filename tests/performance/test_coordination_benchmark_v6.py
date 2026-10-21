"""INTERLOCK V6 — WP-11: coordination benchmarks v2.

Mission requirement: recovery performance within expected operating limits,
with reproducible numbers and budgets that are justified by measurement
rather than assertion.

Scope (the coordination dimensions V5 never measured):
* lease-contention burst — N concurrent ``try_acquire`` calls on one plan;
* lease churn — acquire→renew→release cycle cost at step boundaries;
* concurrent-tenant throughput — T tenants executing durable plans at the
  same time, with per-plan latency percentiles.

Hardware (measured 2026-10-15, the machine these budgets are calibrated on):
* CPU: Intel(R) Core(TM) i5-10310U CPU @ 1.70GHz (8 logical cores)
* RAM: 15.6 GB
* OS:  Microsoft Windows 11 Pro

V5 baselines (unchanged; still enforced by
``tests/performance/test_recovery_adapter_benchmark.py``):
* orchestrator 10-step plan create+execute p95 1.04 ms (budget 10 ms);
* env capture p95 0.124 ms, env compensate p95 0.020 ms, drift p95 0.010 ms.

Budgets here are calibrated at ~5x the measured p95 of each scenario with a
5 ms noise floor (burst) so single-loaded CI machines never flake; measured
values are recorded in each test docstring and in the V6 baseline doc §8.
"""

from __future__ import annotations

import asyncio
import statistics
import time

from app.domain.entities.causal_state_types import DurableExecutionStep
from app.domain.entities.protected_action import ProtectedAction
from app.domain.entities.surgical_recovery_types import (
    AdapterCapability,
    CompensationType,
    RecoveryAdapterType,
    RecoveryEvidence,
    Reversibility,
)
from app.domain.repositories.causal_state_repositories import enforce_write_fence
from app.domain.services.distributed_recovery_orchestrator import (
    DistributedRecoveryOrchestrator,
    InMemoryPlanLeaseStore,
)
from app.infrastructure.recovery.mock_adapter import MockRecoveryAdapter


def _act(tenant: str, action_id: str) -> ProtectedAction:
    return ProtectedAction(
        action_id=action_id,
        tenant_id=tenant,
        actor_user_id=None,
        agent_id="bench-agent",
        authority_grant_id=None,
        tool="database",
        resource=f"record:{action_id}",
        action_type="insert",
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
        before_state_ref=f"state:before:{action_id}",
    )


def _ev(tenant: str, action_id: str) -> RecoveryEvidence:
    return RecoveryEvidence(
        evidence_id=f"ev-{action_id}",
        action_id=action_id,
        tenant_id=tenant,
        agent_id="bench-agent",
        authority_grant_id=None,
        parent_action_id=None,
        root_action_id=action_id,
        correlation_id="corr-bench",
        incident_id="inc-bench",
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

    async def get_by_action_id(self, tenant_id: str, action_id: str):
        return self._by_action.get((tenant_id, action_id))


class _ExecutionRepo:
    def __init__(self) -> None:
        self._steps: dict[str, DurableExecutionStep] = {}
        self._fences: dict[str, int] = {}

    async def save(self, step, expected_fencing_token=None):  # type: ignore[no-untyped-def]
        enforce_write_fence(
            self._fences.get(step.step_id, 0), expected_fencing_token, step.step_id
        )
        if expected_fencing_token is not None:
            self._fences[step.step_id] = expected_fencing_token
        self._steps[step.step_id] = step
        return step

    async def list_by_plan(self, tenant_id, plan_id, limit=500, offset=0):  # type: ignore[no-untyped-def]
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


def _pct(samples_ms: list[float]) -> tuple[float, float]:
    ordered = sorted(samples_ms)
    p50 = ordered[max(0, int(len(ordered) * 0.50) - 1)] if len(ordered) > 1 else ordered[0]
    p95 = ordered[max(0, int(len(ordered) * 0.95) - 1)]
    return p50, p95


async def test_lease_contention_burst_single_winner_budgeted_latency():
    """100 concurrent try_acquire on one plan → exactly one winner.

    Measured 2026-10-15 (hardware above): p50 0.0033ms, p95 0.0048ms over
    100 contenders. Budget 5.0ms is the noise floor (5x measured = 0.024ms
    sits below the floor, so the floor governs).
    """
    store = InMemoryPlanLeaseStore()
    contenders = 100
    latencies_ms: list[float] = []
    won: list[bool] = []

    async def contend(i: int) -> None:
        start = time.perf_counter()
        lease = await store.try_acquire("plan-bench", f"worker-{i % 8}", 30)
        latencies_ms.append((time.perf_counter() - start) * 1000)
        won.append(lease is not None)

    await asyncio.gather(*(contend(i) for i in range(contenders)))

    assert sum(won) == 1, "burst contention must elect exactly one executor"
    p50, p95 = _pct(latencies_ms)
    print(f"[wp11] lease burst p50={p50:.4f}ms p95={p95:.4f}ms n={contenders}")
    assert p95 <= 5.0, f"lease burst p95 {p95:.3f}ms exceeds 5ms noise floor"


async def test_lease_renew_release_churn_latency_budget():
    """Acquire→renew→release churn p95 budget (200 cycles after warm-up).

    Measured 2026-10-15: p50 0.0246ms, p95 0.0265ms (n=200). Budget 5.0ms
    is the noise floor (5x measured = 0.13ms sits below the floor).
    """
    store = InMemoryPlanLeaseStore()

    async def cycle(i: int) -> None:
        lease = await store.try_acquire("plan-churn", "churn-worker", 30)
        assert lease is not None
        renewed = await store.renew("plan-churn", "churn-worker", 30)
        assert renewed is not None
        await store.release("plan-churn", "churn-worker")

    for i in range(5):  # warm-up
        await cycle(i)
    samples: list[float] = []
    for i in range(200):
        start = time.perf_counter()
        await cycle(i)
        samples.append((time.perf_counter() - start) * 1000)
    _p50, p95 = _pct(samples)
    print(f"[wp11] lease churn p50={_p50:.4f}ms p95={p95:.4f}ms n={len(samples)}")
    assert p95 <= 5.0, f"lease churn p95 {p95:.3f}ms exceeds 5ms noise floor"


async def test_concurrent_tenant_throughput_percentiles_budget():
    """8 tenants × 3-step durable plans executed concurrently.

    All plans must complete; per-plan latency percentiles and aggregate
    throughput are recorded. Measured 2026-10-15: p50 2.52ms, p95 2.84ms
    per plan; throughput 1601.8 plans/s (wall 5.0ms for 8 concurrent
    plans). Budget p95 ≤ 50ms (~17x measured) and throughput ≥ 10 plans/s
    (~160x headroom) so a loaded CI machine never flakes.
    """
    tenants = 8
    per_plan_ms: list[float] = []

    async def run_tenant(t: int) -> None:
        tenant = f"bench-tenant-{t}"
        actions = [_act(tenant, f"t{t}-a{i}") for i in range(3)]
        evidence = [_ev(tenant, f"t{t}-a{i}") for i in range(3)]
        orch = DistributedRecoveryOrchestrator(
            _EvidenceRepo(evidence),
            _ExecutionRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )
        await orch.create_durable_plan(
            tenant, f"plan-{t}", actions, [a.action_id for a in actions]
        )
        start = time.perf_counter()
        result = await orch.execute_durable_plan(tenant, f"plan-{t}")
        per_plan_ms.append((time.perf_counter() - start) * 1000)
        assert result["status"] == "completed"
        assert result["verification_status"] != "executed_and_verified"

    wall_start = time.perf_counter()
    await asyncio.gather(*(run_tenant(t) for t in range(tenants)))
    wall_seconds = time.perf_counter() - wall_start

    p50, p95 = _pct(per_plan_ms)
    throughput = tenants / wall_seconds
    print(
        f"[wp11] concurrent-tenant p50={p50:.3f}ms p95={p95:.3f}ms "
        f"throughput={throughput:.1f} plans/s wall={wall_seconds * 1000:.1f}ms"
    )
    assert p95 <= 50.0, f"concurrent-tenant plan p95 {p95:.1f}ms exceeds budget 50ms"
    assert throughput >= 10.0, f"throughput {throughput:.1f} plans/s below floor 10/s"
    # Record-friendly assertion message content is surfaced in §8 evidence
    # from the benchmark log; keep the assertion set stable.
    assert statistics.fmean(per_plan_ms) > 0
