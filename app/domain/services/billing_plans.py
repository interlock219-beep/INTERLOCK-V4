"""Central registry of purchasable INTERLOCK plans.

Single source of truth for plan prices, currency and the recovery-credit
allowance. Nothing else in the application may hardcode plan prices or credit
limits: checkout, seeding, the wallet allocator and the public API all read
from :data:`PLAN_DEFINITIONS` (the wallet allocator additionally trusts only
the *server-side* ``plans`` table row, which is seeded from this registry).

Currency policy: every definition carries the same currency as
:data:`DEFAULT_CURRENCY`; :func:`validate_currency_consistency` is called by
the seeder and the checkout use case so a misconfigured deployment fails
loudly instead of charging the wrong currency.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.entities.billing_entities import PlanTier

DEFAULT_CURRENCY = "usd"


@dataclass(frozen=True, slots=True)
class PlanDefinition:
    """Immutable commercial definition of one plan tier."""

    tier: PlanTier
    name: str
    price_monthly_cents: int
    monthly_recovery_credits: int
    enforce_credits: bool
    summary: str

    @property
    def price_yearly_cents(self) -> int:
        # Annual price is the plain monthly-equivalent total; no discount is
        # advertised until one is explicitly decided.
        return self.price_monthly_cents * 12


PLAN_DEFINITIONS: dict[PlanTier, PlanDefinition] = {
    PlanTier.FREE: PlanDefinition(
        tier=PlanTier.FREE,
        name="Free evaluation",
        price_monthly_cents=0,
        monthly_recovery_credits=0,
        enforce_credits=False,
        summary="Evaluate the full recovery engine with no card and no credits.",
    ),
    PlanTier.STARTER: PlanDefinition(
        tier=PlanTier.STARTER,
        name="Starter",
        price_monthly_cents=1500,
        monthly_recovery_credits=100,
        enforce_credits=True,
        summary="Production recovery for a single team: 100 verified recoveries per month.",
    ),
    PlanTier.PRO: PlanDefinition(
        tier=PlanTier.PRO,
        name="Pro",
        price_monthly_cents=3000,
        monthly_recovery_credits=250,
        enforce_credits=True,
        summary="Higher-volume recovery: 250 verified recoveries per month.",
    ),
    PlanTier.BUSINESS: PlanDefinition(
        tier=PlanTier.BUSINESS,
        name="Business",
        price_monthly_cents=19900,
        monthly_recovery_credits=0,
        enforce_credits=False,
        summary="Legacy tier retained for existing accounts; contact us for terms.",
    ),
    PlanTier.ENTERPRISE: PlanDefinition(
        tier=PlanTier.ENTERPRISE,
        name="Enterprise",
        price_monthly_cents=0,
        monthly_recovery_credits=0,
        enforce_credits=False,
        summary="Custom contracts; priced by agreement.",
    ),
}


def get_plan_definition(tier: PlanTier) -> PlanDefinition:
    """Return the definition for ``tier``.

    Raises ``KeyError`` for unknown tiers; callers map that to
    ``PlanNotFoundError`` at the edge.
    """
    return PLAN_DEFINITIONS[tier]


def monthly_credits_for(tier: PlanTier) -> int:
    """Monthly recovery-credit allowance granted for ``tier`` (0 if none)."""
    return PLAN_DEFINITIONS[tier].monthly_recovery_credits


def price_cents_for(tier: PlanTier, interval: str) -> int:
    """Server-side price in cents for ``tier``; ``interval`` is monthly|yearly."""
    definition = PLAN_DEFINITIONS[tier]
    return definition.price_yearly_cents if interval == "yearly" else definition.price_monthly_cents


def validate_currency_consistency(currency: str) -> None:
    """Fail loudly when a deployment's currency differs from the registry."""
    if currency.lower() != DEFAULT_CURRENCY:
        raise ValueError(
            f"Configured billing currency '{currency}' does not match the plan registry "
            f"currency '{DEFAULT_CURRENCY}'. Plans must not be priced in mixed currencies."
        )
