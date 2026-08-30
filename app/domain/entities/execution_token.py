from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class TokenStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    CONSUMED = "consumed"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class ExecutionToken:
    token_id: str
    tenant_id: str
    jti: str
    agent_id: str
    tool: str
    authority_grant_id: str | None = None
    status: TokenStatus = TokenStatus.ACTIVE
    issued_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    consumed_at: datetime | None = None
    revoked_at: datetime | None = None
