"""Shared (cross-process) coordination stores (V6 WP-3).

SQLAlchemy implementations of the two coordination protocols:

- :class:`SQLPlanLeaseStore` — ``plan_leases`` rows; every transition is one
  conditional UPDATE (or a PK-guarded INSERT), so concurrent coordinators
  serialize at the database and the fencing token only ever increments.
- :class:`SQLQuotaCounterStore` — ``quota_counters`` rows; window roll,
  limit check, and increment are separate conditional statements that
  reproduce the in-process reference semantics exactly (executable
  specification: the shared contract tests in
  ``tests/unit/test_tenant_quota_service.py``).

Both are opt-in through the runbook §6/§7 selectors
``INTERLOCK_LEASE_BACKEND`` / ``INTERLOCK_QUOTA_BACKEND`` (default
``memory`` preserves today's single-process behaviour).  The runbook's
``redis`` value names a live external backend that requires authorized
infrastructure (G-3) and is rejected loudly rather than silently degraded.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.domain.services.distributed_recovery_orchestrator import (
    _RELEASED_AT,
    PlanLease,
    PlanLeaseStore,
    _default_lease_store,
)
from app.domain.services.tenant_quota_service import (
    InProcessQuotaCounterStore,
    QuotaCounterStore,
    QuotaUsageSnapshot,
)
from app.infrastructure.persistence.models.coordination_models import (
    PlanLeaseModel,
    QuotaCounterModel,
)

_BACKEND_ALLOWED = ("memory", "sql")


def _aware_utc(value: datetime) -> datetime:
    """SQLite round-trips naive UTC timestamps; restore the timezone info."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class SQLPlanLeaseStore:
    """``PlanLeaseStore`` backed by the shared ``plan_leases`` table.

    Semantics match :class:`InMemoryPlanLeaseStore` exactly: no reentrant
    acquisition, expiry takeover with a fencing token that never repeats,
    owner-only renew/release, released leases invisible to ``get``.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    async def try_acquire(
        self, plan_id: str, owner: str, ttl_seconds: float
    ) -> PlanLease | None:
        now = self._clock()
        expires_at = now + timedelta(seconds=ttl_seconds)
        session = self._session_factory()
        try:
            # Take over expired/released rows; the token increments inside the
            # same statement, so a late-arriving old executor stays identifiable.
            token = (
                session.execute(
                    update(PlanLeaseModel)
                    .where(
                        PlanLeaseModel.plan_id == plan_id,
                        PlanLeaseModel.expires_at <= now,
                    )
                    .values(
                        owner=owner,
                        fencing_token=PlanLeaseModel.fencing_token + 1,
                        acquired_at=now,
                        expires_at=expires_at,
                    )
                    .returning(PlanLeaseModel.fencing_token)
                    .execution_options(synchronize_session=False)
                )
                .scalars()
                .first()
            )
            if token is not None:
                session.commit()
                return PlanLease(
                    plan_id=plan_id,
                    owner=owner,
                    fencing_token=token,
                    acquired_at=now,
                    expires_at=expires_at,
                )
            # Nothing expired: either this plan never held a lease (fresh
            # acquire at token 1) or an unexpired lease is held elsewhere.
            try:
                session.execute(
                    insert(PlanLeaseModel).values(
                        plan_id=plan_id,
                        owner=owner,
                        fencing_token=1,
                        acquired_at=now,
                        expires_at=expires_at,
                    )
                )
                session.commit()
            except IntegrityError:
                session.rollback()
                return None
            return PlanLease(
                plan_id=plan_id,
                owner=owner,
                fencing_token=1,
                acquired_at=now,
                expires_at=expires_at,
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    async def renew(
        self, plan_id: str, owner: str, ttl_seconds: float
    ) -> PlanLease | None:
        now = self._clock()
        expires_at = now + timedelta(seconds=ttl_seconds)
        session = self._session_factory()
        try:
            row = (
                session.execute(
                    update(PlanLeaseModel)
                    .where(
                        PlanLeaseModel.plan_id == plan_id,
                        PlanLeaseModel.owner == owner,
                        PlanLeaseModel.expires_at > now,
                    )
                    .values(expires_at=expires_at)
                    .returning(
                        PlanLeaseModel.fencing_token,
                        PlanLeaseModel.acquired_at,
                    )
                    .execution_options(synchronize_session=False)
                )
                .first()
            )
            session.commit()
            if row is None:
                return None
            return PlanLease(
                plan_id=plan_id,
                owner=owner,
                fencing_token=row[0],
                acquired_at=_aware_utc(row[1]),
                expires_at=expires_at,
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    async def release(self, plan_id: str, owner: str) -> None:
        session = self._session_factory()
        try:
            # Owner-only no-op otherwise; the tombstone keeps the token monotonic.
            session.execute(
                update(PlanLeaseModel)
                .where(
                    PlanLeaseModel.plan_id == plan_id,
                    PlanLeaseModel.owner == owner,
                )
                .values(owner="", expires_at=_RELEASED_AT)
                .execution_options(synchronize_session=False)
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    async def get(self, plan_id: str) -> PlanLease | None:
        session = self._session_factory()
        try:
            model = session.execute(
                select(PlanLeaseModel).where(PlanLeaseModel.plan_id == plan_id)
            ).scalar_one_or_none()
            session.commit()
            if model is None or model.owner == "":
                return None
            return PlanLease(
                plan_id=model.plan_id,
                owner=model.owner,
                fencing_token=model.fencing_token,
                acquired_at=_aware_utc(model.acquired_at),
                expires_at=_aware_utc(model.expires_at),
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


class SQLQuotaCounterStore:
    """``QuotaCounterStore`` backed by the shared ``quota_counters`` table.

    Every counter decision is a single conditional UPDATE (admit only when
    the row is below its limit), so concurrent processes can never exceed a
    limit together; denied reservations never inflate counters.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def _ensure_row(
        self, session: Session, tenant_id: str, created_at: datetime
    ) -> None:
        try:
            session.execute(
                insert(QuotaCounterModel).values(
                    tenant_id=tenant_id,
                    plans_today=0,
                    day_window_start=created_at,
                    active_compensations=0,
                )
            )
            session.commit()
        except IntegrityError:
            # Row already exists (including a concurrent creator's) — fine.
            session.rollback()

    def _roll_window(
        self, session: Session, tenant_id: str, now: datetime, window: timedelta
    ) -> None:
        cutoff = now - window
        session.execute(
            update(QuotaCounterModel)
            .where(
                QuotaCounterModel.tenant_id == tenant_id,
                QuotaCounterModel.day_window_start <= cutoff,
            )
            .values(plans_today=0, day_window_start=now)
            .execution_options(synchronize_session=False)
        )
        session.commit()

    def _counter_row(self, session: Session, tenant_id: str) -> QuotaCounterModel:
        model = session.execute(
            select(QuotaCounterModel).where(QuotaCounterModel.tenant_id == tenant_id)
        ).scalar_one_or_none()
        if model is None:
            # Rows are never deleted; only a bug or DDL race gets here.
            raise RuntimeError(
                f"quota counter row for tenant {tenant_id!r} is missing"
            )
        return model

    def try_reserve_plan(
        self,
        tenant_id: str,
        now: datetime,
        window: timedelta,
        limit: int | None,
    ) -> tuple[bool, int]:
        session = self._session_factory()
        try:
            self._ensure_row(session, tenant_id, now)
            self._roll_window(session, tenant_id, now, window)
            stmt = update(QuotaCounterModel).where(
                QuotaCounterModel.tenant_id == tenant_id
            )
            if limit is not None:
                stmt = stmt.where(QuotaCounterModel.plans_today < limit)
            count = (
                session.execute(
                    stmt.values(plans_today=QuotaCounterModel.plans_today + 1)
                    .returning(QuotaCounterModel.plans_today)
                    .execution_options(synchronize_session=False)
                )
                .scalars()
                .first()
            )
            session.commit()
            if count is not None:
                return True, count
            # The conditional UPDATE matched nothing: at the limit (rows are
            # ensured above and never deleted).
            model = self._counter_row(session, tenant_id)
            session.commit()
            return False, model.plans_today
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def read_plans_today(
        self, tenant_id: str, now: datetime, window: timedelta
    ) -> int:
        session = self._session_factory()
        try:
            self._ensure_row(session, tenant_id, now)
            self._roll_window(session, tenant_id, now, window)
            model = self._counter_row(session, tenant_id)
            session.commit()
            return model.plans_today
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def try_reserve_compensation(
        self, tenant_id: str, limit: int | None
    ) -> tuple[bool, int]:
        session = self._session_factory()
        try:
            self._ensure_row(session, tenant_id, datetime.now(UTC))
            stmt = update(QuotaCounterModel).where(
                QuotaCounterModel.tenant_id == tenant_id
            )
            if limit is not None:
                stmt = stmt.where(
                    QuotaCounterModel.active_compensations < limit
                )
            count = (
                session.execute(
                    stmt.values(
                        active_compensations=QuotaCounterModel.active_compensations
                        + 1
                    )
                    .returning(QuotaCounterModel.active_compensations)
                    .execution_options(synchronize_session=False)
                )
                .scalars()
                .first()
            )
            session.commit()
            if count is not None:
                return True, count
            model = self._counter_row(session, tenant_id)
            session.commit()
            return False, model.active_compensations
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def release_compensation(self, tenant_id: str) -> int:
        session = self._session_factory()
        try:
            self._ensure_row(session, tenant_id, datetime.now(UTC))
            count = (
                session.execute(
                    update(QuotaCounterModel)
                    .where(QuotaCounterModel.tenant_id == tenant_id)
                    .values(
                        active_compensations=case(
                            (
                                QuotaCounterModel.active_compensations > 0,
                                QuotaCounterModel.active_compensations - 1,
                            ),
                            else_=0,
                        )
                    )
                    .returning(QuotaCounterModel.active_compensations)
                    .execution_options(synchronize_session=False)
                )
                .scalars()
                .first()
            )
            session.commit()
            if count is None:
                raise RuntimeError(
                    f"quota counter row for tenant {tenant_id!r} is missing"
                )
            return count
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def snapshot(
        self, tenant_id: str, now: datetime, window: timedelta
    ) -> QuotaUsageSnapshot:
        session = self._session_factory()
        try:
            self._ensure_row(session, tenant_id, now)
            self._roll_window(session, tenant_id, now, window)
            model = self._counter_row(session, tenant_id)
            session.commit()
            return QuotaUsageSnapshot(
                plans_today=model.plans_today,
                day_window_start=_aware_utc(model.day_window_start),
                active_compensations=model.active_compensations,
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def _backend_from_env(var: str) -> str:
    backend = os.getenv(var, "memory").strip().lower()
    if backend not in _BACKEND_ALLOWED:
        raise ValueError(
            f"Unsupported {var}={backend!r}; expected one of {_BACKEND_ALLOWED}. "
            "The runbook's 'redis' selector requires authorized external "
            "infrastructure (G-3) and is not silently degraded."
        )
    return backend


def build_plan_lease_store() -> PlanLeaseStore:
    """Select the plan-lease backend (runbook §6 selector; default memory)."""
    if _backend_from_env("INTERLOCK_LEASE_BACKEND") == "sql":
        from app.infrastructure.persistence.database import SessionLocal

        return SQLPlanLeaseStore(SessionLocal)
    # memory: the orchestrator's process-global singleton, so request-scoped
    # construction still shares one lease domain per process.
    return _default_lease_store()


def build_quota_counter_store() -> QuotaCounterStore:
    """Select the quota-counter backend (runbook §7 selector; default memory)."""
    if _backend_from_env("INTERLOCK_QUOTA_BACKEND") == "sql":
        from app.infrastructure.persistence.database import SessionLocal

        return SQLQuotaCounterStore(SessionLocal)
    return InProcessQuotaCounterStore()
