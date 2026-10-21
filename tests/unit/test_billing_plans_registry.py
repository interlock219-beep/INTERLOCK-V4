"""Central plan registry: prices, credit allowances and currency policy.

The registry is the single source of truth for commercial terms; nothing else
may hardcode plan prices or credit limits.
"""

from __future__ import annotations

import pytest

from app.domain.entities.billing_entities import PlanTier
from app.domain.services.billing_plans import (
    DEFAULT_CURRENCY,
    PLAN_DEFINITIONS,
    get_plan_definition,
    monthly_credits_for,
    price_cents_for,
    validate_currency_consistency,
)


class TestPlanDefinitions:
    def test_starter_is_15_dollars_with_100_credits(self) -> None:
        starter = get_plan_definition(PlanTier.STARTER)
        assert starter.price_monthly_cents == 1500
        assert starter.monthly_recovery_credits == 100
        assert starter.enforce_credits is True
        assert starter.name == "Starter"

    def test_pro_is_30_dollars_with_250_credits(self) -> None:
        pro = get_plan_definition(PlanTier.PRO)
        assert pro.price_monthly_cents == 3000
        assert pro.monthly_recovery_credits == 250
        assert pro.enforce_credits is True

    def test_free_evaluation_grants_no_credits_and_is_unenforced(self) -> None:
        free = get_plan_definition(PlanTier.FREE)
        assert free.price_monthly_cents == 0
        assert free.monthly_recovery_credits == 0
        assert free.enforce_credits is False

    def test_registry_covers_every_tier(self) -> None:
        assert set(PLAN_DEFINITIONS) == set(PlanTier)

    def test_yearly_price_is_twelve_monthly_payments(self) -> None:
        # No annual discount is advertised; the yearly price is the plain
        # monthly-equivalent total so interval pricing stays consistent.
        assert get_plan_definition(PlanTier.PRO).price_yearly_cents == 3000 * 12
        assert get_plan_definition(PlanTier.STARTER).price_yearly_cents == 1500 * 12


class TestPricingHelpers:
    def test_price_cents_for_monthly_and_yearly(self) -> None:
        assert price_cents_for(PlanTier.PRO, "monthly") == 3000
        assert price_cents_for(PlanTier.PRO, "yearly") == 36000
        assert price_cents_for(PlanTier.STARTER, "monthly") == 1500

    def test_monthly_credits_for(self) -> None:
        assert monthly_credits_for(PlanTier.STARTER) == 100
        assert monthly_credits_for(PlanTier.PRO) == 250
        assert monthly_credits_for(PlanTier.FREE) == 0

    def test_unknown_tier_raises(self) -> None:
        with pytest.raises(KeyError):
            get_plan_definition("not-a-tier")  # type: ignore[arg-type]


class TestCurrencyPolicy:
    def test_registry_currency_is_usd(self) -> None:
        assert DEFAULT_CURRENCY == "usd"

    def test_validate_currency_accepts_registry_currency(self) -> None:
        validate_currency_consistency(DEFAULT_CURRENCY)
        validate_currency_consistency(DEFAULT_CURRENCY.upper())

    def test_validate_currency_rejects_mismatch(self) -> None:
        with pytest.raises(ValueError, match="mixed currencies"):
            validate_currency_consistency("eur")
