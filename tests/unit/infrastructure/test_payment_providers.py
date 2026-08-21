import hashlib
import hmac
import json
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.domain.entities.billing_entities import PlanTier
from app.infrastructure.payments.payment_providers import (
    MockPaymentProvider,
    StripePaymentProvider,
)
from app.infrastructure.persistence.models import PlanModel


@pytest.fixture
def mock_plan() -> PlanModel:
    return PlanModel(
        id=uuid4(),
        name="Pro",
        tier=PlanTier.PRO,
        price_monthly_cents=4900,
        price_yearly_cents=47040,
        currency="usd",
        features="{}",
        limits='{"intents_per_day": 10000}',
        is_active=True,
        created_at=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
        updated_at=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
    )


def _make_mock_stripe() -> ModuleType:
    stripe = ModuleType("stripe")
    stripe.checkout = MagicMock()
    stripe.checkout.Session = MagicMock()
    stripe.billing_portal = MagicMock()
    stripe.billing_portal.Session = MagicMock()
    stripe.Webhook = MagicMock()
    stripe.Customer = MagicMock()
    return stripe


class TestMockPaymentProvider:
    def test_get_publishable_key(self) -> None:
        provider = MockPaymentProvider(publishable_key="pk_test_mock")
        assert provider.get_publishable_key() == "pk_test_mock"

    def test_get_publishable_key_default(self) -> None:
        provider = MockPaymentProvider()
        assert provider.get_publishable_key() == "pk_test_mock"

    @pytest.mark.asyncio
    async def test_create_checkout_session(self, mock_plan: PlanModel) -> None:
        provider = MockPaymentProvider()
        request = MagicMock(
            plan_id=str(mock_plan.id),
            interval="monthly",
            success_url="http://localhost/success",
            cancel_url="http://localhost/cancel",
        )
        response = await provider.create_checkout_session(
            request=request,
            user_id=uuid4(),
            tenant_id="tenant-1",
        )
        assert response.session_id.startswith("cs_mock_")
        assert response.url is not None
        assert response.expires_at is not None

    @pytest.mark.asyncio
    async def test_create_portal_session(self) -> None:
        provider = MockPaymentProvider()
        response = await provider.create_portal_session(
            user_id=uuid4(),
            tenant_id="tenant-1",
            customer_id="cus_123",
        )
        assert response.url is not None
        assert response.expires_at is not None

    @pytest.mark.asyncio
    async def test_construct_webhook_event_valid_signature(self) -> None:
        provider = MockPaymentProvider(webhook_secret="whsec_test")
        payload = json.dumps({"id": "evt_1", "type": "checkout.session.completed"}).encode()
        signature = hmac.new(b"whsec_test", payload, hashlib.sha256).hexdigest()
        result = await provider.construct_webhook_event(payload, f"v1={signature}", "whsec_test")
        assert result["id"] == "evt_1"

    @pytest.mark.asyncio
    async def test_construct_webhook_event_invalid_signature(self) -> None:
        provider = MockPaymentProvider(webhook_secret="whsec_test")
        payload = b"{}"
        with pytest.raises(ValueError, match="Invalid webhook signature"):
            await provider.construct_webhook_event(payload, "v1=invalid", "whsec_test")

    def test_mark_session_complete(self) -> None:
        provider = MockPaymentProvider()
        provider._sessions["cs_test"] = {"status": "open"}
        provider.mark_session_complete("cs_test")
        assert provider._sessions["cs_test"]["status"] == "complete"

    def test_get_session(self) -> None:
        provider = MockPaymentProvider()
        provider._sessions["cs_test"] = {"status": "open"}
        assert provider.get_session("cs_test") is not None
        assert provider.get_session("cs_missing") is None


class TestStripePaymentProvider:
    @pytest.fixture(autouse=True)
    def _inject_stripe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stripe = _make_mock_stripe()
        monkeypatch.setitem(sys.modules, "stripe", stripe)

    def test_init(self) -> None:
        provider = StripePaymentProvider(
            secret_key="sk_test_123",
            webhook_secret="whsec_test",
            publishable_key="pk_test_123",
        )
        assert provider._secret_key == "sk_test_123"
        assert provider._webhook_secret == "whsec_test"
        assert provider._publishable_key == "pk_test_123"

    @pytest.mark.asyncio
    async def test_get_publishable_key(self) -> None:
        provider = StripePaymentProvider(
            secret_key="sk_test_123",
            webhook_secret="whsec_test",
            publishable_key="pk_test_123",
        )
        assert provider.get_publishable_key() == "pk_test_123"

    @pytest.mark.asyncio
    async def test_create_checkout_session(self) -> None:
        mock_session = MagicMock()
        mock_session.id = "cs_test_123"
        mock_session.url = "https://checkout.stripe.com/cs_test"
        mock_session.expires_at = 1234567890
        sys.modules["stripe"].checkout.Session.create.return_value = mock_session

        provider = StripePaymentProvider(
            secret_key="sk_test_123",
            webhook_secret="whsec_test",
            publishable_key="pk_test_123",
        )
        request = MagicMock(
            plan_id=str(uuid4()),
            interval="monthly",
            success_url="http://localhost/success",
            cancel_url="http://localhost/cancel",
        )
        response = await provider.create_checkout_session(request, uuid4(), "tenant-1")
        assert response.session_id == "cs_test_123"
        assert response.url == "https://checkout.stripe.com/cs_test"

    @pytest.mark.asyncio
    async def test_create_checkout_session_yearly(self) -> None:
        mock_session = MagicMock()
        mock_session.id = "cs_test_yearly"
        mock_session.url = "https://checkout.stripe.com/cs_test_yearly"
        mock_session.expires_at = 1234567890
        sys.modules["stripe"].checkout.Session.create.return_value = mock_session

        provider = StripePaymentProvider(
            secret_key="sk_test_123",
            webhook_secret="whsec_test",
            publishable_key="pk_test_123",
        )
        request = MagicMock(
            plan_id=str(uuid4()),
            interval="yearly",
            success_url="http://localhost/success",
            cancel_url="http://localhost/cancel",
        )
        response = await provider.create_checkout_session(request, uuid4(), "tenant-1")
        assert response.session_id == "cs_test_yearly"

    @pytest.mark.asyncio
    async def test_create_portal_session_with_customer_id(self) -> None:
        mock_session = MagicMock()
        mock_session.url = "https://portal.stripe.com"
        sys.modules["stripe"].billing_portal.Session.create.return_value = mock_session

        provider = StripePaymentProvider(
            secret_key="sk_test_123",
            webhook_secret="whsec_test",
            publishable_key="pk_test_123",
        )
        response = await provider.create_portal_session(uuid4(), "tenant-1", customer_id="cus_123")
        assert response.url == "https://portal.stripe.com"

    @pytest.mark.asyncio
    async def test_create_portal_session_without_customer_id(self) -> None:
        mock_session = MagicMock()
        mock_session.url = "https://portal.stripe.com"
        sys.modules["stripe"].billing_portal.Session.create.return_value = mock_session

        provider = StripePaymentProvider(
            secret_key="sk_test_123",
            webhook_secret="whsec_test",
            publishable_key="pk_test_123",
        )
        with patch.object(provider, "_get_customer_id", return_value="cus_456"):
            response = await provider.create_portal_session(uuid4(), "tenant-1")
        assert response.url == "https://portal.stripe.com"

    @pytest.mark.asyncio
    async def test_construct_webhook_event(self) -> None:
        mock_event = {"id": "evt_1", "type": "checkout.session.completed"}
        sys.modules["stripe"].Webhook.construct_event.return_value = mock_event

        provider = StripePaymentProvider(
            secret_key="sk_test_123",
            webhook_secret="whsec_test",
            publishable_key="pk_test_123",
        )
        payload = b'{"id": "evt_1"}'
        result = await provider.construct_webhook_event(payload, "sig=123", "whsec_test")
        assert result["id"] == "evt_1"

    def test_get_customer_id_found(self) -> None:
        mock_customer = MagicMock()
        mock_customer.id = "cus_123"
        sys.modules["stripe"].Customer.list.return_value = MagicMock(data=[mock_customer])

        provider = StripePaymentProvider(
            secret_key="sk_test_123",
            webhook_secret="whsec_test",
            publishable_key="pk_test_123",
        )
        customer_id = provider._get_customer_id(uuid4())
        assert customer_id == "cus_123"

    def test_get_customer_id_not_found(self) -> None:
        sys.modules["stripe"].Customer.list.return_value = MagicMock(data=[])

        provider = StripePaymentProvider(
            secret_key="sk_test_123",
            webhook_secret="whsec_test",
            publishable_key="pk_test_123",
        )
        with pytest.raises(ValueError, match="No Stripe customer found"):
            provider._get_customer_id(uuid4())

    def test_stripe_provider_requires_package(self) -> None:
        import sys

        stripe_module = sys.modules.pop("stripe", None)
        try:
            with pytest.raises(ImportError, match="stripe package is required"):
                StripePaymentProvider(
                    secret_key="sk_test_123",
                    webhook_secret="whsec_test",
                    publishable_key="pk_test_123",
                )
        finally:
            if stripe_module is not None:
                sys.modules["stripe"] = stripe_module
