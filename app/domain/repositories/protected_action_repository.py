from abc import ABC, abstractmethod

from app.domain.entities.protected_action import ActionStatus, ProtectedAction


class ProtectedActionRepository(ABC):
    """Persistence port for ProtectedAction aggregate."""

    @abstractmethod
    async def get_by_action_id(self, tenant_id: str, action_id: str) -> ProtectedAction | None: ...

    @abstractmethod
    async def list_by_agent(
        self,
        tenant_id: str,
        agent_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ProtectedAction], int]: ...

    @abstractmethod
    async def list_by_correlation(
        self,
        tenant_id: str,
        correlation_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ProtectedAction], int]: ...

    @abstractmethod
    async def list_descendants(
        self,
        tenant_id: str,
        root_action_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ProtectedAction], int]: ...

    @abstractmethod
    async def save(self, action: ProtectedAction) -> ProtectedAction: ...

    @abstractmethod
    async def update_status(
        self, tenant_id: str, action_id: str, status: ActionStatus, reason: str = ""
    ) -> ProtectedAction | None: ...
