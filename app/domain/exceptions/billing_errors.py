"""Billing domain exceptions."""

from datetime import datetime

from app.domain.exceptions.domain_errors import DomainError


class BillingError(DomainError):
    """Base billing exception."""


class PlanNotFoundError(BillingError):
    """Requested plan does not exist."""


class InvalidPlanError(BillingError):
    """Plan is not available for purchase."""


class SubscriptionNotFoundError(BillingError):
    """No active subscription found for user."""


class SubscriptionAlreadyExistsError(BillingError):
    """User already has an active subscription."""


class CheckoutSessionError(BillingError):
    """Checkout session could not be created."""


class WebhookVerificationError(BillingError):
    """Webhook signature verification failed."""


class WebhookProcessingError(BillingError):
    """Webhook could not be processed."""


class UsageLimitExceededError(BillingError):
    """Usage limit exceeded for current plan."""


class PaymentProviderError(BillingError):
    """Payment provider returned an error."""


class InvoiceNotFoundError(BillingError):
    """Invoice not found."""


class InsufficientCreditsError(BillingError):
    """A billable recovery was attempted with no credits left.

    Carries the balance context so the API can answer with HTTP 402 and a
    message that states the remaining balance and the renewal date.
    """

    def __init__(
        self,
        tenant_id: str,
        available: int,
        required: int,
        period_end: datetime | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.available = available
        self.required = required
        self.period_end = period_end
        super().__init__(
            f"Tenant {tenant_id} has {available} recovery credit(s) available, "
            f"{required} required."
        )


class DuplicateCreditOperationError(BillingError):
    """An idempotent credit operation was already recorded in the ledger.

    Callers treat this as a no-op (the movement already exists), which is what
    makes duplicate webhook events and retried executions free of double
    charges.
    """
