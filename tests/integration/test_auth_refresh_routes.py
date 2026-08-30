"""Tests for auth API routes - covering refresh token endpoint."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.domain.exceptions.domain_errors import AccountLockedError, AuthenticationError


def test_refresh_requires_token(client: TestClient) -> None:
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": ""})
    assert response.status_code == 401


def test_refresh_invalid_token(client: TestClient) -> None:
    with patch(
        "app.presentation.api.v1.routes.auth.RefreshTokenUseCase.execute",
        side_effect=AuthenticationError("Invalid token"),
    ):
        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid-token"},
        )
        assert response.status_code == 401


def test_refresh_inactive_user(client: TestClient) -> None:
    from app.domain.exceptions.domain_errors import InactiveUserError
    with patch(
        "app.presentation.api.v1.routes.auth.RefreshTokenUseCase.execute",
        side_effect=InactiveUserError("User inactive"),
    ):
        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "some-token"},
        )
        assert response.status_code == 401


def test_refresh_account_locked(client: TestClient) -> None:
    with patch(
        "app.presentation.api.v1.routes.auth.RefreshTokenUseCase.execute",
        side_effect=AccountLockedError("Account locked"),
    ):
        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "some-token"},
        )
        assert response.status_code == 403


def test_refresh_success(client: TestClient) -> None:
    with patch(
        "app.presentation.api.v1.routes.auth.RefreshTokenUseCase.execute",
        return_value={
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "token_type": "bearer",
        },
    ):
        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "valid-refresh-token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "new-access-token"
        assert data["refresh_token"] == "new-refresh-token"
        assert data["token_type"] == "bearer"
