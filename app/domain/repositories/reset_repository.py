from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.domain.entities.email_verification_token import EmailVerificationToken
from app.domain.entities.password_reset_token import PasswordResetToken


class PasswordResetRepository(ABC):
    @abstractmethod
    async def create(self, token: PasswordResetToken) -> PasswordResetToken: ...

    @abstractmethod
    async def get_by_token_hash(self, token_hash: str) -> PasswordResetToken | None: ...

    @abstractmethod
    async def mark_used(self, token_id: UUID, used_at: datetime) -> PasswordResetToken | None: ...

    @abstractmethod
    async def delete_expired(self, before: datetime) -> int: ...


class EmailVerificationRepository(ABC):
    @abstractmethod
    async def create(self, token: EmailVerificationToken) -> EmailVerificationToken: ...

    @abstractmethod
    async def get_by_token_hash(self, token_hash: str) -> EmailVerificationToken | None: ...

    @abstractmethod
    async def mark_used(
        self, token_id: UUID, used_at: datetime
    ) -> EmailVerificationToken | None: ...

    @abstractmethod
    async def delete_expired(self, before: datetime) -> int: ...
