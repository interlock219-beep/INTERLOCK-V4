from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.domain.services.risk_engine import RiskEngine
from app.presentation.api.dependencies.auth import CurrentUser

router = APIRouter(prefix="/risk", tags=["Risk"])


@router.post("/evaluate")
async def evaluate_risk(
    context: dict[str, Any],
    current_user: CurrentUser,
) -> dict[str, object]:
    """Evaluate risk for an authorization context. RISK-001."""
    required = ["agent_id", "action", "tool", "resource"]
    missing = [k for k in required if k not in context]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required fields: {missing}",
        )

    engine = RiskEngine()
    result = engine.evaluate(
        context=context,
        agent_history=context.get("agent_history"),
        authority_grants=context.get("authority_grants"),
        recent_actions=context.get("recent_actions"),
    )
    return result
