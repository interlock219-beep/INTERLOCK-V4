from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from app.domain.entities.agent import Agent
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.agent_session_repository import AgentSessionRepository
from app.domain.repositories.protected_action_repository import ProtectedActionRepository


class AnomalySeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AnomalyType(StrEnum):
    IMPOSSIBLE_TRAVEL = "impossible_travel"
    IMPOSSIBLE_DELEGATION = "impossible_delegation"
    IDENTITY_IMPERSONATION = "identity_impersonation"
    IMPOSSIBLE_ACTION_SEQUENCE = "impossible_action_sequence"
    IMPOSSIBLE_TIME_TRAVEL = "impossible_time_travel"
    SUSPICIOUS_SESSION_PATTERN = "suspicious_session_pattern"
    ANOMALOUS_RESOURCE_ACCESS = "anomalous_resource_access"
    RAPID_IDENTITY_SWITCHING = "rapid_identity_switching"
    UNAUTHORIZED_CHILD_CREATION = "unauthorized_child_creation"
    GEOGRAPHIC_ANOMALY = "geographic_anomaly"


@dataclass(frozen=True, slots=True)
class AnomalyDetectionResult:
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    agent_id: str
    explanation: str
    confidence: float
    evidence: dict[str, Any] = field(default_factory=dict)
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class IdentityAnomalyDetectionService:
    """Detect identity anomalies including impossible travel, impossible
    delegation, impersonation, and suspicious behavioral patterns.

    IDY-010: Identity anomaly detection (impossible travel, impossible delegation)
    IDY-011: Identity impersonation detection via behavioral biometrics
    """

    def __init__(
        self,
        agent_repository: AgentRepository,
        session_repository: AgentSessionRepository,
        action_repository: ProtectedActionRepository | None = None,
    ) -> None:
        self._agent_repo = agent_repository
        self._session_repo = session_repository
        self._action_repo = action_repository

        self._max_travel_speed_kmh = 1500.0
        self._max_actions_per_minute = 100
        self._max_child_creations_per_session = 3
        self._impossible_time_window_seconds = 1
        self._geographic_anomaly_threshold = 0.8
        self._behavioral_deviation_threshold = 2.5

    async def detect_anomalies(
        self,
        tenant_id: str,
        agent_id: str,
        *,
        current_location: dict[str, Any] | None = None,
        current_action: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> list[AnomalyDetectionResult]:
        anomalies: list[AnomalyDetectionResult] = []

        anomalies.extend(
            await self._check_impossible_travel(
                tenant_id, agent_id, current_location
            )
        )
        anomalies.extend(
            await self._check_impossible_delegation(tenant_id, agent_id)
        )
        anomalies.extend(
            await self._check_impossible_action_sequence(tenant_id, agent_id)
        )
        anomalies.extend(
            await self._check_rapid_identity_switching(tenant_id, agent_id)
        )
        anomalies.extend(
            await self._check_unauthorized_child_creation(tenant_id, agent_id)
        )
        anomalies.extend(
            await self._check_suspicious_session_pattern(
                tenant_id, agent_id, session_id
            )
        )
        anomalies.extend(
            await self._check_anomalous_resource_access(
                tenant_id, agent_id, current_action
            )
        )

        agent = await self._agent_repo.get_by_agent_id(tenant_id, agent_id)
        if agent is not None:
            anomalies.extend(
                await self._check_identity_impersonation(tenant_id, agent_id, agent)
            )

        return anomalies

    async def _check_impossible_travel(
        self,
        tenant_id: str,
        agent_id: str,
        current_location: dict[str, Any] | None,
    ) -> list[AnomalyDetectionResult]:
        if not current_location or not current_location.get("latitude") or not current_location.get("longitude"):
            return []

        sessions, _ = await self._session_repo.list_by_agent(tenant_id, agent_id, limit=50)
        if not sessions:
            return []

        prev_session = sessions[0] if sessions else None
        if prev_session is None:
            return []

        prev_location = prev_session.metadata.get("location") if prev_session.metadata else None
        if not prev_location:
            return []

        result = self._detect_impossible_travel(
            agent_id, prev_location, current_location, prev_session.started_at
        )
        if result:
            return [result]
        return []

    def _detect_impossible_travel(
        self,
        agent_id: str,
        prev_location: dict[str, Any],
        current_location: dict[str, Any],
        prev_time: datetime,
    ) -> AnomalyDetectionResult | None:
        from math import asin, cos, radians, sin, sqrt

        lat1, lon1 = radians(prev_location["latitude"]), radians(prev_location["longitude"])
        lat2, lon2 = radians(current_location["latitude"]), radians(current_location["longitude"])

        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        earth_radius_km = 6371.0
        distance_km = earth_radius_km * c

        now = datetime.now(UTC)
        if prev_time.tzinfo is None:
            prev_time = prev_time.replace(tzinfo=UTC)
        elapsed_hours = (now - prev_time).total_seconds() / 3600.0
        elapsed_hours = max(elapsed_hours, 0.001)

        speed_kmh = distance_km / elapsed_hours

        if speed_kmh > self._max_travel_speed_kmh:
            return AnomalyDetectionResult(
                anomaly_type=AnomalyType.IMPOSSIBLE_TRAVEL,
                severity=AnomalySeverity.CRITICAL,
                agent_id=agent_id,
                explanation=(
                    f"Agent '{agent_id}' traveled {distance_km:.1f} km in "
                    f"{elapsed_hours:.2f} hours ({speed_kmh:.1f} km/h), exceeding "
                    f"max speed {self._max_travel_speed_kmh} km/h"
                ),
                confidence=min(1.0, speed_kmh / (self._max_travel_speed_kmh * 5)),
                evidence={
                    "distance_km": distance_km,
                    "elapsed_hours": elapsed_hours,
                    "speed_kmh": speed_kmh,
                    "max_speed_kmh": self._max_travel_speed_kmh,
                    "prev_location": prev_location,
                    "current_location": current_location,
                },
            )
        return None

    async def _check_impossible_delegation(
        self, tenant_id: str, agent_id: str
    ) -> list[AnomalyDetectionResult]:
        agent = await self._agent_repo.get_by_agent_id(tenant_id, agent_id)
        if agent is None:
            return []

        if agent.parent_agent_id is None:
            return []

        parent = await self._agent_repo.get_by_agent_id_global(agent.parent_agent_id)
        if parent is None:
            parent = await self._agent_repo.get_by_agent_id(tenant_id, agent.parent_agent_id)
        if parent is None:
            return [
                AnomalyDetectionResult(
                    anomaly_type=AnomalyType.IMPOSSIBLE_DELEGATION,
                    severity=AnomalySeverity.HIGH,
                    agent_id=agent_id,
                    explanation=(
                        f"Agent '{agent_id}' references non-existent parent "
                        f"'{agent.parent_agent_id}'"
                    ),
                    confidence=0.95,
                    evidence={
                        "parent_agent_id": agent.parent_agent_id,
                        "error": "parent not found",
                    },
                )
            ]

        if parent.tenant_id != agent.tenant_id:
            return [
                AnomalyDetectionResult(
                    anomaly_type=AnomalyType.IMPOSSIBLE_DELEGATION,
                    severity=AnomalySeverity.CRITICAL,
                    agent_id=agent_id,
                    explanation=(
                        f"Agent '{agent_id}' in tenant '{agent.tenant_id}' "
                        f"delegated from parent in different tenant "
                        f"'{parent.tenant_id}'"
                    ),
                    confidence=1.0,
                    evidence={
                        "parent_tenant_id": parent.tenant_id,
                        "agent_tenant_id": agent.tenant_id,
                        "parent_agent_id": agent.parent_agent_id,
                    },
                )
            ]

        return []

    async def _check_impossible_action_sequence(
        self, tenant_id: str, agent_id: str
    ) -> list[AnomalyDetectionResult]:
        if self._action_repo is None:
            return []

        now = datetime.now(UTC)
        one_minute_ago = now - timedelta(minutes=1)
        actions, _ = await self._action_repo.list_by_agent(
            tenant_id, agent_id, limit=200
        )

        recent_actions = [
            a for a in actions
            if a.created_at and a.created_at >= one_minute_ago
        ]

        if len(recent_actions) > self._max_actions_per_minute:
            return [
                AnomalyDetectionResult(
                    anomaly_type=AnomalyType.IMPOSSIBLE_ACTION_SEQUENCE,
                    severity=AnomalySeverity.HIGH,
                    agent_id=agent_id,
                    explanation=(
                        f"Agent '{agent_id}' performed {len(recent_actions)} "
                        f"actions in the last minute, exceeding limit of "
                        f"{self._max_actions_per_minute}"
                    ),
                    confidence=min(1.0, len(recent_actions) / (self._max_actions_per_minute * 3)),
                    evidence={
                        "actions_in_window": len(recent_actions),
                        "threshold": self._max_actions_per_minute,
                        "time_window_seconds": 60,
                    },
                )
            ]
        return []

    async def _check_rapid_identity_switching(
        self, tenant_id: str, agent_id: str
    ) -> list[AnomalyDetectionResult]:
        if self._action_repo is None:
            return []

        actions, _ = await self._action_repo.list_by_agent(
            tenant_id, agent_id, limit=100
        )

        if len(actions) < 3:
            return []

        timestamps = sorted(
            [a.created_at for a in actions if a.created_at is not None]
        )

        for i in range(2, len(timestamps)):
            if timestamps[i].tzinfo is None:
                timestamps[i] = timestamps[i].replace(tzinfo=UTC)
            if timestamps[i - 2].tzinfo is None:
                timestamps[i - 2] = timestamps[i - 2].replace(tzinfo=UTC)

            if (timestamps[i] - timestamps[i - 2]).total_seconds() < self._impossible_time_window_seconds:
                return [
                    AnomalyDetectionResult(
                        anomaly_type=AnomalyType.RAPID_IDENTITY_SWITCHING,
                        severity=AnomalySeverity.HIGH,
                        agent_id=agent_id,
                        explanation=(
                            f"Agent '{agent_id}' performed 3 actions within "
                            f"{self._impossible_time_window_seconds}s, "
                            f"indicating possible identity switching or replay"
                        ),
                        confidence=0.9,
                        evidence={
                            "min_interval": self._impossible_time_window_seconds,
                            "action_count": 3,
                        },
                    )
                ]
        return []

    async def _check_unauthorized_child_creation(
        self, tenant_id: str, agent_id: str
    ) -> list[AnomalyDetectionResult]:
        if self._action_repo is None:
            return []

        actions, _ = await self._action_repo.list_by_agent(
            tenant_id, agent_id, limit=500
        )

        child_creations = [
            a for a in actions
            if a.action_type == "create_agent" and a.executed_at is not None
        ]

        if len(child_creations) > self._max_child_creations_per_session:
            return [
                AnomalyDetectionResult(
                    anomaly_type=AnomalyType.UNAUTHORIZED_CHILD_CREATION,
                    severity=AnomalySeverity.HIGH,
                    agent_id=agent_id,
                    explanation=(
                        f"Agent '{agent_id}' created {len(child_creations)} "
                        f"child agents, exceeding limit of "
                        f"{self._max_child_creations_per_session}"
                    ),
                    confidence=min(1.0, len(child_creations) / (self._max_child_creations_per_session * 5)),
                    evidence={
                        "child_creations": len(child_creations),
                        "threshold": self._max_child_creations_per_session,
                    },
                )
            ]
        return []

    async def _check_suspicious_session_pattern(
        self, tenant_id: str, agent_id: str, session_id: str | None
    ) -> list[AnomalyDetectionResult]:
        sessions, _ = await self._session_repo.list_by_agent(tenant_id, agent_id, limit=20)

        if len(sessions) < 2:
            return []

        if session_id is None:
            current = sessions[0]
        else:
            current = None
            for s in sessions:
                if s.session_id == session_id:
                    current = s
                    break
            if current is None:
                return []

        now = datetime.now(UTC)
        recent_sessions = [
            s for s in sessions
            if s.started_at and (now - s.started_at).total_seconds() < 60
        ]

        if len(recent_sessions) > 5:
            return [
                AnomalyDetectionResult(
                    anomaly_type=AnomalyType.SUSPICIOUS_SESSION_PATTERN,
                    severity=AnomalySeverity.MEDIUM,
                    agent_id=agent_id,
                    explanation=(
                        f"Agent '{agent_id}' created {len(recent_sessions)} "
                        f"sessions in under 60 seconds, indicating possible "
                        f"session manipulation"
                    ),
                    confidence=min(1.0, len(recent_sessions) / 20),
                    evidence={
                        "recent_sessions": len(recent_sessions),
                        "time_window_seconds": 60,
                    },
                )
            ]
        return []

    async def _check_anomalous_resource_access(
        self,
        tenant_id: str,
        agent_id: str,
        current_action: dict[str, Any] | None,
    ) -> list[AnomalyDetectionResult]:
        if current_action is None:
            return []

        resource = current_action.get("resource", "")
        tool = current_action.get("tool", "")
        action_type = current_action.get("action_type", "execute")

        if tool and action_type in ("delete", "drop", "rm", "rmdir", "unlink"):
            return [
                AnomalyDetectionResult(
                    anomaly_type=AnomalyType.ANOMALOUS_RESOURCE_ACCESS,
                    severity=AnomalySeverity.HIGH,
                    agent_id=agent_id,
                    explanation=(
                        f"Agent '{agent_id}' accessed resource '{resource}' "
                        f"with destructive action '{action_type}'"
                    ),
                    confidence=0.8,
                    evidence={
                        "resource": resource,
                        "tool": tool,
                        "action_type": action_type,
                    },
                )
            ]
        return []

    async def _check_identity_impersonation(
        self,
        tenant_id: str,
        agent_id: str,
        agent: Agent,
        behavioral_baselines: dict[str, Any] | None = None,
    ) -> list[AnomalyDetectionResult]:
        if agent.parent_agent_id is not None:
            parent = await self._agent_repo.get_by_agent_id(tenant_id, agent.parent_agent_id)
            if parent is None:
                return []

            if parent.model_name != agent.model_name or parent.agent_type != agent.agent_type:
                if agent.agent_type == "sub_agent" and parent.agent_type != "sub_agent":
                    return [
                        AnomalyDetectionResult(
                            anomaly_type=AnomalyType.IDENTITY_IMPERSONATION,
                            severity=AnomalySeverity.CRITICAL,
                            agent_id=agent_id,
                            explanation=(
                                f"Agent '{agent_id}' created by parent "
                                f"'{parent.agent_id}' has mismatched identity "
                                f"characteristics (model: parent={parent.model_name}, "
                                f"child={agent.model_name})"
                            ),
                            confidence=0.9,
                            evidence={
                                "parent_agent_id": parent.agent_id,
                                "parent_model": parent.model_name,
                                "child_model": agent.model_name,
                                "parent_type": parent.agent_type.value,
                                "child_type": agent.agent_type.value,
                            },
                        )
                    ]

        if behavioral_baselines and agent_id in behavioral_baselines:
            baseline = behavioral_baselines[agent_id]
            current_metrics = self._extract_behavioral_metrics(agent)

            for metric_name, historical_values in baseline.items():
                if metric_name not in current_metrics:
                    continue
                current_value = current_metrics[metric_name]
                if historical_values:
                    mean_val = sum(historical_values) / len(historical_values)
                    variance = sum(
                        (x - mean_val) ** 2 for x in historical_values
                    ) / len(historical_values)
                    std_dev = variance ** 0.5

                    if std_dev > 0:
                        deviations = abs(current_value - mean_val) / std_dev
                        if deviations > self._behavioral_deviation_threshold:
                            return [
                                AnomalyDetectionResult(
                                    anomaly_type=AnomalyType.IDENTITY_IMPERSONATION,
                                    severity=AnomalySeverity.HIGH,
                                    agent_id=agent_id,
                                    explanation=(
                                        f"Behavioral anomaly detected for agent "
                                        f"'{agent_id}': metric '{metric_name}' "
                                        f"deviates by {deviations:.2f} standard "
                                        f"deviations from baseline"
                                    ),
                                    confidence=min(1.0, deviations / 5),
                                    evidence={
                                        "metric": metric_name,
                                        "current_value": current_value,
                                        "mean": mean_val,
                                        "std_dev": std_dev,
                                        "deviations": deviations,
                                    },
                                )
                            ]

        return []

    def _extract_behavioral_metrics(self, agent: Agent) -> dict[str, float]:
        metrics: dict[str, float] = {}
        tool_list = agent.connected_tools
        metrics["tool_count"] = float(len(tool_list))
        if agent.metadata:
            metrics["metadata_keys"] = float(len(agent.metadata))
            avg_key_len = sum(len(k) for k in agent.metadata.keys()) / max(1, len(agent.metadata))
            metrics["avg_metadata_key_length"] = avg_key_len
        return metrics

    async def get_impossible_travel_detection(
        self,
        tenant_id: str,
        agent_id: str,
        prev_location: dict[str, Any],
        current_location: dict[str, Any],
        prev_timestamp: datetime,
    ) -> AnomalyDetectionResult | None:
        return self._detect_impossible_travel(
            agent_id, prev_location, current_location, prev_timestamp
        )

    def configure_detection_thresholds(
        self,
        *,
        max_travel_speed_kmh: float | None = None,
        max_actions_per_minute: int | None = None,
        max_child_creations: int | None = None,
        impossible_time_window_seconds: float | None = None,
        behavioral_deviation_threshold: float | None = None,
        geographic_anomaly_threshold: float | None = None,
    ) -> None:
        if max_travel_speed_kmh is not None:
            self._max_travel_speed_kmh = max_travel_speed_kmh
        if max_actions_per_minute is not None:
            self._max_actions_per_minute = max_actions_per_minute
        if max_child_creations is not None:
            self._max_child_creations_per_session = max_child_creations
        if impossible_time_window_seconds is not None:
            self._impossible_time_window_seconds = impossible_time_window_seconds
        if behavioral_deviation_threshold is not None:
            self._behavioral_deviation_threshold = behavioral_deviation_threshold
        if geographic_anomaly_threshold is not None:
            self._geographic_anomaly_threshold = geographic_anomaly_threshold
