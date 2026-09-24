from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from statistics import mean
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SessionBaseline:
    agent_id: str
    session_id: str
    typical_tools: list[str]
    typical_resources: list[str]
    typical_actions: list[str]
    tool_frequency: dict[str, int]
    resource_frequency: dict[str, int]
    avg_action_interval_seconds: float
    peak_action_hours: list[int]
    established_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class SessionBaselineService:
    """Establishes and compares session behavioral baselines."""

    def establish_baseline(
        self, agent_id: str, session_id: str, actions: list[dict]
    ) -> SessionBaseline:
        tools = [a.get("tool", "") for a in actions]
        resources = [a.get("resource", "") for a in actions]
        action_types = [a.get("action", "execute") for a in actions]
        timestamps = [a.get("timestamp") for a in actions if a.get("timestamp")]

        peak_hours = []
        if timestamps:
            hours = [
                datetime.fromtimestamp(ts, tz=UTC).hour
                for ts in timestamps
                if isinstance(ts, (int, float))
            ]
            if hours:
                hour_counts = Counter(hours)
                peak_hours = [h for h, _ in hour_counts.most_common(3)]

        intervals = []
        for i in range(1, len(timestamps)):
            if isinstance(timestamps[i], (int, float)) and isinstance(
                timestamps[i - 1], (int, float)
            ):
                intervals.append(timestamps[i] - timestamps[i - 1])

        return SessionBaseline(
            agent_id=agent_id,
            session_id=session_id,
            typical_tools=list(set(tools)),
            typical_resources=list(set(resources)),
            typical_actions=list(set(action_types)),
            tool_frequency=dict(Counter(tools)),
            resource_frequency=dict(Counter(resources)),
            avg_action_interval_seconds=mean(intervals) if intervals else 0.0,
            peak_action_hours=peak_hours,
        )

    def compare_to_baseline(
        self,
        agent_id: str,
        session_id: str,
        current_actions: list[dict],
        baseline: SessionBaseline,
    ) -> list[dict]:
        signals = []
        baseline_tools = set(baseline.typical_tools)
        baseline_resources = set(baseline.typical_resources)

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

        if current_actions and baseline.avg_action_interval_seconds > 0:
            timestamps = [
                a.get("timestamp")
                for a in current_actions
                if isinstance(a.get("timestamp"), (int, float))
            ]
            if len(timestamps) > 1:
                intervals = [
                    timestamps[i] - timestamps[i - 1] for i in range(1, len(timestamps))
                ]
                avg_interval = mean(intervals)
                if avg_interval < baseline.avg_action_interval_seconds * 0.5:
                    signals.append(
                        {
                            "signal_type": "velocity_increase",
                            "severity": "high",
                            "description": "Action velocity increased significantly vs baseline",
                            "evidence": {
                                "baseline_interval": baseline.avg_action_interval_seconds,
                                "current_interval": avg_interval,
                            },
                        }
                    )

        return signals
