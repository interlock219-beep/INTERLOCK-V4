"""Phase 15: Delegation security tests.

Tests verify that authority delegation enforces scope narrowing,
depth limits, prevents circular chains, and rejects expired or
revoked parent grants.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.domain.entities.authority_grant import AuthorityScope
from app.domain.services.authority_lineage_service import AuthorityLineageService
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_agent_repository import (
    SQLAlchemyAgentRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_authority_grant_repository import (
    SQLAlchemyAuthorityGrantRepository,
)


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
    client.post(
        "/api/v1/agents/",
        json={
            "agent_id": agent_id,
            "name": f"Agent {agent_id}",
            "agent_type": "service_agent",
        },
        headers=_auth_headers(token),
    )


def _create_grant_via_api(
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


def _make_lineage_service(tenant_id: str) -> AuthorityLineageService:
    session = SessionLocal()
    agent_repo = SQLAlchemyAgentRepository(session)
    grant_repo = SQLAlchemyAuthorityGrantRepository(session)
    return AuthorityLineageService(agent_repo, grant_repo)


def _persist_grant(tenant_id: str, **kwargs: Any) -> Any:
    import asyncio

    async def _save() -> Any:
        session = SessionLocal()
        try:
            grant_repo = SQLAlchemyAuthorityGrantRepository(session)
            agent_repo = SQLAlchemyAgentRepository(session)
            lineage = AuthorityLineageService(agent_repo, grant_repo)
            grant = lineage.create_authority(tenant_id=tenant_id, **kwargs)
            saved = await grant_repo.save(grant)
            session.commit()
            return saved
        finally:
            session.close()

    return asyncio.run(_save())


def _persist_grant_direct(tenant_id: str, **kwargs: Any) -> Any:
    return _persist_grant(tenant_id, **kwargs)


# ---------------------------------------------------------------------------
# Privilege escalation via delegation
# ---------------------------------------------------------------------------


def test_delegation_scope_narrowing_enforced(client: TestClient) -> None:
    token = _register(client, f"deleg-{uuid.uuid4()}@example.com", "tenant-del")
    _create_agent(client, token, "grantor-del")
    _create_agent(client, token, "grantee-del")

    parent_id = _create_grant_via_api(client, token, "grantor-del", "grantee-del", scope="read")

    resp = client.post(
        "/api/v1/authority/",
        json={
            "grantor_agent_id": "grantor-del",
            "grantee_agent_id": "grantee-del-2",
            "scope": "admin",
            "resource": "test-resource",
            "parent_authority_id": parent_id,
        },
        headers=_auth_headers(token),
    )
    assert resp.status_code == 403
    assert "scope" in resp.json()["detail"].lower() or "exceeds" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Delegation depth limit enforcement
# ---------------------------------------------------------------------------


def test_delegation_max_depth_rejected(client: TestClient) -> None:
    token = _register(client, f"depth-{uuid.uuid4()}@example.com", "tenant-depth")
    _create_agent(client, token, "g0")
    _create_agent(client, token, "g1")
    _create_agent(client, token, "g2")
    _create_agent(client, token, "g3")
    _create_agent(client, token, "g4")
    _create_agent(client, token, "g5")
    _create_agent(client, token, "g6")
    _create_agent(client, token, "g7")
    _create_agent(client, token, "g8")
    _create_agent(client, token, "g9")
    _create_agent(client, token, "g10")

    current_grantor = "g0"
    current_grantee = "g1"
    parent_id = None
    for depth in range(10):
        resp = client.post(
            "/api/v1/authority/",
            json={
                "grantor_agent_id": current_grantor,
                "grantee_agent_id": current_grantee,
                "scope": "read",
                "resource": "test-resource",
                "parent_authority_id": parent_id,
            },
            headers=_auth_headers(token),
        )
        assert resp.status_code == 201
        grant_data = resp.json()
        parent_id = grant_data["grant_id"]
        current_grantor = current_grantee
        current_grantee = f"g{depth + 2}"

    resp = client.post(
        "/api/v1/authority/",
        json={
            "grantor_agent_id": current_grantor,
            "grantee_agent_id": "g11",
            "scope": "read",
            "resource": "test-resource",
            "parent_authority_id": parent_id,
        },
        headers=_auth_headers(token),
    )
    assert resp.status_code == 403
    assert "depth" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Circular delegation prevention (via lineage service)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_circular_delegation_rejected_by_lineage_service() -> None:
    tenant_id = "tenant-circ"
    session = SessionLocal()
    try:
        agent_repo = SQLAlchemyAgentRepository(session)
        grant_repo = SQLAlchemyAuthorityGrantRepository(session)
        lineage = AuthorityLineageService(agent_repo, grant_repo)
        grant = lineage.create_authority(
            tenant_id=tenant_id,
            grantor_agent_id="agent-a",
            grantee_agent_id="agent-b",
            scope="read",
            resource="res",
        )
        saved = await grant_repo.save(grant)
        session.commit()
        grant = saved
    finally:
        session.close()

    service = _make_lineage_service(tenant_id)

    with pytest.raises(ValueError):
        await service.delegate_authority(
            tenant_id=tenant_id,
            parent_grant_id=grant.grant_id,
            new_grantee_agent_id="agent-a",
            scope="read",
            resource="res",
        )


# ---------------------------------------------------------------------------
# Expired authority rejection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_authority_rejected_by_lineage_service() -> None:
    tenant_id = "tenant-exp"
    past = datetime.now(UTC) - timedelta(hours=1)
    session = SessionLocal()
    try:
        agent_repo = SQLAlchemyAgentRepository(session)
        grant_repo = SQLAlchemyAuthorityGrantRepository(session)
        lineage = AuthorityLineageService(agent_repo, grant_repo)
        grant = lineage.create_authority(
            tenant_id=tenant_id,
            grantor_agent_id="agent-a",
            grantee_agent_id="agent-b",
            scope="read",
            resource="res",
            expires_at=past,
        )
        saved = await grant_repo.save(grant)
        session.commit()
        grant = saved
    finally:
        session.close()

    service = _make_lineage_service(tenant_id)

    with pytest.raises(ValueError, match="expired"):
        await service.delegate_authority(
            tenant_id=tenant_id,
            parent_grant_id=grant.grant_id,
            new_grantee_agent_id="agent-c",
            scope="read",
            resource="res",
        )


# ---------------------------------------------------------------------------
# Revoked authority rejection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoked_authority_rejected_by_lineage_service() -> None:
    tenant_id = "tenant-rev"
    session = SessionLocal()
    try:
        agent_repo = SQLAlchemyAgentRepository(session)
        grant_repo = SQLAlchemyAuthorityGrantRepository(session)
        lineage = AuthorityLineageService(agent_repo, grant_repo)
        grant = lineage.create_authority(
            tenant_id=tenant_id,
            grantor_agent_id="agent-a",
            grantee_agent_id="agent-b",
            scope="read",
            resource="res",
        )
        saved = await grant_repo.save(grant)
        session.commit()
        grant = saved
    finally:
        session.close()

    session = SessionLocal()
    try:
        grant_repo = SQLAlchemyAuthorityGrantRepository(session)
        await grant_repo.revoke(tenant_id, grant.grant_id, "tester")
        session.commit()
    finally:
        session.close()

    service = _make_lineage_service(tenant_id)

    with pytest.raises(ValueError, match="not active"):
        await service.delegate_authority(
            tenant_id=tenant_id,
            parent_grant_id=grant.grant_id,
            new_grantee_agent_id="agent-c",
            scope="read",
            resource="res",
        )


# ---------------------------------------------------------------------------
# Scope narrowing verification
# ---------------------------------------------------------------------------


def test_scope_within_parent_allows_equal_or_narrower() -> None:
    service = AuthorityLineageService.__new__(AuthorityLineageService)
    assert service._scope_within_parent(AuthorityScope.READ, AuthorityScope.READ) is True
    assert service._scope_within_parent(AuthorityScope.READ, AuthorityScope.WRITE) is True
    assert service._scope_within_parent(AuthorityScope.READ, AuthorityScope.ADMIN) is True
    assert service._scope_within_parent(AuthorityScope.WRITE, AuthorityScope.READ) is False
    assert service._scope_within_parent(AuthorityScope.ADMIN, AuthorityScope.READ) is False
    assert service._scope_within_parent(AuthorityScope.CUSTOM, AuthorityScope.CUSTOM) is True


def test_delegation_scope_narrowing_via_api(client: TestClient) -> None:
    token = _register(client, f"scope-{uuid.uuid4()}@example.com", "tenant-scope")
    _create_agent(client, token, "grantor-sc")
    _create_agent(client, token, "grantee-sc")
    _create_agent(client, token, "grantee2-sc")

    parent_id = _create_grant_via_api(client, token, "grantor-sc", "grantee-sc", scope="write")

    narrower_resp = client.post(
        "/api/v1/authority/",
        json={
            "grantor_agent_id": "grantee-sc",
            "grantee_agent_id": "grantee2-sc",
            "scope": "read",
            "resource": "test-resource",
            "parent_authority_id": parent_id,
        },
        headers=_auth_headers(token),
    )
    assert narrower_resp.status_code == 201

    wider_resp = client.post(
        "/api/v1/authority/",
        json={
            "grantor_agent_id": "grantee-sc",
            "grantee_agent_id": "grantee2-sc",
            "scope": "admin",
            "resource": "test-resource",
            "parent_authority_id": parent_id,
        },
        headers=_auth_headers(token),
    )
    assert wider_resp.status_code == 403
