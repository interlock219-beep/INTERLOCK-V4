from __future__ import annotations

import contextlib
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.models.audit_event_model import AuditEventModel
from app.presentation.api.dependencies.auth import CurrentUser

router = APIRouter(prefix="/authorization", tags=["Authorization"])


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


def _get_session_dep() -> Session:
    """Module-level singleton default to satisfy B008 (no Depends in defaults)."""
    return cast(Session, Depends(_get_session))


@router.get("/decisions")
async def get_authorization_decisions(
    current_user: CurrentUser,
    session: Annotated[Session, _get_session_dep()],
    tenant_id: str | None = None,
    agent_id: str | None = None,
    limit: int = 100,
) -> dict[str, object]:
    """Get authorization decision audit log. AUTH-049."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to view authorization decisions.",
        )

    stmt = select(AuditEventModel).where(
        AuditEventModel.event_type == "authorization_decision",
    )
    stmt = stmt.order_by(AuditEventModel.created_at.desc()).limit(limit)
    rows = session.execute(stmt).scalars().all()

    events = []
    for row in rows:
        payload: dict[str, Any] = {}
        if row.payload:
            import json

            with contextlib.suppress(ValueError, TypeError):
                payload = json.loads(row.payload)

        row_tenant = payload.get("tenant_id") if isinstance(payload, dict) else None
        row_agent = payload.get("agent_id") if isinstance(payload, dict) else None

        if tenant_id and row_tenant != tenant_id:
            continue
        if agent_id and row_agent != agent_id:
            continue

        events.append(
            {
                "event_id": str(row.id),
                "tenant_id": row_tenant,
                "agent_id": row_agent,
                "event_type": row.event_type,
                "timestamp": row.created_at.isoformat() if row.created_at else None,
                "payload": payload,
            }
        )

    return {
        "decisions": events,
        "count": len(events),
        "tenant_id": tenant_id,
        "agent_id": agent_id,
    }


@router.get("/replay/{event_id}")
async def replay_authorization_decision(
    event_id: str,
    current_user: CurrentUser,
    session: Annotated[Session, _get_session_dep()],
) -> dict[str, object]:
    """Replay an authorization decision for forensics. AUTH-050."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to replay authorization decisions.",
        )

    from uuid import UUID

    stmt = select(AuditEventModel).where(AuditEventModel.id == UUID(event_id))
    row = session.execute(stmt).scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authorization event not found",
        )

    payload: dict[str, Any] = {}
    if row.payload:
        import json

        with contextlib.suppress(ValueError, TypeError):
            payload = json.loads(row.payload)

    return {
        "event_id": str(row.id),
        "tenant_id": payload.get("tenant_id"),
        "agent_id": payload.get("agent_id"),
        "event_type": row.event_type,
        "timestamp": row.created_at.isoformat() if row.created_at else None,
        "payload": payload,
        "replayed_at": datetime.now(UTC).isoformat(),
    }
