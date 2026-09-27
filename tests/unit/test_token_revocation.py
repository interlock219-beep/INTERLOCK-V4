from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.domain.entities.execution_token import ExecutionToken, TokenStatus
from app.domain.services.token_revocation_service import (
    TokenRevocationReason,
    TokenRevocationService,
)


@pytest.fixture
def token_repo():
    return AsyncMock()


@pytest.fixture
def service(token_repo):
    return TokenRevocationService(token_repository=token_repo)


def build_token(
    token_id: str = "token-1",
    tenant_id: str = "tenant-1",
    agent_id: str = "agent-1",
    status: TokenStatus = TokenStatus.ACTIVE,
    jti: str = "jti-1",
) -> ExecutionToken:
    return ExecutionToken(
        token_id=token_id,
        tenant_id=tenant_id,
        jti=jti,
        agent_id=agent_id,
        tool="tool-1",
        status=status,
        issued_at=datetime.now(UTC),
        expires_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_revoke_token(service, token_repo):
    token_repo.revoke.return_value = build_token()
    token_repo.list_by_agent.return_value = ([], 0)

    result = await service.revoke_token(
        tenant_id="tenant-1",
        token_id="token-1",
        reason=TokenRevocationReason.MANUAL,
        revoked_by="admin-1",
    )

    assert result["primary_token_id"] == "token-1"
    assert result["reason"] == TokenRevocationReason.MANUAL
    assert result["revoked_by"] == "admin-1"
    assert result["total_revoked"] == 1
    assert result["cascade_performed"] is False
    token_repo.revoke.assert_awaited_once_with("tenant-1", "token-1")


@pytest.mark.asyncio
async def test_revoke_token_with_cascade(service, token_repo):
    token_repo.revoke.return_value = build_token()
    token_repo.list_by_agent.side_effect = [
        ([build_token("token-1")], 1),
        ([build_token("token-1"), build_token("token-2")], 2),
    ]

    result = await service.revoke_token(
        tenant_id="tenant-1",
        token_id="token-1",
        cascade=True,
    )

    assert result["cascade_performed"] is True
    assert result["total_revoked"] >= 1


@pytest.mark.asyncio
async def test_revoke_tokens_by_agent(service, token_repo):
    active_token = build_token("token-1")
    token_repo.list_by_agent.return_value = ([active_token], 1)
    token_repo.revoke.return_value = active_token

    revoked = await service.revoke_tokens_by_agent(
        tenant_id="tenant-1",
        agent_id="agent-1",
        reason=TokenRevocationReason.COMPROMISED,
    )

    assert len(revoked) == 1
    assert revoked[0] == "token-1"
    token_repo.revoke.assert_awaited_once_with("tenant-1", "token-1")


@pytest.mark.asyncio
async def test_revoke_tokens_by_agent_no_active(service, token_repo):
    token_repo.list_by_agent.return_value = ([], 0)

    revoked = await service.revoke_tokens_by_agent(
        tenant_id="tenant-1",
        agent_id="agent-1",
    )

    assert revoked == []
    token_repo.revoke.assert_not_called()


@pytest.mark.asyncio
async def test_revoke_tokens_by_tenant(service, token_repo):
    active = build_token("token-1")
    revoked = build_token("token-1", status=TokenStatus.REVOKED)
    token_repo.list_by_tenant.return_value = ([active, revoked], 2)
    token_repo.revoke.return_value = revoked

    result = await service.revoke_tokens_by_tenant(
        tenant_id="tenant-1",
        reason=TokenRevocationReason.TENANT_CONTAINMENT,
    )

    assert len(result) == 1
    assert result[0] == "token-1"
    token_repo.revoke.assert_awaited_once_with("tenant-1", "token-1")


@pytest.mark.asyncio
async def test_is_revoked_true(service, token_repo):
    revoked_token = build_token(status=TokenStatus.REVOKED)
    token_repo.list_by_agent.return_value = ([revoked_token], 1)

    result = await service.is_revoked("tenant-1", "token-1")
    assert result is True


@pytest.mark.asyncio
async def test_is_revoked_false(service, token_repo):
    token_repo.list_by_agent.return_value = ([], 0)

    result = await service.is_revoked("tenant-1", "token-1")
    assert result is False


@pytest.mark.asyncio
async def test_get_revocation_log(service, token_repo):
    revoked_token = build_token(status=TokenStatus.REVOKED)
    token_repo.list_by_tenant.return_value = ([revoked_token, build_token()], 2)

    log = await service.get_revocation_log("tenant-1", limit=10, offset=0)
    assert len(log) == 1
    assert log[0]["token_id"] == "token-1"
    assert log[0]["status"] == TokenStatus.REVOKED.value


@pytest.mark.asyncio
async def test_get_revocation_log_empty_on_error(service, token_repo):
    token_repo.list_by_tenant.side_effect = Exception("db error")

    log = await service.get_revocation_log("tenant-1")
    assert log == []


@pytest.mark.asyncio
async def test_revoke_token_repo_failure(service, token_repo):
    token_repo.revoke.return_value = None

    result = await service.revoke_token(
        tenant_id="tenant-1",
        token_id="token-1",
    )

    assert result["total_revoked"] == 0
    token_repo.revoke.assert_awaited_once_with("tenant-1", "token-1")
