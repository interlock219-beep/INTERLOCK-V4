"""Seed (and keep in sync) the purchasable plans from the central registry.

The registry in ``app.domain.services.billing_plans`` is the single source of
truth for plan names, prices, currency and the recovery-credit allowance.
This script upserts every registered tier: missing tiers are inserted, and
existing rows have their commercial fields (name/price/currency/credit
allowance) synced. Custom ``features``/``limits`` values written by operators
are preserved; only the registry-owned keys are touched.

Currency consistency is validated against the registry so a deployment can
never seed plans priced in the wrong currency.
"""

import json
from datetime import UTC, datetime
from uuid import UUID

from app.domain.services.billing_plans import PLAN_DEFINITIONS, validate_currency_consistency
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.database import Base, SessionLocal, engine
from app.infrastructure.persistence.models import PlanModel

# Stable ids (keep the historical assignments; Starter was added later).
PLAN_IDS = {
    "free": "00000000-0000-0000-0000-000000000001",
    "pro": "00000000-0000-0000-0000-000000000002",
    "business": "00000000-0000-0000-0000-000000000003",
    "enterprise": "00000000-0000-0000-0000-000000000004",
    "starter": "00000000-0000-0000-0000-000000000005",
}

# Non-registry feature/limit defaults per tier (operator-editable afterwards).
TIER_FEATURES = {
    "free": {"support": "community", "audit_retention_days": 7, "sla": "none"},
    "starter": {"support": "email", "audit_retention_days": 30, "sla": "best_effort"},
    "pro": {"support": "priority_email", "audit_retention_days": 60, "sla": "99.9%"},
    "business": {"support": "priority_chat_csm", "audit_retention_days": 90, "sla": "99.95%"},
    "enterprise": {"support": "dedicated", "audit_retention_days": 365, "sla": "99.99%"},
}
TIER_LIMITS = {
    "free": {"intents_per_day": 100},
    "starter": {"intents_per_day": 1000},
    "pro": {"intents_per_day": 10000},
    "business": {"intents_per_day": 100000},
    "enterprise": {"intents_per_day": 0},
}


def seed_plans() -> None:
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        currency = get_settings().billing_currency
        validate_currency_consistency(currency)
        now = datetime.now(tz=UTC)
        inserted = 0
        synced = 0
        for tier, definition in PLAN_DEFINITIONS.items():
            limits = dict(TIER_LIMITS.get(tier.value, {}))
            limits["recovery_credits"] = definition.monthly_recovery_credits
            existing = session.query(PlanModel).filter(PlanModel.tier == tier).first()
            if existing is None:
                session.add(
                    PlanModel(
                        id=UUID(PLAN_IDS[tier.value]),
                        name=definition.name,
                        tier=tier,
                        price_monthly_cents=definition.price_monthly_cents,
                        price_yearly_cents=definition.price_yearly_cents,
                        currency=currency,
                        features=json.dumps(TIER_FEATURES.get(tier.value, {})),
                        limits=json.dumps(limits),
                        is_active=True,
                        created_at=now,
                        updated_at=now,
                    )
                )
                inserted += 1
            else:
                existing.name = definition.name
                existing.price_monthly_cents = definition.price_monthly_cents
                existing.price_yearly_cents = definition.price_yearly_cents
                existing.currency = currency
                try:
                    current_limits = json.loads(existing.limits or "{}")
                except (TypeError, ValueError):
                    current_limits = {}
                current_limits["recovery_credits"] = definition.monthly_recovery_credits
                existing.limits = json.dumps(current_limits)
                existing.updated_at = now
                synced += 1
        session.commit()
        print(  # noqa: T201 - CLI script: stdout summary is the interface
            f"Plans synced from registry: {inserted} inserted, {synced} updated."
        )
    except Exception as exc:
        session.rollback()
        print(f"Failed to seed plans: {exc}")  # noqa: T201 - CLI script error output
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed_plans()
