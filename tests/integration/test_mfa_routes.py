"""Tests for MFA API routes."""

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.domain.entities.user import User
from app.domain.exceptions.domain_errors import AuthenticationError
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_user_repository import (
    SQLAlchemyUserRepository,
)
from app.infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher
from app.infrastructure.security.jwt_token_service import JWTTokenService


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_user(email: str, role: str = "viewer") -> str:
    settings = get_settings()
    session = SessionLocal()
    try:
        repo = SQLAlchemyUserRepository(session)
        user = User(
            id=uuid4(),
            email=email,
            hashed_password=BcryptPasswordHasher(rounds=4).hash("Password123!"),
            is_active=True,
            created_at=datetime.now(tz=UTC),
            role=role,
            tenant_id="test-tenant",
        )
        saved = await repo.save(user)
        token = JWTTokenService(
            secret_key=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
            expire_minutes=settings.jwt_access_token_expire_minutes,
            clock_skew_seconds=settings.jwt_clock_skew_seconds,
        ).create_access_token(user_id=saved.id, email=saved.email)
        session.commit()
        return token
    finally:
        session.close()


class TestMFARoutes:
    def test_enable_mfa_requires_auth(self, client: TestClient) -> None:
        response = client.post("/api/v1/mfa/enable")
        assert response.status_code == 401

    def test_enable_mfa_success(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("mfaenable@test.com"))
        with patch(
            "app.presentation.api.v1.routes.mfa.EnableMFAUseCase.execute",
            return_value={
                "secret": "secret123",
                "provisioning_uri": "otpauth://test",
                "backup_codes": ["code1", "code2", "code3"],
            },
        ):
            response = client.post(
                "/api/v1/mfa/enable",
                headers=_auth_header(token),
            )
            assert response.status_code == 201

    def test_enable_mfa_auth_error(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("mfaenableerr@test.com"))
        with patch(
            "app.presentation.api.v1.routes.mfa.EnableMFAUseCase.execute",
            side_effect=AuthenticationError("MFA already enabled"),
        ):
            response = client.post(
                "/api/v1/mfa/enable",
                headers=_auth_header(token),
            )
            assert response.status_code == 400

    def test_confirm_mfa_missing_code(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("mfaconfirm@test.com"))
        response = client.post(
            "/api/v1/mfa/confirm",
            headers=_auth_header(token),
            json={},
        )
        assert response.status_code == 422

    def test_confirm_mfa_success(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("mfaconfirmok@test.com"))
        with patch(
            "app.presentation.api.v1.routes.mfa.ConfirmMFAUseCase.execute",
            return_value={"is_enabled": True, "confirmed_at": None},
        ):
            response = client.post(
                "/api/v1/mfa/confirm",
                headers=_auth_header(token),
                json={"code": "123456"},
            )
            assert response.status_code == 200

    def test_verify_mfa_missing_code(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("mfaverify@test.com"))
        response = client.post(
            "/api/v1/mfa/verify",
            headers=_auth_header(token),
            json={},
        )
        assert response.status_code == 422

    def test_verify_mfa_success(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("mfaverifyok@test.com"))
        with patch(
            "app.presentation.api.v1.routes.mfa.VerifyMFAUseCase.execute",
            return_value={"is_enabled": True},
        ):
            response = client.post(
                "/api/v1/mfa/verify",
                headers=_auth_header(token),
                json={"code": "123456"},
            )
            assert response.status_code == 200

    def test_verify_mfa_auth_error(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("mfaverifyerr@test.com"))
        with patch(
            "app.presentation.api.v1.routes.mfa.VerifyMFAUseCase.execute",
            side_effect=AuthenticationError("Invalid code"),
        ):
            response = client.post(
                "/api/v1/mfa/verify",
                headers=_auth_header(token),
                json={"code": "000000"},
            )
            assert response.status_code == 401

    def test_disable_mfa_missing_code(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("mfadisable@test.com"))
        response = client.post(
            "/api/v1/mfa/disable",
            headers=_auth_header(token),
            json={},
        )
        assert response.status_code == 422

    def test_disable_mfa_success(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("mfadisableok@test.com"))
        with patch(
            "app.presentation.api.v1.routes.mfa.DisableMFAUseCase.execute",
            return_value=None,
        ):
            response = client.post(
                "/api/v1/mfa/disable",
                headers=_auth_header(token),
                json={"code": "123456"},
            )
            assert response.status_code == 204

    def test_disable_mfa_auth_error(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("mfadisableerr@test.com"))
        with patch(
            "app.presentation.api.v1.routes.mfa.DisableMFAUseCase.execute",
            side_effect=AuthenticationError("Invalid code"),
        ):
            response = client.post(
                "/api/v1/mfa/disable",
                headers=_auth_header(token),
                json={"code": "000000"},
            )
            assert response.status_code == 400

    def test_regenerate_backup_codes(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("mfabackup@test.com"))
        with patch(
            "app.domain.services.identity_services.PyOTPMFAService.regenerate_backup_codes",
            return_value=["code1", "code2", "code3"],
        ):
            response = client.post(
                "/api/v1/mfa/backup-codes/regenerate",
                headers=_auth_header(token),
            )
            assert response.status_code == 200
            assert len(response.json()) == 3

    def test_regenerate_backup_codes_auth_error(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("mfabackuperr@test.com"))
        with patch(
            "app.domain.services.identity_services.PyOTPMFAService.regenerate_backup_codes",
            side_effect=AuthenticationError("MFA not enabled"),
        ):
            response = client.post(
                "/api/v1/mfa/backup-codes/regenerate",
                headers=_auth_header(token),
            )
            assert response.status_code == 400


class TestPasswordResetRoutes:
    def test_request_password_reset(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/password/reset/request",
            json={"email": "reset@test.com"},
        )
        assert response.status_code == 200
        assert "message" in response.json()

    def test_confirm_password_reset(self, client: TestClient) -> None:
        with patch(
            "app.presentation.api.v1.routes.mfa.ConfirmPasswordResetUseCase.execute",
            return_value=None,
        ):
            response = client.post(
                "/api/v1/password/reset/confirm",
                json={"token": "some-token", "new_password": "NewPass123!"},
            )
            assert response.status_code == 200

    def test_confirm_password_reset_auth_error(self, client: TestClient) -> None:
        with patch(
            "app.presentation.api.v1.routes.mfa.ConfirmPasswordResetUseCase.execute",
            side_effect=AuthenticationError("Invalid token"),
        ):
            response = client.post(
                "/api/v1/password/reset/confirm",
                json={"token": "bad-token", "new_password": "NewPass123!"},
            )
            assert response.status_code == 400


class TestEmailVerificationRoutes:
    def test_request_email_verification(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/email/verify/request",
            json={"email": "verify@test.com"},
        )
        assert response.status_code == 200
        assert "message" in response.json()

    def test_confirm_email_verification(self, client: TestClient) -> None:
        with patch(
            "app.presentation.api.v1.routes.mfa.ConfirmEmailVerificationUseCase.execute",
            return_value=None,
        ):
            response = client.post(
                "/api/v1/email/verify/confirm",
                json={"token": "some-token"},
            )
            assert response.status_code == 200

    def test_confirm_email_verification_auth_error(self, client: TestClient) -> None:
        with patch(
            "app.presentation.api.v1.routes.mfa.ConfirmEmailVerificationUseCase.execute",
            side_effect=AuthenticationError("Invalid token"),
        ):
            response = client.post(
                "/api/v1/email/verify/confirm",
                json={"token": "bad-token"},
            )
            assert response.status_code == 400
