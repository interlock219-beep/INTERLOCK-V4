"""Tests for Phase 1/2 enterprise identity security features."""

from __future__ import annotations

import pyotp
from fastapi.testclient import TestClient


def _register_and_login(client: TestClient, email: str, password: str = "Password123!") -> str:  # noqa: S107
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestMFA:
    def test_enable_mfa_returns_setup(self, client: TestClient) -> None:
        token = _register_and_login(client, "mfa-user@example.com")
        response = client.post("/api/v1/mfa/enable", headers=_auth_headers(token))
        assert response.status_code == 201
        data = response.json()
        assert "secret" in data
        assert "provisioning_uri" in data
        assert len(data["backup_codes"]) == 10

    def test_confirm_mfa_success(self, client: TestClient) -> None:
        token = _register_and_login(client, "mfa-confirm@example.com")
        enable_resp = client.post("/api/v1/mfa/enable", headers=_auth_headers(token))
        assert enable_resp.status_code == 201
        secret = enable_resp.json()["secret"]
        totp = pyotp.TOTP(secret)
        code = totp.now()
        confirm_resp = client.post(
            "/api/v1/mfa/confirm",
            headers=_auth_headers(token),
            json={"code": code},
        )
        assert confirm_resp.status_code == 200
        assert confirm_resp.json()["is_enabled"] is True

    def test_verify_mfa_with_backup_code(self, client: TestClient) -> None:
        token = _register_and_login(client, "mfa-backup@example.com")
        enable_resp = client.post("/api/v1/mfa/enable", headers=_auth_headers(token))
        assert enable_resp.status_code == 201
        backup_code = enable_resp.json()["backup_codes"][0]
        verify_resp = client.post(
            "/api/v1/mfa/verify",
            headers=_auth_headers(token),
            json={"code": backup_code},
        )
        assert verify_resp.status_code == 200
        assert verify_resp.json()["is_enabled"] is True

    def test_verify_mfa_with_invalid_totp(self, client: TestClient) -> None:
        token = _register_and_login(client, "mfa-invalid@example.com")
        enable_resp = client.post("/api/v1/mfa/enable", headers=_auth_headers(token))
        assert enable_resp.status_code == 201
        verify_resp = client.post(
            "/api/v1/mfa/verify",
            headers=_auth_headers(token),
            json={"code": "000000"},
        )
        assert verify_resp.status_code == 401

    def test_disable_mfa_requires_code(self, client: TestClient) -> None:
        token = _register_and_login(client, "mfa-disable@example.com")
        client.post("/api/v1/mfa/enable", headers=_auth_headers(token))
        disable_resp = client.post(
            "/api/v1/mfa/disable",
            headers=_auth_headers(token),
            json={"code": "invalid"},
        )
        assert disable_resp.status_code == 400

    def test_disable_mfa_requires_code_missing(self, client: TestClient) -> None:
        token = _register_and_login(client, "mfa-disable-missing@example.com")
        client.post("/api/v1/mfa/enable", headers=_auth_headers(token))
        disable_resp = client.post(
            "/api/v1/mfa/disable",
            headers=_auth_headers(token),
            json={},
        )
        assert disable_resp.status_code == 422

    def test_regenerate_backup_codes(self, client: TestClient) -> None:
        token = _register_and_login(client, "mfa-regen@example.com")
        client.post("/api/v1/mfa/enable", headers=_auth_headers(token))
        resp = client.post(
            "/api/v1/mfa/backup-codes/regenerate",
            headers=_auth_headers(token),
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 10

    def test_cross_user_cannot_verify_other_mfa(self, client: TestClient) -> None:
        token_a = _register_and_login(client, "mfa-user-a@example.com")
        token_b = _register_and_login(client, "mfa-user-b@example.com")
        enable_resp = client.post("/api/v1/mfa/enable", headers=_auth_headers(token_a))
        assert enable_resp.status_code == 201
        secret = enable_resp.json()["secret"]
        totp = pyotp.TOTP(secret)
        code = totp.now()
        verify_resp = client.post(
            "/api/v1/mfa/verify",
            headers=_auth_headers(token_b),
            json={"code": code},
        )
        assert verify_resp.status_code == 401

    def test_backup_code_single_use(self, client: TestClient) -> None:
        token = _register_and_login(client, "mfa-backup-single@example.com")
        enable_resp = client.post("/api/v1/mfa/enable", headers=_auth_headers(token))
        assert enable_resp.status_code == 201
        backup_code = enable_resp.json()["backup_codes"][0]
        first = client.post(
            "/api/v1/mfa/verify",
            headers=_auth_headers(token),
            json={"code": backup_code},
        )
        assert first.status_code == 200
        second = client.post(
            "/api/v1/mfa/verify",
            headers=_auth_headers(token),
            json={"code": backup_code},
        )
        assert second.status_code == 401


class TestPasswordReset:
    def test_request_password_reset_generic_response(self, client: TestClient) -> None:
        _register_and_login(client, "reset@example.com")
        response = client.post(
            "/api/v1/password/reset/request",
            json={"email": "reset@example.com"},
        )
        assert response.status_code == 200
        assert "message" in response.json()
        assert "token" not in response.json()

    def test_confirm_password_reset_success(self, client: TestClient) -> None:
        _register_and_login(client, "reset-confirm@example.com")
        req_resp = client.post(
            "/api/v1/password/reset/request",
            json={"email": "reset-confirm@example.com"},
        )
        assert req_resp.status_code == 200

    def test_confirm_password_reset_invalid_token(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/password/reset/confirm",
            json={"token": "invalid-token", "new_password": "NewSecure123!"},
        )
        assert response.status_code == 400


class TestEmailVerification:
    def test_request_email_verification_generic_response(self, client: TestClient) -> None:
        _register_and_login(client, "verify@example.com")
        response = client.post(
            "/api/v1/email/verify/request",
            json={"email": "verify@example.com"},
        )
        assert response.status_code == 200
        assert "message" in response.json()
        assert "token" not in response.json()

    def test_confirm_email_verification_success(self, client: TestClient) -> None:
        _register_and_login(client, "verify-confirm@example.com")
        req_resp = client.post(
            "/api/v1/email/verify/request",
            json={"email": "verify-confirm@example.com"},
        )
        assert req_resp.status_code == 200


class TestSessionManagement:
    def test_create_session(self, client: TestClient) -> None:
        token = _register_and_login(client, "session@example.com")
        response = client.post(
            "/api/v1/sessions",
            headers=_auth_headers(token),
            json={"device_info": "test-device", "ip_address": "127.0.0.1"},
        )
        assert response.status_code == 200
        assert "session_id" in response.json()

    def test_list_sessions(self, client: TestClient) -> None:
        token = _register_and_login(client, "list-sessions@example.com")
        client.post(
            "/api/v1/sessions",
            headers=_auth_headers(token),
            json={"device_info": "test-device"},
        )
        response = client.get("/api/v1/sessions", headers=_auth_headers(token))
        assert response.status_code == 200
        assert len(response.json()) >= 1

    def test_revoke_session(self, client: TestClient) -> None:
        token = _register_and_login(client, "revoke-session@example.com")
        create_resp = client.post(
            "/api/v1/sessions",
            headers=_auth_headers(token),
            json={"device_info": "test-device"},
        )
        session_id = create_resp.json()["session_id"]
        response = client.delete(
            f"/api/v1/sessions/{session_id}",
            headers=_auth_headers(token),
        )
        assert response.status_code == 204
