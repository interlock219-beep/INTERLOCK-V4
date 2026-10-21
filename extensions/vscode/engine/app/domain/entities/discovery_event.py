from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class DiscoveryStatus(StrEnum):
    DISCOVERED = "discovered"
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    UNKNOWN = "unknown"


class DiscoverySource(StrEnum):
    MANUAL = "manual"
    API = "api"
    CONNECTOR = "connector"
    EVENT = "event"


@dataclass(frozen=True, slots=True)
class DiscoveryEvent:
    """Discovery event for an agent or resource."""

    discovery_id: str
    tenant_id: str
    source: DiscoverySource
    discovery_status: DiscoveryStatus = DiscoveryStatus.DISCOVERED
    agent_id: str | None = None
    resource_type: str = ""
    resource_id: str = ""
    resource_metadata: dict[str, str] = field(default_factory=dict)
    finding_severity: str = "info"
    finding_message: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
