from app.application.dto.billing import PlanResponse
from app.domain.repositories.billing_repositories import PlanRepository


class ListPlansUseCase:
    def __init__(self, plan_repository: PlanRepository) -> None:
        self._plan_repository = plan_repository

    async def execute(self) -> list[PlanResponse]:
        plans = await self._plan_repository.list_active()
        return [
            PlanResponse(
                id=str(plan.id),
                name=plan.name,
                tier=plan.tier.value,
                price_monthly_cents=plan.price_monthly_cents,
                price_yearly_cents=plan.price_yearly_cents,
                currency=plan.currency,
                features=plan.features,
                limits=plan.limits,
            )
            for plan in plans
        ]
