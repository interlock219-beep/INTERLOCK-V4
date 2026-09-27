from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.domain.entities.agent import AgentType, TrustLevel
from app.domain.repositories.agent_repository import AgentRepository
from app.infrastructure.observability.metrics import metrics

logger = logging.getLogger("intentlock.identity_compromise")


class IdentityCompromiseIndicator:
    """Represents a potential identity compromise signal."""

    def __init__(
        self,
        agent_id: str,
        indicator_type: str,
        severity: str,
        description: str,
        detected_at: datetime,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.indicator_type = indicator_type
        self.severity = severity
        self.description = description
        self.detected_at = detected_at
        self.evidence = evidence or {}


class IdentityCompromiseService:
    """Detect potential identity compromise signals.

    IDY-024: Agent identity compromise indicator.
    Monitors for signals that an agent identity may have been compromised,
    including unexpected privilege changes, location anomalies, and
    behavioral deviations.
    """

    def __init__(self, agent_repository: AgentRepository) -> None:
        self._agent_repo = agent_repository

    async def check_compromise_indicators(
        self,
        tenant_id: str,
        agent_id: str,
    ) -> list[IdentityCompromiseIndicator]:
        """Check for identity compromise indicators for an agent."""
        indicators: list[IdentityCompromiseIndicator] = []
        agent = await self._agent_repo.get_by_agent_id(tenant_id, agent_id)

        if agent is None:
            return indicators

        if agent.trust_level in (TrustLevel.UNVERIFIED, TrustLevel.DISCOVERED):
            indicators.append(
                IdentityCompromiseIndicator(
                    agent_id=agent_id,
                    indicator_type="low_trust_level",
                    severity="medium",
                    description=(f"Agent has low trust level: {agent.trust_level.value}"),
                    detected_at=datetime.now(UTC),
                    evidence={"trust_level": agent.trust_level.value},
                )
            )

        if agent.agent_type == AgentType.UNKNOWN:
            indicators.append(
                IdentityCompromiseIndicator(
                    agent_id=agent_id,
                    indicator_type="unknown_agent_type",
                    severity="low",
                    description="Agent type is unknown",
                    detected_at=datetime.now(UTC),
                    evidence={"agent_type": agent.agent_type.value},
                )
            )

        if not agent.description:
            indicators.append(
                IdentityCompromiseIndicator(
                    agent_id=agent_id,
                    indicator_type="missing_description",
                    severity="low",
                    description="Agent has no description",
                    detected_at=datetime.now(UTC),
                )
            )

        if not agent.owner_user_id:
            indicators.append(
                IdentityCompromiseIndicator(
                    agent_id=agent_id,
                    indicator_type="unowned_agent",
                    severity="medium",
                    description="Agent has no assigned owner",
                    detected_at=datetime.now(UTC),
                )
            )

        if indicators:
            logger.warning(
                "Identity compromise indicators found for agent %s: %d indicators",
                agent_id,
                len(indicators),
            )
            metrics.increment_security_exception("identity_compromise_indicators_found")

        return indicators

    async def get_compromise_summary(
        self,
        tenant_id: str,
    ) -> dict[str, Any]:
        """Get a summary of compromise indicators across all agents."""
        agents, _ = await self._agent_repo.list_by_tenant(tenant_id, limit=1000, offset=0)

        total_agents = len(agents)
        compromised_count = 0
        indicators_by_type: dict[str, int] = {}

        for agent in agents:
            agent_indicators = await self.check_compromise_indicators(tenant_id, agent.agent_id)
            if agent_indicators:
                compromised_count += 1
                for indicator in agent_indicators:
                    indicators_by_type[indicator.indicator_type] = (
                        indicators_by_type.get(indicator.indicator_type, 0) + 1
                    )

        return {
            "tenant_id": tenant_id,
            "total_agents": total_agents,
            "agents_with_indicators": compromised_count,
            "indicators_by_type": indicators_by_type,
            "checked_at": datetime.now(UTC).isoformat(),
        }
