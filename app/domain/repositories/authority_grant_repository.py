from abc import ABC, abstractmethod

from app.domain.entities.authority_grant import AuthorityGrant, AuthorityStatus


class AuthorityGrantRepository(ABC):
    """Persistence port for AuthorityGrant aggregate."""

    @abstractmethod
    async def get_by_grant_id(self, tenant_id: str, grant_id: str) -> AuthorityGrant | None: ...

    @abstractmethod
    async def list_by_grantee(
        self,
        tenant_id: str,
        grantee_agent_id: str,
        status: AuthorityStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[AuthorityGrant], int]: ...

    @abstractmethod
    async def list_by_grantor(
        self,
        tenant_id: str,
        grantor_agent_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[AuthorityGrant], int]: ...

    @abstractmethod
    async def list_descendants(
        self,
        tenant_id: str,
        root_authority_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[AuthorityGrant], int]: ...

    @abstractmethod
    async def save(self, grant: AuthorityGrant) -> AuthorityGrant: ...

    @abstractmethod
    async def revoke(
        self, tenant_id: str, grant_id: str, revoked_by: str
    ) -> AuthorityGrant | None: ...

    @abstractmethod
    async def get_active_for_agent(
        self, tenant_id: str, agent_id: str, resource: str | None = None
    ) -> list[AuthorityGrant]: ...
