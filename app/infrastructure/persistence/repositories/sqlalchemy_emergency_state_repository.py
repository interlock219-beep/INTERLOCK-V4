from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.repositories.emergency_state_repository import EmergencyStateRepository
from app.infrastructure.persistence.models.emergency_state_model import EmergencyStateModel


class SQLAlchemyEmergencyStateRepository(EmergencyStateRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    async def get_by_tenant(self, tenant_id: str) -> EmergencyStateModel | None:
        stmt = select(EmergencyStateModel).where(EmergencyStateModel.tenant_id == tenant_id)
        return self._session.scalar(stmt)

    async def upsert(self, state: EmergencyStateModel) -> EmergencyStateModel:
        self._session.merge(state)
        self._session.flush()
        return state

    async def delete(self, tenant_id: str) -> None:
        stmt = select(EmergencyStateModel).where(EmergencyStateModel.tenant_id == tenant_id)
        model = self._session.scalar(stmt)
        if model is not None:
            self._session.delete(model)
            self._session.flush()
