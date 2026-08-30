from abc import ABC, abstractmethod

from app.domain.entities.surgical_recovery_types import RecoveryExecution


class RecoveryExecutionRepository(ABC):
    """Persistence port for RecoveryExecution aggregate."""

    @abstractmethod
    async def get_by_execution_id(
        self, tenant_id: str, execution_id: str
    ) -> RecoveryExecution | None: ...

    @abstractmethod
    async def list_by_plan(
        self,
        tenant_id: str,
        plan_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[RecoveryExecution], int]: ...

    @abstractmethod
    async def list_by_action(
        self,
        tenant_id: str,
        action_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[RecoveryExecution], int]: ...

    @abstractmethod
    async def save(self, execution: RecoveryExecution) -> RecoveryExecution: ...
