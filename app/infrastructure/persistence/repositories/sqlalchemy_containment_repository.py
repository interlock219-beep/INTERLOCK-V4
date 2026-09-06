import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities.containment_event import (
    ContainmentEvent,
    ContainmentMode,
    ContainmentStatus,
)
from app.domain.entities.recovery_plan import RecoveryOutcome, RecoveryPlan, RecoveryStatus
from app.domain.repositories.containment_repository import (
    ContainmentRepository,
    RecoveryPlanRepository,
)
from app.infrastructure.persistence.models.containment_event_model import ContainmentEventModel
from app.infrastructure.persistence.models.recovery_plan_model import RecoveryPlanModel


class SQLAlchemyContainmentRepository(ContainmentRepository):
    """SQLAlchemy adapter for ContainmentRepository port."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def get_by_containment_id(
        self, tenant_id: str, containment_id: str
    ) -> ContainmentEvent | None:
        stmt = select(ContainmentEventModel).where(
            ContainmentEventModel.tenant_id == tenant_id,
            ContainmentEventModel.containment_id == containment_id,
        )
        model = self._session.scalar(stmt)
        return self._to_entity(model) if model else None

    async def list_by_agent(
        self,
        tenant_id: str,
        target_agent_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ContainmentEvent], int]:
        stmt = select(ContainmentEventModel).where(
            ContainmentEventModel.tenant_id == tenant_id,
            ContainmentEventModel.target_agent_id == target_agent_id,
        )
        count_stmt = select(ContainmentEventModel).where(
            ContainmentEventModel.tenant_id == tenant_id,
            ContainmentEventModel.target_agent_id == target_agent_id,
        )
        total = len(self._session.scalars(count_stmt).all())
        stmt = stmt.order_by(ContainmentEventModel.created_at.desc()).limit(limit).offset(offset)
        models = self._session.scalars(stmt).all()
        return [self._to_entity(m) for m in models], total

    async def save(self, event: ContainmentEvent) -> ContainmentEvent:
        stmt = select(ContainmentEventModel).where(
            ContainmentEventModel.containment_id == event.containment_id
        )
        model = self._session.scalar(stmt)
        if model is None:
            model = ContainmentEventModel(
                containment_id=event.containment_id,
                tenant_id=event.tenant_id,
                target_agent_id=event.target_agent_id,
                target_authority_id=event.target_authority_id,
                mode=event.mode.value,
                status=event.status.value,
                initiated_by=event.initiated_by,
                authorized_by=event.authorized_by,
                reason=event.reason,
                affected_agent_ids=json.dumps(event.affected_agent_ids),
                affected_authority_ids=json.dumps(event.affected_authority_ids),
                affected_session_ids=json.dumps(event.affected_session_ids),
                affected_token_ids=json.dumps(event.affected_token_ids),
                affected_action_ids=json.dumps(event.affected_action_ids),
                dry_run=event.dry_run,
                result_details=json.dumps(event.result_details),
                created_at=event.created_at,
                completed_at=event.completed_at,
            )
            self._session.add(model)
        else:
            model.status = event.status.value
            model.completed_at = event.completed_at
            model.result_details = json.dumps(event.result_details)
            model.affected_agent_ids = json.dumps(event.affected_agent_ids)
            model.affected_authority_ids = json.dumps(event.affected_authority_ids)
            model.affected_session_ids = json.dumps(event.affected_session_ids)
            model.affected_token_ids = json.dumps(event.affected_token_ids)
            model.affected_action_ids = json.dumps(event.affected_action_ids)
        self._session.flush()
        return self._to_entity(model)

    async def update_status(
        self,
        tenant_id: str,
        containment_id: str,
        status: ContainmentStatus,
        result_details: dict[str, str] | None = None,
    ) -> ContainmentEvent | None:
        stmt = select(ContainmentEventModel).where(
            ContainmentEventModel.tenant_id == tenant_id,
            ContainmentEventModel.containment_id == containment_id,
        )
        model = self._session.scalar(stmt)
        if model is None:
            return None
        model.status = status.value
        if result_details is not None:
            model.result_details = json.dumps(result_details)
        if status in (
            ContainmentStatus.COMPLETED,
            ContainmentStatus.FAILED,
            ContainmentStatus.PARTIAL,
        ):
            model.completed_at = datetime.now(UTC)
        self._session.flush()
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: ContainmentEventModel) -> ContainmentEvent:
        affected_agent_ids: list[str] = []
        if model.affected_agent_ids:
            try:
                affected_agent_ids = json.loads(model.affected_agent_ids)
            except (ValueError, TypeError):
                affected_agent_ids = []
        affected_authority_ids: list[str] = []
        if model.affected_authority_ids:
            try:
                affected_authority_ids = json.loads(model.affected_authority_ids)
            except (ValueError, TypeError):
                affected_authority_ids = []
        affected_session_ids: list[str] = []
        if model.affected_session_ids:
            try:
                affected_session_ids = json.loads(model.affected_session_ids)
            except (ValueError, TypeError):
                affected_session_ids = []
        affected_token_ids: list[str] = []
        if model.affected_token_ids:
            try:
                affected_token_ids = json.loads(model.affected_token_ids)
            except (ValueError, TypeError):
                affected_token_ids = []
        affected_action_ids: list[str] = []
        if model.affected_action_ids:
            try:
                affected_action_ids = json.loads(model.affected_action_ids)
            except (ValueError, TypeError):
                affected_action_ids = []
        result_details: dict[str, str] = {}
        if model.result_details:
            try:
                result_details = json.loads(model.result_details)
            except (ValueError, TypeError):
                result_details = {}
        return ContainmentEvent(
            containment_id=model.containment_id,
            tenant_id=model.tenant_id,
            target_agent_id=model.target_agent_id,
            target_authority_id=model.target_authority_id,
            mode=ContainmentMode(model.mode),
            status=ContainmentStatus(model.status),
            initiated_by=model.initiated_by,
            authorized_by=model.authorized_by,
            reason=model.reason,
            affected_agent_ids=affected_agent_ids,
            affected_authority_ids=affected_authority_ids,
            affected_session_ids=affected_session_ids,
            affected_token_ids=affected_token_ids,
            affected_action_ids=affected_action_ids,
            dry_run=model.dry_run,
            result_details=result_details,
            created_at=model.created_at,
            completed_at=model.completed_at,
        )


class SQLAlchemyRecoveryPlanRepository(RecoveryPlanRepository):
    """SQLAlchemy adapter for RecoveryPlanRepository port."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def get_by_plan_id(self, tenant_id: str, plan_id: str) -> RecoveryPlan | None:
        stmt = select(RecoveryPlanModel).where(
            RecoveryPlanModel.tenant_id == tenant_id,
            RecoveryPlanModel.plan_id == plan_id,
        )
        model = self._session.scalar(stmt)
        return self._to_entity(model) if model else None

    async def list_by_incident(
        self,
        tenant_id: str,
        incident_action_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[RecoveryPlan], int]:
        stmt = select(RecoveryPlanModel).where(
            RecoveryPlanModel.tenant_id == tenant_id,
            RecoveryPlanModel.incident_action_id == incident_action_id,
        )
        count_stmt = select(RecoveryPlanModel).where(
            RecoveryPlanModel.tenant_id == tenant_id,
            RecoveryPlanModel.incident_action_id == incident_action_id,
        )
        total = len(self._session.scalars(count_stmt).all())
        stmt = stmt.order_by(RecoveryPlanModel.created_at.desc()).limit(limit).offset(offset)
        models = self._session.scalars(stmt).all()
        return [self._to_entity(m) for m in models], total

    async def save(self, plan: RecoveryPlan) -> RecoveryPlan:
        stmt = select(RecoveryPlanModel).where(
            RecoveryPlanModel.plan_id == plan.plan_id,
            RecoveryPlanModel.tenant_id == plan.tenant_id,
        )
        model = self._session.scalar(stmt)
        if model is None:
            model = RecoveryPlanModel(
                plan_id=plan.plan_id,
                tenant_id=plan.tenant_id,
                incident_action_id=plan.incident_action_id,
                status=plan.status.value,
                outcome=plan.outcome.value,
                simulation_result=json.dumps(plan.simulation_result),
                steps=json.dumps(plan.steps),
                approved_by=plan.approved_by,
                executed_by=plan.executed_by,
                created_at=plan.created_at,
                updated_at=plan.updated_at,
                executed_at=plan.executed_at,
                plan_version=plan.plan_version,
                plan_hash=plan.plan_hash,
                topological_order=json.dumps(plan.topological_order),
                dependency_graph_reference=plan.dependency_graph_reference,
                execution_status=plan.execution_status,
                approval_policy=plan.approval_policy,
                approval_threshold=plan.approval_threshold,
                stop_conditions=json.dumps(plan.stop_conditions),
                compensation_summary=json.dumps(plan.compensation_summary),
                incident_id=plan.incident_id,
                root_action_id=plan.root_action_id,
                affected_action_ids=json.dumps(plan.affected_action_ids),
            )
            self._session.add(model)
        else:
            model.status = plan.status.value
            model.outcome = plan.outcome.value
            model.simulation_result = json.dumps(plan.simulation_result)
            model.steps = json.dumps(plan.steps)
            model.approved_by = plan.approved_by
            model.executed_by = plan.executed_by
            model.updated_at = datetime.now(UTC)
            model.executed_at = plan.executed_at
            model.plan_version = plan.plan_version
            model.plan_hash = plan.plan_hash
            model.topological_order = json.dumps(plan.topological_order)
            model.dependency_graph_reference = plan.dependency_graph_reference
            model.execution_status = plan.execution_status
            model.approval_policy = plan.approval_policy
            model.approval_threshold = plan.approval_threshold
            model.stop_conditions = json.dumps(plan.stop_conditions)
            model.compensation_summary = json.dumps(plan.compensation_summary)
            model.incident_id = plan.incident_id
            model.root_action_id = plan.root_action_id
            model.affected_action_ids = json.dumps(plan.affected_action_ids)
        self._session.flush()
        return self._to_entity(model)

    async def update_status(
        self,
        tenant_id: str,
        plan_id: str,
        status: RecoveryStatus,
        **fields: object,
    ) -> RecoveryPlan | None:
        stmt = select(RecoveryPlanModel).where(
            RecoveryPlanModel.tenant_id == tenant_id,
            RecoveryPlanModel.plan_id == plan_id,
        )
        model = self._session.scalar(stmt)
        if model is None:
            return None
        model.status = status.value
        for key, value in fields.items():
            if hasattr(model, key):
                setattr(model, key, value)
        model.updated_at = datetime.now(UTC)
        if status == RecoveryStatus.COMPLETED:
            model.executed_at = datetime.now(UTC)
        self._session.flush()
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: RecoveryPlanModel) -> RecoveryPlan:
        simulation_result: dict[str, str] = {}
        if model.simulation_result:
            try:
                simulation_result = json.loads(model.simulation_result)
            except (ValueError, TypeError):
                simulation_result = {}
        steps: list[dict[str, str]] = []
        if model.steps:
            try:
                steps = json.loads(model.steps)
            except (ValueError, TypeError):
                steps = []

        def _safe_json_list(raw: str | None) -> list[str]:
            if not raw:
                return []
            try:
                data = json.loads(raw)
                return data if isinstance(data, list) else []
            except (ValueError, TypeError):
                return []

        def _safe_json_dict(raw: str | None) -> dict[str, object]:
            if not raw:
                return {}
            try:
                data = json.loads(raw)
                return data if isinstance(data, dict) else {}
            except (ValueError, TypeError):
                return {}

        return RecoveryPlan(
            plan_id=model.plan_id,
            tenant_id=model.tenant_id,
            incident_action_id=model.incident_action_id,
            status=RecoveryStatus(model.status),
            outcome=(
                RecoveryOutcome(model.outcome)
                if model.outcome in RecoveryOutcome._value2member_map_
                else RecoveryOutcome.UNKNOWN
            ),
            simulation_result=simulation_result,
            steps=steps,
            approved_by=model.approved_by,
            executed_by=model.executed_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
            executed_at=model.executed_at,
            plan_version=model.plan_version or "1.0",
            plan_hash=model.plan_hash or "",
            topological_order=_safe_json_list(model.topological_order),
            dependency_graph_reference=model.dependency_graph_reference or "",
            execution_status=model.execution_status or "pending",
            approval_policy=model.approval_policy or "single_approval",
            approval_threshold=model.approval_threshold or 1,
            stop_conditions=_safe_json_list(model.stop_conditions),
            compensation_summary=_safe_json_dict(model.compensation_summary),
            incident_id=model.incident_id or "",
            root_action_id=model.root_action_id or "",
            affected_action_ids=_safe_json_list(model.affected_action_ids),
        )
