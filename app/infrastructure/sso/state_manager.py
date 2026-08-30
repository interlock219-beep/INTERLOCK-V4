from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.domain.entities.sso_state import SSOState


class StateStore(ABC):
    @abstractmethod
    async def create(self, state: SSOState) -> SSOState: ...

    @abstractmethod
    async def get(self, state_token: str) -> SSOState | None: ...

    @abstractmethod
    async def mark_authorized(self, state_token: str, user_id: UUID) -> SSOState | None: ...

    @abstractmethod
    async def mark_failed(self, state_token: str) -> SSOState | None: ...

    @abstractmethod
    async def delete_expired(self, before: datetime) -> int: ...
