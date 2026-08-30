from collections.abc import Generator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.domain.services.incident_timeline_service import (
    IncidentTimelineService,
    _format_event,
)
from app.infrastructure.logging.audit_logger import log_security_event
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_containment_repository import (
    SQLAlchemyContainmentRepository,
    SQLAlchemyRecoveryPlanRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_discovery_event_repository import (
    SQLAlchemyDiscoveryEventRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_protected_action_repository import (
    SQLAlchemyProtectedActionRepository,
)
from app.presentation.api.dependencies.auth import CurrentUser, get_user_tenant_id

router = APIRouter(tags=["Incident"])
DEFAULT_LIMIT = 100
MAX_LIMIT = 500


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


def _get_timeline_service(
    session: Annotated[Session, Depends(_get_session)],
) -> IncidentTimelineService:
    return IncidentTimelineService(
        discovery_repo=SQLAlchemyDiscoveryEventRepository(session),
        action_repo=SQLAlchemyProtectedActionRepository(session),
        containment_repo=SQLAlchemyContainmentRepository(session),
        recovery_repo=SQLAlchemyRecoveryPlanRepository(session),
    )


@router.get(
    "/incident/{incident_id}/timeline",
    response_model=dict[str, Any],
)
async def get_incident_timeline(
    incident_id: str,
    current_user: CurrentUser,
    service: Annotated[IncidentTimelineService, Depends(_get_timeline_service)],
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    events = await service.get_timeline(
        tenant_id=get_user_tenant_id(current_user),
        incident_id=incident_id,
        limit=limit,
        offset=offset,
    )
    log_security_event(
        "incident_timeline_viewed",
        tenant_id=get_user_tenant_id(current_user),
        incident_id=incident_id,
        event_count=len(events),
    )
    return {
        "incident_id": incident_id,
        "tenant_id": get_user_tenant_id(current_user),
        "total_events": len(events),
        "events": [_format_event(e) for e in events],
    }


@router.get(
    "/incident/{incident_id}/timeline/summary",
    response_model=dict[str, Any],
)
async def get_incident_timeline_summary(
    incident_id: str,
    current_user: CurrentUser,
    service: Annotated[IncidentTimelineService, Depends(_get_timeline_service)],
) -> dict[str, Any]:
    events = await service.get_timeline(
        tenant_id=get_user_tenant_id(current_user),
        incident_id=incident_id,
    )
    summary: dict[str, int] = {}
    for event in events:
        summary[event.event_type.value] = summary.get(event.event_type.value, 0) + 1
    statuses: list[str] = []
    severities: list[str] = []
    for event in events:
        if event.event_type.value not in statuses:
            statuses.append(event.event_type.value)
        sev = event.severity
        if sev not in severities:
            severities.append(sev)
    if not events:
        return {
            "incident_id": incident_id,
            "has_events": False,
            "total_events": 0,
            "event_types": [],
            "severities": [],
        }
    earliest = min(e.timestamp for e in events)
    latest = max(e.timestamp for e in events)
    return {
        "incident_id": incident_id,
        "has_events": True,
        "total_events": len(events),
        "event_types": statuses,
        "severities": severities,
        "earliest_event": earliest.isoformat(),
        "latest_event": latest.isoformat(),
    }
