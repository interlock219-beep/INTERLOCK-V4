from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from app.infrastructure.redis.client import RedisClient, RedisUnavailableError

logger = logging.getLogger("intentlock.distributed_lock")


class DistributedLockService:
    """Distributed lock manager backed by Redis.

    Provides:
    - acquire_lock(tenant_id, resource, ttl_seconds, owner) -> lock_id
    - release_lock(tenant_id, resource, lock_id) -> bool
    - is_locked(tenant_id, resource) -> bool
    - extend_lock(tenant_id, resource, lock_id, ttl_seconds) -> bool
    - refresh_heartbeat(tenant_id, resource, lock_id, ttl_seconds) -> bool

    Lock keys are scoped by tenant_id to prevent cross-tenant interference.
    """

    def __init__(self, redis_client: RedisClient) -> None:
        self._redis = redis_client

    def _key(self, tenant_id: str, resource: str) -> str:
        return f"lock:{tenant_id}:{resource}"

    def acquire_lock(
        self,
        tenant_id: str,
        resource: str,
        ttl_seconds: int = 60,
        owner: str = "system",
    ) -> dict[str, Any]:
        """Acquire a distributed lock.

        Returns a lock token on success. Returns failure dict if lock
        is already held by another owner.
        """
        lock_id = str(uuid.uuid4())
        key = self._key(tenant_id, resource)
        try:
            acquired = self._redis.set_nx(key, lock_id, ex=ttl_seconds)
        except RedisUnavailableError as exc:
            logger.error("Failed to acquire lock: %s", exc)
            return {
                "acquired": False,
                "error": "distributed_lock_unavailable",
                "lock_id": None,
            }

        if acquired:
            logger.info(
                "Lock acquired: tenant=%s resource=%s owner=%s ttl=%ds",
                tenant_id,
                resource,
                owner,
                ttl_seconds,
            )
            return {
                "acquired": True,
                "lock_id": lock_id,
                "tenant_id": tenant_id,
                "resource": resource,
                "owner": owner,
                "ttl_seconds": ttl_seconds,
                "acquired_at": time.time(),
            }

        existing = self._redis.get(key)
        logger.warning(
            "Lock already held: tenant=%s resource=%s owner=%s existing_lock=%s",
            tenant_id,
            resource,
            owner,
            existing,
        )
        return {
            "acquired": False,
            "error": "lock_already_held",
            "existing_lock_id": existing,
            "lock_id": None,
        }

    def release_lock(
        self,
        tenant_id: str,
        resource: str,
        lock_id: str | None,
    ) -> dict[str, Any]:
        """Release a distributed lock.

        Only the owner with the matching lock_id can release.
        """
        key = self._key(tenant_id, resource)
        if lock_id is None:
            return {"released": False, "error": "missing_lock_id"}

        try:
            existing = self._redis.get(key)
        except RedisUnavailableError as exc:
            logger.error("Failed to release lock: %s", exc)
            return {"released": False, "error": "distributed_lock_unavailable"}

        if existing is None:
            return {"released": False, "error": "lock_not_found"}

        if existing != lock_id:
            logger.warning(
                "Lock release mismatch: tenant=%s resource=%s expected=%s actual=%s",
                tenant_id,
                resource,
                lock_id,
                existing,
            )
            return {"released": False, "error": "lock_owner_mismatch"}

        self._redis.delete(key)
        logger.info(
            "Lock released: tenant=%s resource=%s owner_lock=%s",
            tenant_id,
            resource,
            lock_id,
        )
        return {"released": True, "lock_id": lock_id}

    def is_locked(self, tenant_id: str, resource: str) -> dict[str, Any]:
        """Check whether a resource is currently locked."""
        key = self._key(tenant_id, resource)
        try:
            existing = self._redis.get(key)
        except RedisUnavailableError as exc:
            logger.error("Failed to check lock: %s", exc)
            return {"locked": False, "error": "distributed_lock_unavailable"}

        return {
            "locked": existing is not None,
            "lock_id": existing,
            "tenant_id": tenant_id,
            "resource": resource,
        }

    def extend_lock(
        self,
        tenant_id: str,
        resource: str,
        lock_id: str,
        ttl_seconds: int = 60,
    ) -> dict[str, Any]:
        """Extend TTL on an existing lock if still owned by caller."""
        key = self._key(tenant_id, resource)
        try:
            existing = self._redis.get(key)
        except RedisUnavailableError as exc:
            logger.error("Failed to extend lock: %s", exc)
            return {"extended": False, "error": "distributed_lock_unavailable"}

        if existing is None:
            return {"extended": False, "error": "lock_not_found"}
        if existing != lock_id:
            return {"extended": False, "error": "lock_owner_mismatch"}

        refreshed = self._redis.expire(key, ttl_seconds)
        logger.info(
            "Lock extended: tenant=%s resource=%s ttl=%ds refreshed=%s",
            tenant_id,
            resource,
            ttl_seconds,
            refreshed,
        )
        return {
            "extended": bool(refreshed),
            "lock_id": lock_id,
            "ttl_seconds": ttl_seconds,
        }

    def refresh_heartbeat(
        self,
        tenant_id: str,
        resource: str,
        lock_id: str,
        ttl_seconds: int = 60,
    ) -> dict[str, Any]:
        """Refresh lock heartbeat to prevent premature expiry."""
        return self.extend_lock(tenant_id, resource, lock_id, ttl_seconds)
