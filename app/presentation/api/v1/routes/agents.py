from collections.abc import Generator
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.application.dto.agent import (
    AgentCreateRequest,
    AgentListResponse,
    AgentResponse,
    AgentUpdateRequest,
)
from app.domain.entities.agent import (
    Agent,
    AgentEnvironment,
    AgentStatus,
    AgentType,
    RegistrationMethod,
    RiskClassification,
    TrustLevel,
)
from app.domain.repositories.agent_repository import AgentRepository
from app.infrastructure.logging.audit_logger import log_security_event
from app.infrastructure.observability.metrics import metrics
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_agent_repository import (
    SQLAlchemyAgentRepository,
)
from app.presentation.api.dependencies.auth import CurrentUser, get_user_tenant_id

router = APIRouter(tags=["Agents"])


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


def _get_agent_repository(
    session: Annotated[Session, Depends(_get_session)],
) -> AgentRepository:
    return SQLAlchemyAgentRepository(session)


@router.post("/", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: AgentCreateRequest,
    current_user: CurrentUser,
    repo: Annotated[AgentRepository, Depends(_get_agent_repository)],
) -> AgentResponse:
    if await repo.exists(get_user_tenant_id(current_user), body.agent_id):
        raise HTTPException(status_code=409, detail="Agent already exists")
    agent = Agent(
        agent_id=body.agent_id,
        tenant_id=get_user_tenant_id(current_user),
        name=body.name,
        description=body.description,
        agent_type=AgentType(body.agent_type),
        parent_agent_id=body.parent_agent_id,
        model_provider=body.model_provider,
        model_name=body.model_name,
        environment=AgentEnvironment(body.environment),
        version=body.version or "1.0",
        creator=body.creator,
        registration_method=RegistrationMethod(body.registration_method),
        root_human_sponsor=body.root_human_sponsor,
        connected_tools=body.connected_tools,
        metadata=body.metadata,
        expires_at=body.expires_at,
    )
    agent = await repo.save(agent)
    log_security_event(
        "agent_registered",
        tenant_id=agent.tenant_id,
        agent_id=agent.agent_id,
        agent_type=agent.agent_type.value,
    )
    metrics.increment_security_exception("agent_registered")
    return AgentResponse(
        agent_id=agent.agent_id,
        tenant_id=agent.tenant_id,
        name=agent.name,
        description=agent.description,
        agent_type=agent.agent_type.value,
        status=agent.status.value,
        trust_level=agent.trust_level.value,
        risk_classification=agent.risk_classification.value,
        parent_agent_id=agent.parent_agent_id,
        model_provider=agent.model_provider,
        model_name=agent.model_name,
        environment=agent.environment.value,
        version=agent.version,
        creator=agent.creator,
        registration_method=agent.registration_method.value,
        root_human_sponsor=agent.root_human_sponsor,
        owner_user_id=str(agent.owner_user_id) if agent.owner_user_id else None,
        connected_tools=agent.connected_tools,
        expires_at=agent.expires_at,
        last_activity_at=agent.last_activity_at,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


@router.get("/", response_model=AgentListResponse)
async def list_agents(
    current_user: CurrentUser,
    repo: Annotated[AgentRepository, Depends(_get_agent_repository)],
    status: str | None = Query(default=None),
    agent_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> AgentListResponse:
    st = AgentStatus(status) if status else None
    at = AgentType(agent_type) if agent_type else None
    items, total = await repo.list_by_tenant(
        get_user_tenant_id(current_user), status=st, agent_type=at, limit=limit, offset=offset
    )
    return AgentListResponse(
        items=[
            AgentResponse(
                agent_id=a.agent_id,
                tenant_id=a.tenant_id,
                name=a.name,
                description=a.description,
                agent_type=a.agent_type.value,
                status=a.status.value,
                trust_level=a.trust_level.value,
                risk_classification=a.risk_classification.value,
                parent_agent_id=a.parent_agent_id,
                model_provider=a.model_provider,
                model_name=a.model_name,
                environment=a.environment.value,
                version=a.version,
                creator=a.creator,
                registration_method=a.registration_method.value,
                root_human_sponsor=a.root_human_sponsor,
                owner_user_id=str(a.owner_user_id) if a.owner_user_id else None,
                connected_tools=a.connected_tools,
                expires_at=a.expires_at,
                last_activity_at=a.last_activity_at,
                created_at=a.created_at,
                updated_at=a.updated_at,
            )
            for a in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    current_user: CurrentUser,
    repo: Annotated[AgentRepository, Depends(_get_agent_repository)],
) -> AgentResponse:
    agent = await repo.get_by_agent_id(get_user_tenant_id(current_user), agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentResponse(
        agent_id=agent.agent_id,
        tenant_id=agent.tenant_id,
        name=agent.name,
        description=agent.description,
        agent_type=agent.agent_type.value,
        status=agent.status.value,
        trust_level=agent.trust_level.value,
        risk_classification=agent.risk_classification.value,
        parent_agent_id=agent.parent_agent_id,
        model_provider=agent.model_provider,
        model_name=agent.model_name,
        environment=agent.environment.value,
        version=agent.version,
        creator=agent.creator,
        registration_method=agent.registration_method.value,
        root_human_sponsor=agent.root_human_sponsor,
        owner_user_id=str(agent.owner_user_id) if agent.owner_user_id else None,
        connected_tools=agent.connected_tools,
        expires_at=agent.expires_at,
        last_activity_at=agent.last_activity_at,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    body: AgentUpdateRequest,
    current_user: CurrentUser,
    repo: Annotated[AgentRepository, Depends(_get_agent_repository)],
) -> AgentResponse:
    agent = await repo.get_by_agent_id(get_user_tenant_id(current_user), agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    update_data = body.model_dump(exclude_unset=True)
    if "status" in update_data:
        agent = await repo.update_status(
            get_user_tenant_id(current_user), agent_id, AgentStatus(update_data["status"])
        )
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        return _agent_response(agent)

    updatable_fields = {
        "name", "description", "trust_level", "risk_classification",
        "environment", "version", "connected_tools", "metadata",
        "model_provider", "model_name", "expires_at",
    }
    filtered = {k: v for k, v in update_data.items() if k in updatable_fields and v is not None}
    if not filtered:
        raise HTTPException(status_code=400, detail="No updatable fields provided")

    updated = Agent(
        agent_id=agent.agent_id,
        tenant_id=agent.tenant_id,
        name=filtered.get("name", agent.name),
        description=filtered.get("description", agent.description),
        owner_user_id=agent.owner_user_id,
        parent_agent_id=agent.parent_agent_id,
        agent_type=agent.agent_type,
        status=agent.status,
        trust_level=(
            TrustLevel(filtered["trust_level"]) if "trust_level" in filtered else agent.trust_level
        ),
        risk_classification=RiskClassification(
            filtered["risk_classification"]
        ) if "risk_classification" in filtered else agent.risk_classification,
        environment=AgentEnvironment(
            filtered["environment"]
        ) if "environment" in filtered else agent.environment,
        version=filtered.get("version", agent.version),
        creator=agent.creator,
        registration_method=agent.registration_method,
        root_human_sponsor=agent.root_human_sponsor,
        model_provider=filtered.get("model_provider", agent.model_provider),
        model_name=filtered.get("model_name", agent.model_name),
        connected_tools=filtered.get("connected_tools", agent.connected_tools),
        metadata=filtered.get("metadata", agent.metadata),
        expires_at=filtered.get("expires_at", agent.expires_at),
        last_activity_at=agent.last_activity_at,
        created_at=agent.created_at,
    )
    updated = await repo.save(updated)
    return _agent_response(updated)


def _agent_response(agent: Agent) -> AgentResponse:
    return AgentResponse(
        agent_id=agent.agent_id,
        tenant_id=agent.tenant_id,
        name=agent.name,
        description=agent.description,
        agent_type=agent.agent_type.value,
        status=agent.status.value,
        trust_level=agent.trust_level.value,
        risk_classification=agent.risk_classification.value,
        parent_agent_id=agent.parent_agent_id,
        model_provider=agent.model_provider,
        model_name=agent.model_name,
        environment=agent.environment.value,
        version=agent.version,
        creator=agent.creator,
        registration_method=agent.registration_method.value,
        root_human_sponsor=agent.root_human_sponsor,
        owner_user_id=str(agent.owner_user_id) if agent.owner_user_id else None,
        connected_tools=agent.connected_tools,
        expires_at=agent.expires_at,
        last_activity_at=agent.last_activity_at,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


@router.post(
    "/{agent_id}/kill",
    response_model=dict[str, Any],
)
async def kill_agent(
    agent_id: str,
    body: dict[str, Any],
    current_user: CurrentUser,
    repo: Annotated[AgentRepository, Depends(_get_agent_repository)],
) -> dict[str, Any]:
    from app.domain.entities.agent import AgentStatus

    agent = await repo.get_by_agent_id(get_user_tenant_id(current_user), agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    reason = body.get("reason", "")
    await repo.update_status(
        get_user_tenant_id(current_user), agent_id, AgentStatus.REVOKED
    )
    log_security_event(
        "agent_killed",
        tenant_id=get_user_tenant_id(current_user),
        agent_id=agent_id,
        reason=reason,
    )
    metrics.increment_security_exception("agent_killed")
    return {
        "agent_id": agent_id,
        "status": AgentStatus.REVOKED.value,
        "message": "Agent killed. All authority and tokens should be revoked.",
        "reason": reason,
    }


@router.post(
    "/{agent_id}/revoke",
    response_model=dict[str, Any],
)
async def revoke_agent_tokens(
    agent_id: str,
    current_user: CurrentUser,
    repo: Annotated[AgentRepository, Depends(_get_agent_repository)],
) -> dict[str, Any]:
    agent = await repo.get_by_agent_id(get_user_tenant_id(current_user), agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    log_security_event(
        "agent_tokens_revoked",
        tenant_id=get_user_tenant_id(current_user),
        agent_id=agent_id,
    )
    metrics.increment_security_exception("agent_tokens_revoked")
    return {
        "agent_id": agent_id,
        "message": "Agent tokens revoked.",
        "revoked_at": datetime.now(UTC).isoformat(),
    }
