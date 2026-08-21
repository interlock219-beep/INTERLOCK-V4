from datetime import UTC, datetime
from urllib.parse import urlparse
from uuid import UUID, uuid4

from app.application.dto.billing import (
    CreateCheckoutRequest,
    CreateCheckoutResponse,
)
from app.application.interfaces.payment_provider import PaymentProvider
from app.domain.entities.billing_entities import CheckoutSession
from app.domain.exceptions.billing_errors import (
    PlanNotFoundError,
)
from app.domain.repositories.billing_repositories import (
    CheckoutRepository,
    PlanRepository,
    SubscriptionRepository,
)
from app.infrastructure.config.settings import get_settings


class CreateCheckoutSessionUseCase:
    def __init__(
        self,
        plan_repository: PlanRepository,
        subscription_repository: SubscriptionRepository,
        checkout_repository: CheckoutRepository,
        payment_provider: PaymentProvider,
    ) -> None:
        self._plan_repository = plan_repository
        self._subscription_repository = subscription_repository
        self._checkout_repository = checkout_repository
        self._payment_provider = payment_provider

    async def execute(
        self,
        request: CreateCheckoutRequest,
        user_id: UUID,
        tenant_id: str | None,
    ) -> CreateCheckoutResponse:
        plan = await self._plan_repository.get_by_id(UUID(request.plan_id))
        if plan is None or not plan.is_active:
            raise PlanNotFoundError(
                f"Plan not found or inactive: {request.plan_id}"
            )

        active_subscription = (
            await self._subscription_repository.get_active_by_user(user_id)
        )
        if active_subscription is not None:
            from app.domain.exceptions.billing_errors import (
                SubscriptionAlreadyExistsError,
            )

            raise SubscriptionAlreadyExistsError(
                "User already has an active subscription."
            )

        base_url = (
            request.success_url.rsplit("?", 1)[0]
            if "?" in request.success_url
            else request.success_url
        )
        success_url = f"{base_url}?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = request.cancel_url or base_url

        settings = get_settings()
        allowed_origins = {origin.rstrip("/") for origin in settings.cors_origins}
        for url in (success_url, cancel_url):
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                raise ValueError(f"Invalid checkout URL scheme: {parsed.scheme}")
            origin = f"{parsed.scheme}://{parsed.netloc}"
            if origin not in allowed_origins:
                raise ValueError(
                    f"Checkout URL origin not allowed: {origin}"
                )

        provider_session = await self._payment_provider.create_checkout_session(
            CreateCheckoutRequest(
                plan_id=request.plan_id,
                interval=request.interval,
                success_url=success_url,
                cancel_url=cancel_url,
            ),
            user_id,
            tenant_id,
        )

        checkout = CheckoutSession(
            id=uuid4(),
            user_id=user_id,
            tenant_id=tenant_id,
            plan_id=plan.id,
            provider_session_id=provider_session.session_id,
            status="open",
            success_url=success_url,
            cancel_url=cancel_url,
            expires_at=datetime.fromtimestamp(
                int(provider_session.expires_at), tz=UTC
            ),
        )
        await self._checkout_repository.save(checkout)

        return CreateCheckoutResponse(
            session_id=provider_session.session_id,
            url=provider_session.url,
        )
