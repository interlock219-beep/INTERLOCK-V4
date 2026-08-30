import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities.identity_provider import (
    IdentityProvider,
    IdentityProviderStatus,
    IdentityProviderType,
)
from app.domain.entities.sso_state import SSOProviderType, SSOState, SSOStateStatus
from app.domain.repositories.identity_provider_repository import IdentityProviderRepository
from app.domain.repositories.sso_repository import SSOStateRepository
from app.infrastructure.persistence.models.sso_models import (
    IdentityProviderModel,
    ProviderStatusEnum,
    ProviderTypeEnum,
    SSOStateModel,
    SSOStateStatusEnum,
)


class SQLAlchemySSOStateRepository(SSOStateRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    async def create(self, state: SSOState) -> SSOState:
        model = SSOStateModel(
            id=state.id,
            state_token=state.state_token,
            nonce=state.nonce,
            provider_type=SSOProviderType(state.provider_type.value),
            tenant_id=state.tenant_id,
            redirect_uri=state.redirect_uri,
            status=SSOStateStatus(state.status.value),
            user_id=state.user_id,
            created_at=state.created_at,
            expires_at=state.expires_at,
            consumed_at=state.consumed_at,
        )
        self._session.add(model)
        self._session.flush()
        return state

    async def get_by_state_token(self, state_token: str) -> SSOState | None:
        stmt = select(SSOStateModel).where(SSOStateModel.state_token == state_token)
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_entity(model)

    async def mark_authorized(
        self, state_token: str, user_id: UUID, *, consumed_at: datetime | None = None
    ) -> SSOState | None:
        state = await self.get_by_state_token(state_token)
        if state is None:
            return None
        stmt = select(SSOStateModel).where(SSOStateModel.state_token == state_token)
        result = self._session.execute(stmt)
        model = result.scalar_one()
        model.status = SSOStateStatusEnum("authorized")
        model.user_id = user_id
        model.consumed_at = consumed_at or datetime.now(UTC)
        self._session.flush()
        return self._to_entity(model)

    async def mark_failed(self, state_token: str) -> SSOState | None:
        state = await self.get_by_state_token(state_token)
        if state is None:
            return None
        stmt = select(SSOStateModel).where(SSOStateModel.state_token == state_token)
        result = self._session.execute(stmt)
        model = result.scalar_one()
        model.status = SSOStateStatusEnum("failed")
        self._session.flush()
        return self._to_entity(model)

    async def delete_expired(self, before: datetime) -> int:
        stmt = select(SSOStateModel).where(SSOStateModel.expires_at < before)
        result = self._session.execute(stmt)
        models = result.scalars().all()
        for model in models:
            self._session.delete(model)
        self._session.flush()
        return len(models)

    def _to_entity(self, model: SSOStateModel) -> SSOState:
        return SSOState(
            state_token=model.state_token,
            nonce=model.nonce,
            provider_type=SSOProviderType(model.provider_type.value),
            tenant_id=model.tenant_id,
            redirect_uri=model.redirect_uri,
            status=SSOStateStatus(model.status.value),
            user_id=model.user_id,
            id=model.id,
            created_at=model.created_at,
            expires_at=model.expires_at,
            consumed_at=model.consumed_at,
        )


class SQLAlchemyIdentityProviderRepository(IdentityProviderRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    async def get_by_id(self, provider_id: UUID) -> IdentityProvider | None:
        model = self._session.get(IdentityProviderModel, provider_id)
        if model is None:
            return None
        return self._to_entity(model)

    async def get_by_name(self, name: str, tenant_id: str | None = None) -> IdentityProvider | None:
        stmt = select(IdentityProviderModel).where(IdentityProviderModel.name == name)
        if tenant_id is not None:
            stmt = stmt.where(IdentityProviderModel.tenant_id == tenant_id)
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_entity(model)

    async def list_active(
        self, provider_type: IdentityProviderType | None = None, tenant_id: str | None = None
    ) -> list[IdentityProvider]:
        stmt = select(IdentityProviderModel).where(
            IdentityProviderModel.status == ProviderStatusEnum.active
        )
        if provider_type is not None:
            stmt = stmt.where(
                IdentityProviderModel.provider_type == ProviderTypeEnum(provider_type.value)
            )
        if tenant_id is not None:
            stmt = stmt.where(IdentityProviderModel.tenant_id == tenant_id)
        result = self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_entity(model) for model in models]

    async def save(self, provider: IdentityProvider) -> IdentityProvider:
        model = IdentityProviderModel(
            id=provider.id,
            name=provider.name,
            provider_type=ProviderTypeEnum(provider.provider_type.value),
            tenant_id=provider.tenant_id,
            issuer=provider.issuer,
            authorization_url=provider.authorization_url,
            token_url=provider.token_url,
            jwks_uri=provider.jwks_uri,
            client_id=provider.client_id,
            client_secret=provider.client_secret,
            scopes=" ".join(provider.scopes),
            attribute_mapping=str(provider.attribute_mapping),
            saml_sso_url=provider.saml_sso_url,
            saml_entity_id=provider.saml_entity_id,
            saml_x509_cert=provider.saml_x509_cert,
            status=ProviderStatusEnum(provider.status.value),
            created_at=provider.created_at,
            updated_at=provider.updated_at,
        )
        self._session.add(model)
        self._session.flush()
        return provider

    async def delete(self, provider_id: UUID) -> None:
        model = self._session.get(IdentityProviderModel, provider_id)
        if model is not None:
            self._session.delete(model)
            self._session.flush()

    def _to_entity(self, model: IdentityProviderModel) -> IdentityProvider:
        return IdentityProvider(
            id=model.id,
            name=model.name,
            provider_type=IdentityProviderType(model.provider_type.value),
            tenant_id=model.tenant_id,
            issuer=model.issuer,
            authorization_url=model.authorization_url,
            token_url=model.token_url,
            jwks_uri=model.jwks_uri,
            client_id=model.client_id,
            client_secret=model.client_secret,
            scopes=model.scopes.split(" ") if model.scopes else [],
            attribute_mapping=(
                json.loads(model.attribute_mapping) if model.attribute_mapping else {}
            ),
            saml_sso_url=model.saml_sso_url,
            saml_entity_id=model.saml_entity_id,
            saml_x509_cert=model.saml_x509_cert,
            status=IdentityProviderStatus(model.status.value),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
