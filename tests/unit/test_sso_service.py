from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.domain.entities.identity_provider import (
    IdentityProvider,
    IdentityProviderStatus,
    IdentityProviderType,
)
from app.domain.entities.sso_state import SSOProviderType, SSOState
from app.domain.services.sso_services import (
    SSOFlowResult,
)
from app.infrastructure.sso.sso_service import DefaultSSOService


class StubSSOStateRepo:
    def __init__(self, state=None) -> None:
        self._state = state

    async def create(self, state):
        self._state = state
        return state

    async def get_by_state_token(self, state_token):
        return self._state

    async def mark_failed(self, state_token):
        pass


class StubIdentityProviderRepo:
    def __init__(self, provider=None) -> None:
        self._provider = provider

    async def get_by_name(self, name, tenant_id):
        return self._provider

    async def list_active(self, tenant_id=None):
        return [self._provider] if self._provider else []


class StubAccountLinking:
    async def find_user_by_sso(self, provider_type, provider_user_id):
        return None


@pytest.mark.asyncio
async def test_initiate_oidc_success():
    provider = IdentityProvider(
        id="prov-1",
        tenant_id="tenant-1",
        name="oidc-provider",
        provider_type=IdentityProviderType.OIDC,
        client_id="client-id",
        client_secret="secret",

        scopes=["openid", "profile", "email"],
        status=IdentityProviderStatus.ACTIVE,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    state_repo = StubSSOStateRepo()
    provider_repo = StubIdentityProviderRepo(provider)
    linking = StubAccountLinking()
    service = DefaultSSOService(state_repo, provider_repo, linking)

    with patch("app.infrastructure.sso.sso_service.DefaultOIDCAdapter") as mock_oidc:
        mock_adapter = AsyncMock()
        mock_adapter.get_authorization_url.return_value = "https://idp.example.com/auth"
        mock_oidc.return_value = mock_adapter
        result = await service.initiate("oidc-provider", "tenant-1", "https://example.com/callback")

    assert result.result == SSOFlowResult.PENDING
    assert result.authorization_url == "https://idp.example.com/auth"
    assert state_repo._state is not None


@pytest.mark.asyncio
async def test_initiate_saml_success():
    provider = IdentityProvider(
        id="prov-1",
        tenant_id="tenant-1",
        name="saml-provider",
        provider_type=IdentityProviderType.SAML,
        client_id="client-id",
        client_secret="secret",

        scopes=[],
        status=IdentityProviderStatus.ACTIVE,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    state_repo = StubSSOStateRepo()
    provider_repo = StubIdentityProviderRepo(provider)
    linking = StubAccountLinking()
    service = DefaultSSOService(state_repo, provider_repo, linking)
    result = await service.initiate("saml-provider", "tenant-1", "https://example.com/callback")
    assert result.result == SSOFlowResult.PENDING
    assert result.authorization_url is not None


@pytest.mark.asyncio
async def test_initiate_provider_not_found():
    state_repo = StubSSOStateRepo()
    provider_repo = StubIdentityProviderRepo(provider=None)
    linking = StubAccountLinking()
    service = DefaultSSOService(state_repo, provider_repo, linking)
    result = await service.initiate("missing", "tenant-1", "https://example.com/callback")
    assert result.result == SSOFlowResult.FAILED


@pytest.mark.asyncio
async def test_initiate_unsupported_provider():
    provider = IdentityProvider(
        id="prov-1",
        tenant_id="tenant-1",
        name="unknown",
        provider_type=IdentityProviderType.OIDC,
        client_id="client-id",
        client_secret="secret",

        scopes=[],
        status=IdentityProviderStatus.ACTIVE,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    state_repo = StubSSOStateRepo()
    provider_repo = StubIdentityProviderRepo(provider)
    linking = StubAccountLinking()
    service = DefaultSSOService(state_repo, provider_repo, linking)
    result = await service.initiate("unknown", "tenant-1", "https://example.com/callback")
    assert result.result == SSOFlowResult.PENDING


@pytest.mark.asyncio
async def test_handle_callback_state_not_found():
    state_repo = StubSSOStateRepo(state=None)
    provider_repo = StubIdentityProviderRepo()
    linking = StubAccountLinking()
    service = DefaultSSOService(state_repo, provider_repo, linking)
    result = await service.handle_callback("invalid-state")
    assert result.result == SSOFlowResult.FAILED


@pytest.mark.asyncio
async def test_handle_callback_provider_not_found():
    state = SSOState(
        state_token="token-1",
        nonce="nonce-1",
        provider_type=SSOProviderType.OIDC,
        tenant_id="tenant-1",
        redirect_uri="https://example.com/callback",
        expires_at=datetime.now(UTC),
    )
    state_repo = StubSSOStateRepo(state=state)
    provider_repo = StubIdentityProviderRepo(provider=None)
    linking = StubAccountLinking()
    service = DefaultSSOService(state_repo, provider_repo, linking)
    result = await service.handle_callback("token-1")
    assert result.result == SSOFlowResult.FAILED


@pytest.mark.asyncio
async def test_handle_callback_oidc_success():
    state = SSOState(
        state_token="token-1",
        nonce="nonce-1",
        provider_type=SSOProviderType.OIDC,
        tenant_id="tenant-1",
        redirect_uri="https://example.com/callback",
        expires_at=datetime.now(UTC),
    )
    state_repo = StubSSOStateRepo(state=state)
    provider = IdentityProvider(
        id="prov-1",
        tenant_id="tenant-1",
        name="oidc",
        provider_type=IdentityProviderType.OIDC,
        client_id="client-id",
        client_secret="secret",

        scopes=[],
        status=IdentityProviderStatus.ACTIVE,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    provider_repo = StubIdentityProviderRepo(provider=provider)
    linking = StubAccountLinking()
    service = DefaultSSOService(state_repo, provider_repo, linking)

    with patch("app.infrastructure.sso.sso_service.DefaultOIDCAdapter") as mock_oidc:
        mock_adapter = AsyncMock()
        mock_adapter.handle_callback.return_value = ("user-1", {"email": "user@example.com"})
        mock_oidc.return_value = mock_adapter
        result = await service.handle_callback("token-1", code="auth-code")

    assert result.result == SSOFlowResult.AUTHORIZED
    assert result.email == "user@example.com"


@pytest.mark.asyncio
async def test_handle_callback_saml_success():
    state = SSOState(
        state_token="token-1",
        nonce="nonce-1",
        provider_type=SSOProviderType.SAML,
        tenant_id="tenant-1",
        redirect_uri="https://example.com/callback",
        expires_at=datetime.now(UTC),
    )
    state_repo = StubSSOStateRepo(state=state)
    provider = IdentityProvider(
        id="prov-1",
        tenant_id="tenant-1",
        name="mock-provider",
        provider_type=IdentityProviderType.SAML,
        client_id="client-id",
        client_secret="secret",
        scopes=[],
        status=IdentityProviderStatus.ACTIVE,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    provider_repo = StubIdentityProviderRepo(provider=provider)
    linking = StubAccountLinking()
    service = DefaultSSOService(state_repo, provider_repo, linking)
    result = await service.handle_callback("token-1", saml_response="<saml>response</saml>")
    assert result.result == SSOFlowResult.AUTHORIZED


@pytest.mark.asyncio
async def test_handle_callback_unsupported_provider():
    state = SSOState(
        state_token="token-1",
        nonce="nonce-1",
        provider_type=SSOProviderType.OIDC,
        tenant_id="tenant-1",
        redirect_uri="https://example.com/callback",
        expires_at=datetime.now(UTC),
    )
    state_repo = StubSSOStateRepo(state=state)
    provider_repo = StubIdentityProviderRepo()
    linking = StubAccountLinking()
    service = DefaultSSOService(state_repo, provider_repo, linking)
    result = await service.handle_callback("token-1")
    assert result.result == SSOFlowResult.FAILED


@pytest.mark.asyncio
async def test_get_providers():
    provider = IdentityProvider(
        id="prov-1",
        tenant_id="tenant-1",
        name="oidc",
        provider_type=IdentityProviderType.OIDC,
        client_id="client-id",
        client_secret="secret",

        scopes=[],
        status=IdentityProviderStatus.ACTIVE,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    state_repo = StubSSOStateRepo()
    provider_repo = StubIdentityProviderRepo(provider=provider)
    linking = StubAccountLinking()
    service = DefaultSSOService(state_repo, provider_repo, linking)
    providers = await service.get_providers("tenant-1")
    assert len(providers) == 1
