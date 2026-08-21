"""Billing domain exceptions."""

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
