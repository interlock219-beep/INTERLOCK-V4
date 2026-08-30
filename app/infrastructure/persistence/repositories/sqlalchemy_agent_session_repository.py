from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities.agent_session import AgentSession, AgentSessionStatus
from app.domain.repositories.agent_session_repository import AgentSessionRepository
from app.infrastructure.persistence.models.agent_session_model import AgentSessionModel


class SQLAlchemyAgentSessionRepository(AgentSessionRepository):
    """SQLAlchemy adapter for AgentSessionRepository port."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def get_by_session_id(
        self, tenant_id: str, session_id: str
    ) -> AgentSession | None:
        stmt = select(AgentSessionModel).where(
            AgentSessionModel.tenant_id == tenant_id,
            AgentSessionModel.session_id == session_id,
        )
        model = self._session.scalar(stmt)
        return self._to_entity(model) if model else None

    async def list_by_agent(
        self,
        tenant_id: str,
        agent_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[AgentSession], int]:
        stmt = (
            select(AgentSessionModel)
            .where(
                AgentSessionModel.tenant_id == tenant_id,
                AgentSessionModel.agent_id == agent_id,
            )
            .order_by(AgentSessionModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        models = self._session.scalars(stmt).all()
        count_stmt = select(AgentSessionModel).where(
            AgentSessionModel.tenant_id == tenant_id,
            AgentSessionModel.agent_id == agent_id,
        )
        total = len(self._session.scalars(count_stmt).all())
        return [self._to_entity(m) for m in models], total

    async def list_by_tenant(
        self,
        tenant_id: str,
        status: AgentSessionStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[AgentSession], int]:
        stmt = select(AgentSessionModel).where(
            AgentSessionModel.tenant_id == tenant_id
        )
        if status is not None:
            stmt = stmt.where(AgentSessionModel.status == status.value)
        stmt = (
            stmt.order_by(AgentSessionModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        models = self._session.scalars(stmt).all()
        count_stmt = select(AgentSessionModel).where(
            AgentSessionModel.tenant_id == tenant_id
        )
        if status is not None:
            count_stmt = count_stmt.where(AgentSessionModel.status == status.value)
        total = len(self._session.scalars(count_stmt).all())
        return [self._to_entity(m) for m in models], total

    async def save(self, session: AgentSession) -> AgentSession:
        stmt = select(AgentSessionModel).where(
            AgentSessionModel.session_id == session.session_id
        )
        model = self._session.scalar(stmt)
        if model is None:
            model = AgentSessionModel(
                session_id=session.session_id,
                tenant_id=session.tenant_id,
                agent_id=session.agent_id,
                intent_id=session.intent_id,
                policy_version=session.policy_version,
                started_at=session.started_at,
                ended_at=session.ended_at,
                status=session.status.value,
                risk_level=session.risk_level,
                correlation_id=session.correlation_id,
                parent_session_id=session.parent_session_id,
                session_metadata=json.dumps(session.metadata) if session.metadata else None,
                created_at=session.started_at,
            )
            self._session.add(model)
        else:
            model.status = session.status.value
            model.ended_at = session.ended_at
            model.risk_level = session.risk_level
            model.session_metadata = (
                json.dumps(session.metadata) if session.metadata else None
            )
        self._session.flush()
        return self._to_entity(model)

    async def update_status(
        self,
        tenant_id: str,
        session_id: str,
        status: AgentSessionStatus,
        ended_at: datetime | None = None,
    ) -> AgentSession | None:
        stmt = select(AgentSessionModel).where(
            AgentSessionModel.tenant_id == tenant_id,
            AgentSessionModel.session_id == session_id,
        )
        model = self._session.scalar(stmt)
        if model is None:
            return None
        model.status = status.value
        model.ended_at = ended_at or datetime.now(UTC)
        self._session.flush()
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: AgentSessionModel) -> AgentSession:
        metadata: dict[str, Any] = {}
        if model.session_metadata:
            try:
                metadata = json.loads(model.session_metadata)
            except (ValueError, TypeError):
                metadata = {}
        return AgentSession(
            session_id=model.session_id,
            tenant_id=model.tenant_id,
            agent_id=model.agent_id,
            intent_id=model.intent_id,
            policy_version=model.policy_version,
            started_at=model.started_at,
            ended_at=model.ended_at,
            status=AgentSessionStatus(model.status),
            risk_level=model.risk_level,
            correlation_id=model.correlation_id,
            parent_session_id=model.parent_session_id,
            metadata=metadata,
        )
