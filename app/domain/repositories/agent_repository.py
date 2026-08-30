from abc import ABC, abstractmethod

from app.domain.entities.agent import Agent, AgentStatus, AgentType


class AgentRepository(ABC):
    """Persistence port for Agent aggregate."""

    @abstractmethod
    async def get_by_agent_id(self, tenant_id: str, agent_id: str) -> Agent | None: ...

    @abstractmethod
    async def list_by_tenant(
        self,
        tenant_id: str,
        status: AgentStatus | None = None,
        agent_type: AgentType | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Agent], int]: ...

    @abstractmethod
    async def save(self, agent: Agent) -> Agent: ...

    @abstractmethod
    async def delete(self, tenant_id: str, agent_id: str) -> bool: ...

    @abstractmethod
    async def update_status(
        self, tenant_id: str, agent_id: str, status: AgentStatus
    ) -> Agent | None: ...

    @abstractmethod
    async def exists(self, tenant_id: str, agent_id: str) -> bool: ...
