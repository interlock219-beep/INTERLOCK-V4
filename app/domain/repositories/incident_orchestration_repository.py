from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities.incident_orchestration_types import (
    IncidentOrchestrationPlan,
    OrchestrationResult,
    OrchestrationStep,
)


class IncidentOrchestrationRepository(ABC):
    """Persistence port for incident orchestration state."""

    @abstractmethod
    async def save_orchestration_plan(
        self, tenant_id: str, plan: IncidentOrchestrationPlan
    ) -> IncidentOrchestrationPlan: ...

    @abstractmethod
    async def get_orchestration_plan(
        self, tenant_id: str, plan_id: str
    ) -> IncidentOrchestrationPlan | None: ...

    @abstractmethod
    async def save_step(self, tenant_id: str, step: OrchestrationStep) -> OrchestrationStep: ...

    @abstractmethod
    async def list_steps(
        self,
        tenant_id: str,
        plan_id: str,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[list[OrchestrationStep], int]: ...

    @abstractmethod
    async def save_result(
        self, tenant_id: str, result: OrchestrationResult
    ) -> OrchestrationResult: ...

    @abstractmethod
    async def get_result(
        self, tenant_id: str, orchestration_id: str
    ) -> OrchestrationResult | None: ...


__all__ = ["IncidentOrchestrationRepository"]
