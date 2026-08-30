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
from app.domain.repositories.containment_repository import (
    ContainmentRepository,
    RecoveryPlanRepository,
)
from app.infrastructure.logging.audit_logger import log_security_event
from app.infrastructure.observability.metrics import metrics
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_containment_repository import (
    SQLAlchemyContainmentRepository,
)
from app.presentation.api.dependencies.auth import CurrentUser, get_user_tenant_id

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
    from app.domain.services.recovery_planning_service import RecoveryPlanningService
    from app.infrastructure.persistence.repositories.sqlalchemy_protected_action_repository import (
        SQLAlchemyProtectedActionRepository,
    )
    from app.infrastructure.recovery.config_rollback_adapter import ConfigRollbackAdapter
    from app.infrastructure.recovery.database_record_adapter import DatabaseRecordAdapter
    from app.infrastructure.recovery.file_version_adapter import FileVersionAdapter
    session = SessionLocal()
    try:
        action_repo = SQLAlchemyProtectedActionRepository(session)
        adapters = [
            DatabaseRecordAdapter(),
            FileVersionAdapter(),
            ConfigRollbackAdapter(),
        ]
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
        with suppress(Exception):
            session.commit()
        return simulation
    finally:
        session.close()


@router.post("/recovery/execute", response_model=RecoveryPlanResponse)
async def execute_recovery(
    body: RecoveryExecuteRequest,
    current_user: CurrentUser,
    repo: Annotated[RecoveryPlanRepository, Depends(_get_recovery_repo)],
) -> RecoveryPlanResponse:
    from app.domain.services.recovery_planning_service import RecoveryPlanningService
    from app.infrastructure.persistence.repositories.sqlalchemy_protected_action_repository import (
        SQLAlchemyProtectedActionRepository,
    )
    from app.infrastructure.recovery.config_rollback_adapter import ConfigRollbackAdapter
    from app.infrastructure.recovery.database_record_adapter import DatabaseRecordAdapter
    from app.infrastructure.recovery.file_version_adapter import FileVersionAdapter
    session = SessionLocal()
    try:
        action_repo = SQLAlchemyProtectedActionRepository(session)
        adapters = [
            DatabaseRecordAdapter(),
            FileVersionAdapter(),
            ConfigRollbackAdapter(),
        ]
        plan_service = RecoveryPlanningService(action_repo, repo, adapters=adapters)
        try:
            plan = await plan_service.execute_plan(
                get_user_tenant_id(current_user), body.plan_id, body.approved_by
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        log_security_event(
            "recovery_executed",
            tenant_id=plan.tenant_id,
            plan_id=plan.plan_id,
            executed_by=body.approved_by,
        )
        metrics.increment_security_exception("recovery_executed")
        with suppress(Exception):
            session.commit()
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
