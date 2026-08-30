import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.entities.surgical_recovery_types import (
    CompensationType,
    ExecutionState,
    RecoveryExecution,
)
from app.domain.repositories.recovery_execution_repository import (
    RecoveryExecutionRepository,
)
from app.infrastructure.persistence.models.recovery_execution_model import (
    RecoveryExecutionModel,
)


class SQLAlchemyRecoveryExecutionRepository(RecoveryExecutionRepository):
    """SQLAlchemy adapter for RecoveryExecutionRepository port."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def get_by_execution_id(
        self, tenant_id: str, execution_id: str
    ) -> RecoveryExecution | None:
        stmt = select(RecoveryExecutionModel).where(
            RecoveryExecutionModel.tenant_id == tenant_id,
            RecoveryExecutionModel.execution_id == execution_id,
        )
        model = self._session.scalar(stmt)
        return self._to_entity(model) if model else None

    async def list_by_plan(
        self,
        tenant_id: str,
        plan_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[RecoveryExecution], int]:
        stmt = select(RecoveryExecutionModel).where(
            RecoveryExecutionModel.tenant_id == tenant_id,
            RecoveryExecutionModel.plan_id == plan_id,
        )
        count_stmt = select(func.count()).select_from(RecoveryExecutionModel).where(
            RecoveryExecutionModel.tenant_id == tenant_id,
            RecoveryExecutionModel.plan_id == plan_id,
        )
        total = self._session.scalar(count_stmt) or 0
        stmt = stmt.order_by(RecoveryExecutionModel.execution_order).limit(limit).offset(offset)
        models = self._session.scalars(stmt).all()
        return [self._to_entity(m) for m in models], total

    async def list_by_action(
        self,
        tenant_id: str,
        action_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[RecoveryExecution], int]:
        stmt = select(RecoveryExecutionModel).where(
            RecoveryExecutionModel.tenant_id == tenant_id,
            RecoveryExecutionModel.action_id == action_id,
        )
        count_stmt = select(func.count()).select_from(RecoveryExecutionModel).where(
            RecoveryExecutionModel.tenant_id == tenant_id,
            RecoveryExecutionModel.action_id == action_id,
        )
        total = self._session.scalar(count_stmt) or 0
        stmt = stmt.order_by(RecoveryExecutionModel.execution_order).limit(limit).offset(offset)
        models = self._session.scalars(stmt).all()
        return [self._to_entity(m) for m in models], total

    async def save(self, execution: RecoveryExecution) -> RecoveryExecution:
        stmt = select(RecoveryExecutionModel).where(
            RecoveryExecutionModel.execution_id == execution.execution_id
        )
        model = self._session.scalar(stmt)
        if model is None:
            model = RecoveryExecutionModel(
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
                details=json.dumps(execution.details),
                external_outcome=execution.external_outcome,
                verification_passed=execution.verification_passed,
                verification_details=json.dumps(execution.verification_details),
                started_at=execution.started_at,
                completed_at=execution.completed_at,
                executed_by=execution.executed_by,
                created_at=execution.created_at,
            )
            self._session.add(model)
        else:
            model.plan_id = execution.plan_id
            model.compensation_type = execution.compensation_type.value
            model.target_system = execution.target_system
            model.target_resource = execution.target_resource
            model.idempotency_key = execution.idempotency_key
            model.execution_order = execution.execution_order
            model.execution_state = execution.execution_state.value
            model.success = execution.success
            model.error = execution.error
            model.details = json.dumps(execution.details)
            model.external_outcome = execution.external_outcome
            model.verification_passed = execution.verification_passed
            model.verification_details = json.dumps(execution.verification_details)
            model.started_at = execution.started_at
            model.completed_at = execution.completed_at
            model.executed_by = execution.executed_by
        self._session.flush()
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: RecoveryExecutionModel) -> RecoveryExecution:
        def _safe_json_dict(raw: str | None) -> dict[str, object]:
            if not raw:
                return {}
            try:
                data = json.loads(raw)
                return data if isinstance(data, dict) else {}
            except (ValueError, TypeError):
                return {}

        return RecoveryExecution(
            execution_id=model.execution_id,
            plan_id=model.plan_id,
            action_id=model.action_id,
            tenant_id=model.tenant_id,
            compensation_type=CompensationType(model.compensation_type),
            target_system=model.target_system,
            target_resource=model.target_resource or "",
            idempotency_key=model.idempotency_key or "",
            execution_order=model.execution_order or 0,
            execution_state=ExecutionState(model.execution_state),
            success=bool(model.success),
            error=model.error,
            details=_safe_json_dict(model.details),
            external_outcome=model.external_outcome or "",
            verification_passed=bool(model.verification_passed),
            verification_details=_safe_json_dict(model.verification_details),
            started_at=model.started_at,
            completed_at=model.completed_at,
            executed_by=model.executed_by,
            created_at=model.created_at or datetime.now(UTC),
        )
