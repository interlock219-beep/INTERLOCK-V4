from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.domain.entities.api_key import ApiKey


class ApiKeyRepository(ABC):
    @abstractmethod
    async def create(self, api_key: ApiKey) -> ApiKey: ...

    @abstractmethod
    async def get_by_key_hash(self, key_hash: str) -> ApiKey | None: ...

    @abstractmethod
    async def get_by_key_id(self, key_id: str) -> ApiKey | None: ...

    @abstractmethod
    async def get_by_user_id(self, user_id: UUID) -> list[ApiKey]: ...

    @abstractmethod
    async def revoke(
        self, key_id: str, *, user_id: UUID | None = None
    ) -> ApiKey | None: ...

    @abstractmethod
    async def delete_expired(self, before: datetime) -> int: ...
