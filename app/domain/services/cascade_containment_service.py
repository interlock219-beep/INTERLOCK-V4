from __future__ import annotations

import logging
import secrets
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities.agent import Agent, AgentStatus
from app.domain.entities.authority_grant import AuthorityGrant, AuthorityStatus
from app.domain.entities.containment_event import (
    ContainmentEvent,
    ContainmentMode,
    ContainmentStatus,
)
from app.domain.entities.execution_token import TokenStatus
from app.domain.entities.protected_action import ActionStatus
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.authority_grant_repository import AuthorityGrantRepository
from app.domain.repositories.containment_repository import ContainmentRepository
from app.domain.repositories.execution_token_repository import ExecutionTokenRepository
from app.domain.repositories.protected_action_repository import ProtectedActionRepository
from app.infrastructure.logging.audit_logger import log_security_event
from app.infrastructure.observability.metrics import metrics
from app.infrastructure.persistence.models.approval_request_model import ApprovalRequestModel

logger = logging.getLogger(__name__)


class CascadeContainmentService:
    """Automatic cascade containment for compromised agents and authority trees."""

    def __init__(
        self,
        agent_repository: AgentRepository,
        grant_repository: AuthorityGrantRepository,
        containment_repository: ContainmentRepository,
        action_repository: ProtectedActionRepository | None = None,
        token_repository: ExecutionTokenRepository | None = None,
    ) -> None:
        self._agent_repo = agent_repository
        self._grant_repo = grant_repository
        self._containment_repo = containment_repository
        self._action_repo = action_repository
        self._token_repo = token_repository

    async def contain_authority_tree(
        self,
        tenant_id: str,
        target_agent_id: str,
        mode: ContainmentMode,
        initiated_by: str,
        authorized_by: str,
        *,
        reason: str = "",
        dry_run: bool = False,
        target_authority_id: str | None = None,
    ) -> ContainmentEvent:
        containment_id = f"cnt-{secrets.token_hex(12)}"
        affected_agents: list[str] = []
        affected_authorities: list[str] = []
        affected_tokens: list[str] = []
        affected_actions: list[str] = []
        affected_sessions: list[str] = []

        if not dry_run:
            agent = await self._agent_repo.get_by_agent_id(tenant_id, target_agent_id)
            if agent is None:
                raise ValueError("Target agent not found")
            await self._agent_repo.update_status(
                tenant_id, target_agent_id, AgentStatus.QUARANTINED
            )
            affected_agents.append(target_agent_id)

            grants, _ = await self._grant_repo.list_by_grantee(
                tenant_id, target_agent_id, limit=1000, offset=0
            )
            for grant in grants:
                if grant.status == AuthorityStatus.ACTIVE:
                    await self._grant_repo.revoke(tenant_id, grant.grant_id, initiated_by)
                    affected_authorities.append(grant.grant_id)

            child_agents, _ = await self._agent_repo.list_by_tenant(
                tenant_id, limit=1000, offset=0
            )
            for child in child_agents:
                if child.parent_agent_id == target_agent_id:
                    await self._agent_repo.update_status(
                        tenant_id, child.agent_id, AgentStatus.QUARANTINED
                    )
                    affected_agents.append(child.agent_id)
                    child_grants, _ = await self._grant_repo.list_by_grantee(
                        tenant_id, child.agent_id, limit=1000, offset=0
                    )
                    for grant in child_grants:
                        if grant.status == AuthorityStatus.ACTIVE:
                            await self._grant_repo.revoke(
                                tenant_id, grant.grant_id, initiated_by
                            )
                            affected_authorities.append(grant.grant_id)

            if self._token_repo is not None:
                tokens, _ = await self._token_repo.list_by_agent(
                    tenant_id, target_agent_id, status=TokenStatus.ACTIVE, limit=1000, offset=0
                )
                for token in tokens:
                    await self._token_repo.revoke(tenant_id, token.token_id)
                    affected_tokens.append(token.token_id)

            if self._action_repo is not None:
                pending_actions, _ = await self._action_repo.list_by_agent(
                    tenant_id, target_agent_id, limit=1000, offset=0
                )
                for action in pending_actions:
                    if action.status in (ActionStatus.PENDING, ActionStatus.EVALUATING):
                        await self._action_repo.update_status(
                            tenant_id, action.action_id, ActionStatus.CONTAINED
                        )
                        affected_actions.append(action.action_id)

            if agent.owner_user_id is not None:
                try:
                    with self._get_db_session() as session:
                        stmt = select(ApprovalRequestModel).where(
                            ApprovalRequestModel.tenant_id == tenant_id,
                            ApprovalRequestModel.user_id == agent.owner_user_id,
                            ApprovalRequestModel.status == "pending",
                        )
                        for model in session.scalars(stmt).all():
                            affected_sessions.append(model.request_id)
                except Exception as exc:
                    logger.debug("Failed to load affected sessions: %s", exc)

        result_details: dict[str, str] = {
            "mode": mode.value,
            "target_agent_id": target_agent_id,
        }
        if target_authority_id:
            result_details["target_authority_id"] = target_authority_id
        result_details["dry_run"] = str(dry_run).lower()
        result_details["affected_agents_count"] = str(len(affected_agents))
        result_details["affected_authorities_count"] = str(len(affected_authorities))
        result_details["affected_tokens_count"] = str(len(affected_tokens))
        result_details["affected_actions_count"] = str(len(affected_actions))
        result_details["affected_sessions_count"] = str(len(affected_sessions))

        event = ContainmentEvent(
            containment_id=containment_id,
            tenant_id=tenant_id,
            target_agent_id=target_agent_id,
            target_authority_id=target_authority_id,
            mode=mode,
            status=ContainmentStatus.COMPLETED if not dry_run else ContainmentStatus.PENDING,
            initiated_by=initiated_by,
            authorized_by=authorized_by,
            reason=reason,
            affected_agent_ids=affected_agents,
            affected_authority_ids=affected_authorities,
            affected_session_ids=affected_sessions,
            affected_token_ids=affected_tokens,
            affected_action_ids=affected_actions,
            dry_run=dry_run,
            result_details=result_details,
            created_at=datetime.now(UTC),
            completed_at=datetime.now(UTC) if not dry_run else None,
        )
        saved = await self._containment_repo.save(event)
        log_security_event(
            "containment_executed",
            tenant_id=tenant_id,
            containment_id=containment_id,
            target_agent_id=target_agent_id,
            mode=mode.value,
            dry_run=str(dry_run).lower(),
        )
        metrics.increment_security_exception("containment_executed")
        return saved

    async def contain_execution_tokens(
        self, tenant_id: str, agent_id: str, *, dry_run: bool = False
    ) -> list[str]:
        if self._token_repo is None:
            return []
        tokens, _ = await self._token_repo.list_by_agent(
            tenant_id, agent_id, status=TokenStatus.ACTIVE, limit=1000, offset=0
        )
        revoked: list[str] = []
        for token in tokens:
            if not dry_run:
                await self._token_repo.revoke(tenant_id, token.token_id)
            revoked.append(token.token_id)
        return revoked

    async def contain_pending_actions(
        self, tenant_id: str, agent_id: str, *, dry_run: bool = False
    ) -> list[str]:
        if self._action_repo is None:
            return []
        actions, _ = await self._action_repo.list_by_agent(
            tenant_id, agent_id, limit=1000, offset=0
        )
        contained: list[str] = []
        for action in actions:
            if action.status in (ActionStatus.PENDING, ActionStatus.EVALUATING):
                if not dry_run:
                    await self._action_repo.update_status(
                        tenant_id, action.action_id, ActionStatus.CONTAINED
                    )
                contained.append(action.action_id)
        return contained

    async def get_blast_radius(self, tenant_id: str, agent_id: str) -> dict[str, Any]:
        agent = await self._agent_repo.get_by_agent_id(tenant_id, agent_id)
        if agent is None:
            raise ValueError("Agent not found")
        grants, _ = await self._grant_repo.list_by_grantee(
            tenant_id, agent_id, limit=1000, offset=0
        )
        child_agents, _ = await self._agent_repo.list_by_tenant(tenant_id, limit=1000, offset=0)
        descendants = [a for a in child_agents if a.parent_agent_id == agent_id]
        descendant_ids = [d.agent_id for d in descendants]
        resources: dict[str, list[str]] = {}
        for grant in grants:
            resources.setdefault(grant.resource, [])
            if grant.grantee_agent_id not in resources[grant.resource]:
                resources[grant.resource].append(grant.grantee_agent_id)

        active_sessions: list[dict[str, Any]] = []
        active_tokens: list[dict[str, Any]] = []
        pending_approvals: list[dict[str, Any]] = []
        pending_actions: list[dict[str, Any]] = []

        if agent.owner_user_id is not None:
            try:
                with self._get_db_session() as session:
                    from app.infrastructure.persistence.models.identity_models import (
                        UserSessionModel,
                    )

                    session_stmt = select(UserSessionModel).where(
                        UserSessionModel.user_id == agent.owner_user_id,
                        UserSessionModel.revoked == False,  # noqa: E712
                    )
                    for model in session.scalars(session_stmt).all():
                        active_sessions.append({
                            "session_id": model.session_id,
                            "device_info": model.device_info,
                            "ip_address": model.ip_address,
                            "created_at": model.created_at.isoformat(),
                        })
            except Exception as exc:
                logger.debug("Failed to load active sessions: %s", exc)

            try:
                with self._get_db_session() as session:
                    approval_stmt = select(ApprovalRequestModel).where(
                        ApprovalRequestModel.tenant_id == tenant_id,
                        ApprovalRequestModel.user_id == agent.owner_user_id,
                        ApprovalRequestModel.status == "pending",
                    )
                    approval_models = cast(
                        list[ApprovalRequestModel],
                        list(session.execute(approval_stmt).scalars().all()),
                    )
                    for approval_model in approval_models:
                        pending_approvals.append({
                            "request_id": approval_model.request_id,
                            "risk_score": approval_model.risk_score,
                            "status": approval_model.status,
                            "created_at": approval_model.created_at.isoformat(),
                        })
            except Exception as exc:
                logger.debug("Failed to load pending approvals: %s", exc)

        if self._token_repo is not None:
            tokens, _ = await self._token_repo.list_by_agent(
                tenant_id, agent_id, status=TokenStatus.ACTIVE, limit=1000, offset=0
            )
            for token in tokens:
                active_tokens.append({
                    "token_id": token.token_id,
                    "jti": token.jti,
                    "tool": token.tool,
                    "issued_at": token.issued_at.isoformat(),
                    "expires_at": token.expires_at.isoformat() if token.expires_at else None,
                })

        if self._action_repo is not None:
            actions, _ = await self._action_repo.list_by_agent(
                tenant_id, agent_id, limit=1000, offset=0
            )
            for action in actions:
                if action.status in (ActionStatus.PENDING, ActionStatus.EVALUATING):
                    pending_actions.append({
                        "action_id": action.action_id,
                        "tool": action.tool,
                        "resource": action.resource,
                        "action_type": action.action_type,
                        "status": action.status.value,
                        "created_at": action.created_at.isoformat(),
                    })

        return {
            "agent_id": agent_id,
            "status": agent.status.value,
            "risk_classification": agent.risk_classification.value,
            "direct_authorities": len(grants),
            "child_agents": descendant_ids,
            "child_agents_count": len(descendant_ids),
            "affected_resources": resources,
            "blast_radius_score": self._compute_blast_radius(grants, descendants),
            "active_sessions": active_sessions,
            "active_sessions_count": len(active_sessions),
            "active_execution_tokens": active_tokens,
            "active_execution_tokens_count": len(active_tokens),
            "pending_approvals": pending_approvals,
            "pending_approvals_count": len(pending_approvals),
            "pending_actions": pending_actions,
            "pending_actions_count": len(pending_actions),
        }

    @staticmethod
    def _compute_blast_radius(grants: list[AuthorityGrant], descendants: list[Agent]) -> float:
        score = 0.0
        score += len(grants) * 0.1
        for grant in grants:
            if grant.scope.value in ("admin", "execute"):
                score += 0.2
            if grant.delegation_depth > 3:
                score += 0.1
        score += len(descendants) * 0.15
        for desc in descendants:
            if desc.risk_classification.value in ("high", "critical"):
                score += 0.2
        return max(0.0, min(1.0, round(score, 3)))

    @staticmethod
    def _get_db_session() -> AbstractContextManager[Session]:
        from app.infrastructure.persistence.database import get_db_session

        return get_db_session()
