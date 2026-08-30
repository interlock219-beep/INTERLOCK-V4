import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.entities.agent import (
    Agent,
    AgentEnvironment,
    AgentStatus,
    AgentType,
    RegistrationMethod,
    RiskClassification,
    TrustLevel,
)
from app.domain.repositories.agent_repository import AgentRepository
from app.infrastructure.persistence.models.agent_model import AgentModel


class SQLAlchemyAgentRepository(AgentRepository):
    """SQLAlchemy adapter for AgentRepository port."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def get_by_agent_id(self, tenant_id: str, agent_id: str) -> Agent | None:
        stmt = select(AgentModel).where(
            AgentModel.tenant_id == tenant_id,
            AgentModel.agent_id == agent_id,
        )
        model = self._session.scalar(stmt)
        return self._to_entity(model) if model else None

    async def list_by_tenant(
        self,
        tenant_id: str,
        status: AgentStatus | None = None,
        agent_type: AgentType | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Agent], int]:
        stmt = select(AgentModel).where(AgentModel.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(AgentModel.status == status.value)
        if agent_type is not None:
            stmt = stmt.where(AgentModel.agent_type == agent_type.value)
        count_stmt = select(AgentModel).where(AgentModel.tenant_id == tenant_id)
        if status is not None:
            count_stmt = count_stmt.where(AgentModel.status == status.value)
        if agent_type is not None:
            count_stmt = count_stmt.where(AgentModel.agent_type == agent_type.value)
        total = self._session.scalar(
            select(func.count()).select_from(count_stmt.subquery())
        ) or 0
        stmt = stmt.order_by(AgentModel.created_at.desc()).limit(limit).offset(offset)
        models = self._session.scalars(stmt).all()
        return [self._to_entity(m) for m in models], total

    async def save(self, agent: Agent) -> Agent:
        stmt = select(AgentModel).where(AgentModel.agent_id == agent.agent_id)
        model = self._session.scalar(stmt)
        if model is None:
            model = AgentModel(
                agent_id=agent.agent_id,
                tenant_id=agent.tenant_id,
                name=agent.name,
                description=agent.description,
                owner_user_id=agent.owner_user_id,
                parent_agent_id=agent.parent_agent_id,
                agent_type=agent.agent_type.value,
                status=agent.status.value,
                trust_level=agent.trust_level.value,
                model_provider=agent.model_provider,
                model_name=agent.model_name,
                risk_classification=agent.risk_classification.value,
                environment=agent.environment.value,
                version=agent.version,
                creator=agent.creator,
                registration_method=agent.registration_method.value,
                root_human_sponsor=agent.root_human_sponsor,
                expires_at=agent.expires_at,
                last_activity_at=agent.last_activity_at,
                connected_tools=json.dumps(agent.connected_tools),
                agent_metadata=json.dumps(agent.metadata),
                created_at=agent.created_at,
                updated_at=agent.updated_at,
            )
            self._session.add(model)
        else:
            model.name = agent.name
            model.description = agent.description
            model.owner_user_id = agent.owner_user_id
            model.parent_agent_id = agent.parent_agent_id
            model.agent_type = agent.agent_type.value
            model.status = agent.status.value
            model.trust_level = agent.trust_level.value
            model.model_provider = agent.model_provider
            model.model_name = agent.model_name
            model.risk_classification = agent.risk_classification.value
            model.environment = agent.environment.value
            model.version = agent.version
            model.creator = agent.creator
            model.registration_method = agent.registration_method.value
            model.root_human_sponsor = agent.root_human_sponsor
            model.expires_at = agent.expires_at
            model.last_activity_at = agent.last_activity_at
            model.connected_tools = json.dumps(agent.connected_tools)
            model.agent_metadata = json.dumps(agent.metadata)
            model.updated_at = datetime.now(UTC)
        self._session.flush()
        return self._to_entity(model)

    async def delete(self, tenant_id: str, agent_id: str) -> bool:
        stmt = select(AgentModel).where(
            AgentModel.tenant_id == tenant_id,
            AgentModel.agent_id == agent_id,
        )
        model = self._session.scalar(stmt)
        if model is None:
            return False
        self._session.delete(model)
        self._session.flush()
        return True

    async def update_status(
        self, tenant_id: str, agent_id: str, status: AgentStatus
    ) -> Agent | None:
        stmt = select(AgentModel).where(
            AgentModel.tenant_id == tenant_id,
            AgentModel.agent_id == agent_id,
        )
        model = self._session.scalar(stmt)
        if model is None:
            return None
        model.status = status.value
        model.updated_at = datetime.now(UTC)
        self._session.flush()
        return self._to_entity(model)

    async def exists(self, tenant_id: str, agent_id: str) -> bool:
        stmt = select(func.count()).where(
            AgentModel.tenant_id == tenant_id,
            AgentModel.agent_id == agent_id,
        )
        return (self._session.scalar(stmt) or 0) > 0

    @staticmethod
    def _to_entity(model: AgentModel) -> Agent:
        connected_tools = []
        if model.connected_tools:
            try:
                connected_tools = json.loads(model.connected_tools)
            except (ValueError, TypeError):
                connected_tools = []
        metadata: dict[str, str] = {}
        if model.agent_metadata:
            try:
                metadata = json.loads(model.agent_metadata)
            except (ValueError, TypeError):
                metadata = {}
        return Agent(
            agent_id=model.agent_id,
            tenant_id=model.tenant_id,
            name=model.name,
            description=model.description,
            owner_user_id=model.owner_user_id,
            parent_agent_id=model.parent_agent_id,
            agent_type=AgentType(model.agent_type),
            status=AgentStatus(model.status),
            trust_level=TrustLevel(model.trust_level),
            model_provider=model.model_provider,
            model_name=model.model_name,
            risk_classification=RiskClassification(model.risk_classification),
            environment=AgentEnvironment(model.environment),
            version=model.version,
            creator=model.creator,
            registration_method=RegistrationMethod(model.registration_method),
            root_human_sponsor=model.root_human_sponsor,
            expires_at=model.expires_at,
            last_activity_at=model.last_activity_at,
            connected_tools=connected_tools,
            metadata=metadata,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
