from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class AuthorityStatus(StrEnum):
    ACTIVE = "active"
    DELEGATED = "delegated"
    REVOKED = "revoked"
    EXPIRED = "expired"
    SUSPENDED = "suspended"
    JIT_EXPIRED = "jit_expired"
    ONE_SHOT_USED = "one_shot_used"


class AuthorityScope(StrEnum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class AuthorityGrant:
    """Authority grant aggregate with lineage tracking."""

    grant_id: str
    tenant_id: str
    grantor_agent_id: str
    grantee_agent_id: str
    scope: AuthorityScope
    resource: str
    conditions: dict[str, str] = field(default_factory=dict)
    expires_at: datetime | None = None
    delegation_depth: int = 0
    parent_authority_id: str | None = None
    root_authority_id: str | None = None
    status: AuthorityStatus = AuthorityStatus.ACTIVE
    revoked_at: datetime | None = None
    revoked_by: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    is_jit: bool = False
    jit_created_at: datetime | None = None
    jit_expires_at: datetime | None = None
    jit_consumed_at: datetime | None = None
    one_shot: bool = False
    usage_count: int = 0
