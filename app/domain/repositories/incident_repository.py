from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.entities.incident import Incident, IncidentStatus


class IncidentRepository(ABC):
    """Persistence port for Incident aggregate."""

    @abstractmethod
    async def get_by_incident_id(self, tenant_id: str, incident_id: str) -> Incident | None: ...

    @abstractmethod
    async def list_by_agent(
        self,
        tenant_id: str,
        agent_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Incident], int]: ...

    @abstractmethod
    async def list_by_tenant(
        self,
        tenant_id: str,
        status: IncidentStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Incident], int]: ...

    @abstractmethod
    async def save(self, incident: Incident) -> Incident: ...

    @abstractmethod
    async def update_status(
        self,
        tenant_id: str,
        incident_id: str,
        status: IncidentStatus,
        resolved_at: datetime | None = None,
    ) -> Incident | None: ...
