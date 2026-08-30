import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities.protected_action import ActionStatus, ProtectedAction, Reversibility
from app.domain.repositories.protected_action_repository import ProtectedActionRepository
from app.infrastructure.persistence.models.protected_action_model import ProtectedActionModel


class SQLAlchemyProtectedActionRepository(ProtectedActionRepository):
    """SQLAlchemy adapter for ProtectedActionRepository port."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def get_by_action_id(self, tenant_id: str, action_id: str) -> ProtectedAction | None:
        stmt = select(ProtectedActionModel).where(
            ProtectedActionModel.tenant_id == tenant_id,
            ProtectedActionModel.action_id == action_id,
        )
        model = self._session.scalar(stmt)
        return self._to_entity(model) if model else None

    async def list_by_agent(
        self,
        tenant_id: str,
        agent_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ProtectedAction], int]:
        stmt = select(ProtectedActionModel).where(
            ProtectedActionModel.tenant_id == tenant_id,
            ProtectedActionModel.agent_id == agent_id,
        )
        count_stmt = select(ProtectedActionModel).where(
            ProtectedActionModel.tenant_id == tenant_id,
            ProtectedActionModel.agent_id == agent_id,
        )
        total = len(self._session.scalars(count_stmt).all())
        stmt = stmt.order_by(ProtectedActionModel.created_at.desc()).limit(limit).offset(offset)
        models = self._session.scalars(stmt).all()
        return [self._to_entity(m) for m in models], total

    async def list_by_correlation(
        self,
        tenant_id: str,
        correlation_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ProtectedAction], int]:
        stmt = select(ProtectedActionModel).where(
            ProtectedActionModel.tenant_id == tenant_id,
            ProtectedActionModel.correlation_id == correlation_id,
        )
        count_stmt = select(ProtectedActionModel).where(
            ProtectedActionModel.tenant_id == tenant_id,
            ProtectedActionModel.correlation_id == correlation_id,
        )
        total = len(self._session.scalars(count_stmt).all())
        stmt = stmt.order_by(ProtectedActionModel.created_at.desc()).limit(limit).offset(offset)
        models = self._session.scalars(stmt).all()
        return [self._to_entity(m) for m in models], total

    async def list_descendants(
        self,
        tenant_id: str,
        root_action_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ProtectedAction], int]:
        visited: set[str] = set()
        result: list[ProtectedAction] = []

        def _collect(parent_id: str) -> None:
            children = self._session.scalars(
                select(ProtectedActionModel).where(
                    ProtectedActionModel.tenant_id == tenant_id,
                    ProtectedActionModel.parent_action_id == parent_id,
                )
            ).all()
            for child in children:
                if child.action_id not in visited:
                    visited.add(child.action_id)
                    result.append(self._to_entity(child))
                    _collect(child.action_id)

        _collect(root_action_id)
        total = len(result)
        return result[offset : offset + limit], total

    async def save(self, action: ProtectedAction) -> ProtectedAction:
        stmt = select(ProtectedActionModel).where(
            ProtectedActionModel.action_id == action.action_id
        )
        model = self._session.scalar(stmt)
        if model is None:
            model = ProtectedActionModel(
                action_id=action.action_id,
                tenant_id=action.tenant_id,
                actor_user_id=action.actor_user_id,
                agent_id=action.agent_id,
                authority_grant_id=action.authority_grant_id,
                tool=action.tool,
                resource=action.resource,
                action_type=action.action_type,
                risk_score=action.risk_score,
                policy_version=action.policy_version,
                correlation_id=action.correlation_id,
                parent_action_id=action.parent_action_id,
                workflow_id=action.workflow_id,
                reversibility=action.reversibility.value,
                before_state_ref=action.before_state_ref,
                after_state_ref=action.after_state_ref,
                tool_arguments=json.dumps(action.tool_arguments),
                status=action.status.value,
                decision_reason=action.decision_reason,
                evaluated_at=action.evaluated_at,
                executed_at=action.executed_at,
                created_at=action.created_at,
            )
            self._session.add(model)
        else:
            model.status = action.status.value
            model.decision_reason = action.decision_reason
            model.evaluated_at = action.evaluated_at
            model.executed_at = action.executed_at
            model.after_state_ref = action.after_state_ref
            model.risk_score = action.risk_score
        self._session.flush()
        return self._to_entity(model)

    async def update_status(
        self, tenant_id: str, action_id: str, status: ActionStatus, reason: str = ""
    ) -> ProtectedAction | None:
        stmt = select(ProtectedActionModel).where(
            ProtectedActionModel.tenant_id == tenant_id,
            ProtectedActionModel.action_id == action_id,
        )
        model = self._session.scalar(stmt)
        if model is None:
            return None
        model.status = status.value
        model.decision_reason = reason or model.decision_reason
        if status == ActionStatus.EVALUATING:
            model.evaluated_at = datetime.now(UTC)
        if status == ActionStatus.EXECUTED:
            model.executed_at = datetime.now(UTC)
        self._session.flush()
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: ProtectedActionModel) -> ProtectedAction:
        tool_arguments: dict[str, str] = {}
        if model.tool_arguments:
            try:
                tool_arguments = json.loads(model.tool_arguments)
            except (ValueError, TypeError):
                tool_arguments = {}
        return ProtectedAction(
            action_id=model.action_id,
            tenant_id=model.tenant_id,
            actor_user_id=model.actor_user_id,
            agent_id=model.agent_id,
            authority_grant_id=model.authority_grant_id,
            tool=model.tool,
            resource=model.resource,
            action_type=model.action_type,
            risk_score=model.risk_score,
            policy_version=model.policy_version,
            correlation_id=model.correlation_id,
            parent_action_id=model.parent_action_id,
            workflow_id=model.workflow_id,
            reversibility=Reversibility(model.reversibility),
            before_state_ref=model.before_state_ref,
            after_state_ref=model.after_state_ref,
            tool_arguments=tool_arguments,
            status=ActionStatus(model.status),
            decision_reason=model.decision_reason,
            evaluated_at=model.evaluated_at,
            executed_at=model.executed_at,
            created_at=model.created_at,
        )
