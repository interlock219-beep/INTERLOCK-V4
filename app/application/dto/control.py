from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ContainmentRequest(BaseModel):
    target_agent_id: str = Field(..., min_length=1, max_length=255)
    mode: str = Field(..., pattern=r"^(observe|restrict|suspend|quarantine|revoke)$")
    target_authority_id: str | None = None
    reason: str = Field(default="", max_length=1024)
    dry_run: bool = Field(default=False)


class ContainmentResponse(BaseModel):
    containment_id: str
    tenant_id: str
    target_agent_id: str
    target_authority_id: str | None
    mode: str
    status: str
    dry_run: bool
    affected_agent_ids: list[str]
    affected_authority_ids: list[str]
    affected_session_ids: list[str]
    affected_token_ids: list[str]
    affected_action_ids: list[str]
    result_details: dict[str, str]
    created_at: datetime
    completed_at: datetime | None


class RecoverySimulateRequest(BaseModel):
    incident_action_id: str = Field(..., min_length=1, max_length=64)
    recovery_steps: list[dict[str, str]] = Field(default_factory=list)


class RecoveryPlanResponse(BaseModel):
    plan_id: str
    tenant_id: str
    incident_action_id: str
    status: str
    outcome: str
    simulation_result: dict[str, Any]
    steps: list[dict[str, str]]
    approved_by: str | None
    executed_by: str | None
    created_at: datetime
    updated_at: datetime
    executed_at: datetime | None
    plan_version: str = "1.0"
    plan_hash: str = ""
    topological_order: list[str] = Field(default_factory=list)
    dependency_graph_reference: str = ""
    execution_status: str = "pending"
    approval_policy: str = "single_approval"
    approval_threshold: int = 1
    stop_conditions: list[str] = Field(default_factory=list)
    compensation_summary: dict[str, Any] = Field(default_factory=dict)
    incident_id: str = ""
    root_action_id: str = ""
    affected_action_ids: list[str] = Field(default_factory=list)


class RecoveryExecuteRequest(BaseModel):
    plan_id: str = Field(..., min_length=1, max_length=64)
    approved_by: str = Field(..., min_length=1, max_length=255)


class RecoveryEvidenceResponse(BaseModel):
    evidence_id: str
    action_id: str
    tenant_id: str
    agent_id: str
    authority_grant_id: str | None
    parent_action_id: str | None
    root_action_id: str | None
    correlation_id: str
    incident_id: str | None
    target_system: str
    target_resource: str
    action_type: str
    before_state_reference: str | None
    after_state_reference: str | None
    request_payload_reference: str | None
    response_payload_reference: str | None
    compensation_payload: dict[str, Any]
    compensation_type: str
    recovery_adapter_type: str
    idempotency_key: str
    dependency_edges: list[str]
    reversibility_classification: str
    state_version: str | None
    state_hash: str | None
    resource_version: str | None
    verification_requirements: list[str]
    recovery_metadata: dict[str, Any]
    evidence_hash: str
    adapter_capability: str
    created_at: datetime


class RecoveryExecutionResponse(BaseModel):
    execution_id: str
    plan_id: str
    action_id: str
    tenant_id: str
    compensation_type: str
    target_system: str
    target_resource: str
    idempotency_key: str
    execution_order: int
    execution_state: str
    success: bool
    error: str | None
    details: dict[str, Any]
    external_outcome: str
    verification_passed: bool
    verification_details: dict[str, Any]
    started_at: datetime | None
    completed_at: datetime | None
    executed_by: str | None
    created_at: datetime


class RecoveryExecutionListResponse(BaseModel):
    items: list[RecoveryExecutionResponse]
    total: int
    limit: int
    offset: int


class SurgicalRecoveryPlanResponse(BaseModel):
    plan_id: str
    tenant_id: str
    incident_action_id: str
    status: str
    outcome: str
    simulation_result: dict[str, Any]
    steps: list[dict[str, str]]
    approved_by: str | None
    executed_by: str | None
    created_at: datetime
    updated_at: datetime
    executed_at: datetime | None
    plan_version: str
    plan_hash: str
    topological_order: list[str]
    dependency_graph_reference: str
    execution_status: str
    approval_policy: str
    approval_threshold: int
    stop_conditions: list[str]
    compensation_summary: dict[str, Any]
    incident_id: str
    root_action_id: str
    affected_action_ids: list[str]


class RecoveryEvidenceListResponse(BaseModel):
    items: list[RecoveryEvidenceResponse]
    total: int
    limit: int
    offset: int


class DiscoveryRegisterRequest(BaseModel):
    agent_id: str | None = Field(default=None, max_length=255)
    source: str = Field(..., pattern=r"^(manual|api|connector|event)$")
    resource_type: str = Field(default="", max_length=64)
    resource_id: str = Field(default="", max_length=255)
    resource_metadata: dict[str, str] = Field(default_factory=dict)
    finding_severity: str = Field(default="info", pattern=r"^(info|low|medium|high|critical)$")
    finding_message: str = Field(default="", max_length=1024)


class DiscoveryEventResponse(BaseModel):
    discovery_id: str
    tenant_id: str
    source: str
    discovery_status: str
    agent_id: str | None
    resource_type: str
    resource_id: str
    finding_severity: str
    finding_message: str
    created_at: datetime
