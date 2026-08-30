from collections.abc import Generator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.application.dto.action_graph import (
    DownstreamResponse,
    GraphEdge,
    GraphNode,
    IncidentGraphResponse,
    UpstreamResponse,
)
from app.application.dto.agent import (
    ProtectedActionCreateRequest,
    ProtectedActionListResponse,
    ProtectedActionResponse,
)
from app.domain.repositories.protected_action_repository import ProtectedActionRepository
from app.domain.services.causal_graph_service import CausalGraphService
from app.infrastructure.logging.audit_logger import log_security_event
from app.infrastructure.observability.metrics import metrics
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_protected_action_repository import (
    SQLAlchemyProtectedActionRepository,
)
from app.presentation.api.dependencies.auth import CurrentUser, get_user_tenant_id

router = APIRouter(tags=["Actions"])


def _get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _get_action_repository(
    session: Annotated[Session, Depends(_get_session)],
) -> ProtectedActionRepository:
    return SQLAlchemyProtectedActionRepository(session)


@router.post("/", response_model=ProtectedActionResponse, status_code=status.HTTP_201_CREATED)
async def create_action(
    body: ProtectedActionCreateRequest,
    current_user: CurrentUser,
    repo: Annotated[ProtectedActionRepository, Depends(_get_action_repository)],
) -> ProtectedActionResponse:
    import secrets
    from datetime import UTC, datetime

    from app.domain.entities.protected_action import (
        ActionStatus,
        ProtectedAction,
    )
    action_id = f"act-{secrets.token_hex(12)}"
    action = ProtectedAction(
        action_id=action_id,
        tenant_id=get_user_tenant_id(current_user),
        actor_user_id=current_user.id,
        agent_id=body.agent_id,
        authority_grant_id=body.authority_grant_id,
        tool=body.tool,
        resource=body.resource,
        action_type=body.action_type,
        correlation_id=body.correlation_id,
        parent_action_id=body.parent_action_id,
        workflow_id=body.workflow_id,
        tool_arguments=body.tool_arguments,
        before_state_ref=body.before_state_ref,
        status=ActionStatus.PENDING,
        created_at=datetime.now(UTC),
    )
    action = await repo.save(action)
    log_security_event(
        "protected_action_created",
        tenant_id=action.tenant_id,
        action_id=action.action_id,
        agent_id=action.agent_id,
        action_type=action.action_type,
    )
    metrics.increment_security_exception("protected_action_created")
    return ProtectedActionResponse(
        action_id=action.action_id,
        tenant_id=action.tenant_id,
        agent_id=action.agent_id,
        tool=action.tool,
        resource=action.resource,
        action_type=action.action_type,
        status=action.status.value,
        risk_score=action.risk_score,
        reversibility=action.reversibility.value,
        authority_grant_id=action.authority_grant_id,
        correlation_id=action.correlation_id,
        parent_action_id=action.parent_action_id,
        workflow_id=action.workflow_id,
        decision_reason=action.decision_reason,
        created_at=action.created_at,
        evaluated_at=action.evaluated_at,
        executed_at=action.executed_at,
    )


@router.get("/", response_model=ProtectedActionListResponse)
async def list_actions(
    current_user: CurrentUser,
    repo: Annotated[ProtectedActionRepository, Depends(_get_action_repository)],
    agent_id: str | None = Query(default=None),
    correlation_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> ProtectedActionListResponse:
    if agent_id:
        items, total = await repo.list_by_agent(
            get_user_tenant_id(current_user), agent_id, limit=limit, offset=offset
        )
    elif correlation_id:
        items, total = await repo.list_by_correlation(
            get_user_tenant_id(current_user), correlation_id, limit=limit, offset=offset
        )
    else:
        raise HTTPException(status_code=400, detail="agent_id or correlation_id required")
    return ProtectedActionListResponse(
        items=[
            ProtectedActionResponse(
                action_id=a.action_id,
                tenant_id=a.tenant_id,
                agent_id=a.agent_id,
                tool=a.tool,
                resource=a.resource,
                action_type=a.action_type,
                status=a.status.value,
                risk_score=a.risk_score,
                reversibility=a.reversibility.value,
                authority_grant_id=a.authority_grant_id,
                correlation_id=a.correlation_id,
                parent_action_id=a.parent_action_id,
                workflow_id=a.workflow_id,
                decision_reason=a.decision_reason,
                created_at=a.created_at,
                evaluated_at=a.evaluated_at,
                executed_at=a.executed_at,
            )
            for a in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{action_id}/evaluate", response_model=ProtectedActionResponse)
async def evaluate_action(
    action_id: str,
    current_user: CurrentUser,
    repo: Annotated[ProtectedActionRepository, Depends(_get_action_repository)],
) -> ProtectedActionResponse:
    from app.domain.entities.protected_action import ActionStatus
    action = await repo.get_by_action_id(get_user_tenant_id(current_user), action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    if action.status != ActionStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Action already {action.status.value}")
    action = await repo.update_status(
        get_user_tenant_id(current_user), action_id, ActionStatus.EVALUATING
    )
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    from app.domain.services.action_control_service import ActionControlService
    from app.domain.services.authorization_service import AuthorizationService
    from app.domain.services.central_policy_engine import CentralPolicyEngine
    from app.domain.services.risk_engine import RiskEngine
    from app.domain.value_objects.authorization_context import AuthorizationContext
    authz = AuthorizationService()
    policy = CentralPolicyEngine.from_file()
    risk = RiskEngine()
    control = ActionControlService(authz, policy, risk)
    ctx = AuthorizationContext(
        user_id=current_user.id,
        agent_id=action.agent_id,
        proposed_tool=action.tool,
        tenant_id=action.tenant_id,
        action=action.action_type,
        resource=action.resource,
    )
    from app.domain.models.intent import AgentActionDAG

    dag = AgentActionDAG(
        user_prompt="",
        agent_id=action.agent_id,
        reasoning_step="",
        proposed_tool=action.tool,
        tool_arguments=action.tool_arguments,
        tenant_id=action.tenant_id,
        action=action.action_type,
        resource=action.resource,
    )
    result = control.evaluate_protected_action(ctx, dag)
    final_status = ActionStatus.PERMITTED if result["decision"] == "allow" else ActionStatus.DENIED
    if result["decision"] == "require_hitl":
        final_status = ActionStatus.REQUIRES_APPROVAL
    action = await repo.update_status(
        get_user_tenant_id(current_user), action_id, final_status, reason=result.get("reason", "")
    )
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    return ProtectedActionResponse(
        action_id=action.action_id,
        tenant_id=action.tenant_id,
        agent_id=action.agent_id,
        tool=action.tool,
        resource=action.resource,
        action_type=action.action_type,
        status=action.status.value,
        risk_score=result.get("risk_score", action.risk_score),
        reversibility=action.reversibility.value,
        authority_grant_id=action.authority_grant_id,
        correlation_id=action.correlation_id,
        parent_action_id=action.parent_action_id,
        workflow_id=action.workflow_id,
        decision_reason=action.decision_reason,
        created_at=action.created_at,
        evaluated_at=action.evaluated_at,
        executed_at=action.executed_at,
    )


@router.get("/{action_id}/upstream", response_model=UpstreamResponse)
async def get_upstream_actions(
    action_id: str,
    current_user: CurrentUser,
    repo: Annotated[ProtectedActionRepository, Depends(_get_action_repository)],
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> UpstreamResponse:
    service = CausalGraphService(repo)
    upstream, total = await service.get_upstream_actions(
        get_user_tenant_id(current_user), action_id, limit=limit, offset=offset
    )
    metrics.increment_causal_graph_query("upstream")
    return UpstreamResponse(
        action_id=action_id,
        upstream=[
            {
                "action_id": a.action_id,
                "agent_id": a.agent_id,
                "tool": a.tool,
                "resource": a.resource,
                "action_type": a.action_type,
                "status": a.status.value,
                "parent_action_id": a.parent_action_id,
                "created_at": a.created_at,
            }
            for a in upstream
        ],
        total=total,
    )


@router.get("/{action_id}/downstream", response_model=DownstreamResponse)
async def get_downstream_actions(
    action_id: str,
    current_user: CurrentUser,
    repo: Annotated[ProtectedActionRepository, Depends(_get_action_repository)],
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> DownstreamResponse:
    service = CausalGraphService(repo)
    downstream, total = await service.get_downstream_actions(
        get_user_tenant_id(current_user), action_id, limit=limit, offset=offset
    )
    metrics.increment_causal_graph_query("downstream")
    return DownstreamResponse(
        action_id=action_id,
        downstream=[
            {
                "action_id": a.action_id,
                "agent_id": a.agent_id,
                "tool": a.tool,
                "resource": a.resource,
                "action_type": a.action_type,
                "status": a.status.value,
                "parent_action_id": a.parent_action_id,
                "created_at": a.created_at,
            }
            for a in downstream
        ],
        total=total,
    )


@router.get("/{action_id}/graph", response_model=IncidentGraphResponse)
async def get_incident_graph(
    action_id: str,
    current_user: CurrentUser,
    repo: Annotated[ProtectedActionRepository, Depends(_get_action_repository)],
) -> IncidentGraphResponse:
    service = CausalGraphService(repo)
    graph = await service.get_incident_graph(get_user_tenant_id(current_user), action_id)
    metrics.increment_causal_graph_query("graph")
    return IncidentGraphResponse(
        root_action_id=graph["root_action_id"],
        nodes=[GraphNode(**n) for n in graph["nodes"]],
        edges=[GraphEdge(**e) for e in graph["edges"]],
    )


@router.post(
    "/{action_id}/rollback",
    response_model=dict[str, Any],
)
async def rollback_action(
    action_id: str,
    current_user: CurrentUser,
    repo: Annotated[ProtectedActionRepository, Depends(_get_action_repository)],
) -> dict[str, Any]:
    from app.domain.entities.protected_action import ActionStatus

    action = await repo.get_by_action_id(get_user_tenant_id(current_user), action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    action = await repo.update_status(
        get_user_tenant_id(current_user),
        action_id,
        ActionStatus.CONTAINED,
        reason="rollback_requested",
    )
    log_security_event(
        "action_rollback_requested",
        tenant_id=get_user_tenant_id(current_user),
        action_id=action_id,
        agent_id=action.agent_id if action else "",
    )
    return {
        "action_id": action_id,
        "status": "rollback_requested",
        "message": "Action rollback requested. Recovery plan will be generated.",
    }
