"""Tests for Phase 3 enterprise SSO (OIDC/SAML) API."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient


def _register_and_login(client: TestClient, email: str, password: str = "Password123!") -> str:  # noqa: S107
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return response.json()["access_token"]


def _seed_provider(client: TestClient) -> None:
    from app.infrastructure.config.settings import get_settings
    from app.infrastructure.persistence.database import SessionLocal
    from app.infrastructure.persistence.models.sso_models import (
        IdentityProviderModel,
        ProviderStatusEnum,
        ProviderTypeEnum,
    )

    get_settings.cache_clear()
    session = SessionLocal()
    try:
        existing = session.query(IdentityProviderModel).filter_by(name="mock-provider").first()
        if existing is None:
            provider = IdentityProviderModel(
                id=uuid4(),
                name="mock-provider",
                provider_type=ProviderTypeEnum.oidc,
                tenant_id=None,
                issuer="https://issuer.example.com",
                authorization_url="https://provider.example.com/authorize",
                token_url="https://provider.example.com/token",
                jwks_uri="https://provider.example.com/jwks",
                client_id="test-client",
                client_secret="test-secret",
                scopes="openid profile email",
                attribute_mapping="{}",
                saml_sso_url="",
                saml_entity_id="",
                saml_x509_cert="",
                status=ProviderStatusEnum.active,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            session.add(provider)
            session.commit()
    finally:
        session.close()


def _seed_sso_state_with_user(client: TestClient, user_id: UUID) -> None:
    from app.infrastructure.config.settings import get_settings
    from app.infrastructure.persistence.database import SessionLocal
    from app.infrastructure.persistence.models.sso_models import (
        ProviderTypeEnum,
        SSOStateModel,
        SSOStateStatusEnum,
    )

    get_settings.cache_clear()
    session = SessionLocal()
    try:
        existing = session.query(SSOStateModel).filter_by(state_token="mock-state-token").first()
        if existing is None:
            sso_state = SSOStateModel(
                id=uuid4(),
                state_token="mock-state-token",
                nonce="mock-nonce",
                provider_type=ProviderTypeEnum.oidc,
                tenant_id=None,
                redirect_uri="http://localhost:8000/api/v1/sso/callback",
                status=SSOStateStatusEnum.authorized,
                user_id=user_id,
                created_at=datetime.now(UTC),
                expires_at=datetime.now(UTC),
                consumed_at=datetime.now(UTC),
            )
            session.add(sso_state)
            session.commit()
    finally:
        session.close()


class TestSSOProviders:
    def test_list_providers_returns_empty_by_default(self, client: TestClient) -> None:
        response = client.get("/api/v1/sso/providers")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_providers_returns_seeded_provider(self, client: TestClient) -> None:
        _seed_provider(client)
        response = client.get("/api/v1/sso/providers")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "mock-provider"


class TestSSOAuthorize:
    def test_authorize_returns_redirect_for_unknown_provider(self, client: TestClient) -> None:
        response = client.post("/api/v1/sso/authorize", json={"provider_name": "unknown-provider"})
        assert response.status_code == 400
        assert "detail" in response.json()

    def test_authorize_returns_redirect_url_and_state(self, client: TestClient) -> None:
        _seed_provider(client)
        response = client.post("/api/v1/sso/authorize", json={"provider_name": "mock-provider"})
        assert response.status_code == 200
        data = response.json()
        assert "authorization_url" in data
        assert "state_token" in data


class TestSSOCallback:
    def test_callback_with_invalid_state_returns_401(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/sso/callback",
            json={"state_token": "invalid", "code": "code123"},
        )
        assert response.status_code == 401

    def test_callback_flow_returns_tokens(self, client: TestClient) -> None:
        _seed_provider(client)
        email = f"sso-user-{uuid4().hex[:8]}@example.com"
        client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Password123!"},
        )
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "Password123!"},
        )
        login_resp.json()["access_token"]

        from uuid import UUID

        from app.infrastructure.config.settings import get_settings
        from app.infrastructure.persistence.database import SessionLocal
        from app.infrastructure.persistence.models.user_model import UserModel

        get_settings.cache_clear()
        session = SessionLocal()
        try:
            user = session.query(UserModel).filter_by(email=email).first()
            assert user is not None
            _seed_sso_state_with_user(client, UUID(str(user.id)))
        finally:
            session.close()

        callback_resp = client.post(
            "/api/v1/sso/callback",
            json={"state_token": "mock-state-token", "code": "code123"},
        )
        assert callback_resp.status_code == 200
        data = callback_resp.json()
        assert "access_token" in data
        assert "token_type" in data
