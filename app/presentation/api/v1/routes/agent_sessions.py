from collections.abc import Generator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.domain.entities.agent_session import AgentSession, AgentSessionStatus
from app.domain.repositories.agent_session_repository import AgentSessionRepository
from app.infrastructure.logging.audit_logger import log_security_event
from app.infrastructure.observability.metrics import metrics
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_agent_session_repository import (
    SQLAlchemyAgentSessionRepository,
)
from app.presentation.api.dependencies.auth import CurrentUser, get_user_tenant_id

router = APIRouter(tags=["Agent Sessions"])


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


def _get_session_repo(
    session: Annotated[Session, Depends(_get_session)],
) -> AgentSessionRepository:
    return SQLAlchemyAgentSessionRepository(session)


@router.post(
    "/",
    response_model=dict[str, Any],
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_session(
    body: dict[str, Any],
    current_user: CurrentUser,
    repo: Annotated[AgentSessionRepository, Depends(_get_session_repo)],
) -> dict[str, Any]:
    import secrets

    session_id = body.get("session_id") or f"ses-{secrets.token_hex(12)}"
    existing = await repo.get_by_session_id(get_user_tenant_id(current_user), session_id)
    if existing:
        raise HTTPException(status_code=409, detail="Session already exists")

    agent_session = AgentSession(
        session_id=session_id,
        tenant_id=get_user_tenant_id(current_user),
        agent_id=body.get("agent_id", ""),
        intent_id=body.get("intent_id"),
        policy_version=body.get("policy_version"),
        correlation_id=body.get("correlation_id", ""),
        parent_session_id=body.get("parent_session_id"),
        risk_level=body.get("risk_level", "low"),
        status=AgentSessionStatus.ACTIVE,
        metadata=body.get("metadata", {}),
    )
    saved = await repo.save(agent_session)
    log_security_event(
        "agent_session_created",
        tenant_id=saved.tenant_id,
        session_id=saved.session_id,
        agent_id=saved.agent_id,
    )
    return {
        "session_id": saved.session_id,
        "tenant_id": saved.tenant_id,
        "agent_id": saved.agent_id,
        "status": saved.status.value,
        "created_at": saved.started_at.isoformat(),
    }


@router.get(
    "/{session_id}",
    response_model=dict[str, Any],
)
async def get_agent_session(
    session_id: str,
    current_user: CurrentUser,
    repo: Annotated[AgentSessionRepository, Depends(_get_session_repo)],
) -> dict[str, Any]:
    session = await repo.get_by_session_id(get_user_tenant_id(current_user), session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session.session_id,
        "tenant_id": session.tenant_id,
        "agent_id": session.agent_id,
        "intent_id": session.intent_id,
        "policy_version": session.policy_version,
        "status": session.status.value,
        "risk_level": session.risk_level,
        "correlation_id": session.correlation_id,
        "parent_session_id": session.parent_session_id,
        "started_at": session.started_at.isoformat(),
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "metadata": session.metadata,
    }


@router.post(
    "/{session_id}/freeze",
    response_model=dict[str, Any],
)
async def freeze_agent_session(
    session_id: str,
    current_user: CurrentUser,
    repo: Annotated[AgentSessionRepository, Depends(_get_session_repo)],
) -> dict[str, Any]:
    from datetime import UTC, datetime

    session = await repo.get_by_session_id(get_user_tenant_id(current_user), session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status in (AgentSessionStatus.FROZEN, AgentSessionStatus.COMPLETED):
        raise HTTPException(
            status_code=400,
            detail=f"Session is already {session.status.value}",
        )
    await repo.update_status(
        get_user_tenant_id(current_user), session_id, AgentSessionStatus.FROZEN
    )
    log_security_event(
        "agent_session_frozen",
        tenant_id=get_user_tenant_id(current_user),
        session_id=session_id,
        agent_id=session.agent_id,
    )
    metrics.increment_security_exception("agent_session_frozen")
    return {
        "session_id": session_id,
        "status": AgentSessionStatus.FROZEN.value,
        "frozen_at": datetime.now(UTC).isoformat(),
    }


@router.post(
    "/{session_id}/rollback",
    response_model=dict[str, Any],
)
async def rollback_agent_session(
    session_id: str,
    current_user: CurrentUser,
    repo: Annotated[AgentSessionRepository, Depends(_get_session_repo)],
) -> dict[str, Any]:
    session = await repo.get_by_session_id(get_user_tenant_id(current_user), session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status == AgentSessionStatus.ROLLING_BACK:
        raise HTTPException(status_code=409, detail="Rollback already in progress")
    await repo.update_status(
        get_user_tenant_id(current_user), session_id, AgentSessionStatus.ROLLBACK_PENDING
    )
    log_security_event(
        "agent_session_rollback_requested",
        tenant_id=get_user_tenant_id(current_user),
        session_id=session_id,
        agent_id=session.agent_id,
    )
    return {
        "session_id": session_id,
        "status": AgentSessionStatus.ROLLBACK_PENDING.value,
        "message": "Rollback requested. Recovery plan will be generated and executed.",
    }


@router.post(
    "/{session_id}/rollback/preview",
    response_model=dict[str, Any],
)
async def preview_agent_session_rollback(
    session_id: str,
    current_user: CurrentUser,
    repo: Annotated[AgentSessionRepository, Depends(_get_session_repo)],
) -> dict[str, Any]:
    session = await repo.get_by_session_id(get_user_tenant_id(current_user), session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "agent_id": session.agent_id,
        "status": session.status.value,
        "preview": {
            "affected_resources": [],
            "recoverable": [],
            "irreversible": [],
            "conflicts": [],
            "blast_radius": "unknown",
        },
        "message": "Preview generated. Execute rollback to apply recovery.",
    }
