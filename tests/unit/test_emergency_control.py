from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.domain.repositories.emergency_state_repository import EmergencyStateRepository
from app.domain.services.emergency_control_service import EmergencyControlService
from app.domain.value_objects.authorization_decision import AuthorizationDecision


@pytest.fixture
def repository():
    return AsyncMock(spec=EmergencyStateRepository)


@pytest.fixture
def service(repository):
    return EmergencyControlService(emergency_state_repository=repository)


@pytest.mark.asyncio
async def test_activate_emergency_deny(service, repository):
    repository.get_by_tenant.return_value = None
    result = await service.activate_emergency_deny(
        tenant_id="tenant-1",
        activated_by="admin-1",
        reason="security incident",
        approval_ids=["approval-1"],
    )
    assert result["success"] is True
    assert result["emergency_deny_active"] is True
    assert result["record"]["reason"] == "security incident"
    assert result["record"]["activated_by"] == "admin-1"


@pytest.mark.asyncio
async def test_deactivate_emergency_deny(service, repository):
    repository.get_by_tenant.return_value = None
    await service.activate_emergency_deny(
        tenant_id="tenant-1", activated_by="admin-1",
    )
    result = await service.deactivate_emergency_deny(
        tenant_id="tenant-1", deactivated_by="admin-2",
    )
    assert result["success"] is True
    assert result["emergency_deny_active"] is False


@pytest.mark.asyncio
async def test_is_emergency_deny_active(service, repository):
    repository.get_by_tenant.return_value = None
    assert await service.is_emergency_deny_active("tenant-1") is False
    await service.activate_emergency_deny(
        tenant_id="tenant-1", activated_by="admin-1",
    )
    assert await service.is_emergency_deny_active("tenant-1") is True


@pytest.mark.asyncio
async def test_activate_emergency_deny_requires_approval(service, repository):
    repository.get_by_tenant.return_value = None
    result = await service.activate_emergency_deny(
        tenant_id="tenant-1",
        activated_by="admin-1",
        reason="test",
        approval_ids=["approval-1"],
    )
    assert result["success"] is True
    assert len(result["record"]["approval_ids"]) == 1


@pytest.mark.asyncio
async def test_activate_emergency_allow_with_controls(service, repository):
    from datetime import timedelta
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    repository.get_by_tenant.return_value = None
    result = await service.activate_emergency_allow(
        tenant_id="tenant-1",
        activated_by="admin-1",
        allowed_actions=["read", "write"],
        allowed_tools=["file_reader"],
        allowed_agents=["agent-1"],
        expires_at=expires_at,
        approval_ids=["approval-1"],
        reason="controlled recovery",
    )
    assert result["success"] is True
    assert result["emergency_allow_active"] is True
    record = result["record"]
    assert record["allowed_actions"] == ["read", "write"]
    assert record["expires_at"] is not None


@pytest.mark.asyncio
async def test_activate_emergency_allow_requires_actions(service, repository):
    result = await service.activate_emergency_allow(
        tenant_id="tenant-1",
        activated_by="admin-1",
        allowed_actions=[],
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    assert result["success"] is False
    assert "requires explicit" in result["error"]


@pytest.mark.asyncio
async def test_activate_emergency_allow_requires_expiry(service, repository):
    result = await service.activate_emergency_allow(
        tenant_id="tenant-1",
        activated_by="admin-1",
        allowed_actions=["read"],
    )
    assert result["success"] is False
    assert "expires_at" in result["error"]


@pytest.mark.asyncio
async def test_emergency_deny_blocks_authorization(service, repository):
    repository.get_by_tenant.return_value = None
    await service.activate_emergency_deny(
        tenant_id="tenant-1", activated_by="admin-1",
    )
    decision, reason = await service.evaluate_authorization(
        tenant_id="tenant-1",
        agent_id="agent-1",
        action="execute",
        tool="file_reader",
    )
    assert decision == AuthorizationDecision.DENY
    assert "EMERGENCY DENY" in reason


@pytest.mark.asyncio
async def test_emergency_allow_authorizes_listed_action(service, repository):
    from datetime import timedelta
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    repository.get_by_tenant.return_value = None
    await service.activate_emergency_allow(
        tenant_id="tenant-1",
        activated_by="admin-1",
        allowed_actions=["execute"],
        expires_at=expires_at,
    )
    decision, reason = await service.evaluate_authorization(
        tenant_id="tenant-1",
        agent_id="agent-1",
        action="execute",
        tool="file_reader",
    )
    assert decision == AuthorizationDecision.ALLOW


@pytest.mark.asyncio
async def test_emergency_allow_denies_unlisted_action(service, repository):
    from datetime import timedelta
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    repository.get_by_tenant.return_value = None
    await service.activate_emergency_allow(
        tenant_id="tenant-1",
        activated_by="admin-1",
        allowed_actions=["read"],
        expires_at=expires_at,
    )
    decision, reason = await service.evaluate_authorization(
        tenant_id="tenant-1",
        agent_id="agent-999",
        action="execute",
        tool="file_reader",
    )
    assert decision == AuthorizationDecision.DENY


@pytest.mark.asyncio
async def test_emergency_allow_denies_expired(service, repository):
    from datetime import timedelta
    expired = datetime.now(UTC) - timedelta(minutes=5)
    repository.get_by_tenant.return_value = None
    await service.activate_emergency_allow(
        tenant_id="tenant-1",
        activated_by="admin-1",
        allowed_actions=["execute"],
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    service._emergency_allow_active["tenant-1"]["expires_at"] = expired.isoformat()
    decision, reason = await service.evaluate_authorization(
        tenant_id="tenant-1",
        agent_id="agent-1",
        action="execute",
        tool="file_reader",
    )
    assert decision == AuthorizationDecision.DENY
    assert "expired" in reason


@pytest.mark.asyncio
async def test_emergency_allow_denies_unlisted_agent(service, repository):
    from datetime import timedelta
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    repository.get_by_tenant.return_value = None
    await service.activate_emergency_allow(
        tenant_id="tenant-1",
        activated_by="admin-1",
        allowed_actions=["execute"],
        allowed_agents=["agent-1"],
        expires_at=expires_at,
    )
    decision, reason = await service.evaluate_authorization(
        tenant_id="tenant-1",
        agent_id="agent-999",
        action="execute",
        tool="file_reader",
    )
    assert decision == AuthorizationDecision.DENY
    assert "not in emergency allow list" in reason


@pytest.mark.asyncio
async def test_get_emergency_status(service, repository):
    repository.get_by_tenant.return_value = None
    await service.activate_emergency_deny(
        tenant_id="tenant-1", activated_by="admin-1",
    )
    status = await service.get_emergency_status("tenant-1")
    assert status["tenant_id"] == "tenant-1"
    assert status["emergency_deny_active"] is True


@pytest.mark.asyncio
async def test_get_emergency_log(service, repository):
    repository.get_by_tenant.return_value = None
    await service.activate_emergency_deny(
        tenant_id="tenant-1", activated_by="admin-1",
    )
    log = service.get_emergency_log()
    assert len(log) >= 1
    assert log[0]["action"] == "emergency_deny_activate"


@pytest.mark.asyncio
async def test_emergency_control_serialization(service, repository):
    repository.get_by_tenant.return_value = None
    result = await service.activate_emergency_deny(
        tenant_id="tenant-1", activated_by="admin-1",
    )
    record = result["record"]
    assert "tenant_id" in record
    assert "activated_at" in record
    datetime.fromisoformat(record["activated_at"])
