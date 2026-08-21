from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CheckoutSessionResponse:
    """Hosted checkout session result."""

    session_id: str
    url: str
    expires_at: str


@dataclass(frozen=True, slots=True)
class PortalSessionResponse:
    """Customer portal session result."""

    url: str
    expires_at: str


@dataclass(frozen=True, slots=True)
class PlanResponse:
    """Public plan representation."""

    id: str
    name: str
    tier: str
    price_monthly_cents: int
    price_yearly_cents: int
    currency: str
    features: dict[str, object]
    limits: dict[str, int]


@dataclass(frozen=True, slots=True)
class SubscriptionResponse:
    """Public subscription representation."""

    id: str
    plan_id: str
    plan_name: str
    tier: str
    status: str
    interval: str
    current_period_start: str
    current_period_end: str
    cancel_at_period_end: bool


@dataclass(frozen=True, slots=True)
class UsageResponse:
    """Usage metrics response."""

    resource_type: str
    current: int
    limit: int | None
    period_start: str
    period_end: str
    percentage: float | None


@dataclass(frozen=True, slots=True)
class BillingOverviewResponse:
    """Combined billing overview for dashboard."""

    plan: PlanResponse | None
    subscription: SubscriptionResponse | None
    usage: list[UsageResponse]


@dataclass(frozen=True, slots=True)
class CreateCheckoutRequest:
    plan_id: str
    interval: str = "monthly"
    success_url: str = ""
    cancel_url: str = ""


@dataclass(frozen=True, slots=True)
class CreateCheckoutResponse:
    session_id: str
    url: str


@dataclass(frozen=True, slots=True)
class CancelSubscriptionResponse:
    subscription_id: str
    canceled_at: str
    access_until: str


@dataclass
class RecordUsageRequest:
    """Request to record usage for a resource type."""

    resource_type: str
    quantity: int = 1


@dataclass(frozen=True, slots=True)
class PortalSessionResponseDTO:
    """Public customer portal session representation."""

    url: str
    expires_at: str
