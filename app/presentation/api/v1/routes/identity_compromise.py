from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.domain.repositories.agent_repository import AgentRepository
from app.domain.services.identity_compromise_service import (
    IdentityCompromiseIndicator,
    IdentityCompromiseService,
)
from app.infrastructure.logging.audit_logger import log_security_event
from app.infrastructure.observability.metrics import metrics
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_agent_repository import (
    SQLAlchemyAgentRepository,
)
from app.presentation.api.dependencies.auth import CurrentUser, get_user_tenant_id

router = APIRouter(tags=["Identity"])


def _get_session() -> Any:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _get_agent_repo(
    session: Annotated[Session, Depends(_get_session)],
) -> AgentRepository:
    return SQLAlchemyAgentRepository(session)


@router.get("/compromise/indicators/{agent_id}")
async def get_compromise_indicators(
    agent_id: str,
    current_user: CurrentUser,
    agent_repo: Annotated[AgentRepository, Depends(_get_agent_repo)],
) -> dict[str, Any]:
    """Get identity compromise indicators for an agent. IDY-024."""
    service = IdentityCompromiseService(agent_repo)
    indicators = await service.check_compromise_indicators(
        tenant_id=get_user_tenant_id(current_user),
        agent_id=agent_id,
    )

    log_security_event(
        "identity_compromise_checked",
        tenant_id=get_user_tenant_id(current_user),
        agent_id=agent_id,
        indicator_count=len(indicators),
    )
    metrics.increment_security_exception("identity_compromise_checked")
    return {
        "tenant_id": get_user_tenant_id(current_user),
        "agent_id": agent_id,
        "indicators": [
            {
                "indicator_type": i.indicator_type,
                "severity": i.severity,
                "description": i.description,
                "detected_at": i.detected_at.isoformat(),
                "evidence": i.evidence,
            }
            for i in indicators
        ],
        "count": len(indicators),
    }


@router.get("/compromise/summary")
async def get_compromise_summary(
    current_user: CurrentUser,
    agent_repo: Annotated[AgentRepository, Depends(_get_agent_repo)],
) -> dict[str, Any]:
    """Get compromise indicator summary across all agents. IDY-024."""
    if current_user.role not in {"admin", "operator"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for this operation.",
        )

    service = IdentityCompromiseService(agent_repo)
    summary = await service.get_compromise_summary(
        tenant_id=get_user_tenant_id(current_user),
    )

    log_security_event(
        "identity_compromise_summary_viewed",
        tenant_id=get_user_tenant_id(current_user),
        agents_with_indicators=summary.get("agents_with_indicators", 0),
    )
    metrics.increment_security_exception("identity_compromise_summary_viewed")
    return summary
