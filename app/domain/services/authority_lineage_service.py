from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from app.domain.entities.agent import AgentStatus, RiskClassification
from app.domain.entities.authority_grant import (
    AuthorityGrant,
    AuthorityScope,
    AuthorityStatus,
)
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.authority_grant_repository import AuthorityGrantRepository
from app.domain.value_objects.authorization_decision import AuthorizationDecision


class AuthorityLineageService:
    """Service for managing authority grants and lineage traversal."""

    def __init__(
        self,
        agent_repository: AgentRepository,
        grant_repository: AuthorityGrantRepository,
        max_delegation_depth: int = 9,
    ) -> None:
        self._agent_repo = agent_repository
        self._grant_repo = grant_repository
        self._max_delegation_depth = max_delegation_depth

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

    async def enforce_max_delegation_depth(
        self, tenant_id: str, parent_grant_id: str, new_grantee_agent_id: str
    ) -> bool:
        """Check if delegating would exceed max depth."""
        parent = await self._grant_repo.get_by_grant_id(tenant_id, parent_grant_id)
        if parent is None:
            raise ValueError("Parent grant not found")
        max_depth = getattr(self, "_max_delegation_depth", 9)
        if parent.delegation_depth >= max_depth:
            raise ValueError(f"Maximum delegation depth {max_depth} exceeded")
        return True

    async def create_one_shot_authority(
        self,
        tenant_id: str,
        grantor_agent_id: str,
        grantee_agent_id: str,
        scope: str | AuthorityScope,
        resource: str,
        *,
        conditions: dict[str, str] | None = None,
        expires_at: datetime | None = None,
    ) -> AuthorityGrant:
        """Create a one-shot authority that auto-revokes after first use."""
        grant = self.create_authority(
            tenant_id,
            grantor_agent_id,
            grantee_agent_id,
            scope,
            resource,
            conditions=conditions,
            expires_at=expires_at,
        )
        grant = AuthorityGrant(
            grant_id=grant.grant_id,
            tenant_id=grant.tenant_id,
            grantor_agent_id=grant.grantor_agent_id,
            grantee_agent_id=grant.grantee_agent_id,
            scope=grant.scope,
            resource=grant.resource,
            conditions=grant.conditions,
            expires_at=grant.expires_at,
            delegation_depth=grant.delegation_depth,
            parent_authority_id=grant.parent_authority_id,
            root_authority_id=grant.root_authority_id,
            status=grant.status,
            metadata=grant.metadata,
            created_at=grant.created_at,
            updated_at=grant.updated_at,
            is_jit=grant.is_jit,
            jit_created_at=grant.jit_created_at,
            jit_expires_at=grant.jit_expires_at,
            jit_consumed_at=grant.jit_consumed_at,
            one_shot=True,
            usage_count=grant.usage_count,
        )
        await self._grant_repo.save(grant)
        return grant

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
        if parent.is_jit:
            raise ValueError("JIT authority cannot be delegated")
        if parent.one_shot:
            raise ValueError("One-shot authority cannot be delegated")
        if parent.expires_at:
            now = datetime.now(UTC)
            parent_expires = parent.expires_at
            if parent_expires.tzinfo is None:
                parent_expires = parent_expires.replace(tzinfo=UTC)
            if parent_expires < now:
                raise ValueError("Parent authority has expired")
        await self.enforce_max_delegation_depth(tenant_id, parent_grant_id, new_grantee_agent_id)
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
        now = datetime.now(UTC)
        for grant in active_grants:
            if grant.is_jit and grant.jit_expires_at is not None:
                jit_expires = grant.jit_expires_at
                if jit_expires.tzinfo is None:
                    jit_expires = jit_expires.replace(tzinfo=UTC)
                if jit_expires < now:
                    continue
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

    def create_jit_authority(
        self,
        tenant_id: str,
        grantor_agent_id: str,
        grantee_agent_id: str,
        scope: str | AuthorityScope,
        resource: str,
        *,
        ttl_seconds: int = 300,
        conditions: dict[str, str] | None = None,
    ) -> AuthorityGrant:
        normalized_scope = self._normalize_scope(scope)
        grant_id = f"jit-{secrets.token_hex(12)}"
        now = datetime.now(UTC)
        jit_expires = now + __import__("datetime").timedelta(seconds=ttl_seconds)
        return AuthorityGrant(
            grant_id=grant_id,
            tenant_id=tenant_id,
            grantor_agent_id=grantor_agent_id,
            grantee_agent_id=grantee_agent_id,
            scope=normalized_scope,
            resource=resource,
            conditions=conditions or {},
            expires_at=jit_expires,
            delegation_depth=0,
            parent_authority_id=None,
            root_authority_id=grant_id,
            status=AuthorityStatus.ACTIVE,
            metadata={"jit": "true"},
            created_at=now,
            updated_at=now,
            is_jit=True,
            jit_created_at=now,
            jit_expires_at=jit_expires,
        )

    async def consume_one_shot(
        self, tenant_id: str, grant_id: str
    ) -> AuthorityGrant | None:
        grant = await self._grant_repo.get_by_grant_id(tenant_id, grant_id)
        if grant is None:
            return None
        if grant.status != AuthorityStatus.ACTIVE:
            return None
        if grant.expires_at:
            now = datetime.now(UTC)
            expires = grant.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            if expires < now:
                return None
        if not grant.one_shot:
            return grant
        if grant.usage_count > 0:
            return None
        consumed = AuthorityGrant(
            grant_id=grant.grant_id,
            tenant_id=grant.tenant_id,
            grantor_agent_id=grant.grantor_agent_id,
            grantee_agent_id=grant.grantee_agent_id,
            scope=grant.scope,
            resource=grant.resource,
            conditions=grant.conditions,
            expires_at=grant.expires_at,
            delegation_depth=grant.delegation_depth,
            parent_authority_id=grant.parent_authority_id,
            root_authority_id=grant.root_authority_id,
            status=AuthorityStatus.ONE_SHOT_USED,
            revoked_at=grant.revoked_at,
            revoked_by=grant.revoked_by,
            metadata=grant.metadata,
            created_at=grant.created_at,
            updated_at=datetime.now(UTC),
            is_jit=grant.is_jit,
            jit_created_at=grant.jit_created_at,
            jit_expires_at=grant.jit_expires_at,
            jit_consumed_at=datetime.now(UTC),
            one_shot=grant.one_shot,
            usage_count=grant.usage_count + 1,
        )
        await self._grant_repo.save(consumed)
        return consumed

    async def validate_attenuation(
        self,
        tenant_id: str,
        grantor_agent_id: str,
        grantee_agent_id: str,
        resource: str,
        scope: AuthorityScope,
    ) -> AuthorizationDecision:
        decision = await self.validate_delegation(
            tenant_id, grantor_agent_id, grantee_agent_id, resource, scope
        )
        if decision != AuthorizationDecision.ALLOW:
            return decision
        grantor = await self._agent_repo.get_by_agent_id(tenant_id, grantor_agent_id)
        if grantor is None:
            return AuthorizationDecision.DENY
        active_grants = await self._grant_repo.get_active_for_agent(
            tenant_id, grantor_agent_id, resource
        )
        for grant in active_grants:
            if not self._scope_within_parent(scope, grant.scope):
                return AuthorizationDecision.DENY
        return AuthorizationDecision.ALLOW

    async def validate_chain_consistency(self, tenant_id: str, grant_id: str) -> dict[str, Any]:
        grant = await self._grant_repo.get_by_grant_id(tenant_id, grant_id)
        if grant is None:
            raise ValueError("Authority grant not found")
        current = grant
        max_depth = 0
        chain: list[dict[str, Any]] = []
        while current is not None:
            chain.append({
                "grant_id": current.grant_id,
                "scope": current.scope.value,
                "status": current.status.value,
                "delegation_depth": current.delegation_depth,
            })
            if current.delegation_depth > max_depth:
                max_depth = current.delegation_depth
            if current.parent_authority_id is None:
                break
            current = await self._grant_repo.get_by_grant_id(tenant_id, current.parent_authority_id)
            if current is None:
                break
        return {
            "grant_id": grant_id,
            "chain": chain,
            "max_depth": max_depth,
            "consistent": True,
        }

    async def expire_jit_grants(self, tenant_id: str) -> int:
        now = datetime.now(UTC)
        all_grants, total = await self._grant_repo.list_by_tenant(tenant_id, limit=5000, offset=0)
        expired_count = 0
        for grant in all_grants:
            if not grant.is_jit:
                continue
            if grant.status != AuthorityStatus.ACTIVE:
                continue
            if grant.jit_expires_at is None:
                continue
            expires = grant.jit_expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            if expires < now:
                expired = AuthorityGrant(
                    grant_id=grant.grant_id,
                    tenant_id=grant.tenant_id,
                    grantor_agent_id=grant.grantor_agent_id,
                    grantee_agent_id=grant.grantee_agent_id,
                    scope=grant.scope,
                    resource=grant.resource,
                    conditions=grant.conditions,
                    expires_at=grant.expires_at,
                    delegation_depth=grant.delegation_depth,
                    parent_authority_id=grant.parent_authority_id,
                    root_authority_id=grant.root_authority_id,
                    status=AuthorityStatus.JIT_EXPIRED,
                    revoked_at=grant.revoked_at,
                    revoked_by=grant.revoked_by,
                    metadata=grant.metadata,
                    created_at=grant.created_at,
                    updated_at=now,
                    is_jit=grant.is_jit,
                    jit_created_at=grant.jit_created_at,
                    jit_expires_at=grant.jit_expires_at,
                    jit_consumed_at=grant.jit_consumed_at,
                    one_shot=grant.one_shot,
                    usage_count=grant.usage_count,
                )
                await self._grant_repo.save(expired)
                expired_count += 1
        return expired_count
