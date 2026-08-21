import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.application.interfaces.payment_provider import PaymentProvider
from app.domain.entities.billing_entities import (
    BillingInterval,
    Subscription,
    SubscriptionStatus,
    WebhookEvent,
)
from app.domain.exceptions.billing_errors import WebhookProcessingError
from app.domain.repositories.billing_repositories import (
    CheckoutRepository,
    PlanRepository,
    SubscriptionRepository,
    WebhookRepository,
)

logger = logging.getLogger(__name__)


def _get_str(value: object, default: str = "") -> str:
    if isinstance(value, str):
        return value
    return default


def _get_int(value: object, default: int = 0) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return default


def _get_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


class HandleWebhookUseCase:
    def __init__(
        self,
        webhook_repository: WebhookRepository,
        subscription_repository: SubscriptionRepository,
        checkout_repository: CheckoutRepository,
        plan_repository: PlanRepository,
        payment_provider: PaymentProvider,
    ) -> None:
        self._webhook_repository = webhook_repository
        self._subscription_repository = subscription_repository
        self._checkout_repository = checkout_repository
        self._plan_repository = plan_repository
        self._payment_provider = payment_provider

    async def execute(
        self, payload: bytes, signature: str, webhook_secret: str
    ) -> None:
        provider_event = await self._payment_provider.construct_webhook_event(
            payload, signature, webhook_secret
        )

        if isinstance(provider_event, dict):
            event_id = _get_str(provider_event.get("id", ""))
            event_type = _get_str(provider_event.get("type", ""))
        else:
            event_id = _get_str(getattr(provider_event, "id", ""))
            event_type = _get_str(getattr(provider_event, "type", ""))
        if not event_id or not event_type:
            raise WebhookProcessingError(
                "Webhook event missing id or type."
            )

        existing = await self._webhook_repository.get_by_provider_event_id(
            event_id
        )
        if existing is not None:
            if existing.processed:
                logger.info(
                    "Webhook %s already processed; idempotent skip.",
                    event_id,
                )
                return
            if existing.error_message:
                raise WebhookProcessingError(
                    f"Previous webhook processing failed: "
                    f"{existing.error_message}"
                )

        event_payload = (
            _get_dict(provider_event)
            if hasattr(provider_event, "__dict__")
            else _get_dict(provider_event)
        )
        webhook_event = WebhookEvent(
            id=existing.id if existing else uuid4(),
            provider_event_id=event_id,
            event_type=event_type,
            payload=event_payload,
            processed=False,
            created_at=datetime.now(tz=UTC),
        )
        await self._webhook_repository.save(webhook_event)

        try:
            await self._process_event(provider_event)
            webhook_event = WebhookEvent(
                id=webhook_event.id,
                provider_event_id=webhook_event.provider_event_id,
                event_type=webhook_event.event_type,
                payload=webhook_event.payload,
                processed=True,
                processed_at=datetime.now(tz=UTC),
                error_message=None,
                created_at=webhook_event.created_at,
            )
            await self._webhook_repository.save(webhook_event)
        except Exception as exc:
            logger.exception("Failed to process webhook %s", event_id)
            webhook_event = WebhookEvent(
                id=webhook_event.id,
                provider_event_id=webhook_event.provider_event_id,
                event_type=webhook_event.event_type,
                payload=webhook_event.payload,
                processed=False,
                processed_at=None,
                error_message=str(exc),
                created_at=webhook_event.created_at,
            )
            await self._webhook_repository.save(webhook_event)
            raise WebhookProcessingError(
                f"Webhook processing failed: {exc}"
            ) from exc

    async def _process_event(self, provider_event: object) -> None:
        event_type = ""
        if isinstance(provider_event, dict):
            event_type = _get_str(provider_event.get("type", ""))
            event_data = provider_event.get("data", {})
            event_object = _get_dict(event_data).get("object", {})
        else:
            event_type = _get_str(getattr(provider_event, "type", ""))
            event_data = getattr(provider_event, "data", {})
            event_object = (
                _get_dict(event_data).get("object", {})
                if isinstance(event_data, dict)
                else {}
            )

        if event_type in (
            "checkout.session.completed",
            "checkout.session.async_payment_succeeded",
        ):
            await self._handle_checkout_complete(event_object)
        elif event_type == "customer.subscription.updated":
            await self._handle_subscription_updated(event_object)
        elif event_type == "customer.subscription.deleted":
            await self._handle_subscription_deleted(event_object)
        elif event_type == "invoice.paid":
            await self._handle_invoice_paid(event_object)
        elif event_type == "invoice.payment_failed":
            await self._handle_invoice_payment_failed(event_object)
        else:
            logger.info("Unhandled webhook event type: %s", event_type)

    async def _handle_checkout_complete(
        self, event_object: dict[str, Any]
    ) -> None:
        provider_session_id = _get_str(event_object.get("id", ""))
        subscription_id = _get_str(event_object.get("subscription", ""))
        customer_id = _get_str(event_object.get("customer", ""))

        checkout = (
            await self._checkout_repository.get_by_provider_session_id(
                provider_session_id
            )
        )
        if checkout is None:
            return

        metadata = _get_dict(event_object.get("metadata", {}))
        metadata_plan_id = _get_str(metadata.get("plan_id", ""))
        plan_id = checkout.plan_id
        if metadata_plan_id and metadata_plan_id != str(plan_id):
            raise WebhookProcessingError(
                f"Plan ID mismatch: metadata={metadata_plan_id}, checkout={plan_id}"
            )
        plan = await self._plan_repository.get_by_id(plan_id)
        if plan is None:
            raise WebhookProcessingError(
                f"Plan not found for checkout: {plan_id}"
            )

        if customer_id and checkout.customer_id != customer_id:
            await self._checkout_repository.update_customer_id(
                checkout.id, customer_id, checkout.user_id
            )

        now = datetime.now(tz=UTC)
        subscription = Subscription(
            id=UUID(int=0),
            user_id=checkout.user_id,
            tenant_id=checkout.tenant_id,
            plan_id=plan_id,
            status=SubscriptionStatus.ACTIVE,
            interval=BillingInterval.MONTHLY,
            current_period_start=now,
            current_period_end=now,
            provider_subscription_id=subscription_id or None,
            created_at=now,
            updated_at=now,
        )
        await self._subscription_repository.save(subscription)

    async def _handle_subscription_updated(
        self, event_object: dict[str, Any]
    ) -> None:
        provider_subscription_id = _get_str(event_object.get("id", ""))
        subscription = (
            await self._subscription_repository.get_by_provider_id(
                provider_subscription_id
            )
        )
        if subscription is None:
            return

        status_map = {
            "active": SubscriptionStatus.ACTIVE,
            "past_due": SubscriptionStatus.PAST_DUE,
            "canceled": SubscriptionStatus.CANCELED,
            "incomplete": SubscriptionStatus.INCOMPLETE,
            "incomplete_expired": SubscriptionStatus.INCOMPLETE_EXPIRED,
            "trialing": SubscriptionStatus.TRIALING,
            "unpaid": SubscriptionStatus.UNPAID,
        }
        raw_status = _get_str(event_object.get("status", "")).lower()
        new_status = status_map.get(
            raw_status, SubscriptionStatus(raw_status)
        )

        current_period_start = datetime.fromtimestamp(
            _get_int(event_object.get("current_period_start", 0)), tz=UTC
        )
        current_period_end = datetime.fromtimestamp(
            _get_int(event_object.get("current_period_end", 0)), tz=UTC
        )

        updated_subscription = Subscription(
            id=subscription.id,
            user_id=subscription.user_id,
            tenant_id=subscription.tenant_id,
            plan_id=subscription.plan_id,
            status=new_status,
            interval=subscription.interval,
            current_period_start=current_period_start,
            current_period_end=current_period_end,
            cancel_at_period_end=bool(
                event_object.get("cancel_at_period_end", False)
            ),
            provider_subscription_id=subscription.provider_subscription_id,
            created_at=subscription.created_at,
            updated_at=datetime.now(tz=UTC),
        )
        await self._subscription_repository.save(updated_subscription)

    async def _handle_subscription_deleted(
        self, event_object: dict[str, Any]
    ) -> None:
        provider_subscription_id = _get_str(event_object.get("id", ""))
        subscription = (
            await self._subscription_repository.get_by_provider_id(
                provider_subscription_id
            )
        )
        if subscription is None:
            return

        updated_subscription = Subscription(
            id=subscription.id,
            user_id=subscription.user_id,
            tenant_id=subscription.tenant_id,
            plan_id=subscription.plan_id,
            status=SubscriptionStatus.CANCELED,
            interval=subscription.interval,
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            cancel_at_period_end=True,
            provider_subscription_id=subscription.provider_subscription_id,
            created_at=subscription.created_at,
            updated_at=datetime.now(tz=UTC),
        )
        await self._subscription_repository.save(updated_subscription)

    async def _handle_invoice_paid(
        self, event_object: dict[str, Any]
    ) -> None:
        pass

    async def _handle_invoice_payment_failed(
        self, event_object: dict[str, Any]
    ) -> None:
        pass
