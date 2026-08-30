"""Tests for agent control API routes."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, email: str, password: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert response.status_code == 201
    return response.json()


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
