import hashlib
import hmac
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.interfaces.payment_provider import PaymentProvider
from app.application.use_cases.handle_webhook import HandleWebhookUseCase
from app.domain.entities.billing_entities import (
    CheckoutSession,
    Plan,
    PlanTier,
    WebhookEvent,
)
from app.domain.repositories.billing_repositories import (
    CheckoutRepository,
    PlanRepository,
    SubscriptionRepository,
    WebhookRepository,
)


class MockPaymentProvider(PaymentProvider):
    def __init__(self, events: dict) -> None:
        self._events = events

    def get_publishable_key(self) -> str | None:
        return "pk_test_mock"

    async def create_checkout_session(self, request, user_id, tenant_id):
        pass

    async def create_portal_session(self, user_id, tenant_id, customer_id=None):
        pass

    async def construct_webhook_event(self, payload, signature, secret):
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        actual = signature
        for part in signature.split(","):
            part = part.strip()
            if part.startswith("v1="):
                actual = part[3:]
                break
        if not hmac.compare_digest(expected, actual):
            raise ValueError("Invalid webhook signature")
        return self._events.get(payload, json.loads(payload))


class FakeWebhookRepository(WebhookRepository):
    def __init__(self, events: list[WebhookEvent]) -> None:
        self._events = {e.id: e for e in events}
        self._saved: list[WebhookEvent] = []

    async def get_by_provider_event_id(self, provider_event_id):
        for event in self._events.values():
            if event.provider_event_id == provider_event_id:
                return event
        return None

    async def save(self, webhook_event):
        self._saved.append(webhook_event)
        self._events[webhook_event.id] = webhook_event
        return webhook_event


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
    def __init__(self, checkouts: list) -> None:
        self._checkouts = {c.id: c for c in checkouts}

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


class FakePlanRepository(PlanRepository):
    def __init__(self, plans: list) -> None:
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


@pytest.fixture
def sample_checkout(sample_plan: Plan) -> CheckoutSession:
    return CheckoutSession(
        id=uuid4(),
        user_id=uuid4(),
        plan_id=sample_plan.id,
        provider_session_id="cs_test_123",
        status="open",
        success_url="http://localhost/success",
        cancel_url="http://localhost/cancel",
        expires_at=datetime.now(tz=UTC),
        tenant_id="tenant-1",
    )


class TestHandleWebhookUseCase:
    @pytest.mark.asyncio
    async def test_execute_handles_subscription_updated(self, sample_plan: Plan) -> None:
        webhook_repo = FakeWebhookRepository([])
        plan_repo = FakePlanRepository([sample_plan])
        checkout_repo = FakeCheckoutRepository([])
        sub_repo = FakeSubscriptionRepository([])
        provider = MockPaymentProvider({})

        payload = json.dumps({
            "id": "evt_sub_updated",
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_test_123",
                    "status": "active",
                    "current_period_start": int(datetime.now(tz=UTC).timestamp()),
                    "current_period_end": int(datetime.now(tz=UTC).timestamp()),
                }
            },
        }).encode()
        secret = "whsec_test"
        signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        use_case = HandleWebhookUseCase(webhook_repo, sub_repo, checkout_repo, plan_repo, provider)
        await use_case.execute(payload, f"v1={signature}", secret)
        assert len(webhook_repo._saved) == 2
        assert webhook_repo._saved[-1].processed is True

    @pytest.mark.asyncio
    async def test_execute_handles_subscription_deleted(self, sample_plan: Plan) -> None:
        webhook_repo = FakeWebhookRepository([])
        plan_repo = FakePlanRepository([sample_plan])
        checkout_repo = FakeCheckoutRepository([])
        sub_repo = FakeSubscriptionRepository([])
        provider = MockPaymentProvider({})

        payload = json.dumps({
            "id": "evt_sub_deleted",
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "id": "sub_test_123",
                }
            },
        }).encode()
        secret = "whsec_test"
        signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        use_case = HandleWebhookUseCase(webhook_repo, sub_repo, checkout_repo, plan_repo, provider)
        await use_case.execute(payload, f"v1={signature}", secret)
        assert len(webhook_repo._saved) == 2
        assert webhook_repo._saved[-1].processed is True

    @pytest.mark.asyncio
    async def test_execute_handles_invoice_paid(self) -> None:
        webhook_repo = FakeWebhookRepository([])
        plan_repo = FakePlanRepository([])
        checkout_repo = FakeCheckoutRepository([])
        sub_repo = FakeSubscriptionRepository([])
        provider = MockPaymentProvider({})

        payload = json.dumps({
            "id": "evt_invoice_paid",
            "type": "invoice.paid",
            "data": {"object": {}},
        }).encode()
        secret = "whsec_test"
        signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        use_case = HandleWebhookUseCase(webhook_repo, sub_repo, checkout_repo, plan_repo, provider)
        await use_case.execute(payload, f"v1={signature}", secret)
        assert len(webhook_repo._saved) == 2
        assert webhook_repo._saved[-1].processed is True

    @pytest.mark.asyncio
    async def test_execute_handles_invoice_payment_failed(self) -> None:
        webhook_repo = FakeWebhookRepository([])
        plan_repo = FakePlanRepository([])
        checkout_repo = FakeCheckoutRepository([])
        sub_repo = FakeSubscriptionRepository([])
        provider = MockPaymentProvider({})

        payload = json.dumps({
            "id": "evt_invoice_failed",
            "type": "invoice.payment_failed",
            "data": {"object": {}},
        }).encode()
        secret = "whsec_test"
        signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        use_case = HandleWebhookUseCase(webhook_repo, sub_repo, checkout_repo, plan_repo, provider)
        await use_case.execute(payload, f"v1={signature}", secret)
        assert len(webhook_repo._saved) == 2
        assert webhook_repo._saved[-1].processed is True
