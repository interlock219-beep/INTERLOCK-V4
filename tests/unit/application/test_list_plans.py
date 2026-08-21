from uuid import uuid4

import pytest

from app.application.dto.billing import PlanResponse
from app.application.use_cases.list_plans import ListPlansUseCase
from app.domain.entities.billing_entities import Plan, PlanTier
from app.domain.repositories.billing_repositories import PlanRepository


class FakePlanRepository(PlanRepository):
    def __init__(self, plans: list[Plan]) -> None:
        self._plans = plans

    async def get_by_id(self, plan_id):
        for plan in self._plans:
            if plan.id == plan_id:
                return plan
        return None

    async def get_by_tier(self, tier):
        for plan in self._plans:
            if plan.tier.value == tier:
                return plan
        return None

    async def list_active(self):
        return [p for p in self._plans if p.is_active]

    async def save(self, plan):
        self._plans.append(plan)
        return plan


@pytest.fixture
def sample_plans() -> list[Plan]:
    return [
        Plan(
            id=uuid4(),
            name="Free",
            tier=PlanTier.FREE,
            price_monthly_cents=0,
            price_yearly_cents=0,
            currency="usd",
            features={},
            limits={"intents_per_day": 100},
            is_active=True,
        ),
        Plan(
            id=uuid4(),
            name="Pro",
            tier=PlanTier.PRO,
            price_monthly_cents=4900,
            price_yearly_cents=47040,
            currency="usd",
            features={},
            limits={"intents_per_day": 10000},
            is_active=True,
        ),
    ]


class TestListPlansUseCase:
    @pytest.mark.asyncio
    async def test_execute_returns_active_plans(self, sample_plans: list[Plan]) -> None:
        repo = FakePlanRepository(sample_plans)
        use_case = ListPlansUseCase(repo)
        result = await use_case.execute()
        assert len(result) == 2
        assert all(isinstance(p, PlanResponse) for p in result)

    @pytest.mark.asyncio
    async def test_execute_excludes_inactive_plans(self, sample_plans: list[Plan]) -> None:
        inactive_plan = Plan(
            id=sample_plans[0].id,
            name=sample_plans[0].name,
            tier=sample_plans[0].tier,
            price_monthly_cents=sample_plans[0].price_monthly_cents,
            price_yearly_cents=sample_plans[0].price_yearly_cents,
            currency=sample_plans[0].currency,
            features=sample_plans[0].features,
            limits=sample_plans[0].limits,
            is_active=False,
        )
        repo = FakePlanRepository([inactive_plan, sample_plans[1]])
        use_case = ListPlansUseCase(repo)
        result = await use_case.execute()
        assert len(result) == 1
        assert result[0].name == "Pro"
