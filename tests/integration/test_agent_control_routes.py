"""Tests for agent control API routes."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.domain.entities.user import User
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_user_repository import (
    SQLAlchemyUserRepository,
)
from app.infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher
from app.infrastructure.security.jwt_token_service import JWTTokenService


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, email: str, password: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert response.status_code == 201
    return response.json()


async def _create_user_with_role(*, email: str, role: str, tenant_id: str = "tenant-a") -> str:
    settings = get_settings()
    session = SessionLocal()
    try:
        repo = SQLAlchemyUserRepository(session)
        user = User(
            id=uuid4(),
            email=email,
            hashed_password=BcryptPasswordHasher(rounds=4).hash("SecurePass1!"),
            is_active=True,
            created_at=datetime.now(tz=UTC),
            role=role,
            tenant_id=tenant_id,
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


async def _create_session_for_user(
    client: TestClient, token: str, *, agent_id: str = "agent-1"
) -> str:
    response = client.post(
        "/api/v1/agent-sessions",
        json={"agent_id": agent_id, "intent_id": "intent-1"},
        headers=_auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["session_id"]


class TestAgentSessionRoutes:
    def test_create_session_requires_auth(self, client: TestClient) -> None:
        response = client.post("/api/v1/agent-sessions", json={})
        assert response.status_code == 401

    def test_create_session(self, client: TestClient) -> None:
        auth = _register(client, "session1@test.com", "SecurePass1!")
        response = client.post(
            "/api/v1/agent-sessions",
            json={"agent_id": "agent-1", "intent_id": "intent-1"},
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 201
        body = response.json()
        assert "session_id" in body
        assert body["status"] == "active"

    def test_get_session_requires_auth(self, client: TestClient) -> None:
        response = client.get("/api/v1/agent-sessions/ses-123")
        assert response.status_code == 401

    def test_get_session_not_found(self, client: TestClient) -> None:
        auth = _register(client, "session2@test.com", "SecurePass1!")
        response = client.get(
            "/api/v1/agent-sessions/nonexistent",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 404

    def test_freeze_session_requires_auth(self, client: TestClient) -> None:
        response = client.post("/api/v1/agent-sessions/ses-123/freeze")
        assert response.status_code == 401

    def test_freeze_session_not_found(self, client: TestClient) -> None:
        auth = _register(client, "session3@test.com", "SecurePass1!")
        response = client.post(
            "/api/v1/agent-sessions/nonexistent/freeze",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 404

    def test_freeze_session_unauthorized_existing_session(self, client: TestClient) -> None:
        import asyncio

        token = asyncio.run(_create_user_with_role(email="viewer-session@test.com", role="viewer"))
        session_id = asyncio.run(_create_session_for_user(client, token))

        response = client.post(
            f"/api/v1/agent-sessions/{session_id}/freeze",
            headers=_auth_header(token),
        )
        assert response.status_code == 403
        assert "Insufficient permissions" in response.json()["detail"]

    def test_freeze_session_authorized_existing_session(self, client: TestClient) -> None:
        import asyncio

        token = asyncio.run(_create_user_with_role(email="admin-session@test.com", role="admin"))
        session_id = asyncio.run(_create_session_for_user(client, token))

        response = client.post(
            f"/api/v1/agent-sessions/{session_id}/freeze",
            headers=_auth_header(token),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["session_id"] == session_id
        assert body["status"] == "frozen"

    def test_freeze_session_cross_tenant_not_found(self, client: TestClient) -> None:
        import asyncio

        owner_token = asyncio.run(
            _create_user_with_role(
                email="owner-session@test.com", role="admin", tenant_id="tenant-a"
            )
        )
        other_token = asyncio.run(
            _create_user_with_role(
                email="other-session@test.com", role="admin", tenant_id="tenant-b"
            )
        )
        session_id = asyncio.run(_create_session_for_user(client, owner_token))

        response = client.post(
            f"/api/v1/agent-sessions/{session_id}/freeze",
            headers=_auth_header(other_token),
        )
        assert response.status_code == 404

    def test_rollback_session_requires_auth(self, client: TestClient) -> None:
        response = client.post("/api/v1/agent-sessions/ses-123/rollback")
        assert response.status_code == 401

    def test_rollback_session_not_found(self, client: TestClient) -> None:
        auth = _register(client, "session4@test.com", "SecurePass1!")
        response = client.post(
            "/api/v1/agent-sessions/nonexistent/rollback",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 404

    def test_rollback_preview_requires_auth(self, client: TestClient) -> None:
        response = client.post("/api/v1/agent-sessions/ses-123/rollback/preview")
        assert response.status_code == 401

    def test_rollback_preview_not_found(self, client: TestClient) -> None:
        auth = _register(client, "session5@test.com", "SecurePass1!")
        response = client.post(
            "/api/v1/agent-sessions/nonexistent/rollback/preview",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 404


class TestIncidentRoutes:
    def test_create_incident_requires_auth(self, client: TestClient) -> None:
        response = client.post("/api/v1/incidents", json={})
        assert response.status_code == 401

    def test_create_incident(self, client: TestClient) -> None:
        auth = _register(client, "incident1@test.com", "SecurePass1!")
        response = client.post(
            "/api/v1/incidents",
            json={"agent_id": "agent-1", "severity": "high", "trigger": "anomaly"},
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 201
        body = response.json()
        assert "incident_id" in body
        assert body["status"] == "detected"

    def test_get_incident_requires_auth(self, client: TestClient) -> None:
        response = client.get("/api/v1/incidents/inc-123")
        assert response.status_code == 401

    def test_get_incident_not_found(self, client: TestClient) -> None:
        auth = _register(client, "incident2@test.com", "SecurePass1!")
        response = client.get(
            "/api/v1/incidents/nonexistent",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 404

    def test_list_incidents_requires_auth(self, client: TestClient) -> None:
        response = client.get("/api/v1/incidents")
        assert response.status_code == 401

    def test_update_incident_status_requires_auth(self, client: TestClient) -> None:
        response = client.patch("/api/v1/incidents/inc-123/status", json={})
        assert response.status_code == 401

    def test_update_incident_status_not_found(self, client: TestClient) -> None:
        auth = _register(client, "incident3@test.com", "SecurePass1!")
        response = client.patch(
            "/api/v1/incidents/nonexistent/status",
            json={"status": "RESOLVED"},
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 404


class TestActionRollbackRoutes:
    def test_rollback_action_requires_auth(self, client: TestClient) -> None:
        response = client.post("/api/v1/actions/act-123/rollback")
        assert response.status_code == 401

    def test_rollback_action_not_found(self, client: TestClient) -> None:
        auth = _register(client, "action1@test.com", "SecurePass1!")
        response = client.post(
            "/api/v1/actions/nonexistent/rollback",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 404


class TestAgentKillRevokeRoutes:
    def test_kill_agent_requires_auth(self, client: TestClient) -> None:
        response = client.post("/api/v1/agents/agent-123/kill", json={})
        assert response.status_code == 401

    def test_kill_agent_not_found(self, client: TestClient) -> None:
        auth = _register(client, "kill1@test.com", "SecurePass1!")
        response = client.post(
            "/api/v1/agents/nonexistent/kill",
            json={"reason": "test"},
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 404

    def test_revoke_agent_requires_auth(self, client: TestClient) -> None:
        response = client.post("/api/v1/agents/agent-123/revoke")
        assert response.status_code == 401

    def test_revoke_agent_not_found(self, client: TestClient) -> None:
        auth = _register(client, "revoke1@test.com", "SecurePass1!")
        response = client.post(
            "/api/v1/agents/nonexistent/revoke",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 404
