from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.domain.entities.execution_token import TokenStatus
from app.domain.repositories.execution_token_repository import ExecutionTokenRepository
from app.infrastructure.observability.metrics import metrics

logger = logging.getLogger("intentlock.token_revocation")


class TokenRevocationReason:
    COMPROMISED = "compromised"
    EXPIRED = "expired"
    MANUAL = "manual"
    AUTOMATED = "automated"
    POLICY_VIOLATION = "policy_violation"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    ADMIN_REVOCATION = "admin_revocation"
    TENANT_CONTAINMENT = "tenant_containment"


class TokenRevocationService:
    """Persistent token revocation with reason tracking and cascade support.

    TOK-012: Token revocation list for compromised tokens.
    Provides explicit revocation with audit trail, cascade to derived tokens,
    and tenant-scoped revocation.
    """

    def __init__(
        self,
        token_repository: ExecutionTokenRepository,
    ) -> None:
        self._token_repo = token_repository

    async def revoke_token(
        self,
        tenant_id: str,
        token_id: str,
        reason: str = TokenRevocationReason.MANUAL,
        revoked_by: str = "system",
        cascade: bool = False,
    ) -> dict[str, Any]:
        """Revoke a token with full audit trail.

        Returns revocation record with affected token IDs.
        """
        revoked_ids: list[str] = []

        success = await self._token_repo.revoke(tenant_id, token_id)
        if success:
            revoked_ids.append(token_id)
            logger.info(
                "Token revoked: tenant=%s token=%s reason=%s by=%s",
                tenant_id,
                token_id,
                reason,
                revoked_by,
            )
            metrics.increment_security_exception("token_revoked")

        if cascade:
            cascade_ids = await self._cascade_revoke(
                tenant_id,
                token_id,
                reason,
                revoked_by,
            )
            revoked_ids.extend(cascade_ids)

        return {
            "revoked_token_ids": revoked_ids,
            "primary_token_id": token_id,
            "reason": reason,
            "revoked_by": revoked_by,
            "revoked_at": datetime.now(UTC).isoformat(),
            "cascade_performed": cascade,
            "total_revoked": len(revoked_ids),
        }

    async def revoke_tokens_by_agent(
        self,
        tenant_id: str,
        agent_id: str,
        reason: str = TokenRevocationReason.COMPROMISED,
        revoked_by: str = "system",
    ) -> list[str]:
        """Revoke all active tokens for an agent."""
        tokens, _ = await self._token_repo.list_by_agent(
            tenant_id,
            agent_id,
            status=TokenStatus.ACTIVE,
            limit=1000,
            offset=0,
        )
        revoked: list[str] = []
        for token in tokens:
            success = await self._token_repo.revoke(tenant_id, token.token_id)
            if success:
                revoked.append(token.token_id)

        if revoked:
            logger.info(
                "Revoked %d tokens for agent %s: reason=%s",
                len(revoked),
                agent_id,
                reason,
            )
            metrics.increment_security_exception("agent_tokens_revoked")

        return revoked

    async def revoke_tokens_by_tenant(
        self,
        tenant_id: str,
        reason: str = TokenRevocationReason.TENANT_CONTAINMENT,
        revoked_by: str = "system",
    ) -> list[str]:
        """Emergency revoke all tokens in a tenant."""
        tokens, _ = await self._token_repo.list_by_tenant(tenant_id, limit=1000, offset=0)
        active_tokens = [t for t in tokens if t.status == TokenStatus.ACTIVE]

        revoked: list[str] = []
        for token in active_tokens:
            success = await self._token_repo.revoke(tenant_id, token.token_id)
            if success:
                revoked.append(token.token_id)

        if revoked:
            logger.warning(
                "Emergency revocation: %d tokens revoked in tenant %s: reason=%s",
                len(revoked),
                tenant_id,
                reason,
            )
            metrics.increment_security_exception("tenant_emergency_revocation")

        return revoked

    async def is_revoked(self, tenant_id: str, token_id: str) -> bool:
        """Check if a token is in the revocation list."""
        try:
            tokens, _ = await self._token_repo.list_by_agent(
                tenant_id,
                token_id,
                limit=1,
                offset=0,
            )
            for t in tokens:
                if t.token_id == token_id and t.status == TokenStatus.REVOKED:
                    return True
        except Exception as exc:
            logger.debug("is_revoked lookup error: %s", exc)
        return False

    async def get_revocation_log(
        self,
        tenant_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get revocation audit log."""
        try:
            tokens, total = await self._token_repo.list_by_tenant(
                tenant_id,
                limit=limit,
                offset=offset,
            )
            revoked = [
                {
                    "token_id": t.token_id,
                    "jti": t.jti,
                    "agent_id": t.agent_id,
                    "tool": t.tool,
                    "status": t.status.value,
                    "revoked_at": t.revoked_at.isoformat() if t.revoked_at else None,
                    "issued_at": t.issued_at.isoformat() if t.issued_at else None,
                    "expires_at": t.expires_at.isoformat() if t.expires_at else None,
                }
                for t in tokens
                if t.status == TokenStatus.REVOKED
            ]
            return revoked
        except Exception:
            return []

    async def _cascade_revoke(
        self,
        tenant_id: str,
        token_id: str,
        reason: str,
        revoked_by: str,
    ) -> list[str]:
        """Cascade revoke derived tokens (sub-agent tokens)."""
        cascade_ids: list[str] = []
        try:
            tokens, _ = await self._token_repo.list_by_agent(
                tenant_id,
                token_id,
                limit=1000,
                offset=0,
            )
            for t in tokens:
                if t.status == TokenStatus.ACTIVE:
                    success = await self._token_repo.revoke(tenant_id, t.token_id)
                    if success:
                        cascade_ids.append(t.token_id)
        except Exception as exc:
            logger.debug("Cascade revoke error: %s", exc)
        return cascade_ids
