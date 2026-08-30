from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.entities.agent_session import AgentSession, AgentSessionStatus


class AgentSessionRepository(ABC):
    """Persistence port for AgentSession aggregate."""

    @abstractmethod
    async def get_by_session_id(self, tenant_id: str, session_id: str) -> AgentSession | None: ...

    @abstractmethod
    async def list_by_agent(
        self,
        tenant_id: str,
        agent_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[AgentSession], int]: ...

    @abstractmethod
    async def list_by_tenant(
        self,
        tenant_id: str,
        status: AgentSessionStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[AgentSession], int]: ...

    @abstractmethod
    async def save(self, session: AgentSession) -> AgentSession: ...

    @abstractmethod
    async def update_status(
        self,
        tenant_id: str,
        session_id: str,
        status: AgentSessionStatus,
        ended_at: datetime | None = None,
    ) -> AgentSession | None: ...
