from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TokenPayload:
    """Decoded JWT claims."""

    sub: UUID
    email: str
    jti: str
    sid: str = ""


class TokenService(ABC):
    """Port for JWT creation and validation."""

    @abstractmethod
    def create_access_token(
        self, *, user_id: UUID, email: str, session_id: str | None = None
    ) -> str: ...

    @abstractmethod
    def decode_access_token(self, token: str) -> TokenPayload: ...
