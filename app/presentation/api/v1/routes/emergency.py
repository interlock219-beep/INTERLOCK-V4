from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.domain.services.emergency_control_service import EmergencyControlService
from app.domain.services.token_revocation_service import TokenRevocationService
from app.domain.value_objects.authorization_decision import AuthorizationDecision

logger = logging.getLogger("intentlock.api.emergency")

emergency_router = APIRouter(prefix="/emergency", tags=["emergency-control"])
token_revocation_router = APIRouter(
    prefix="/token-revocation", tags=["token-revocation"]
)

emergency_service = EmergencyControlService()
token_revocation_service: TokenRevocationService | None = None


def set_token_revocation_service(service: TokenRevocationService) -> None:
    global token_revocation_service
    token_revocation_service = service


@emergency_router.post("/deny/{tenant_id}")
async def activate_emergency_deny(
    tenant_id: str,
    activated_by: str,
    reason: str = "",
    approval_ids: list[str] | None = None,
) -> dict:
    """Activate emergency deny for a tenant.

    Blocks ALL execution. Requires explicit approval tracking.
    AUTH-030
    """
    result = emergency_service.activate_emergency_deny(
        tenant_id=tenant_id,
        activated_by=activated_by,
        reason=reason,
        approval_ids=approval_ids,
    )
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=result["error"],
        )
    return result


@emergency_router.post("/deny/{tenant_id}/deactivate")
async def deactivate_emergency_deny(
    tenant_id: str,
    deactivated_by: str,
    reason: str = "",
) -> dict:
    """Deactivate emergency deny. AUTH-030."""
    result = emergency_service.deactivate_emergency_deny(
        tenant_id=tenant_id,
        deactivated_by=deactivated_by,
        reason=reason,
    )
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["error"],
        )
    return result


@emergency_router.post("/allow/{tenant_id}")
async def activate_emergency_allow(
    tenant_id: str,
    activated_by: str,
    allowed_actions: list[str],
    allowed_tools: list[str] | None = None,
    allowed_agents: list[str] | None = None,
    expires_hours: int = 1,
    approval_ids: list[str] | None = None,
    reason: str = "",
) -> dict:
    """Activate emergency allow with explicit controls. AUTH-031.

    Requires explicit action list and time limit.
    """
    from datetime import datetime, timedelta

    expires_at = datetime.now() + timedelta(hours=expires_hours)
    result = emergency_service.activate_emergency_allow(
        tenant_id=tenant_id,
        activated_by=activated_by,
        allowed_actions=allowed_actions,
        allowed_tools=allowed_tools,
        allowed_agents=allowed_agents,
        expires_at=expires_at,
        approval_ids=approval_ids,
        reason=reason,
    )
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"],
        )
    return result


@emergency_router.post("/allow/{tenant_id}/deactivate")
async def deactivate_emergency_allow(
    tenant_id: str,
    deactivated_by: str,
) -> dict:
    """Deactivate emergency allow. AUTH-031."""
    result = emergency_service.deactivate_emergency_allow(
        tenant_id=tenant_id,
        deactivated_by=deactivated_by,
    )
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["error"],
        )
    return result


@emergency_router.get("/status/{tenant_id}")
async def get_emergency_status(tenant_id: str) -> dict:
    """Get emergency control status for a tenant."""
    return emergency_service.get_emergency_status(tenant_id)


@emergency_router.get("/log")
async def get_emergency_log(limit: int = 100) -> dict:
    """Get emergency control audit log."""
    return {
        "entries": emergency_service.get_emergency_log(limit),
        "total": len(emergency_service.get_emergency_log(limit)),
    }


@token_revocation_router.post("/revoke")
async def revoke_token(
    tenant_id: str,
    token_id: str,
    reason: str = "manual",
    revoked_by: str = "system",
    cascade: bool = False,
) -> dict:
    """Revoke a token with optional cascade. TOK-012."""
    if token_revocation_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token revocation service not configured",
        )
    return await token_revocation_service.revoke_token(
        tenant_id=tenant_id,
        token_id=token_id,
        reason=reason,
        revoked_by=revoked_by,
        cascade=cascade,
    )


@token_revocation_router.post("/revoke-agent/{tenant_id}/{agent_id}")
async def revoke_agent_tokens(
    tenant_id: str,
    agent_id: str,
    reason: str = "compromised",
    revoked_by: str = "system",
) -> dict:
    """Revoke all tokens for an agent. TOK-012."""
    if token_revocation_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token revocation service not configured",
        )
    revoked = await token_revocation_service.revoke_tokens_by_agent(
        tenant_id=tenant_id,
        agent_id=agent_id,
        reason=reason,
        revoked_by=revoked_by,
    )
    return {
        "revoked_token_ids": revoked,
        "count": len(revoked),
        "reason": reason,
    }


@token_revocation_router.post("/revoke-tenant/{tenant_id}")
async def revoke_tenant_tokens(
    tenant_id: str,
    reason: str = "tenant_containment",
    revoked_by: str = "system",
) -> dict:
    """Emergency revoke all tokens in a tenant. TOK-012."""
    if token_revocation_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token revocation service not configured",
        )
    revoked = await token_revocation_service.revoke_tokens_by_tenant(
        tenant_id=tenant_id,
        reason=reason,
        revoked_by=revoked_by,
    )
    return {
        "revoked_token_ids": revoked,
        "count": len(revoked),
        "reason": reason,
    }


@token_revocation_router.get("/log/{tenant_id}")
async def get_revocation_log(
    tenant_id: str,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """Get revocation audit log. TOK-012."""
    if token_revocation_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token revocation service not configured",
        )
    return {
        "entries": await token_revocation_service.get_revocation_log(
            tenant_id, limit, offset
        ),
    }
