"""Tests for activity API routes - covering search endpoint."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.domain.entities.user import User
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.models.audit_event_model import AuditEventModel
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


async def _create_admin_user(email: str) -> str:
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
            role="admin",
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


class TestActivitySearchRoutes:
    def test_search_requires_auth(self, client: TestClient) -> None:
        response = client.get("/api/v1/activity/search")
        assert response.status_code == 401

    def test_search_requires_admin_role(self, client: TestClient) -> None:
        auth = _register(client, "searchviewer@test.com", "SecurePass1!")
        response = client.get(
            "/api/v1/activity/search",
            headers=_auth_header(auth["access_token"]),
        )
        assert response.status_code == 403
        assert "Admin role required" in response.json()["detail"]

    def test_search_returns_events_for_admin(self, client: TestClient, db_session) -> None:
        import asyncio
        admin_token = asyncio.run(_create_admin_user("searchadmin@test.com"))

        event = AuditEventModel(
            id=uuid4(),
            event_type="login.success",
            payload='{"ip": "127.0.0.1"}',
            correlation_id=str(uuid4()),
            user_id=uuid4(),
            created_at=datetime(2026, 1, 5, tzinfo=UTC),
        )
        db_session.add(event)
        db_session.commit()

        response = client.get(
            "/api/v1/activity/search",
            headers=_auth_header(admin_token),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["events"]) == 1
        assert data["events"][0]["event_type"] == "login.success"

    def test_search_filters_by_event_type(self, client: TestClient, db_session) -> None:
        import asyncio
        admin_token = asyncio.run(_create_admin_user("searchfilter@test.com"))

        event1 = AuditEventModel(
            id=uuid4(),
            event_type="login.success",
            payload="{}",
            correlation_id=str(uuid4()),
            user_id=uuid4(),
            created_at=datetime(2026, 1, 5, tzinfo=UTC),
        )
        event2 = AuditEventModel(
            id=uuid4(),
            event_type="intent.evaluated",
            payload="{}",
            correlation_id=str(uuid4()),
            user_id=uuid4(),
            created_at=datetime(2026, 1, 6, tzinfo=UTC),
        )
        db_session.add(event1)
        db_session.add(event2)
        db_session.commit()

        response = client.get(
            "/api/v1/activity/search",
            headers=_auth_header(admin_token),
            params={"event_type": "login.success"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["events"][0]["event_type"] == "login.success"

    def test_search_filters_by_date_range(self, client: TestClient, db_session) -> None:
        import asyncio
        admin_token = asyncio.run(_create_admin_user("searchdate@test.com"))

        event = AuditEventModel(
            id=uuid4(),
            event_type="login.success",
            payload="{}",
            correlation_id=str(uuid4()),
            user_id=uuid4(),
            created_at=datetime(2026, 6, 15, tzinfo=UTC),
        )
        db_session.add(event)
        db_session.commit()

        response = client.get(
            "/api/v1/activity/search",
            headers=_auth_header(admin_token),
            params={"since": "2026-06-01", "until": "2026-06-30"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    def test_search_handles_invalid_payload(self, client: TestClient, db_session) -> None:
        import asyncio
        admin_token = asyncio.run(_create_admin_user("searchinvalid@test.com"))

        event = AuditEventModel(
            id=uuid4(),
            event_type="login.success",
            payload="not valid json",
            correlation_id=str(uuid4()),
            user_id=uuid4(),
            created_at=datetime(2026, 1, 5, tzinfo=UTC),
        )
        db_session.add(event)
        db_session.commit()

        response = client.get(
            "/api/v1/activity/search",
            headers=_auth_header(admin_token),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["events"][0]["details"] == {}
