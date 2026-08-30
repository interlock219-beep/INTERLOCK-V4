"""Tests for surgical recovery API routes."""

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


class TestGetRecoveryEvidence:
    def test_get_evidence_requires_auth(self, client: TestClient) -> None:
        response = client.get("/api/v1/recovery/evidence/ev-123")
        assert response.status_code == 401

    def test_get_evidence_not_found(self, client: TestClient) -> None:
        auth = _register(client, "evtest1@test.com", "SecurePass1!")
        response = client.get(
            "/api/v1/recovery/evidence/nonexistent",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 404


class TestListRecoveryEvidence:
    def test_list_evidence_requires_auth(self, client: TestClient) -> None:
        response = client.get("/api/v1/recovery/evidence?incident_id=inc-1")
        assert response.status_code == 401

    def test_list_evidence_requires_filter(self, client: TestClient) -> None:
        auth = _register(client, "evlist1@test.com", "SecurePass1!")
        response = client.get(
            "/api/v1/recovery/evidence",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 400


class TestListRecoveryExecutions:
    def test_list_executions_requires_auth(self, client: TestClient) -> None:
        response = client.get("/api/v1/recovery/executions?plan_id=plan-1")
        assert response.status_code == 401

    def test_list_executions_requires_filter(self, client: TestClient) -> None:
        auth = _register(client, "exlist1@test.com", "SecurePass1!")
        response = client.get(
            "/api/v1/recovery/executions",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 400


class TestGetRecoveryExecution:
    def test_get_execution_requires_auth(self, client: TestClient) -> None:
        response = client.get("/api/v1/recovery/executions/exec-123")
        assert response.status_code == 401

    def test_get_execution_not_found(self, client: TestClient) -> None:
        auth = _register(client, "extest1@test.com", "SecurePass1!")
        response = client.get(
            "/api/v1/recovery/executions/nonexistent",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 404


class TestGetSurgicalRecoveryPlan:
    def test_get_plan_requires_auth(self, client: TestClient) -> None:
        response = client.get("/api/v1/recovery/plan/plan-123")
        assert response.status_code == 401

    def test_get_plan_not_found(self, client: TestClient) -> None:
        auth = _register(client, "plantest1@test.com", "SecurePass1!")
        response = client.get(
            "/api/v1/recovery/plan/nonexistent",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 404


class TestCreateRecoveryPlan:
    def test_create_plan_requires_auth(self, client: TestClient) -> None:
        response = client.post("/api/v1/recovery/plan?incident_action_id=act-1")
        assert response.status_code == 401

    def test_create_plan_requires_incident_action_id(self, client: TestClient) -> None:
        auth = _register(client, "createplan1@test.com", "SecurePass1!")
        response = client.post(
            "/api/v1/recovery/plan",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 422


class TestSimulateRecoveryPlan:
    def test_simulate_plan_requires_auth(self, client: TestClient) -> None:
        response = client.post("/api/v1/recovery/plan/plan-1/simulate")
        assert response.status_code == 401


class TestExecuteRecoveryPlan:
    def test_execute_plan_requires_auth(self, client: TestClient) -> None:
        response = client.post("/api/v1/recovery/plan/plan-1/execute")
        assert response.status_code == 401
