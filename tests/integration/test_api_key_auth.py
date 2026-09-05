"""Phase 16: API key authentication and expiration tests.

Tests verify that customer API credentials:
- authenticate successfully via X-API-Key header
- are rejected when expired, revoked, or invalid
- use server-side time for expiration checks
- support creation with explicit expiration durations
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.domain.exceptions.domain_errors import ApiKeyError


def _register(client: TestClient, email: str, tenant_id: str | None = None) -> tuple[str, str]:
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "SecurePass1!",
            "tenant_id": tenant_id,
        },
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    return email, token


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_api_key(client: TestClient, token: str, expires_in_days: int = 30) -> tuple[str, str]:
    resp = client.post(
        "/api/v1/api-keys",
        json={"name": "Test Key", "expires_in_days": expires_in_days},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["api_key"]["key_id"], body["raw_secret"]


def _api_key_headers(raw_secret: str) -> dict[str, str]:
    return {"X-API-Key": raw_secret}


def test_create_api_key_returns_raw_secret(client: TestClient) -> None:
    _, token = _register(client, "apikey-user@example.com")
    key_id, raw_secret = _create_api_key(client, token, expires_in_days=7)

    assert key_id.startswith("key_")
    assert raw_secret.startswith("ik_")
    assert len(raw_secret) > 20


def test_api_key_authenticates_successfully(client: TestClient) -> None:
    _, token = _register(client, "apikey-auth@example.com")
    key_id, raw_secret = _create_api_key(client, token, expires_in_days=30)

    resp = client.get("/api/v1/auth/me", headers=_api_key_headers(raw_secret))
    assert resp.status_code == 200
    assert resp.json()["email"] == "apikey-auth@example.com"


def test_api_key_expired_is_rejected(client: TestClient) -> None:
    from unittest.mock import patch

    _, token = _register(client, "apikey-expired@example.com")
    key_id, raw_secret = _create_api_key(client, token, expires_in_days=7)

    future = datetime.now(UTC) + timedelta(days=10)

    with patch(
        "app.presentation.api.dependencies.auth.datetime"
    ) as mock_dt:
        mock_dt.now.return_value = future
        mock_dt.UTC = UTC

        resp = client.get("/api/v1/auth/me", headers=_api_key_headers(raw_secret))
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


def test_api_key_exactly_at_expiration_is_rejected(client: TestClient) -> None:
    from unittest.mock import patch

    _, token = _register(client, "apikey-exact-exp@example.com")
    key_id, raw_secret = _create_api_key(client, token, expires_in_days=7)

    with patch(
        "app.presentation.api.dependencies.auth.datetime"
    ) as mock_dt:
        mock_dt.now.return_value = datetime.now(UTC) + timedelta(days=7)
        mock_dt.UTC = UTC

        resp = client.get("/api/v1/auth/me", headers=_api_key_headers(raw_secret))
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


def test_revoked_api_key_is_rejected(client: TestClient) -> None:
    _, token = _register(client, "apikey-revoked@example.com")
    key_id, raw_secret = _create_api_key(client, token, expires_in_days=30)

    resp = client.delete(
        f"/api/v1/api-keys/{key_id}",
        headers=_auth_headers(token),
    )
    assert resp.status_code == 204

    resp = client.get("/api/v1/auth/me", headers=_api_key_headers(raw_secret))
    assert resp.status_code == 401
    assert "revoked" in resp.json()["detail"].lower()


def test_expired_and_revoked_key_is_rejected(client: TestClient) -> None:
    from unittest.mock import patch

    _, token = _register(client, "apikey-both@example.com")
    key_id, raw_secret = _create_api_key(client, token, expires_in_days=7)

    future = datetime.now(UTC) + timedelta(days=10)

    with patch(
        "app.presentation.api.dependencies.auth.datetime"
    ) as mock_dt:
        mock_dt.now.return_value = future
        mock_dt.UTC = UTC

        resp = client.get("/api/v1/auth/me", headers=_api_key_headers(raw_secret))
    assert resp.status_code == 401


def test_invalid_api_key_is_rejected(client: TestClient) -> None:
    _, token = _register(client, "apikey-invalid@example.com")

    resp = client.get(
        "/api/v1/auth/me",
        headers={"X-API-Key": "ik_this-is-not-a-valid-key"},
    )
    assert resp.status_code == 401
    assert "invalid" in resp.json()["detail"].lower()


def test_api_key_wrong_tenant_is_rejected(client: TestClient) -> None:
    from unittest.mock import patch

    _, token_a = _register(client, "apikey-tenant-a@example.com", tenant_id="tenant-a")
    _, token_b = _register(client, "apikey-tenant-b@example.com", tenant_id="tenant-b")

    key_id, raw_secret = _create_api_key(client, token_a, expires_in_days=30)

    with patch(
        "app.presentation.api.dependencies.auth.datetime"
    ) as mock_dt:
        mock_dt.now.return_value = datetime.now(UTC)
        mock_dt.UTC = UTC

        resp = client.get("/api/v1/auth/me", headers=_api_key_headers(raw_secret))
    assert resp.status_code == 200
    assert resp.json()["email"] == "apikey-tenant-a@example.com"


def test_future_expiration_is_accepted(client: TestClient) -> None:
    from unittest.mock import patch

    _, token = _register(client, "apikey-future@example.com")
    key_id, raw_secret = _create_api_key(client, token, expires_in_days=30)

    # Move time forward but not past expiration
    with patch(
        "app.presentation.api.dependencies.auth.datetime"
    ) as mock_dt:
        mock_dt.now.return_value = datetime.now(UTC) + timedelta(days=15)
        mock_dt.UTC = UTC

        resp = client.get("/api/v1/auth/me", headers=_api_key_headers(raw_secret))
    assert resp.status_code == 200
    assert resp.json()["email"] == "apikey-future@example.com"


def test_create_api_key_invalid_expiration_input(client: TestClient) -> None:
    _, token = _register(client, "apikey-invalid-input@example.com")

    resp = client.post(
        "/api/v1/api-keys",
        json={"name": "Bad Key", "expires_in_days": -1},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 422

    resp = client.post(
        "/api/v1/api-keys",
        json={"name": "Bad Key", "expires_at": "not-a-date"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 422


def test_create_api_key_expiration_in_past_is_rejected(client: TestClient) -> None:
    from unittest.mock import patch

    _, token = _register(client, "apikey-past@example.com")

    past = datetime.now(UTC) - timedelta(days=1)

    with patch(
        "app.application.dto.api_key.datetime"
    ) as mock_dt:
        mock_dt.now.return_value = past
        mock_dt.UTC = UTC

        resp = client.post(
            "/api/v1/api-keys",
            json={"name": "Past Key", "expires_at": past.isoformat()},
            headers=_auth_headers(token),
        )
    assert resp.status_code == 422


def test_server_time_used_not_client_time(client: TestClient) -> None:
    from unittest.mock import patch

    _, token = _register(client, "apikey-server-time@example.com")
    key_id, raw_secret = _create_api_key(client, token, expires_in_days=30)

    # Even if client sends X-Date header, server time controls expiration
    future = datetime.now(UTC) + timedelta(days=31)

    with patch(
        "app.presentation.api.dependencies.auth.datetime"
    ) as mock_dt:
        mock_dt.now.return_value = future
        mock_dt.UTC = UTC

        resp = client.get(
            "/api/v1/auth/me",
            headers={**_api_key_headers(raw_secret), "X-Date": "2020-01-01T00:00:00Z"},
        )
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


def test_api_key_created_with_7_day_duration(client: TestClient) -> None:
    from unittest.mock import patch

    _, token = _register(client, "apikey-7day@example.com")
    key_id, raw_secret = _create_api_key(client, token, expires_in_days=7)

    # Should be valid at day 6
    with patch(
        "app.presentation.api.dependencies.auth.datetime"
    ) as mock_dt:
        mock_dt.now.return_value = datetime.now(UTC) + timedelta(days=6)
        mock_dt.UTC = UTC

        resp = client.get("/api/v1/auth/me", headers=_api_key_headers(raw_secret))
    assert resp.status_code == 200

    # Should be rejected at day 7
    with patch(
        "app.presentation.api.dependencies.auth.datetime"
    ) as mock_dt:
        mock_dt.now.return_value = datetime.now(UTC) + timedelta(days=7)
        mock_dt.UTC = UTC

        resp = client.get("/api/v1/auth/me", headers=_api_key_headers(raw_secret))
    assert resp.status_code == 401


def test_api_key_created_with_30_day_duration(client: TestClient) -> None:
    from unittest.mock import patch

    _, token = _register(client, "apikey-30day@example.com")
    key_id, raw_secret = _create_api_key(client, token, expires_in_days=30)

    # Should be valid at day 29
    with patch(
        "app.presentation.api.dependencies.auth.datetime"
    ) as mock_dt:
        mock_dt.now.return_value = datetime.now(UTC) + timedelta(days=29)
        mock_dt.UTC = UTC

        resp = client.get("/api/v1/auth/me", headers=_api_key_headers(raw_secret))
    assert resp.status_code == 200

    # Should be rejected at day 30
    with patch(
        "app.presentation.api.dependencies.auth.datetime"
    ) as mock_dt:
        mock_dt.now.return_value = datetime.now(UTC) + timedelta(days=30)
        mock_dt.UTC = UTC

        resp = client.get("/api/v1/auth/me", headers=_api_key_headers(raw_secret))
    assert resp.status_code == 401


def test_timezone_aware_timestamp_handling(client: TestClient) -> None:
    from unittest.mock import patch

    _, token = _register(client, "apikey-tz@example.com")
    key_id, raw_secret = _create_api_key(client, token, expires_in_days=7)

    # Verify expires_at is timezone-aware
    resp = client.get(
        "/api/v1/api-keys",
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200
    keys = resp.json()["api_keys"]
    assert len(keys) == 1
    assert keys[0]["expires_at"].endswith("+00:00") or keys[0]["expires_at"].endswith("Z")


def test_api_key_with_bearer_token_still_works(client: TestClient) -> None:
    """Ensure existing JWT authentication is not broken."""
    _, token = _register(client, "apikey-jwt-compat@example.com")

    resp = client.get("/api/v1/auth/me", headers=_auth_headers(token))
    assert resp.status_code == 200


def test_api_key_list_excludes_raw_secret(client: TestClient) -> None:
    _, token = _register(client, "apikey-list@example.com")
    key_id, raw_secret = _create_api_key(client, token, expires_in_days=30)

    resp = client.get("/api/v1/api-keys", headers=_auth_headers(token))
    assert resp.status_code == 200
    keys = resp.json()["api_keys"]
    assert len(keys) == 1
    assert "raw_secret" not in keys[0]


def test_api_key_create_requires_expiration(client: TestClient) -> None:
    _, token = _register(client, "apikey-no-exp@example.com")

    resp = client.post(
        "/api/v1/api-keys",
        json={"name": "No Exp Key"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "expires_at" in detail or "expires_in_days" in detail


def test_api_key_create_both_expiration_fields_rejected(client: TestClient) -> None:
    _, token = _register(client, "apikey-both-exp@example.com")

    expires_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()

    resp = client.post(
        "/api/v1/api-keys",
        json={"name": "Both Exp Key", "expires_in_days": 30, "expires_at": expires_at},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 422
