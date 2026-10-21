"""Interlock V5 — tenant quota service tests.

Covers opt-in policy semantics (unlimited without a policy), atomic
check-and-reserve admission, daily window rollover, per-plan action caps,
concurrent-compensation slots, tenant isolation, and the
``RecoveryPlanningService`` enforcement hook.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.entities.protected_action import ProtectedAction
from app.domain.entities.recovery_plan import RecoveryPlan
from app.domain.services.recovery_planning_service import RecoveryPlanningService
from app.domain.services.tenant_quota_service import (
    InProcessQuotaCounterStore,
    QuotaDecision,
    QuotaExceededError,
    TenantQuotaPolicy,
    TenantQuotaService,
)
from tests.unit.coordination_store_factories import make_sql_quota_store


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 3, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, hours: float) -> None:
        self.now += timedelta(hours=hours)


def test_policy_rejects_negative_limits():
    with pytest.raises(ValueError, match="max_plans_per_day"):
        TenantQuotaPolicy(tenant_id="t1", max_plans_per_day=-1)
    with pytest.raises(ValueError, match="max_actions_per_plan"):
        TenantQuotaPolicy(tenant_id="t1", max_actions_per_plan=-5)


async def test_unlimited_without_registered_policy():
    service = TenantQuotaService()

    assert service.check_plan_creation("t1", 10_000).admitted is True
    assert service.begin_plan_creation("t1", 10_000).admitted is True
    for _ in range(50):
        assert service.begin_compensation("t1").admitted is True
    service.end_compensation("t1")


async def test_daily_plan_quota_enforced_and_rolls_over():
    clock = _Clock()
    service = TenantQuotaService(clock=clock)
    service.register_policy(
        TenantQuotaPolicy(tenant_id="t1", max_plans_per_day=2)
    )

    assert service.begin_plan_creation("t1", 1).admitted is True
    assert service.begin_plan_creation("t1", 1).admitted is True

    denied = service.begin_plan_creation("t1", 1)
    assert denied.admitted is False
    assert "quota exhausted" in denied.reason.lower()

    # Dry-run check never reserves.
    assert service.check_plan_creation("t1", 1).admitted is False

    # Next day the window rolls over.
    clock.advance(25)
    assert service.begin_plan_creation("t1", 1).admitted is True
    snapshot = service.usage_snapshot("t1")
    assert snapshot["plans_today"] == 1


async def test_actions_per_plan_cap():
    service = TenantQuotaService()
    service.register_policy(
        TenantQuotaPolicy(tenant_id="t1", max_actions_per_plan=3)
    )

    assert service.begin_plan_creation("t1", 3).admitted is True
    denied = service.begin_plan_creation("t1", 4)
    assert denied.admitted is False
    assert denied.details["limit"] == 3
    assert denied.details["requested"] == 4


async def test_concurrent_compensation_slots():
    service = TenantQuotaService()
    service.register_policy(
        TenantQuotaPolicy(tenant_id="t1", max_concurrent_compensations=1)
    )

    assert service.begin_compensation("t1").admitted is True
    denied = service.begin_compensation("t1")
    assert denied.admitted is False
    assert "concurrent" in denied.reason.lower()

    service.end_compensation("t1")
    assert service.begin_compensation("t1").admitted is True
    assert service.usage_snapshot("t1")["active_compensations"] == 1

    # Releasing below zero clamps at zero.
    service.end_compensation("t1")
    service.end_compensation("t1")
    service.end_compensation("t1")
    assert service.usage_snapshot("t1")["active_compensations"] == 0


async def test_tenant_isolation_of_policies_and_counters():
    service = TenantQuotaService()
    service.register_policy(TenantQuotaPolicy(tenant_id="t1", max_plans_per_day=1))

    assert service.begin_plan_creation("t1", 1).admitted is True
    assert service.begin_plan_creation("t1", 1).admitted is False

    # t2 has no policy: unaffected by t1's exhaustion.
    assert service.begin_plan_creation("t2", 1).admitted is True
    assert service.usage_snapshot("t2")["plans_today"] == 1
    assert service.usage_snapshot("t1")["plans_today"] == 1


async def test_revoke_policy_restores_unlimited():
    service = TenantQuotaService()
    policy = TenantQuotaPolicy(tenant_id="t1", max_plans_per_day=1)
    service.register_policy(policy)
    assert service.begin_plan_creation("t1", 1).admitted is True
    assert service.begin_plan_creation("t1", 1).admitted is False

    assert service.revoke_policy("t1") is True
    assert service.get_policy("t1") is None
    assert service.begin_plan_creation("t1", 1).admitted is True
    assert service.revoke_policy("t1") is False


async def test_concurrent_admission_never_overshoots():
    """Atomic check-and-reserve under real thread concurrency."""
    service = TenantQuotaService()
    service.register_policy(
        TenantQuotaPolicy(tenant_id="t1", max_plans_per_day=5)
    )

    admitted: list[bool] = []
    barrier = threading.Barrier(16)

    def worker() -> None:
        barrier.wait()
        decision = service.begin_plan_creation("t1", 1)
        admitted.append(decision.admitted)

    threads = [threading.Thread(target=worker) for _ in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert admitted.count(True) == 5
    assert admitted.count(False) == 11
    assert service.usage_snapshot("t1")["plans_today"] == 5


# ---------------------------------------------------------------------------
# RecoveryPlanningService enforcement hook
# ---------------------------------------------------------------------------


class _ActionRepo:
    def __init__(self, action: ProtectedAction) -> None:
        self._action = action

    async def get_by_action_id(self, tenant_id: str, action_id: str):
        if self._action.action_id == action_id and self._action.tenant_id == tenant_id:
            return self._action
        return None

    async def list_descendants(self, tenant_id: str, action_id: str, limit=1000, offset=0):
        return [], 0


class _PlanRepo:
    def __init__(self) -> None:
        self.saved: list[RecoveryPlan] = []

    async def save(self, plan: RecoveryPlan) -> RecoveryPlan:
        self.saved.append(plan)
        return plan


def _incident_action() -> ProtectedAction:
    return ProtectedAction(
        action_id="inc-1",
        tenant_id="t1",
        actor_user_id=None,
        agent_id="agent-1",
        authority_grant_id=None,
        tool="database",
        resource="db:public.users",
        action_type="insert",
    )


async def test_planning_service_quota_hook_denies_plan_creation():
    quota = TenantQuotaService()
    quota.register_policy(TenantQuotaPolicy(tenant_id="t1", max_actions_per_plan=0))
    action_repo = _ActionRepo(_incident_action())
    plan_repo = _PlanRepo()
    service = RecoveryPlanningService(
        action_repo, plan_repo, adapters=[], quota_service=quota
    )

    with pytest.raises(QuotaExceededError, match="denied"):
        await service.create_plan("t1", "inc-1")
    assert plan_repo.saved == []


async def test_planning_service_without_quota_is_unchanged():
    action_repo = _ActionRepo(_incident_action())
    plan_repo = _PlanRepo()
    service = RecoveryPlanningService(action_repo, plan_repo, adapters=[])

    plan = await service.create_plan("t1", "inc-1")
    assert plan.plan_id
    assert len(plan_repo.saved) == 1


async def test_planning_service_daily_quota_blocks_after_limit():
    quota = TenantQuotaService()
    quota.register_policy(TenantQuotaPolicy(tenant_id="t1", max_plans_per_day=1))
    action_repo = _ActionRepo(_incident_action())
    plan_repo = _PlanRepo()
    service = RecoveryPlanningService(
        action_repo, plan_repo, adapters=[], quota_service=quota
    )

    await service.create_plan("t1", "inc-1")
    with pytest.raises(QuotaExceededError, match="quota"):
        await service.create_plan("t1", "inc-1")
    assert len(plan_repo.saved) == 1


def test_quota_decision_factories():
    allow = QuotaDecision.allow(x=1)
    assert allow.admitted is True
    assert allow.details["x"] == 1

    deny = QuotaDecision.deny("nope", limit=2)
    assert deny.admitted is False
    assert deny.reason == "nope"
    assert deny.details["limit"] == 2


# ---------------------------------------------------------------------------
# QuotaCounterStore backend contract — the executable specification any
# distributed counter backend (Redis/Postgres, G-2) must satisfy unchanged.
#
# V6 WP-3: ``quota_store`` parametrizes the SAME assertions over the
# in-process backend and the SQL backend; no assertion below differs
# between backends.
# ---------------------------------------------------------------------------

_T0 = datetime(2026, 3, 1, tzinfo=UTC)
_WINDOW = timedelta(days=1)


@pytest.fixture(params=["memory", "sql"])
def quota_store(request, tmp_path):
    if request.param == "memory":
        return InProcessQuotaCounterStore()
    return make_sql_quota_store(tmp_path)


def test_counter_store_contract_reserve_honours_limit(quota_store):
    store = quota_store

    assert store.try_reserve_plan("t1", _T0, _WINDOW, 2) == (True, 1)
    assert store.try_reserve_plan("t1", _T0, _WINDOW, 2) == (True, 2)
    # Denied reservations never inflate the counter.
    assert store.try_reserve_plan("t1", _T0, _WINDOW, 2) == (False, 2)
    assert store.read_plans_today("t1", _T0, _WINDOW) == 2


def test_counter_store_contract_window_roll(quota_store):
    store = quota_store

    assert store.try_reserve_plan("t1", _T0, _WINDOW, 1) == (True, 1)
    later = _T0 + timedelta(hours=25)
    assert store.read_plans_today("t1", later, _WINDOW) == 0
    assert store.try_reserve_plan("t1", later, _WINDOW, 1) == (True, 1)


def test_counter_store_contract_unlimited_and_compensation_slots(quota_store):
    store = quota_store

    # limit=None admits unconditionally but keeps counting (observability).
    assert store.try_reserve_plan("t1", _T0, _WINDOW, None) == (True, 1)
    assert store.try_reserve_plan("t1", _T0, _WINDOW, None) == (True, 2)

    assert store.try_reserve_compensation("t1", 1) == (True, 1)
    # Denied reservation leaves the counter untouched.
    assert store.try_reserve_compensation("t1", 1) == (False, 1)
    assert store.release_compensation("t1") == 0
    # Releasing below zero clamps at zero.
    assert store.release_compensation("t1") == 0


def test_counter_store_contract_snapshot(quota_store):
    store = quota_store

    store.try_reserve_plan("t1", _T0, _WINDOW, None)
    store.try_reserve_compensation("t1", None)
    snap = store.snapshot("t1", _T0, _WINDOW)
    assert snap.plans_today == 1
    assert snap.active_compensations == 1
    assert snap.day_window_start == _T0


def test_service_accepts_injected_counter_store():
    store = InProcessQuotaCounterStore()
    service = TenantQuotaService(counter_store=store)
    service.register_policy(TenantQuotaPolicy(tenant_id="t1", max_plans_per_day=2))

    assert service.begin_plan_creation("t1", 1).admitted is True
    # The injected store is the counter backend: raw contract reads agree.
    assert store.read_plans_today("t1", datetime.now(UTC), _WINDOW) == 1


def test_services_sharing_one_store_share_quota_domain():
    """Two service instances over one counter store behave as one quota
    domain — the exact wiring a shared (Redis) backend uses across
    instances; policies stay per-instance until the admin API exists (G-2)."""
    store = InProcessQuotaCounterStore()
    svc_a = TenantQuotaService(counter_store=store)
    svc_b = TenantQuotaService(counter_store=store)
    for svc in (svc_a, svc_b):
        svc.register_policy(TenantQuotaPolicy(tenant_id="t1", max_plans_per_day=2))

    assert svc_a.begin_plan_creation("t1", 1).admitted is True
    assert svc_b.begin_plan_creation("t1", 1).admitted is True
    # Cross-instance limit honoured through the shared store.
    assert svc_b.begin_plan_creation("t1", 1).admitted is False


def test_service_rejects_non_contract_counter_store():
    with pytest.raises(TypeError, match="QuotaCounterStore"):
        TenantQuotaService(counter_store=object())
