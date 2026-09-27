from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class AgentEnvironment(StrEnum):
    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"
    TEST = "test"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AuthorizationContext:
    """Immutable bundle of identities for an authorization decision."""

    user_id: UUID
    agent_id: str
    proposed_tool: str
    tenant_id: str | None = None
    action: str = "execute"
    resource: str = ""
    service_id: str | None = None
    user_role: str | None = None
    authorized_at: datetime | None = field(default=None, kw_only=True)

    task_id: str | None = None
    resource_type_hierarchy: str | None = None
    parameter_hash: str | None = None
    parameter_constraints: dict[str, Any] = field(default_factory=dict)
    environment: AgentEnvironment = AgentEnvironment.UNKNOWN
    agent_history: list[dict[str, Any]] = field(default_factory=list)
    dependency_state: dict[str, str] = field(default_factory=dict)
    incident_state: dict[str, Any] = field(default_factory=dict)
    recovery_state: dict[str, Any] = field(default_factory=dict)
    authority_grants: list[dict[str, Any]] = field(default_factory=list)
    recent_actions: list[dict[str, Any]] = field(default_factory=list)
    risk_threshold: float = 0.7
    jit_ttl_seconds: int = 300
    one_shot: bool = False
    require_task_scoping: bool = False
    max_delegation_depth: int = 9
    session_id: str | None = None
    intent_id: str | None = None
    expected_parameter_hash: str | None = None
    agent_history_required: bool = False
