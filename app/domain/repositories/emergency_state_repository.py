from abc import ABC, abstractmethod

from app.infrastructure.persistence.models.emergency_state_model import EmergencyStateModel


class EmergencyStateRepository(ABC):
    @abstractmethod
    async def get_by_tenant(self, tenant_id: str) -> EmergencyStateModel | None: ...

    @abstractmethod
    async def upsert(self, state: EmergencyStateModel) -> EmergencyStateModel: ...

    @abstractmethod
    async def delete(self, tenant_id: str) -> None: ...
