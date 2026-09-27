from __future__ import annotations

import fnmatch
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from app.domain.services.risk_engine import RiskEngine
from app.domain.value_objects.authorization_context import AgentEnvironment, AuthorizationContext
from app.domain.value_objects.authorization_decision import AuthorizationDecision
from app.infrastructure.config.settings import get_settings


class AuthorizationService:
    """Explicit identity-based authorization service.

    Evaluates agent, user, tool, action, resource, service, and tenant
    identities to produce a deterministic ALLOW / DENY / REQUIRE_HITL
    decision.  Supports default-deny posture and role-based permission
    enforcement for high-assurance deployments.
    """

    def __init__(self, settings: Any | None = None) -> None:
        self._settings = settings or get_settings()

    def authorize(self, context: AuthorizationContext) -> tuple[AuthorizationDecision, str]:
        """Return an explicit authorization decision and reason.

        The decision is deterministic and auditable.  Checks are ordered
        from most restrictive to least restrictive so that the strongest
        applicable rule wins.
        """
        tenant_decision = self._check_tenant(context)
        if tenant_decision != AuthorizationDecision.ALLOW:
            return tenant_decision, self._tenant_reason(context)

        agent_decision = self._check_agent(context)
        if agent_decision != AuthorizationDecision.ALLOW:
            return agent_decision, self._agent_reason(context)

        user_decision = self._check_user(context)
        if user_decision != AuthorizationDecision.ALLOW:
            return user_decision, self._user_reason(context)

        role_decision = self._check_role_permissions(context)
        if role_decision != AuthorizationDecision.ALLOW:
            return role_decision, self._role_reason(context)

        service_decision = self._check_service(context)
        if service_decision != AuthorizationDecision.ALLOW:
            return service_decision, self._service_reason(context)

        action_decision = self._check_action(context)
        if action_decision != AuthorizationDecision.ALLOW:
            return action_decision, self._action_reason(context)

        resource_decision = self._check_resource(context)
        if resource_decision != AuthorizationDecision.ALLOW:
            return resource_decision, self._resource_reason(context)

        task_decision = self._check_task(context)
        if task_decision != AuthorizationDecision.ALLOW:
            return task_decision, self._task_reason(context)

        resource_hierarchy_decision = self._check_resource_hierarchy(context)
        if resource_hierarchy_decision != AuthorizationDecision.ALLOW:
            return resource_hierarchy_decision, self._resource_hierarchy_reason(context)

        parameter_decision = self._check_parameters(context)
        if parameter_decision != AuthorizationDecision.ALLOW:
            return parameter_decision, self._parameter_reason(context)

        environment_decision = self._check_environment(context)
        if environment_decision != AuthorizationDecision.ALLOW:
            return environment_decision, self._environment_reason(context)

        incident_state_decision = self._check_incident_state(context)
        if incident_state_decision != AuthorizationDecision.ALLOW:
            return incident_state_decision, self._incident_state_reason(context)

        recovery_state_decision = self._check_recovery_state(context)
        if recovery_state_decision != AuthorizationDecision.ALLOW:
            return recovery_state_decision, self._recovery_state_reason(context)

        dependency_state_decision = self._check_dependency_state(context)
        if dependency_state_decision != AuthorizationDecision.ALLOW:
            return dependency_state_decision, self._dependency_state_reason(context)

        risk_score_decision = self._check_risk_score(context)
        if risk_score_decision != AuthorizationDecision.ALLOW:
            return risk_score_decision, self._risk_score_reason(context)

        previous_behavior_decision = self._check_previous_behavior(context)
        if previous_behavior_decision != AuthorizationDecision.ALLOW:
            return previous_behavior_decision, self._previous_behavior_reason(context)

        authority_ttl_decision = self._check_authority_ttl(context)
        if authority_ttl_decision != AuthorizationDecision.ALLOW:
            return authority_ttl_decision, self._authority_ttl_reason(context)

        expiration_decision = self._check_expiration(context)
        if expiration_decision != AuthorizationDecision.ALLOW:
            return expiration_decision, self._expiration_reason(context)

        tool_decision = self._check_tool(context)
        if tool_decision != AuthorizationDecision.ALLOW:
            return tool_decision, self._tool_reason(context)

        return AuthorizationDecision.ALLOW, "Authorized"

    def _check_tenant(self, context: AuthorizationContext) -> AuthorizationDecision:
        require_tenant = getattr(self._settings, "authorization_require_tenant", False)
        if not require_tenant:
            return AuthorizationDecision.ALLOW
        if not context.tenant_id:
            return AuthorizationDecision.DENY
        if not self._is_valid_tenant(context.tenant_id):
            return AuthorizationDecision.DENY
        return AuthorizationDecision.ALLOW

    def _check_agent(self, context: AuthorizationContext) -> AuthorizationDecision:
        if not context.agent_id or not str(context.agent_id).strip():
            return AuthorizationDecision.DENY
        return AuthorizationDecision.ALLOW

    def _check_user(self, context: AuthorizationContext) -> AuthorizationDecision:
        if not context.user_id:
            return AuthorizationDecision.DENY
        return AuthorizationDecision.ALLOW

    def _check_role_permissions(self, context: AuthorizationContext) -> AuthorizationDecision:
        default_deny = getattr(self._settings, "authorization_default_deny", False)
        if not default_deny:
            return AuthorizationDecision.ALLOW
        role_actions = getattr(self._settings, "authorization_role_actions", {})
        user_role = getattr(context, "user_role", None)
        if not user_role:
            return AuthorizationDecision.DENY
        allowed_actions = role_actions.get(user_role)
        if allowed_actions is None:
            return AuthorizationDecision.DENY
        if context.action not in allowed_actions:
            return AuthorizationDecision.DENY
        return AuthorizationDecision.ALLOW

    def _check_service(self, context: AuthorizationContext) -> AuthorizationDecision:
        allowed_services = getattr(self._settings, "authorization_allowed_services", None)
        if allowed_services is not None:
            if not context.service_id:
                return AuthorizationDecision.DENY
            if context.service_id not in allowed_services:
                return AuthorizationDecision.DENY
        return AuthorizationDecision.ALLOW

    def _check_action(self, context: AuthorizationContext) -> AuthorizationDecision:
        allowed_actions = getattr(self._settings, "authorization_allowed_actions", None)
        if allowed_actions is not None:
            if not context.action:
                return AuthorizationDecision.DENY
            if context.action not in allowed_actions:
                return AuthorizationDecision.DENY
        return AuthorizationDecision.ALLOW

    def _check_resource(self, context: AuthorizationContext) -> AuthorizationDecision:
        allowed_resources = getattr(self._settings, "authorization_allowed_resources", None)
        if allowed_resources is not None:
            if not context.resource:
                return AuthorizationDecision.DENY
            if context.resource not in allowed_resources:
                return AuthorizationDecision.DENY
        return AuthorizationDecision.ALLOW

    def _check_task(self, context: AuthorizationContext) -> AuthorizationDecision:
        if not context.require_task_scoping:
            return AuthorizationDecision.ALLOW
        if not context.task_id:
            return AuthorizationDecision.DENY
        allowed_tasks = getattr(self._settings, "authorization_allowed_tasks", None)
        if allowed_tasks is not None and context.task_id not in allowed_tasks:
            return AuthorizationDecision.DENY
        return AuthorizationDecision.ALLOW

    def _check_resource_hierarchy(self, context: AuthorizationContext) -> AuthorizationDecision:
        allowed_resources = getattr(self._settings, "authorization_allowed_resources", None)
        if allowed_resources is None or not context.resource:
            return AuthorizationDecision.ALLOW
        for allowed in allowed_resources:
            if fnmatch.fnmatch(context.resource, allowed):
                return AuthorizationDecision.ALLOW
        return AuthorizationDecision.DENY

    def _check_parameters(self, context: AuthorizationContext) -> AuthorizationDecision:
        if not context.parameter_constraints:
            return AuthorizationDecision.ALLOW
        if not context.parameter_hash:
            return AuthorizationDecision.DENY
        constraints = context.parameter_constraints
        allowed_types = constraints.get("allowed_types")
        if allowed_types and context.parameter_hash not in allowed_types:
            return AuthorizationDecision.DENY
        allowed_values = constraints.get("allowed_values")
        if allowed_values and context.parameter_hash not in allowed_values:
            return AuthorizationDecision.DENY
        return AuthorizationDecision.ALLOW

    def _check_environment(self, context: AuthorizationContext) -> AuthorizationDecision:
        destructive_actions = getattr(self._settings, "authorization_destructive_actions", [])
        if context.action not in destructive_actions:
            return AuthorizationDecision.ALLOW
        if context.environment != AgentEnvironment.PRODUCTION:
            return AuthorizationDecision.REQUIRE_HITL
        return AuthorizationDecision.ALLOW

    def _check_incident_state(self, context: AuthorizationContext) -> AuthorizationDecision:
        incident_state = context.incident_state or {}
        if not incident_state:
            return AuthorizationDecision.ALLOW
        active = incident_state.get("active")
        if active is None:
            return AuthorizationDecision.DENY
        if not active:
            return AuthorizationDecision.ALLOW
        incident_response_actions = getattr(
            self._settings,
            "authorization_incident_response_actions",
            ["respond", "recover", "diagnose", "contain"],
        )
        if context.action in incident_response_actions:
            return AuthorizationDecision.ALLOW
        return AuthorizationDecision.DENY

    def _check_recovery_state(self, context: AuthorizationContext) -> AuthorizationDecision:
        recovery_state = context.recovery_state or {}
        if not recovery_state:
            return AuthorizationDecision.ALLOW
        resource_status = recovery_state.get(context.resource)
        if resource_status is None:
            return AuthorizationDecision.DENY
        if resource_status in ("recovering", "in_progress"):
            recovery_actions = getattr(
                self._settings,
                "authorization_recovery_actions",
                ["recover", "status_check", "monitor"],
            )
            if context.action in recovery_actions:
                return AuthorizationDecision.ALLOW
            return AuthorizationDecision.DENY
        return AuthorizationDecision.DENY

    def _check_dependency_state(self, context: AuthorizationContext) -> AuthorizationDecision:
        dependency_state = context.dependency_state or {}
        if not dependency_state:
            return AuthorizationDecision.ALLOW
        for _dep_name, dep_status in dependency_state.items():
            if dep_status in ("degraded", "down"):
                return AuthorizationDecision.REQUIRE_HITL
            if dep_status == "unknown":
                return AuthorizationDecision.DENY
        return AuthorizationDecision.ALLOW

    def _check_risk_score(self, context: AuthorizationContext) -> AuthorizationDecision:
        risk_engine = RiskEngine(settings=self._settings)
        risk_result = risk_engine.evaluate(
            context,
            agent_history=context.agent_history,
            authority_grants=context.authority_grants,
            recent_actions=context.recent_actions,
        )
        risk_threshold = getattr(self._settings, "authorization_risk_threshold", 0.7)
        score = risk_result.get("score", 0.0)
        if score >= risk_threshold:
            if score >= 0.8:
                return AuthorizationDecision.DENY
            return AuthorizationDecision.REQUIRE_HITL
        return AuthorizationDecision.ALLOW

    def _check_previous_behavior(self, context: AuthorizationContext) -> AuthorizationDecision:
        history = context.agent_history or []
        if not history:
            if getattr(context, "agent_history_required", False):
                return AuthorizationDecision.DENY
            return AuthorizationDecision.ALLOW
        historical_combinations = set()
        for h in history:
            tool = h.get("tool", "")
            resource = h.get("resource", "")
            if tool:
                historical_combinations.add((tool, resource))
        if not historical_combinations:
            if getattr(context, "agent_history_required", False):
                return AuthorizationDecision.DENY
            return AuthorizationDecision.ALLOW
        current_combo = (context.proposed_tool, context.resource)
        if current_combo not in historical_combinations:
            return AuthorizationDecision.REQUIRE_HITL
        return AuthorizationDecision.ALLOW

    def _check_authority_ttl(self, context: AuthorizationContext) -> AuthorizationDecision:
        authority_grants = context.authority_grants or []
        now = datetime.now(UTC)
        for grant in authority_grants:
            expires_at = grant.get("expires_at")
            if expires_at is None:
                return AuthorizationDecision.DENY
            if isinstance(expires_at, str):
                try:
                    expires_at = datetime.fromisoformat(expires_at)
                except ValueError:
                    return AuthorizationDecision.DENY
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at < now:
                return AuthorizationDecision.DENY
        return AuthorizationDecision.ALLOW

    def _check_expiration(self, context: AuthorizationContext) -> AuthorizationDecision:
        if context.authorized_at is None:
            return AuthorizationDecision.ALLOW
        expiry_seconds = getattr(self._settings, "authorization_expiry_seconds", 3600)
        authorized_at = context.authorized_at
        if authorized_at.tzinfo is None:
            authorized_at = authorized_at.replace(tzinfo=UTC)
        now = datetime.now(tz=UTC)
        if (now - authorized_at).total_seconds() > expiry_seconds:
            return AuthorizationDecision.DENY
        return AuthorizationDecision.ALLOW

    def _check_tool(self, context: AuthorizationContext) -> AuthorizationDecision:
        denied_tools = getattr(self._settings, "authorization_denied_tools", [])
        if context.proposed_tool in denied_tools:
            return AuthorizationDecision.DENY

        hitl_tools = getattr(self._settings, "authorization_hitl_tools", [])
        if context.proposed_tool in hitl_tools:
            return AuthorizationDecision.REQUIRE_HITL

        return AuthorizationDecision.ALLOW

    @staticmethod
    def _is_valid_tenant(tenant_id: str) -> bool:
        return bool(tenant_id and tenant_id.strip() and len(tenant_id) <= 64)

    @staticmethod
    def _tenant_reason(context: AuthorizationContext) -> str:
        if not context.tenant_id:
            return "Missing tenant identity"
        return "Invalid tenant identity"

    @staticmethod
    def _agent_reason(context: AuthorizationContext) -> str:
        return "Missing agent identity"

    @staticmethod
    def _user_reason(context: AuthorizationContext) -> str:
        return "Missing user identity"

    @staticmethod
    def _role_reason(context: AuthorizationContext) -> str:
        return "Insufficient role permissions"

    @staticmethod
    def _service_reason(context: AuthorizationContext) -> str:
        return "Missing or unauthorized service identity"

    @staticmethod
    def _action_reason(context: AuthorizationContext) -> str:
        return "Missing or unauthorized action"

    @staticmethod
    def _resource_reason(context: AuthorizationContext) -> str:
        return "Missing or unauthorized resource"

    @staticmethod
    def _task_reason(context: AuthorizationContext) -> str:
        return "Missing or unauthorized task"

    @staticmethod
    def _resource_hierarchy_reason(context: AuthorizationContext) -> str:
        return "Resource does not match allowed hierarchy pattern"

    @staticmethod
    def _parameter_reason(context: AuthorizationContext) -> str:
        return "Missing or invalid parameters"

    @staticmethod
    def _environment_reason(context: AuthorizationContext) -> str:
        return "Action not permitted in current environment"

    @staticmethod
    def _incident_state_reason(context: AuthorizationContext) -> str:
        return "Action restricted during active incident"

    @staticmethod
    def _recovery_state_reason(context: AuthorizationContext) -> str:
        return "Action not permitted during resource recovery"

    @staticmethod
    def _dependency_state_reason(context: AuthorizationContext) -> str:
        return "Action restricted due to dependency health"

    def _risk_score_reason(self, context: AuthorizationContext) -> str:
        risk_engine = RiskEngine(settings=self._settings)
        risk_result = risk_engine.evaluate(
            context,
            agent_history=context.agent_history,
            authority_grants=context.authority_grants,
            recent_actions=context.recent_actions,
        )
        signals = risk_result.get("signals", [])
        signal_names = ", ".join(s.get("name", "") for s in signals[:3])
        return (
            f"Risk score {risk_result.get('score', 0.0)} exceeds threshold. Signals: {signal_names}"
        )

    @staticmethod
    def _previous_behavior_reason(context: AuthorizationContext) -> str:
        return "Agent behavior deviates from historical patterns"

    @staticmethod
    def _authority_ttl_reason(context: AuthorizationContext) -> str:
        return "Authority grant has expired or expiration is unknown"

    def _tool_reason(self, context: AuthorizationContext) -> str:
        denied_tools = getattr(self._settings, "authorization_denied_tools", [])
        if context.proposed_tool in denied_tools:
            return f"Tool '{context.proposed_tool}' is denied by authorization policy"
        return f"Tool '{context.proposed_tool}' requires human approval"

    def _expiration_reason(self, context: AuthorizationContext) -> str:
        return "Authorization has expired"

    @staticmethod
    def compute_parameter_hash(parameters: dict[str, Any]) -> str:
        sorted_params = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(sorted_params.encode("utf-8")).hexdigest()
