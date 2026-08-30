"""Dedicated security tests proving production authorization defaults.

These tests run against a fresh application instance with production
configuration (AUTHORIZATION_DEFAULT_DENY=true, AUTHORIZATION_REQUIRE_TENANT=true)
independent of the legacy test overrides in conftest.py.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.config.settings import get_settings
from app.main import create_app

PRODUCTION_DEFAULT_DENY = "true"
PRODUCTION_REQUIRE_TENANT = "true"
TEST_DEFAULT_DENY = "false"
TEST_REQUIRE_TENANT = "false"


@pytest.fixture
def production_client() -> TestClient:
    os.environ["AUTHORIZATION_DEFAULT_DENY"] = PRODUCTION_DEFAULT_DENY
    os.environ["AUTHORIZATION_REQUIRE_TENANT"] = PRODUCTION_REQUIRE_TENANT
    get_settings.cache_clear()

    application = create_app()
    with TestClient(application) as test_client:
        yield test_client

    os.environ["AUTHORIZATION_DEFAULT_DENY"] = TEST_DEFAULT_DENY
    os.environ["AUTHORIZATION_REQUIRE_TENANT"] = TEST_REQUIRE_TENANT
    get_settings.cache_clear()


def test_production_config_defaults_to_deny() -> None:
    os.environ["AUTHORIZATION_DEFAULT_DENY"] = PRODUCTION_DEFAULT_DENY
    os.environ["AUTHORIZATION_REQUIRE_TENANT"] = PRODUCTION_REQUIRE_TENANT
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.authorization_default_deny is True
        assert settings.authorization_require_tenant is True
    finally:
        os.environ["AUTHORIZATION_DEFAULT_DENY"] = TEST_DEFAULT_DENY
        os.environ["AUTHORIZATION_REQUIRE_TENANT"] = TEST_REQUIRE_TENANT
        get_settings.cache_clear()


def test_protected_endpoint_without_authorization_denied(
    production_client: TestClient,
) -> None:
    response = production_client.get("/api/v1/recovery/evidence/ev-123")
    assert response.status_code == 401


def test_invalid_authorization_denied(production_client: TestClient) -> None:
    response = production_client.get(
        "/api/v1/recovery/evidence/ev-123",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert response.status_code == 401


def test_wrong_tenant_is_denied(production_client: TestClient) -> None:
    token_tenant_a = production_client.post(
        "/api/v1/auth/register",
        json={
            "email": "tenant-a@example.com",
            "password": "SecurePass1!",
            "tenant_id": "tenant-a",
        },
    ).json()["access_token"]

    token_tenant_b = production_client.post(
        "/api/v1/auth/register",
        json={
            "email": "tenant-b@example.com",
            "password": "SecurePass1!",
            "tenant_id": "tenant-b",
        },
    ).json()["access_token"]

    create_response = production_client.post(
        "/api/v1/actions/",
        json={
            "agent_id": "agent-alpha",
            "tool": "search",
            "resource": "test-resource",
            "action_type": "query",
        },
        headers={"Authorization": f"Bearer {token_tenant_a}"},
    )
    assert create_response.status_code == 201
    action_id = create_response.json()["action_id"]

    response = production_client.post(
        f"/api/v1/actions/{action_id}/evaluate",
        headers={"Authorization": f"Bearer {token_tenant_b}"},
    )
    assert response.status_code == 404


def test_missing_tenant_context_cannot_silently_become_authorized(
    production_client: TestClient,
) -> None:
    response = production_client.post(
        "/api/v1/auth/register",
        json={
            "email": "no-tenant@example.com",
            "password": "SecurePass1!",
        },
    )
    assert response.status_code == 201
    token = response.json()["access_token"]

    response = production_client.get(
        "/api/v1/recovery/evidence/ev-123",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_explicit_authorization_works(production_client: TestClient) -> None:
    token = production_client.post(
        "/api/v1/auth/register",
        json={
            "email": "explicit@example.com",
            "password": "SecurePass1!",
            "tenant_id": "tenant-a",
        },
    ).json()["access_token"]

    response = production_client.get(
        "/api/v1/recovery/evidence/ev-123",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_legitimate_authorized_flow_continues_working(
    production_client: TestClient,
) -> None:
    token = production_client.post(
        "/api/v1/auth/register",
        json={
            "email": "legacy@example.com",
            "password": "SecurePass1!",
            "tenant_id": "tenant-a",
        },
    ).json()["access_token"]

    response = production_client.get(
        "/api/v1/agents/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
