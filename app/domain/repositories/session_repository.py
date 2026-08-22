from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.domain.entities.user_mfa import UserMFA
from app.domain.entities.user_session import UserSession


class MFARepository(ABC):
    @abstractmethod
    async def get_by_user_id(self, user_id: UUID) -> UserMFA | None: ...

    @abstractmethod
    async def save(self, mfa: UserMFA) -> UserMFA: ...

    @abstractmethod
    async def delete(self, user_id: UUID) -> None: ...


class SessionRepository(ABC):
    @abstractmethod
    async def get_by_session_id(self, session_id: str) -> UserSession | None: ...

    @abstractmethod
    async def get_active_by_user_id(self, user_id: UUID) -> list[UserSession]: ...

    @abstractmethod
    async def save(self, session: UserSession) -> UserSession: ...

    @abstractmethod
    async def revoke(
        self, session_id: str, *, revoked_at: datetime | None = None
    ) -> UserSession | None: ...

    @abstractmethod
    async def revoke_all_for_user(
        self, user_id: UUID, *, revoked_at: datetime | None = None
    ) -> list[UserSession]: ...

    @abstractmethod
    async def delete_expired(self, before: datetime) -> int: ...
