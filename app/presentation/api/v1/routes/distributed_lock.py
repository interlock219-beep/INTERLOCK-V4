from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.domain.services.distributed_lock_service import DistributedLockService
from app.infrastructure.redis.client import RedisClient
from app.presentation.api.dependencies.auth import CurrentUser

router = APIRouter(prefix="/locks", tags=["Distributed Locks"])


def _get_lock_service() -> DistributedLockService:
    from app.infrastructure.config.settings import get_settings

    settings = get_settings()
    redis_url = settings.redis_url
    redis_client = RedisClient(url=redis_url)
    return DistributedLockService(redis_client)


@router.post("/acquire")
async def acquire_lock(
    current_user: CurrentUser,
    tenant_id: str,
    resource: str,
    ttl_seconds: int = 60,
    owner: str = "system",
) -> dict[str, object]:
    """Acquire a distributed lock. Returns lock token on success."""
    service = _get_lock_service()
    result = service.acquire_lock(tenant_id, resource, ttl_seconds, owner)
    if not result.get("acquired"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=result.get("error", "lock_unavailable"),
        )
    return result


@router.post("/release")
async def release_lock(
    current_user: CurrentUser,
    tenant_id: str,
    resource: str,
    lock_id: str,
) -> dict[str, object]:
    """Release a distributed lock by lock token."""
    service = _get_lock_service()
    result = service.release_lock(tenant_id, resource, lock_id)
    if not result.get("released"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "release_failed"),
        )
    return result


@router.get("/status/{tenant_id}/{resource}")
async def lock_status(
    current_user: CurrentUser,
    tenant_id: str,
    resource: str,
) -> dict[str, object]:
    """Check lock status for a resource."""
    service = _get_lock_service()
    return service.is_locked(tenant_id, resource)


@router.post("/extend")
async def extend_lock(
    current_user: CurrentUser,
    tenant_id: str,
    resource: str,
    lock_id: str,
    ttl_seconds: int = 60,
) -> dict[str, object]:
    """Extend TTL on an existing lock."""
    service = _get_lock_service()
    result = service.extend_lock(tenant_id, resource, lock_id, ttl_seconds)
    if not result.get("extended"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "extension_failed"),
        )
    return result
