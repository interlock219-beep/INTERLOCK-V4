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
    async def get_by_action_id(
        self, tenant_id: str, action_id: str
    ) -> StateCheckpoint | None: ...

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
    async def get_by_incident(
        self, tenant_id: str, incident_id: str
    ) -> AIChangeSet | None: ...

    @abstractmethod
    async def save(self, changeset: AIChangeSet) -> AIChangeSet: ...


class CausalStateGraphRepository(ABC):
    """Persistence port for CausalStateGraph."""

    @abstractmethod
    async def get_by_graph_id(
        self, tenant_id: str, graph_id: str
    ) -> CausalStateGraph | None: ...

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
    async def get_by_plan(
        self, tenant_id: str, plan_id: str
    ) -> RecoveryConfidence | None: ...

    @abstractmethod
    async def save(self, confidence: RecoveryConfidence) -> RecoveryConfidence: ...


class DurableExecutionRepository(ABC):
    """Persistence port for DurableExecutionStep."""

    @abstractmethod
    async def get_by_step_id(
        self, tenant_id: str, step_id: str
    ) -> DurableExecutionStep | None: ...

    @abstractmethod
    async def list_by_plan(
        self,
        tenant_id: str,
        plan_id: str,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[list[DurableExecutionStep], int]: ...

    @abstractmethod
    async def save(self, step: DurableExecutionStep) -> DurableExecutionStep: ...


class RecoveryReportRepository(ABC):
    """Persistence port for RecoveryReport."""

    @abstractmethod
    async def get_by_report_id(
        self, tenant_id: str, report_id: str
    ) -> RecoveryReport | None: ...

    @abstractmethod
    async def get_by_plan(
        self, tenant_id: str, plan_id: str
    ) -> RecoveryReport | None: ...

    @abstractmethod
    async def get_by_incident(
        self, tenant_id: str, incident_id: str
    ) -> RecoveryReport | None: ...

    @abstractmethod
    async def save(self, report: RecoveryReport) -> RecoveryReport: ...


class StateDeltaRepository(ABC):
    """Persistence port for StateDelta."""

    @abstractmethod
    async def get_by_delta_id(
        self, tenant_id: str, delta_id: str
    ) -> StateDelta | None: ...

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
