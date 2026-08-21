"""Seed default subscription plans into the database."""

import asyncio
from datetime import UTC, datetime

from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.database import Base, engine, SessionLocal
from app.infrastructure.persistence.models import PlanModel


def seed_plans() -> None:
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        existing = session.query(PlanModel).count()
        if existing > 0:
            print(f"Plans already seeded ({existing} found). Skipping.")
            return

        plans = [
            PlanModel(
                id="00000000-0000-0000-0000-000000000001",
                name="Free",
                tier="free",
                price_monthly_cents=0,
                price_yearly_cents=0,
                currency="usd",
                features={"agents": 1, "intents_per_day": 100, "hitl_approvers": 1, "policy_rules": 10, "support": "community", "audit_retention_days": 7, "sla": "none"},
                limits={"agents": 1, "intents_per_day": 100, "policy_rules": 10, "hitl_approvers": 1},
                is_active=True,
                created_at=datetime.now(tz=UTC),
                updated_at=datetime.now(tz=UTC),
            ),
            PlanModel(
                id="00000000-0000-0000-0000-000000000002",
                name="Pro",
                tier="pro",
                price_monthly_cents=4900,
                price_yearly_cents=47040,
                currency="usd",
                features={"agents": 10, "intents_per_day": 10000, "hitl_approvers": 5, "policy_rules": 100, "support": "priority_email", "audit_retention_days": 30, "sla": "99.9%"},
                limits={"agents": 10, "intents_per_day": 10000, "policy_rules": 100, "hitl_approvers": 5},
                is_active=True,
                created_at=datetime.now(tz=UTC),
                updated_at=datetime.now(tz=UTC),
            ),
            PlanModel(
                id="00000000-0000-0000-0000-000000000003",
                name="Business",
                tier="business",
                price_monthly_cents=19900,
                price_yearly_cents=191040,
                currency="usd",
                features={"agents": 100, "intents_per_day": 100000, "hitl_approvers": 25, "policy_rules": 1000, "support": "priority_chat_csm", "audit_retention_days": 90, "sla": "99.95%", "multi_tenant_rbac": True},
                limits={"agents": 100, "intents_per_day": 100000, "policy_rules": 1000, "hitl_approvers": 25},
                is_active=True,
                created_at=datetime.now(tz=UTC),
                updated_at=datetime.now(tz=UTC),
            ),
            PlanModel(
                id="00000000-0000-0000-0000-000000000004",
                name="Enterprise",
                tier="enterprise",
                price_monthly_cents=0,
                price_yearly_cents=0,
                currency="usd",
                features={"agents": 0, "intents_per_day": 0, "hitl_approvers": 0, "policy_rules": 0, "support": "dedicated", "audit_retention_days": 365, "sla": "99.99%", "custom": True},
                limits={"agents": 0, "intents_per_day": 0, "policy_rules": 0, "hitl_approvers": 0},
                is_active=True,
                created_at=datetime.now(tz=UTC),
                updated_at=datetime.now(tz=UTC),
            ),
        ]
        for plan in plans:
            session.add(plan)
        session.commit()
        print(f"Seeded {len(plans)} plans successfully.")
    except Exception as exc:
        session.rollback()
        print(f"Failed to seed plans: {exc}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed_plans()
