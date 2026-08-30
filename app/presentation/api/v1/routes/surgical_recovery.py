from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.application.dto.auth import UserResponse
from app.application.dto.control import (
    RecoveryEvidenceListResponse,
    RecoveryEvidenceResponse,
    RecoveryExecutionListResponse,
    RecoveryExecutionResponse,
    RecoveryPlanResponse,
    SurgicalRecoveryPlanResponse,
)
from app.domain.entities.recovery_plan import RecoveryPlan
from app.domain.entities.surgical_recovery_types import (
    RecoveryEvidence,
    RecoveryExecution,
)
from app.domain.repositories.containment_repository import RecoveryPlanRepository
from app.domain.repositories.protected_action_repository import (
    ProtectedActionRepository,
)
from app.domain.repositories.recovery_evidence_repository import RecoveryEvidenceRepository
from app.domain.repositories.recovery_execution_repository import RecoveryExecutionRepository
from app.domain.services.recovery_planning_service import RecoveryPlanningService
from app.infrastructure.logging.audit_logger import log_security_event
from app.infrastructure.persistence.repositories.sqlalchemy_containment_repository import (
    SQLAlchemyRecoveryPlanRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_protected_action_repository import (
    SQLAlchemyProtectedActionRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_recovery_evidence_repository import (
    SQLAlchemyRecoveryEvidenceRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_recovery_execution_repository import (
    SQLAlchemyRecoveryExecutionRepository,
)
from app.infrastructure.recovery.config_rollback_adapter import ConfigRollbackAdapter
from app.infrastructure.recovery.database_record_adapter import DatabaseRecordAdapter
from app.infrastructure.recovery.file_version_adapter import FileVersionAdapter
from app.presentation.api.dependencies.auth import (
    CurrentUser,
    _get_session,
    get_user_tenant_id,
    require_recovery_executor,
)

router = APIRouter(tags=["Surgical Recovery"])
DEFAULT_LIMIT = 100
MAX_LIMIT = 500


def _get_evidence_repo(
    session: Annotated[Session, Depends(_get_session)],
) -> RecoveryEvidenceRepository:
    return SQLAlchemyRecoveryEvidenceRepository(session)


def _get_execution_repo(
    session: Annotated[Session, Depends(_get_session)],
) -> RecoveryExecutionRepository:
    return SQLAlchemyRecoveryExecutionRepository(session)


def _get_plan_repo(
    session: Annotated[Session, Depends(_get_session)],
) -> RecoveryPlanRepository:
    return SQLAlchemyRecoveryPlanRepository(session)


def _get_action_repo(
    session: Annotated[Session, Depends(_get_session)],
) -> ProtectedActionRepository:
    return SQLAlchemyProtectedActionRepository(session)


def _get_adapters(
    session: Annotated[Session, Depends(_get_session)],
) -> list[Any]:
    return [
        DatabaseRecordAdapter(),
        ConfigRollbackAdapter(),
        FileVersionAdapter(),
    ]


def _get_recovery_service(
    action_repo: Annotated[Any, Depends(_get_action_repo)],
    plan_repo: Annotated[RecoveryPlanRepository, Depends(_get_plan_repo)],
    adapters: Annotated[list[Any], Depends(_get_adapters)],
) -> RecoveryPlanningService:
    return RecoveryPlanningService(action_repo, plan_repo, adapters)


def _evidence_to_response(evidence: RecoveryEvidence) -> RecoveryEvidenceResponse:
    return RecoveryEvidenceResponse(
        evidence_id=evidence.evidence_id,
        action_id=evidence.action_id,
        tenant_id=evidence.tenant_id,
        agent_id=evidence.agent_id,
        authority_grant_id=evidence.authority_grant_id,
        parent_action_id=evidence.parent_action_id,
        root_action_id=evidence.root_action_id,
        correlation_id=evidence.correlation_id,
        incident_id=evidence.incident_id,
        target_system=evidence.target_system,
        target_resource=evidence.target_resource,
        action_type=evidence.action_type,
        before_state_reference=evidence.before_state_reference,
        after_state_reference=evidence.after_state_reference,
        request_payload_reference=evidence.request_payload_reference,
        response_payload_reference=evidence.response_payload_reference,
        compensation_payload=evidence.compensation_payload,
        compensation_type=evidence.compensation_type.value,
        recovery_adapter_type=evidence.recovery_adapter_type.value,
        idempotency_key=evidence.idempotency_key,
        dependency_edges=evidence.dependency_edges,
        reversibility_classification=evidence.reversibility_classification.value,
        state_version=evidence.state_version,
        state_hash=evidence.state_hash,
        resource_version=evidence.resource_version,
        verification_requirements=evidence.verification_requirements,
        recovery_metadata=evidence.recovery_metadata,
        evidence_hash=evidence.evidence_hash,
        adapter_capability=evidence.adapter_capability.value,
        created_at=evidence.created_at,
    )


def _execution_to_response(execution: RecoveryExecution) -> RecoveryExecutionResponse:
    return RecoveryExecutionResponse(
        execution_id=execution.execution_id,
        plan_id=execution.plan_id,
        action_id=execution.action_id,
        tenant_id=execution.tenant_id,
        compensation_type=execution.compensation_type.value,
        target_system=execution.target_system,
        target_resource=execution.target_resource,
        idempotency_key=execution.idempotency_key,
        execution_order=execution.execution_order,
        execution_state=execution.execution_state.value,
        success=execution.success,
        error=execution.error,
        details=execution.details,
        external_outcome=execution.external_outcome,
        verification_passed=execution.verification_passed,
        verification_details=execution.verification_details,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        executed_by=execution.executed_by,
        created_at=execution.created_at,
    )


def _plan_to_response(plan: RecoveryPlan) -> SurgicalRecoveryPlanResponse:
    return SurgicalRecoveryPlanResponse(
        plan_id=plan.plan_id,
        tenant_id=plan.tenant_id,
        incident_action_id=plan.incident_action_id,
        status=plan.status.value,
        outcome=plan.outcome.value,
        simulation_result=plan.simulation_result,
        steps=plan.steps,
        approved_by=plan.approved_by,
        executed_by=plan.executed_by,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        executed_at=plan.executed_at,
        plan_version=plan.plan_version,
        plan_hash=plan.plan_hash,
        topological_order=plan.topological_order,
        dependency_graph_reference=plan.dependency_graph_reference,
        execution_status=plan.execution_status,
        approval_policy=plan.approval_policy,
        approval_threshold=plan.approval_threshold,
        stop_conditions=plan.stop_conditions,
        compensation_summary=plan.compensation_summary,
        incident_id=plan.incident_id,
        root_action_id=plan.root_action_id,
        affected_action_ids=plan.affected_action_ids,
    )


@router.get(
    "/recovery/evidence",
    response_model=RecoveryEvidenceListResponse,
)
async def list_recovery_evidence(
    current_user: CurrentUser,
    evidence_repo: Annotated[
        RecoveryEvidenceRepository, Depends(_get_evidence_repo)
    ],
    incident_id: str = Query(default="", min_length=0),
    root_action_id: str = Query(default="", min_length=0),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> RecoveryEvidenceListResponse:
    if incident_id:
        items, total = await evidence_repo.list_by_incident(
            get_user_tenant_id(current_user),
            incident_id,
            limit=limit,
            offset=offset,
        )
    elif root_action_id:
        items, total = await evidence_repo.list_by_root_action(
            get_user_tenant_id(current_user),
            root_action_id,
            limit=limit,
            offset=offset,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either incident_id or root_action_id must be provided",
        )
    log_security_event(
        "recovery_evidence_listed",
        tenant_id=get_user_tenant_id(current_user),
        count=total,
    )
    return RecoveryEvidenceListResponse(
        items=[_evidence_to_response(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/recovery/evidence/{evidence_id}",
    response_model=RecoveryEvidenceResponse,
)
async def get_recovery_evidence(
    evidence_id: str,
    current_user: CurrentUser,
    evidence_repo: Annotated[
        RecoveryEvidenceRepository, Depends(_get_evidence_repo)
    ],
) -> RecoveryEvidenceResponse:
    evidence = await evidence_repo.get_by_evidence_id(
        get_user_tenant_id(current_user), evidence_id
    )
    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recovery evidence not found",
        )
    log_security_event(
        "recovery_evidence_viewed",
        tenant_id=get_user_tenant_id(current_user),
        evidence_id=evidence_id,
    )
    return _evidence_to_response(evidence)


@router.get(
    "/recovery/executions",
    response_model=RecoveryExecutionListResponse,
)
async def list_recovery_executions(
    current_user: CurrentUser,
    execution_repo: Annotated[
        RecoveryExecutionRepository, Depends(_get_execution_repo)
    ],
    plan_id: str = Query(default="", min_length=0),
    action_id: str = Query(default="", min_length=0),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> RecoveryExecutionListResponse:
    if plan_id:
        items, total = await execution_repo.list_by_plan(
            get_user_tenant_id(current_user),
            plan_id,
            limit=limit,
            offset=offset,
        )
    elif action_id:
        items, total = await execution_repo.list_by_action(
            get_user_tenant_id(current_user),
            action_id,
            limit=limit,
            offset=offset,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either plan_id or action_id must be provided",
        )
    log_security_event(
        "recovery_executions_listed",
        tenant_id=get_user_tenant_id(current_user),
        count=total,
    )
    return RecoveryExecutionListResponse(
        items=[_execution_to_response(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/recovery/executions/{execution_id}",
    response_model=RecoveryExecutionResponse,
)
async def get_recovery_execution(
    execution_id: str,
    current_user: CurrentUser,
    execution_repo: Annotated[
        RecoveryExecutionRepository, Depends(_get_execution_repo)
    ],
) -> RecoveryExecutionResponse:
    execution = await execution_repo.get_by_execution_id(
        get_user_tenant_id(current_user), execution_id
    )
    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recovery execution not found",
        )
    log_security_event(
        "recovery_execution_viewed",
        tenant_id=get_user_tenant_id(current_user),
        execution_id=execution_id,
    )
    return _execution_to_response(execution)


@router.get(
    "/recovery/plan/{plan_id}",
    response_model=SurgicalRecoveryPlanResponse,
)
async def get_surgical_recovery_plan(
    plan_id: str,
    current_user: CurrentUser,
    plan_repo: Annotated[RecoveryPlanRepository, Depends(_get_plan_repo)],
) -> SurgicalRecoveryPlanResponse:
    plan = await plan_repo.get_by_plan_id(get_user_tenant_id(current_user), plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recovery plan not found",
        )
    return _plan_to_response(plan)


@router.post(
    "/recovery/plan",
    response_model=RecoveryPlanResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_recovery_plan(
    current_user: CurrentUser,
    recovery_service: Annotated[RecoveryPlanningService, Depends(_get_recovery_service)],
    incident_action_id: str = Query(..., min_length=1, max_length=64),
) -> RecoveryPlanResponse:
    plan = await recovery_service.create_plan(
        get_user_tenant_id(current_user), incident_action_id
    )
    log_security_event(
        "recovery_plan_created",
        tenant_id=get_user_tenant_id(current_user),
        plan_id=plan.plan_id,
        incident_action_id=incident_action_id,
    )
    return RecoveryPlanResponse(
        plan_id=plan.plan_id,
        tenant_id=plan.tenant_id,
        incident_action_id=plan.incident_action_id,
        status=plan.status.value,
        outcome=plan.outcome.value,
        simulation_result=plan.simulation_result,
        steps=plan.steps,
        approved_by=plan.approved_by,
        executed_by=plan.executed_by,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        executed_at=plan.executed_at,
        plan_version=plan.plan_version,
        plan_hash=plan.plan_hash,
        topological_order=plan.topological_order,
        dependency_graph_reference=plan.dependency_graph_reference,
        execution_status=plan.execution_status,
        approval_policy=plan.approval_policy,
        approval_threshold=plan.approval_threshold,
        stop_conditions=plan.stop_conditions,
        compensation_summary=plan.compensation_summary,
        incident_id=plan.incident_id,
        root_action_id=plan.root_action_id,
        affected_action_ids=plan.affected_action_ids,
    )


@router.post(
    "/recovery/plan/{plan_id}/simulate",
    response_model=dict[str, Any],
)
async def simulate_recovery_plan(
    plan_id: str,
    current_user: CurrentUser,
    recovery_service: Annotated[RecoveryPlanningService, Depends(_get_recovery_service)],
) -> dict[str, Any]:
    simulation = await recovery_service.simulate_plan(
        get_user_tenant_id(current_user), plan_id
    )
    log_security_event(
        "recovery_plan_simulated",
        tenant_id=get_user_tenant_id(current_user),
        plan_id=plan_id,
    )
    return simulation


@router.post(
    "/recovery/plan/{plan_id}/execute",
    response_model=RecoveryPlanResponse,
)
async def execute_recovery_plan(
    plan_id: str,
    _authorized: Annotated[UserResponse, Depends(require_recovery_executor)],
    current_user: CurrentUser,
    recovery_service: Annotated[RecoveryPlanningService, Depends(_get_recovery_service)],
) -> RecoveryPlanResponse:
    plan = await recovery_service.execute_plan(
        get_user_tenant_id(current_user), plan_id, current_user.email or "unknown"
    )
    log_security_event(
        "recovery_plan_executed",
        tenant_id=get_user_tenant_id(current_user),
        plan_id=plan.plan_id,
        executed_by=current_user.email or "unknown",
    )
    return RecoveryPlanResponse(
        plan_id=plan.plan_id,
        tenant_id=plan.tenant_id,
        incident_action_id=plan.incident_action_id,
        status=plan.status.value,
        outcome=plan.outcome.value,
        simulation_result=plan.simulation_result,
        steps=plan.steps,
        approved_by=plan.approved_by,
        executed_by=plan.executed_by,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        executed_at=plan.executed_at,
        plan_version=plan.plan_version,
        plan_hash=plan.plan_hash,
        topological_order=plan.topological_order,
        dependency_graph_reference=plan.dependency_graph_reference,
        execution_status=plan.execution_status,
        approval_policy=plan.approval_policy,
        approval_threshold=plan.approval_threshold,
        stop_conditions=plan.stop_conditions,
        compensation_summary=plan.compensation_summary,
        incident_id=plan.incident_id,
        root_action_id=plan.root_action_id,
        affected_action_ids=plan.affected_action_ids,
    )
