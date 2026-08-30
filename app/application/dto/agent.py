from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentCreateRequest(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="", max_length=1024)
    agent_type: str = Field(
        default="unknown",
        pattern=r"^(user_agent|service_agent|sub_agent|tool_agent|unknown)$",
    )
    parent_agent_id: str | None = None
    model_provider: str | None = Field(default=None, max_length=64)
    model_name: str | None = Field(default=None, max_length=128)
    environment: str = Field(
        default="unknown",
        pattern=r"^(production|staging|development|test|unknown)$",
    )
    version: str | None = Field(default=None, max_length=64)
    creator: str | None = Field(default=None, max_length=255)
    registration_method: str = Field(
        default="manual",
        pattern=r"^(manual|api|auto_discovered|agent_created|sso_provisioned)$",
    )
    root_human_sponsor: str | None = Field(default=None, max_length=255)
    connected_tools: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=50)
    expires_at: datetime | None = None


class AgentUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1024)
    status: str | None = Field(
        default=None,
        pattern=r"^(active|suspended|quarantined|revoked|expired)$",
    )
    trust_level: str | None = Field(
        default=None,
        pattern=r"^(verified|unverified|unknown|discovered)$",
    )
    risk_classification: str | None = Field(default=None, pattern=r"^(low|medium|high|critical)$")
    environment: str | None = Field(
        default=None,
        pattern=r"^(production|staging|development|test|unknown)$",
    )
    version: str | None = Field(default=None, max_length=64)
    connected_tools: list[str] | None = None
    metadata: dict[str, Any] | None = None
    expires_at: datetime | None = None


class AgentResponse(BaseModel):
    agent_id: str
    tenant_id: str
    name: str
    description: str
    agent_type: str
    status: str
    trust_level: str
    risk_classification: str
    parent_agent_id: str | None
    model_provider: str | None
    model_name: str | None
    environment: str
    version: str
    creator: str | None
    registration_method: str
    root_human_sponsor: str | None
    owner_user_id: str | None = None
    connected_tools: list[str]
    expires_at: datetime | None
    last_activity_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AgentListResponse(BaseModel):
    items: list[AgentResponse]
    total: int
    limit: int
    offset: int


class AuthorityGrantCreateRequest(BaseModel):
    grantor_agent_id: str = Field(..., min_length=1, max_length=255)
    grantee_agent_id: str = Field(..., min_length=1, max_length=255)
    scope: str = Field(..., pattern=r"^(read|write|execute|admin|custom)$")
    resource: str = Field(..., min_length=1, max_length=255)
    conditions: dict[str, str] = Field(default_factory=dict)
    expires_at: datetime | None = None
    delegation_depth: int = Field(default=0, ge=0, le=9)
    parent_authority_id: str | None = None


class AuthorityGrantResponse(BaseModel):
    grant_id: str
    tenant_id: str
    grantor_agent_id: str
    grantee_agent_id: str
    scope: str
    resource: str
    conditions: dict[str, str]
    expires_at: datetime | None
    delegation_depth: int
    parent_authority_id: str | None
    root_authority_id: str | None
    status: str
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AuthorityGrantListResponse(BaseModel):
    items: list[AuthorityGrantResponse]
    total: int
    limit: int
    offset: int


class ProtectedActionCreateRequest(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=255)
    tool: str = Field(..., min_length=1, max_length=255)
    resource: str = Field(..., min_length=1, max_length=255)
    action_type: str = Field(..., min_length=1, max_length=64)
    authority_grant_id: str | None = None
    correlation_id: str = Field(default="", max_length=64)
    parent_action_id: str | None = None
    workflow_id: str | None = None
    tool_arguments: dict[str, str] = Field(default_factory=dict)
    before_state_ref: str | None = None


class ProtectedActionResponse(BaseModel):
    action_id: str
    tenant_id: str
    agent_id: str
    tool: str
    resource: str
    action_type: str
    status: str
    risk_score: float
    reversibility: str
    authority_grant_id: str | None
    correlation_id: str
    parent_action_id: str | None
    workflow_id: str | None
    decision_reason: str
    created_at: datetime
    evaluated_at: datetime | None
    executed_at: datetime | None


class ProtectedActionListResponse(BaseModel):
    items: list[ProtectedActionResponse]
    total: int
    limit: int
    offset: int
