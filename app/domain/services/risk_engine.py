from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.domain.value_objects.authorization_context import AuthorizationContext
from app.domain.value_objects.authorization_decision import AuthorizationDecision
from app.infrastructure.config.settings import get_settings


@dataclass
class RiskSignal:
    name: str
    score: float
    explanation: str


class RiskEngine:
    """Modular risk evaluation layer.

    Produces explainable deterministic risk signals.
    Designed to be extensible for future ML models.
    """

    def __init__(self, settings: Any | None = None) -> None:
        self._settings = settings or get_settings()

    def evaluate(
        self,
        context: AuthorizationContext,
        *,
        agent_history: list[dict[str, Any]] | None = None,
        authority_grants: list[dict[str, Any]] | None = None,
        recent_actions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        signals = []
        signals.extend(self._check_unusual_escalation(context, authority_grants or []))
        signals.extend(self._check_excessive_depth(authority_grants or []))
        signals.extend(self._check_expired_authority(authority_grants or []))
        signals.extend(self._check_repeated_failures(recent_actions or []))
        signals.extend(self._check_abnormal_rate(recent_actions or []))
        signals.extend(self._check_unusual_tool_combination(context, recent_actions or []))
        signals.extend(self._check_sensitive_sequences(recent_actions or []))
        signals.extend(self._check_cross_boundary(context))
        signals.extend(self._check_suspicious_child_creation(context, agent_history or []))

        total_score = sum(s.score for s in signals)
        total_score = max(0.0, min(1.0, total_score))
        explanations = [s.explanation for s in signals]

        if total_score >= 0.8:
            decision = AuthorizationDecision.DENY
        elif total_score >= 0.5:
            decision = AuthorizationDecision.REQUIRE_HITL
        else:
            decision = AuthorizationDecision.ALLOW

        return {
            "score": round(total_score, 3),
            "decision": decision.value,
            "signals": [
                {"name": s.name, "score": round(s.score, 3), "explanation": s.explanation}
                for s in signals
            ],
            "explanations": explanations,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def _check_unusual_escalation(
        self, context: AuthorizationContext, grants: list[dict[str, Any]]
    ) -> list[RiskSignal]:
        signals = []
        for grant in grants:
            if grant.get("scope") == "admin" and context.action in ("delete", "drop", "truncate"):
                signals.append(RiskSignal(
                    name="unusual_privilege_escalation",
                    score=0.4,
                    explanation=(
                    f"Admin scope used for destructive action '{context.action}' "
                    f"on resource '{context.resource}'"
                ),
                ))
        return signals

    def _check_excessive_depth(self, grants: list[dict[str, Any]]) -> list[RiskSignal]:
        signals = []
        max_depth = max((g.get("delegation_depth", 0) for g in grants), default=0)
        if max_depth > 5:
            signals.append(RiskSignal(
                name="excessive_delegation_depth",
                score=0.3,
                explanation=(
                    f"Authority delegation depth {max_depth} exceeds "
                    f"recommended threshold of 5"
                ),
            ))
        return signals

    def _check_expired_authority(self, grants: list[dict[str, Any]]) -> list[RiskSignal]:
        signals = []
        now = datetime.now(UTC)
        for grant in grants:
            expires = grant.get("expires_at")
            if expires:
                if isinstance(expires, str):
                    try:
                        expires = datetime.fromisoformat(expires)
                    except ValueError:
                        continue
                if expires < now:
                    signals.append(RiskSignal(
                        name="expired_authority_usage",
                        score=0.5,
                        explanation=(
                        f"Authority grant {grant.get('grant_id')} expired at "
                        f"{expires.isoformat()}"
                    ),
                    ))
        return signals

    def _check_repeated_failures(self, actions: list[dict[str, Any]]) -> list[RiskSignal]:
        signals = []
        failures = [a for a in actions if a.get("status") in ("denied", "failed")]
        if len(failures) >= 5:
            signals.append(RiskSignal(
                name="repeated_authorization_failures",
                score=0.35,
                    explanation=(
                        f"{len(failures)} recent failures detected, "
                        f"possible brute force or misconfiguration"
                    ),
            ))
        return signals

    def _check_abnormal_rate(self, actions: list[dict[str, Any]]) -> list[RiskSignal]:
        signals = []
        if len(actions) >= 50:
            signals.append(RiskSignal(
                name="abnormal_action_rate",
                score=0.25,
                explanation=f"{len(actions)} actions in recent window exceeds normal threshold",
            ))
        return signals

    def _check_unusual_tool_combination(
        self, context: AuthorizationContext, actions: list[dict[str, Any]]
    ) -> list[RiskSignal]:
        signals = []
        tool_combos = set()
        for a in actions:
            tool_combos.add(a.get("tool", ""))
        if context.proposed_tool not in tool_combos and len(tool_combos) > 0:
            signals.append(RiskSignal(
                name="unusual_tool_resource_combination",
                score=0.2,
                    explanation=(
                        f"Tool '{context.proposed_tool}' on resource "
                        f"'{context.resource}' is a new combination"
                    ),
            ))
        return signals

    def _check_sensitive_sequences(self, actions: list[dict[str, Any]]) -> list[RiskSignal]:
        signals = []
        sensitive = {"drop_table", "truncate", "delete_from", "update_set", "transfer_funds"}
        recent_tools = [a.get("tool", "").lower() for a in actions[-10:]]
        if any(any(s in t for s in sensitive) for t in recent_tools):
            signals.append(RiskSignal(
                name="sensitive_action_sequence",
                score=0.3,
                explanation="Recent actions include sensitive tools in sequence",
            ))
        return signals

    def _check_cross_boundary(self, context: AuthorizationContext) -> list[RiskSignal]:
        signals = []
        if context.service_id and context.action == "execute":
            signals.append(RiskSignal(
                name="cross_boundary_attempt",
                score=0.15,
                explanation=f"Service '{context.service_id}' attempting cross-boundary execution",
            ))
        return signals

    def _check_suspicious_child_creation(
        self, context: AuthorizationContext, history: list[dict[str, Any]]
    ) -> list[RiskSignal]:
        signals = []
        child_creations = [h for h in history if h.get("action_type") == "create_agent"]
        if len(child_creations) >= 3:
            signals.append(RiskSignal(
                name="suspicious_child_agent_creation",
                score=0.4,
                    explanation=(
                        f"{len(child_creations)} child agents created recently, "
                        f"possible privilege spread"
                    ),
            ))
        return signals
