from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from app.domain.entities.surgical_recovery_types import Reversibility


class ActionStatus(StrEnum):
    PENDING = "pending"
    EVALUATING = "evaluating"
    PERMITTED = "permitted"
    DENIED = "denied"
    REQUIRES_APPROVAL = "requires_approval"
    EXECUTED = "executed"
    FAILED = "failed"
    CONTAINED = "contained"


@dataclass(frozen=True, slots=True)
class ProtectedAction:
    """Protected action journal entry."""

    action_id: str
    tenant_id: str
    actor_user_id: UUID | None
    agent_id: str
    authority_grant_id: str | None
    tool: str
    resource: str
    action_type: str
    risk_score: float = 0.0
    policy_version: str | None = None
    correlation_id: str = ""
    parent_action_id: str | None = None
    workflow_id: str | None = None
    reversibility: Reversibility = Reversibility.UNKNOWN
    before_state_ref: str | None = None
    after_state_ref: str | None = None
    tool_arguments: dict[str, str] = field(default_factory=dict)
    status: ActionStatus = ActionStatus.PENDING
    decision_reason: str = ""
    evaluated_at: datetime | None = None
    executed_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


__all__ = ["ProtectedAction", "ActionStatus", "Reversibility"]
