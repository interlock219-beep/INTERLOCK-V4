from uuid import UUID

from app.application.dto.billing import PlanResponse, SubscriptionResponse
from app.domain.repositories.billing_repositories import (
    PlanRepository,
    SubscriptionRepository,
)


class GetSubscriptionUseCase:
    def __init__(
        self,
        subscription_repository: SubscriptionRepository,
        plan_repository: PlanRepository,
    ) -> None:
        self._subscription_repository = subscription_repository
        self._plan_repository = plan_repository

    async def execute(
        self, user_id: UUID
    ) -> tuple[SubscriptionResponse | None, PlanResponse | None]:
        subscription = (
            await self._subscription_repository.get_active_by_user(user_id)
        )
        if subscription is None:
            return None, None

        plan = await self._plan_repository.get_by_id(subscription.plan_id)
        if plan is None:
            return None, None

        return SubscriptionResponse(
            id=str(subscription.id),
            plan_id=str(plan.id),
            plan_name=plan.name,
            tier=plan.tier.value,
            status=subscription.status.value,
            interval=subscription.interval.value,
            current_period_start=subscription.current_period_start.isoformat(),
            current_period_end=subscription.current_period_end.isoformat(),
            cancel_at_period_end=subscription.cancel_at_period_end,
        ), PlanResponse(
            id=str(plan.id),
            name=plan.name,
            tier=plan.tier.value,
            price_monthly_cents=plan.price_monthly_cents,
            price_yearly_cents=plan.price_yearly_cents,
            currency=plan.currency,
            features=plan.features,
            limits=plan.limits,
        )
