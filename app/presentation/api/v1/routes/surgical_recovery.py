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
from app.domain.entities.causal_state_types import VerificationStatus
from app.domain.entities.recovery_plan import (
    RecoveryOutcome,
    RecoveryPlan,
    RecoveryStatus,
)
from app.domain.entities.surgical_recovery_types import (
    RecoveryEvidence,
    RecoveryExecution,
)
from app.domain.repositories.causal_state_repositories import (
    ConfidenceRepository,
    DurableExecutionRepository,
    RecoveryReportRepository,
)
from app.domain.repositories.containment_repository import RecoveryPlanRepository
from app.domain.repositories.protected_action_repository import (
    ProtectedActionRepository,
)
from app.domain.repositories.recovery_evidence_repository import RecoveryEvidenceRepository
from app.domain.repositories.recovery_execution_repository import RecoveryExecutionRepository
from app.domain.services.continuous_verification_service import ContinuousVerificationService
from app.domain.services.distributed_recovery_orchestrator import (
    DistributedRecoveryOrchestrator,
)
from app.domain.services.recovery_confidence_model import RecoveryConfidenceModel
from app.domain.services.recovery_planning_service import RecoveryPlanningService
from app.domain.services.tenant_quota_service import (
    QuotaExceededError,
    TenantQuotaService,
)
from app.infrastructure.logging.audit_logger import log_security_event
from app.infrastructure.persistence.repositories.sqlalchemy_causal_state_repositories import (
    SQLAlchemyConfidenceRepository,
    SQLAlchemyDurableExecutionRepository,
    SQLAlchemyRecoveryReportRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_containment_repository import (
    SQLAlchemyRecoveryPlanRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_coordination_stores import (
    build_plan_lease_store,
    build_quota_counter_store,
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
from app.infrastructure.recovery.config_recovery_adapter import ConfigRecoveryAdapter
from app.infrastructure.recovery.config_rollback_adapter import ConfigRollbackAdapter
from app.infrastructure.recovery.database_record_adapter import DatabaseRecordAdapter
from app.infrastructure.recovery.database_recovery_adapter import DatabaseRecoveryAdapter
from app.infrastructure.recovery.file_version_adapter import FileVersionAdapter
from app.infrastructure.recovery.filesystem_recovery_adapter import FilesystemRecoveryAdapter
from app.infrastructure.recovery.mock_adapter import MockRecoveryAdapter
from app.presentation.api.dependencies.auth import (
    CurrentUser,
    _get_session,
    get_user_tenant_id,
    require_recovery_executor,
)
from app.presentation.api.dependencies.emergency_guard import assert_execution_permitted

router = APIRouter(tags=["Surgical Recovery"])
DEFAULT_LIMIT = 100
MAX_LIMIT = 500

# Process-wide recovery quota store (opt-in per tenant: no registered policy
# means unlimited, so default behaviour is unchanged).  The backend follows
# the runbook §7 selector (INTERLOCK_QUOTA_BACKEND): default in-process,
# "sql" shares quota_counters across processes.
quota_service = TenantQuotaService(counter_store=build_quota_counter_store())


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


def _get_durable_execution_repo(
    session: Annotated[Session, Depends(_get_session)],
) -> DurableExecutionRepository:
    return SQLAlchemyDurableExecutionRepository(session)


def _get_report_repo(
    session: Annotated[Session, Depends(_get_session)],
) -> RecoveryReportRepository:
    return SQLAlchemyRecoveryReportRepository(session)


def _get_confidence_repo(
    session: Annotated[Session, Depends(_get_session)],
) -> ConfidenceRepository:
    return SQLAlchemyConfidenceRepository(session)


def _get_adapters(
    session: Annotated[Session, Depends(_get_session)],
) -> list[Any]:
    from app.infrastructure.config.settings import get_settings

    settings = get_settings()
    adapters: list[Any] = []

    if settings.interlock_workspace_path:
        adapters.append(FilesystemRecoveryAdapter(base_path=settings.interlock_workspace_path))

    adapters.append(DatabaseRecoveryAdapter())
    adapters.append(ConfigRecoveryAdapter())

    if settings.app_env != "production":
        adapters.append(DatabaseRecordAdapter())
        adapters.append(ConfigRollbackAdapter())
        adapters.append(FileVersionAdapter())
        adapters.append(MockRecoveryAdapter())

    return adapters


def _get_recovery_service(
    action_repo: Annotated[Any, Depends(_get_action_repo)],
    plan_repo: Annotated[RecoveryPlanRepository, Depends(_get_plan_repo)],
    adapters: Annotated[list[Any], Depends(_get_adapters)],
    evidence_repo: Annotated[RecoveryEvidenceRepository, Depends(_get_evidence_repo)],
) -> RecoveryPlanningService:
    return RecoveryPlanningService(
        action_repo, plan_repo, adapters, evidence_repo, quota_service=quota_service
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
    evidence_repo: Annotated[RecoveryEvidenceRepository, Depends(_get_evidence_repo)],
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
    evidence_repo: Annotated[RecoveryEvidenceRepository, Depends(_get_evidence_repo)],
) -> RecoveryEvidenceResponse:
    evidence = await evidence_repo.get_by_evidence_id(get_user_tenant_id(current_user), evidence_id)
    if evidence is None:
        # Cross-tenant and unknown-id denials must leave an audit trace
        # exactly like the success path does (V6 doc-WP-6 scenario F).
        log_security_event(
            "recovery_evidence_access_denied",
            tenant_id=get_user_tenant_id(current_user),
            evidence_id=evidence_id,
        )
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
    execution_repo: Annotated[RecoveryExecutionRepository, Depends(_get_execution_repo)],
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
    execution_repo: Annotated[RecoveryExecutionRepository, Depends(_get_execution_repo)],
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
    try:
        plan = await recovery_service.create_plan(
            get_user_tenant_id(current_user), incident_action_id
        )
    except QuotaExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
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
    simulation = await recovery_service.simulate_plan(get_user_tenant_id(current_user), plan_id)
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
    plan_repo: Annotated[RecoveryPlanRepository, Depends(_get_plan_repo)],
    action_repo: Annotated[ProtectedActionRepository, Depends(_get_action_repo)],
    evidence_repo: Annotated[RecoveryEvidenceRepository, Depends(_get_evidence_repo)],
    execution_repo: Annotated[DurableExecutionRepository, Depends(_get_durable_execution_repo)],
    adapters: Annotated[list[Any], Depends(_get_adapters)],
) -> RecoveryPlanResponse:
    tenant_id = get_user_tenant_id(current_user)
    # Emergency deny must be observed at execution time (PILLAR 6): a deny
    # activated through the emergency routes blocks this entry point.
    await assert_execution_permitted(tenant_id)
    plan = await plan_repo.get_by_plan_id(tenant_id, plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recovery plan not found",
        )

    if plan.status not in (RecoveryStatus.APPROVED,):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Plan status '{plan.status.value}' does not allow execution",
        )

    action = await action_repo.get_by_action_id(tenant_id, plan.incident_action_id)
    if action is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident action not found",
        )

    descendants, _ = await action_repo.list_descendants(
        tenant_id, plan.incident_action_id, limit=1000, offset=0
    )
    affected = [action] + descendants

    orchestrator = DistributedRecoveryOrchestrator(
        evidence_repo,
        execution_repo,
        adapters,
        lease_store=build_plan_lease_store(),
    )
    await orchestrator.create_durable_plan(tenant_id, plan_id, affected, plan.topological_order)

    # Tenant quota: hold one concurrent-compensation slot for this execution.
    slot = quota_service.begin_compensation(tenant_id)
    if not slot.admitted:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=slot.reason,
        )
    try:
        execution_result = await orchestrator.execute_durable_plan(
            tenant_id, plan_id, plan.stop_conditions
        )
    finally:
        quota_service.end_compensation(tenant_id)

    orchestrator_status = execution_result.get("status", "error")
    if orchestrator_status == "completed":
        new_status = RecoveryStatus.COMPLETED
        # SAFE_AUTOMATIC is a safety promise: it requires the plan to have
        # completed AND passed independent verification of every step.
        # Completed-but-unverified runs (V6 WP-7) are honestly UNKNOWN.
        new_outcome = (
            RecoveryOutcome.SAFE_AUTOMATIC
            if execution_result.get("verification_status")
            == VerificationStatus.EXECUTED_AND_VERIFIED.value
            else RecoveryOutcome.UNKNOWN
        )
        new_execution_status = "completed"
    elif orchestrator_status == "already_running":
        new_status = RecoveryStatus.EXECUTING
        new_outcome = RecoveryOutcome.UNKNOWN
        new_execution_status = "executing"
    else:
        new_status = RecoveryStatus.FAILED
        new_outcome = RecoveryOutcome.UNKNOWN
        new_execution_status = "failed"

    updated_simulation = dict(plan.simulation_result)
    updated_simulation["execution_results"] = execution_result.get("execution_results", {})

    updated_plan = await plan_repo.update_status(
        tenant_id,
        plan.plan_id,
        new_status,
        outcome=new_outcome.value,
        execution_status=new_execution_status,
        simulation_result=updated_simulation,
        steps=plan.steps,
        approved_by=plan.approved_by,
        executed_by=current_user.email or "unknown",
        plan_version=plan.plan_version,
        plan_hash=plan.plan_hash,
        topological_order=plan.topological_order,
        dependency_graph_reference=plan.dependency_graph_reference,
        approval_policy=plan.approval_policy,
        approval_threshold=plan.approval_threshold,
        stop_conditions=plan.stop_conditions,
        compensation_summary=plan.compensation_summary,
        incident_id=plan.incident_id,
        root_action_id=plan.root_action_id,
        affected_action_ids=plan.affected_action_ids,
    )
    if updated_plan is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update recovery plan",
        )

    log_security_event(
        "recovery_plan_executed",
        tenant_id=tenant_id,
        plan_id=updated_plan.plan_id,
        executed_by=current_user.email or "unknown",
    )
    return _plan_to_response(updated_plan)  # type: ignore[return-value]


@router.post(
    "/recovery/plan/{plan_id}/resume",
    response_model=dict[str, Any],
)
async def resume_recovery_plan(
    plan_id: str,
    _authorized: Annotated[UserResponse, Depends(require_recovery_executor)],
    current_user: CurrentUser,
    plan_repo: Annotated[RecoveryPlanRepository, Depends(_get_plan_repo)],
    evidence_repo: Annotated[RecoveryEvidenceRepository, Depends(_get_evidence_repo)],
    execution_repo: Annotated[DurableExecutionRepository, Depends(_get_durable_execution_repo)],
    adapters: Annotated[list[Any], Depends(_get_adapters)],
) -> dict[str, Any]:
    tenant_id = get_user_tenant_id(current_user)
    await assert_execution_permitted(tenant_id)
    plan = await plan_repo.get_by_plan_id(tenant_id, plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recovery plan not found",
        )
    if plan.status != RecoveryStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Recovery plan must be in APPROVED state to resume.",
        )


    orchestrator = DistributedRecoveryOrchestrator(
        evidence_repo,
        execution_repo,
        adapters,
        lease_store=build_plan_lease_store(),
    )
    result = await orchestrator.resume_plan(tenant_id, plan_id, plan.stop_conditions)

    log_security_event(
        "recovery_plan_resumed",
        tenant_id=tenant_id,
        plan_id=plan_id,
    )
    return result


@router.post(
    "/recovery/plan/{plan_id}/verify",
    response_model=dict[str, Any],
)
async def verify_recovery_plan(
    plan_id: str,
    _authorized: Annotated[UserResponse, Depends(require_recovery_executor)],
    current_user: CurrentUser,
    plan_repo: Annotated[RecoveryPlanRepository, Depends(_get_plan_repo)],
    evidence_repo: Annotated[RecoveryEvidenceRepository, Depends(_get_evidence_repo)],
    execution_repo: Annotated[DurableExecutionRepository, Depends(_get_durable_execution_repo)],
    report_repo: Annotated[RecoveryReportRepository, Depends(_get_report_repo)],
    adapters: Annotated[list[Any], Depends(_get_adapters)],
) -> dict[str, Any]:
    tenant_id = get_user_tenant_id(current_user)
    plan = await plan_repo.get_by_plan_id(tenant_id, plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recovery plan not found",
        )
    if plan.status != RecoveryStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Recovery plan must be in APPROVED state to verify.",
        )


    verification_service = ContinuousVerificationService(
        evidence_repo, execution_repo, report_repo, adapters
    )
    report = await verification_service.verify_recovery(tenant_id, plan_id, plan.incident_id)

    log_security_event(
        "recovery_plan_verified",
        tenant_id=tenant_id,
        plan_id=plan_id,
    )
    return {
        "report_id": report.report_id,
        "tenant_id": report.tenant_id,
        "plan_id": report.plan_id,
        "incident_id": report.incident_id,
        "created_at": report.created_at.isoformat(),
        "ai_changes_recovered": report.ai_changes_recovered,
        "ai_changes_failed": report.ai_changes_failed,
        "unrelated_changes_preserved": report.unrelated_changes_preserved,
        "manual_recovery_required": report.manual_recovery_required,
        "verification_status": report.verification_status.value,
        "confidence_level": report.confidence_level.value,
        "resource_results": report.resource_results,
        "summary": report.summary,
        "limitations": report.limitations,
    }


@router.post(
    "/recovery/plan/{plan_id}/confidence",
    response_model=dict[str, Any],
)
async def assess_recovery_confidence(
    plan_id: str,
    _authorized: Annotated[UserResponse, Depends(require_recovery_executor)],
    current_user: CurrentUser,
    plan_repo: Annotated[RecoveryPlanRepository, Depends(_get_plan_repo)],
    action_repo: Annotated[ProtectedActionRepository, Depends(_get_action_repo)],
    confidence_repo: Annotated[ConfidenceRepository, Depends(_get_confidence_repo)],
    evidence_repo: Annotated[RecoveryEvidenceRepository, Depends(_get_evidence_repo)],
) -> dict[str, Any]:
    tenant_id = get_user_tenant_id(current_user)
    plan = await plan_repo.get_by_plan_id(tenant_id, plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recovery plan not found",
        )

    affected = []
    for action_id in plan.affected_action_ids:
        action = await action_repo.get_by_action_id(tenant_id, action_id)
        if action is not None:
            affected.append(action)

    confidence_model = RecoveryConfidenceModel(confidence_repo, evidence_repo)
    confidence = await confidence_model.assess_confidence(tenant_id, plan_id, affected)

    log_security_event(
        "recovery_confidence_assessed",
        tenant_id=tenant_id,
        plan_id=plan_id,
    )
    return {
        "confidence_id": confidence.confidence_id,
        "tenant_id": confidence.tenant_id,
        "plan_id": confidence.plan_id,
        "level": confidence.level.value,
        "created_at": confidence.created_at.isoformat(),
        "before_state_available": confidence.before_state_available,
        "after_state_available": confidence.after_state_available,
        "current_state_available": confidence.current_state_available,
        "adapter_support": confidence.adapter_support,
        "version_match": confidence.version_match,
        "drift_detected": confidence.drift_detected,
        "conflict_detected": confidence.conflict_detected,
        "dependency_completeness": confidence.dependency_completeness,
        "verification_capability": confidence.verification_capability,
        "evidence_completeness": confidence.evidence_completeness,
        "factors": confidence.factors,
        "recommendations": confidence.recommendations,
    }


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
