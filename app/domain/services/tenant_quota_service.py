"""Tenant quota enforcement for recovery operations (Interlock V5).

Quotas are opt-in per tenant: a tenant without a registered policy is
unlimited, so existing installations keep their current behaviour exactly.
Policies are registered programmatically; an administration API for policy
management is tracked as a production gap (see
``INTERLOCK_V5_PRODUCTION_GAP_MATRIX.md``).

Counter state lives behind the ``QuotaCounterStore`` backend contract.  The
default implementation (``InProcessQuotaCounterStore``) is process-local;
multi-instance deployments must inject a shared backend (Redis/Postgres) that
honours the same atomicity contract — the in-process store is the executable
specification, and a distributed implementation is tracked as an
external-validation gap.  All admission decisions remain atomic
check-then-reserve operations (window roll, limit check, and increment happen
in one indivisible store step), so concurrent submissions cannot overshoot a
limit.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any, Protocol, runtime_checkable

_DAY_WINDOW = timedelta(days=1)


class QuotaExceededError(ValueError):
    """Raised when a recovery operation would exceed the tenant's quota."""


@dataclass(frozen=True)
class TenantQuotaPolicy:
    """Recovery-operation limits for one tenant (``None`` = unlimited)."""

    tenant_id: str
    max_plans_per_day: int | None = None
    max_actions_per_plan: int | None = None
    max_concurrent_compensations: int | None = None

    def __post_init__(self) -> None:
        for name in (
            "max_plans_per_day",
            "max_actions_per_plan",
            "max_concurrent_compensations",
        ):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be >= 0 or None, got {value!r}")


@dataclass(frozen=True)
class QuotaDecision:
    """Admission decision for a quota-checked operation."""

    admitted: bool
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def allow(cls, **details: Any) -> QuotaDecision:
        return cls(admitted=True, details=details)

    @classmethod
    def deny(cls, reason: str, **details: Any) -> QuotaDecision:
        return cls(admitted=False, reason=reason, details=details)


@dataclass(frozen=True)
class QuotaUsageSnapshot:
    """Point-in-time counter values for one tenant."""

    plans_today: int
    day_window_start: datetime
    active_compensations: int


@runtime_checkable
class QuotaCounterStore(Protocol):
    """Backend contract for tenant quota counters.

    Atomicity is the contract: every reserve operation must roll the daily
    window, check its limit, and increment in one indivisible step *per
    tenant*.  A distributed implementation (Redis ``INCR``/``SET NX``,
    Postgres ``INSERT ... ON CONFLICT``) must reproduce the in-process
    semantics exactly — ``InProcessQuotaCounterStore`` is the executable
    specification and the shared contract tests in
    ``tests/unit/test_tenant_quota_service.py`` must pass unchanged against
    any backend before it may be used in production.
    """

    def try_reserve_plan(
        self,
        tenant_id: str,
        now: datetime,
        window: timedelta,
        limit: int | None,
    ) -> tuple[bool, int]:
        """Atomically roll the window, then reserve one daily plan slot.

        ``limit=None`` admits unconditionally (counters are still tracked).
        Returns ``(admitted, plans_today)`` where the count is the current
        value; a reservation increments only when admitted.
        """

    def read_plans_today(
        self, tenant_id: str, now: datetime, window: timedelta
    ) -> int:
        """Return the daily plan count after rolling the window (no reserve)."""

    def try_reserve_compensation(
        self, tenant_id: str, limit: int | None
    ) -> tuple[bool, int]:
        """Atomically reserve one concurrent-compensation slot.

        ``limit=None`` admits unconditionally.  Returns
        ``(admitted, active_compensations)``; a reservation increments only
        when admitted.
        """

    def release_compensation(self, tenant_id: str) -> int:
        """Release one compensation slot (floored at zero).  Returns the count."""

    def snapshot(
        self, tenant_id: str, now: datetime, window: timedelta
    ) -> QuotaUsageSnapshot:
        """Point-in-time counters after rolling the daily window."""


@dataclass
class _TenantUsage:
    plans_today: int = 0
    day_window_start: datetime = field(default_factory=lambda: datetime.now(UTC))
    active_compensations: int = 0


class InProcessQuotaCounterStore:
    """In-process implementation of the quota counter contract.

    Also the reference semantics for distributed backends: every operation is
    atomic per tenant under one lock, the daily window rolls before any plan
    decision, and compensation counts never drop below zero.
    """

    def __init__(self) -> None:
        self._usage: dict[str, _TenantUsage] = {}
        self._lock = Lock()

    def _rolled(
        self, tenant_id: str, now: datetime, window: timedelta
    ) -> _TenantUsage:
        """Return the tenant's usage, rolling the daily window when elapsed."""
        usage = self._usage.get(tenant_id)
        if usage is None:
            usage = _TenantUsage(day_window_start=now)
            self._usage[tenant_id] = usage
        elif now - usage.day_window_start >= window:
            usage.plans_today = 0
            usage.day_window_start = now
        return usage

    def try_reserve_plan(
        self,
        tenant_id: str,
        now: datetime,
        window: timedelta,
        limit: int | None,
    ) -> tuple[bool, int]:
        with self._lock:
            usage = self._rolled(tenant_id, now, window)
            if limit is not None and usage.plans_today >= limit:
                return False, usage.plans_today
            usage.plans_today += 1
            return True, usage.plans_today

    def read_plans_today(
        self, tenant_id: str, now: datetime, window: timedelta
    ) -> int:
        with self._lock:
            return self._rolled(tenant_id, now, window).plans_today

    def try_reserve_compensation(
        self, tenant_id: str, limit: int | None
    ) -> tuple[bool, int]:
        with self._lock:
            usage = self._usage.setdefault(tenant_id, _TenantUsage())
            if limit is not None and usage.active_compensations >= limit:
                return False, usage.active_compensations
            usage.active_compensations += 1
            return True, usage.active_compensations

    def release_compensation(self, tenant_id: str) -> int:
        with self._lock:
            usage = self._usage.setdefault(tenant_id, _TenantUsage())
            usage.active_compensations = max(0, usage.active_compensations - 1)
            return usage.active_compensations

    def snapshot(
        self, tenant_id: str, now: datetime, window: timedelta
    ) -> QuotaUsageSnapshot:
        with self._lock:
            usage = self._rolled(tenant_id, now, window)
            return QuotaUsageSnapshot(
                plans_today=usage.plans_today,
                day_window_start=usage.day_window_start,
                active_compensations=usage.active_compensations,
            )


class TenantQuotaService:
    """Policy-driven recovery quotas with atomic check-and-reserve.

    Policies are process-local (admin API is a tracked gap); counters live in
    the injected ``QuotaCounterStore`` (in-process by default).  Two service
    instances sharing one counter store share one quota domain, which is how
    a distributed backend will be wired in multi-instance deployments.
    """

    def __init__(
        self,
        clock: Callable[[], datetime] | None = None,
        *,
        counter_store: QuotaCounterStore | None = None,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._policies: dict[str, TenantQuotaPolicy] = {}
        self._policy_lock = Lock()
        store: QuotaCounterStore = counter_store or InProcessQuotaCounterStore()
        if not isinstance(store, QuotaCounterStore):
            msg = f"{type(store).__name__} does not implement the QuotaCounterStore contract"
            raise TypeError(msg)
        self._store = store

    # ------------------------------------------------------------------
    # Policy management
    # ------------------------------------------------------------------

    def register_policy(self, policy: TenantQuotaPolicy) -> None:
        """Register (or replace) the quota policy for a tenant."""
        with self._policy_lock:
            self._policies[policy.tenant_id] = policy

    def revoke_policy(self, tenant_id: str) -> bool:
        """Remove the policy for a tenant (back to unlimited)."""
        with self._policy_lock:
            return self._policies.pop(tenant_id, None) is not None

    def get_policy(self, tenant_id: str) -> TenantQuotaPolicy | None:
        with self._policy_lock:
            return self._policies.get(tenant_id)

    # ------------------------------------------------------------------
    # Usage accounting
    # ------------------------------------------------------------------

    def usage_snapshot(self, tenant_id: str) -> dict[str, Any]:
        """Point-in-time usage counters for a tenant (observability/testing)."""
        with self._policy_lock:
            policy = self._policies.get(tenant_id)
        snap = self._store.snapshot(tenant_id, self._clock(), _DAY_WINDOW)
        return {
            "tenant_id": tenant_id,
            "policy_registered": policy is not None,
            "plans_today": snap.plans_today,
            "active_compensations": snap.active_compensations,
            "day_window_start": snap.day_window_start.isoformat(),
        }

    # ------------------------------------------------------------------
    # Admission control (atomic check-and-reserve in the counter store)
    # ------------------------------------------------------------------

    def _plan_denials(
        self, policy: TenantQuotaPolicy, action_count: int
    ) -> QuotaDecision | None:
        """Counter-free per-plan denial, evaluated before any reservation."""
        if (
            policy.max_actions_per_plan is not None
            and action_count > policy.max_actions_per_plan
        ):
            return QuotaDecision.deny(
                "Recovery plan exceeds the per-plan action limit",
                limit=policy.max_actions_per_plan,
                requested=action_count,
            )
        return None

    def check_plan_creation(self, tenant_id: str, action_count: int) -> QuotaDecision:
        """Dry-run admission for plan creation (no reservation)."""
        with self._policy_lock:
            policy = self._policies.get(tenant_id)
        if policy is None:
            return QuotaDecision.allow(policy_registered=False, action_count=action_count)
        denial = self._plan_denials(policy, action_count)
        if denial is not None:
            return denial
        used = self._store.read_plans_today(tenant_id, self._clock(), _DAY_WINDOW)
        if (
            policy.max_plans_per_day is not None
            and used >= policy.max_plans_per_day
        ):
            return QuotaDecision.deny(
                "Daily recovery plan quota exhausted",
                limit=policy.max_plans_per_day,
                used=used,
            )
        return QuotaDecision.allow(
            policy_registered=True,
            action_count=action_count,
            plans_today=used,
        )

    def begin_plan_creation(self, tenant_id: str, action_count: int) -> QuotaDecision:
        """Atomically check and reserve one daily plan slot."""
        with self._policy_lock:
            policy = self._policies.get(tenant_id)
        if policy is None:
            # Unlimited, but still track the counter for observability.
            self._store.try_reserve_plan(tenant_id, self._clock(), _DAY_WINDOW, None)
            return QuotaDecision.allow(policy_registered=False, action_count=action_count)
        denial = self._plan_denials(policy, action_count)
        if denial is not None:
            return denial
        admitted, used = self._store.try_reserve_plan(
            tenant_id, self._clock(), _DAY_WINDOW, policy.max_plans_per_day
        )
        if not admitted:
            return QuotaDecision.deny(
                "Daily recovery plan quota exhausted",
                limit=policy.max_plans_per_day,
                used=used,
            )
        return QuotaDecision.allow(
            policy_registered=True,
            action_count=action_count,
            plans_today=used,
        )

    def begin_compensation(self, tenant_id: str) -> QuotaDecision:
        """Atomically check and reserve one concurrent-compensation slot."""
        with self._policy_lock:
            policy = self._policies.get(tenant_id)
        limit = policy.max_concurrent_compensations if policy else None
        admitted, active = self._store.try_reserve_compensation(tenant_id, limit)
        if not admitted:
            return QuotaDecision.deny(
                "Concurrent recovery compensation quota exhausted",
                limit=limit,
                active=active,
            )
        return QuotaDecision.allow(
            policy_registered=policy is not None,
            active_compensations=active,
        )

    def end_compensation(self, tenant_id: str) -> None:
        """Release one concurrent-compensation slot."""
        self._store.release_compensation(tenant_id)
