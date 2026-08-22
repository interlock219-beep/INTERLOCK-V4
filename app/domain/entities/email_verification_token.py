from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class EmailVerificationToken:
    user_id: UUID
    token_hash: str
    expires_at: datetime
    id: UUID = field(default_factory=uuid4)
    used: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    used_at: datetime | None = None
