from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


class AgentStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    QUARANTINED = "quarantined"
    REVOKED = "revoked"
    EXPIRED = "expired"


class AgentType(StrEnum):
    USER_AGENT = "user_agent"
    SERVICE_AGENT = "service_agent"
    SUB_AGENT = "sub_agent"
    TOOL_AGENT = "tool_agent"
    UNKNOWN = "unknown"


class TrustLevel(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    UNKNOWN = "unknown"
    DISCOVERED = "discovered"


class RiskClassification(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RegistrationMethod(StrEnum):
    MANUAL = "manual"
    API = "api"
    AUTO_DISCOVERED = "auto_discovered"
    AGENT_CREATED = "agent_created"
    SSO_PROVISIONED = "sso_provisioned"


class AgentEnvironment(StrEnum):
    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"
    TEST = "test"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Agent:
    """Registered AI agent aggregate root with full lineage and identity.

    Distinguishes human-created, system-created, agent-created, and
    externally discovered agents.  For agent-created agents the
    ``creator`` field holds the parent agent ID and the root human
    sponsor is preserved via ``root_human_sponsor``.
    """

    agent_id: str
    tenant_id: str
    name: str
    description: str = ""
    owner_user_id: UUID | None = None
    parent_agent_id: str | None = None
    agent_type: AgentType = AgentType.UNKNOWN
    status: AgentStatus = AgentStatus.ACTIVE
    trust_level: TrustLevel = TrustLevel.UNKNOWN
    risk_classification: RiskClassification = RiskClassification.MEDIUM
    model_provider: str | None = None
    model_name: str | None = None
    environment: AgentEnvironment = AgentEnvironment.UNKNOWN
    version: str = "1.0"
    creator: str | None = None
    registration_method: RegistrationMethod = RegistrationMethod.MANUAL
    root_human_sponsor: str | None = None
    expires_at: datetime | None = None
    last_activity_at: datetime | None = None
    connected_tools: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
