from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class PlanTier(StrEnum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


class BillingInterval(StrEnum):
    MONTHLY = "monthly"
    YEARLY = "yearly"


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired"
    TRIALING = "trialing"
    UNPAID = "unpaid"


@dataclass(frozen=True, slots=True)
class Plan:
    id: UUID
    name: str
    tier: PlanTier
    price_monthly_cents: int
    price_yearly_cents: int
    currency: str = "usd"
    features: dict[str, object] = field(default_factory=dict)
    limits: dict[str, int] = field(default_factory=dict)
    is_active: bool = True
    created_at: datetime = field(
        default_factory=lambda: datetime.now(tz=datetime.now().astimezone().tzinfo)
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(tz=datetime.now().astimezone().tzinfo)
    )


@dataclass(frozen=True, slots=True)
class Subscription:
    id: UUID
    user_id: UUID
    tenant_id: str | None
    plan_id: UUID
    status: SubscriptionStatus
    interval: BillingInterval
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool = False
    provider_subscription_id: str | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(tz=datetime.now().astimezone().tzinfo)
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(tz=datetime.now().astimezone().tzinfo)
    )


@dataclass(frozen=True, slots=True)
class UsageRecord:
    id: UUID
    user_id: UUID
    tenant_id: str | None
    resource_type: str
    quantity: int
    period_start: datetime
    period_end: datetime
    created_at: datetime = field(
        default_factory=lambda: datetime.now(tz=datetime.now().astimezone().tzinfo)
    )


@dataclass(frozen=True, slots=True)
class CheckoutSession:
    id: UUID
    user_id: UUID
    plan_id: UUID
    provider_session_id: str
    status: str
    success_url: str
    cancel_url: str
    expires_at: datetime
    tenant_id: str | None = None
    customer_id: str | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(tz=datetime.now().astimezone().tzinfo)
    )


@dataclass(frozen=True, slots=True)
class WebhookEvent:
    id: UUID
    provider_event_id: str
    event_type: str
    payload: dict[str, object]
    processed: bool = False
    processed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(tz=datetime.now().astimezone().tzinfo)
    )


@dataclass(frozen=True, slots=True)
class Invoice:
    id: UUID
    user_id: UUID
    subscription_id: UUID
    amount_cents: int
    currency: str
    status: str
    provider_invoice_id: str | None
    due_date: datetime
    paid_at: datetime | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(tz=datetime.now().astimezone().tzinfo)
    )


class CreditLedgerKind(StrEnum):
    """Kinds of movements recorded in the append-only recovery-credit ledger.

    Every entry moves the tenant's *available* balance (allocated - consumed -
    reserved) and carries ``balance_after`` so the full history is auditable
    without reading the wallet row.
    """

    ALLOCATION = "allocation"  # paid period grant:            available +n
    RESERVATION = "reservation"  # hold before execution:        available -1
    RELEASE = "release"  # hold returned (non-billable):   available +1
    CONSUMPTION = "consumption"  # hold captured by outcome:        available  0
    EXPIRY = "expiry"  # unused credits expired:         available -n
    REFUND = "refund"  # operator refund:                available +n
    ADJUSTMENT = "adjustment"  # plan upgrade mid-period:       available +n


class CreditReservationStatus(StrEnum):
    """Lifecycle of the hold taken around one recovery execution."""

    ACTIVE = "active"
    CONSUMED = "consumed"
    RELEASED = "released"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class CreditWallet:
    """Server-controlled recovery-credit wallet for one tenant (organization).

    Customers can never edit this row; all mutations go through
    ``RecoveryCreditService`` inside database transactions. Invariant:
    ``available == allocated - consumed - reserved``.
    """

    id: UUID
    tenant_id: str
    allocated: int
    consumed: int
    reserved: int
    period_start: datetime
    period_end: datetime
    is_enforced: bool = False
    plan_tier: str = ""
    plan_name: str = ""
    subscription_id: UUID | None = None
    provider_subscription_id: str | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(tz=datetime.now().astimezone().tzinfo)
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(tz=datetime.now().astimezone().tzinfo)
    )

    @property
    def available(self) -> int:
        return self.allocated - self.consumed - self.reserved


@dataclass(frozen=True, slots=True)
class CreditLedgerEntry:
    """One append-only credit movement. Never updated or deleted."""

    id: UUID
    tenant_id: str
    kind: CreditLedgerKind
    delta: int
    balance_after: int
    reason: str
    idempotency_key: str
    recovery_plan_id: str | None = None
    subscription_id: UUID | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(tz=datetime.now().astimezone().tzinfo)
    )


@dataclass(frozen=True, slots=True)
class CreditReservation:
    """Hold placed around one recovery execution before its outcome is known."""

    id: UUID
    tenant_id: str
    recovery_plan_id: str
    status: CreditReservationStatus
    expires_at: datetime
    settled_at: datetime | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(tz=datetime.now().astimezone().tzinfo)
    )
