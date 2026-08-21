from uuid import uuid4

import pytest

from app.application.use_cases.get_subscription import GetSubscriptionUseCase
from app.application.use_cases.get_usage import GetUsageUseCase
from app.domain.entities.billing_entities import Plan, PlanTier
from app.domain.repositories.billing_repositories import (
    PlanRepository,
    SubscriptionRepository,
    UsageRepository,
)


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


class FakeUsageRepository(UsageRepository):
    def __init__(self) -> None:
        self._records = []

    async def get_current_period_usage(self, user_id, resource_type, period_start, period_end):
        total = 0
        for record in self._records:
            if record.user_id == user_id and record.resource_type == resource_type:
                total += record.quantity
        return total

    async def record_usage(
        self, user_id, tenant_id, resource_type, quantity, period_start, period_end
    ):
        from app.domain.entities.billing_entities import UsageRecord
        record = UsageRecord(
            id=uuid4(),
            user_id=user_id,
            tenant_id=tenant_id,
            resource_type=resource_type,
            quantity=quantity,
            period_start=period_start,
            period_end=period_end,
        )
        self._records.append(record)


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


class TestGetSubscriptionUseCase:
    @pytest.mark.asyncio
    async def test_execute_returns_none_when_plan_not_found(self, sample_plan: Plan) -> None:
        user_id = uuid4()
        subscription = type('Sub', (), {
            'id': uuid4(),
            'user_id': user_id,
            'plan_id': sample_plan.id,
            'status': type('S', (), {'value': 'active'})(),
            'interval': type('I', (), {'value': 'monthly'})(),
            'current_period_start': None,
            'current_period_end': None,
            'cancel_at_period_end': False,
            'provider_subscription_id': None,
        })()
        plan_repo = FakePlanRepository([])
        sub_repo = FakeSubscriptionRepository([subscription])
        use_case = GetSubscriptionUseCase(sub_repo, plan_repo)
        sub_response, plan_response = await use_case.execute(user_id)
        assert sub_response is None
        assert plan_response is None


class TestGetUsageUseCase:
    @pytest.mark.asyncio
    async def test_execute_returns_empty_when_plan_not_found(self, sample_plan: Plan) -> None:
        user_id = uuid4()
        subscription = type('Sub', (), {
            'id': uuid4(),
            'user_id': user_id,
            'plan_id': sample_plan.id,
            'status': type('S', (), {'value': 'active'})(),
            'interval': type('I', (), {'value': 'monthly'})(),
            'current_period_start': None,
            'current_period_end': None,
            'cancel_at_period_end': False,
            'provider_subscription_id': None,
        })()
        plan_repo = FakePlanRepository([])
        sub_repo = FakeSubscriptionRepository([subscription])
        usage_repo = FakeUsageRepository()
        use_case = GetUsageUseCase(usage_repo, sub_repo, plan_repo)
        result = await use_case.execute(user_id, "tenant-1")
        assert result == []
