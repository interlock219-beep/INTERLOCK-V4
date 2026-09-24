from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.interfaces.execution_token_service import ExecutionTokenService
from app.presentation.api.dependencies.auth import CurrentUser

router = APIRouter(prefix="/tokens", tags=["Tokens"])


def _get_token_service() -> ExecutionTokenService:
    from app.infrastructure.security.ed25519_execution_token_service import (
        Ed25519ExecutionTokenService,
    )
    from app.infrastructure.security.env_key_manager import EnvKeyManager
    from app.infrastructure.redis.nonce_store import RedisNonceStore

    key_manager = EnvKeyManager()
    nonce_store = RedisNonceStore()
    return Ed25519ExecutionTokenService(
        key_manager=key_manager,
        nonce_store=nonce_store,
    )


class TokenIntrospectionResponse:
    active: bool
    token_id: str | None = None
    agent_id: str | None = None
    tool: str | None = None
    tenant_id: str | None = None
    exp: int | None = None
    iat: int | None = None
    error: str | None = None


@router.post("/introspect")
async def introspect_token(
    token: str,
    current_user: CurrentUser,
) -> dict[str, object]:
    """Introspect an execution token without consuming its nonce. TOK-013."""
    service = _get_token_service()
    try:
        payload = service.peek_execution_token(token)
        return {
            "active": True,
            "token_id": payload.get("jti"),
            "agent_id": payload.get("agent_id"),
            "tool": payload.get("tool"),
            "tenant_id": payload.get("tenant_id"),
            "exp": payload.get("exp"),
            "iat": payload.get("iat"),
        }
    except Exception as exc:
        return {
            "active": False,
            "error": str(exc),
        }


@router.get("/jwks")
async def get_jwks(current_user: CurrentUser) -> dict[str, object]:
    """Return JWKS for token verification."""
    service = _get_token_service()
    return service.get_jwks()


@router.post("/claims/validate")
async def validate_token_claims(
    body: dict[str, Any],
    current_user: CurrentUser,
) -> dict[str, object]:
    """Validate token claims against expected values. TOK-004/006/008/009."""
    token = body.get("token")
    expected_audience = body.get("expected_audience")
    expected_resource = body.get("expected_resource")
    expected_tool = body.get("expected_tool")
    expected_tenant = body.get("expected_tenant")
    expected_agent = body.get("expected_agent")

    if not token:
        raise HTTPException(status_code=400, detail="token is required")

    service = _get_token_service()
    try:
        payload = service.peek_execution_token(token)
    except Exception as exc:
        return {
            "valid": False,
            "error": str(exc),
            "claim_checks": {},
        }

    claim_checks: dict[str, dict[str, Any]] = {}
    all_valid = True

    if expected_audience is not None:
        aud = payload.get("aud") or payload.get("audience")
        valid = aud == expected_audience
        claim_checks["audience"] = {
            "expected": expected_audience,
            "actual": aud,
            "valid": valid,
        }
        if not valid:
            all_valid = False

    if expected_resource is not None:
        res = payload.get("resource") or payload.get("target_resource")
        valid = res == expected_resource
        claim_checks["resource"] = {
            "expected": expected_resource,
            "actual": res,
            "valid": valid,
        }
        if not valid:
            all_valid = False

    if expected_tool is not None:
        tool = payload.get("tool")
        valid = tool == expected_tool
        claim_checks["tool"] = {
            "expected": expected_tool,
            "actual": tool,
            "valid": valid,
        }
        if not valid:
            all_valid = False

    if expected_tenant is not None:
        tenant = payload.get("tenant_id") or payload.get("tenant")
        valid = tenant == expected_tenant
        claim_checks["tenant"] = {
            "expected": expected_tenant,
            "actual": tenant,
            "valid": valid,
        }
        if not valid:
            all_valid = False

    if expected_agent is not None:
        agent = payload.get("agent_id") or payload.get("agent")
        valid = agent == expected_agent
        claim_checks["agent"] = {
            "expected": expected_agent,
            "actual": agent,
            "valid": valid,
        }
        if not valid:
            all_valid = False

    return {
        "valid": all_valid,
        "token_id": payload.get("jti"),
        "claim_checks": claim_checks,
    }
