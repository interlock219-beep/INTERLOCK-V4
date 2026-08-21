from uuid import UUID, uuid4

import pytest

from app.application.dto.billing import CancelSubscriptionResponse
from app.application.use_cases.cancel_subscription import CancelSubscriptionUseCase
from app.domain.entities.billing_entities import (
    BillingInterval,
    Subscription,
    SubscriptionStatus,
)
from app.domain.exceptions.billing_errors import SubscriptionNotFoundError
from app.domain.repositories.billing_repositories import SubscriptionRepository


class FakeSubscriptionRepository(SubscriptionRepository):
    def __init__(self, subscriptions: list[Subscription]) -> None:
        self._subscriptions = {s.id: s for s in subscriptions}
        self._updated: list[Subscription] = []

    async def get_by_id(
        self, subscription_id: UUID, user_id: UUID | None = None
    ) -> Subscription | None:
        sub = self._subscriptions.get(subscription_id)
        if sub and user_id is not None and sub.user_id != user_id:
            return None
        return sub

    async def get_active_by_user(self, user_id: UUID) -> Subscription | None:
        for sub in self._subscriptions.values():
            if sub.user_id == user_id and sub.status in (
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.TRIALING,
                SubscriptionStatus.PAST_DUE,
            ):
                return sub
        return None

    async def get_by_provider_id(self, provider_subscription_id: str) -> Subscription | None:
        for sub in self._subscriptions.values():
            if sub.provider_subscription_id == provider_subscription_id:
                return sub
        return None

    async def save(self, subscription: Subscription) -> Subscription:
        self._subscriptions[subscription.id] = subscription
        self._updated.append(subscription)
        return subscription

    async def delete(self, subscription_id: UUID, user_id: UUID | None = None) -> None:
        if subscription_id in self._subscriptions:
            del self._subscriptions[subscription_id]


@pytest.fixture
def active_subscription() -> Subscription:
    return Subscription(
        id=uuid4(),
        user_id=uuid4(),
        tenant_id="tenant-1",
        plan_id=uuid4(),
        status=SubscriptionStatus.ACTIVE,
        interval=BillingInterval.MONTHLY,
        current_period_start=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
        current_period_end=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
        cancel_at_period_end=False,
        provider_subscription_id="sub_test_123",
    )


class TestCancelSubscriptionUseCase:
    @pytest.mark.asyncio
    async def test_execute_cancels_active_subscription(
        self, active_subscription: Subscription
    ) -> None:
        repo = FakeSubscriptionRepository([active_subscription])
        use_case = CancelSubscriptionUseCase(repo)
        response = await use_case.execute(active_subscription.user_id)
        assert isinstance(response, CancelSubscriptionResponse)
        assert response.subscription_id == str(active_subscription.id)
        assert response.access_until is not None

    @pytest.mark.asyncio
    async def test_execute_raises_when_no_active_subscription(self) -> None:
        repo = FakeSubscriptionRepository([])
        use_case = CancelSubscriptionUseCase(repo)
        with pytest.raises(SubscriptionNotFoundError, match="No active subscription found"):
            await use_case.execute(uuid4())
