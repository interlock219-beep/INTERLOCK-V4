from collections.abc import Generator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.domain.entities.incident import Incident, IncidentSeverity, IncidentStatus
from app.domain.repositories.incident_repository import IncidentRepository
from app.infrastructure.logging.audit_logger import log_security_event
from app.infrastructure.observability.metrics import metrics
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_incident_repository import (
    SQLAlchemyIncidentRepository,
)
from app.presentation.api.dependencies.auth import CurrentUser, get_user_tenant_id

router = APIRouter(tags=["Incidents"])
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


def _get_incident_repo(
    session: Annotated[Session, Depends(_get_session)],
) -> IncidentRepository:
    return SQLAlchemyIncidentRepository(session)


@router.post(
    "/incidents",
    response_model=dict[str, Any],
    status_code=status.HTTP_201_CREATED,
)
async def create_incident(
    body: dict[str, Any],
    current_user: CurrentUser,
    repo: Annotated[IncidentRepository, Depends(_get_incident_repo)],
) -> dict[str, Any]:
    import secrets

    incident_id = body.get("incident_id") or f"inc-{secrets.token_hex(12)}"
    existing = await repo.get_by_incident_id(get_user_tenant_id(current_user), incident_id)
    if existing:
        raise HTTPException(status_code=409, detail="Incident already exists")

    severity = IncidentSeverity(body.get("severity", "medium"))
    incident = Incident(
        incident_id=incident_id,
        tenant_id=get_user_tenant_id(current_user),
        agent_id=body.get("agent_id", ""),
        severity=severity,
        trigger=body.get("trigger", ""),
        session_ids=body.get("session_ids", []),
        affected_action_ids=body.get("affected_action_ids", []),
        affected_resources=body.get("affected_resources", []),
        blast_radius=body.get("blast_radius", {}),
        status=IncidentStatus.DETECTED,
    )
    saved = await repo.save(incident)
    log_security_event(
        "incident_created",
        tenant_id=saved.tenant_id,
        incident_id=saved.incident_id,
        agent_id=saved.agent_id,
        severity=saved.severity.value,
    )
    metrics.increment_security_exception("incident_created")
    return {
        "incident_id": saved.incident_id,
        "tenant_id": saved.tenant_id,
        "agent_id": saved.agent_id,
        "severity": saved.severity.value,
        "status": saved.status.value,
        "created_at": saved.created_at.isoformat(),
    }


@router.get(
    "/incidents/{incident_id}",
    response_model=dict[str, Any],
)
async def get_incident(
    incident_id: str,
    current_user: CurrentUser,
    repo: Annotated[IncidentRepository, Depends(_get_incident_repo)],
) -> dict[str, Any]:
    incident = await repo.get_by_incident_id(get_user_tenant_id(current_user), incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {
        "incident_id": incident.incident_id,
        "tenant_id": incident.tenant_id,
        "agent_id": incident.agent_id,
        "severity": incident.severity.value,
        "status": incident.status.value,
        "trigger": incident.trigger,
        "session_ids": incident.session_ids,
        "affected_action_ids": incident.affected_action_ids,
        "affected_resources": incident.affected_resources,
        "blast_radius": incident.blast_radius,
        "containment_state": incident.containment_state,
        "rollback_state": incident.rollback_state,
        "verification_state": incident.verification_state,
        "created_at": incident.created_at.isoformat(),
        "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
    }


@router.get(
    "/incidents",
    response_model=dict[str, Any],
)
async def list_incidents(
    current_user: CurrentUser,
    repo: Annotated[IncidentRepository, Depends(_get_incident_repo)],
    agent_id: str = Query(default=""),
    status: str = Query(default=""),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    st = IncidentStatus(status) if status else None
    if agent_id:
        items, total = await repo.list_by_agent(
            get_user_tenant_id(current_user), agent_id, limit=limit, offset=offset
        )
    else:
        items, total = await repo.list_by_tenant(
            get_user_tenant_id(current_user), status=st, limit=limit, offset=offset
        )
    return {
        "items": [
            {
                "incident_id": i.incident_id,
                "tenant_id": i.tenant_id,
                "agent_id": i.agent_id,
                "severity": i.severity.value,
                "status": i.status.value,
                "trigger": i.trigger,
                "created_at": i.created_at.isoformat(),
            }
            for i in items
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.patch(
    "/incidents/{incident_id}/status",
    response_model=dict[str, Any],
)
async def update_incident_status(
    incident_id: str,
    body: dict[str, Any],
    current_user: CurrentUser,
    repo: Annotated[IncidentRepository, Depends(_get_incident_repo)],
) -> dict[str, Any]:
    from datetime import UTC, datetime

    incident = await repo.get_by_incident_id(get_user_tenant_id(current_user), incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    new_status = IncidentStatus(body.get("status", incident.status.value))
    await repo.update_status(
        get_user_tenant_id(current_user), incident_id, new_status
    )
    log_security_event(
        "incident_status_updated",
        tenant_id=get_user_tenant_id(current_user),
        incident_id=incident_id,
        new_status=new_status.value,
    )
    return {
        "incident_id": incident_id,
        "status": new_status.value,
        "updated_at": datetime.now(UTC).isoformat(),
    }
