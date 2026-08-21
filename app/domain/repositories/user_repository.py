from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.domain.entities.user import User


class UserRepository(ABC):
    """Persistence port for User aggregate."""

    @abstractmethod
    async def get_by_id(self, user_id: UUID) -> User | None: ...

    @abstractmethod
    async def get_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    async def get_by_tenant(self, tenant_id: str) -> list[User]: ...

    @abstractmethod
    async def save(self, user: User) -> User: ...

    @abstractmethod
    async def exists_by_email(self, email: str) -> bool: ...

    @abstractmethod
    async def increment_failed_login(self, user_id: UUID) -> User | None: ...

    @abstractmethod
    async def reset_failed_login(self, user_id: UUID) -> User | None: ...

    @abstractmethod
    async def update_password(self, user_id: UUID, hashed_password: str) -> User | None: ...

    @abstractmethod
    async def lock_account(self, user_id: UUID, locked_until: datetime) -> User | None: ...
