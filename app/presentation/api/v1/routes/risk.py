from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.domain.services.risk_engine import RiskEngine
from app.domain.value_objects.authorization_context import AuthorizationContext
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

    auth_context = AuthorizationContext(
        user_id=current_user.id,
        agent_id=context["agent_id"],
        proposed_tool=context["tool"],
        tenant_id=current_user.tenant_id,
        action=context["action"],
        resource=context["resource"],
        user_role=current_user.role,
    )
    engine = RiskEngine()
    result = engine.evaluate(
        context=auth_context,
        agent_history=context.get("agent_history"),
        authority_grants=context.get("authority_grants"),
        recent_actions=context.get("recent_actions"),
    )
    return result
