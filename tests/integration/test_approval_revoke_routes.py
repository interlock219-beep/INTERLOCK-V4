"""Tests for approval API routes - covering revoke endpoint."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.domain.entities.user import User
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_user_repository import (
    SQLAlchemyUserRepository,
)
from app.infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher
from app.infrastructure.security.jwt_token_service import JWTTokenService


async def _create_user_with_role(*, email: str, role: str) -> str:
    settings = get_settings()
    session = SessionLocal()
    try:
        repo = SQLAlchemyUserRepository(session)
        user = User(
            id=__import__("uuid").uuid4(),
            email=email,
            hashed_password=BcryptPasswordHasher(rounds=4).hash("Password123!"),
            is_active=True,
            created_at=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
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


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestApprovalRevokeRoutes:
    def test_revoke_requires_auth(self, client: TestClient) -> None:
        response = client.post("/api/v1/approval/req-123/revoke")
        assert response.status_code == 401

    def test_revoke_nonexistent_request(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user_with_role(email="revokeviewer@test.com", role="operator"))
        response = client.post(
            "/api/v1/approval/nonexistent-id/revoke",
            headers=_auth_headers(token),
        )
        assert response.status_code == 404
        assert "detail" in response.json()

    @pytest.mark.asyncio
    async def test_revoke_success(self, client: TestClient) -> None:
        from app.presentation.api.v1.routes.approval import _hitl_queue
        _hitl_queue.reset()
        token = await _create_user_with_role(email="revokeuser@test.com", role="operator")
        request_id = await _hitl_queue.enqueue_request(intent_text="transfer $500", risk_score=0.85)
        await _hitl_queue.approve_request(request_id, decided_by=uuid4())

        response = client.post(
            f"/api/v1/approval/{request_id}/revoke",
            headers=_auth_headers(token),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["request_id"] == request_id
        assert data["status"] == "revoked"
        _hitl_queue.reset()

    def test_revoke_unauthorized_role(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user_with_role(email="revokeunauth@test.com", role="viewer"))
        response = client.post(
            "/api/v1/approval/req-123/revoke",
            headers=_auth_headers(token),
        )
        assert response.status_code == 403
        assert "Insufficient permissions" in response.json()["detail"]
