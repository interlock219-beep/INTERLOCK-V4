from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class ContainmentMode(StrEnum):
    OBSERVE = "observe"
    RESTRICT = "restrict"
    SUSPEND = "suspend"
    QUARANTINE = "quarantine"
    REVOKE = "revoke"


class ContainmentStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass(frozen=True, slots=True)
class ContainmentEvent:
    """Containment action record."""

    containment_id: str
    tenant_id: str
    target_agent_id: str
    target_authority_id: str | None
    mode: ContainmentMode
    status: ContainmentStatus = ContainmentStatus.PENDING
    initiated_by: str = ""
    authorized_by: str = ""
    reason: str = ""
    affected_agent_ids: list[str] = field(default_factory=list)
    affected_authority_ids: list[str] = field(default_factory=list)
    affected_session_ids: list[str] = field(default_factory=list)
    affected_token_ids: list[str] = field(default_factory=list)
    affected_action_ids: list[str] = field(default_factory=list)
    dry_run: bool = False
    result_details: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
