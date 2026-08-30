from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.application.use_cases.create_checkout_session import CreateCheckoutSessionUseCase
from app.domain.exceptions.billing_errors import PlanNotFoundError, SubscriptionAlreadyExistsError


class StubPlanRepository:
    def __init__(self, plan) -> None:
        self._plan = plan

    async def get_by_id(self, plan_id):
        return self._plan


class StubSubscriptionRepository:
    async def get_active_by_user(self, user_id):
        return None


class StubCheckoutRepository:
    def __init__(self) -> None:
        self.saved = []

    async def save(self, checkout):
        self.saved.append(checkout)


class StubPaymentProvider:
    def __init__(self, session) -> None:
        self._session = session

    async def create_checkout_session(self, request, user_id, tenant_id):
        return self._session


class FakeCheckoutSession:
    def __init__(
        self, session_id="sess-1", url="https://checkout.stripe.com/session"
    ) -> None:
        self.session_id = session_id
        self.url = url
        self.expires_at = "1735689600"


def make_use_case(plan_active=True):
    plan = type("Plan", (), {
        "id": uuid4(),
        "is_active": plan_active,
        "name": "Pro",
    })()
    plan_repo = StubPlanRepository(plan)
    sub_repo = StubSubscriptionRepository()
    checkout_repo = StubCheckoutRepository()
    payment = StubPaymentProvider(FakeCheckoutSession())
    return CreateCheckoutSessionUseCase(plan_repo, sub_repo, checkout_repo, payment), checkout_repo


@pytest.mark.asyncio
async def test_create_checkout_session_success() -> None:
    from unittest.mock import patch

    from app.application.dto.billing import CreateCheckoutRequest

    use_case, checkout_repo = make_use_case(plan_active=True)
    with patch("app.application.use_cases.create_checkout_session.get_settings") as mock_settings:
        mock_settings.return_value.cors_origins = ["http://localhost:3000"]
        request = CreateCheckoutRequest(
            plan_id=str(use_case._plan_repository._plan.id),
            interval="month",
            success_url="http://localhost:3000/success",
            cancel_url="http://localhost:3000/cancel",
        )
        result = await use_case.execute(request, uuid4(), "tenant-1")
    assert result.session_id == "sess-1"
    assert result.url == "https://checkout.stripe.com/session"
    assert len(checkout_repo.saved) == 1


@pytest.mark.asyncio
async def test_create_checkout_session_plan_not_found() -> None:
    from app.application.dto.billing import CreateCheckoutRequest

    use_case, _ = make_use_case(plan_active=False)
    request = CreateCheckoutRequest(
        plan_id=str(uuid4()),
        interval="month",
        success_url="http://localhost:3000/success",
        cancel_url="http://localhost:3000/cancel",
    )
    with pytest.raises(PlanNotFoundError):
        await use_case.execute(request, uuid4(), "tenant-1")


@pytest.mark.asyncio
async def test_create_checkout_session_already_subscribed() -> None:
    from app.application.dto.billing import CreateCheckoutRequest
    from app.domain.entities.billing_entities import (
        BillingInterval,
        Subscription,
        SubscriptionStatus,
    )

    class ActiveSubRepo(StubSubscriptionRepository):
        async def get_active_by_user(self, user_id):
            return Subscription(
                id=uuid4(),
                user_id=user_id,
                tenant_id="tenant-1",
                plan_id=uuid4(),
                status=SubscriptionStatus.ACTIVE,
                interval=BillingInterval.MONTHLY,
                current_period_start=datetime.now(UTC),
                current_period_end=datetime.now(UTC) + timedelta(days=30),
            )

    plan = type("Plan", (), {
        "id": uuid4(),
        "is_active": True,
        "name": "Pro",
    })()
    plan_repo = StubPlanRepository(plan)
    sub_repo = ActiveSubRepo()
    checkout_repo = StubCheckoutRepository()
    payment = StubPaymentProvider(FakeCheckoutSession())
    use_case = CreateCheckoutSessionUseCase(plan_repo, sub_repo, checkout_repo, payment)
    request = CreateCheckoutRequest(
        plan_id=str(plan.id),
        interval="month",
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
    )
    with pytest.raises(SubscriptionAlreadyExistsError):
        await use_case.execute(request, uuid4(), "tenant-1")


@pytest.mark.asyncio
async def test_create_checkout_session_invalid_scheme() -> None:
    from app.application.dto.billing import CreateCheckoutRequest
    use_case, _ = make_use_case(plan_active=True)
    request = CreateCheckoutRequest(
        plan_id=str(use_case._plan_repository._plan.id),
        interval="month",
        success_url="ftp://example.com/success",
        cancel_url="https://example.com/cancel",
    )
    with pytest.raises(ValueError, match="Invalid checkout URL scheme"):
        await use_case.execute(request, uuid4(), "tenant-1")


@pytest.mark.asyncio
async def test_create_checkout_session_invalid_origin() -> None:
    from app.application.dto.billing import CreateCheckoutRequest
    use_case, _ = make_use_case(plan_active=True)
    request = CreateCheckoutRequest(
        plan_id=str(use_case._plan_repository._plan.id),
        interval="month",
        success_url="https://evil.com/success",
        cancel_url="https://example.com/cancel",
    )
    with pytest.raises(ValueError, match="Checkout URL origin not allowed"):
        await use_case.execute(request, uuid4(), "tenant-1")
