import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities.discovery_event import DiscoveryEvent, DiscoverySource, DiscoveryStatus
from app.domain.repositories.discovery_event_repository import DiscoveryEventRepository
from app.infrastructure.persistence.models.discovery_event_model import DiscoveryEventModel


class SQLAlchemyDiscoveryEventRepository(DiscoveryEventRepository):
    """SQLAlchemy adapter for DiscoveryEventRepository port."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def get_by_discovery_id(self, tenant_id: str, discovery_id: str) -> DiscoveryEvent | None:
        stmt = select(DiscoveryEventModel).where(
            DiscoveryEventModel.tenant_id == tenant_id,
            DiscoveryEventModel.discovery_id == discovery_id,
        )
        model = self._session.scalar(stmt)
        return self._to_entity(model) if model else None

    async def list_by_tenant(
        self,
        tenant_id: str,
        source: DiscoverySource | None = None,
        discovery_status: DiscoveryStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[DiscoveryEvent], int]:
        stmt = select(DiscoveryEventModel).where(DiscoveryEventModel.tenant_id == tenant_id)
        if source is not None:
            stmt = stmt.where(DiscoveryEventModel.source == source.value)
        if discovery_status is not None:
            stmt = stmt.where(DiscoveryEventModel.discovery_status == discovery_status.value)
        count_stmt = select(DiscoveryEventModel).where(DiscoveryEventModel.tenant_id == tenant_id)
        if source is not None:
            count_stmt = count_stmt.where(DiscoveryEventModel.source == source.value)
        if discovery_status is not None:
            count_stmt = count_stmt.where(
                DiscoveryEventModel.discovery_status == discovery_status.value
            )
        total = len(self._session.scalars(count_stmt).all())
        stmt = stmt.order_by(DiscoveryEventModel.created_at.desc()).limit(limit).offset(offset)
        models = self._session.scalars(stmt).all()
        return [self._to_entity(m) for m in models], total

    async def list_by_agent(
        self,
        tenant_id: str,
        agent_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[DiscoveryEvent], int]:
        stmt = select(DiscoveryEventModel).where(
            DiscoveryEventModel.tenant_id == tenant_id,
            DiscoveryEventModel.agent_id == agent_id,
        )
        count_stmt = select(DiscoveryEventModel).where(
            DiscoveryEventModel.tenant_id == tenant_id,
            DiscoveryEventModel.agent_id == agent_id,
        )
        total = len(self._session.scalars(count_stmt).all())
        stmt = stmt.order_by(DiscoveryEventModel.created_at.desc()).limit(limit).offset(offset)
        models = self._session.scalars(stmt).all()
        return [self._to_entity(m) for m in models], total

    async def save(self, event: DiscoveryEvent) -> DiscoveryEvent:
        stmt = select(DiscoveryEventModel).where(
            DiscoveryEventModel.discovery_id == event.discovery_id
        )
        model = self._session.scalar(stmt)
        if model is None:
            model = DiscoveryEventModel(
                discovery_id=event.discovery_id,
                tenant_id=event.tenant_id,
                source=event.source.value,
                discovery_status=event.discovery_status.value,
                agent_id=event.agent_id,
                resource_type=event.resource_type,
                resource_id=event.resource_id,
                resource_metadata=json.dumps(event.resource_metadata),
                finding_severity=event.finding_severity,
                finding_message=event.finding_message,
                created_at=event.created_at,
            )
            self._session.add(model)
        else:
            model.discovery_status = event.discovery_status.value
            model.finding_severity = event.finding_severity
            model.finding_message = event.finding_message
            model.resource_metadata = json.dumps(event.resource_metadata)
        self._session.flush()
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: DiscoveryEventModel) -> DiscoveryEvent:
        resource_metadata: dict[str, str] = {}
        if model.resource_metadata:
            try:
                resource_metadata = json.loads(model.resource_metadata)
            except (ValueError, TypeError):
                resource_metadata = {}
        return DiscoveryEvent(
            discovery_id=model.discovery_id,
            tenant_id=model.tenant_id,
            source=DiscoverySource(model.source),
            discovery_status=DiscoveryStatus(model.discovery_status),
            agent_id=model.agent_id,
            resource_type=model.resource_type,
            resource_id=model.resource_id,
            resource_metadata=resource_metadata,
            finding_severity=model.finding_severity,
            finding_message=model.finding_message,
            created_at=model.created_at,
        )
