from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.domain.services.distributed_lock_service import DistributedLockService


@pytest.fixture
def redis_client():
    client = MagicMock()
    client.available = True
    return client


@pytest.fixture
def service(redis_client):
    return DistributedLockService(redis_client)


def test_acquire_lock_success(service, redis_client):
    redis_client.set_nx.return_value = True

    result = service.acquire_lock(
        tenant_id="tenant-1",
        resource="plan-1",
        ttl_seconds=60,
        owner="agent-1",
    )

    assert result["acquired"] is True
    assert result["lock_id"] is not None
    assert result["tenant_id"] == "tenant-1"
    assert result["resource"] == "plan-1"
    assert result["owner"] == "agent-1"
    redis_client.set_nx.assert_called_once()


def test_acquire_lock_already_held(service, redis_client):
    redis_client.set_nx.return_value = False
    redis_client.get.return_value = "existing-lock-id"

    result = service.acquire_lock(
        tenant_id="tenant-1",
        resource="plan-1",
    )

    assert result["acquired"] is False
    assert result["error"] == "lock_already_held"
    assert result["existing_lock_id"] == "existing-lock-id"


def test_release_lock_success(service, redis_client):
    redis_client.get.return_value = "lock-123"

    result = service.release_lock("tenant-1", "plan-1", "lock-123")
    assert result["released"] is True
    redis_client.delete.assert_called_once()


def test_release_lock_not_found(service, redis_client):
    redis_client.get.return_value = None

    result = service.release_lock("tenant-1", "plan-1", "lock-123")
    assert result["released"] is False
    assert result["error"] == "lock_not_found"


def test_release_lock_owner_mismatch(service, redis_client):
    redis_client.get.return_value = "other-lock-id"

    result = service.release_lock("tenant-1", "plan-1", "lock-123")
    assert result["released"] is False
    assert result["error"] == "lock_owner_mismatch"


def test_is_locked_true(service, redis_client):
    redis_client.get.return_value = "lock-123"

    result = service.is_locked("tenant-1", "plan-1")
    assert result["locked"] is True
    assert result["lock_id"] == "lock-123"


def test_is_locked_false(service, redis_client):
    redis_client.get.return_value = None

    result = service.is_locked("tenant-1", "plan-1")
    assert result["locked"] is False


def test_extend_lock_success(service, redis_client):
    redis_client.get.return_value = "lock-123"
    redis_client.expire.return_value = True

    result = service.extend_lock("tenant-1", "plan-1", "lock-123", ttl_seconds=120)
    assert result["extended"] is True
    redis_client.expire.assert_called_once()


def test_extend_lock_not_found(service, redis_client):
    redis_client.get.return_value = None

    result = service.extend_lock("tenant-1", "plan-1", "lock-123")
    assert result["extended"] is False
    assert result["error"] == "lock_not_found"


def test_extend_lock_owner_mismatch(service, redis_client):
    redis_client.get.return_value = "other-lock-id"

    result = service.extend_lock("tenant-1", "plan-1", "lock-123")
    assert result["extended"] is False
    assert result["error"] == "lock_owner_mismatch"


def test_refresh_heartbeat_delegates_to_extend(service, redis_client):
    redis_client.get.return_value = "lock-123"
    redis_client.expire.return_value = True

    result = service.refresh_heartbeat("tenant-1", "plan-1", "lock-123", 120)
    assert result["extended"] is True
    redis_client.expire.assert_called_once()
