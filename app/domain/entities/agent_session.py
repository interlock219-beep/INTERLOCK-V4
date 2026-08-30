from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class AgentSessionStatus(StrEnum):
    CREATED = "created"
    ACTIVE = "active"
    FROZEN = "frozen"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPROMISED = "compromised"
    ROLLBACK_PENDING = "rollback_pending"
    ROLLING_BACK = "rolling_back"
    RECOVERED = "recovered"
    PARTIALLY_RECOVERED = "partially_recovered"
    RECOVERY_FAILED = "recovery_failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class AgentSession:
    """Durable agent session that serves as the fundamental rollback boundary."""

    session_id: str
    tenant_id: str
    agent_id: str
    intent_id: str | None = None
    policy_version: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    status: AgentSessionStatus = AgentSessionStatus.CREATED
    risk_level: str = "low"
    correlation_id: str = ""
    parent_session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
