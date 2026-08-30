from collections.abc import Generator
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.application.dto.agent import (
    AuthorityGrantCreateRequest,
    AuthorityGrantListResponse,
    AuthorityGrantResponse,
)
from app.domain.entities.authority_grant import AuthorityScope, AuthorityStatus
from app.domain.repositories.authority_grant_repository import AuthorityGrantRepository
from app.infrastructure.logging.audit_logger import log_security_event
from app.infrastructure.observability.metrics import metrics
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_authority_grant_repository import (
    SQLAlchemyAuthorityGrantRepository,
)
from app.presentation.api.dependencies.auth import CurrentUser, get_user_tenant_id

router = APIRouter(tags=["Authority"])


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


def _get_grant_repository(
    session: Annotated[Session, Depends(_get_session)],
) -> AuthorityGrantRepository:
    return SQLAlchemyAuthorityGrantRepository(session)


@router.post("/", response_model=AuthorityGrantResponse, status_code=status.HTTP_201_CREATED)
async def create_grant(
    body: AuthorityGrantCreateRequest,
    current_user: CurrentUser,
    repo: Annotated[AuthorityGrantRepository, Depends(_get_grant_repository)],
) -> AuthorityGrantResponse:
    from app.domain.services.authority_lineage_service import AuthorityLineageService
    from app.infrastructure.persistence.repositories.sqlalchemy_agent_repository import (
        SQLAlchemyAgentRepository,
    )
    session = SessionLocal()
    try:
        agent_repo = SQLAlchemyAgentRepository(session)
        lineage = AuthorityLineageService(agent_repo, repo)
        scope = AuthorityScope(body.scope)
        delegation_depth = body.delegation_depth
        root_authority_id = body.parent_authority_id
        if body.parent_authority_id:
            parent = await repo.get_by_grant_id(
                get_user_tenant_id(current_user), body.parent_authority_id
            )
            if parent is None:
                raise HTTPException(status_code=400, detail="Parent authority grant not found")
            if parent.status != AuthorityStatus.ACTIVE:
                raise HTTPException(status_code=403, detail="Parent authority is not active")
            if parent.expires_at:
                expires_at = parent.expires_at
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
                if expires_at < datetime.now(UTC):
                    raise HTTPException(status_code=403, detail="Parent authority has expired")
            computed_depth = parent.delegation_depth + 1
            if computed_depth > 9:
                raise HTTPException(
                    status_code=403,
                    detail="Maximum delegation depth exceeded",
                )
            if not lineage._scope_within_parent(scope, parent.scope):
                raise HTTPException(
                    status_code=403,
                    detail="Delegated scope exceeds parent scope",
                )
            if body.grantor_agent_id != parent.grantee_agent_id:
                raise HTTPException(
                    status_code=403,
                    detail="Grantor must be the parent grantee for delegated authority",
                )
            delegation_depth = computed_depth
            root_authority_id = parent.root_authority_id or parent.grant_id
        elif body.delegation_depth != 0:
            raise HTTPException(
                status_code=400,
                detail="Root authority grants must have delegation_depth=0",
            )
        grant = lineage.create_authority(
            tenant_id=get_user_tenant_id(current_user),
            grantor_agent_id=body.grantor_agent_id,
            grantee_agent_id=body.grantee_agent_id,
            scope=scope,
            resource=body.resource,
            conditions=body.conditions,
            expires_at=body.expires_at,
            delegation_depth=delegation_depth,
            parent_authority_id=body.parent_authority_id,
            root_authority_id=root_authority_id,
        )
        grant = await repo.save(grant)
        log_security_event(
            "authority_granted",
            tenant_id=grant.tenant_id,
            grant_id=grant.grant_id,
            grantee_agent_id=grant.grantee_agent_id,
            scope=grant.scope.value,
            resource=grant.resource,
        )
        metrics.increment_security_exception("authority_granted")
        return AuthorityGrantResponse(
            grant_id=grant.grant_id,
            tenant_id=grant.tenant_id,
            grantor_agent_id=grant.grantor_agent_id,
            grantee_agent_id=grant.grantee_agent_id,
            scope=grant.scope.value,
            resource=grant.resource,
            conditions=grant.conditions,
            expires_at=grant.expires_at,
            delegation_depth=grant.delegation_depth,
            parent_authority_id=grant.parent_authority_id,
            root_authority_id=grant.root_authority_id,
            status=grant.status.value,
            revoked_at=grant.revoked_at,
            created_at=grant.created_at,
            updated_at=grant.updated_at,
        )
    finally:
        session.close()


@router.get("/", response_model=AuthorityGrantListResponse)
async def list_grants(
    current_user: CurrentUser,
    repo: Annotated[AuthorityGrantRepository, Depends(_get_grant_repository)],
    grantee_agent_id: str | None = Query(default=None),
    grantor_agent_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> AuthorityGrantListResponse:
    if grantee_agent_id:
        st = AuthorityStatus(status) if status else None
        items, total = await repo.list_by_grantee(
            get_user_tenant_id(current_user),
            grantee_agent_id,
            status=st,
            limit=limit,
            offset=offset,
        )
    elif grantor_agent_id:
        items, total = await repo.list_by_grantor(
            get_user_tenant_id(current_user), grantor_agent_id, limit=limit, offset=offset
        )
    else:
        raise HTTPException(status_code=400, detail="grantee_agent_id or grantor_agent_id required")
    return AuthorityGrantListResponse(
        items=[
            AuthorityGrantResponse(
                grant_id=g.grant_id,
                tenant_id=g.tenant_id,
                grantor_agent_id=g.grantor_agent_id,
                grantee_agent_id=g.grantee_agent_id,
                scope=g.scope.value,
                resource=g.resource,
                conditions=g.conditions,
                expires_at=g.expires_at,
                delegation_depth=g.delegation_depth,
                parent_authority_id=g.parent_authority_id,
                root_authority_id=g.root_authority_id,
                status=g.status.value,
                revoked_at=g.revoked_at,
                created_at=g.created_at,
                updated_at=g.updated_at,
            )
            for g in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{grant_id}", response_model=AuthorityGrantResponse)
async def get_grant(
    grant_id: str,
    current_user: CurrentUser,
    repo: Annotated[AuthorityGrantRepository, Depends(_get_grant_repository)],
) -> AuthorityGrantResponse:
    grant = await repo.get_by_grant_id(get_user_tenant_id(current_user), grant_id)
    if grant is None:
        raise HTTPException(status_code=404, detail="Authority grant not found")
    return AuthorityGrantResponse(
        grant_id=grant.grant_id,
        tenant_id=grant.tenant_id,
        grantor_agent_id=grant.grantor_agent_id,
        grantee_agent_id=grant.grantee_agent_id,
        scope=grant.scope.value,
        resource=grant.resource,
        conditions=grant.conditions,
        expires_at=grant.expires_at,
        delegation_depth=grant.delegation_depth,
        parent_authority_id=grant.parent_authority_id,
        root_authority_id=grant.root_authority_id,
        status=grant.status.value,
        revoked_at=grant.revoked_at,
        created_at=grant.created_at,
        updated_at=grant.updated_at,
    )


@router.post("/{grant_id}/revoke", response_model=AuthorityGrantResponse)
async def revoke_grant(
    grant_id: str,
    current_user: CurrentUser,
    repo: Annotated[AuthorityGrantRepository, Depends(_get_grant_repository)],
) -> AuthorityGrantResponse:
    grant = await repo.get_by_grant_id(get_user_tenant_id(current_user), grant_id)
    if grant is None:
        raise HTTPException(status_code=404, detail="Authority grant not found")
    if grant.status == AuthorityStatus.REVOKED:
        raise HTTPException(status_code=400, detail="Grant already revoked")
    from app.domain.services.authority_lineage_service import AuthorityLineageService
    from app.infrastructure.persistence.repositories.sqlalchemy_agent_repository import (
        SQLAlchemyAgentRepository,
    )
    session = SessionLocal()
    try:
        agent_repo = SQLAlchemyAgentRepository(session)
        lineage = AuthorityLineageService(agent_repo, repo)
        grant = await lineage.revoke_authority(
            get_user_tenant_id(current_user), grant_id, str(current_user.id)
        )
        if grant is None:
            raise HTTPException(status_code=404, detail="Authority grant not found")
        log_security_event(
            "authority_revoked",
            tenant_id=grant.tenant_id,
            grant_id=grant.grant_id,
            revoked_by=str(current_user.id),
        )
        metrics.increment_security_exception("authority_revoked")
        return AuthorityGrantResponse(
            grant_id=grant.grant_id,
            tenant_id=grant.tenant_id,
            grantor_agent_id=grant.grantor_agent_id,
            grantee_agent_id=grant.grantee_agent_id,
            scope=grant.scope.value,
            resource=grant.resource,
            conditions=grant.conditions,
            expires_at=grant.expires_at,
            delegation_depth=grant.delegation_depth,
            parent_authority_id=grant.parent_authority_id,
            root_authority_id=grant.root_authority_id,
            status=grant.status.value,
            revoked_at=grant.revoked_at,
            created_at=grant.created_at,
            updated_at=grant.updated_at,
        )
    finally:
        session.close()


@router.get("/{grant_id}/lineage")
async def get_grant_lineage(
    grant_id: str,
    current_user: CurrentUser,
    repo: Annotated[AuthorityGrantRepository, Depends(_get_grant_repository)],
) -> dict[str, Any]:
    from app.domain.services.authority_lineage_service import AuthorityLineageService
    from app.infrastructure.persistence.repositories.sqlalchemy_agent_repository import (
        SQLAlchemyAgentRepository,
    )
    session = SessionLocal()
    try:
        agent_repo = SQLAlchemyAgentRepository(session)
        lineage = AuthorityLineageService(agent_repo, repo)
        result = await lineage.get_lineage(get_user_tenant_id(current_user), grant_id)
        return result
    finally:
        session.close()
