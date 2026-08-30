from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text, Uuid
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.database import Base


class ProviderTypeEnum(StrEnum):
    oidc = "oidc"
    saml = "saml"


class ProviderStatusEnum(StrEnum):
    active = "active"
    inactive = "inactive"
    error = "error"


class SSOStateStatusEnum(StrEnum):
    pending = "pending"
    authorized = "authorized"
    failed = "failed"
    expired = "expired"


class IdentityProviderModel(Base):
    __tablename__ = "identity_providers"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    provider_type: Mapped[ProviderTypeEnum] = mapped_column(
        SQLEnum(ProviderTypeEnum, name="provider_type"), nullable=False
    )
    tenant_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    issuer: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    authorization_url: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    token_url: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    jwks_uri: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    client_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    client_secret: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    scopes: Mapped[str] = mapped_column(String(512), nullable=False, default="openid profile email")
    attribute_mapping: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    saml_sso_url: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    saml_entity_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    saml_x509_cert: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[ProviderStatusEnum] = mapped_column(
        SQLEnum(ProviderStatusEnum, name="provider_status"),
        nullable=False,
        default=ProviderStatusEnum.active,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SSOStateModel(Base):
    __tablename__ = "sso_states"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    state_token: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    nonce: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_type: Mapped[ProviderTypeEnum] = mapped_column(
        SQLEnum(ProviderTypeEnum, name="sso_provider_type"), nullable=False
    )
    tenant_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    redirect_uri: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    status: Mapped[SSOStateStatusEnum] = mapped_column(
        SQLEnum(SSOStateStatusEnum, name="sso_state_status"),
        nullable=False,
        default=SSOStateStatusEnum.pending,
    )
    user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
