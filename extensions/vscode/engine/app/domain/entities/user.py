from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class User:
    """Core user aggregate root."""

    id: UUID
    email: str
    hashed_password: str
    is_active: bool
    created_at: datetime
    role: str = "viewer"
    tenant_id: str | None = None
    failed_login_attempts: int = 0
    locked_until: datetime | None = None
    password_changed_at: datetime | None = None
