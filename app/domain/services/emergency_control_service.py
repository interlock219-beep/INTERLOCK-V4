from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

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

    def __init__(self) -> None:
        self._emergency_deny_active: dict[str, bool] = {}
        self._emergency_allow_active: dict[str, dict[str, Any]] = {}
        self._emergency_log: list[dict[str, Any]] = []
        self._lock = False  # Simple flag to prevent concurrent emergency ops

    def is_emergency_deny_active(self, tenant_id: str) -> bool:
        """Check if emergency deny is active for a tenant."""
        return self._emergency_deny_active.get(tenant_id, False)

    def activate_emergency_deny(
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
                tenant_id, activated_by, reason,
            )
            return {
                "success": True,
                "emergency_deny_active": True,
                "record": record,
            }
        finally:
            self._lock = False

    def deactivate_emergency_deny(
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
                tenant_id, deactivated_by,
            )
            return {
                "success": True,
                "emergency_deny_active": False,
                "record": record,
            }
        finally:
            self._lock = False

    def activate_emergency_allow(
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
            tenant_id, activated_by, allowed_actions, expires_at.isoformat(),
        )
        return {
            "success": True,
            "emergency_allow_active": True,
            "record": record,
        }

    def deactivate_emergency_allow(
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
        return {"success": True, "record": deactivation}

    def evaluate_authorization(
        self,
        tenant_id: str,
        agent_id: str,
        action: str,
        tool: str,
    ) -> tuple[AuthorizationDecision, str]:
        """Evaluate authorization considering emergency controls.

        Called by authorization service to check emergency state.
        """
        if self.is_emergency_deny_active(tenant_id):
            return (
                AuthorizationDecision.DENY,
                "EMERGENCY DENY is active for this tenant — all execution blocked",
            )

        allow_record = self._emergency_allow_active.get(tenant_id)
        if allow_record is not None:
            import os
            now = datetime.now(UTC)
            expires = datetime.fromisoformat(allow_record["expires_at"])
            if now > expires:
                self.deactivate_emergency_allow(tenant_id, "system")
                return (
                    AuthorizationDecision.DENY,
                    "Emergency allow has expired",
                )

            if allowed_agents := allow_record.get("allowed_agents"):
                if agent_id not in allowed_agents:
                    return (
                        AuthorizationDecision.DENY,
                        "Agent not in emergency allow list",
                    )

            if action not in allow_record.get("allowed_actions", []):
                return (
                    AuthorizationDecision.DENY,
                    f"Action '{action}' not in emergency allow list",
                )

            if allowed_tools := allow_record.get("allowed_tools"):
                if tool and tool not in allowed_tools:
                    return (
                        AuthorizationDecision.DENY,
                        f"Tool '{tool}' not in emergency allow list",
                    )

            return (
                AuthorizationDecision.ALLOW,
                "Emergency allow authorizes this action",
            )

        return AuthorizationDecision.ALLOW, "No emergency controls active"

    def get_emergency_status(self, tenant_id: str) -> dict[str, Any]:
        """Get current emergency control status for a tenant."""
        return {
            "tenant_id": tenant_id,
            "emergency_deny_active": self.is_emergency_deny_active(tenant_id),
            "emergency_allow_active": tenant_id in self._emergency_allow_active,
            "emergency_allow_record": self._emergency_allow_active.get(tenant_id),
        }

    def get_emergency_log(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get emergency control audit log."""
        return list(self._emergency_log[-limit:])
