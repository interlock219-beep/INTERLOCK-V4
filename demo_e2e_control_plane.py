"""Phase 20: End-to-end demo of IntentLock AI Agent Control Plane.

Scenario: human -> Agent A -> Agent B delegation -> protected actions ->
incident detection -> blast radius -> containment -> recovery planning ->
approved execution.
"""

from __future__ import annotations

import os
import uuid

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "JWT_SECRET_KEY",
    "test-secret-key-that-is-at-least-32-characters-long",
)
os.environ.setdefault("COMPLIANCE_SECRET_KEY", "test-compliance-secret-key")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test")
os.environ.setdefault("AUTHORIZATION_REQUIRE_TENANT", "false")
os.environ.setdefault("AUTHORIZATION_DEFAULT_DENY", "false")

from typing import Any, cast

from fastapi.testclient import TestClient

from app.main import create_app

app = create_app()


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
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return cast(str, resp.json()["access_token"])


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
    assert resp.status_code == 201, f"Create agent failed: {resp.text}"


def _create_grant(
    client: TestClient, token: str, grantor: str, grantee: str, scope: str = "read"
) -> str:
    resp = client.post(
        "/api/v1/authority/",
        json={
            "grantor_agent_id": grantor,
            "grantee_agent_id": grantee,
            "scope": scope,
            "resource": "demo-resource",
        },
        headers=_auth_headers(token),
    )
    assert resp.status_code == 201, f"Create grant failed: {resp.text}"
    return cast(str, resp.json()["grant_id"])


def _create_action(client: TestClient, token: str, agent_id: str, tool: str = "search") -> str:
    resp = client.post(
        "/api/v1/actions/",
        json={
            "agent_id": agent_id,
            "tool": tool,
            "resource": "demo-resource",
            "action_type": "query",
        },
        headers=_auth_headers(token),
    )
    assert resp.status_code == 201, f"Create action failed: {resp.text}"
    return cast(str, resp.json()["action_id"])


def _evaluate_action(client: TestClient, token: str, action_id: str) -> dict[str, Any]:
    resp = client.post(
        f"/api/v1/actions/{action_id}/evaluate",
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200, f"Evaluate action failed: {resp.text}"
    return cast(dict[str, Any], resp.json())


def _verify_intent(
    client: TestClient,
    token: str,
    tenant_id: str,
    agent_id: str,
    tool: str,
) -> dict[str, Any]:
    resp = client.post(
        "/api/v1/intent/verify",
        json={
            "user_prompt": "Search records for Q3 report",
            "agent_id": agent_id,
            "reasoning_step": "normal",
            "proposed_tool": tool,
            "tool_arguments": {"query": "Q3"},
            "tenant_id": tenant_id,
        },
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200, f"Verify intent failed: {resp.text}"
    return cast(dict[str, Any], resp.json())


def main() -> None:
    with TestClient(app) as client:
        tenant_id = f"tenant-{uuid.uuid4()}"
        human_email = f"human-{uuid.uuid4()}@example.com"

        print("=" * 70)
        print("IntentLock AI Agent Control Plane - End-to-End Demo")
        print("=" * 70)

        # Step 1: Human registers and logs in
        print("\n[Step 1] Human user registers and logs in...")
        token = _register(client, human_email, tenant_id)
        print(f"  Human logged in: {human_email}")

        # Step 2: Create Agent A (primary agent)
        print("\n[Step 2] Human creates Agent A (primary agent)...")
        agent_a = f"agent-a-{uuid.uuid4().hex[:8]}"
        _create_agent(client, token, agent_a)
        print(f"  Created Agent A: {agent_a}")

        # Step 3: Create Agent B (delegated agent)
        print("\n[Step 3] Human creates Agent B (delegated agent)...")
        agent_b = f"agent-b-{uuid.uuid4().hex[:8]}"
        _create_agent(client, token, agent_b)
        print(f"  Created Agent B: {agent_b}")

        # Step 4: Delegate authority from Agent A to Agent B
        print("\n[Step 4] Delegate authority from Agent A to Agent B...")
        grant_id = _create_grant(client, token, agent_a, agent_b, scope="read")
        print(f"  Authority granted: {grant_id}")

        # Step 5: Agent B performs protected action (search)
        print("\n[Step 5] Agent B performs protected action (search)...")
        action_id = _create_action(client, token, agent_b, tool="search")
        eval_result = _evaluate_action(client, token, action_id)
        print(f"  Action evaluated: {eval_result.get('status')}")

        # Step 6: Human verifies intent for Agent B
        print("\n[Step 6] Human verifies intent for Agent B...")
        intent_result = _verify_intent(client, token, tenant_id, agent_b, tool="search")
        print(f"  Intent verified: {intent_result.get('is_valid')}")

        # Step 7: Simulate incident - Agent B is compromised
        print("\n[Step 7] Simulate incident: Agent B is compromised...")
        containment_resp = client.post(
            "/api/v1/containment",
            json={
                "target_agent_id": agent_b,
                "mode": "quarantine",
                "reason": "Simulated compromise - unauthorized access pattern",
            },
            headers=_auth_headers(token),
        )
        assert (
            containment_resp.status_code in (200, 201)
        ), f"Containment failed: {containment_resp.text}"
        containment = containment_resp.json()
        print(f"  Agent contained: {containment.get('target_agent_id')}")
        print(f"  Affected agents: {containment.get('affected_agent_ids', [])}")
        print(f"  Affected authorities: {containment.get('affected_authority_ids', [])}")

        # Step 8: Calculate blast radius
        print("\n[Step 8] Calculate blast radius for Agent B...")
        blast_resp = client.get(
            f"/api/v1/containment/agent/{agent_b}",
            headers=_auth_headers(token),
        )
        assert blast_resp.status_code == 200, f"Blast radius failed: {blast_resp.text}"
        blast = blast_resp.json()
        print(f"  Blast radius agents: {blast.get('affected_agents', [])}")
        print(f"  Blast radius authorities: {blast.get('affected_authorities', [])}")

        # Step 9: Simulate recovery plan
        print("\n[Step 9] Simulate recovery plan...")
        sim_resp = client.post(
            "/api/v1/recovery/simulate",
            json={
                "incident_action_id": action_id,
                "recovery_steps": [{"step": "revert"}],
            },
            headers=_auth_headers(token),
        )
        assert sim_resp.status_code == 200, f"Recovery simulation failed: {sim_resp.text}"
        simulation = sim_resp.json()
        plan_id = simulation.get("plan_id")
        print(f"  Recovery plan simulated: {plan_id}")

        # Step 10: Execute approved recovery
        print("\n[Step 10] Execute approved recovery...")
        exec_resp = client.post(
            "/api/v1/recovery/execute",
            json={"plan_id": plan_id, "approved_by": human_email},
            headers=_auth_headers(token),
        )
        assert exec_resp.status_code == 200, f"Recovery execution failed: {exec_resp.text}"
        execution = exec_resp.json()
        print(f"  Recovery executed: {execution.get('plan_id')}")
        print(f"  Outcome: {execution.get('outcome')}")

        print("\n" + "=" * 70)
        print("End-to-end demo completed successfully!")
        print("=" * 70)


if __name__ == "__main__":
    main()
