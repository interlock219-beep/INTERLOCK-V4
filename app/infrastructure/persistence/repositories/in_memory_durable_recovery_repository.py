from __future__ import annotations

import secrets
import threading
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from app.domain.entities.durable_recovery_types import (
    LeaseAcquisitionResult,
    OrphanRecord,
    PlanCoordinationState,
    ReconciliationRecord,
    RecoveryLease,
    WorkerRecord,
    WorkerState,
)
from app.domain.repositories.durable_recovery_repository import (
    RecoveryLeaseRepository,
    RecoveryReconciliationRepository,
    RecoveryWorkerRepository,
)

LeaseKey = tuple[str, str]
WorkerKey = tuple[str, str, str]
RecordKey = tuple[str, str, str]


class InMemoryDurableRecoveryRepository(
    RecoveryLeaseRepository,
    RecoveryWorkerRepository,
    RecoveryReconciliationRepository,
):
    """Thread-safe in-memory implementation of the durable recovery ports."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()
        self._leases: dict[LeaseKey, RecoveryLease] = {}
        self._fencing_tokens: dict[LeaseKey, int] = {}
        self._workers: dict[WorkerKey, WorkerRecord] = {}
        self._reconciliations: dict[RecordKey, ReconciliationRecord] = {}
        self._reconciliation_order: dict[RecordKey, int] = {}
        self._reconciliation_sequence = 0
        self._orphans: dict[RecordKey, OrphanRecord] = {}
        self._coordination_states: dict[LeaseKey, PlanCoordinationState] = {}

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _scope(tenant_id: str, plan_id: str) -> LeaseKey:
        return tenant_id, plan_id

    @staticmethod
    def _worker_key(tenant_id: str, plan_id: str, worker_id: str) -> WorkerKey:
        return tenant_id, plan_id, worker_id

    @staticmethod
    def _record_key(tenant_id: str, plan_id: str, record_id: str) -> RecordKey:
        return tenant_id, plan_id, record_id

    def _now(self) -> datetime:
        return self._as_utc(self._clock())

    @staticmethod
    def _validate_lease_ttl(ttl_seconds: int) -> None:
        if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or ttl_seconds < 0:
            raise ValueError("ttl_seconds must be a non-negative integer")

    @staticmethod
    def _validate_token(fencing_token: int, name: str = "fencing_token") -> None:
        if (
            not isinstance(fencing_token, int)
            or isinstance(fencing_token, bool)
            or fencing_token < 0
        ):
            raise ValueError(f"{name} must be a non-negative integer")

    @staticmethod
    def _copy_lease(lease: RecoveryLease) -> RecoveryLease:
        return replace(lease, lease_metadata=dict(lease.lease_metadata))

    @staticmethod
    def _copy_worker(worker: WorkerRecord) -> WorkerRecord:
        return replace(worker, worker_metadata=dict(worker.worker_metadata))

    @staticmethod
    def _copy_reconciliation(record: ReconciliationRecord) -> ReconciliationRecord:
        return replace(
            record,
            reconciled_at=InMemoryDurableRecoveryRepository._as_utc(record.reconciled_at),
            details=dict(record.details),
            reconciled_states=dict(record.reconciled_states),
        )

    @staticmethod
    def _copy_orphan(record: OrphanRecord) -> OrphanRecord:
        return replace(
            record,
            detected_at=InMemoryDurableRecoveryRepository._as_utc(record.detected_at),
            details=dict(record.details),
        )

    @staticmethod
    def _copy_coordination_state(state: PlanCoordinationState) -> PlanCoordinationState:
        completed_at = (
            InMemoryDurableRecoveryRepository._as_utc(state.completed_at)
            if state.completed_at is not None
            else None
        )
        return replace(
            state,
            started_at=InMemoryDurableRecoveryRepository._as_utc(state.started_at),
            completed_at=completed_at,
            stop_conditions=list(state.stop_conditions),
            coordination_metadata=dict(state.coordination_metadata),
        )

    def _set_fencing_token_locked(self, key: LeaseKey, fencing_token: int) -> None:
        self._leases.pop(key, None)
        self._fencing_tokens[key] = fencing_token
        state = self._coordination_states.get(key)
        if state is not None and state.fencing_token != fencing_token:
            self._coordination_states[key] = replace(state, fencing_token=fencing_token)

    def _advance_fencing_token_locked(self, key: LeaseKey, reason: str) -> int:
        fencing_token = self._fencing_tokens.get(key, 0) + 1
        self._set_fencing_token_locked(key, fencing_token)
        return fencing_token

    def _active_lease_locked(
        self,
        key: LeaseKey,
        now: datetime,
        *,
        remove_expired: bool = True,
    ) -> RecoveryLease | None:
        lease = self._leases.get(key)
        if lease is None:
            return None
        if lease.is_expired(now):
            if remove_expired:
                self._leases.pop(key, None)
            return None
        return lease

    @staticmethod
    def _lease_failure(
        reason: str,
        fencing_token: int,
        lease_id: str | None,
        evicted_worker_id: str | None = None,
    ) -> LeaseAcquisitionResult:
        return LeaseAcquisitionResult(
            acquired=False,
            lease=None,
            reason=reason,
            evicted_worker_id=evicted_worker_id,
            fencing_token=fencing_token,
            lease_id=lease_id,
        )

    async def acquire_lease(
        self,
        tenant_id: str,
        plan_id: str,
        worker_id: str,
        ttl_seconds: int = 60,
        expected_fencing_token: int | None = None,
        reason: str = "initial_acquisition",
    ) -> LeaseAcquisitionResult:
        self._validate_lease_ttl(ttl_seconds)
        if expected_fencing_token is not None:
            self._validate_token(expected_fencing_token, "expected_fencing_token")

        key = self._scope(tenant_id, plan_id)
        now = self._now()
        with self._lock:
            previous_lease = self._leases.get(key)
            evicted_worker_id = (
                previous_lease.worker_id
                if previous_lease is not None and previous_lease.is_expired(now)
                else None
            )
            lease = self._active_lease_locked(key, now)
            fencing_token = self._fencing_tokens.get(key, 0)
            if lease is not None:
                if (
                    expected_fencing_token is not None
                    and expected_fencing_token != lease.fencing_token
                ):
                    return self._lease_failure(
                        "expected_fencing_token_mismatch",
                        lease.fencing_token,
                        lease.lease_id,
                    )
                if lease.worker_id == worker_id:
                    return LeaseAcquisitionResult(
                        acquired=True,
                        lease=self._copy_lease(lease),
                        reason="already_acquired",
                        fencing_token=lease.fencing_token,
                        lease_id=lease.lease_id,
                    )
                return self._lease_failure(
                    "lease_already_held",
                    lease.fencing_token,
                    lease.lease_id,
                    lease.worker_id,
                )

            if expected_fencing_token is not None and expected_fencing_token != fencing_token:
                return self._lease_failure(
                    "expected_fencing_token_mismatch",
                    fencing_token,
                    None,
                )

            fencing_token = self._advance_fencing_token_locked(key, reason)
            lease_id = secrets.token_hex(16)
            lease = RecoveryLease(
                plan_id=plan_id,
                tenant_id=tenant_id,
                worker_id=worker_id,
                lease_id=lease_id,
                fencing_token=fencing_token,
                acquired_at=now,
                expires_at=now + timedelta(seconds=ttl_seconds),
                renewed_at=now,
                lease_ttl_seconds=ttl_seconds,
                lease_metadata={"reason": reason},
            )
            self._leases[key] = lease
            return LeaseAcquisitionResult(
                acquired=True,
                lease=self._copy_lease(lease),
                reason="lease_reclaimed" if evicted_worker_id is not None else "lease_acquired",
                evicted_worker_id=evicted_worker_id,
                fencing_token=fencing_token,
                lease_id=lease_id,
            )

    async def renew_lease(
        self,
        tenant_id: str,
        plan_id: str,
        lease_id: str,
        worker_id: str,
        ttl_seconds: int = 60,
    ) -> bool:
        self._validate_lease_ttl(ttl_seconds)
        key = self._scope(tenant_id, plan_id)
        now = self._now()
        with self._lock:
            lease = self._active_lease_locked(key, now)
            if lease is None or lease.lease_id != lease_id or lease.worker_id != worker_id:
                return False
            self._leases[key] = self._copy_lease(
                replace(
                    lease,
                    renewed_at=now,
                    expires_at=now + timedelta(seconds=ttl_seconds),
                    lease_ttl_seconds=ttl_seconds,
                )
            )
            return True

    async def release_lease(
        self,
        tenant_id: str,
        plan_id: str,
        lease_id: str,
        worker_id: str,
    ) -> bool:
        key = self._scope(tenant_id, plan_id)
        now = self._now()
        with self._lock:
            lease = self._active_lease_locked(key, now)
            if lease is None or lease.lease_id != lease_id or lease.worker_id != worker_id:
                return False
            self._leases.pop(key, None)
            return True

    async def get_active_lease(self, tenant_id: str, plan_id: str) -> RecoveryLease | None:
        key = self._scope(tenant_id, plan_id)
        now = self._now()
        with self._lock:
            lease = self._active_lease_locked(key, now, remove_expired=False)
            return self._copy_lease(lease) if lease is not None else None

    async def revoke_lease(self, tenant_id: str, plan_id: str, reason: str) -> bool:
        key = self._scope(tenant_id, plan_id)
        with self._lock:
            if key not in self._leases:
                return False
            self._leases.pop(key, None)
            self._advance_fencing_token_locked(key, reason)
            return True

    async def bump_fencing_token(self, tenant_id: str, plan_id: str, reason: str) -> int:
        key = self._scope(tenant_id, plan_id)
        with self._lock:
            return self._advance_fencing_token_locked(key, reason)

    async def get_fencing_token(self, tenant_id: str, plan_id: str) -> int:
        key = self._scope(tenant_id, plan_id)
        with self._lock:
            return self._fencing_tokens.get(key, 0)

    async def register_worker(
        self,
        tenant_id: str,
        plan_id: str,
        worker_id: str,
        fencing_token: int = 0,
        lease_id: str | None = None,
    ) -> WorkerRecord:
        self._validate_token(fencing_token)
        key = self._worker_key(tenant_id, plan_id, worker_id)
        now = self._now()
        with self._lock:
            existing = self._workers.get(key)
            if existing is None:
                worker = WorkerRecord(
                    plan_id=plan_id,
                    tenant_id=tenant_id,
                    worker_id=worker_id,
                    state=WorkerState.ACTIVE,
                    fencing_token=fencing_token,
                    lease_id=lease_id,
                    acquired_at=now,
                    last_heartbeat=now,
                )
                self._workers[key] = worker
                return self._copy_worker(worker)

            if (
                existing.fencing_token == fencing_token
                and existing.lease_id == lease_id
                and existing.state == WorkerState.ACTIVE
                and existing.last_error is None
            ):
                return self._copy_worker(existing)

            token = max(existing.fencing_token, fencing_token)
            worker = replace(
                existing,
                fencing_token=token,
                lease_id=lease_id if lease_id is not None else existing.lease_id,
                state=WorkerState.ACTIVE,
                last_heartbeat=now,
                last_error=None,
            )
            self._workers[key] = worker
            return self._copy_worker(worker)

    async def get_worker(self, tenant_id: str, plan_id: str, worker_id: str) -> WorkerRecord | None:
        key = self._worker_key(tenant_id, plan_id, worker_id)
        with self._lock:
            worker = self._workers.get(key)
            return self._copy_worker(worker) if worker is not None else None

    async def list_workers(self, tenant_id: str, plan_id: str) -> list[WorkerRecord]:
        prefix = (tenant_id, plan_id)
        with self._lock:
            workers = [
                self._copy_worker(worker)
                for key, worker in self._workers.items()
                if key[:2] == prefix
            ]
            workers.sort(key=lambda worker: worker.worker_id)
            return workers

    async def update_heartbeat(
        self,
        tenant_id: str,
        plan_id: str,
        worker_id: str,
        fencing_token: int,
        lease_id: str | None = None,
        now: datetime | None = None,
    ) -> WorkerRecord | None:
        self._validate_token(fencing_token)
        key = self._worker_key(tenant_id, plan_id, worker_id)
        heartbeat_at = self._as_utc(now) if now is not None else self._now()
        with self._lock:
            worker = self._workers.get(key)
            if worker is None or fencing_token < worker.fencing_token:
                return None
            active_lease = self._leases.get(self._scope(tenant_id, plan_id))
            if active_lease is not None and (
                active_lease.is_expired(heartbeat_at)
                or active_lease.worker_id != worker_id
                or (lease_id is not None and active_lease.lease_id != lease_id)
            ):
                return None
            token = max(worker.fencing_token, fencing_token)
            updated = replace(
                worker,
                fencing_token=token,
                lease_id=lease_id if lease_id is not None else worker.lease_id,
                last_heartbeat=heartbeat_at,
                state=WorkerState.ACTIVE,
            )
            self._workers[key] = updated
            return self._copy_worker(updated)

    async def mark_stale(self, tenant_id: str, plan_id: str, worker_id: str) -> WorkerRecord | None:
        key = self._worker_key(tenant_id, plan_id, worker_id)
        with self._lock:
            worker = self._workers.get(key)
            if worker is None:
                return None
            updated = replace(worker, state=WorkerState.STALE)
            self._workers[key] = updated
            return self._copy_worker(updated)

    async def mark_state(
        self,
        tenant_id: str,
        plan_id: str,
        worker_id: str,
        state: str,
        error: str | None = None,
    ) -> WorkerRecord | None:
        key = self._worker_key(tenant_id, plan_id, worker_id)
        with self._lock:
            worker = self._workers.get(key)
            if worker is None:
                return None
            updated = replace(
                worker,
                state=WorkerState(state),
                last_error=error,
            )
            self._workers[key] = updated
            return self._copy_worker(updated)

    async def remove_worker(self, tenant_id: str, plan_id: str, worker_id: str) -> bool:
        key = self._worker_key(tenant_id, plan_id, worker_id)
        with self._lock:
            return self._workers.pop(key, None) is not None

    async def detect_stale_workers(
        self,
        tenant_id: str,
        plan_id: str,
        stale_threshold_seconds: int,
        now: datetime | None = None,
    ) -> list[WorkerRecord]:
        if (
            not isinstance(stale_threshold_seconds, int)
            or isinstance(stale_threshold_seconds, bool)
            or stale_threshold_seconds < 0
        ):
            raise ValueError("stale_threshold_seconds must be a non-negative integer")
        prefix = (tenant_id, plan_id)
        heartbeat_time = self._as_utc(now) if now is not None else self._now()
        with self._lock:
            stale = [
                self._copy_worker(worker)
                for key, worker in self._workers.items()
                if key[:2] == prefix and worker.is_stale(stale_threshold_seconds, heartbeat_time)
            ]
            stale.sort(key=lambda worker: worker.worker_id)
            return stale

    @staticmethod
    def _validate_record_scope(
        tenant_id: str,
        plan_id: str,
        record: ReconciliationRecord | OrphanRecord | PlanCoordinationState,
    ) -> None:
        if record.tenant_id != tenant_id or record.plan_id != plan_id:
            raise ValueError("record tenant or plan does not match repository scope")

    async def save_reconciliation(
        self, tenant_id: str, plan_id: str, record: ReconciliationRecord
    ) -> ReconciliationRecord:
        self._validate_record_scope(tenant_id, plan_id, record)
        key = self._record_key(tenant_id, plan_id, record.reconciliation_id)
        with self._lock:
            existing = self._reconciliations.get(key)
            if existing is not None:
                return self._copy_reconciliation(existing)
            stored = self._copy_reconciliation(record)
            self._reconciliations[key] = stored
            self._reconciliation_sequence += 1
            self._reconciliation_order[key] = self._reconciliation_sequence
            return self._copy_reconciliation(stored)

    async def get_latest_reconciliation(
        self, tenant_id: str, plan_id: str
    ) -> ReconciliationRecord | None:
        prefix = (tenant_id, plan_id)
        with self._lock:
            records = [record for key, record in self._reconciliations.items() if key[:2] == prefix]
            if not records:
                return None
            latest = max(
                records,
                key=lambda record: (
                    record.reconciled_at,
                    self._reconciliation_order.get(
                        self._record_key(tenant_id, plan_id, record.reconciliation_id), 0
                    ),
                ),
            )
            return self._copy_reconciliation(latest)

    async def save_orphan(self, tenant_id: str, plan_id: str, record: OrphanRecord) -> OrphanRecord:
        self._validate_record_scope(tenant_id, plan_id, record)
        key = self._record_key(tenant_id, plan_id, record.orphan_id)
        with self._lock:
            existing = self._orphans.get(key)
            if existing is not None:
                return self._copy_orphan(existing)
            stored = self._copy_orphan(record)
            self._orphans[key] = stored
            return self._copy_orphan(stored)

    async def list_orphans(self, tenant_id: str, plan_id: str) -> list[OrphanRecord]:
        prefix = (tenant_id, plan_id)
        with self._lock:
            records = [
                self._copy_orphan(record)
                for key, record in self._orphans.items()
                if key[:2] == prefix
            ]
            records.sort(key=lambda record: (record.detected_at, record.orphan_id))
            return records

    async def clear_orphans(self, tenant_id: str, plan_id: str) -> int:
        prefix = (tenant_id, plan_id)
        with self._lock:
            keys = [key for key in self._orphans if key[:2] == prefix]
            for key in keys:
                self._orphans.pop(key, None)
            return len(keys)

    async def save_coordination_state(
        self, tenant_id: str, plan_id: str, state: PlanCoordinationState
    ) -> PlanCoordinationState:
        self._validate_record_scope(tenant_id, plan_id, state)
        self._validate_token(state.fencing_token, "state.fencing_token")
        key = self._scope(tenant_id, plan_id)
        with self._lock:
            current_token = self._fencing_tokens.get(key, 0)
            existing = self._coordination_states.get(key)
            if state.fencing_token < current_token:
                if existing is not None:
                    return self._copy_coordination_state(existing)
                raise ValueError("coordination state has a stale fencing token")
            if existing is not None and state.fencing_token < existing.fencing_token:
                return self._copy_coordination_state(existing)
            if state.fencing_token > current_token:
                self._set_fencing_token_locked(key, state.fencing_token)
            stored = self._copy_coordination_state(state)
            self._coordination_states[key] = stored
            return self._copy_coordination_state(stored)

    async def get_coordination_state(
        self, tenant_id: str, plan_id: str
    ) -> PlanCoordinationState | None:
        key = self._scope(tenant_id, plan_id)
        with self._lock:
            state = self._coordination_states.get(key)
            return self._copy_coordination_state(state) if state is not None else None

    async def list_orphan_steps_for_plan(
        self, tenant_id: str, plan_id: str
    ) -> list[dict[str, Any]]:
        prefix = (tenant_id, plan_id)
        with self._lock:
            records = [record for key, record in self._orphans.items() if key[:2] == prefix]
            records.sort(key=lambda record: (record.detected_at, record.orphan_id))
            return [asdict(record) for record in records]


__all__ = ["InMemoryDurableRecoveryRepository"]
