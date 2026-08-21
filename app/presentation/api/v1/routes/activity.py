import json
from collections.abc import Generator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.models.audit_event_model import AuditEventModel
from app.presentation.api.dependencies.auth import CurrentUser

router = APIRouter(prefix="/activity", tags=["Activity"])


class ActivityEventResponse(BaseModel):
    event_type: str
    timestamp: str
    details: dict[str, Any]


class AuditSearchResponse(BaseModel):
    total: int
    events: list[ActivityEventResponse]


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


@router.get("/me", response_model=list[ActivityEventResponse])
async def list_my_activity(
    current_user: CurrentUser,
    session: Annotated[Session, Depends(_get_session)],
) -> list[ActivityEventResponse]:
    stmt = (
        select(AuditEventModel)
        .where(AuditEventModel.user_id == current_user.id)
        .order_by(AuditEventModel.created_at.desc())
        .limit(20)
    )
    rows = session.execute(stmt).scalars().all()

    events: list[ActivityEventResponse] = []
    for row in rows:
        try:
            parsed: dict[str, Any] = json.loads(row.payload) if row.payload else {}
        except (ValueError, TypeError):
            parsed = {}
        events.append(
            ActivityEventResponse(
                event_type=row.event_type,
                timestamp=row.created_at.isoformat(),
                details=parsed,
            )
        )
    return events


@router.get("/search", response_model=AuditSearchResponse)
async def search_audit_events(
    current_user: CurrentUser,
    session: Annotated[Session, Depends(_get_session)],
    event_type: str | None = Query(default=None),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> AuditSearchResponse:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to search audit events.",
        )

    stmt = select(AuditEventModel)

    if event_type:
        stmt = stmt.where(AuditEventModel.event_type == event_type)

    if since:
        stmt = stmt.where(AuditEventModel.created_at >= since)

    if until:
        stmt = stmt.where(AuditEventModel.created_at <= until)

    stmt = stmt.order_by(AuditEventModel.created_at.desc()).limit(limit)
    rows = session.execute(stmt).scalars().all()

    events: list[ActivityEventResponse] = []
    for row in rows:
        try:
            parsed: dict[str, Any] = json.loads(row.payload) if row.payload else {}
        except (ValueError, TypeError):
            parsed = {}
        events.append(
            ActivityEventResponse(
                event_type=row.event_type,
                timestamp=row.created_at.isoformat(),
                details=parsed,
            )
        )

    return AuditSearchResponse(total=len(events), events=events)
