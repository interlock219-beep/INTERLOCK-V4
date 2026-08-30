from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from app.domain.entities.agent import AgentStatus, RiskClassification
from app.domain.entities.authority_grant import AuthorityGrant, AuthorityScope, AuthorityStatus
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.authority_grant_repository import AuthorityGrantRepository
from app.domain.value_objects.authorization_decision import AuthorizationDecision


class AuthorityLineageService:
    """Service for managing authority grants and lineage traversal."""

    def __init__(
        self,
        agent_repository: AgentRepository,
        grant_repository: AuthorityGrantRepository,
    ) -> None:
        self._agent_repo = agent_repository
        self._grant_repo = grant_repository

    @staticmethod
    def _normalize_scope(scope: str | AuthorityScope) -> AuthorityScope:
        if isinstance(scope, AuthorityScope):
            return scope
        return AuthorityScope(scope)

    def create_authority(
        self,
        tenant_id: str,
        grantor_agent_id: str,
        grantee_agent_id: str,
        scope: str | AuthorityScope,
        resource: str,
        *,
        conditions: dict[str, str] | None = None,
        expires_at: datetime | None = None,
        parent_authority_id: str | None = None,
        root_authority_id: str | None = None,
        delegation_depth: int = 0,
        metadata: dict[str, str] | None = None,
    ) -> AuthorityGrant:
        normalized_scope = self._normalize_scope(scope)
        grant_id = f"auth-{secrets.token_hex(12)}"
        now = datetime.now(UTC)
        return AuthorityGrant(
            grant_id=grant_id,
            tenant_id=tenant_id,
            grantor_agent_id=grantor_agent_id,
            grantee_agent_id=grantee_agent_id,
            scope=normalized_scope,
            resource=resource,
            conditions=conditions or {},
            expires_at=expires_at,
            delegation_depth=delegation_depth,
            parent_authority_id=parent_authority_id,
            root_authority_id=root_authority_id,
            status=AuthorityStatus.ACTIVE,
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )

    async def delegate_authority(
        self,
        tenant_id: str,
        parent_grant_id: str,
        new_grantee_agent_id: str,
        scope: str | AuthorityScope,
        resource: str,
        *,
        conditions: dict[str, str] | None = None,
        expires_at: datetime | None = None,
        metadata: dict[str, str] | None = None,
    ) -> AuthorityGrant:
        parent = await self._grant_repo.get_by_grant_id(tenant_id, parent_grant_id)
        if parent is None:
            raise ValueError("Parent authority grant not found")
        if parent.status != AuthorityStatus.ACTIVE:
            raise ValueError("Parent authority is not active")
        if parent.expires_at:
            now = datetime.now(UTC)
            parent_expires = parent.expires_at
            if parent_expires.tzinfo is None:
                parent_expires = parent_expires.replace(tzinfo=UTC)
            if parent_expires < now:
                raise ValueError("Parent authority has expired")
        if parent.delegation_depth >= 9:
            raise ValueError("Maximum delegation depth exceeded")
        normalized_scope = self._normalize_scope(scope)
        if not self._scope_within_parent(normalized_scope, parent.scope):
            raise ValueError("Delegated scope exceeds parent scope")
        if await self._is_circular(tenant_id, parent, new_grantee_agent_id):
            raise ValueError("Circular delegation detected")
        root_id = parent.root_authority_id or parent.grant_id
        return self.create_authority(
            tenant_id=tenant_id,
            grantor_agent_id=parent.grantee_agent_id,
            grantee_agent_id=new_grantee_agent_id,
            scope=normalized_scope,
            resource=resource,
            conditions=conditions or {},
            expires_at=expires_at,
            parent_authority_id=parent_grant_id,
            root_authority_id=root_id,
            delegation_depth=parent.delegation_depth + 1,
            metadata=metadata or {},
        )

    async def _is_circular(self, tenant_id: str, parent: AuthorityGrant, new_grantee: str) -> bool:
        current: AuthorityGrant | None = parent
        while current is not None:
            if current.grantor_agent_id == new_grantee:
                return True
            if current.parent_authority_id is None:
                break
            current = await self._grant_repo.get_by_grant_id(tenant_id, current.parent_authority_id)
        return False

    async def revoke_authority(
        self, tenant_id: str, grant_id: str, revoked_by: str
    ) -> AuthorityGrant | None:
        return await self._grant_repo.revoke(tenant_id, grant_id, revoked_by)

    async def get_lineage(self, tenant_id: str, grant_id: str) -> dict[str, Any]:
        grant = await self._grant_repo.get_by_grant_id(tenant_id, grant_id)
        if grant is None:
            raise ValueError("Authority grant not found")
        ancestors: list[dict[str, Any]] = []
        current = grant
        while current.parent_authority_id:
            parent = await self._grant_repo.get_by_grant_id(tenant_id, current.parent_authority_id)
            if parent is None:
                break
            ancestors.append({
                "grant_id": parent.grant_id,
                "grantor_agent_id": parent.grantor_agent_id,
                "grantee_agent_id": parent.grantee_agent_id,
                "scope": parent.scope.value,
                "resource": parent.resource,
                "status": parent.status.value,
            })
            current = parent
        descendants, total = await self._grant_repo.list_descendants(
            tenant_id, grant.root_authority_id or grant.grant_id, limit=1000, offset=0
        )
        descendant_summary = [
            {
                "grant_id": d.grant_id,
                "grantee_agent_id": d.grantee_agent_id,
                "scope": d.scope.value,
                "resource": d.resource,
                "status": d.status.value,
                "delegation_depth": d.delegation_depth,
            }
            for d in descendants
        ]
        return {
            "grant_id": grant.grant_id,
            "root_authority_id": grant.root_authority_id,
            "ancestors": ancestors,
            "descendants_count": total,
            "descendants": descendant_summary,
        }

    async def get_affected_resources(self, tenant_id: str, grant_id: str) -> dict[str, Any]:
        grant = await self._grant_repo.get_by_grant_id(tenant_id, grant_id)
        if grant is None:
            raise ValueError("Authority grant not found")
        root_id = grant.root_authority_id or grant.grant_id
        descendants, _ = await self._grant_repo.list_descendants(
            tenant_id, root_id, limit=1000, offset=0
        )
        resources: dict[str, list[str]] = {}
        for d in descendants:
            resources.setdefault(d.resource, [])
            if d.grantee_agent_id not in resources[d.resource]:
                resources[d.resource].append(d.grantee_agent_id)
        return {
            "root_authority_id": root_id,
            "resources": resources,
            "total_affected_agents": sum(len(v) for v in resources.values()),
        }

    async def validate_delegation(
        self,
        tenant_id: str,
        grantor_agent_id: str,
        grantee_agent_id: str,
        resource: str,
        scope: AuthorityScope,
    ) -> AuthorizationDecision:
        grantor = await self._agent_repo.get_by_agent_id(tenant_id, grantor_agent_id)
        if grantor is None:
            return AuthorizationDecision.DENY
        if grantor.status != AgentStatus.ACTIVE:
            return AuthorizationDecision.DENY
        if grantor.risk_classification in (RiskClassification.HIGH, RiskClassification.CRITICAL):
            return AuthorizationDecision.REQUIRE_HITL
        active_grants = await self._grant_repo.get_active_for_agent(
            tenant_id, grantor_agent_id, resource
        )
        if not active_grants:
            return AuthorizationDecision.DENY
        for grant in active_grants:
            if self._scope_within_parent(scope, grant.scope):
                return AuthorizationDecision.ALLOW
        return AuthorizationDecision.DENY

    @staticmethod
    def _scope_within_parent(child: AuthorityScope, parent: AuthorityScope) -> bool:
        hierarchy = {
            AuthorityScope.READ: 1,
            AuthorityScope.WRITE: 2,
            AuthorityScope.EXECUTE: 3,
            AuthorityScope.ADMIN: 4,
            AuthorityScope.CUSTOM: 5,
        }
        return hierarchy[child] <= hierarchy[parent]
