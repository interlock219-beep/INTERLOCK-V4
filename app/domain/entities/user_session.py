from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UserSession:
    user_id: UUID
    session_id: str
    expires_at: datetime
    device_info: str | None = None
    ip_address: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_used_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    revoked: bool = False
    revoked_at: datetime | None = None
