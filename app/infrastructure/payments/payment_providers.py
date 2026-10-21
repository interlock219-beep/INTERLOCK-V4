"""Payment provider implementations."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from uuid import UUID

from app.application.dto.billing import (
    CheckoutSessionResponse,
    CreateCheckoutRequest,
    PortalSessionResponse,
)
from app.application.interfaces.payment_provider import PaymentProvider
from app.domain.entities.billing_entities import BillingInterval, Plan


class MockPaymentProvider(PaymentProvider):
    def __init__(
        self,
        publishable_key: str | None = None,
        webhook_secret: str | None = None,
    ) -> None:
        self._publishable_key = publishable_key or "pk_test_mock"
        self._webhook_secret = webhook_secret or "whsec_mock"
        self._sessions: dict[str, dict[str, Any]] = {}

    def get_publishable_key(self) -> str | None:
        return self._publishable_key

    async def create_checkout_session(
        self,
        request: CreateCheckoutRequest,
        user_id: UUID,
        tenant_id: str | None,
        plan: Plan,
    ) -> CheckoutSessionResponse:
        session_id = f"cs_mock_{int(time.time())}_{user_id.hex[:8]}"
        unit_amount = (
            plan.price_yearly_cents
            if request.interval == "yearly"
            else plan.price_monthly_cents
        )
        self._sessions[session_id] = {
            "id": session_id,
            "user_id": str(user_id),
            "plan_id": request.plan_id,
            "interval": request.interval,
            "status": "open",
            "success_url": request.success_url,
            "cancel_url": request.cancel_url,
            # Priced from the server-side plan record, mirroring what the
            # Stripe adapter does with price_data.
            "unit_amount_cents": unit_amount,
            "currency": plan.currency,
        }
        return CheckoutSessionResponse(
            session_id=session_id,
            url=f"/mock-checkout/{session_id}?plan={request.plan_id}&interval={request.interval}",
            expires_at=str(int(time.time()) + 3600),
        )

    async def create_portal_session(
        self,
        user_id: UUID,
        tenant_id: str | None,
        customer_id: str | None = None,
    ) -> PortalSessionResponse:
        return PortalSessionResponse(
            url=f"/mock-portal/{user_id.hex[:8]}",
            expires_at=str(int(time.time()) + 3600),
        )

    async def construct_webhook_event(self, payload: bytes, signature: str, secret: str) -> Any:
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        actual = signature
        for part in signature.split(","):
            part = part.strip()
            if part.startswith("v1="):
                actual = part[3:]
                break
        if not hmac.compare_digest(expected, actual):
            raise ValueError("Invalid webhook signature")
        return json.loads(payload)

    def mark_session_complete(self, session_id: str) -> None:
        if session_id in self._sessions:
            self._sessions[session_id]["status"] = "complete"

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        return self._sessions.get(session_id)


class StripePaymentProvider(PaymentProvider):
    def __init__(
        self,
        secret_key: str,
        webhook_secret: str,
        publishable_key: str | None = None,
    ) -> None:
        try:
            import stripe  # type: ignore[import-not-found]  # optional dependency, ImportError-raised above
        except ImportError as exc:
            raise ImportError(
                "stripe package is required for StripePaymentProvider. "
                "Install with: pip install stripe"
            ) from exc
        self._secret_key = secret_key
        self._webhook_secret = webhook_secret
        self._publishable_key = publishable_key
        import stripe

        stripe.api_key = secret_key
        self._stripe = stripe

    def get_publishable_key(self) -> str | None:
        return self._publishable_key

    async def create_checkout_session(
        self,
        request: CreateCheckoutRequest,
        user_id: UUID,
        tenant_id: str | None,
        plan: Plan,
    ) -> CheckoutSessionResponse:
        import stripe

        # Price comes from the server-side plan record only. Inline price_data
        # means no pre-created Stripe Price id is required and a client can
        # never influence the charged amount or currency.
        interval = "year" if request.interval == BillingInterval.YEARLY.value else "month"
        unit_amount = (
            plan.price_yearly_cents
            if request.interval == BillingInterval.YEARLY.value
            else plan.price_monthly_cents
        )
        subscription_metadata = {
            "user_id": str(user_id),
            "tenant_id": tenant_id or "",
            "plan_id": str(plan.id),
            "plan_tier": plan.tier.value,
        }
        params: dict[str, Any] = {
            "mode": "subscription",
            "success_url": request.success_url,
            "cancel_url": request.cancel_url,
            "line_items": [
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": plan.currency,
                        "unit_amount": unit_amount,
                        "recurring": {"interval": interval},
                        "product_data": {"name": f"INTERLOCK {plan.name}"},
                    },
                }
            ],
            "metadata": subscription_metadata,
            "subscription_data": {"metadata": subscription_metadata},
        }
        session = stripe.checkout.Session.create(**params)
        url = session.url or ""
        expires_at = (
            str(int(session.expires_at)) if session.expires_at else str(int(time.time()) + 3600)
        )
        return CheckoutSessionResponse(
            session_id=session.id,
            url=url,
            expires_at=expires_at,
        )

    async def create_portal_session(
        self,
        user_id: UUID,
        tenant_id: str | None,
        customer_id: str | None = None,
    ) -> PortalSessionResponse:
        import stripe

        from app.infrastructure.config.settings import get_settings

        stripe_customer_id = customer_id or self._get_customer_id(user_id)
        return_url = get_settings().billing_portal_return_url
        session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=return_url,
        )
        return PortalSessionResponse(
            url=session.url or "",
            expires_at=str(int(time.time()) + 3600),
        )

    async def construct_webhook_event(self, payload: bytes, signature: str, secret: str) -> Any:
        import stripe

        return stripe.Webhook.construct_event(payload, signature, secret)

    def _get_customer_id(self, user_id: UUID) -> str:
        import stripe

        customers = stripe.Customer.list(email=str(user_id), limit=1)
        if customers.data:
            return customers.data[0].id  # type: ignore[no-any-return]
        raise ValueError(f"No Stripe customer found for user {user_id}")
