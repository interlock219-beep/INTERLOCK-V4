"""Tests for authority API routes."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.domain.entities.agent import Agent, AgentType
from app.domain.entities.authority_grant import AuthorityScope, AuthorityStatus
from app.domain.entities.user import User
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_agent_repository import (
    SQLAlchemyAgentRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_authority_grant_repository import (
    SQLAlchemyAuthorityGrantRepository,
)
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


async def _create_agent(tenant_id: str, agent_id: str) -> Agent:
    session = SessionLocal()
    try:
        repo = SQLAlchemyAgentRepository(session)
        agent = Agent(
            agent_id=agent_id,
            tenant_id=tenant_id,
            name=f"Agent {agent_id}",
            agent_type=AgentType.UNKNOWN,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        saved = await repo.save(agent)
        session.commit()
        return saved
    finally:
        session.close()


async def _create_grant(tenant_id: str, grant_id: str, **kwargs) -> None:
    session = SessionLocal()
    try:
        repo = SQLAlchemyAuthorityGrantRepository(session)
        from app.domain.entities.authority_grant import AuthorityGrant
        grant = AuthorityGrant(
            grant_id=grant_id,
            tenant_id=tenant_id,
            grantor_agent_id=kwargs.get("grantor_agent_id", "grantor-1"),
            grantee_agent_id=kwargs.get("grantee_agent_id", "grantee-1"),
            scope=kwargs.get("scope", AuthorityScope.READ),
            resource=kwargs.get("resource", "res-1"),
            conditions=kwargs.get("conditions", {}),
            expires_at=kwargs.get("expires_at"),
            delegation_depth=kwargs.get("delegation_depth", 0),
            parent_authority_id=kwargs.get("parent_authority_id"),
            root_authority_id=kwargs.get("root_authority_id"),
            status=kwargs.get("status", AuthorityStatus.ACTIVE),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        await repo.save(grant)
        session.commit()
    finally:
        session.close()


class TestAuthorityRoutes:
    def test_create_grant_requires_auth(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/authority/",
            json={
                "grantor_agent_id": "agent-1",
                "grantee_agent_id": "agent-2",
                "scope": "read",
                "resource": "res-1",
            },
        )
        assert response.status_code == 401

    def test_create_grant_success(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("authoritycreate@test.com"))
        asyncio.run(_create_agent("test-tenant", "grantor-1"))
        asyncio.run(_create_agent("test-tenant", "grantee-1"))
        response = client.post(
            "/api/v1/authority/",
            headers=_auth_header(token),
            json={
                "grantor_agent_id": "grantor-1",
                "grantee_agent_id": "grantee-1",
                "scope": "read",
                "resource": "res-1",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["grantor_agent_id"] == "grantor-1"
        assert data["grantee_agent_id"] == "grantee-1"
        assert data["scope"] == "read"
        assert data["delegation_depth"] == 0

    def test_create_grant_with_parent_not_found(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("authorityparentnf@test.com"))
        response = client.post(
            "/api/v1/authority/",
            headers=_auth_header(token),
            json={
                "grantor_agent_id": "grantor-1",
                "grantee_agent_id": "grantee-1",
                "scope": "read",
                "resource": "res-1",
                "parent_authority_id": "nonexistent",
            },
        )
        assert response.status_code == 400
        assert "Parent authority grant not found" in response.json()["detail"]

    def test_create_grant_with_inactive_parent(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("authorityinactive@test.com"))
        asyncio.run(_create_agent("test-tenant", "grantor-inactive"))
        asyncio.run(_create_agent("test-tenant", "grantee-inactive"))
        asyncio.run(_create_grant(
            "test-tenant",
            "grant-inactive",
            grantor_agent_id="grantor-inactive",
            grantee_agent_id="grantee-inactive",
            status=AuthorityStatus.REVOKED,
        ))
        response = client.post(
            "/api/v1/authority/",
            headers=_auth_header(token),
            json={
                "grantor_agent_id": "grantor-inactive",
                "grantee_agent_id": "grantee-inactive",
                "scope": "read",
                "resource": "res-1",
                "parent_authority_id": "grant-inactive",
            },
        )
        assert response.status_code == 403
        assert "not active" in response.json()["detail"]

    def test_create_grant_with_expired_parent(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("authorityexpired@test.com"))
        asyncio.run(_create_agent("test-tenant", "grantor-exp"))
        asyncio.run(_create_agent("test-tenant", "grantee-exp"))
        asyncio.run(_create_grant(
            "test-tenant",
            "grant-expired",
            grantor_agent_id="grantor-exp",
            grantee_agent_id="grantee-exp",
            expires_at=datetime(2020, 1, 1, tzinfo=UTC),
        ))
        response = client.post(
            "/api/v1/authority/",
            headers=_auth_header(token),
            json={
                "grantor_agent_id": "grantor-exp",
                "grantee_agent_id": "grantee-exp",
                "scope": "read",
                "resource": "res-1",
                "parent_authority_id": "grant-expired",
            },
        )
        assert response.status_code == 403
        assert "expired" in response.json()["detail"]

    def test_create_grant_depth_exceeded(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("authoritydepth@test.com"))
        asyncio.run(_create_agent("test-tenant", "grantor-depth"))
        asyncio.run(_create_agent("test-tenant", "grantee-depth"))
        asyncio.run(_create_grant(
            "test-tenant",
            "grant-depth-9",
            grantor_agent_id="grantor-depth",
            grantee_agent_id="grantee-depth",
            delegation_depth=9,
        ))
        response = client.post(
            "/api/v1/authority/",
            headers=_auth_header(token),
            json={
                "grantor_agent_id": "grantor-depth",
                "grantee_agent_id": "grantee-depth",
                "scope": "read",
                "resource": "res-1",
                "parent_authority_id": "grant-depth-9",
            },
        )
        assert response.status_code == 403
        assert "depth" in response.json()["detail"].lower()

    def test_create_grant_scope_exceeds_parent(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("authorityscope@test.com"))
        asyncio.run(_create_agent("test-tenant", "grantor-scope"))
        asyncio.run(_create_agent("test-tenant", "grantee-scope"))
        asyncio.run(_create_grant(
            "test-tenant",
            "grant-scope-parent",
            grantor_agent_id="grantor-scope",
            grantee_agent_id="grantee-scope",
            scope=AuthorityScope.READ,
        ))
        response = client.post(
            "/api/v1/authority/",
            headers=_auth_header(token),
            json={
                "grantor_agent_id": "grantor-scope",
                "grantee_agent_id": "grantee-scope",
                "scope": "admin",
                "resource": "res-1",
                "parent_authority_id": "grant-scope-parent",
            },
        )
        assert response.status_code == 403
        assert "scope" in response.json()["detail"].lower()

    def test_create_grant_grantor_mismatch(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("authoritymismatch@test.com"))
        asyncio.run(_create_agent("test-tenant", "grantor-mismatch"))
        asyncio.run(_create_agent("test-tenant", "grantee-mismatch"))
        asyncio.run(_create_agent("test-tenant", "other-agent"))
        asyncio.run(_create_grant(
            "test-tenant",
            "grant-mismatch",
            grantor_agent_id="grantor-mismatch",
            grantee_agent_id="grantee-mismatch",
        ))
        response = client.post(
            "/api/v1/authority/",
            headers=_auth_header(token),
            json={
                "grantor_agent_id": "other-agent",
                "grantee_agent_id": "grantee-mismatch",
                "scope": "read",
                "resource": "res-1",
                "parent_authority_id": "grant-mismatch",
            },
        )
        assert response.status_code == 403
        assert "Grantor must be" in response.json()["detail"]

    def test_create_grant_root_depth_mismatch(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("authorityrootdepth@test.com"))
        response = client.post(
            "/api/v1/authority/",
            headers=_auth_header(token),
            json={
                "grantor_agent_id": "agent-1",
                "grantee_agent_id": "agent-2",
                "scope": "read",
                "resource": "res-1",
                "delegation_depth": 5,
            },
        )
        assert response.status_code == 400
        assert "delegation_depth=0" in response.json()["detail"]

    def test_list_grants_by_grantee(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("authoritylist@test.com"))
        asyncio.run(_create_grant(
            "test-tenant",
            "grant-list-1",
            grantee_agent_id="grantee-list",
        ))
        response = client.get(
            "/api/v1/authority/",
            headers=_auth_header(token),
            params={"grantee_agent_id": "grantee-list"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    def test_list_grants_by_grantor(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("authoritylistgrantor@test.com"))
        asyncio.run(_create_grant(
            "test-tenant",
            "grant-list-grantor",
            grantor_agent_id="grantor-list",
        ))
        response = client.get(
            "/api/v1/authority/",
            headers=_auth_header(token),
            params={"grantor_agent_id": "grantor-list"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    def test_list_grants_requires_filter(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("authorityfilter@test.com"))
        response = client.get(
            "/api/v1/authority/",
            headers=_auth_header(token),
        )
        assert response.status_code == 400
        assert "grantee_agent_id or grantor_agent_id required" in response.json()["detail"]

    def test_get_grant(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("authorityget@test.com"))
        asyncio.run(_create_grant("test-tenant", "grant-get-1"))
        response = client.get(
            "/api/v1/authority/grant-get-1",
            headers=_auth_header(token),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["grant_id"] == "grant-get-1"

    def test_get_grant_not_found(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("authoritygetnf@test.com"))
        response = client.get(
            "/api/v1/authority/nonexistent",
            headers=_auth_header(token),
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_revoke_grant(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("authorityrevoke@test.com"))
        asyncio.run(_create_grant("test-tenant", "grant-revoke-1"))
        response = client.post(
            "/api/v1/authority/grant-revoke-1/revoke",
            headers=_auth_header(token),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "revoked"

    def test_revoke_grant_not_found(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("authorityrevokenf@test.com"))
        response = client.post(
            "/api/v1/authority/nonexistent/revoke",
            headers=_auth_header(token),
        )
        assert response.status_code == 404

    def test_revoke_already_revoked(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("authorityrevokealready@test.com"))
        asyncio.run(
            _create_grant("test-tenant", "grant-revoke-already", status=AuthorityStatus.REVOKED)
        )
        response = client.post(
            "/api/v1/authority/grant-revoke-already/revoke",
            headers=_auth_header(token),
        )
        assert response.status_code == 400
        assert "already revoked" in response.json()["detail"]

    def test_get_grant_lineage(self, client: TestClient) -> None:
        import asyncio
        token = asyncio.run(_create_user("authoritylineage@test.com"))
        asyncio.run(_create_grant("test-tenant", "grant-lineage-1"))
        response = client.get(
            "/api/v1/authority/grant-lineage-1/lineage",
            headers=_auth_header(token),
        )
        assert response.status_code == 200
