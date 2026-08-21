from uuid import uuid4

import pytest

from app.application.dto.billing import CreateCheckoutRequest
from app.application.use_cases.create_checkout_session import CreateCheckoutSessionUseCase
from app.domain.entities.billing_entities import Plan, PlanTier
from app.domain.exceptions.billing_errors import PlanNotFoundError, SubscriptionAlreadyExistsError
from app.domain.repositories.billing_repositories import (
    CheckoutRepository,
    PlanRepository,
    SubscriptionRepository,
)


class FakePlanRepository(PlanRepository):
    def __init__(self, plans: list[Plan]) -> None:
        self._plans = {p.id: p for p in plans}

    async def get_by_id(self, plan_id):
        return self._plans.get(plan_id)

    async def get_by_tier(self, tier):
        for plan in self._plans.values():
            if plan.tier.value == tier:
                return plan
        return None

    async def list_active(self):
        return [p for p in self._plans.values() if p.is_active]

    async def save(self, plan):
        self._plans[plan.id] = plan
        return plan


class FakeSubscriptionRepository(SubscriptionRepository):
    def __init__(self, subscriptions: list) -> None:
        self._subscriptions = {s.id: s for s in subscriptions}

    async def get_by_id(self, subscription_id, user_id=None):
        return self._subscriptions.get(subscription_id)

    async def get_active_by_user(self, user_id):
        for sub in self._subscriptions.values():
            if sub.user_id == user_id and sub.status.value in ("active", "trialing", "past_due"):
                return sub
        return None

    async def get_by_provider_id(self, provider_subscription_id):
        for sub in self._subscriptions.values():
            if sub.provider_subscription_id == provider_subscription_id:
                return sub
        return None

    async def save(self, subscription):
        self._subscriptions[subscription.id] = subscription
        return subscription

    async def delete(self, subscription_id, user_id=None):
        if subscription_id in self._subscriptions:
            del self._subscriptions[subscription_id]


class FakeCheckoutRepository(CheckoutRepository):
    def __init__(self) -> None:
        self._checkouts = {}

    async def get_by_id(self, checkout_id, user_id=None):
        return self._checkouts.get(checkout_id)

    async def get_by_provider_session_id(self, provider_session_id):
        for checkout in self._checkouts.values():
            if checkout.provider_session_id == provider_session_id:
                return checkout
        return None

    async def get_by_user_id(self, user_id):
        for checkout in self._checkouts.values():
            if checkout.user_id == user_id:
                return checkout
        return None

    async def save(self, checkout):
        self._checkouts[checkout.id] = checkout
        return checkout

    async def update_customer_id(self, checkout_id, customer_id, user_id=None):
        checkout = self._checkouts.get(checkout_id)
        if checkout:
            checkout.customer_id = customer_id
            return checkout
        return None

    async def delete(self, checkout_id, user_id=None):
        if checkout_id in self._checkouts:
            del self._checkouts[checkout_id]


class FakePaymentProvider:
    async def create_checkout_session(self, request, user_id, tenant_id):
        from app.application.dto.billing import CheckoutSessionResponse
        return CheckoutSessionResponse(
            session_id="cs_test",
            url="http://test.com",
            expires_at="1234567890",
        )


@pytest.fixture
def sample_plan() -> Plan:
    return Plan(
        id=uuid4(),
        name="Pro",
        tier=PlanTier.PRO,
        price_monthly_cents=4900,
        price_yearly_cents=47040,
        currency="usd",
        features={},
        limits={"intents_per_day": 10000},
        is_active=True,
    )


class TestCreateCheckoutSessionUseCase:
    @pytest.mark.asyncio
    async def test_execute_raises_for_invalid_plan(self, sample_plan: Plan) -> None:
        plan_repo = FakePlanRepository([sample_plan])
        sub_repo = FakeSubscriptionRepository([])
        checkout_repo = FakeCheckoutRepository()
        provider = FakePaymentProvider()
        use_case = CreateCheckoutSessionUseCase(plan_repo, sub_repo, checkout_repo, provider)

        request = CreateCheckoutRequest(
            plan_id=str(uuid4()),
            interval="monthly",
            success_url="ftp://invalid.com",
            cancel_url="http://localhost/cancel",
        )
        with pytest.raises(PlanNotFoundError):
            await use_case.execute(request, uuid4(), "tenant-1")

    @pytest.mark.asyncio
    async def test_execute_raises_when_already_subscribed(self, sample_plan: Plan) -> None:
        user_id = uuid4()
        subscription = type('Sub', (), {
            'id': uuid4(), 'user_id': user_id, 'plan_id': sample_plan.id,
            'status': type('S', (), {'value': 'active'})()
        })()
        plan_repo = FakePlanRepository([sample_plan])
        sub_repo = FakeSubscriptionRepository([subscription])
        checkout_repo = FakeCheckoutRepository()
        provider = FakePaymentProvider()
        use_case = CreateCheckoutSessionUseCase(plan_repo, sub_repo, checkout_repo, provider)

        request = CreateCheckoutRequest(
            plan_id=str(sample_plan.id),
            interval="monthly",
            success_url="http://localhost/success",
            cancel_url="http://localhost/cancel",
        )
        with pytest.raises(SubscriptionAlreadyExistsError):
            await use_case.execute(request, user_id, "tenant-1")
