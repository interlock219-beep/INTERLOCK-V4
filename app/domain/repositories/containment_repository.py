from abc import ABC, abstractmethod

from app.domain.entities.containment_event import (
    ContainmentEvent,
    ContainmentStatus,
)
from app.domain.entities.recovery_plan import RecoveryPlan, RecoveryStatus


class ContainmentRepository(ABC):
    """Persistence port for ContainmentEvent aggregate."""

    @abstractmethod
    async def get_by_containment_id(
        self, tenant_id: str, containment_id: str
    ) -> ContainmentEvent | None: ...

    @abstractmethod
    async def list_by_agent(
        self,
        tenant_id: str,
        target_agent_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ContainmentEvent], int]: ...

    @abstractmethod
    async def save(self, event: ContainmentEvent) -> ContainmentEvent: ...

    @abstractmethod
    async def update_status(
        self,
        tenant_id: str,
        containment_id: str,
        status: ContainmentStatus,
        result_details: dict[str, str] | None = None,
    ) -> ContainmentEvent | None: ...


class RecoveryPlanRepository(ABC):
    """Persistence port for RecoveryPlan aggregate."""

    @abstractmethod
    async def get_by_plan_id(self, tenant_id: str, plan_id: str) -> RecoveryPlan | None: ...

    @abstractmethod
    async def list_by_incident(
        self,
        tenant_id: str,
        incident_action_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[RecoveryPlan], int]: ...

    @abstractmethod
    async def save(self, plan: RecoveryPlan) -> RecoveryPlan: ...

    @abstractmethod
    async def update_status(
        self,
        tenant_id: str,
        plan_id: str,
        status: RecoveryStatus,
        **fields: object,
    ) -> RecoveryPlan | None: ...
