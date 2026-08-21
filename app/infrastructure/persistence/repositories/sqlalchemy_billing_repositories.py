import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
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
from app.domain.repositories.billing_repositories import (
    CheckoutRepository,
    PlanRepository,
    SubscriptionRepository,
    UsageRepository,
    WebhookRepository,
)
from app.infrastructure.persistence.models import (
    CheckoutSessionModel,
    PlanModel,
    SubscriptionModel,
    UsageRecordModel,
    WebhookEventModel,
)


def _plan_to_entity(model: PlanModel) -> Plan:
    return Plan(
        id=model.id,
        name=model.name,
        tier=PlanTier(model.tier.value),
        price_monthly_cents=model.price_monthly_cents,
        price_yearly_cents=model.price_yearly_cents,
        currency=model.currency,
        features=json.loads(model.features),
        limits=json.loads(model.limits),
        is_active=model.is_active,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _subscription_to_entity(model: SubscriptionModel) -> Subscription:
    return Subscription(
        id=model.id,
        user_id=model.user_id,
        tenant_id=model.tenant_id,
        plan_id=model.plan_id,
        status=SubscriptionStatus(model.status.value),
        interval=BillingInterval(model.interval.value),
        current_period_start=model.current_period_start,
        current_period_end=model.current_period_end,
        cancel_at_period_end=model.cancel_at_period_end,
        provider_subscription_id=model.provider_subscription_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _checkout_to_entity(model: CheckoutSessionModel) -> CheckoutSession:
    return CheckoutSession(
        id=model.id,
        user_id=model.user_id,
        plan_id=model.plan_id,
        provider_session_id=model.provider_session_id,
        customer_id=model.customer_id,
        status=model.status,
        success_url=model.success_url,
        cancel_url=model.cancel_url,
        expires_at=model.expires_at,
        tenant_id=model.tenant_id,
        created_at=model.created_at,
    )


def _webhook_to_entity(model: WebhookEventModel) -> WebhookEvent:
    return WebhookEvent(
        id=model.id,
        provider_event_id=model.provider_event_id,
        event_type=model.event_type,
        payload=json.loads(model.payload),
        processed=model.processed,
        processed_at=model.processed_at,
        error_message=model.error_message,
        created_at=model.created_at,
    )


class SQLAlchemyPlanRepository(PlanRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def _to_entity(self, model: PlanModel) -> Plan:
        return _plan_to_entity(model)

    async def get_by_id(self, plan_id: UUID) -> Plan | None:
        stmt = select(PlanModel).where(PlanModel.id == plan_id)
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_tier(self, tier: str) -> Plan | None:
        stmt = (
            select(PlanModel)
            .where(PlanModel.tier == tier, PlanModel.is_active)
            .order_by(PlanModel.price_monthly_cents)
        )
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list_active(self) -> list[Plan]:
        stmt = (
            select(PlanModel)
            .where(PlanModel.is_active)
            .order_by(PlanModel.price_monthly_cents)
        )
        result = self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def save(self, plan: Plan) -> Plan:
        model = PlanModel(
            id=plan.id,
            name=plan.name,
            tier=plan.tier,
            price_monthly_cents=plan.price_monthly_cents,
            price_yearly_cents=plan.price_yearly_cents,
            currency=plan.currency,
            features=json.dumps(plan.features),
            limits=json.dumps(plan.limits),
            is_active=plan.is_active,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        )
        self._session.add(model)
        self._session.flush()
        return plan


class SQLAlchemySubscriptionRepository(SubscriptionRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def _to_entity(self, model: SubscriptionModel) -> Subscription:
        return _subscription_to_entity(model)

    async def get_by_id(
        self, subscription_id: UUID, user_id: UUID | None = None
    ) -> Subscription | None:
        stmt = select(SubscriptionModel).where(
            SubscriptionModel.id == subscription_id
        )
        if user_id is not None:
            stmt = stmt.where(SubscriptionModel.user_id == user_id)
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_active_by_user(self, user_id: UUID) -> Subscription | None:
        stmt = (
            select(SubscriptionModel)
            .where(
                SubscriptionModel.user_id == user_id,
                SubscriptionModel.status.in_(
                    ["active", "trialing", "past_due"]
                ),
            )
            .order_by(SubscriptionModel.created_at.desc())
        )
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_provider_id(
        self, provider_subscription_id: str
    ) -> Subscription | None:
        stmt = select(SubscriptionModel).where(
            SubscriptionModel.provider_subscription_id
            == provider_subscription_id
        )
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def save(self, subscription: Subscription) -> Subscription:
        model = SubscriptionModel(
            id=subscription.id,
            user_id=subscription.user_id,
            tenant_id=subscription.tenant_id,
            plan_id=subscription.plan_id,
            status=subscription.status,
            interval=subscription.interval,
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            cancel_at_period_end=subscription.cancel_at_period_end,
            provider_subscription_id=subscription.provider_subscription_id,
            created_at=subscription.created_at,
            updated_at=subscription.updated_at,
        )
        self._session.add(model)
        self._session.flush()
        return subscription

    async def delete(self, subscription_id: UUID, user_id: UUID | None = None) -> None:
        stmt = select(SubscriptionModel).where(
            SubscriptionModel.id == subscription_id
        )
        if user_id is not None:
            stmt = stmt.where(SubscriptionModel.user_id == user_id)
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            self._session.delete(model)


class SQLAlchemyUsageRepository(UsageRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    async def get_current_period_usage(
        self,
        user_id: UUID,
        resource_type: str,
        period_start: datetime,
        period_end: datetime,
    ) -> int:
        stmt = (
            select(func.coalesce(func.sum(UsageRecordModel.quantity), 0))
            .where(
                UsageRecordModel.user_id == user_id,
                UsageRecordModel.resource_type == resource_type,
                UsageRecordModel.period_start >= period_start,
                UsageRecordModel.period_end <= period_end,
            )
        )
        result = self._session.execute(stmt)
        return int(result.scalar_one())

    async def record_usage(
        self,
        user_id: UUID,
        tenant_id: str | None,
        resource_type: str,
        quantity: int,
        period_start: datetime,
        period_end: datetime,
    ) -> None:
        model = UsageRecordModel(
            user_id=user_id,
            tenant_id=tenant_id,
            resource_type=resource_type,
            quantity=quantity,
            period_start=period_start,
            period_end=period_end,
            created_at=datetime.now(tz=timezone.utc),
        )
        self._session.add(model)
        self._session.flush()


class SQLAlchemyCheckoutRepository(CheckoutRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def _to_entity(self, model: CheckoutSessionModel) -> CheckoutSession:
        return _checkout_to_entity(model)

    async def get_by_id(
        self, checkout_id: UUID, user_id: UUID | None = None
    ) -> CheckoutSession | None:
        stmt = select(CheckoutSessionModel).where(
            CheckoutSessionModel.id == checkout_id
        )
        if user_id is not None:
            stmt = stmt.where(CheckoutSessionModel.user_id == user_id)
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_provider_session_id(
        self, provider_session_id: str
    ) -> CheckoutSession | None:
        stmt = select(CheckoutSessionModel).where(
            CheckoutSessionModel.provider_session_id == provider_session_id
        )
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_user_id(
        self, user_id: UUID
    ) -> CheckoutSession | None:
        stmt = (
            select(CheckoutSessionModel)
            .where(CheckoutSessionModel.user_id == user_id)
            .order_by(CheckoutSessionModel.created_at.desc())
            .limit(1)
        )
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def save(self, checkout: CheckoutSession) -> CheckoutSession:
        model = CheckoutSessionModel(
            id=checkout.id,
            user_id=checkout.user_id,
            tenant_id=checkout.tenant_id,
            plan_id=checkout.plan_id,
            provider_session_id=checkout.provider_session_id,
            customer_id=checkout.customer_id,
            status=checkout.status,
            success_url=checkout.success_url,
            cancel_url=checkout.cancel_url,
            expires_at=checkout.expires_at,
            created_at=checkout.created_at,
        )
        self._session.add(model)
        self._session.flush()
        return checkout

    async def update_customer_id(
        self, checkout_id: UUID, customer_id: str | None, user_id: UUID | None = None
    ) -> CheckoutSession | None:
        stmt = (
            select(CheckoutSessionModel)
            .where(CheckoutSessionModel.id == checkout_id)
            .with_for_update()
        )
        if user_id is not None:
            stmt = stmt.where(CheckoutSessionModel.user_id == user_id)
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        model.customer_id = customer_id
        self._session.flush()
        return self._to_entity(model)

    async def delete(self, checkout_id: UUID, user_id: UUID | None = None) -> None:
        stmt = select(CheckoutSessionModel).where(
            CheckoutSessionModel.id == checkout_id
        )
        if user_id is not None:
            stmt = stmt.where(CheckoutSessionModel.user_id == user_id)
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            self._session.delete(model)


class SQLAlchemyWebhookRepository(WebhookRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def _to_entity(self, model: WebhookEventModel) -> WebhookEvent:
        return _webhook_to_entity(model)

    async def get_by_provider_event_id(
        self, provider_event_id: str
    ) -> WebhookEvent | None:
        stmt = select(WebhookEventModel).where(
            WebhookEventModel.provider_event_id == provider_event_id
        )
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def save(self, webhook_event: WebhookEvent) -> WebhookEvent:
        model = WebhookEventModel(
            id=webhook_event.id,
            provider_event_id=webhook_event.provider_event_id,
            event_type=webhook_event.event_type,
            payload=json.dumps(webhook_event.payload),
            processed=webhook_event.processed,
            processed_at=webhook_event.processed_at,
            error_message=webhook_event.error_message,
            created_at=webhook_event.created_at,
        )
        self._session.merge(model)
        self._session.flush()
        return webhook_event
