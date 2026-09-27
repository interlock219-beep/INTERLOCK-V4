from __future__ import annotations

import logging
from typing import Any

from app.domain.entities.authority_grant import AuthorityGrant, AuthorityScope
from app.domain.services.authority_lineage_service import AuthorityLineageService
from app.domain.services.authorization_service import AuthorizationService
from app.domain.value_objects.authorization_context import AuthorizationContext
from app.domain.value_objects.authorization_decision import AuthorizationDecision

logger = logging.getLogger(__name__)


class AdvancedAuthorizationService:
    """Orchestrates advanced authorization checks."""

    def __init__(
        self,
        authorization_service: AuthorizationService,
        authority_service: AuthorityLineageService,
    ):
        self._authz = authorization_service
        self._authority = authority_service

    def authorize_with_advanced_checks(
        self, context: AuthorizationContext
    ) -> tuple[AuthorizationDecision, str]:
        """Run full authorization with all advanced checks."""
        return self._authz.authorize(context)

    async def provision_jit_authority(
        self,
        context: AuthorizationContext,
        scope: str | AuthorityScope,
        resource: str,
        ttl_seconds: int = 300,
    ) -> AuthorityGrant:
        """Provision JIT authority for the agent."""
        from app.domain.entities.authority_grant import AuthorityScope

        return self._authority.create_jit_authority(
            context.tenant_id or "default",
            context.agent_id,
            context.agent_id,
            AuthorityScope(scope) if isinstance(scope, str) else scope,
            resource,
            ttl_seconds=ttl_seconds,
        )

    async def validate_authority_chain(self, tenant_id: str, grant_id: str) -> dict[str, Any]:
        """Validate full authority chain for consistency."""
        return await self._authority.validate_chain_consistency(tenant_id, grant_id)
