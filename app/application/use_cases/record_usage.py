from uuid import UUID

from app.domain.repositories.billing_repositories import (
    PlanRepository,
    SubscriptionRepository,
    UsageRepository,
)


class RecordUsageUseCase:
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
        self,
        user_id: UUID,
        tenant_id: str | None,
        resource_type: str,
        quantity: int = 1,
    ) -> dict[str, object]:
        subscription = (
            await self._subscription_repository.get_active_by_user(user_id)
        )
        if subscription is None:
            return {"allowed": False, "reason": "no_active_subscription"}

        plan = await self._plan_repository.get_by_id(subscription.plan_id)
        if plan is None:
            return {"allowed": False, "reason": "plan_not_found"}

        limit = plan.limits.get(resource_type)
        if limit is None:
            return {"allowed": True, "reason": "unlimited"}

        period_start = subscription.current_period_start
        period_end = subscription.current_period_end

        current_usage = (
            await self._usage_repository.get_current_period_usage(
                user_id, resource_type, period_start, period_end
            )
        )
        if current_usage + quantity > limit:
            return {
                "allowed": False,
                "reason": "limit_exceeded",
                "current": current_usage,
                "limit": limit,
                "resource_type": resource_type,
            }

        await self._usage_repository.record_usage(
            user_id, tenant_id, resource_type, quantity, period_start, period_end
        )
        return {
            "allowed": True,
            "reason": "recorded",
            "current": current_usage + quantity,
            "limit": limit,
            "resource_type": resource_type,
        }
