import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.application.interfaces.execution_token_service import ExecutionTokenService
from app.domain.entities.agent import AgentStatus
from app.domain.entities.agent_session import AgentSessionStatus
from app.domain.entities.protected_action import ActionStatus, ProtectedAction
from app.domain.exceptions.domain_errors import (
    ApprovalRequiredError,
    AuthorizationError,
    ExecutionTokenError,
)
from app.domain.models.intent import AgentActionDAG, IntentProofResponse
from app.domain.services.authorization_service import AuthorizationService
from app.domain.services.central_policy_engine import CentralPolicyEngine
from app.domain.services.intent_evaluator import IntentEvaluatorService
from app.domain.value_objects.authorization_context import AuthorizationContext
from app.domain.value_objects.authorization_decision import AuthorizationDecision
from app.infrastructure.config.settings import get_settings
from app.infrastructure.logging.audit_logger import log_verification
from app.infrastructure.observability.metrics import metrics
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_agent_repository import (
    SQLAlchemyAgentRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_agent_session_repository import (
    SQLAlchemyAgentSessionRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_protected_action_repository import (
    SQLAlchemyProtectedActionRepository,
)
from app.presentation.api.dependencies.auth import CurrentUser, get_user_tenant_id
from app.presentation.api.dependencies.emergency_guard import assert_execution_permitted
from app.presentation.api.dependencies.security import get_execution_token_service

router = APIRouter(prefix="/intent", tags=["Intent"])

_evaluator = IntentEvaluatorService()
_authz_service = AuthorizationService()
_policy_engine = CentralPolicyEngine.from_file()


class ExecuteRequest(BaseModel):
    execution_token: str
    agent_id: str | None = None


def _extract_jti(token: str) -> str | None:
    try:
        parts = token.split(".")
        payload = json.loads(__import__("base64").b64decode(parts[1] + "=="))
        return str(payload.get("jti", "")) or None
    except Exception:
        return None


@router.post("/verify", response_model=IntentProofResponse)
async def verify_intent(
    request: Request,
    agent_action: AgentActionDAG,
    current_user: CurrentUser,
    execution_token_service: Annotated[ExecutionTokenService, Depends(get_execution_token_service)],
) -> IntentProofResponse:
    correlation_id = getattr(request.state, "correlation_id", "")

    if (
        current_user.tenant_id
        and agent_action.tenant_id
        and current_user.tenant_id != agent_action.tenant_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant mismatch: request tenant does not match user tenant.",
        )

    auth_context = AuthorizationContext(
        user_id=current_user.id,
        agent_id=agent_action.agent_id,
        proposed_tool=agent_action.proposed_tool,
        tenant_id=agent_action.tenant_id,
        action=agent_action.action,
        resource=agent_action.resource or "",
        service_id=agent_action.service_id,
        user_role=current_user.role,
    )
    auth_decision, auth_reason = _authz_service.authorize(auth_context)

    if auth_decision == AuthorizationDecision.DENY:
        metrics.increment_authorization_denial(auth_reason)
        log_verification(
            agent_id=agent_action.agent_id,
            proposed_tool=agent_action.proposed_tool,
            tool_arguments=agent_action.tool_arguments,
            verification_status="AUTH_DENIED",
            rejection_reason=auth_reason,
            correlation_id=correlation_id,
        )
        raise AuthorizationError(auth_reason)

    if auth_decision == AuthorizationDecision.REQUIRE_HITL:
        log_verification(
            agent_id=agent_action.agent_id,
            proposed_tool=agent_action.proposed_tool,
            tool_arguments=agent_action.tool_arguments,
            verification_status="AUTH_REQUIRE_HITL",
            rejection_reason=auth_reason,
            correlation_id=correlation_id,
        )
        raise ApprovalRequiredError(auth_reason)

    policy_result = _policy_engine.evaluate(auth_context)
    if policy_result.effect == AuthorizationDecision.DENY:
        metrics.increment_policy_decision(policy_result.effect.value)
        log_verification(
            agent_id=agent_action.agent_id,
            proposed_tool=agent_action.proposed_tool,
            tool_arguments=agent_action.tool_arguments,
            verification_status="POLICY_DENIED",
            rejection_reason=policy_result.reason,
            correlation_id=correlation_id,
        )
        raise AuthorizationError(policy_result.reason)

    if policy_result.effect == AuthorizationDecision.REQUIRE_HITL:
        metrics.increment_policy_decision(policy_result.effect.value)
        log_verification(
            agent_id=agent_action.agent_id,
            proposed_tool=agent_action.proposed_tool,
            tool_arguments=agent_action.tool_arguments,
            verification_status="POLICY_REQUIRE_HITL",
            rejection_reason=policy_result.reason,
            correlation_id=correlation_id,
        )
        raise ApprovalRequiredError(policy_result.reason)

    result = _evaluator.evaluate(agent_action)
    if not result.is_valid:
        metrics.increment_policy_decision("blocked")
        log_verification(
            agent_id=agent_action.agent_id,
            proposed_tool=agent_action.proposed_tool,
            tool_arguments=agent_action.tool_arguments,
            verification_status="BLOCKED",
            rejection_reason=result.reason,
            correlation_id=correlation_id,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=result.reason)

    settings = get_settings()
    tenant_id = agent_action.tenant_id or current_user.tenant_id
    ephemeral_token = execution_token_service.create_execution_token(
        agent_id=agent_action.agent_id,
        tool=agent_action.proposed_tool,
        ttl_seconds=settings.execution_token_ttl_seconds,
        subject=str(current_user.id),
        tenant_id=tenant_id,
    )
    metrics.increment_execution_tokens_issued()
    token_jti = _extract_jti(ephemeral_token)

    log_verification(
        agent_id=agent_action.agent_id,
        proposed_tool=agent_action.proposed_tool,
        tool_arguments=agent_action.tool_arguments,
        verification_status="PERMITTED",
        rejection_reason="",
        correlation_id=correlation_id,
        jti=token_jti,
    )
    return IntentProofResponse(
        is_valid=True,
        confidence_score=result.confidence_score,
        reason=result.reason,
        ephemeral_token=ephemeral_token,
        requires_hitl=False,
    )


@router.post("/execute")
async def execute_intent(
    request: Request,
    body: ExecuteRequest,
    current_user: CurrentUser,
    execution_token_service: Annotated[ExecutionTokenService, Depends(get_execution_token_service)],
) -> dict[str, str]:
    """Log execution intent for a verified ephemeral token.

    This endpoint performs an authoritative containment check AND
    consumes the token.  The token cannot be reused after this call.
    """
    correlation_id = getattr(request.state, "correlation_id", "")

    try:
        payload = execution_token_service.verify_execution_token(body.execution_token)
    except ExecutionTokenError as exc:
        metrics.increment_execution_tokens_replayed()
        token_jti = _extract_jti(body.execution_token)
        log_verification(
            agent_id="unknown",
            proposed_tool="unknown",
            tool_arguments={},
            verification_status="REPLAY_BLOCKED",
            rejection_reason=str(exc),
            correlation_id=correlation_id,
            jti=token_jti,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    token_subject = str(payload.get("sub", ""))
    if token_subject != str(current_user.id):
        log_verification(
            agent_id=str(payload.get("agent_id", payload.get("sub", ""))),
            proposed_tool=str(payload.get("tool", "")),
            tool_arguments={},
            verification_status="SUBJECT_MISMATCH",
            rejection_reason="Token subject does not match authenticated user.",
            correlation_id=correlation_id,
            jti=str(payload.get("jti", "")) or None,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token subject does not match authenticated user.",
        )

    token_tenant_id = payload.get("tenant_id")
    if (
        token_tenant_id
        and current_user.tenant_id
        and str(token_tenant_id) != str(current_user.tenant_id)
    ):
        log_verification(
            agent_id=str(payload.get("agent_id", payload.get("sub", ""))),
            proposed_tool=str(payload.get("tool", "")),
            tool_arguments={},
            verification_status="TENANT_MISMATCH",
            rejection_reason="Token tenant does not match authenticated user tenant.",
            correlation_id=correlation_id,
            jti=str(payload.get("jti", "")) or None,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token tenant does not match authenticated user tenant.",
        )

    # Emergency deny must stop execution authorisation itself: the token is
    # verified but no execution may proceed while the tenant is under deny
    # (PILLAR 6: emergency deny blocks ALL execution).
    await assert_execution_permitted(
        str(payload.get("tenant_id") or current_user.tenant_id or "")
    )

    token_agent_id = str(payload.get("agent_id", ""))
    if body.agent_id and token_agent_id and token_agent_id != body.agent_id:
        log_verification(
            agent_id=body.agent_id,
            proposed_tool=str(payload.get("tool", "")),
            tool_arguments={},
            verification_status="AGENT_MISMATCH",
            rejection_reason="Token agent_id does not match request agent_id.",
            correlation_id=correlation_id,
            jti=str(payload.get("jti", "")) or None,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token agent_id does not match request agent_id.",
        )

    agent_id_for_check = body.agent_id or token_agent_id
    if agent_id_for_check:
        db_session = SessionLocal()
        try:
            agent_repo = SQLAlchemyAgentRepository(db_session)
            agent = await agent_repo.get_by_agent_id(
                get_user_tenant_id(current_user), agent_id_for_check
            )
            if agent is not None and agent.status in (
                AgentStatus.REVOKED,
                AgentStatus.QUARANTINED,
                AgentStatus.SUSPENDED,
            ):
                log_verification(
                    agent_id=agent_id_for_check,
                    proposed_tool=str(payload.get("tool", "")),
                    tool_arguments={},
                    verification_status=f"AGENT_{agent.status.value.upper()}",
                    rejection_reason=f"Agent is {agent.status.value}.",
                    correlation_id=correlation_id,
                    jti=str(payload.get("jti", "")) or None,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Agent is {agent.status.value}.",
                )
        finally:
            db_session.close()

    log_verification(
        agent_id=str(payload.get("agent_id", payload.get("sub", ""))),
        proposed_tool=str(payload.get("tool", "")),
        tool_arguments={},
        verification_status="EXECUTED",
        rejection_reason="",
        correlation_id=correlation_id,
        jti=str(payload.get("jti", "")) or None,
    )
    metrics.increment_execution_tokens_consumed()

    db_session = SessionLocal()
    try:
        action_repo = SQLAlchemyProtectedActionRepository(db_session)
        execution_action = ProtectedAction(
            action_id=f"act-{__import__('secrets').token_hex(12)}",
            tenant_id=get_user_tenant_id(current_user),
            actor_user_id=current_user.id,
            agent_id=str(payload.get("agent_id", payload.get("sub", ""))),
            authority_grant_id=None,
            tool=str(payload.get("tool", "")),
            resource="",
            action_type="execution",
            correlation_id=correlation_id,
            status=ActionStatus.EXECUTED,
        )
        await action_repo.save(execution_action)
        db_session.commit()
    except Exception:
        db_session.rollback()
        raise
    finally:
        db_session.close()

    return {"status": "executed", "agent_id": str(payload.get("agent_id", payload.get("sub", "")))}


@router.post("/authorize-mutation")
async def authorize_mutation(
    request: Request,
    body: dict[str, Any],
    current_user: CurrentUser,
    execution_token_service: Annotated[ExecutionTokenService, Depends(get_execution_token_service)],
) -> dict[str, str]:
    """Authoritative pre-mutation gate.

    Performs a final containment check immediately before the local
    filesystem mutation.  If an ``execution_token`` is provided, it is
    verified and consumed; otherwise the gate relies on the caller's
    authenticated identity and the supplied ``agent_id``/``session_id``.

    Request body:
        execution_token: str | None
        agent_id: str | None
        session_id: str | None
    """
    correlation_id = getattr(request.state, "correlation_id", "")
    execution_token = body.get("execution_token")
    request_agent_id = body.get("agent_id")
    request_session_id = body.get("session_id")

    payload: dict[str, Any] = {}
    token_jti: str | None = None

    if execution_token:
        try:
            payload = execution_token_service.verify_execution_token(execution_token)
        except ExecutionTokenError as exc:
            metrics.increment_execution_tokens_replayed()
            token_jti = _extract_jti(execution_token)
            log_verification(
                agent_id="unknown",
                proposed_tool="unknown",
                tool_arguments={},
                verification_status="MUTATION_BLOCKED",
                rejection_reason=str(exc),
                correlation_id=correlation_id,
                jti=token_jti,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
            ) from exc

        token_subject = str(payload.get("sub", ""))
        if token_subject != str(current_user.id):
            log_verification(
                agent_id=str(payload.get("agent_id", payload.get("sub", ""))),
                proposed_tool=str(payload.get("tool", "")),
                tool_arguments={},
                verification_status="MUTATION_BLOCKED",
                rejection_reason="Token subject does not match authenticated user.",
                correlation_id=correlation_id,
                jti=str(payload.get("jti", "")) or None,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Token subject does not match authenticated user.",
            )

    token_agent_id = str(payload.get("agent_id", ""))
    agent_id_for_check = request_agent_id or token_agent_id
    if agent_id_for_check:
        db_session = SessionLocal()
        try:
            agent_repo = SQLAlchemyAgentRepository(db_session)
            agent = await agent_repo.get_by_agent_id(
                get_user_tenant_id(current_user), agent_id_for_check
            )
            if agent is not None and agent.status in (
                AgentStatus.REVOKED,
                AgentStatus.QUARANTINED,
                AgentStatus.SUSPENDED,
            ):
                log_verification(
                    agent_id=agent_id_for_check,
                    proposed_tool=str(payload.get("tool", "")),
                    tool_arguments={},
                    verification_status=f"MUTATION_BLOCKED_{agent.status.value.upper()}",
                    rejection_reason=f"Agent is {agent.status.value}.",
                    correlation_id=correlation_id,
                    jti=str(payload.get("jti", "")) or None,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Agent is {agent.status.value}.",
                )
        finally:
            db_session.close()

    if request_session_id:
        db_session = SessionLocal()
        try:
            session_repo = SQLAlchemyAgentSessionRepository(db_session)
            session = await session_repo.get_by_session_id(
                get_user_tenant_id(current_user), request_session_id
            )
            if session is not None:
                if session.tenant_id != get_user_tenant_id(current_user):
                    log_verification(
                        agent_id=agent_id_for_check or token_agent_id,
                        proposed_tool=str(payload.get("tool", "")),
                        tool_arguments={},
                        verification_status="MUTATION_BLOCKED_SESSION_TENANT_MISMATCH",
                        rejection_reason="Session tenant does not match authenticated user tenant.",
                        correlation_id=correlation_id,
                        jti=str(payload.get("jti", "")) or None,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Session tenant does not match authenticated user tenant.",
                    )
                if agent_id_for_check and session.agent_id != agent_id_for_check:
                    log_verification(
                        agent_id=agent_id_for_check or token_agent_id,
                        proposed_tool=str(payload.get("tool", "")),
                        tool_arguments={},
                        verification_status="MUTATION_BLOCKED_SESSION_AGENT_MISMATCH",
                        rejection_reason="Session agent does not match the requested agent.",
                        correlation_id=correlation_id,
                        jti=str(payload.get("jti", "")) or None,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Session agent does not match the requested agent.",
                    )
                if session.status == AgentSessionStatus.FROZEN:
                    log_verification(
                        agent_id=agent_id_for_check or token_agent_id,
                        proposed_tool=str(payload.get("tool", "")),
                        tool_arguments={},
                        verification_status="MUTATION_BLOCKED_SESSION_FROZEN",
                        rejection_reason="Session is frozen.",
                        correlation_id=correlation_id,
                        jti=str(payload.get("jti", "")) or None,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Session is frozen.",
                    )
        finally:
            db_session.close()

    log_verification(
        agent_id=agent_id_for_check or token_agent_id,
        proposed_tool=str(payload.get("tool", "")),
        tool_arguments={},
        verification_status="MUTATION_AUTHORIZED",
        rejection_reason="",
        correlation_id=correlation_id,
        jti=str(payload.get("jti", "")) or None,
    )

    return {"status": "mutation_authorized"}


class SimulateRequest(BaseModel):
    agent_id: str
    proposed_tool: str
    tenant_id: str | None = None
    action: str = "execute"
    resource: str = ""
    service_id: str | None = None
    confidence: float = 1.0
    risk_score: float = 0.0


@router.post("/simulate", response_model=dict[str, Any])
async def simulate_policy(
    request: Request,
    body: SimulateRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Simulate a policy decision without issuing an execution token.

    Returns the matched rules, winning rule, and final effect.
    """
    correlation_id = getattr(request.state, "correlation_id", "")

    if current_user.tenant_id and body.tenant_id and current_user.tenant_id != body.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant mismatch: request tenant does not match user tenant.",
        )

    context = AuthorizationContext(
        user_id=current_user.id,
        agent_id=body.agent_id,
        proposed_tool=body.proposed_tool,
        tenant_id=body.tenant_id,
        action=body.action,
        resource=body.resource,
        service_id=body.service_id,
        user_role=current_user.role,
    )

    auth_decision, auth_reason = _authz_service.authorize(context)
    if auth_decision == AuthorizationDecision.DENY:
        return {
            "effect": auth_decision.value,
            "reason": auth_reason,
            "authorization_decision": auth_decision.value,
        }

    simulation = _policy_engine.simulate(context, body.confidence, body.risk_score)
    simulation["authorization_decision"] = auth_decision.value
    simulation["authorization_reason"] = auth_reason

    log_verification(
        agent_id=body.agent_id,
        proposed_tool=body.proposed_tool,
        tool_arguments={},
        verification_status="POLICY_SIMULATED",
        rejection_reason="",
        correlation_id=correlation_id,
    )
    return simulation
