from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.domain.services.velocity_tracker import VelocityTracker
from app.presentation.api.dependencies.auth import CurrentUser

router = APIRouter(prefix="/velocity", tags=["Velocity"])


_tracker = VelocityTracker(
    window_seconds=60,
    max_requests=100,
    max_cumulative_value=10_000.0,
    max_cumulative_risk=5.0,
    max_sensitive_operations=10,
)


@router.post("/record")
async def record_velocity(
    current_user: CurrentUser,
    scope: str,
    value: float = 0.0,
    risk_score: float = 0.0,
    is_sensitive: bool = False,
) -> dict[str, object]:
    """Record a velocity event for a scope."""
    result = _tracker.record(
        scope=scope,
        value=value,
        risk_score=risk_score,
        is_sensitive=is_sensitive,
    )
    return result


@router.get("/state/{scope}")
async def get_velocity_state(
    current_user: CurrentUser,
    scope: str,
) -> dict[str, object]:
    """Get current velocity state for a scope."""
    return _tracker.get_state(scope)


@router.post("/reset")
async def reset_velocity(
    current_user: CurrentUser,
    scope: str | None = None,
) -> dict[str, object]:
    """Reset velocity tracking."""
    _tracker.reset(scope)
    return {"reset": True, "scope": scope}
