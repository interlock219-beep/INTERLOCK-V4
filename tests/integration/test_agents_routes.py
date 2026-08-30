"""Tests for agents API routes."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.domain.entities.agent import Agent, AgentType
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


async def _create_user(email: str, role: str = "viewer", tenant_id: str = "test-tenant") -> str:
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


async def _create_agent(tenant_id: str, agent_id: str, **kwargs) -> Agent:
    session = SessionLocal()
    try:
        from app.infrastructure.persistence.repositories.sqlalchemy_agent_repository import (
            SQLAlchemyAgentRepository,
        )
        repo = SQLAlchemyAgentRepository(session)
        agent = Agent(
            agent_id=agent_id,
            tenant_id=tenant_id,
            name=kwargs.get("name", f"Agent {agent_id}"),
            description=kwargs.get("description", ""),
            agent_type=kwargs.get("agent_type", AgentType.UNKNOWN),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        saved = await repo.save(agent)
        session.commit()
        return saved
    finally:
        session.close()


class TestAgentsRoutes:
    def test_create_agent_requires_auth(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/agents/",
            json={
                "agent_id": "agent-1",
                "name": "Test Agent",
            },
        )
        assert response.status_code == 401

    def test_create_agent_success(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("agentcreate@test.com"))
        response = client.post(
            "/api/v1/agents/",
            headers=_auth_header(token),
            json={
                "agent_id": "agent-create-1",
                "name": "Test Agent",
                "description": "A test agent",
                "agent_type": "user_agent",
                "environment": "development",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["agent_id"] == "agent-create-1"
        assert data["name"] == "Test Agent"
        assert data["agent_type"] == "user_agent"
        assert data["environment"] == "development"

    def test_create_agent_duplicate(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("agentdup@test.com"))
        client.post(
            "/api/v1/agents/",
            headers=_auth_header(token),
            json={"agent_id": "agent-dup", "name": "Duplicate"},
        )
        response = client.post(
            "/api/v1/agents/",
            headers=_auth_header(token),
            json={"agent_id": "agent-dup", "name": "Duplicate"},
        )
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    def test_list_agents(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("agentlist@test.com"))
        tenant_id = "test-tenant"
        asyncio.run(_create_agent(tenant_id, "agent-list-1"))
        asyncio.run(_create_agent(tenant_id, "agent-list-2"))
        response = client.get(
            "/api/v1/agents/",
            headers=_auth_header(token),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 2

    def test_list_agents_with_filters(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("agentfilter@test.com"))
        response = client.get(
            "/api/v1/agents/",
            headers=_auth_header(token),
            params={"status": "active", "agent_type": "user_agent"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["items"], list)

    def test_get_agent(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("agentget@test.com"))
        asyncio.run(_create_agent("test-tenant", "agent-get-1", name="Get Agent"))
        response = client.get(
            "/api/v1/agents/agent-get-1",
            headers=_auth_header(token),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "agent-get-1"
        assert data["name"] == "Get Agent"

    def test_get_agent_not_found(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("agentnotfound@test.com"))
        response = client.get(
            "/api/v1/agents/nonexistent-agent",
            headers=_auth_header(token),
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_update_agent_status(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("agentupdate@test.com"))
        asyncio.run(_create_agent("test-tenant", "agent-update-1"))
        response = client.patch(
            "/api/v1/agents/agent-update-1",
            headers=_auth_header(token),
            json={"status": "suspended"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "suspended"

    def test_update_agent_fields(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("agentupdatefields@test.com"))
        asyncio.run(_create_agent("test-tenant", "agent-update-fields"))
        response = client.patch(
            "/api/v1/agents/agent-update-fields",
            headers=_auth_header(token),
            json={"name": "Updated Name", "trust_level": "verified"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["trust_level"] == "verified"

    def test_update_agent_no_fields(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("agentupdateempty@test.com"))
        asyncio.run(_create_agent("test-tenant", "agent-update-empty"))
        response = client.patch(
            "/api/v1/agents/agent-update-empty",
            headers=_auth_header(token),
            json={},
        )
        assert response.status_code == 400
        assert "No updatable fields" in response.json()["detail"]

    def test_update_agent_not_found(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("agentupdatenf@test.com"))
        response = client.patch(
            "/api/v1/agents/nonexistent",
            headers=_auth_header(token),
            json={"name": "New Name"},
        )
        assert response.status_code == 404
