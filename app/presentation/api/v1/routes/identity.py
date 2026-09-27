from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.domain.services.identity_anomaly_detection import IdentityAnomalyDetectionService
from app.infrastructure.persistence.repositories.sqlalchemy_agent_repository import (
    SQLAlchemyAgentRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_agent_session_repository import (
    SQLAlchemyAgentSessionRepository,
)
from app.presentation.api.dependencies.auth import CurrentUser, _get_session

router = APIRouter(prefix="/identity", tags=["Identity"])


@router.get("/anomalies/{tenant_id}/{agent_id}")
async def get_identity_anomalies(
    tenant_id: str,
    agent_id: str,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(_get_session)],
) -> dict[str, object]:
    """Detect identity anomalies for an agent. IDY-010."""
    agent_repository = SQLAlchemyAgentRepository(session)
    session_repository = SQLAlchemyAgentSessionRepository(session)
    service = IdentityAnomalyDetectionService(
        agent_repository=agent_repository,
        session_repository=session_repository,
    )
    anomalies = await service.detect_anomalies(
        tenant_id=tenant_id,
        agent_id=agent_id,
    )
    return {
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "anomalies": [
            {
                "type": a.anomaly_type,
                "severity": a.severity,
                "description": a.explanation,
                "detected_at": a.detected_at.isoformat() if a.detected_at else None,
            }
            for a in anomalies
        ],
        "count": len(anomalies),
    }
