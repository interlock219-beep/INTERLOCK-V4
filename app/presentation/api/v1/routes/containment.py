from __future__ import annotations

from collections.abc import Generator
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.domain.entities.containment_event import ContainmentMode
from app.domain.services.cascade_containment_service import CascadeContainmentService
from app.infrastructure.logging.audit_logger import log_security_event
from app.infrastructure.observability.metrics import metrics
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_agent_repository import (
    SQLAlchemyAgentRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_authority_grant_repository import (
    SQLAlchemyAuthorityGrantRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_containment_repository import (
    SQLAlchemyContainmentRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_execution_token_repository import (
    SQLAlchemyExecutionTokenRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_protected_action_repository import (
    SQLAlchemyProtectedActionRepository,
)
from app.presentation.api.dependencies.auth import CurrentUser, get_user_tenant_id

router = APIRouter(prefix="/containment", tags=["Containment"])


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


def _get_containment_service(
    session: Annotated[Session, Depends(_get_session)],
) -> CascadeContainmentService:
    agent_repo = SQLAlchemyAgentRepository(session)
    grant_repo = SQLAlchemyAuthorityGrantRepository(session)
    containment_repo = SQLAlchemyContainmentRepository(session)
    action_repo = SQLAlchemyProtectedActionRepository(session)
    token_repo = SQLAlchemyExecutionTokenRepository(session)
    return CascadeContainmentService(
        agent_repository=agent_repo,
        grant_repository=grant_repo,
        containment_repository=containment_repo,
        action_repository=action_repo,
        token_repository=token_repo,
    )


@router.post("/authority-tree/{agent_id}")
async def contain_authority_tree(
    agent_id: str,
    mode: ContainmentMode,
    current_user: CurrentUser,
    service: Annotated[CascadeContainmentService, Depends(_get_containment_service)],
    reason: str = "",
    dry_run: bool = False,
) -> dict[str, object]:
    """Contain an agent's entire authority tree. CNF-002."""
    tenant_id = get_user_tenant_id(current_user)
    result = await service.contain_authority_tree(
        tenant_id=tenant_id,
        target_agent_id=agent_id,
        mode=mode,
        initiated_by=str(current_user.id),
        authorized_by=str(current_user.id),
        reason=reason,
        dry_run=dry_run,
    )
    log_security_event(
        "authority_tree_containment",
        tenant_id=tenant_id,
        agent_id=agent_id,
        mode=mode.value,
    )
    metrics.increment_security_exception("authority_tree_containment")
    return asdict(result)


@router.get("/blast-radius/{agent_id}")
async def get_blast_radius(
    agent_id: str,
    current_user: CurrentUser,
    service: Annotated[CascadeContainmentService, Depends(_get_containment_service)],
) -> dict[str, object]:
    """Calculate blast radius for an agent. CNF-003."""
    tenant_id = get_user_tenant_id(current_user)
    radius = await service.get_blast_radius(tenant_id, agent_id)
    return {
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "blast_radius": radius,
    }


@router.post("/execution-tokens/{agent_id}")
async def contain_execution_tokens(
    agent_id: str,
    current_user: CurrentUser,
    service: Annotated[CascadeContainmentService, Depends(_get_containment_service)],
    reason: str = "agent_containment",
) -> dict[str, object]:
    """Revoke all execution tokens for an agent."""
    tenant_id = get_user_tenant_id(current_user)
    result = await service.contain_execution_tokens(
        tenant_id=tenant_id,
        agent_id=agent_id,
        dry_run=False,
    )
    metrics.increment_security_exception("execution_tokens_contained")
    return {"revoked_tokens": result}
