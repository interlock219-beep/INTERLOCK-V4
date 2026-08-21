from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.domain.entities.billing_entities import (
    CheckoutSession,
    Plan,
    Subscription,
    WebhookEvent,
)


class PlanRepository(ABC):
    @abstractmethod
    async def get_by_id(self, plan_id: UUID) -> Plan | None: ...

    @abstractmethod
    async def get_by_tier(self, tier: str) -> Plan | None: ...

    @abstractmethod
    async def list_active(self) -> list[Plan]: ...

    @abstractmethod
    async def save(self, plan: Plan) -> Plan: ...


class SubscriptionRepository(ABC):
    @abstractmethod
    async def get_by_id(
        self, subscription_id: UUID, user_id: UUID | None = None
    ) -> Subscription | None: ...

    @abstractmethod
    async def get_active_by_user(self, user_id: UUID) -> Subscription | None: ...

    @abstractmethod
    async def get_by_provider_id(
        self, provider_subscription_id: str
    ) -> Subscription | None: ...

    @abstractmethod
    async def save(self, subscription: Subscription) -> Subscription: ...

    @abstractmethod
    async def delete(self, subscription_id: UUID, user_id: UUID | None = None) -> None: ...


class UsageRepository(ABC):
    @abstractmethod
    async def get_current_period_usage(
        self,
        user_id: UUID,
        resource_type: str,
        period_start: datetime,
        period_end: datetime,
    ) -> int: ...

    @abstractmethod
    async def record_usage(
        self,
        user_id: UUID,
        tenant_id: str | None,
        resource_type: str,
        quantity: int,
        period_start: datetime,
        period_end: datetime,
    ) -> None: ...


class CheckoutRepository(ABC):
    @abstractmethod
    async def get_by_id(
        self, checkout_id: UUID, user_id: UUID | None = None
    ) -> CheckoutSession | None: ...

    @abstractmethod
    async def get_by_provider_session_id(
        self, provider_session_id: str
    ) -> CheckoutSession | None: ...

    @abstractmethod
    async def get_by_user_id(
        self, user_id: UUID
    ) -> CheckoutSession | None: ...

    @abstractmethod
    async def save(self, checkout: CheckoutSession) -> CheckoutSession: ...

    @abstractmethod
    async def update_customer_id(
        self, checkout_id: UUID, customer_id: str | None, user_id: UUID | None = None
    ) -> CheckoutSession | None: ...

    @abstractmethod
    async def delete(self, checkout_id: UUID, user_id: UUID | None = None) -> None: ...


class WebhookRepository(ABC):
    @abstractmethod
    async def get_by_provider_event_id(
        self, provider_event_id: str
    ) -> WebhookEvent | None: ...

    @abstractmethod
    async def save(self, webhook_event: WebhookEvent) -> WebhookEvent: ...
