"""Phase 15: Cross-tenant isolation security tests.

Tests verify that resources created in one tenant are inaccessible
to users authenticated under a different tenant across all major
domain boundaries: agents, authority grants, protected actions,
containment events, recovery plans, and blast radius calculations.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def _register(client: TestClient, email: str, tenant_id: str, role: str = "admin") -> str:
    client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "SecurePass1!",
            "tenant_id": tenant_id,
        },
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "SecurePass1!"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_agent(client: TestClient, token: str, agent_id: str) -> None:
    resp = client.post(
        "/api/v1/agents/",
        json={
            "agent_id": agent_id,
            "name": f"Agent {agent_id}",
            "agent_type": "service_agent",
        },
        headers=_auth_headers(token),
    )
    assert resp.status_code == 201


def _create_grant(
    client: TestClient, token: str, grantor: str, grantee: str, scope: str = "read"
) -> str:
    resp = client.post(
        "/api/v1/authority/",
        json={
            "grantor_agent_id": grantor,
            "grantee_agent_id": grantee,
            "scope": scope,
            "resource": "test-resource",
        },
        headers=_auth_headers(token),
    )
    assert resp.status_code == 201
    return resp.json()["grant_id"]


def _create_action(client: TestClient, token: str, agent_id: str) -> str:
    resp = client.post(
        "/api/v1/actions/",
        json={
            "agent_id": agent_id,
            "tool": "search",
            "resource": "test-resource",
            "action_type": "query",
        },
        headers=_auth_headers(token),
    )
    assert resp.status_code == 201
    return resp.json()["action_id"]


# ---------------------------------------------------------------------------
# Cross-tenant agent isolation
# ---------------------------------------------------------------------------


def test_cross_tenant_cannot_list_other_tenant_agents(client: TestClient) -> None:
    token_a = _register(client, f"agent-a-{uuid.uuid4()}@example.com", "tenant-a")
    token_b = _register(client, f"agent-b-{uuid.uuid4()}@example.com", "tenant-b")

    _create_agent(client, token_a, "agent-alpha")

    resp = client.get("/api/v1/agents/", headers=_auth_headers(token_b))
    assert resp.status_code == 200
    data = resp.json()
    assert all(a["tenant_id"] == "tenant-b" for a in data["items"])


def test_cross_tenant_cannot_read_other_tenant_agent(client: TestClient) -> None:
    token_a = _register(client, f"agent-a-{uuid.uuid4()}@example.com", "tenant-a")
    token_b = _register(client, f"agent-b-{uuid.uuid4()}@example.com", "tenant-b")

    _create_agent(client, token_a, "agent-alpha")

    resp = client.get("/api/v1/agents/agent-alpha", headers=_auth_headers(token_b))
    assert resp.status_code == 404


def test_cross_tenant_cannot_update_other_tenant_agent(client: TestClient) -> None:
    token_a = _register(client, f"agent-a-{uuid.uuid4()}@example.com", "tenant-a")
    token_b = _register(client, f"agent-b-{uuid.uuid4()}@example.com", "tenant-b")

    _create_agent(client, token_a, "agent-alpha")

    resp = client.patch(
        "/api/v1/agents/agent-alpha",
        json={"name": "Hacked"},
        headers=_auth_headers(token_b),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Cross-tenant authority grant isolation
# ---------------------------------------------------------------------------


def test_cross_tenant_cannot_view_other_tenant_grant(client: TestClient) -> None:
    token_a = _register(client, f"auth-a-{uuid.uuid4()}@example.com", "tenant-a")
    token_b = _register(client, f"auth-b-{uuid.uuid4()}@example.com", "tenant-b")

    _create_agent(client, token_a, "grantor-a")
    _create_agent(client, token_a, "grantee-a")
    grant_id = _create_grant(client, token_a, "grantor-a", "grantee-a")

    resp = client.get(f"/api/v1/authority/{grant_id}", headers=_auth_headers(token_b))
    assert resp.status_code == 404


def test_cross_tenant_cannot_revoke_other_tenant_grant(client: TestClient) -> None:
    token_a = _register(client, f"auth-a-{uuid.uuid4()}@example.com", "tenant-a")
    token_b = _register(client, f"auth-b-{uuid.uuid4()}@example.com", "tenant-b")

    _create_agent(client, token_a, "grantor-a")
    _create_agent(client, token_a, "grantee-a")
    grant_id = _create_grant(client, token_a, "grantor-a", "grantee-a")

    resp = client.post(
        f"/api/v1/authority/{grant_id}/revoke",
        headers=_auth_headers(token_b),
    )
    assert resp.status_code == 404


def test_cross_tenant_cannot_list_other_tenant_grants(client: TestClient) -> None:
    token_a = _register(client, f"auth-a-{uuid.uuid4()}@example.com", "tenant-a")
    token_b = _register(client, f"auth-b-{uuid.uuid4()}@example.com", "tenant-b")

    _create_agent(client, token_a, "grantor-a")
    _create_agent(client, token_a, "grantee-a")
    _create_grant(client, token_a, "grantor-a", "grantee-a")

    resp = client.get(
        "/api/v1/authority/",
        params={"grantee_agent_id": "grantee-a"},
        headers=_auth_headers(token_b),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# Cross-tenant protected action isolation
# ---------------------------------------------------------------------------


def test_cross_tenant_cannot_list_other_tenant_actions(client: TestClient) -> None:
    token_a = _register(client, f"act-a-{uuid.uuid4()}@example.com", "tenant-a")
    token_b = _register(client, f"act-b-{uuid.uuid4()}@example.com", "tenant-b")

    _create_agent(client, token_a, "agent-a")
    _create_action(client, token_a, "agent-a")

    resp = client.get(
        "/api/v1/actions/",
        params={"agent_id": "agent-a"},
        headers=_auth_headers(token_b),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_cross_tenant_cannot_evaluate_other_tenant_action(client: TestClient) -> None:
    token_a = _register(client, f"act-a-{uuid.uuid4()}@example.com", "tenant-a")
    token_b = _register(client, f"act-b-{uuid.uuid4()}@example.com", "tenant-b")

    _create_agent(client, token_a, "agent-a")
    action_id = _create_action(client, token_a, "agent-a")

    resp = client.post(
        f"/api/v1/actions/{action_id}/evaluate",
        headers=_auth_headers(token_b),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Cross-tenant containment isolation
# ---------------------------------------------------------------------------


def test_cross_tenant_cannot_contain_other_tenant_agent(client: TestClient) -> None:
    token_a = _register(client, f"cnt-a-{uuid.uuid4()}@example.com", "tenant-a")
    token_b = _register(client, f"cnt-b-{uuid.uuid4()}@example.com", "tenant-b")

    _create_agent(client, token_a, "agent-a")

    resp = client.post(
        "/api/v1/containment",
        json={
            "target_agent_id": "agent-a",
            "mode": "quarantine",
            "reason": "cross-tenant attempt",
        },
        headers=_auth_headers(token_b),
    )
    assert resp.status_code in (400, 404)


def test_cross_tenant_cannot_view_other_tenant_blast_radius(client: TestClient) -> None:
    token_a = _register(client, f"cnt-a-{uuid.uuid4()}@example.com", "tenant-a")
    token_b = _register(client, f"cnt-b-{uuid.uuid4()}@example.com", "tenant-b")

    _create_agent(client, token_a, "agent-a")

    resp = client.get(
        "/api/v1/containment/agent/agent-a",
        headers=_auth_headers(token_b),
    )
    assert resp.status_code in (400, 404)


# ---------------------------------------------------------------------------
# Cross-tenant recovery isolation
# ---------------------------------------------------------------------------


def test_cross_tenant_cannot_simulate_other_tenant_recovery(client: TestClient) -> None:
    token_a = _register(client, f"rec-a-{uuid.uuid4()}@example.com", "tenant-a")
    token_b = _register(client, f"rec-b-{uuid.uuid4()}@example.com", "tenant-b")

    _create_agent(client, token_a, "agent-a")
    action_id = _create_action(client, token_a, "agent-a")

    resp = client.post(
        "/api/v1/recovery/simulate",
        json={
            "incident_action_id": action_id,
            "recovery_steps": [{"step": "revert"}],
        },
        headers=_auth_headers(token_b),
    )
    assert resp.status_code in (400, 404)


def test_cross_tenant_cannot_execute_other_tenant_recovery(client: TestClient) -> None:
    token_a = _register(client, f"rec-a-{uuid.uuid4()}@example.com", "tenant-a")
    token_b = _register(client, f"rec-b-{uuid.uuid4()}@example.com", "tenant-b")

    _create_agent(client, token_a, "agent-a")
    action_id = _create_action(client, token_a, "agent-a")

    sim = client.post(
        "/api/v1/recovery/simulate",
        json={
            "incident_action_id": action_id,
            "recovery_steps": [{"step": "revert"}],
        },
        headers=_auth_headers(token_a),
    )
    assert sim.status_code == 200
    plan_id = sim.json()["plan_id"]

    resp = client.post(
        "/api/v1/recovery/execute",
        json={"plan_id": plan_id, "approved_by": "admin"},
        headers=_auth_headers(token_b),
    )
    assert resp.status_code in (400, 404)


def test_cross_tenant_cannot_read_other_tenant_recovery_plan(client: TestClient) -> None:
    token_a = _register(client, f"rec-a-{uuid.uuid4()}@example.com", "tenant-a")
    token_b = _register(client, f"rec-b-{uuid.uuid4()}@example.com", "tenant-b")

    _create_agent(client, token_a, "agent-a")
    action_id = _create_action(client, token_a, "agent-a")

    sim = client.post(
        "/api/v1/recovery/simulate",
        json={
            "incident_action_id": action_id,
            "recovery_steps": [{"step": "revert"}],
        },
        headers=_auth_headers(token_a),
    )
    assert sim.status_code == 200
    plan_id = sim.json()["plan_id"]

    resp = client.get(
        f"/api/v1/recovery/{plan_id}",
        headers=_auth_headers(token_b),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Cross-tenant blast radius isolation
# ---------------------------------------------------------------------------


def test_cross_tenant_cannot_compute_blast_radius_for_other_agent(
    client: TestClient,
) -> None:
    token_a = _register(client, f"cnt-a-{uuid.uuid4()}@example.com", "tenant-a")
    token_b = _register(client, f"cnt-b-{uuid.uuid4()}@example.com", "tenant-b")

    _create_agent(client, token_a, "agent-a")

    resp = client.get(
        "/api/v1/containment/agent/agent-a",
        headers=_auth_headers(token_b),
    )
    assert resp.status_code in (400, 404)
