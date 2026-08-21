import pytest
from sqlalchemy.orm import Session

from app.domain.entities.billing_entities import (
    BillingInterval,
    CheckoutSession,
    Plan,
    PlanTier,
    Subscription,
    SubscriptionStatus,
    WebhookEvent,
)
from app.infrastructure.persistence.repositories.sqlalchemy_billing_repositories import (
    SQLAlchemyCheckoutRepository,
    SQLAlchemyPlanRepository,
    SQLAlchemySubscriptionRepository,
    SQLAlchemyUsageRepository,
    SQLAlchemyWebhookRepository,
)


@pytest.fixture
def billing_db() -> Session:
    from app.infrastructure.persistence.database import SessionLocal
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def plan_repo(billing_db: Session) -> SQLAlchemyPlanRepository:
    return SQLAlchemyPlanRepository(billing_db)


@pytest.fixture
def subscription_repo(billing_db: Session) -> SQLAlchemySubscriptionRepository:
    return SQLAlchemySubscriptionRepository(billing_db)


@pytest.fixture
def checkout_repo(billing_db: Session) -> SQLAlchemyCheckoutRepository:
    return SQLAlchemyCheckoutRepository(billing_db)


@pytest.fixture
def usage_repo(billing_db: Session) -> SQLAlchemyUsageRepository:
    return SQLAlchemyUsageRepository(billing_db)


@pytest.fixture
def webhook_repo(billing_db: Session) -> SQLAlchemyWebhookRepository:
    return SQLAlchemyWebhookRepository(billing_db)


@pytest.fixture
async def sample_plan(plan_repo: SQLAlchemyPlanRepository) -> Plan:
    plan = Plan(
        id=__import__("uuid").uuid4(),
        name="Pro",
        tier=PlanTier.PRO,
        price_monthly_cents=4900,
        price_yearly_cents=47040,
        currency="usd",
        features={},
        limits={"intents_per_day": 10000},
        is_active=True,
        created_at=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
        updated_at=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
    )
    return await plan_repo.save(plan)


class TestSQLAlchemyPlanRepository:
    @pytest.mark.asyncio
    async def test_get_by_id(self, plan_repo: SQLAlchemyPlanRepository, sample_plan: Plan) -> None:
        result = await plan_repo.get_by_id(sample_plan.id)
        assert result is not None
        assert result.id == sample_plan.id
        assert result.name == "Pro"

    @pytest.mark.asyncio
    async def test_get_by_id_missing(self, plan_repo: SQLAlchemyPlanRepository) -> None:
        result = await plan_repo.get_by_id(__import__("uuid").uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_tier(
        self, plan_repo: SQLAlchemyPlanRepository, sample_plan: Plan
    ) -> None:
        result = await plan_repo.get_by_tier("pro")
        assert result is not None
        assert result.id == sample_plan.id

    @pytest.mark.asyncio
    async def test_list_active(
        self, plan_repo: SQLAlchemyPlanRepository, sample_plan: Plan
    ) -> None:
        results = await plan_repo.list_active()
        assert len(results) >= 1
        assert any(p.id == sample_plan.id for p in results)


class TestSQLAlchemySubscriptionRepository:
    @pytest.mark.asyncio
    async def test_get_by_id(
        self, subscription_repo: SQLAlchemySubscriptionRepository, sample_plan: Plan
    ) -> None:
        subscription = Subscription(
            id=__import__("uuid").uuid4(),
            user_id=__import__("uuid").uuid4(),
            tenant_id="tenant-1",
            plan_id=sample_plan.id,
            status=SubscriptionStatus.ACTIVE,
            interval=BillingInterval.MONTHLY,
            current_period_start=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
            current_period_end=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
        )
        saved = await subscription_repo.save(subscription)
        result = await subscription_repo.get_by_id(saved.id)
        assert result is not None
        assert result.id == saved.id

    @pytest.mark.asyncio
    async def test_get_by_id_with_user_filter(
        self, subscription_repo: SQLAlchemySubscriptionRepository, sample_plan: Plan
    ) -> None:
        user_a = __import__("uuid").uuid4()
        user_b = __import__("uuid").uuid4()
        sub_a = Subscription(
            id=__import__("uuid").uuid4(),
            user_id=user_a,
            tenant_id="tenant-1",
            plan_id=sample_plan.id,
            status=SubscriptionStatus.ACTIVE,
            interval=BillingInterval.MONTHLY,
            current_period_start=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
            current_period_end=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
        )
        sub_b = Subscription(
            id=__import__("uuid").uuid4(),
            user_id=user_b,
            tenant_id="tenant-2",
            plan_id=sample_plan.id,
            status=SubscriptionStatus.ACTIVE,
            interval=BillingInterval.MONTHLY,
            current_period_start=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
            current_period_end=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
        )
        await subscription_repo.save(sub_a)
        await subscription_repo.save(sub_b)

        result_a = await subscription_repo.get_by_id(sub_a.id, user_a)
        assert result_a is not None
        assert result_a.user_id == user_a

        result_b = await subscription_repo.get_by_id(sub_a.id, user_b)
        assert result_b is None

    @pytest.mark.asyncio
    async def test_delete_with_user_filter(
        self,
        subscription_repo: SQLAlchemySubscriptionRepository,
        billing_db: Session,
        sample_plan: Plan,
    ) -> None:
        user_a = __import__("uuid").uuid4()
        user_b = __import__("uuid").uuid4()
        sub_a = Subscription(
            id=__import__("uuid").uuid4(),
            user_id=user_a,
            tenant_id="tenant-1",
            plan_id=sample_plan.id,
            status=SubscriptionStatus.ACTIVE,
            interval=BillingInterval.MONTHLY,
            current_period_start=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
            current_period_end=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
        )
        sub_b = Subscription(
            id=__import__("uuid").uuid4(),
            user_id=user_b,
            tenant_id="tenant-2",
            plan_id=sample_plan.id,
            status=SubscriptionStatus.ACTIVE,
            interval=BillingInterval.MONTHLY,
            current_period_start=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
            current_period_end=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
        )
        await subscription_repo.save(sub_a)
        await subscription_repo.save(sub_b)
        billing_db.commit()

        await subscription_repo.delete(sub_a.id, user_b)
        billing_db.commit()
        remaining = await subscription_repo.get_by_id(sub_a.id)
        assert remaining is not None

        await subscription_repo.delete(sub_a.id, user_a)
        billing_db.commit()
        remaining = await subscription_repo.get_by_id(sub_a.id)
        assert remaining is None

    @pytest.mark.asyncio
    async def test_get_active_by_user(
        self, subscription_repo: SQLAlchemySubscriptionRepository, sample_plan: Plan
    ) -> None:
        user_id = __import__("uuid").uuid4()
        subscription = Subscription(
            id=__import__("uuid").uuid4(),
            user_id=user_id,
            tenant_id="tenant-1",
            plan_id=sample_plan.id,
            status=SubscriptionStatus.ACTIVE,
            interval=BillingInterval.MONTHLY,
            current_period_start=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
            current_period_end=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
            provider_subscription_id="sub_test_456",
        )
        await subscription_repo.save(subscription)
        result = await subscription_repo.get_active_by_user(user_id)
        assert result is not None
        assert result.id == subscription.id

    @pytest.mark.asyncio
    async def test_get_by_provider_id(
        self, subscription_repo: SQLAlchemySubscriptionRepository, sample_plan: Plan
    ) -> None:
        subscription = Subscription(
            id=__import__("uuid").uuid4(),
            user_id=__import__("uuid").uuid4(),
            tenant_id="tenant-1",
            plan_id=sample_plan.id,
            status=SubscriptionStatus.ACTIVE,
            interval=BillingInterval.MONTHLY,
            current_period_start=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
            current_period_end=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
            provider_subscription_id="sub_provider_test",
        )
        await subscription_repo.save(subscription)
        result = await subscription_repo.get_by_provider_id("sub_provider_test")
        assert result is not None
        assert result.id == subscription.id


class TestSQLAlchemyCheckoutRepository:
    @pytest.mark.asyncio
    async def test_get_by_id(
        self, checkout_repo: SQLAlchemyCheckoutRepository, sample_plan: Plan
    ) -> None:
        checkout = CheckoutSession(
            id=__import__("uuid").uuid4(),
            user_id=__import__("uuid").uuid4(),
            plan_id=sample_plan.id,
            provider_session_id="cs_test_123",
            status="open",
            success_url="http://localhost/success",
            cancel_url="http://localhost/cancel",
            expires_at=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
        )
        saved = await checkout_repo.save(checkout)
        result = await checkout_repo.get_by_id(saved.id)
        assert result is not None
        assert result.id == saved.id

    @pytest.mark.asyncio
    async def test_get_by_id_with_user_filter(
        self, checkout_repo: SQLAlchemyCheckoutRepository, sample_plan: Plan
    ) -> None:
        user_a = __import__("uuid").uuid4()
        user_b = __import__("uuid").uuid4()
        checkout_a = CheckoutSession(
            id=__import__("uuid").uuid4(),
            user_id=user_a,
            plan_id=sample_plan.id,
            provider_session_id="cs_a",
            status="open",
            success_url="http://localhost/success",
            cancel_url="http://localhost/cancel",
            expires_at=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
        )
        checkout_b = CheckoutSession(
            id=__import__("uuid").uuid4(),
            user_id=user_b,
            plan_id=sample_plan.id,
            provider_session_id="cs_b",
            status="open",
            success_url="http://localhost/success",
            cancel_url="http://localhost/cancel",
            expires_at=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
        )
        await checkout_repo.save(checkout_a)
        await checkout_repo.save(checkout_b)

        result_a = await checkout_repo.get_by_id(checkout_a.id, user_a)
        assert result_a is not None
        assert result_a.user_id == user_a

        result_b = await checkout_repo.get_by_id(checkout_a.id, user_b)
        assert result_b is None

    @pytest.mark.asyncio
    async def test_update_customer_id_with_user_filter(
        self, checkout_repo: SQLAlchemyCheckoutRepository, sample_plan: Plan
    ) -> None:
        user_a = __import__("uuid").uuid4()
        user_b = __import__("uuid").uuid4()
        checkout = CheckoutSession(
            id=__import__("uuid").uuid4(),
            user_id=user_a,
            plan_id=sample_plan.id,
            provider_session_id="cs_test",
            status="open",
            success_url="http://localhost/success",
            cancel_url="http://localhost/cancel",
            expires_at=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
        )
        saved = await checkout_repo.save(checkout)

        result = await checkout_repo.update_customer_id(saved.id, "cus_123", user_b)
        assert result is None

        result = await checkout_repo.update_customer_id(saved.id, "cus_123", user_a)
        assert result is not None
        assert result.customer_id == "cus_123"

    @pytest.mark.asyncio
    async def test_delete_with_user_filter(
        self, checkout_repo: SQLAlchemyCheckoutRepository, billing_db: Session, sample_plan: Plan
    ) -> None:
        user_a = __import__("uuid").uuid4()
        user_b = __import__("uuid").uuid4()
        checkout_a = CheckoutSession(
            id=__import__("uuid").uuid4(),
            user_id=user_a,
            plan_id=sample_plan.id,
            provider_session_id="cs_a",
            status="open",
            success_url="http://localhost/success",
            cancel_url="http://localhost/cancel",
            expires_at=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
        )
        await checkout_repo.save(checkout_a)
        billing_db.commit()

        await checkout_repo.delete(checkout_a.id, user_b)
        billing_db.commit()
        remaining = await checkout_repo.get_by_id(checkout_a.id)
        assert remaining is not None

        await checkout_repo.delete(checkout_a.id, user_a)
        billing_db.commit()
        remaining = await checkout_repo.get_by_id(checkout_a.id)
        assert remaining is None


class TestSQLAlchemyUsageRepository:
    @pytest.mark.asyncio
    async def test_record_and_get_usage(self, usage_repo: SQLAlchemyUsageRepository) -> None:
        user_id = __import__("uuid").uuid4()
        now = __import__("datetime").datetime.now(tz=__import__("datetime").UTC)
        period_start = now
        period_end = now

        await usage_repo.record_usage(
            user_id, "tenant-1", "intents_per_day", 5, period_start, period_end
        )
        total = await usage_repo.get_current_period_usage(
            user_id, "intents_per_day", period_start, period_end
        )
        assert total == 5


class TestSQLAlchemyWebhookRepository:
    @pytest.mark.asyncio
    async def test_save_and_get_by_provider_event_id(
        self, webhook_repo: SQLAlchemyWebhookRepository, billing_db: Session
    ) -> None:
        event_id = "evt_test_123"
        await webhook_repo.save(
            WebhookEvent(
                id=__import__("uuid").uuid4(),
                provider_event_id=event_id,
                event_type="checkout.session.completed",
                payload={"id": event_id},
                processed=False,
                created_at=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
            )
        )
        billing_db.commit()
        result = await webhook_repo.get_by_provider_event_id(event_id)
        assert result is not None
        assert result.event_type == "checkout.session.completed"
