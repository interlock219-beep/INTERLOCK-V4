"""Tests for activity API routes."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

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


class TestActivityRoutes:
    def test_list_activity_requires_auth(self, client: TestClient) -> None:
        response = client.get("/api/v1/activity/me")
        assert response.status_code == 401

    def test_list_activity_returns_empty_for_new_user(
        self, client: TestClient
    ) -> None:
        auth = _register(client, "activity@test.com", "SecurePass1!")
        response = client.get(
            "/api/v1/activity/me",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_list_activity_returns_user_events(
        self, client: TestClient, db_session
    ) -> None:
        from app.infrastructure.persistence.models import AuditEventModel

        auth = _register(client, "activity2@test.com", "SecurePass1!")
        user_id = UUID(auth["user"]["id"])

        old_time = datetime(2026, 1, 1, tzinfo=UTC)
        newer_time = datetime(2026, 1, 2, tzinfo=UTC)

        events = [
            AuditEventModel(
                id=uuid4(),
                event_type="intent.evaluated",
                payload='{"action": "deploy"}',
                correlation_id=str(uuid4()),
                user_id=user_id,
                created_at=old_time,
            ),
            AuditEventModel(
                id=uuid4(),
                event_type="approval.requested",
                payload='{"resource": "api_key"}',
                correlation_id=str(uuid4()),
                user_id=user_id,
                created_at=newer_time,
            ),
        ]
        for event in events:
            db_session.add(event)
        db_session.commit()

        response = client.get(
            "/api/v1/activity/me",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["event_type"] == "approval.requested"
        assert data[0]["timestamp"] == "2026-01-02T00:00:00"
        assert data[1]["event_type"] == "intent.evaluated"
        assert data[1]["timestamp"] == "2026-01-01T00:00:00"

    def test_list_activity_excludes_other_users_events(
        self, client: TestClient, db_session
    ) -> None:
        from app.infrastructure.persistence.models import AuditEventModel

        auth1 = _register(client, "actuser1@test.com", "SecurePass1!")
        auth2 = _register(client, "actuser2@test.com", "SecurePass1!")
        user2_id = UUID(auth2["user"]["id"])

        event = AuditEventModel(
            id=uuid4(),
            event_type="login.success",
            payload="{}",
            correlation_id=str(uuid4()),
            user_id=user2_id,
            created_at=datetime(2026, 1, 3, tzinfo=UTC),
        )
        db_session.add(event)
        db_session.commit()

        response = client.get(
            "/api/v1/activity/me",
            headers=_auth_header(auth1["access_token"]),
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_list_activity_handles_invalid_payload(
        self, client: TestClient, db_session
    ) -> None:
        from app.infrastructure.persistence.models import AuditEventModel

        auth = _register(client, "invalidpayload@test.com", "SecurePass1!")
        user_id = UUID(auth["user"]["id"])

        event = AuditEventModel(
            id=uuid4(),
            event_type="intent.evaluated",
            payload="not valid json",
            correlation_id=str(uuid4()),
            user_id=user_id,
            created_at=datetime(2026, 1, 4, tzinfo=UTC),
        )
        db_session.add(event)
        db_session.commit()

        response = client.get(
            "/api/v1/activity/me",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["event_type"] == "intent.evaluated"
        assert data[0]["details"] == {}
