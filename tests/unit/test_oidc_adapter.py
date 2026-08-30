from __future__ import annotations

import pytest

from app.domain.entities.identity_provider import IdentityProvider, IdentityProviderType
from app.domain.entities.sso_state import SSOProviderType, SSOState
from app.infrastructure.sso.oidc_adapter import DefaultOIDCAdapter, OIDCProviderError


def make_provider():
    return IdentityProvider(
        name="oidc",
        provider_type=IdentityProviderType.OIDC,
        tenant_id="tenant-1",
        client_id="client-id",
        client_secret="secret",
        authorization_url="https://example.com/auth",
        scopes=["openid", "profile", "email"],
        issuer="https://example.com",
    )


def test_default_oidc_adapter_get_authorization_url():
    import asyncio

    adapter = DefaultOIDCAdapter()
    provider = make_provider()
    state = SSOState(
        state_token="token-1",
        nonce="nonce-1",
        provider_type=SSOProviderType.OIDC,
        tenant_id="tenant-1",
        redirect_uri="https://example.com/callback",
        expires_at=None,
    )
    result = asyncio.run(adapter.get_authorization_url(state, provider))
    assert "client_id=client-id" in result


@pytest.mark.asyncio
async def test_default_oidc_adapter_handle_callback_missing_code():
    adapter = DefaultOIDCAdapter()
    provider = make_provider()
    state = SSOState(
        state_token="token-1",
        nonce="nonce-1",
        provider_type=SSOProviderType.OIDC,
        tenant_id="tenant-1",
        redirect_uri="https://example.com/callback",
        expires_at=None,
    )
    state = SSOState(
        state_token="token-1",
        nonce="nonce-1",
        provider_type=SSOProviderType.OIDC,
        tenant_id="tenant-1",
        redirect_uri="https://example.com/callback",
        expires_at=None,
    )
    with pytest.raises(OIDCProviderError, match="Missing authorization code"):
        await adapter.handle_callback(state, provider, code=None)


@pytest.mark.asyncio
async def test_default_oidc_adapter_handle_callback_success():
    adapter = DefaultOIDCAdapter()
    provider = make_provider()
    state = SSOState(
        state_token="token-1",
        nonce="nonce-1",
        provider_type=SSOProviderType.OIDC,
        tenant_id="tenant-1",
        redirect_uri="https://example.com/callback",
        expires_at=None,
    )
    user_id, claims = await adapter.handle_callback(state, provider, code="auth-code")
    assert user_id == "mock-user-id"
    assert claims["email"] == "user@example.com"
