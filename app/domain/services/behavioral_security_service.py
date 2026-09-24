from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from statistics import mean, stdev
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DriftSignal:
    signal_type: str
    severity: str
    description: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AnomalyReport:
    agent_id: str
    session_id: str
    anomaly_score: float
    signals: list[DriftSignal]
    is_anomalous: bool
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class BehavioralSecurityService:
    """Behavioral security layer for agent anomaly defense."""

    def __init__(self, velocity_tracker=None, risk_engine=None):
        self._velocity_tracker = velocity_tracker
        self._risk_engine = risk_engine
        self._baselines: dict[str, dict] = {}

    def establish_baseline(
        self, agent_id: str, session_id: str, actions: list[dict]
    ) -> dict:
        """Establish behavioral baseline from historical actions."""
        tools = [a.get("tool", "") for a in actions]
        resources = [a.get("resource", "") for a in actions]
        action_types = [a.get("action_type", "") for a in actions]
        timestamps = [
            a.get("timestamp", 0) for a in actions if a.get("timestamp")
        ]

        baseline = {
            "agent_id": agent_id,
            "session_id": session_id,
            "established_at": datetime.now(UTC).isoformat(),
            "typical_tools": list(set(tools)),
            "typical_resources": list(set(resources)),
            "typical_action_types": list(set(action_types)),
            "tool_distribution": dict(Counter(tools)),
            "resource_distribution": dict(Counter(resources)),
            "avg_velocity": self._compute_avg_velocity(timestamps),
            "velocity_stddev": self._compute_velocity_stddev(timestamps),
            "max_delegation_depth_used": max(
                (a.get("delegation_depth", 0) for a in actions), default=0
            ),
            "total_actions": len(actions),
        }
        key = f"{agent_id}:{session_id}"
        self._baselines[key] = baseline
        return baseline

    def compare_to_baseline(
        self, agent_id: str, session_id: str, current_actions: list[dict]
    ) -> list[dict]:
        key = f"{agent_id}:{session_id}"
        baseline = self._baselines.get(key)
        if baseline is None:
            return []

        signals = []
        baseline_tools = set(baseline.get("typical_tools", []))
        baseline_resources = set(baseline.get("typical_resources", []))

        current_tools = {a.get("tool", "") for a in current_actions}
        current_resources = {a.get("resource", "") for a in current_actions}

        new_tools = current_tools - baseline_tools
        if new_tools:
            signals.append(
                {
                    "signal_type": "new_tool_usage",
                    "severity": "medium",
                    "description": f"Agent used {len(new_tools)} tool(s) not seen in baseline",
                    "evidence": {"unusual_tools": list(new_tools)},
                }
            )

        new_resources = current_resources - baseline_resources
        if new_resources:
            signals.append(
                {
                    "signal_type": "new_resource_targeting",
                    "severity": "medium",
                    "description": f"Agent targeted {len(new_resources)} resource(s) not seen in baseline",
                    "evidence": {"unusual_resources": list(new_resources)},
                }
            )

        return signals

    def detect_drift(
        self,
        agent_id: str,
        session_id: str,
        baseline: dict,
        current: dict,
    ) -> dict:
        """Detect behavioral drift from baseline."""
        signals = []
        score = 0.0

        baseline_tools = set(baseline.get("typical_tools", []))
        current_tools = set(current.get("tools_used", []))
        new_tools = current_tools - baseline_tools
        if new_tools:
            signals.append(
                DriftSignal(
                    signal_type="new_tool_usage",
                    severity="medium",
                    description=f"{len(new_tools)} new tool(s) used",
                    evidence={"tools": list(new_tools)},
                )
            )
            score += 0.25

        baseline_resources = set(baseline.get("typical_resources", []))
        current_resources = set(current.get("resources_targeted", []))
        new_resources = current_resources - baseline_resources
        if new_resources:
            signals.append(
                DriftSignal(
                    signal_type="new_resource_targeting",
                    severity="medium",
                    description=f"{len(new_resources)} new resource(s) targeted",
                    evidence={"resources": list(new_resources)},
                )
            )
            score += 0.25

        baseline_velocity = baseline.get("avg_velocity", 0)
        current_velocity = current.get("velocity", 0)
        if baseline_velocity > 0 and current_velocity > baseline_velocity * 2:
            signals.append(
                DriftSignal(
                    signal_type="velocity_increase",
                    severity="high",
                    description="Action velocity doubled from baseline",
                    evidence={
                        "baseline_velocity": baseline_velocity,
                        "current_velocity": current_velocity,
                    },
                )
            )
            score += 0.35

        baseline_action_types = set(baseline.get("typical_action_types", []))
        current_action_types = set(current.get("action_types", []))
        scope_expansion = current_action_types - baseline_action_types
        if scope_expansion:
            signals.append(
                DriftSignal(
                    signal_type="scope_expansion",
                    severity="high",
                    description=f"New action types observed: {scope_expansion}",
                    evidence={"action_types": list(scope_expansion)},
                )
            )
            score += 0.35

        score = max(0.0, min(1.0, score))
        confidence = 0.8 if signals else 0.95

        return {
            "drift_score": round(score, 3),
            "drift_signals": [asdict(s) for s in signals],
            "drift_confidence": confidence,
            "is_drifted": score >= 0.5,
        }

    def detect_action_sequence_anomaly(
        self,
        action_sequence: list[str],
        known_sequences: list[list[str]],
    ) -> dict:
        """Detect unusual action patterns using sequence alignment."""
        if not known_sequences:
            return {
                "anomaly_score": 1.0,
                "is_anomalous": True,
                "explanation": "No known sequences to compare against",
            }

        best_score = 0.0
        best_match = None
        for seq in known_sequences:
            similarity = self._sequence_similarity(action_sequence, seq)
            if similarity > best_score:
                best_score = similarity
                best_match = seq

        anomaly_score = 1.0 - best_score
        is_anomalous = anomaly_score >= 0.5

        return {
            "anomaly_score": round(anomaly_score, 3),
            "is_anomalous": is_anomalous,
            "explanation": (
                f"Sequence deviates from known pattern (best match similarity: {best_score:.2f})"
                if is_anomalous
                else "Sequence matches known pattern"
            ),
        }

    def detect_unusual_tool_selection(
        self,
        current_tools: list[str],
        baseline_tools: set[str],
        all_tools: set[str],
    ) -> dict:
        """Identify tools never seen in baseline."""
        unusual = [t for t in current_tools if t not in baseline_tools]
        risk_multiplier = 1.0 + (len(unusual) * 0.2)
        return {
            "unusual_tools": unusual,
            "risk_multiplier": round(risk_multiplier, 2),
        }

    def detect_unusual_target_selection(
        self,
        current_targets: list[str],
        baseline_targets: set[str],
    ) -> dict:
        """Identify resources never targeted in baseline."""
        unusual = [t for t in current_targets if t not in baseline_targets]
        risk_multiplier = 1.0 + (len(unusual) * 0.2)
        return {
            "unusual_targets": unusual,
            "risk_multiplier": round(risk_multiplier, 2),
        }

    def detect_unusual_velocity(
        self,
        current_velocity: float,
        baseline_velocity: float,
        std_dev: float,
    ) -> dict:
        """Z-score based velocity anomaly detection."""
        if std_dev == 0:
            z_score = 0.0
        else:
            z_score = (current_velocity - baseline_velocity) / std_dev
        is_anomalous = abs(z_score) > 3.0
        return {
            "velocity_z_score": round(z_score, 3),
            "is_anomalous": is_anomalous,
        }

    def detect_privilege_escalation(
        self,
        current_scope: str,
        previous_scopes: list[str],
        authority_grants: list[dict],
    ) -> dict:
        """Detect if agent is requesting/granting higher privileges than baseline."""
        escalation_detected = False
        escalation_details = []

        if previous_scopes:
            scope_hierarchy = {"read": 1, "write": 2, "admin": 3}
            current_level = scope_hierarchy.get(current_scope, 0)
            max_previous = max(
                (scope_hierarchy.get(s, 0) for s in previous_scopes), default=0
            )
            if current_level > max_previous:
                escalation_detected = True
                escalation_details.append(
                    f"Scope increased from {max_previous} to {current_level}"
                )

        for grant in authority_grants:
            grant_scope = grant.get("scope", "")
            if grant_scope == "admin" and current_scope != "admin":
                escalation_detected = True
                escalation_details.append(
                    f"Admin grant detected with current scope {current_scope}"
                )

        return {
            "escalation_detected": escalation_detected,
            "escalation_details": escalation_details,
        }

    def detect_runaway_behavior(
        self,
        action_sequence: list[dict],
        time_window_seconds: float = 60.0,
        repetition_threshold: int = 5,
    ) -> dict:
        """Detect rapid repeated mutations."""
        if not action_sequence:
            return {
                "is_runaway": False,
                "repetition_count": 0,
                "repetition_rate": 0.0,
            }

        action_types = [a.get("action_type", a.get("tool", "")) for a in action_sequence]
        type_counts = Counter(action_types)
        max_repetition = max(type_counts.values()) if type_counts else 0

        if len(action_sequence) < 2:
            return {
                "is_runaway": False,
                "repetition_count": max_repetition,
                "repetition_rate": 0.0,
            }

        timestamps = [
            a.get("timestamp")
            for a in action_sequence
            if isinstance(a.get("timestamp"), (int, float))
        ]
        if len(timestamps) < 2:
            rate = 0.0
        else:
            total_time = max(timestamps) - min(timestamps)
            rate = max_repetition / (total_time / time_window_seconds) if total_time > 0 else 0.0

        is_runaway = max_repetition > repetition_threshold
        return {
            "is_runaway": is_runaway,
            "repetition_count": max_repetition,
            "repetition_rate": round(rate, 3),
        }

    def detect_autonomous_escalation(
        self,
        action_history: list[dict],
        authorization_history: list[dict],
    ) -> dict:
        """Detect agent escalating privileges without human authorization."""
        escalation_detected = False
        escalation_chain = []

        unauthorized_scopes = []
        for action in action_history:
            scope = action.get("scope", "")
            if scope in ("admin", "write"):
                authorized = any(
                    auth.get("scope") == scope and auth.get("authorized")
                    for auth in authorization_history
                )
                if not authorized:
                    unauthorized_scopes.append(
                        {
                            "action": action.get("action_type"),
                            "scope": scope,
                            "timestamp": action.get("timestamp"),
                        }
                    )

        if len(unauthorized_scopes) >= 2:
            escalation_detected = True
            escalation_chain = unauthorized_scopes

        return {
            "escalation_detected": escalation_detected,
            "escalation_chain": escalation_chain,
        }

    def detect_intent_action_mismatch(
        self,
        declared_intent: str,
        executed_actions: list[dict],
    ) -> dict:
        """Detect mismatch between stated intent and actions."""
        if not declared_intent or not executed_actions:
            return {
                "mismatch_detected": False,
                "mismatch_score": 0.0,
                "evidence": [],
            }

        intent_lower = declared_intent.lower()
        mismatch_keywords = {
            "read": ["write", "delete", "drop", "update", "transfer", "escalate"],
            "query": ["delete", "drop", "truncate", "update"],
            "search": ["delete", "drop", "modify", "transfer"],
            "view": ["delete", "drop", "modify", "escalate"],
            "list": ["delete", "drop", "modify", "transfer"],
        }

        evidence = []
        mismatch_count = 0
        total_actions = len(executed_actions)

        for action in executed_actions:
            action_type = action.get("action_type", action.get("tool", "")).lower()
            for keyword, conflicting in mismatch_keywords.items():
                if keyword in intent_lower and action_type in conflicting:
                    mismatch_count += 1
                    evidence.append(
                        {
                            "action": action_type,
                            "conflicts_with": keyword,
                        }
                    )

        mismatch_score = mismatch_count / total_actions if total_actions > 0 else 0.0
        mismatch_detected = mismatch_score > 0.3

        return {
            "mismatch_detected": mismatch_detected,
            "mismatch_score": round(mismatch_score, 3),
            "evidence": evidence,
        }

    def _compute_avg_velocity(self, timestamps: list[float]) -> float:
        if len(timestamps) < 2:
            return 0.0
        intervals = [timestamps[i] - timestamps[i - 1] for i in range(1, len(timestamps))]
        return mean(intervals) if intervals else 0.0

    def _compute_velocity_stddev(self, timestamps: list[float]) -> float:
        if len(timestamps) < 2:
            return 0.0
        intervals = [timestamps[i] - timestamps[i - 1] for i in range(1, len(timestamps))]
        return stdev(intervals) if len(intervals) > 1 else 0.0

    def _sequence_similarity(self, seq1: list[str], seq2: list[str]) -> float:
        if not seq1 or not seq2:
            return 0.0
        matches = sum(1 for a, b in zip(seq1, seq2) if a == b)
        return matches / max(len(seq1), len(seq2))
