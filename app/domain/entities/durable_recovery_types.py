"""Durable recovery coordination types.

Defines the durable state-machine semantics, lease/fencing primitives,
worker registry records, reconciliation and orphan-detection records
used by :class:`DistributedRecoveryOrchestrator` for durable, fault-tolerant
recovery coordination.

Tenant-scoped state is encoded on every record via ``tenant_id`` so that
records from different tenants never collide.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class DurablePlanStatus(StrEnum):
    """Lifecycle states for a durable recovery plan coordination."""

    PENDING = "pending"
    ACQUIRING_LEASE = "acquiring_lease"
    ACTIVE = "active"
    PAUSED = "paused"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"
    ERROR = "error"
    STALE = "stale"
    FENCED = "fenced"


class WorkerState(StrEnum):
    """Lifecycle states for a recovery worker process."""

    ACTIVE = "active"
    STALE = "stale"
    CRASHED = "crashed"
    OFFLINE = "offline"


class LockMode(StrEnum):
    """Coordination lock modes for recovery plans."""

    EXCLUSIVE = "exclusive"
    SHARED = "shared"


class FencingBumpReason(StrEnum):
    """Reasons for monotonically increasing a fencing token."""

    INITIAL_ACQUISITION = "initial_acquisition"
    STALE_WORKER_DETECTED = "stale_worker_detected"
    CRASH_DETECTED = "crash_detected"
    FORCED_EVICTION = "forced_eviction"
    ORPHAN_RECLAIM = "orphan_reclaim"
    HEARTBEAT_LOST = "heartbeat_lost"


class ReconciliationPhase(StrEnum):
    """Phases of a distributed reconciliation pass."""

    LOAD = "load"
    RESUME = "resume"
    CONVERGE = "converge"
    VERIFY = "verify"
    FINALIZE = "finalize"


@dataclass(frozen=True, slots=True)
class WorkerRecord:
    """A worker registered to coordinate recovery for a plan."""

    plan_id: str
    tenant_id: str
    worker_id: str
    state: WorkerState = WorkerState.ACTIVE
    fencing_token: int = 0
    lease_id: str | None = None
    acquired_at: datetime | None = None
    last_heartbeat: datetime | None = None
    last_error: str | None = None
    worker_metadata: dict[str, Any] = field(default_factory=dict)

    def is_stale(self, threshold_seconds: int, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        if self.last_heartbeat is None:
            return True
        return (now - self.last_heartbeat).total_seconds() > threshold_seconds


@dataclass(frozen=True, slots=True)
class RecoveryLease:
    """A tenant-scoped exclusive lease on a recovery plan.

    The ``fencing_token`` is monotonically increasing per (tenant, plan).
    A stale lease can be reclaimed by a new worker with a strictly higher
    fencing token, fencing out the old owner.
    """

    plan_id: str
    tenant_id: str
    worker_id: str
    lease_id: str
    fencing_token: int
    acquired_at: datetime
    expires_at: datetime
    renewed_at: datetime
    lease_ttl_seconds: int = 60
    lease_metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        return now >= self.expires_at

    def is_owned_by(self, tenant_id: str, worker_id: str) -> bool:
        return self.tenant_id == tenant_id and self.worker_id == worker_id


@dataclass(frozen=True, slots=True)
class LeaseAcquisitionResult:
    """Outcome of a lease acquisition attempt."""

    acquired: bool
    lease: RecoveryLease | None
    reason: str = ""
    evicted_worker_id: str | None = None
    fencing_token: int = 0
    lease_id: str | None = None


@dataclass(frozen=True, slots=True)
class ReconciliationRecord:
    """Record of a distributed reconciliation pass for a plan."""

    plan_id: str
    tenant_id: str
    reconciliation_id: str
    fencing_token: int
    worker_id: str
    reconciled_at: datetime
    phase: ReconciliationPhase
    converged: bool
    divergence_count: int = 0
    details: dict[str, Any] = field(default_factory=dict)
    reconciled_states: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OrphanRecord:
    """Record of an orphaned execution artifact (e.g. a step with no owner)."""

    tenant_id: str
    plan_id: str
    orphan_id: str
    action_id: str
    detected_at: datetime
    orphan_kind: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PlanCoordinationState:
    """Durable coordination state machine for a recovery plan."""

    plan_id: str
    tenant_id: str
    status: DurablePlanStatus = DurablePlanStatus.PENDING
    fencing_token: int = 0
    coordinator_worker_id: str = ""
    active_worker_id: str = ""
    lease_id: str | None = None
    lock_mode: LockMode = LockMode.EXCLUSIVE
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    stop_conditions: list[str] = field(default_factory=list)
    completed_steps: int = 0
    total_steps: int = 0
    verification_passed: bool = False
    coordination_metadata: dict[str, Any] = field(default_factory=dict)

    def with_status(
        self,
        status: DurablePlanStatus,
        completed_at: datetime | None = None,
        **overrides: Any,
    ) -> PlanCoordinationState:
        return PlanCoordinationState(
            plan_id=self.plan_id,
            tenant_id=self.tenant_id,
            status=status,
            fencing_token=overrides.get("fencing_token", self.fencing_token),
            coordinator_worker_id=overrides.get(
                "coordinator_worker_id", self.coordinator_worker_id
            ),
            active_worker_id=overrides.get("active_worker_id", self.active_worker_id),
            lease_id=overrides.get("lease_id", self.lease_id),
            lock_mode=overrides.get("lock_mode", self.lock_mode),
            started_at=self.started_at,
            completed_at=completed_at or self.completed_at,
            stop_conditions=overrides.get("stop_conditions", self.stop_conditions),
            completed_steps=overrides.get("completed_steps", self.completed_steps),
            total_steps=overrides.get("total_steps", self.total_steps),
            verification_passed=overrides.get("verification_passed", self.verification_passed),
            coordination_metadata=self.coordination_metadata,
        )
