"""Tests for actions API routes."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.domain.entities.protected_action import ActionStatus, ProtectedAction, Reversibility
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_protected_action_repository import (
    SQLAlchemyProtectedActionRepository,
)


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, email: str, password: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert response.status_code == 201
    return response.json()


async def _seed_action(tenant_id: str, action_id: str, **kwargs) -> ProtectedAction:
    session = SessionLocal()
    try:
        repo = SQLAlchemyProtectedActionRepository(session)
        action = ProtectedAction(
            action_id=action_id,
            tenant_id=tenant_id,
            actor_user_id=uuid4(),
            agent_id=kwargs.get("agent_id", "agent-1"),
            authority_grant_id=kwargs.get("authority_grant_id"),
            tool=kwargs.get("tool", "search"),
            resource=kwargs.get("resource", "res-1"),
            action_type=kwargs.get("action_type", "execute"),
            correlation_id=kwargs.get("correlation_id", ""),
            parent_action_id=kwargs.get("parent_action_id"),
            workflow_id=kwargs.get("workflow_id"),
            tool_arguments=kwargs.get("tool_arguments", {}),
            before_state_ref=kwargs.get("before_state_ref"),
            status=kwargs.get("status", ActionStatus.PENDING),
            reversibility=kwargs.get("reversibility", Reversibility.AUTOMATICALLY_REVERSIBLE),
            created_at=datetime.now(UTC),
        )
        saved = await repo.save(action)
        session.commit()
        return saved
    finally:
        session.close()


class TestActionsRoutes:
    def test_create_action_requires_auth(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/actions/",
            json={
                "agent_id": "agent-1",
                "tool": "search",
                "resource": "res-1",
                "action_type": "execute",
            },
        )
        assert response.status_code == 401

    def test_create_action_success(self, client: TestClient) -> None:
        auth = _register(client, "actions@test.com", "SecurePass1!")
        response = client.post(
            "/api/v1/actions/",
            headers=_auth_header(auth["access_token"]),
            json={
                "agent_id": "agent-1",
                "tool": "search",
                "resource": "res-1",
                "action_type": "execute",
                "correlation_id": "corr-123",
                "tool_arguments": {"q": "test"},
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["action_id"].startswith("act-")
        assert data["agent_id"] == "agent-1"
        assert data["tool"] == "search"
        assert data["resource"] == "res-1"
        assert data["action_type"] == "execute"
        assert data["status"] == "pending"
        assert data["correlation_id"] == "corr-123"

    def test_list_actions_requires_auth(self, client: TestClient) -> None:
        response = client.get("/api/v1/actions/")
        assert response.status_code == 401

    def test_list_actions_requires_filter(self, client: TestClient) -> None:
        auth = _register(client, "actionsfilter@test.com", "SecurePass1!")
        response = client.get(
            "/api/v1/actions/",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 400
        assert "agent_id or correlation_id required" in response.json()["detail"]

    def test_list_actions_by_agent(self, client: TestClient) -> None:
        auth = _register(client, "actionsbyagent@test.com", "SecurePass1!")
        tenant_id = auth["user"]["tenant_id"] or ""
        import asyncio
        asyncio.run(_seed_action(tenant_id, "act-list-1", agent_id="agent-list"))
        asyncio.run(_seed_action(tenant_id, "act-list-2", agent_id="agent-list"))
        response = client.get(
            "/api/v1/actions/",
            headers=_auth_header(auth["access_token"]),
            params={"agent_id": "agent-list"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_list_actions_by_correlation(self, client: TestClient) -> None:
        auth = _register(client, "actionsbycorr@test.com", "SecurePass1!")
        tenant_id = auth["user"]["tenant_id"] or ""
        import asyncio
        asyncio.run(_seed_action(tenant_id, "act-corr-1", correlation_id="corr-abc"))
        response = client.get(
            "/api/v1/actions/",
            headers=_auth_header(auth["access_token"]),
            params={"correlation_id": "corr-abc"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["correlation_id"] == "corr-abc"

    def test_evaluate_action_not_found(self, client: TestClient) -> None:
        auth = _register(client, "evalnotfound@test.com", "SecurePass1!")
        response = client.post(
            "/api/v1/actions/nonexistent/evaluate",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 404

    def test_evaluate_action_already_evaluated(self, client: TestClient) -> None:
        auth = _register(client, "evalalready@test.com", "SecurePass1!")
        tenant_id = auth["user"]["tenant_id"] or ""
        import asyncio
        asyncio.run(_seed_action(tenant_id, "act-eval-done", status=ActionStatus.PERMITTED))
        response = client.post(
            "/api/v1/actions/act-eval-done/evaluate",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 400
        assert "already" in response.json()["detail"]

    def test_get_upstream_actions(self, client: TestClient) -> None:
        auth = _register(client, "upstream@test.com", "SecurePass1!")
        tenant_id = auth["user"]["tenant_id"] or ""
        import asyncio
        asyncio.run(_seed_action(tenant_id, "act-upstream-1"))
        response = client.get(
            "/api/v1/actions/act-upstream-1/upstream",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["action_id"] == "act-upstream-1"
        assert "upstream" in data

    def test_get_downstream_actions(self, client: TestClient) -> None:
        auth = _register(client, "downstream@test.com", "SecurePass1!")
        tenant_id = auth["user"]["tenant_id"] or ""
        import asyncio
        asyncio.run(_seed_action(tenant_id, "act-downstream-1"))
        response = client.get(
            "/api/v1/actions/act-downstream-1/downstream",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["action_id"] == "act-downstream-1"
        assert "downstream" in data

    def test_get_incident_graph(self, client: TestClient) -> None:
        auth = _register(client, "graph@test.com", "SecurePass1!")
        tenant_id = auth["user"]["tenant_id"] or ""
        import asyncio
        asyncio.run(_seed_action(tenant_id, "act-graph-1"))
        response = client.get(
            "/api/v1/actions/act-graph-1/graph",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 200
        data = response.json()
        assert "root_action_id" in data
        assert "nodes" in data
        assert "edges" in data
