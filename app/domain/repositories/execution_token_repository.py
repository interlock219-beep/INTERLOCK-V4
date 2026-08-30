from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.entities.execution_token import ExecutionToken, TokenStatus


class ExecutionTokenRepository(ABC):
    @abstractmethod
    async def get_by_jti(self, tenant_id: str, jti: str) -> ExecutionToken | None: ...

    @abstractmethod
    async def list_by_agent(
        self,
        tenant_id: str,
        agent_id: str,
        status: TokenStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ExecutionToken], int]: ...

    @abstractmethod
    async def save(self, token: ExecutionToken) -> ExecutionToken: ...

    @abstractmethod
    async def revoke(
        self,
        tenant_id: str,
        token_id: str,
        *,
        revoked_at: datetime | None = None,
    ) -> ExecutionToken | None: ...
