from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ApiKey:
    id: UUID
    key_id: str
    key_hash: str
    user_id: UUID
    tenant_id: str | None
    name: str
    expires_at: datetime
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_used_at: datetime | None = None
    revoked: bool = False
    revoked_at: datetime | None = None
