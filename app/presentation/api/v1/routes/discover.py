from collections.abc import Generator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.application.dto.control import (
    DiscoveryEventResponse,
    DiscoveryRegisterRequest,
)
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.discovery_event_repository import DiscoveryEventRepository
from app.domain.services.discovery_service import DiscoveryService
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_agent_repository import (
    SQLAlchemyAgentRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_discovery_event_repository import (
    SQLAlchemyDiscoveryEventRepository,
)
from app.presentation.api.dependencies.auth import CurrentUser, get_user_tenant_id

router = APIRouter(tags=["Discovery"])


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


def _get_discovery_repo(
    session: Annotated[Session, Depends(_get_session)],
) -> DiscoveryEventRepository:
    return SQLAlchemyDiscoveryEventRepository(session)


def _get_agent_repo(
    session: Annotated[Session, Depends(_get_session)],
) -> AgentRepository:
    return SQLAlchemyAgentRepository(session)


@router.post(
    "/register",
    response_model=DiscoveryEventResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_discovery(
    body: DiscoveryRegisterRequest,
    current_user: CurrentUser,
    discovery_repo: Annotated[DiscoveryEventRepository, Depends(_get_discovery_repo)],
    agent_repo: Annotated[AgentRepository, Depends(_get_agent_repo)],
) -> DiscoveryEventResponse:
    from app.domain.entities.discovery_event import DiscoverySource
    service = DiscoveryService(agent_repo, discovery_repo)
    source = DiscoverySource(body.source)
    agent, event = await service.register_agent(
        tenant_id=get_user_tenant_id(current_user),
        agent_id=body.agent_id or f"disc-agent-{source.value}-{__import__('secrets').token_hex(4)}",
        name=body.resource_id or body.agent_id or "Discovered Agent",
        source=source,
        resource_metadata=body.resource_metadata,
        finding_severity=body.finding_severity,
        finding_message=body.finding_message,
    )
    return DiscoveryEventResponse(
        discovery_id=event.discovery_id,
        tenant_id=event.tenant_id,
        source=event.source.value,
        discovery_status=event.discovery_status.value,
        agent_id=event.agent_id,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        finding_severity=event.finding_severity,
        finding_message=event.finding_message,
        created_at=event.created_at,
    )


@router.post(
    "/ingest",
    response_model=DiscoveryEventResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_discovery_event(
    body: DiscoveryRegisterRequest,
    current_user: CurrentUser,
    discovery_repo: Annotated[DiscoveryEventRepository, Depends(_get_discovery_repo)],
    agent_repo: Annotated[AgentRepository, Depends(_get_agent_repo)],
) -> DiscoveryEventResponse:
    from app.domain.entities.discovery_event import DiscoverySource
    service = DiscoveryService(agent_repo, discovery_repo)
    source = DiscoverySource(body.source)
    event = await service.ingest_discovery_event(
        tenant_id=get_user_tenant_id(current_user),
        source=source,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        agent_id=body.agent_id,
        resource_metadata=body.resource_metadata,
        finding_severity=body.finding_severity,
        finding_message=body.finding_message,
    )
    return DiscoveryEventResponse(
        discovery_id=event.discovery_id,
        tenant_id=event.tenant_id,
        source=event.source.value,
        discovery_status=event.discovery_status.value,
        agent_id=event.agent_id,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        finding_severity=event.finding_severity,
        finding_message=event.finding_message,
        created_at=event.created_at,
    )


@router.get("/events", response_model=dict)
async def list_discovery_events(
    current_user: CurrentUser,
    discovery_repo: Annotated[DiscoveryEventRepository, Depends(_get_discovery_repo)],
    source: str | None = Query(default=None),
    discovery_status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    from app.domain.entities.discovery_event import DiscoverySource, DiscoveryStatus
    src = DiscoverySource(source) if source else None
    dst = DiscoveryStatus(discovery_status) if discovery_status else None
    items, total = await discovery_repo.list_by_tenant(
        get_user_tenant_id(current_user),
        source=src,
        discovery_status=dst,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [
            DiscoveryEventResponse(
                discovery_id=e.discovery_id,
                tenant_id=e.tenant_id,
                source=e.source.value,
                discovery_status=e.discovery_status.value,
                agent_id=e.agent_id,
                resource_type=e.resource_type,
                resource_id=e.resource_id,
                finding_severity=e.finding_severity,
                finding_message=e.finding_message,
                created_at=e.created_at,
            )
            for e in items
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
