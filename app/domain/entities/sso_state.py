from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


class SSOProviderType(StrEnum):
    OIDC = "oidc"
    SAML = "saml"


class SSOStateStatus(StrEnum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class SSOState:
    state_token: str
    nonce: str
    provider_type: SSOProviderType
    tenant_id: str | None = None
    redirect_uri: str = ""
    status: SSOStateStatus = SSOStateStatus.PENDING
    user_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    consumed_at: datetime | None = None
