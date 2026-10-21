import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from app.application.interfaces.payment_provider import PaymentProvider
from app.domain.entities.billing_entities import (
    BillingInterval,
    Invoice,
    Subscription,
    SubscriptionStatus,
    WebhookEvent,
)
from app.domain.exceptions.billing_errors import WebhookProcessingError
from app.domain.repositories.billing_repositories import (
    CheckoutRepository,
    InvoiceRepository,
    PlanRepository,
    SubscriptionRepository,
    WebhookRepository,
)
from app.domain.services.recovery_credit_service import RecoveryCreditService

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


def _extract_invoice_period(
    event_object: dict[str, Any], subscription: Subscription, now: datetime
) -> tuple[datetime, datetime]:
    """Billing period for an invoice event (provider-trusted data only).

    Preference order: invoice line period (Stripe always sends it), then the
    subscription's current period, then a derived month/year from the
    subscription interval as a last resort for degenerate payloads.
    """
    lines = _get_dict(event_object.get("lines"))
    data = lines.get("data")
    if isinstance(data, list):
        for line in data:
            if not isinstance(line, dict):
                continue
            period = _get_dict(line.get("period"))
            start = _get_int(period.get("start", 0))
            end = _get_int(period.get("end", 0))
            if start and end and end > start:
                return (
                    datetime.fromtimestamp(start, tz=UTC),
                    datetime.fromtimestamp(end, tz=UTC),
                )
    if subscription.current_period_end > subscription.current_period_start:
        return subscription.current_period_start, subscription.current_period_end
    days = 365 if subscription.interval is BillingInterval.YEARLY else 30
    return now, now + timedelta(days=days)


class HandleWebhookUseCase:
    def __init__(
        self,
        webhook_repository: WebhookRepository,
        subscription_repository: SubscriptionRepository,
        checkout_repository: CheckoutRepository,
        plan_repository: PlanRepository,
        payment_provider: PaymentProvider,
        *,
        credit_service: RecoveryCreditService | None = None,
        invoice_repository: InvoiceRepository | None = None,
    ) -> None:
        self._webhook_repository = webhook_repository
        self._subscription_repository = subscription_repository
        self._checkout_repository = checkout_repository
        self._plan_repository = plan_repository
        self._payment_provider = payment_provider
        # Credit allocation happens only on verified provider events
        # (invoice.paid), never on a frontend redirect. Both dependencies are
        # optional so constructions without billing persistence keep working;
        # the billing route always passes them.
        self._credit_service = credit_service
        self._invoice_repository = invoice_repository

    async def execute(self, payload: bytes, signature: str, webhook_secret: str) -> None:
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
            raise WebhookProcessingError("Webhook event missing id or type.")

        existing = await self._webhook_repository.get_by_provider_event_id(event_id)
        if existing is not None:
            if existing.processed:
                logger.info(
                    "Webhook %s already processed; idempotent skip.",
                    event_id,
                )
                return
            if existing.error_message:
                raise WebhookProcessingError(
                    f"Previous webhook processing failed: {existing.error_message}"
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
            raise WebhookProcessingError(f"Webhook processing failed: {exc}") from exc

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
                _get_dict(event_data).get("object", {}) if isinstance(event_data, dict) else {}
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

    async def _handle_checkout_complete(self, event_object: dict[str, Any]) -> None:
        provider_session_id = _get_str(event_object.get("id", ""))
        subscription_id = _get_str(event_object.get("subscription", ""))
        customer_id = _get_str(event_object.get("customer", ""))

        checkout = await self._checkout_repository.get_by_provider_session_id(provider_session_id)
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
            raise WebhookProcessingError(f"Plan not found for checkout: {plan_id}")

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

    async def _handle_subscription_updated(self, event_object: dict[str, Any]) -> None:
        provider_subscription_id = _get_str(event_object.get("id", ""))
        subscription = await self._subscription_repository.get_by_provider_id(
            provider_subscription_id
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
        new_status = status_map.get(raw_status, SubscriptionStatus(raw_status))

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
            cancel_at_period_end=bool(event_object.get("cancel_at_period_end", False)),
            provider_subscription_id=subscription.provider_subscription_id,
            created_at=subscription.created_at,
            updated_at=datetime.now(tz=UTC),
        )
        await self._subscription_repository.save(updated_subscription)
        await self._handle_plan_change(updated_subscription, event_object)

    async def _handle_plan_change(
        self, subscription: Subscription, event_object: dict[str, Any]
    ) -> None:
        """Apply mid-period plan changes to the credit wallet.

        Upgrade (higher credit allowance): the difference is granted
        immediately, recorded as an ADJUSTMENT ledger entry. Downgrade: the
        current allowance stands until the period ends, then the new plan's
        allowance applies at the next renewal (documented policy -- nothing
        paid for is clawed back mid-period).
        """
        if self._credit_service is None:
            return
        tenant_id = subscription.tenant_id or ""
        if not tenant_id:
            return
        metadata = _get_dict(event_object.get("metadata", {}))
        new_tier = _get_str(metadata.get("plan_tier", ""))
        if not new_tier:
            return
        plan = await self._plan_repository.get_by_tier(new_tier)
        if plan is None:
            return
        credits = _get_int(plan.limits.get("recovery_credits", 0))
        summary = await self._credit_service.summary(tenant_id)
        if not summary.has_wallet:
            # E.g. trialing before the first paid invoice: just link the
            # wallet to the subscription. No credits are granted here --
            # grants happen only in _handle_invoice_paid (verified payment).
            await self._credit_service.attach_subscription(
                tenant_id,
                subscription_id=subscription.id,
                provider_subscription_id=subscription.provider_subscription_id,
                plan_tier=plan.tier.value,
                plan_name=plan.name,
            )
            return
        if plan.tier.value == summary.plan_tier:
            return
        marker = subscription.provider_subscription_id or str(subscription.id)
        if credits > summary.allocated:
            granted = await self._credit_service.apply_plan_upgrade(
                tenant_id,
                new_monthly_credits=credits,
                subscription_id=subscription.id,
                idempotency_key=(
                    f"adjust:{marker}:{plan.tier.value}:"
                    f"{int(subscription.current_period_start.timestamp())}"
                ),
                reason=f"plan upgraded to {plan.name} (allowance difference granted)",
            )
            if granted:
                logger.info(
                    "Plan upgrade granted %d extra credits to tenant %s",
                    granted,
                    tenant_id,
                )
        else:
            logger.info(
                "Plan change to %s for tenant %s deferred to next renewal (downgrade policy)",
                plan.tier.value,
                tenant_id,
            )

    async def _handle_subscription_deleted(self, event_object: dict[str, Any]) -> None:
        provider_subscription_id = _get_str(event_object.get("id", ""))
        subscription = await self._subscription_repository.get_by_provider_id(
            provider_subscription_id
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

        # Cancellation: expire the remaining allowance (no rollover) and stop
        # enforcement. The tenant falls back to the free evaluation tier.
        if self._credit_service is not None and subscription.tenant_id:
            expired = await self._credit_service.deactivate(
                subscription.tenant_id, reason="subscription canceled"
            )
            logger.info(
                "Credit enforcement deactivated for tenant %s (%d credits expired)",
                subscription.tenant_id,
                expired,
            )

    async def _handle_invoice_paid(self, event_object: dict[str, Any]) -> None:
        """Verified payment: record the invoice and allocate the allowance.

        This is the ONLY path that grants paid credits. The allocation's
        idempotency key (provider subscription + period start) makes repeated
        deliveries of the same invoice -- or renewals replayed with different
        event ids -- grant the allowance exactly once per billing period.
        """
        provider_subscription_id = _get_str(event_object.get("subscription", ""))
        if not provider_subscription_id:
            logger.info("invoice.paid without subscription reference; nothing to allocate")
            return
        subscription = await self._subscription_repository.get_by_provider_id(
            provider_subscription_id
        )
        if subscription is None:
            logger.warning(
                "invoice.paid for unknown subscription %s; skipping", provider_subscription_id
            )
            return

        now = datetime.now(tz=UTC)
        if self._invoice_repository is not None:
            await self._record_invoice(
                event_object, subscription, invoice_status="paid", now=now
            )
        await self._allocate_credits_for_period(event_object, subscription, now=now)

    async def _handle_invoice_payment_failed(self, event_object: dict[str, Any]) -> None:
        """Failed renewal payment: mark past_due and record the invoice.

        No credits are granted. Current-period credits stand until the period
        ends (documented policy: the tenant keeps what was already paid for).
        """
        provider_subscription_id = _get_str(event_object.get("subscription", ""))
        if not provider_subscription_id:
            return
        subscription = await self._subscription_repository.get_by_provider_id(
            provider_subscription_id
        )
        if subscription is None:
            logger.warning(
                "invoice.payment_failed for unknown subscription %s; skipping",
                provider_subscription_id,
            )
            return

        now = datetime.now(tz=UTC)
        if self._invoice_repository is not None:
            await self._record_invoice(
                event_object, subscription, invoice_status="open", now=now
            )
        if subscription.status is not SubscriptionStatus.PAST_DUE:
            await self._subscription_repository.save(
                replace(subscription, status=SubscriptionStatus.PAST_DUE, updated_at=now)
            )
            logger.warning(
                "Subscription %s marked past_due after failed payment",
                provider_subscription_id,
            )

    async def _record_invoice(
        self,
        event_object: dict[str, Any],
        subscription: Subscription,
        *,
        invoice_status: str,
        now: datetime,
    ) -> None:
        if self._invoice_repository is None:
            return
        provider_invoice_id = _get_str(event_object.get("id", "")) or None
        if provider_invoice_id is not None:
            existing = await self._invoice_repository.get_by_provider_invoice_id(
                provider_invoice_id
            )
            if existing is not None:
                return  # duplicate delivery: invoice history is written once
        amount_cents = _get_int(event_object.get("amount_paid", 0)) or _get_int(
            event_object.get("amount_due", 0)
        )
        currency = (_get_str(event_object.get("currency", ""), "usd") or "usd").lower()
        await self._invoice_repository.save(
            Invoice(
                id=uuid4(),
                user_id=subscription.user_id,
                subscription_id=subscription.id,
                amount_cents=amount_cents,
                currency=currency,
                status=invoice_status,
                provider_invoice_id=provider_invoice_id,
                due_date=now,
                paid_at=now if invoice_status == "paid" else None,
                created_at=now,
            )
        )

    async def _allocate_credits_for_period(
        self,
        event_object: dict[str, Any],
        subscription: Subscription,
        *,
        now: datetime,
    ) -> None:
        if self._credit_service is None:
            return
        tenant_id = subscription.tenant_id or ""
        if not tenant_id:
            logger.warning(
                "subscription %s has no tenant; credits are tenant-scoped, skipping allocation",
                subscription.provider_subscription_id,
            )
            return
        plan = await self._plan_repository.get_by_id(subscription.plan_id)
        if plan is None:
            logger.warning("plan %s missing; skipping credit allocation", subscription.plan_id)
            return
        credits = _get_int(plan.limits.get("recovery_credits", 0))
        if credits <= 0:
            logger.info(
                "plan %s grants no recovery credits; nothing to allocate", plan.tier.value
            )
            return

        period_start, period_end = _extract_invoice_period(event_object, subscription, now)
        marker = subscription.provider_subscription_id or str(subscription.id)
        entry = await self._credit_service.allocate(
            tenant_id,
            amount=credits,
            period_start=period_start,
            period_end=period_end,
            idempotency_key=f"alloc:{marker}:{int(period_start.timestamp())}",
            reason=f"{plan.name} allowance for paid period ({credits} credits)",
            subscription_id=subscription.id,
            plan_tier=plan.tier.value,
            plan_name=plan.name,
        )
        if entry is None:
            logger.info(
                "Credit allocation for %s period %s already recorded; idempotent skip",
                marker,
                period_start.isoformat(),
            )
        else:
            logger.info(
                "Allocated %d recovery credits to tenant %s (plan %s)",
                credits,
                tenant_id,
                plan.tier.value,
            )
