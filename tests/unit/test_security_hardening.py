from uuid import uuid4

from fastapi.testclient import TestClient


def test_disabled_account_cannot_login(client: TestClient) -> None:
    from app.infrastructure.persistence.database import get_db_session
    from app.infrastructure.persistence.models.user_model import UserModel

    email = f"disabled-{uuid4()}@example.com"
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecurePass1!"},
    )

    with get_db_session() as session:
        model = session.scalar(
            __import__("sqlalchemy").select(UserModel).where(UserModel.email == email)
        )
        assert model is not None
        model.is_active = False
        session.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "SecurePass1!"},
    )
    assert response.status_code == 401
    assert "inactive" in response.json()["detail"].lower()


def test_locked_account_cannot_login(client: TestClient) -> None:
    from datetime import UTC, timedelta

    from app.infrastructure.persistence.database import get_db_session
    from app.infrastructure.persistence.models.user_model import UserModel

    email = f"locked-{uuid4()}@example.com"
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecurePass1!"},
    )

    with get_db_session() as session:
        model = session.scalar(
            __import__("sqlalchemy").select(UserModel).where(UserModel.email == email)
        )
        assert model is not None
        model.locked_until = __import__("datetime").datetime.now(tz=UTC) + timedelta(minutes=15)
        session.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "SecurePass1!"},
    )
    assert response.status_code == 401
    assert "locked" in response.json()["detail"].lower()


def test_account_lockout_after_failed_attempts(client: TestClient) -> None:
    from app.presentation.api.middleware.rate_limit import reset_rate_limits

    email = f"lockout-{uuid4()}@example.com"
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecurePass1!"},
    )

    for _ in range(5):
        client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "WrongPass1!"},
        )

    reset_rate_limits()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "SecurePass1!"},
    )
    assert response.status_code == 401
    assert "locked" in response.json()["detail"].lower()


def test_password_policy_enforced_on_registration(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "password": "short"},
    )
    assert response.status_code == 422


def test_cross_tenant_intent_blocked(client: TestClient) -> None:
    email1 = f"tenant1-{uuid4()}@example.com"
    email2 = f"tenant2-{uuid4()}@example.com"

    client.post(
        "/api/v1/auth/register",
        json={"email": email1, "password": "SecurePass1!", "tenant_id": "tenant-1"},
    )
    client.post(
        "/api/v1/auth/register",
        json={"email": email2, "password": "SecurePass1!", "tenant_id": "tenant-2"},
    )

    client.post(
        "/api/v1/auth/login", json={"email": email1, "password": "SecurePass1!"}
    ).json()
    login2 = client.post(
        "/api/v1/auth/login", json={"email": email2, "password": "SecurePass1!"}
    ).json()

    token2 = login2["access_token"]

    response = client.post(
        "/api/v1/intent/verify",
        json={
            "user_prompt": "list active users",
            "agent_id": "agent-1",
            "reasoning_step": "step",
            "proposed_tool": "search",
            "tool_arguments": {"query": "test"},
            "tenant_id": "tenant-1",
        },
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert response.status_code == 403
    assert "tenant mismatch" in response.json()["detail"].lower()


def test_viewer_cannot_access_admin_endpoints(client: TestClient) -> None:
    email = f"viewer-{uuid4()}@example.com"
    client.post("/api/v1/auth/register", json={"email": email, "password": "SecurePass1!"})
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "SecurePass1!"}
    ).json()
    token = login["access_token"]

    response = client.get(
        "/api/v1/activity/search",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_default_deny_blocks_unknown_action(client: TestClient) -> None:
    email = f"deny-{uuid4()}@example.com"
    client.post("/api/v1/auth/register", json={"email": email, "password": "SecurePass1!"})
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "SecurePass1!"}
    ).json()
    token = login["access_token"]

    response = client.post(
        "/api/v1/intent/verify",
        json={
            "user_prompt": "test",
            "agent_id": "agent-1",
            "reasoning_step": "step",
            "proposed_tool": "search",
            "tool_arguments": {"query": "test"},
            "action": "drop_database",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_policy_simulation_returns_decision(client: TestClient) -> None:
    email = f"sim-{uuid4()}@example.com"
    client.post("/api/v1/auth/register", json={"email": email, "password": "SecurePass1!"})
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "SecurePass1!"}
    ).json()
    token = login["access_token"]

    response = client.post(
        "/api/v1/intent/simulate",
        json={
            "agent_id": "agent-1",
            "proposed_tool": "search",
            "tenant_id": "tenant-1",
            "confidence": 1.0,
            "risk_score": 0.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "effect" in data
    assert "matched_rules" in data
