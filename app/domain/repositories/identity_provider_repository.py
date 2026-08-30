from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.identity_provider import IdentityProvider, IdentityProviderType


class IdentityProviderRepository(ABC):
    @abstractmethod
    async def get_by_id(self, provider_id: UUID) -> IdentityProvider | None: ...

    @abstractmethod
    async def get_by_name(
        self, name: str, tenant_id: str | None = None
    ) -> IdentityProvider | None: ...

    @abstractmethod
    async def list_active(
        self, provider_type: IdentityProviderType | None = None, tenant_id: str | None = None
    ) -> list[IdentityProvider]: ...

    @abstractmethod
    async def save(self, provider: IdentityProvider) -> IdentityProvider: ...

    @abstractmethod
    async def delete(self, provider_id: UUID) -> None: ...
