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
    ) -> CheckoutSessionResponse:
        session_id = f"cs_mock_{int(time.time())}_{user_id.hex[:8]}"
        self._sessions[session_id] = {
            "id": session_id,
            "user_id": str(user_id),
            "plan_id": request.plan_id,
            "interval": request.interval,
            "status": "open",
            "success_url": request.success_url,
            "cancel_url": request.cancel_url,
        }
        return CheckoutSessionResponse(
            session_id=session_id,
            url=f"/mock-checkout/{session_id}?plan={request.plan_id}"
            f"&interval={request.interval}",
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

    async def construct_webhook_event(
        self, payload: bytes, signature: str, secret: str
    ) -> Any:
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
            import stripe  # type: ignore
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
    ) -> CheckoutSessionResponse:
        import stripe

        params: dict[str, Any] = {
            "mode": "subscription",
            "success_url": request.success_url,
            "cancel_url": request.cancel_url,
            "line_items": [
                {
                    "price": request.plan_id,
                    "quantity": 1,
                }
            ],
            "metadata": {
                "user_id": str(user_id),
                "tenant_id": tenant_id or "",
            },
        }
        if request.interval == "yearly":
            params["subscription_data"] = {
                "metadata": {
                    "user_id": str(user_id),
                    "tenant_id": tenant_id or "",
                }
            }
        session = stripe.checkout.Session.create(**params)
        url = session.url or ""
        expires_at = (
            str(int(session.expires_at))
            if session.expires_at
            else str(int(time.time()) + 3600)
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

        stripe_customer_id = customer_id or self._get_customer_id(user_id)
        session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url="https://intentlock.io/dashboard/billing",
        )
        return PortalSessionResponse(
            url=session.url or "",
            expires_at=str(int(time.time()) + 3600),
        )

    async def construct_webhook_event(
        self, payload: bytes, signature: str, secret: str
    ) -> Any:
        import stripe

        return stripe.Webhook.construct_event(payload, signature, secret)

    def _get_customer_id(self, user_id: UUID) -> str:
        import stripe

        customers = stripe.Customer.list(email=str(user_id), limit=1)
        if customers.data:
            return customers.data[0].id  # type: ignore[no-any-return]
        raise ValueError(f"No Stripe customer found for user {user_id}")
