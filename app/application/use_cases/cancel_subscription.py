from datetime import UTC, datetime
from uuid import UUID

from app.application.dto.billing import CancelSubscriptionResponse
from app.domain.entities.billing_entities import Subscription
from app.domain.exceptions.billing_errors import SubscriptionNotFoundError
from app.domain.repositories.billing_repositories import SubscriptionRepository


class CancelSubscriptionUseCase:
    def __init__(self, subscription_repository: SubscriptionRepository) -> None:
        self._subscription_repository = subscription_repository

    async def execute(self, user_id: UUID) -> CancelSubscriptionResponse:
        subscription = await self._subscription_repository.get_active_by_user(user_id)
        if subscription is None:
            raise SubscriptionNotFoundError("No active subscription found.")

        updated = Subscription(
            id=subscription.id,
            user_id=subscription.user_id,
            tenant_id=subscription.tenant_id,
            plan_id=subscription.plan_id,
            status=subscription.status,
            interval=subscription.interval,
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            cancel_at_period_end=True,
            provider_subscription_id=subscription.provider_subscription_id,
            created_at=subscription.created_at,
            updated_at=datetime.now(tz=UTC),
        )
        saved = await self._subscription_repository.save(updated)
        return CancelSubscriptionResponse(
            subscription_id=str(saved.id),
            canceled_at=datetime.now(tz=UTC).isoformat(),
            access_until=saved.current_period_end.isoformat(),
        )
