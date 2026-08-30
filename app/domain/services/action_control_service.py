from __future__ import annotations

from typing import Any

from app.domain.models.intent import AgentActionDAG
from app.domain.services.authorization_service import AuthorizationService
from app.domain.services.central_policy_engine import CentralPolicyEngine
from app.domain.services.risk_engine import RiskEngine
from app.domain.value_objects.authorization_decision import AuthorizationDecision
from app.infrastructure.config.settings import get_settings


class ActionControlService:
    """Protected action evaluation pipeline.

    Reuses existing policy engine and authorization service.
    Adds authority validation and risk evaluation.
    """

    def __init__(
        self,
        authorization_service: AuthorizationService,
        policy_engine: CentralPolicyEngine,
        risk_engine: RiskEngine,
    ) -> None:
        self._authz_service = authorization_service
        self._policy_engine = policy_engine
        self._risk_engine = risk_engine

    def evaluate_protected_action(
        self,
        context: Any,
        agent_action: AgentActionDAG,
        *,
        authority_grants: list[dict[str, Any]] | None = None,
        recent_actions: list[dict[str, Any]] | None = None,
        agent_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        auth_context = context
        tenant_decision = self._check_tenant(auth_context)
        if tenant_decision != AuthorizationDecision.ALLOW:
            return {"decision": tenant_decision.value, "reason": self._tenant_reason(auth_context)}

        agent_decision = self._check_agent(auth_context)
        if agent_decision != AuthorizationDecision.ALLOW:
            return {"decision": agent_decision.value, "reason": "Missing agent identity"}

        auth_decision, auth_reason = self._authz_service.authorize(auth_context)
        if auth_decision != AuthorizationDecision.ALLOW:
            return {"decision": auth_decision.value, "reason": auth_reason}

        authority_decision = self._check_authority(auth_context, authority_grants or [])
        if authority_decision != AuthorizationDecision.ALLOW:
            return {"decision": authority_decision.value, "reason": "Insufficient authority"}

        policy_result = self._policy_engine.evaluate(auth_context)
        if policy_result.effect != AuthorizationDecision.ALLOW:
            return {
                "decision": policy_result.effect.value,
                "reason": policy_result.reason,
                "policy_version": policy_result.rule_version,
            }

        risk_result = self._risk_engine.evaluate(
            auth_context,
            agent_history=agent_history or [],
            authority_grants=authority_grants or [],
            recent_actions=recent_actions or [],
        )
        if risk_result["decision"] == AuthorizationDecision.DENY.value:
            return {
                "decision": AuthorizationDecision.DENY.value,
                "reason": f"Risk evaluation denied: {'; '.join(risk_result['explanations'])}",
                "risk_score": risk_result["score"],
                "risk_signals": risk_result["signals"],
            }
        if risk_result["decision"] == AuthorizationDecision.REQUIRE_HITL.value:
            return {
                "decision": AuthorizationDecision.REQUIRE_HITL.value,
                "reason": (
                    f"Risk evaluation requires approval: "
                    f"{'; '.join(risk_result['explanations'])}"
                ),
                "risk_score": risk_result["score"],
                "risk_signals": risk_result["signals"],
            }

        return {
            "decision": AuthorizationDecision.ALLOW.value,
            "reason": "Authorized",
            "risk_score": risk_result["score"],
            "risk_signals": risk_result["signals"],
        }

    @staticmethod
    def _check_tenant(context: Any) -> AuthorizationDecision:
        require_tenant = getattr(get_settings(), "authorization_require_tenant", False)
        if not require_tenant:
            return AuthorizationDecision.ALLOW
        if not getattr(context, "tenant_id", None):
            return AuthorizationDecision.DENY
        return AuthorizationDecision.ALLOW

    @staticmethod
    def _check_agent(context: Any) -> AuthorizationDecision:
        if not getattr(context, "agent_id", None):
            return AuthorizationDecision.DENY
        return AuthorizationDecision.ALLOW

    @staticmethod
    def _check_authority(context: Any, grants: list[dict[str, Any]]) -> AuthorizationDecision:
        if not grants:
            return AuthorizationDecision.DENY
        now = __import__("datetime").datetime.now(__import__("datetime").UTC)
        for grant in grants:
            expires = grant.get("expires_at")
            if expires:
                if isinstance(expires, str):
                    try:
                        expires = __import__("datetime").datetime.fromisoformat(expires)
                    except ValueError:
                        continue
                if expires < now:
                    continue
            return AuthorizationDecision.ALLOW
        return AuthorizationDecision.DENY

    @staticmethod
    def _tenant_reason(context: Any) -> str:
        if not getattr(context, "tenant_id", None):
            return "Missing tenant identity"
        return "Invalid tenant identity"
