from abc import ABC, abstractmethod

from app.domain.entities.causal_state_types import (
    AIChangeSet,
    CausalStateGraph,
    DurableExecutionStep,
    RecoveryConfidence,
    RecoveryReport,
    ResourceVersion,
    StateCheckpoint,
    StateDelta,
)


class StateCheckpointRepository(ABC):
    """Persistence port for StateCheckpoint."""

    @abstractmethod
    async def get_by_checkpoint_id(
        self, tenant_id: str, checkpoint_id: str
    ) -> StateCheckpoint | None: ...

    @abstractmethod
    async def get_by_action_id(self, tenant_id: str, action_id: str) -> StateCheckpoint | None: ...

    @abstractmethod
    async def list_by_resource(
        self,
        tenant_id: str,
        resource_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[StateCheckpoint], int]: ...

    @abstractmethod
    async def save(self, checkpoint: StateCheckpoint) -> StateCheckpoint: ...


class ResourceVersionRepository(ABC):
    """Persistence port for ResourceVersion lineage."""

    @abstractmethod
    async def get_by_version_id(
        self, tenant_id: str, version_id: str
    ) -> ResourceVersion | None: ...

    @abstractmethod
    async def list_by_resource(
        self,
        tenant_id: str,
        resource_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ResourceVersion], int]: ...

    @abstractmethod
    async def get_latest_version(
        self, tenant_id: str, resource_id: str
    ) -> ResourceVersion | None: ...

    @abstractmethod
    async def save(self, version: ResourceVersion) -> ResourceVersion: ...


class ChangeSetRepository(ABC):
    """Persistence port for AIChangeSet."""

    @abstractmethod
    async def get_by_changeset_id(
        self, tenant_id: str, changeset_id: str
    ) -> AIChangeSet | None: ...

    @abstractmethod
    async def get_by_incident(self, tenant_id: str, incident_id: str) -> AIChangeSet | None: ...

    @abstractmethod
    async def save(self, changeset: AIChangeSet) -> AIChangeSet: ...


class CausalStateGraphRepository(ABC):
    """Persistence port for CausalStateGraph."""

    @abstractmethod
    async def get_by_graph_id(self, tenant_id: str, graph_id: str) -> CausalStateGraph | None: ...

    @abstractmethod
    async def get_by_incident(
        self, tenant_id: str, incident_id: str
    ) -> CausalStateGraph | None: ...

    @abstractmethod
    async def save(self, graph: CausalStateGraph) -> CausalStateGraph: ...


class ConfidenceRepository(ABC):
    """Persistence port for RecoveryConfidence."""

    @abstractmethod
    async def get_by_confidence_id(
        self, tenant_id: str, confidence_id: str
    ) -> RecoveryConfidence | None: ...

    @abstractmethod
    async def get_by_plan(self, tenant_id: str, plan_id: str) -> RecoveryConfidence | None: ...

    @abstractmethod
    async def save(self, confidence: RecoveryConfidence) -> RecoveryConfidence: ...


class StaleFencingTokenError(RuntimeError):
    """Durable write rejected: a newer fencing token already advanced the fence.

    Raised by :class:`DurableExecutionRepository.save` when
    ``expected_fencing_token`` is older than the stored ``write_fence`` of the
    step. Callers must treat this as a distinct concurrency outcome — the
    write did NOT persist — and never report it as success.
    """


def enforce_write_fence(
    stored_write_fence: int,
    expected_fencing_token: int | None,
    step_id: str,
) -> None:
    """Shared fencing check for DurableExecutionRepository implementations.

    ``expected_fencing_token=None`` selects the documented legacy path: an
    unconditional write that never consults or mutates the stored fence.
    Otherwise the write is accepted iff ``stored_write_fence <=
    expected_fencing_token``.
    """
    if expected_fencing_token is None:
        return
    if stored_write_fence > expected_fencing_token:
        raise StaleFencingTokenError(
            f"Stale fencing token for step {step_id!r}: stored write fence "
            f"{stored_write_fence} is newer than expected token "
            f"{expected_fencing_token} (stale writer rejected)"
        )


class DurableExecutionRepository(ABC):
    """Persistence port for DurableExecutionStep."""

    @abstractmethod
    async def get_by_step_id(self, tenant_id: str, step_id: str) -> DurableExecutionStep | None: ...

    @abstractmethod
    async def list_by_plan(
        self,
        tenant_id: str,
        plan_id: str,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[list[DurableExecutionStep], int]: ...

    @abstractmethod
    async def save(
        self,
        step: DurableExecutionStep,
        expected_fencing_token: int | None = None,
    ) -> DurableExecutionStep:
        """Persist a step, fenced by ``expected_fencing_token``.

        When a token is supplied, the write is accepted only if it is not
        older than the stored write fence; otherwise
        :class:`StaleFencingTokenError` is raised and nothing persists.
        ``None`` keeps the legacy unconditional behavior.
        """


class RecoveryReportRepository(ABC):
    """Persistence port for RecoveryReport."""

    @abstractmethod
    async def get_by_report_id(self, tenant_id: str, report_id: str) -> RecoveryReport | None: ...

    @abstractmethod
    async def get_by_plan(self, tenant_id: str, plan_id: str) -> RecoveryReport | None: ...

    @abstractmethod
    async def get_by_incident(self, tenant_id: str, incident_id: str) -> RecoveryReport | None: ...

    @abstractmethod
    async def save(self, report: RecoveryReport) -> RecoveryReport: ...


class StateDeltaRepository(ABC):
    """Persistence port for StateDelta."""

    @abstractmethod
    async def get_by_delta_id(self, tenant_id: str, delta_id: str) -> StateDelta | None: ...

    @abstractmethod
    async def list_by_resource(
        self,
        tenant_id: str,
        resource_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[StateDelta], int]: ...

    @abstractmethod
    async def save(self, delta: StateDelta) -> StateDelta: ...
