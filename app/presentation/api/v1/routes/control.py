from collections.abc import Generator
from contextlib import suppress
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.application.dto.control import (
    ContainmentRequest,
    ContainmentResponse,
    RecoveryExecuteRequest,
    RecoveryPlanResponse,
    RecoverySimulateRequest,
)
from app.domain.entities.recovery_plan import RecoveryStatus
from app.domain.repositories.containment_repository import (
    ContainmentRepository,
    RecoveryPlanRepository,
)
from app.domain.services.continuous_verification_service import (
    ContinuousVerificationService,
)
from app.domain.services.distributed_recovery_orchestrator import (
    DistributedRecoveryOrchestrator,
)
from app.domain.services.recovery_confidence_model import RecoveryConfidenceModel
from app.infrastructure.logging.audit_logger import log_security_event
from app.infrastructure.observability.metrics import metrics
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_causal_state_repositories import (
    SQLAlchemyConfidenceRepository,
    SQLAlchemyDurableExecutionRepository,
    SQLAlchemyRecoveryReportRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_containment_repository import (
    SQLAlchemyContainmentRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_recovery_evidence_repository import (
    SQLAlchemyRecoveryEvidenceRepository,
)
from app.presentation.api.dependencies.auth import (
    CurrentUser,
    UserResponse,
    get_user_tenant_id,
    require_recovery_executor,
)

router = APIRouter(tags=["Control"])


def _get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _get_containment_repo(
    session: Annotated[Session, Depends(_get_session)],
) -> ContainmentRepository:
    return SQLAlchemyContainmentRepository(session)


def _get_recovery_repo(
    session: Annotated[Session, Depends(_get_session)],
) -> RecoveryPlanRepository:
    from app.infrastructure.persistence.repositories.sqlalchemy_containment_repository import (
        SQLAlchemyRecoveryPlanRepository,
    )

    return SQLAlchemyRecoveryPlanRepository(session)


def _build_recovery_adapters() -> list[Any]:
    from app.infrastructure.config.settings import get_settings
    from app.infrastructure.recovery.config_recovery_adapter import ConfigRecoveryAdapter
    from app.infrastructure.recovery.database_recovery_adapter import DatabaseRecoveryAdapter
    from app.infrastructure.recovery.filesystem_recovery_adapter import (
        FilesystemRecoveryAdapter,
    )
    from app.infrastructure.recovery.mock_adapter import MockRecoveryAdapter

    settings = get_settings()
    adapters: list[Any] = [DatabaseRecoveryAdapter()]
    if settings.interlock_workspace_path:
        adapters.append(FilesystemRecoveryAdapter(base_path=settings.interlock_workspace_path))
    adapters.append(ConfigRecoveryAdapter())
    if settings.app_env != "production":
        adapters.append(MockRecoveryAdapter())
    return adapters


@router.post(
    "/containment",
    response_model=ContainmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_containment(
    body: ContainmentRequest,
    current_user: CurrentUser,
    repo: Annotated[ContainmentRepository, Depends(_get_containment_repo)],
) -> ContainmentResponse:
    from app.domain.entities.containment_event import ContainmentMode
    from app.domain.services.cascade_containment_service import CascadeContainmentService
    from app.infrastructure.persistence.repositories.sqlalchemy_agent_repository import (
        SQLAlchemyAgentRepository,
    )
    from app.infrastructure.persistence.repositories.sqlalchemy_authority_grant_repository import (
        SQLAlchemyAuthorityGrantRepository,
    )
    from app.infrastructure.persistence.repositories.sqlalchemy_execution_token_repository import (
        SQLAlchemyExecutionTokenRepository,
    )
    from app.infrastructure.persistence.repositories.sqlalchemy_protected_action_repository import (
        SQLAlchemyProtectedActionRepository,
    )

    session = SessionLocal()
    try:
        agent_repo = SQLAlchemyAgentRepository(session)
        grant_repo = SQLAlchemyAuthorityGrantRepository(session)
        action_repo = SQLAlchemyProtectedActionRepository(session)
        token_repo = SQLAlchemyExecutionTokenRepository(session)
        service = CascadeContainmentService(
            agent_repo,
            grant_repo,
            repo,
            action_repository=action_repo,
            token_repository=token_repo,
        )
        try:
            event = await service.contain_authority_tree(
                tenant_id=get_user_tenant_id(current_user),
                target_agent_id=body.target_agent_id,
                mode=ContainmentMode(body.mode),
                initiated_by=str(current_user.id),
                authorized_by=str(current_user.id),
                reason=body.reason,
                dry_run=body.dry_run,
                target_authority_id=body.target_authority_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        metrics.record_containment_cascade_depth(len(event.affected_agent_ids))
        return ContainmentResponse(
            containment_id=event.containment_id,
            tenant_id=event.tenant_id,
            target_agent_id=event.target_agent_id,
            target_authority_id=event.target_authority_id,
            mode=event.mode.value,
            status=event.status.value,
            dry_run=event.dry_run,
            affected_agent_ids=event.affected_agent_ids,
            affected_authority_ids=event.affected_authority_ids,
            affected_session_ids=event.affected_session_ids,
            affected_token_ids=event.affected_token_ids,
            affected_action_ids=event.affected_action_ids,
            result_details=event.result_details,
            created_at=event.created_at,
            completed_at=event.completed_at,
        )
    finally:
        session.close()


@router.get("/containment/agent/{agent_id}", response_model=dict)
async def get_blast_radius(
    agent_id: str,
    current_user: CurrentUser,
    repo: Annotated[ContainmentRepository, Depends(_get_containment_repo)],
) -> dict[str, Any]:
    import time

    from app.domain.services.cascade_containment_service import CascadeContainmentService
    from app.infrastructure.persistence.repositories.sqlalchemy_agent_repository import (
        SQLAlchemyAgentRepository,
    )
    from app.infrastructure.persistence.repositories.sqlalchemy_authority_grant_repository import (
        SQLAlchemyAuthorityGrantRepository,
    )
    from app.infrastructure.persistence.repositories.sqlalchemy_execution_token_repository import (
        SQLAlchemyExecutionTokenRepository,
    )
    from app.infrastructure.persistence.repositories.sqlalchemy_protected_action_repository import (
        SQLAlchemyProtectedActionRepository,
    )

    session = SessionLocal()
    try:
        agent_repo = SQLAlchemyAgentRepository(session)
        grant_repo = SQLAlchemyAuthorityGrantRepository(session)
        action_repo = SQLAlchemyProtectedActionRepository(session)
        token_repo = SQLAlchemyExecutionTokenRepository(session)
        service = CascadeContainmentService(
            agent_repo,
            grant_repo,
            repo,
            action_repository=action_repo,
            token_repository=token_repo,
        )
        start = time.perf_counter()
        try:
            result = await service.get_blast_radius(get_user_tenant_id(current_user), agent_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        duration = time.perf_counter() - start
        metrics.record_blast_radius_calculation(duration)
        return result
    finally:
        session.close()


@router.post("/recovery/simulate", response_model=dict)
async def simulate_recovery(
    body: RecoverySimulateRequest,
    current_user: CurrentUser,
    repo: Annotated[RecoveryPlanRepository, Depends(_get_recovery_repo)],
) -> dict[str, Any]:
    from app.domain.entities.protected_action import ProtectedAction
    from app.domain.services.recovery_planning_service import RecoveryPlanningService
    from app.infrastructure.persistence.repositories.sqlalchemy_protected_action_repository import (
        SQLAlchemyProtectedActionRepository,
    )

    session = SessionLocal()
    try:
        action_repo = SQLAlchemyProtectedActionRepository(session)
        adapters = _build_recovery_adapters()
        plan_service = RecoveryPlanningService(action_repo, repo, adapters=adapters)
        try:
            plan = await plan_service.create_plan(
                get_user_tenant_id(current_user), body.incident_action_id, body.recovery_steps
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        import time

        start = time.perf_counter()
        simulation = await plan_service.simulate_plan(
            get_user_tenant_id(current_user), plan.plan_id
        )
        duration = time.perf_counter() - start
        metrics.record_recovery_preview_duration(duration)

        confidence_repo = SQLAlchemyConfidenceRepository(session)
        evidence_repo = SQLAlchemyRecoveryEvidenceRepository(session)
        confidence_model = RecoveryConfidenceModel(confidence_repo, evidence_repo)
        confidence_assessment = await confidence_model.assess_confidence(
            tenant_id=get_user_tenant_id(current_user),
            plan_id=plan.plan_id,
            actions=[
                ProtectedAction(
                    action_id=step.get("action_id", ""),
                    tenant_id=get_user_tenant_id(current_user),
                    actor_user_id=None,
                    agent_id="",
                    authority_grant_id=None,
                    tool=step.get("target_system", ""),
                    resource=step.get("target_resource", ""),
                    action_type=step.get("action_type", ""),
                )
                for step in plan.steps
            ],
        )

        with suppress(Exception):
            session.commit()
        result = dict(simulation)
        result["confidence_level"] = confidence_assessment.level.value
        return result
    finally:
        session.close()


@router.post("/recovery/execute", response_model=dict[str, Any])
async def execute_recovery(
    body: RecoveryExecuteRequest,
    current_user: CurrentUser,
    _authorized: Annotated[UserResponse, Depends(require_recovery_executor)],
    repo: Annotated[RecoveryPlanRepository, Depends(_get_recovery_repo)],
) -> dict[str, Any]:
    from app.domain.entities.protected_action import ProtectedAction

    session = SessionLocal()
    try:
        evidence_repo = SQLAlchemyRecoveryEvidenceRepository(session)
        execution_repo = SQLAlchemyDurableExecutionRepository(session)
        report_repo = SQLAlchemyRecoveryReportRepository(session)
        confidence_repo = SQLAlchemyConfidenceRepository(session)

        adapters = _build_recovery_adapters()

        plan = await repo.get_by_plan_id(get_user_tenant_id(current_user), body.plan_id)
        if plan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recovery plan not found",
            )

        if plan.status not in (RecoveryStatus.SIMULATED, RecoveryStatus.APPROVED):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Plan must be simulated or approved before execution. "
                    f"Current status: {plan.status.value}"
                ),
            )

        orchestrator = DistributedRecoveryOrchestrator(
            evidence_repository=evidence_repo,
            execution_repository=execution_repo,
            adapters=adapters,
        )

        protected_actions: list[ProtectedAction] = []
        for step in plan.steps:
            protected_actions.append(
                ProtectedAction(
                    action_id=step.get("action_id", ""),
                    tenant_id=get_user_tenant_id(current_user),
                    actor_user_id=None,
                    agent_id="",
                    authority_grant_id=None,
                    tool=step.get("target_system", ""),
                    resource=step.get("target_resource", ""),
                    action_type=step.get("action_type", ""),
                )
            )

        await orchestrator.create_durable_plan(
            tenant_id=get_user_tenant_id(current_user),
            plan_id=plan.plan_id,
            actions=protected_actions,
            topological_order=plan.topological_order,
        )

        execution_result = await orchestrator.execute_durable_plan(
            tenant_id=get_user_tenant_id(current_user),
            plan_id=plan.plan_id,
            stop_conditions=plan.stop_conditions,
        )

        verification_service = ContinuousVerificationService(
            evidence_repository=evidence_repo,
            execution_repository=execution_repo,
            report_repository=report_repo,
            adapters=adapters,
        )
        verification_report = await verification_service.verify_recovery(
            tenant_id=get_user_tenant_id(current_user),
            plan_id=plan.plan_id,
            incident_id=plan.incident_id,
        )

        confidence_model = RecoveryConfidenceModel(confidence_repo, evidence_repo)
        confidence_assessment = await confidence_model.assess_confidence(
            tenant_id=get_user_tenant_id(current_user),
            plan_id=plan.plan_id,
            actions=protected_actions,
        )

        log_security_event(
            "recovery_executed",
            tenant_id=plan.tenant_id,
            plan_id=plan.plan_id,
            executed_by=body.approved_by,
        )
        metrics.increment_security_exception("recovery_executed")
        with suppress(Exception):
            session.commit()

        return {
            "plan_id": plan.plan_id,
            "tenant_id": plan.tenant_id,
            "incident_action_id": plan.incident_action_id,
            "status": plan.status.value,
            "outcome": plan.outcome.value,
            "simulation_result": plan.simulation_result,
            "steps": plan.steps,
            "approved_by": plan.approved_by,
            "executed_by": plan.executed_by,
            "created_at": plan.created_at,
            "updated_at": plan.updated_at,
            "executed_at": plan.executed_at,
            "verification_status": verification_report.verification_status.value,
            "confidence_level": confidence_assessment.level.value,
            "partial_results": execution_result,
            "verification_report_id": verification_report.report_id,
        }
    finally:
        session.close()


@router.get("/recovery/{plan_id}", response_model=RecoveryPlanResponse)
async def get_recovery_plan(
    plan_id: str,
    current_user: CurrentUser,
    repo: Annotated[RecoveryPlanRepository, Depends(_get_recovery_repo)],
) -> RecoveryPlanResponse:
    plan = await repo.get_by_plan_id(get_user_tenant_id(current_user), plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Recovery plan not found")
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
    )


@router.post("/recovery/{plan_id}/verify", response_model=dict)
async def verify_recovery(
    plan_id: str,
    _authorized: Annotated[UserResponse, Depends(require_recovery_executor)],
    repo: Annotated[RecoveryPlanRepository, Depends(_get_recovery_repo)],
) -> dict[str, Any]:
    plan = await repo.get_by_plan_id(get_user_tenant_id(_authorized), plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Recovery plan not found")

    session = SessionLocal()
    try:
        evidence_repo = SQLAlchemyRecoveryEvidenceRepository(session)
        execution_repo = SQLAlchemyDurableExecutionRepository(session)
        report_repo = SQLAlchemyRecoveryReportRepository(session)
        adapters = _build_recovery_adapters()

        verification_service = ContinuousVerificationService(
            evidence_repository=evidence_repo,
            execution_repository=execution_repo,
            report_repository=report_repo,
            adapters=adapters,
        )
        verification_report = await verification_service.verify_recovery(
            tenant_id=get_user_tenant_id(_authorized),
            plan_id=plan_id,
            incident_id=plan.incident_id,
        )
        with suppress(Exception):
            session.commit()
        return {
            "report_id": verification_report.report_id,
            "plan_id": verification_report.plan_id,
            "incident_id": verification_report.incident_id,
            "verification_status": verification_report.verification_status.value,
            "ai_changes_recovered": verification_report.ai_changes_recovered,
            "ai_changes_failed": verification_report.ai_changes_failed,
            "manual_recovery_required": verification_report.manual_recovery_required,
            "resource_results": verification_report.resource_results,
            "summary": verification_report.summary,
            "limitations": verification_report.limitations,
            "created_at": verification_report.created_at,
        }
    finally:
        session.close()


@router.post("/recovery/{plan_id}/confidence", response_model=dict)
async def assess_confidence(
    plan_id: str,
    _authorized: Annotated[UserResponse, Depends(require_recovery_executor)],
    repo: Annotated[RecoveryPlanRepository, Depends(_get_recovery_repo)],
) -> dict[str, Any]:
    from app.domain.entities.protected_action import ProtectedAction

    plan = await repo.get_by_plan_id(get_user_tenant_id(_authorized), plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Recovery plan not found")

    session = SessionLocal()
    try:
        evidence_repo = SQLAlchemyRecoveryEvidenceRepository(session)
        confidence_repo = SQLAlchemyConfidenceRepository(session)

        confidence_model = RecoveryConfidenceModel(confidence_repo, evidence_repo)
        actions = [
            ProtectedAction(
                action_id=step.get("action_id", ""),
                tenant_id=get_user_tenant_id(_authorized),
                actor_user_id=None,
                agent_id="",
                authority_grant_id=None,
                tool=step.get("target_system", ""),
                resource=step.get("target_resource", ""),
                action_type=step.get("action_type", ""),
            )
            for step in plan.steps
        ]
        confidence_assessment = await confidence_model.assess_confidence(
            tenant_id=get_user_tenant_id(_authorized),
            plan_id=plan_id,
            actions=actions,
        )
        with suppress(Exception):
            session.commit()
        return {
            "confidence_id": confidence_assessment.confidence_id,
            "plan_id": confidence_assessment.plan_id,
            "level": confidence_assessment.level.value,
            "before_state_available": confidence_assessment.before_state_available,
            "after_state_available": confidence_assessment.after_state_available,
            "current_state_available": confidence_assessment.current_state_available,
            "adapter_support": confidence_assessment.adapter_support,
            "version_match": confidence_assessment.version_match,
            "drift_detected": confidence_assessment.drift_detected,
            "conflict_detected": confidence_assessment.conflict_detected,
            "dependency_completeness": confidence_assessment.dependency_completeness,
            "verification_capability": confidence_assessment.verification_capability,
            "evidence_completeness": confidence_assessment.evidence_completeness,
            "factors": confidence_assessment.factors,
            "recommendations": confidence_assessment.recommendations,
            "created_at": confidence_assessment.created_at,
        }
    finally:
        session.close()


@router.post("/recovery/{plan_id}/resume", response_model=dict)
async def resume_recovery(
    plan_id: str,
    _authorized: Annotated[UserResponse, Depends(require_recovery_executor)],
    repo: Annotated[RecoveryPlanRepository, Depends(_get_recovery_repo)],
) -> dict[str, Any]:
    plan = await repo.get_by_plan_id(get_user_tenant_id(_authorized), plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Recovery plan not found")

    session = SessionLocal()
    try:
        evidence_repo = SQLAlchemyRecoveryEvidenceRepository(session)
        execution_repo = SQLAlchemyDurableExecutionRepository(session)
        adapters = _build_recovery_adapters()

        orchestrator = DistributedRecoveryOrchestrator(
            evidence_repository=evidence_repo,
            execution_repository=execution_repo,
            adapters=adapters,
        )
        resume_result = await orchestrator.resume_plan(
            tenant_id=get_user_tenant_id(_authorized),
            plan_id=plan_id,
            stop_conditions=plan.stop_conditions,
        )
        with suppress(Exception):
            session.commit()
        return resume_result
    finally:
        session.close()
