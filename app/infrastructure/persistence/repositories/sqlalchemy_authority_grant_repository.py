import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities.authority_grant import AuthorityGrant, AuthorityScope, AuthorityStatus
from app.domain.repositories.authority_grant_repository import AuthorityGrantRepository
from app.infrastructure.persistence.models.authority_grant_model import AuthorityGrantModel


class SQLAlchemyAuthorityGrantRepository(AuthorityGrantRepository):
    """SQLAlchemy adapter for AuthorityGrantRepository port."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def get_by_grant_id(self, tenant_id: str, grant_id: str) -> AuthorityGrant | None:
        stmt = select(AuthorityGrantModel).where(
            AuthorityGrantModel.tenant_id == tenant_id,
            AuthorityGrantModel.grant_id == grant_id,
        )
        model = self._session.scalar(stmt)
        return self._to_entity(model) if model else None

    async def list_by_grantee(
        self,
        tenant_id: str,
        grantee_agent_id: str,
        status: AuthorityStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[AuthorityGrant], int]:
        stmt = select(AuthorityGrantModel).where(
            AuthorityGrantModel.tenant_id == tenant_id,
            AuthorityGrantModel.grantee_agent_id == grantee_agent_id,
        )
        if status is not None:
            stmt = stmt.where(AuthorityGrantModel.status == status.value)
        count_stmt = select(AuthorityGrantModel).where(
            AuthorityGrantModel.tenant_id == tenant_id,
            AuthorityGrantModel.grantee_agent_id == grantee_agent_id,
        )
        if status is not None:
            count_stmt = count_stmt.where(AuthorityGrantModel.status == status.value)
        total = len(self._session.scalars(count_stmt).all())
        stmt = stmt.order_by(AuthorityGrantModel.created_at.desc()).limit(limit).offset(offset)
        models = self._session.scalars(stmt).all()
        return [self._to_entity(m) for m in models], total

    async def list_by_grantor(
        self,
        tenant_id: str,
        grantor_agent_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[AuthorityGrant], int]:
        stmt = select(AuthorityGrantModel).where(
            AuthorityGrantModel.tenant_id == tenant_id,
            AuthorityGrantModel.grantor_agent_id == grantor_agent_id,
        )
        count_stmt = select(AuthorityGrantModel).where(
            AuthorityGrantModel.tenant_id == tenant_id,
            AuthorityGrantModel.grantor_agent_id == grantor_agent_id,
        )
        total = len(self._session.scalars(count_stmt).all())
        stmt = stmt.order_by(AuthorityGrantModel.created_at.desc()).limit(limit).offset(offset)
        models = self._session.scalars(stmt).all()
        return [self._to_entity(m) for m in models], total

    async def list_by_tenant(
        self,
        tenant_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[AuthorityGrant], int]:
        stmt = select(AuthorityGrantModel).where(
            AuthorityGrantModel.tenant_id == tenant_id,
        )
        count_stmt = select(AuthorityGrantModel).where(
            AuthorityGrantModel.tenant_id == tenant_id,
        )
        total = len(self._session.scalars(count_stmt).all())
        stmt = stmt.order_by(AuthorityGrantModel.created_at.desc()).limit(limit).offset(offset)
        models = self._session.scalars(stmt).all()
        return [self._to_entity(m) for m in models], total

    async def list_descendants(
        self,
        tenant_id: str,
        root_authority_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[AuthorityGrant], int]:
        stmt = select(AuthorityGrantModel).where(
            AuthorityGrantModel.tenant_id == tenant_id,
            AuthorityGrantModel.root_authority_id == root_authority_id,
        )
        count_stmt = select(AuthorityGrantModel).where(
            AuthorityGrantModel.tenant_id == tenant_id,
            AuthorityGrantModel.root_authority_id == root_authority_id,
        )
        total = len(self._session.scalars(count_stmt).all())
        stmt = stmt.order_by(AuthorityGrantModel.delegation_depth.asc()).limit(limit).offset(offset)
        models = self._session.scalars(stmt).all()
        return [self._to_entity(m) for m in models], total

    async def save(self, grant: AuthorityGrant) -> AuthorityGrant:
        stmt = select(AuthorityGrantModel).where(AuthorityGrantModel.grant_id == grant.grant_id)
        model = self._session.scalar(stmt)
        if model is None:
            model = AuthorityGrantModel(
                grant_id=grant.grant_id,
                tenant_id=grant.tenant_id,
                grantor_agent_id=grant.grantor_agent_id,
                grantee_agent_id=grant.grantee_agent_id,
                scope=grant.scope.value,
                resource=grant.resource,
                conditions=json.dumps(grant.conditions),
                expires_at=grant.expires_at,
                delegation_depth=grant.delegation_depth,
                parent_authority_id=grant.parent_authority_id,
                root_authority_id=grant.root_authority_id,
                status=grant.status.value,
                revoked_at=grant.revoked_at,
                revoked_by=grant.revoked_by,
                grant_metadata=json.dumps(grant.metadata),
                created_at=grant.created_at,
                updated_at=grant.updated_at,
                is_jit=grant.is_jit,
                jit_created_at=grant.jit_created_at,
                jit_expires_at=grant.jit_expires_at,
                jit_consumed_at=grant.jit_consumed_at,
                one_shot=grant.one_shot,
                usage_count=grant.usage_count,
            )
            self._session.add(model)
        else:
            model.scope = grant.scope.value
            model.resource = grant.resource
            model.conditions = json.dumps(grant.conditions)
            model.expires_at = grant.expires_at
            model.delegation_depth = grant.delegation_depth
            model.parent_authority_id = grant.parent_authority_id
            model.root_authority_id = grant.root_authority_id
            model.status = grant.status.value
            model.revoked_at = grant.revoked_at
            model.revoked_by = grant.revoked_by
            model.grant_metadata = json.dumps(grant.metadata)
            model.updated_at = datetime.now(UTC)
            model.is_jit = grant.is_jit
            model.jit_created_at = grant.jit_created_at
            model.jit_expires_at = grant.jit_expires_at
            model.jit_consumed_at = grant.jit_consumed_at
            model.one_shot = grant.one_shot
            model.usage_count = grant.usage_count
        self._session.flush()
        return self._to_entity(model)

    async def revoke(self, tenant_id: str, grant_id: str, revoked_by: str) -> AuthorityGrant | None:
        stmt = select(AuthorityGrantModel).where(
            AuthorityGrantModel.tenant_id == tenant_id,
            AuthorityGrantModel.grant_id == grant_id,
        )
        model = self._session.scalar(stmt)
        if model is None:
            return None
        model.status = AuthorityStatus.REVOKED.value
        model.revoked_at = datetime.now(UTC)
        model.revoked_by = revoked_by
        model.updated_at = datetime.now(UTC)
        self._session.flush()
        return self._to_entity(model)

    async def get_active_for_agent(
        self, tenant_id: str, agent_id: str, resource: str | None = None
    ) -> list[AuthorityGrant]:
        stmt = select(AuthorityGrantModel).where(
            AuthorityGrantModel.tenant_id == tenant_id,
            AuthorityGrantModel.grantee_agent_id == agent_id,
            AuthorityGrantModel.status == AuthorityStatus.ACTIVE.value,
            AuthorityGrantModel.expires_at > datetime.now(UTC),
        )
        if resource is not None:
            stmt = stmt.where(AuthorityGrantModel.resource == resource)
        models = self._session.scalars(stmt).all()
        return [self._to_entity(m) for m in models]

    async def consume_one_shot(self, tenant_id: str, grant_id: str) -> AuthorityGrant | None:
        from datetime import UTC as _UTC

        now = datetime.now(_UTC)
        stmt = (
            select(AuthorityGrantModel)
            .where(
                AuthorityGrantModel.tenant_id == tenant_id,
                AuthorityGrantModel.grant_id == grant_id,
                AuthorityGrantModel.status == AuthorityStatus.ACTIVE.value,
                AuthorityGrantModel.one_shot.is_(True),
                AuthorityGrantModel.usage_count == 0,
                (AuthorityGrantModel.expires_at.is_(None) | (AuthorityGrantModel.expires_at > now)),
            )
            .with_for_update(skip_locked=True)
        )
        model = self._session.scalar(stmt)
        if model is None:
            return None
        model.status = AuthorityStatus.ONE_SHOT_USED.value
        model.usage_count = 1
        model.jit_consumed_at = now
        model.updated_at = now
        self._session.flush()
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: AuthorityGrantModel) -> AuthorityGrant:
        conditions: dict[str, str] = {}
        if model.conditions:
            try:
                conditions = json.loads(model.conditions)
            except (ValueError, TypeError):
                conditions = {}
        metadata: dict[str, str] = {}
        if model.grant_metadata:
            try:
                metadata = json.loads(model.grant_metadata)
            except (ValueError, TypeError):
                metadata = {}
        return AuthorityGrant(
            grant_id=model.grant_id,
            tenant_id=model.tenant_id,
            grantor_agent_id=model.grantor_agent_id,
            grantee_agent_id=model.grantee_agent_id,
            scope=AuthorityScope(model.scope),
            resource=model.resource,
            conditions=conditions,
            expires_at=model.expires_at,
            delegation_depth=model.delegation_depth,
            parent_authority_id=model.parent_authority_id,
            root_authority_id=model.root_authority_id,
            status=AuthorityStatus(model.status),
            revoked_at=model.revoked_at,
            revoked_by=model.revoked_by,
            metadata=metadata,
            created_at=model.created_at,
            updated_at=model.updated_at,
            is_jit=model.is_jit,
            jit_created_at=model.jit_created_at,
            jit_expires_at=model.jit_expires_at,
            jit_consumed_at=model.jit_consumed_at,
            one_shot=model.one_shot,
            usage_count=model.usage_count,
        )
