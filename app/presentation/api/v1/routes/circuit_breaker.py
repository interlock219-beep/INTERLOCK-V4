from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.domain.services.circuit_breaker_service import CircuitBreakerService
from app.presentation.api.dependencies.auth import CurrentUser

router = APIRouter(prefix="/circuit-breakers", tags=["Circuit Breakers"])

_breaker = CircuitBreakerService(
    failure_threshold=5,
    recovery_timeout_seconds=30.0,
    success_threshold=2,
)


@router.get("/status/{resource}")
async def get_circuit_status(
    resource: str,
    current_user: CurrentUser,
) -> dict[str, object]:
    """Get circuit breaker state for a resource."""
    return _breaker.get_state(resource)


@router.post("/allow/{resource}")
async def check_circuit_allow(
    resource: str,
    current_user: CurrentUser,
) -> dict[str, object]:
    """Check whether requests to a resource are allowed."""
    decision = _breaker.allow_request(resource)
    if not decision.get("allowed"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=decision.get("state", "open"),
        )
    return decision


@router.post("/success/{resource}")
async def record_circuit_success(
    resource: str,
    current_user: CurrentUser,
) -> dict[str, object]:
    """Record a successful call for a resource."""
    _breaker.record_success(resource)
    return {"recorded": True, "resource": resource}


@router.post("/failure/{resource}")
async def record_circuit_failure(
    resource: str,
    current_user: CurrentUser,
) -> dict[str, object]:
    """Record a failed call for a resource."""
    _breaker.record_failure(resource)
    return {"recorded": True, "resource": resource}


@router.post("/reset/{resource}")
async def reset_circuit(
    resource: str,
    current_user: CurrentUser,
) -> dict[str, object]:
    """Reset circuit breaker state for a resource."""
    _breaker.reset(resource)
    return {"reset": True, "resource": resource}
