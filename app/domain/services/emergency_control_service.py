from __future__ import annotations

import json
import logging
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from app.domain.repositories.emergency_state_repository import EmergencyStateRepository
from app.domain.value_objects.authorization_decision import AuthorizationDecision
from app.infrastructure.observability.metrics import metrics

logger = logging.getLogger("intentlock.emergency_control")


class EmergencyControlService:
    """Emergency deny/allow controls with explicit safety gates.

    AUTH-030: Emergency deny all for tenant
    AUTH-031: Emergency allow with explicit controls

    Emergency deny immediately blocks all execution for a tenant.
    Emergency allow enables controlled execution with explicit controls,
    audit trail, automatic expiration, and mandatory approval.
    """

    def __init__(self, emergency_state_repository: EmergencyStateRepository | None = None) -> None:
        self._repository = emergency_state_repository
        self._emergency_deny_active: dict[str, bool] = {}
        self._emergency_allow_active: dict[str, dict[str, Any]] = {}
        self._emergency_log: list[dict[str, Any]] = []
        self._lock = False

    async def _ensure_loaded(self, tenant_id: str) -> None:
        if tenant_id in self._emergency_deny_active or tenant_id in self._emergency_allow_active:
            return
        if self._repository is None:
            return
        model = await self._repository.get_by_tenant(tenant_id)
        if model is None:
            return
        self._emergency_deny_active[tenant_id] = model.emergency_deny_active
        if model.emergency_allow_active and model.allow_details:
            with suppress(ValueError, TypeError):
                self._emergency_allow_active[tenant_id] = json.loads(model.allow_details)

    async def _persist(self, tenant_id: str) -> None:
        if self._repository is None:
            return
        from app.infrastructure.persistence.models.emergency_state_model import EmergencyStateModel

        model = EmergencyStateModel(
            tenant_id=tenant_id,
            emergency_deny_active=self._emergency_deny_active.get(tenant_id, False),
            emergency_allow_active=tenant_id in self._emergency_allow_active,
            allow_details=json.dumps(self._emergency_allow_active[tenant_id])
            if tenant_id in self._emergency_allow_active
            else None,
        )
        existing = await self._repository.get_by_tenant(tenant_id)
        if existing is not None:
            model.id = existing.id
            model.activated_by = existing.activated_by
            model.activated_at = existing.activated_at
            model.deactivated_by = existing.deactivated_by
            model.deactivated_at = existing.deactivated_at
            model.reason = existing.reason
            model.approval_ids = existing.approval_ids
            model.affected_sessions = existing.affected_sessions
        await self._repository.upsert(model)

    async def is_emergency_deny_active(self, tenant_id: str) -> bool:
        """Check if emergency deny is active for a tenant."""
        await self._ensure_loaded(tenant_id)
        return self._emergency_deny_active.get(tenant_id, False)

    async def activate_emergency_deny(
        self,
        tenant_id: str,
        activated_by: str,
        reason: str = "",
        approval_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Activate emergency deny for a tenant.

        BLOCKS all execution. Requires explicit approval tracking.
        """
        if self._lock:
            return {
                "success": False,
                "error": "Emergency control is locked; another operation in progress",
            }

        self._lock = True
        try:
            await self._ensure_loaded(tenant_id)
            self._emergency_deny_active[tenant_id] = True
            record = {
                "tenant_id": tenant_id,
                "action": "emergency_deny_activate",
                "activated_by": activated_by,
                "reason": reason,
                "approval_ids": approval_ids or [],
                "activated_at": datetime.now(UTC).isoformat(),
                "affected_sessions": [],
            }
            self._emergency_log.append(record)
            metrics.increment_security_exception("emergency_deny_activated")
            logger.warning(
                "EMERGENCY DENY activated for tenant %s by %s: reason=%s",
                tenant_id,
                activated_by,
                reason,
            )
            await self._persist(tenant_id)
            return {
                "success": True,
                "emergency_deny_active": True,
                "record": record,
            }
        finally:
            self._lock = False

    async def deactivate_emergency_deny(
        self,
        tenant_id: str,
        deactivated_by: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """Deactivate emergency deny. Requires explicit deactivation."""
        if self._lock:
            return {
                "success": False,
                "error": "Emergency control is locked",
            }

        self._lock = True
        try:
            await self._ensure_loaded(tenant_id)
            was_active = self._emergency_deny_active.get(tenant_id, False)
            self._emergency_deny_active[tenant_id] = False
            record = {
                "tenant_id": tenant_id,
                "action": "emergency_deny_deactivate",
                "deactivated_by": deactivated_by,
                "reason": reason,
                "was_active": was_active,
                "deactivated_at": datetime.now(UTC).isoformat(),
            }
            self._emergency_log.append(record)
            metrics.increment_security_exception("emergency_deny_deactivated")
            logger.info(
                "EMERGENCY DENY deactivated for tenant %s by %s",
                tenant_id,
                deactivated_by,
            )
            await self._persist(tenant_id)
            return {
                "success": True,
                "emergency_deny_active": False,
                "record": record,
            }
        finally:
            self._lock = False

    async def activate_emergency_allow(
        self,
        tenant_id: str,
        activated_by: str,
        allowed_actions: list[str],
        allowed_tools: list[str] | None = None,
        allowed_agents: list[str] | None = None,
        expires_at: datetime | None = None,
        approval_ids: list[str] | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        """Emergency allow with explicit controls.

        REQUIRES:
        - Explicit action list (no wildcards)
        - Time-limited (expires_at required)
        - Approval tracking
        - Audit trail
        """
        if not allowed_actions:
            return {
                "success": False,
                "error": "Emergency allow requires explicit allowed_actions list",
            }
        if expires_at is None:
            return {
                "success": False,
                "error": "Emergency allow requires expires_at (time-limited)",
            }
        if expires_at <= datetime.now(UTC):
            return {
                "success": False,
                "error": "Emergency allow expires_at must be in the future",
            }

        record = {
            "tenant_id": tenant_id,
            "action": "emergency_allow_activate",
            "activated_by": activated_by,
            "allowed_actions": allowed_actions,
            "allowed_tools": allowed_tools or [],
            "allowed_agents": allowed_agents or [],
            "expires_at": expires_at.isoformat(),
            "approval_ids": approval_ids or [],
            "reason": reason,
            "activated_at": datetime.now(UTC).isoformat(),
        }
        self._emergency_allow_active[tenant_id] = record
        self._emergency_log.append(record)
        metrics.increment_security_exception("emergency_allow_activated")
        logger.warning(
            "EMERGENCY ALLOW activated for tenant %s by %s: actions=%s expires=%s",
            tenant_id,
            activated_by,
            allowed_actions,
            expires_at.isoformat(),
        )
        await self._persist(tenant_id)
        return {
            "success": True,
            "emergency_allow_active": True,
            "record": record,
        }

    async def deactivate_emergency_allow(
        self,
        tenant_id: str,
        deactivated_by: str,
    ) -> dict[str, Any]:
        """Deactivate emergency allow."""
        record = self._emergency_allow_active.pop(tenant_id, None)
        if record is None:
            return {"success": False, "error": "No emergency allow active"}

        deactivation = {
            "tenant_id": tenant_id,
            "action": "emergency_allow_deactivate",
            "deactivated_by": deactivated_by,
            "original_activated_at": record.get("activated_at"),
            "deactivated_at": datetime.now(UTC).isoformat(),
        }
        self._emergency_log.append(deactivation)
        metrics.increment_security_exception("emergency_allow_deactivated")
        await self._persist(tenant_id)
        return {"success": True, "record": deactivation}

    async def evaluate_authorization(
        self,
        tenant_id: str,
        agent_id: str,
        action: str,
        tool: str,
    ) -> tuple[AuthorizationDecision, str]:
        """Evaluate authorization considering emergency controls.

        Called by authorization service to check emergency state.
        """
        if await self.is_emergency_deny_active(tenant_id):
            return (
                AuthorizationDecision.DENY,
                "EMERGENCY DENY is active for this tenant — all execution blocked",
            )

        await self._ensure_loaded(tenant_id)
        allow_record = self._emergency_allow_active.get(tenant_id)
        if allow_record is None:
            return (
                AuthorizationDecision.ALLOW,
                "No emergency controls active",
            )

        now = datetime.now(UTC)
        expires = datetime.fromisoformat(allow_record["expires_at"])
        if now > expires:
            await self.deactivate_emergency_allow(tenant_id, "system")
            return (
                AuthorizationDecision.DENY,
                "Emergency allow has expired",
            )

        allowed_agents = allow_record.get("allowed_agents")
        if allowed_agents and agent_id not in allowed_agents:
            return (
                AuthorizationDecision.DENY,
                "Agent not in emergency allow list",
            )

        if action not in allow_record.get("allowed_actions", []):
            return (
                AuthorizationDecision.DENY,
                f"Action '{action}' not in emergency allow list",
            )

        allowed_tools_list = allow_record.get("allowed_tools")
        if allowed_tools_list and tool and tool not in allowed_tools_list:
            return (
                AuthorizationDecision.DENY,
                f"Tool '{tool}' not in emergency allow list",
            )

        return (
            AuthorizationDecision.ALLOW,
            "Emergency allow authorizes this action",
        )

    async def get_emergency_status(self, tenant_id: str) -> dict[str, Any]:
        """Get current emergency control status for a tenant."""
        await self._ensure_loaded(tenant_id)
        return {
            "tenant_id": tenant_id,
            "emergency_deny_active": await self.is_emergency_deny_active(tenant_id),
            "emergency_allow_active": tenant_id in self._emergency_allow_active,
            "emergency_allow_record": self._emergency_allow_active.get(tenant_id),
        }

    def get_emergency_log(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get emergency control audit log."""
        return list(self._emergency_log[-limit:])
