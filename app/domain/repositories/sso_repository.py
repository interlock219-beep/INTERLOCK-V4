from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.domain.entities.identity_provider import IdentityProvider, IdentityProviderType
from app.domain.entities.sso_state import SSOState


class SSOStateRepository(ABC):
    @abstractmethod
    async def create(self, state: SSOState) -> SSOState: ...

    @abstractmethod
    async def get_by_state_token(self, state_token: str) -> SSOState | None: ...

    @abstractmethod
    async def mark_authorized(
        self, state_token: str, user_id: UUID, *, consumed_at: datetime | None = None
    ) -> SSOState | None: ...

    @abstractmethod
    async def mark_failed(self, state_token: str) -> SSOState | None: ...

    @abstractmethod
    async def delete_expired(self, before: datetime) -> int: ...


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
