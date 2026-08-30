"""Test data factories for recovery validation."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.domain.entities.agent_session import AgentSession, AgentSessionStatus
from app.domain.entities.incident import Incident, IncidentSeverity, IncidentStatus
from app.domain.entities.protected_action import ActionStatus, ProtectedAction, Reversibility
from app.domain.entities.recovery_plan import RecoveryPlan, RecoveryStatus
from app.domain.entities.surgical_recovery_types import (
    AdapterCapability,
    CompensationAction,
    CompensationResult,
    CompensationType,
    ConflictStatus,
    DriftStatus,
    ExecutionState,
    RecoveryAdapterType,
    RecoveryEvidence,
)


def make_action(
    action_id: str | None = None,
    tenant_id: str = "test-tenant",
    agent_id: str = "agent-test",
    tool: str = "filesystem",
    resource: str = "file:test.txt",
    action_type: str = "write",
    reversibility: Reversibility = Reversibility.AUTOMATICALLY_REVERSIBLE,
    before_state_ref: str | None = "state:before:123",
    after_state_ref: str | None = "state:after:456",
    parent_action_id: str | None = None,
    status: ActionStatus = ActionStatus.EXECUTED,
    workflow_id: str | None = None,
    correlation_id: str = "",
) -> ProtectedAction:
    """Factory for ProtectedAction with sensible defaults."""
    return ProtectedAction(
        action_id=action_id or f"act-{uuid4().hex[:12]}",
        tenant_id=tenant_id,
        actor_user_id=uuid4(),
        agent_id=agent_id,
        authority_grant_id=None,
        tool=tool,
        resource=resource,
        action_type=action_type,
        risk_score=0.5,
        policy_version="v1",
        correlation_id=correlation_id or f"corr-{uuid4().hex[:8]}",
        parent_action_id=parent_action_id,
        workflow_id=workflow_id,
        reversibility=reversibility,
        before_state_ref=before_state_ref,
        after_state_ref=after_state_ref,
        tool_arguments={"path": resource},
        status=status,
        decision_reason="test",
        evaluated_at=datetime.now(UTC),
        executed_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


def make_evidence(action: ProtectedAction) -> RecoveryEvidence:
    """Factory for RecoveryEvidence from a ProtectedAction."""
    return RecoveryEvidence(
        evidence_id=f"ev-{action.action_id}",
        action_id=action.action_id,
        tenant_id=action.tenant_id,
        agent_id=action.agent_id,
        authority_grant_id=action.authority_grant_id,
        parent_action_id=action.parent_action_id,
        root_action_id=action.parent_action_id or action.action_id,
        correlation_id=action.correlation_id,
        incident_id="",
        target_system=action.tool,
        target_resource=action.resource,
        action_type=action.action_type,
        before_state_reference=action.before_state_ref or f"mock:{action.action_id}:before",
        after_state_reference=action.after_state_ref or f"mock:{action.action_id}:after",
        compensation_payload={"operation": "mock_revert", "target": action.resource},
        compensation_type=CompensationType.REVERSE_OPERATION,
        recovery_adapter_type=RecoveryAdapterType.MOCK,
        idempotency_key=f"idem-{action.action_id}",
        dependency_edges=[],
        reversibility_classification=action.reversibility,
        state_version=action.policy_version,
        evidence_hash=f"hash-{action.action_id}",
        adapter_capability=AdapterCapability.MOCK,
        verification_requirements=["mock_verification"],
    )


def make_plan(
    plan_id: str | None = None,
    tenant_id: str = "test-tenant",
    incident_action_id: str = "act-root",
    status: RecoveryStatus = RecoveryStatus.DRAFT,
    topological_order: list[str] | None = None,
) -> RecoveryPlan:
    """Factory for RecoveryPlan with sensible defaults."""
    return RecoveryPlan(
        plan_id=plan_id or f"plan-{uuid4().hex[:12]}",
        tenant_id=tenant_id,
        incident_action_id=incident_action_id,
        status=status,
        outcome=RecoveryStatus.SIMULATED,
        topological_order=topological_order or [incident_action_id],
    )


def make_session(
    session_id: str | None = None,
    tenant_id: str = "test-tenant",
    agent_id: str = "agent-test",
    status: AgentSessionStatus = AgentSessionStatus.ACTIVE,
) -> AgentSession:
    """Factory for AgentSession with sensible defaults."""
    return AgentSession(
        session_id=session_id or f"sess-{uuid4().hex[:12]}",
        tenant_id=tenant_id,
        agent_id=agent_id,
        status=status,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def make_incident(
    incident_id: str | None = None,
    tenant_id: str = "test-tenant",
    agent_id: str = "agent-test",
    session_ids: list[str] | None = None,
) -> Incident:
    """Factory for Incident with sensible defaults."""
    return Incident(
        incident_id=incident_id or f"inc-{uuid4().hex[:12]}",
        tenant_id=tenant_id,
        agent_id=agent_id,
        severity=IncidentSeverity.HIGH,
        status=IncidentStatus.DETECTED,
        trigger="test",
        session_ids=session_ids or [],
        affected_action_ids=[],
    )


def make_compensation(
    action_id: str = "act-1",
    compensation_type: CompensationType = CompensationType.REVERSE_OPERATION,
    execution_state: ExecutionState = ExecutionState.PENDING,
) -> CompensationAction:
    """Factory for CompensationAction."""
    return CompensationAction(
        action_id=action_id,
        incident_action_id=action_id,
        compensation_type=compensation_type,
        compensation_payload={"operation": "mock_revert", "target": f"file:{action_id}.txt"},
        idempotency_key=f"idem-{action_id}",
        target_system="mock",
        target_resource=f"file:{action_id}.txt",
        execution_order=0,
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
        drift_status=DriftStatus.NO_DRIFT,
        conflict_status=ConflictStatus.NO_CONFLICT,
        verification_requirements=["mock_verification"],
        dependency_edges=[],
    )


def make_compensation_result(
    action_id: str = "act-1",
    success: bool = False,
    execution_state: ExecutionState = ExecutionState.REQUIRES_MANUAL_ACTION,
) -> CompensationResult:
    """Factory for CompensationResult."""
    return CompensationResult(
        action_id=action_id,
        success=success,
        execution_state=execution_state,
        idempotency_key=f"idem-{action_id}",
        details={"operation": "mock_revert"},
        external_outcome="mock_not_implemented",
        error="MockRecoveryAdapter does not perform actual recovery.",
    )
