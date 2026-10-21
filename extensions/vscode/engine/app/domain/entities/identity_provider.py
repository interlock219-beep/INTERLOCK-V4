from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


class IdentityProviderType(StrEnum):
    OIDC = "oidc"
    SAML = "saml"


class IdentityProviderStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class IdentityProvider:
    name: str
    provider_type: IdentityProviderType
    tenant_id: str | None = None
    issuer: str = ""
    authorization_url: str = ""
    token_url: str = ""
    jwks_uri: str = ""
    client_id: str = ""
    client_secret: str = ""
    scopes: list[str] = field(default_factory=lambda: ["openid", "profile", "email"])
    attribute_mapping: dict[str, str] = field(default_factory=dict)
    saml_sso_url: str = ""
    saml_entity_id: str = ""
    saml_x509_cert: str = ""
    status: IdentityProviderStatus = IdentityProviderStatus.ACTIVE
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
