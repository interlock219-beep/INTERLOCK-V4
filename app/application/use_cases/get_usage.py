from uuid import UUID

from app.application.dto.billing import UsageResponse
from app.domain.repositories.billing_repositories import (
    PlanRepository,
    SubscriptionRepository,
    UsageRepository,
)


class GetUsageUseCase:
    def __init__(
        self,
        usage_repository: UsageRepository,
        subscription_repository: SubscriptionRepository,
        plan_repository: PlanRepository,
    ) -> None:
        self._usage_repository = usage_repository
        self._subscription_repository = subscription_repository
        self._plan_repository = plan_repository

    async def execute(
        self, user_id: UUID, tenant_id: str | None
    ) -> list[UsageResponse]:
        subscription = (
            await self._subscription_repository.get_active_by_user(user_id)
        )
        if subscription is None:
            return []

        plan = await self._plan_repository.get_by_id(subscription.plan_id)
        if plan is None:
            return []

        period_start = subscription.current_period_start
        period_end = subscription.current_period_end

        response = []
        for resource_type, limit in plan.limits.items():
            current = (
                await self._usage_repository.get_current_period_usage(
                    user_id, resource_type, period_start, period_end
                )
            )
            percentage = (current / limit * 100) if limit > 0 else None
            response.append(
                UsageResponse(
                    resource_type=resource_type,
                    current=current,
                    limit=limit if limit > 0 else None,
                    period_start=period_start.isoformat(),
                    period_end=period_end.isoformat(),
                    percentage=percentage,
                )
            )
        return response
