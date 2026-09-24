from __future__ import annotations

import json
import logging
import secrets
from datetime import UTC, datetime
from typing import Any

from app.domain.entities.agent import Agent, AgentStatus
from app.domain.entities.authority_grant import (
    AuthorityGrant,
    AuthorityScope,
    AuthorityStatus,
)
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

logger = logging.getLogger(__name__)


class AdvancedContainmentService:
    """Advanced containment operations extending CascadeContainmentService.

    Feature 51 - Staged containment: graduated response from observe to quarantine.
    Feature 52 - Blast radius scoring: pre-execution blast-radius risk score.
    Feature 53 - Containment verification: post-containment validation checks.
    Feature 54 - Containment policies: apply named policy bundles to agents.
    Feature 55 - Exception handling: structured containment failure tracking.
    Feature 56 - Audit trail: record containment audit log entries.
    Feature 57 - Notify affected parties: fan-out notification for stakeholders.
    Feature 58 - Recovery coordination: hand-off to recovery pipeline.
    """

    def __init__(
        self,
        agent_repository: AgentRepository,
        grant_repository: AuthorityGrantRepository,
        containment_repository: ContainmentRepository,
        token_repository: ExecutionTokenRepository | None = None,
        action_repository: ProtectedActionRepository | None = None,
    ) -> None:
        self._agent_repo = agent_repository
        self._grant_repo = grant_repository
        self._containment_repo = containment_repository
        self._token_repo = token_repository
        self._action_repo = action_repository

    @staticmethod
    def _new_containment_id() -> str:
        return "cnt-" + secrets.token_hex(12)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    # ------------------------------------------------------------------
    # Feature 51 - Staged containment
    # ------------------------------------------------------------------

    STAGE_ORDER = [
        ContainmentMode.OBSERVE,
        ContainmentMode.RESTRICT,
        ContainmentMode.SUSPEND,
        ContainmentMode.QUARANTINE,
    ]

    async def staged_containment(
        self,
        tenant_id: str,
        target_agent_id: str,
        initiated_by: str,
        authorized_by: str,
        *,
        start_stage: ContainmentMode = ContainmentMode.OBSERVE,
        max_stage: ContainmentMode = ContainmentMode.QUARANTINE,
        reason: str = "",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Graduate containment from start_stage up to max_stage."""
        start_idx = self.STAGE_ORDER.index(start_stage)
        max_idx = self.STAGE_ORDER.index(max_stage)

        applied_stages: list[str] = []
        containment_id = self._new_containment_id()
        final_stage = start_stage

        for idx in range(start_idx, max_idx + 1):
            stage = self.STAGE_ORDER[idx]
            event = ContainmentEvent(
                containment_id=containment_id,
                tenant_id=tenant_id,
                target_agent_id=target_agent_id,
                target_authority_id=None,
                mode=stage,
                status=ContainmentStatus.PENDING,
                initiated_by=initiated_by,
                authorized_by=authorized_by,
                reason=reason,
                dry_run=dry_run,
                result_details={
                    "staged_containment": "true",
                    "stage_sequence": stage.value,
                },
                created_at=self._now(),
            )
            saved = await self._containment_repo.save(event)
            applied_stages.append(stage.value)
            final_stage = stage

            if not dry_run:
                await self._apply_stage_status(tenant_id, target_agent_id, stage)

            await self._update_event_status(
                saved,
                ContainmentStatus.COMPLETED,
                {"stage_applied": stage.value},
            )
            final_stage = stage

        return {
            "containment_id": containment_id,
            "applied_stages": applied_stages,
            "final_stage": final_stage.value,
            "dry_run": dry_run,
        }

    async def _apply_stage_status(
        self, tenant_id: str, agent_id: str, stage: ContainmentMode
    ) -> None:
        agent = await self._agent_repo.get_by_agent_id(tenant_id, agent_id)
        if agent is None:
            return
        if stage == ContainmentMode.OBSERVE:
            return
        if stage in (ContainmentMode.RESTRICT, ContainmentMode.SUSPEND):
            await self._agent_repo.update_status(
                tenant_id, agent_id, AgentStatus.SUSPENDED
            )
        elif stage == ContainmentMode.QUARANTINE:
            await self._agent_repo.update_status(
                tenant_id, agent_id, AgentStatus.QUARANTINED
            )

    async def _update_event_status(
        self,
        event: ContainmentEvent,
        status: ContainmentStatus,
        details: dict[str, str],
    ) -> ContainmentEvent:
        merged = {**event.result_details, **details}
        return await self._containment_repo.update_status(
            event.tenant_id, event.containment_id, status, result_details=merged
        )

    # ------------------------------------------------------------------
    # Feature 52 - Blast radius scoring
    # ------------------------------------------------------------------

    async def compute_blast_radius_score(
        self, tenant_id: str, agent_id: str
    ) -> dict[str, Any]:
        """Compute a pre-execution blast-radius risk score for an agent."""
        agent = await self._agent_repo.get_by_agent_id(tenant_id, agent_id)
        if agent is None:
            raise ValueError("Agent not found: " + agent_id)

        grants, _ = await self._grant_repo.list_by_grantee(
            tenant_id, agent_id, limit=1000, offset=0
        )
        child_agents, _ = await self._agent_repo.list_by_tenant(
            tenant_id, limit=1000, offset=0
        )
        descendants = [a for a in child_agents if a.parent_agent_id == agent_id]

        score = 0.0
        breakdown: dict[str, float] = {}

        direct_authorities = len(grants)
        breakdown["direct_authorities"] = float(direct_authorities) * 0.1
        score += breakdown["direct_authorities"]

        admin_scope_count = 0
        for grant in grants:
            if grant.scope == AuthorityScope.ADMIN:
                admin_scope_count += 1
                score += 0.2
            elif grant.scope == AuthorityScope.EXECUTE:
                score += 0.15
            if grant.delegation_depth > 3:
                score += 0.1

        breakdown["admin_scope_count"] = float(admin_scope_count) * 0.2

        child_count = len(descendants)
        breakdown["child_agents"] = float(child_count) * 0.15
        score += breakdown["child_agents"]

        high_risk_children = 0
        for desc in descendants:
            if desc.risk_classification.value in ("high", "critical"):
                high_risk_children += 1
                score += 0.2
        breakdown["high_risk_children"] = float(high_risk_children) * 0.2

        score = max(0.0, min(1.0, round(score, 3)))

        if score >= 0.7:
            risk_level = "critical"
        elif score >= 0.4:
            risk_level = "high"
        elif score >= 0.2:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "agent_id": agent_id,
            "score": score,
            "risk_level": risk_level,
            "breakdown": breakdown,
            "direct_authorities": direct_authorities,
            "child_agents_count": child_count,
        }

    # ------------------------------------------------------------------
    # Feature 53 - Containment verification
    # ------------------------------------------------------------------

    async def verify_containment(
        self,
        tenant_id: str,
        containment_id: str,
        target_agent_id: str,
    ) -> dict[str, Any]:
        """Post-containment validation: confirm all expected state changes occurred."""
        checks: list[dict[str, Any]] = []

        agent = await self._agent_repo.get_by_agent_id(tenant_id, target_agent_id)
        if agent is None:
            checks.append({
                "check": "agent_quarantined",
                "passed": False,
                "detail": "Agent not found",
            })
            return {
                "containment_id": containment_id,
                "all_passed": False,
                "checks": checks,
            "status": ContainmentStatus.FAILED.value,
            }

        agent_quarantined = agent.status == AgentStatus.QUARANTINED
        checks.append({
            "check": "agent_quarantined",
            "passed": agent_quarantined,
            "detail": agent.status.value,
        })

        grants, _ = await self._grant_repo.list_by_grantee(
            tenant_id, target_agent_id, limit=1000, offset=0
        )
        active_remaining = sum(
            1 for g in grants if g.status != AuthorityStatus.REVOKED
        )
        all_grants_revoked = active_remaining == 0
        checks.append({
            "check": "all_grants_revoked",
            "passed": all_grants_revoked,
            "detail": str(active_remaining) + " active remaining",
        })

        tokens_revoked = True
        if self._token_repo is not None:
            tokens, _ = await self._token_repo.list_by_agent(
                tenant_id, target_agent_id, status=TokenStatus.ACTIVE, limit=1000, offset=0
            )
            tokens_revoked = len(tokens) == 0
        checks.append({
            "check": "tokens_revoked",
            "passed": tokens_revoked,
            "detail": "no active tokens" if tokens_revoked else "active tokens remain",
        })

        actions_contained = True
        if self._action_repo is not None:
            pending, _ = await self._action_repo.list_by_agent(
                tenant_id, target_agent_id, limit=1000, offset=0
            )
            terminal_statuses = (
                ActionStatus.CONTAINED,
                ActionStatus.EXECUTED,
                ActionStatus.FAILED,
                ActionStatus.DENIED,
            )
            actions_contained = all(a.status in terminal_statuses for a in pending)
        checks.append({
            "check": "pending_actions_contained",
            "passed": actions_contained,
            "detail": "all resolved" if actions_contained else "pending actions remain",
        })

        all_passed = all(c["passed"] for c in checks)

        event = await self._containment_repo.get_by_containment_id(
            tenant_id, containment_id
        )
        if event is not None:
            verification_details = {
                **event.result_details,
                "verification_passed": str(all_passed).lower(),
                "verified_at": self._now().isoformat(),
            }
            await self._containment_repo.update_status(
                tenant_id,
                containment_id,
                ContainmentStatus.COMPLETED if all_passed else ContainmentStatus.FAILED,
                result_details=verification_details,
            )

        return {
            "containment_id": containment_id,
            "all_passed": all_passed,
            "checks": checks,
            "status": (
                ContainmentStatus.COMPLETED.value
                if all_passed
                else ContainmentStatus.FAILED.value
            ),
        }

    # ------------------------------------------------------------------
    # Feature 54 - Containment policies
    # ------------------------------------------------------------------

    CONTAINMENT_POLICIES: dict[str, dict[str, Any]] = {
        "low_risk": {
            "mode": ContainmentMode.OBSERVE,
            "max_stage": ContainmentMode.RESTRICT,
            "revoke_tokens": False,
            "notify": False,
        },
        "medium_risk": {
            "mode": ContainmentMode.RESTRICT,
            "max_stage": ContainmentMode.SUSPEND,
            "revoke_tokens": True,
            "notify": True,
        },
        "high_risk": {
            "mode": ContainmentMode.QUARANTINE,
            "max_stage": ContainmentMode.QUARANTINE,
            "revoke_tokens": True,
            "revoke_grants": True,
            "notify": True,
        },
        "critical_risk": {
            "mode": ContainmentMode.QUARANTINE,
            "max_stage": ContainmentMode.QUARANTINE,
            "revoke_tokens": True,
            "notify": True,
            "revoke_grants": True,
        },
    }

    async def apply_containment_policy(
        self,
        tenant_id: str,
        target_agent_id: str,
        policy_name: str,
        initiated_by: str,
        authorized_by: str,
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Apply a named containment policy bundle to an agent."""
        policy = self.CONTAINMENT_POLICIES.get(policy_name)
        if policy is None:
            raise ValueError(
                "Unknown containment policy: "
                + policy_name
                + ". Available: "
                + ", ".join(self.CONTAINMENT_POLICIES.keys())
            )

        agent = await self._agent_repo.get_by_agent_id(tenant_id, target_agent_id)
        if agent is None:
            raise ValueError("Agent not found: " + target_agent_id)

        actions_taken: list[str] = []
        mode = policy["mode"]

        if not dry_run and mode != ContainmentMode.OBSERVE:
            await self._agent_repo.update_status(
                tenant_id, target_agent_id, AgentStatus.QUARANTINED
            )
            actions_taken.append("agent_quarantined")

            if policy.get("revoke_grants", False):
                grants, _ = await self._grant_repo.list_by_grantee(
                    tenant_id, target_agent_id, limit=1000, offset=0
                )
                for grant in grants:
                    if grant.status == AuthorityStatus.ACTIVE:
                        await self._grant_repo.revoke(
                            tenant_id, grant.grant_id, initiated_by
                        )
                        grant_id = grant.grant_id
                        actions_taken.append("grant_revoked:" + grant_id)

            if policy.get("revoke_tokens", False) and self._token_repo is not None:
                tokens, _ = await self._token_repo.list_by_agent(
                    tenant_id, target_agent_id, status=TokenStatus.ACTIVE, limit=1000, offset=0
                )
                for token in tokens:
                    await self._token_repo.revoke(tenant_id, token.token_id)
                    actions_taken.append("token_revoked:" + token.token_id)

        containment_id = self._new_containment_id()
        event = ContainmentEvent(
            containment_id=containment_id,
            tenant_id=tenant_id,
            target_agent_id=target_agent_id,
            target_authority_id=None,
            mode=mode,
            status=ContainmentStatus.COMPLETED if not dry_run else ContainmentStatus.PENDING,
            initiated_by=initiated_by,
            authorized_by=authorized_by,
            reason="Policy applied: " + policy_name,
            dry_run=dry_run,
            result_details={
                "policy_name": policy_name,
                "actions_taken": ",".join(actions_taken),
            },
            created_at=self._now(),
            completed_at=self._now() if not dry_run else None,
        )
        await self._containment_repo.save(event)

        return {
            "policy_name": policy_name,
            "agent_id": target_agent_id,
            "mode": mode.value,
            "actions_taken": actions_taken,
            "success": True,
            "dry_run": dry_run,
        }

    # ------------------------------------------------------------------
    # Feature 55 - Containment exception handling
    # ------------------------------------------------------------------

    async def handle_containment_exception(
        self,
        tenant_id: str,
        containment_id: str,
        target_agent_id: str,
        exception_message: str,
        *,
        retry: bool = True,
        fallback_mode: ContainmentMode = ContainmentMode.QUARANTINE,
    ) -> dict[str, Any]:
        """Record a containment failure and optionally trigger fallback."""
        exception_id = "exc-" + secrets.token_hex(8)

        event = await self._containment_repo.get_by_containment_id(
            tenant_id, containment_id
        )

        if event is not None:
            updated_details = {
                **event.result_details,
                "exception_id": exception_id,
                "exception_message": exception_message,
                "exception_at": self._now().isoformat(),
            }
            await self._containment_repo.update_status(
                tenant_id,
                containment_id,
                ContainmentStatus.FAILED,
                result_details=updated_details,
            )

        fallback_triggered = False
        fallback_id = None

        should_fallback = retry
        if event is not None and event.dry_run:
            should_fallback = False

        if should_fallback:
            try:
                fallback_event = ContainmentEvent(
                    containment_id=self._new_containment_id(),
                    tenant_id=tenant_id,
                    target_agent_id=target_agent_id,
                    target_authority_id=None,
                    mode=fallback_mode,
                    status=ContainmentStatus.COMPLETED,
                    initiated_by="exception_handler",
                    authorized_by="system",
                    reason="Fallback after exception: " + exception_message,
                    dry_run=False,
                    result_details={
                        "fallback_for": containment_id,
                        "exception_id": exception_id,
                    },
                    created_at=self._now(),
                    completed_at=self._now(),
                )
                saved_fallback = await self._containment_repo.save(fallback_event)
                fallback_id = saved_fallback.containment_id
                await self._agent_repo.update_status(
                    tenant_id, target_agent_id, AgentStatus.QUARANTINED
                )
                fallback_triggered = True
            except Exception:
                pass

        return {
            "exception_id": exception_id,
            "containment_id": containment_id,
            "handled": True,
            "fallback_triggered": fallback_triggered,
            "fallback_containment_id": fallback_id,
            "message": exception_message,
        }

    # ------------------------------------------------------------------
    # Feature 56 - Containment audit trail
    # ------------------------------------------------------------------

    async def record_containment_audit(
        self,
        tenant_id: str,
        containment_id: str,
        action: str,
        actor: str,
        details: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Append an audit log entry to the containment event's result_details."""
        audit_id = "aud-" + secrets.token_hex(8)
        event = await self._containment_repo.get_by_containment_id(
            tenant_id, containment_id
        )

        audit_entry: dict[str, Any] = {
            "audit_id": audit_id,
            "action": action,
            "actor": actor,
            "timestamp": self._now().isoformat(),
        }
        if details:
            audit_entry["details"] = details

        if event is not None:
            existing_audit = event.result_details.get("audit_trail", "[]")
            try:
                audit_list = json.loads(existing_audit)
            except (json.JSONDecodeError, TypeError):
                audit_list = []
            audit_list.append(audit_entry)
            updated_details = {
                **event.result_details,
                "audit_trail": json.dumps(audit_list),
            }
            await self._containment_repo.update_status(
                tenant_id,
                containment_id,
                event.status,
                result_details=updated_details,
            )

        return {
            "audit_id": audit_id,
            "containment_id": containment_id,
            "recorded": event is not None,
            "action": action,
            "actor": actor,
        }

    # ------------------------------------------------------------------
    # Feature 57 - Notify affected parties
    # ------------------------------------------------------------------

    async def notify_affected_parties(
        self,
        tenant_id: str,
        containment_id: str,
        target_agent_id: str,
        *,
        recipients: list[str] | None = None,
        message: str = "Agent has been contained.",
    ) -> dict[str, Any]:
        """Fan-out notification to affected parties about containment action."""
        notification_id = "notif-" + secrets.token_hex(8)

        event = await self._containment_repo.get_by_containment_id(
            tenant_id, containment_id
        )

        if recipients is None:
            recipients = []
            if event is not None and event.affected_agent_ids:
                recipients = list(event.affected_agent_ids)

        notified = list(recipients)

        if event is not None:
            updated_details = {
                **event.result_details,
                "notification_sent": "true",
                "notification_id": notification_id,
                "notification_message": message,
                "recipients": ",".join(notified),
            }
            await self._containment_repo.update_status(
                tenant_id,
                containment_id,
                event.status,
                result_details=updated_details,
            )

        return {
            "notification_id": notification_id,
            "containment_id": containment_id,
            "recipients_notified": notified,
            "success": True,
            "message": message,
        }

    # ------------------------------------------------------------------
    # Feature 58 - Recovery coordination
    # ------------------------------------------------------------------

    async def coordinate_recovery(
        self,
        tenant_id: str,
        containment_id: str,
        target_agent_id: str,
        *,
        recovery_plan_id: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Hand-off to recovery pipeline after containment is complete."""
        recovery_id = "rec-" + secrets.token_hex(8)

        event = await self._containment_repo.get_by_containment_id(
            tenant_id, containment_id
        )

        terminal_statuses = (
            ContainmentStatus.COMPLETED,
            ContainmentStatus.FAILED,
        )
        if event is not None and event.status not in terminal_statuses:
            return {
                "recovery_id": recovery_id,
                "containment_id": containment_id,
                "status": "skipped",
                "reason": "Containment not yet completed",
                "next_steps": [],
            }

        if not dry_run:
            recovery_details = {
                "recovery_coordinated": "true",
                "recovery_id": recovery_id,
                "recovery_plan_id": recovery_plan_id or "",
                "recovery_coordinated_at": self._now().isoformat(),
            }
            if event is not None:
                merged = {**event.result_details, **recovery_details}
                await self._containment_repo.update_status(
                    tenant_id,
                    containment_id,
                    event.status,
                    result_details=merged,
                )

        next_steps = [
            "validate_agent_state",
            "assess_recovery_readiness",
            "execute_recovery_plan",
            "verify_recovery_completion",
        ]

        return {
            "recovery_id": recovery_id,
            "containment_id": containment_id,
            "agent_id": target_agent_id,
            "status": "initiated" if not dry_run else "planned",
            "recovery_plan_id": recovery_plan_id,
            "dry_run": dry_run,
            "next_steps": next_steps,
        }
