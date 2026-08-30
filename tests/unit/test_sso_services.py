from datetime import datetime
from uuid import UUID, uuid4

import pytest

from app.domain.entities.identity_provider import (
    IdentityProvider,
    IdentityProviderStatus,
    IdentityProviderType,
)
from app.domain.entities.sso_state import SSOProviderType, SSOState, SSOStateStatus
from app.domain.repositories.identity_provider_repository import IdentityProviderRepository
from app.domain.repositories.sso_repository import SSOStateRepository
from app.domain.services.sso_services import (
    MockAccountLinkingService,
    SSOFlowResult,
    SSOService,
    StateManager,
)


class FakeSSOStateRepository(SSOStateRepository):
    def __init__(self) -> None:
        self._states: dict[str, SSOState] = {}

    async def create(self, state: SSOState) -> SSOState:
        self._states[state.state_token] = state
        return state

    async def get_by_state_token(self, state_token: str) -> SSOState | None:
        return self._states.get(state_token)

    async def mark_authorized(
        self, state_token: str, user_id: UUID, *, consumed_at: datetime | None = None
    ) -> SSOState | None:
        state = self._states.get(state_token)
        if state is None:
            return None
        state = SSOState(
            state_token=state.state_token,
            nonce=state.nonce,
            provider_type=state.provider_type,
            tenant_id=state.tenant_id,
            redirect_uri=state.redirect_uri,
            status=SSOStateStatus.AUTHORIZED,
            user_id=user_id,
            id=state.id,
            created_at=state.created_at,
            expires_at=state.expires_at,
            consumed_at=consumed_at,
        )
        self._states[state_token] = state
        return state

    async def mark_failed(self, state_token: str) -> SSOState | None:
        state = self._states.get(state_token)
        if state is None:
            return None
        state = SSOState(
            state_token=state.state_token,
            nonce=state.nonce,
            provider_type=state.provider_type,
            tenant_id=state.tenant_id,
            redirect_uri=state.redirect_uri,
            status=SSOStateStatus.FAILED,
            id=state.id,
            created_at=state.created_at,
            expires_at=state.expires_at,
            consumed_at=state.consumed_at,
        )
        self._states[state_token] = state
        return state

    async def delete_expired(self, before: datetime) -> int:
        expired = [token for token, state in self._states.items() if state.expires_at < before]
        for token in expired:
            del self._states[token]
        return len(expired)


class FakeIdentityProviderRepository(IdentityProviderRepository):
    def __init__(self, providers: list[IdentityProvider] | None = None) -> None:
        self._providers = {p.name: p for p in (providers or [])}

    async def get_by_id(self, provider_id: UUID) -> IdentityProvider | None:
        for provider in self._providers.values():
            if provider.id == provider_id:
                return provider
        return None

    async def get_by_name(self, name: str, tenant_id: str | None = None) -> IdentityProvider | None:
        return self._providers.get(name)

    async def list_active(
        self, provider_type: IdentityProviderType | None = None, tenant_id: str | None = None
    ) -> list[IdentityProvider]:
        providers = list(self._providers.values())
        if provider_type is not None:
            providers = [p for p in providers if p.provider_type == provider_type]
        if tenant_id is not None:
            providers = [p for p in providers if p.tenant_id == tenant_id]
        return providers

    async def save(self, provider: IdentityProvider) -> IdentityProvider:
        self._providers[provider.name] = provider
        return provider

    async def delete(self, provider_id: UUID) -> None:
        to_delete = [name for name, p in self._providers.items() if p.id == provider_id]
        for name in to_delete:
            del self._providers[name]


class TestStateManager:
    def test_generate_state_creates_state(self) -> None:
        manager = StateManager(state_ttl_seconds=600)
        state = manager.generate_state(SSOProviderType.OIDC, "tenant-1", "http://example.com/callback")
        assert state.state_token
        assert state.nonce
        assert state.provider_type == SSOProviderType.OIDC
        assert state.tenant_id == "tenant-1"
        assert state.status == SSOStateStatus.PENDING

    def test_get_state_returns_none_for_missing_token(self) -> None:
        manager = StateManager()
        assert manager.get_state("missing") is None

    def test_get_state_returns_none_for_expired_token(self) -> None:

        manager = StateManager(state_ttl_seconds=-1)
        state = manager.generate_state(SSOProviderType.OIDC, None, "http://example.com/callback")
        assert manager.get_state(state.state_token) is None

    def test_mark_consumed_updates_state(self) -> None:
        manager = StateManager()
        state = manager.generate_state(SSOProviderType.OIDC, None, "http://example.com/callback")
        user_id = uuid4()
        updated = manager.mark_consumed(state.state_token, user_id)
        assert updated is not None
        assert updated.status == SSOStateStatus.AUTHORIZED
        assert updated.user_id == user_id
        assert updated.consumed_at is not None

    def test_mark_failed_updates_state(self) -> None:
        manager = StateManager()
        state = manager.generate_state(SSOProviderType.OIDC, None, "http://example.com/callback")
        updated = manager.mark_failed(state.state_token)
        assert updated is not None
        assert updated.status == SSOStateStatus.FAILED

    def test_cleanup_expired_removes_stale_entries(self) -> None:

        manager = StateManager(state_ttl_seconds=-1)
        state = manager.generate_state(SSOProviderType.OIDC, None, "http://example.com/callback")
        assert manager.cleanup_expired() == 1
        assert manager.get_state(state.state_token) is None


class TestMockAccountLinkingService:
    async def test_link_and_find_user(self) -> None:
        service = MockAccountLinkingService()
        user_id = uuid4()
        await service.link_sso_account(user_id, IdentityProviderType.OIDC, "provider-user-1")
        found = await service.find_user_by_sso(IdentityProviderType.OIDC, "provider-user-1")
        assert found == user_id

    async def test_find_unknown_user_returns_none(self) -> None:
        service = MockAccountLinkingService()
        result = await service.find_user_by_sso(IdentityProviderType.OIDC, "unknown")
        assert result is None


class TestDefaultSSOService:
    @pytest.fixture
    def sso_service(self) -> SSOService:
        from app.infrastructure.sso.sso_service import DefaultSSOService

        return DefaultSSOService(
            sso_state_repository=FakeSSOStateRepository(),
            identity_provider_repository=FakeIdentityProviderRepository(),
            account_linking=MockAccountLinkingService(),
        )

    @pytest.fixture
    def provider(self) -> IdentityProvider:
        return IdentityProvider(
            id=uuid4(),
            name="test-oidc",
            provider_type=IdentityProviderType.OIDC,
            issuer="https://issuer.example.com",
            authorization_url="https://provider.example.com/authorize",
            token_url="https://provider.example.com/token",
            jwks_uri="https://provider.example.com/jwks",
            client_id="test-client",
            client_secret="test-secret",
            scopes=["openid", "profile"],
            status=IdentityProviderStatus.ACTIVE,
        )

    async def test_initiate_returns_pending_with_url(
        self, sso_service: SSOService, provider: IdentityProvider
    ) -> None:
        await sso_service._identity_provider_repository.save(provider)

        result = await sso_service.initiate("test-oidc", "tenant-1", "http://localhost/callback")
        assert result.result == SSOFlowResult.PENDING
        assert result.authorization_url is not None
        assert "client_id=test-client" in result.authorization_url
        assert result.state_token is not None

    async def test_initiate_returns_failed_for_unknown_provider(
        self, sso_service: SSOService
    ) -> None:
        result = await sso_service.initiate("unknown", None, "http://localhost/callback")
        assert result.result == SSOFlowResult.FAILED

    async def test_handle_callback_returns_authorized_for_linked_user(
        self, sso_service: SSOService, provider: IdentityProvider
    ) -> None:
        from app.infrastructure.sso.sso_service import DefaultSSOService

        assert isinstance(sso_service, DefaultSSOService)
        await sso_service._identity_provider_repository.save(provider)

        initiate_result = await sso_service.initiate("test-oidc", None, "http://localhost/callback")
        assert initiate_result.state_token

        sso_service._identity_provider_repository._providers["mock-provider"] = provider
        callback_result = await sso_service.handle_callback(
            initiate_result.state_token, code="mock-code"
        )
        assert callback_result.result == SSOFlowResult.AUTHORIZED
        assert callback_result.user_id is not None
        assert callback_result.email == "user@example.com"

    async def test_handle_callback_returns_failed_for_invalid_state(
        self, sso_service: SSOService
    ) -> None:
        result = await sso_service.handle_callback("invalid-state", code="mock-code")
        assert result.result == SSOFlowResult.FAILED

    async def test_get_providers_returns_active_providers(
        self, sso_service: SSOService, provider: IdentityProvider
    ) -> None:
        await sso_service._identity_provider_repository.save(provider)

        providers = await sso_service.get_providers()
        assert len(providers) == 1
        assert providers[0].name == "test-oidc"
