from uuid import uuid4

import pytest

from app.application.use_cases.record_usage import RecordUsageUseCase
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
        limits={"intents_per_day": 10},
        is_active=True,
    )


class TestRecordUsageUseCase:
    @pytest.mark.asyncio
    async def test_execute_returns_no_active_subscription(self, sample_plan: Plan) -> None:
        plan_repo = FakePlanRepository([sample_plan])
        sub_repo = FakeSubscriptionRepository([])
        usage_repo = FakeUsageRepository()
        use_case = RecordUsageUseCase(usage_repo, sub_repo, plan_repo)
        result = await use_case.execute(uuid4(), "tenant-1", "intents_per_day")
        assert result == {"allowed": False, "reason": "no_active_subscription"}

    @pytest.mark.asyncio
    async def test_execute_returns_plan_not_found(self, sample_plan: Plan) -> None:
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
        use_case = RecordUsageUseCase(usage_repo, sub_repo, plan_repo)
        result = await use_case.execute(user_id, "tenant-1", "intents_per_day")
        assert result == {"allowed": False, "reason": "plan_not_found"}

    @pytest.mark.asyncio
    async def test_execute_returns_unlimited(self, sample_plan: Plan) -> None:
        user_id = uuid4()
        unlimited_plan = Plan(
            id=sample_plan.id,
            name=sample_plan.name,
            tier=sample_plan.tier,
            price_monthly_cents=sample_plan.price_monthly_cents,
            price_yearly_cents=sample_plan.price_yearly_cents,
            currency=sample_plan.currency,
            features=sample_plan.features,
            limits={},
            is_active=sample_plan.is_active,
        )
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
        plan_repo = FakePlanRepository([unlimited_plan])
        sub_repo = FakeSubscriptionRepository([subscription])
        usage_repo = FakeUsageRepository()
        use_case = RecordUsageUseCase(usage_repo, sub_repo, plan_repo)
        result = await use_case.execute(user_id, "tenant-1", "intents_per_day")
        assert result == {"allowed": True, "reason": "unlimited"}

    @pytest.mark.asyncio
    async def test_execute_returns_limit_exceeded(self, sample_plan: Plan) -> None:
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
        plan_repo = FakePlanRepository([sample_plan])
        sub_repo = FakeSubscriptionRepository([subscription])
        usage_repo = FakeUsageRepository()
        use_case = RecordUsageUseCase(usage_repo, sub_repo, plan_repo)
        result = await use_case.execute(user_id, "tenant-1", "intents_per_day", quantity=20)
        assert result["allowed"] is False
        assert result["reason"] == "limit_exceeded"
