"""Persistence ports for durable recovery coordination.

Defines tenant-scoped repository contracts for:
- recovery leases (acquire/renew/release/bump fencing token)
- worker registry (register/heartbeat/stale detection/failover)
- reconciliation, orphan detection and plan coordination state

All methods are async to allow backing stores (SQL, Redis, in-memory).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from app.domain.entities.durable_recovery_types import (
    LeaseAcquisitionResult,
    OrphanRecord,
    PlanCoordinationState,
    ReconciliationRecord,
    RecoveryLease,
    WorkerRecord,
)


class RecoveryLeaseRepository(ABC):
    """Persistence port for tenant-scoped recovery leases."""

    @abstractmethod
    async def acquire_lease(
        self,
        tenant_id: str,
        plan_id: str,
        worker_id: str,
        ttl_seconds: int = 60,
        expected_fencing_token: int | None = None,
        reason: str = "initial_acquisition",
    ) -> LeaseAcquisitionResult: ...

    @abstractmethod
    async def renew_lease(
        self,
        tenant_id: str,
        plan_id: str,
        lease_id: str,
        worker_id: str,
        ttl_seconds: int = 60,
    ) -> bool: ...

    @abstractmethod
    async def release_lease(
        self,
        tenant_id: str,
        plan_id: str,
        lease_id: str,
        worker_id: str,
    ) -> bool: ...

    @abstractmethod
    async def get_active_lease(
        self, tenant_id: str, plan_id: str
    ) -> RecoveryLease | None: ...

    @abstractmethod
    async def revoke_lease(
        self, tenant_id: str, plan_id: str, reason: str
    ) -> bool: ...

    @abstractmethod
    async def bump_fencing_token(
        self, tenant_id: str, plan_id: str, reason: str
    ) -> int: ...

    @abstractmethod
    async def get_fencing_token(self, tenant_id: str, plan_id: str) -> int: ...


class RecoveryWorkerRepository(ABC):
    """Persistence port for the recovery worker registry."""

    @abstractmethod
    async def register_worker(
        self,
        tenant_id: str,
        plan_id: str,
        worker_id: str,
        fencing_token: int = 0,
        lease_id: str | None = None,
    ) -> WorkerRecord: ...

    @abstractmethod
    async def get_worker(
        self, tenant_id: str, plan_id: str, worker_id: str
    ) -> WorkerRecord | None: ...

    @abstractmethod
    async def list_workers(self, tenant_id: str, plan_id: str) -> list[WorkerRecord]: ...

    @abstractmethod
    async def update_heartbeat(
        self,
        tenant_id: str,
        plan_id: str,
        worker_id: str,
        fencing_token: int,
        lease_id: str | None = None,
        now: datetime | None = None,
    ) -> WorkerRecord | None: ...

    @abstractmethod
    async def mark_stale(
        self, tenant_id: str, plan_id: str, worker_id: str
    ) -> WorkerRecord | None: ...

    @abstractmethod
    async def mark_state(
        self,
        tenant_id: str,
        plan_id: str,
        worker_id: str,
        state: str,
        error: str | None = None,
    ) -> WorkerRecord | None: ...

    @abstractmethod
    async def remove_worker(
        self, tenant_id: str, plan_id: str, worker_id: str
    ) -> bool: ...

    @abstractmethod
    async def detect_stale_workers(
        self,
        tenant_id: str,
        plan_id: str,
        stale_threshold_seconds: int,
        now: datetime | None = None,
    ) -> list[WorkerRecord]: ...


class RecoveryReconciliationRepository(ABC):
    """Persistence port for reconciliation, orphan and coordination state."""

    @abstractmethod
    async def save_reconciliation(
        self, tenant_id: str, plan_id: str, record: ReconciliationRecord
    ) -> ReconciliationRecord: ...

    @abstractmethod
    async def get_latest_reconciliation(
        self, tenant_id: str, plan_id: str
    ) -> ReconciliationRecord | None: ...

    @abstractmethod
    async def save_orphan(
        self, tenant_id: str, plan_id: str, record: OrphanRecord
    ) -> OrphanRecord: ...

    @abstractmethod
    async def list_orphans(
        self, tenant_id: str, plan_id: str
    ) -> list[OrphanRecord]: ...

    @abstractmethod
    async def clear_orphans(
        self, tenant_id: str, plan_id: str
    ) -> int: ...

    @abstractmethod
    async def save_coordination_state(
        self, tenant_id: str, plan_id: str, state: PlanCoordinationState
    ) -> PlanCoordinationState: ...

    @abstractmethod
    async def get_coordination_state(
        self, tenant_id: str, plan_id: str
    ) -> PlanCoordinationState | None: ...

    @abstractmethod
    async def list_orphan_steps_for_plan(
        self, tenant_id: str, plan_id: str
    ) -> list[dict[str, Any]]: ...
