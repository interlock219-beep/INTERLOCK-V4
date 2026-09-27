from __future__ import annotations

from app.domain.entities.incident_orchestration_types import (
    IncidentOrchestrationPlan,
    OrchestrationResult,
    OrchestrationStep,
)
from app.domain.repositories.incident_orchestration_repository import (
    IncidentOrchestrationRepository,
)


class InMemoryIncidentOrchestrationRepository(IncidentOrchestrationRepository):
    """In-memory implementation of :class:`IncidentOrchestrationRepository`.

    Suitable for unit tests and single-process deployments.
    """

    def __init__(self) -> None:
        self._plans: dict[str, IncidentOrchestrationPlan] = {}
        self._steps: dict[str, list[OrchestrationStep]] = {}
        self._results: dict[str, OrchestrationResult] = {}

    async def save_orchestration_plan(
        self, tenant_id: str, plan: IncidentOrchestrationPlan
    ) -> IncidentOrchestrationPlan:
        self._plans[plan.plan_id] = plan
        return plan

    async def get_orchestration_plan(
        self, tenant_id: str, plan_id: str
    ) -> IncidentOrchestrationPlan | None:
        plan = self._plans.get(plan_id)
        if plan is not None and plan.tenant_id == tenant_id:
            return plan
        return None

    async def save_step(self, tenant_id: str, step: OrchestrationStep) -> OrchestrationStep:
        plan_id = (
            step.plan_id
            if hasattr(step, "plan_id")
            else step.orchestration_id
            if hasattr(step, "orchestration_id")
            else ""
        )
        if plan_id:
            if plan_id not in self._steps:
                self._steps[plan_id] = []
            self._steps[plan_id].append(step)
        else:
            key = f"{step.tenant_id}:{step.incident_id}"
            if key not in self._steps:
                self._steps[key] = []
            self._steps[key].append(step)
        return step

    async def list_steps(
        self,
        tenant_id: str,
        plan_id: str,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[list[OrchestrationStep], int]:
        steps = self._steps.get(plan_id, [])
        total = len(steps)
        page = steps[offset : offset + limit]
        return page, total

    async def save_result(self, tenant_id: str, result: OrchestrationResult) -> OrchestrationResult:
        self._results[result.orchestration_id] = result
        return result

    async def get_result(self, tenant_id: str, orchestration_id: str) -> OrchestrationResult | None:
        result = self._results.get(orchestration_id)
        if result is not None and result.tenant_id == tenant_id:
            return result
        return None


__all__ = ["InMemoryIncidentOrchestrationRepository"]
