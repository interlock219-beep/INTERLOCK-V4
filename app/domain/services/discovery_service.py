from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from app.domain.entities.agent import (
    Agent,
    AgentType,
    RegistrationMethod,
    TrustLevel,
)
from app.domain.entities.discovery_event import DiscoveryEvent, DiscoverySource, DiscoveryStatus
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.discovery_event_repository import DiscoveryEventRepository
from app.infrastructure.logging.audit_logger import log_security_event
from app.infrastructure.observability.metrics import metrics


class DiscoveryService:
    """Discovery foundation with manual, API, and connector-based registration."""

    def __init__(
        self,
        agent_repository: AgentRepository,
        discovery_repository: DiscoveryEventRepository,
    ) -> None:
        self._agent_repo = agent_repository
        self._discovery_repo = discovery_repository

    async def register_agent(
        self,
        tenant_id: str,
        agent_id: str,
        name: str,
        source: DiscoverySource,
        *,
        description: str = "",
        agent_type: AgentType = AgentType.UNKNOWN,
        trust_level: TrustLevel = TrustLevel.DISCOVERED,
        owner_user_id: Any = None,
        resource_metadata: dict[str, str] | None = None,
        finding_severity: str = "info",
        finding_message: str = "",
    ) -> tuple[Agent, DiscoveryEvent]:
        discovery_id = f"disc-{secrets.token_hex(12)}"
        existing = await self._agent_repo.get_by_agent_id(tenant_id, agent_id)
        if existing is None:
            source_to_method = {
                "manual": RegistrationMethod.MANUAL,
                "api": RegistrationMethod.API,
                "connector": RegistrationMethod.AUTO_DISCOVERED,
                "event": RegistrationMethod.AUTO_DISCOVERED,
            }
            registration_method = source_to_method.get(
                source.value, RegistrationMethod.API
            )
            agent = Agent(
                agent_id=agent_id,
                tenant_id=tenant_id,
                name=name,
                description=description,
                owner_user_id=owner_user_id,
                agent_type=agent_type,
                trust_level=trust_level,
                registration_method=registration_method,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            agent = await self._agent_repo.save(agent)
        else:
            agent = existing
        event = DiscoveryEvent(
            discovery_id=discovery_id,
            tenant_id=tenant_id,
            source=source,
            discovery_status=DiscoveryStatus(trust_level.value),
            agent_id=agent_id,
            resource_type="agent",
            resource_id=agent_id,
            resource_metadata=resource_metadata or {},
            finding_severity=finding_severity,
            finding_message=finding_message or f"Agent discovered via {source.value}",
            created_at=datetime.now(UTC),
        )
        event = await self._discovery_repo.save(event)
        log_security_event(
            "agent_discovered",
            tenant_id=tenant_id,
            discovery_id=discovery_id,
            agent_id=agent_id,
            source=source.value,
            discovery_status=trust_level.value,
            finding_severity=finding_severity,
        )
        metrics.increment_security_exception("agent_discovered")
        return agent, event

    async def ingest_discovery_event(
        self,
        tenant_id: str,
        source: DiscoverySource,
        resource_type: str,
        resource_id: str,
        *,
        agent_id: str | None = None,
        resource_metadata: dict[str, str] | None = None,
        finding_severity: str = "info",
        finding_message: str = "",
    ) -> DiscoveryEvent:
        discovery_id = f"disc-{secrets.token_hex(12)}"
        if agent_id and resource_type == "agent":
            existing = await self._agent_repo.get_by_agent_id(tenant_id, agent_id)
            discovery_status = DiscoveryStatus.DISCOVERED
            if existing and existing.trust_level:
                discovery_status = DiscoveryStatus(existing.trust_level.value)
            if finding_severity in ("high", "critical"):
                discovery_status = DiscoveryStatus.UNVERIFIED
                log_security_event(
                    "unknown_agent_detected",
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    severity=finding_severity,
                    message=finding_message,
                )
        else:
            discovery_status = DiscoveryStatus.DISCOVERED
        event = DiscoveryEvent(
            discovery_id=discovery_id,
            tenant_id=tenant_id,
            source=source,
            discovery_status=discovery_status,
            agent_id=agent_id,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_metadata=resource_metadata or {},
            finding_severity=finding_severity,
            finding_message=finding_message,
            created_at=datetime.now(UTC),
        )
        return await self._discovery_repo.save(event)
