from abc import ABC, abstractmethod

from app.domain.entities.discovery_event import DiscoveryEvent, DiscoverySource, DiscoveryStatus


class DiscoveryEventRepository(ABC):
    """Persistence port for DiscoveryEvent aggregate."""

    @abstractmethod
    async def get_by_discovery_id(
        self, tenant_id: str, discovery_id: str
    ) -> DiscoveryEvent | None: ...

    @abstractmethod
    async def list_by_tenant(
        self,
        tenant_id: str,
        source: DiscoverySource | None = None,
        discovery_status: DiscoveryStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[DiscoveryEvent], int]: ...

    @abstractmethod
    async def list_by_agent(
        self,
        tenant_id: str,
        agent_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[DiscoveryEvent], int]: ...

    @abstractmethod
    async def save(self, event: DiscoveryEvent) -> DiscoveryEvent: ...
