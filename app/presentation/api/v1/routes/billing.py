from collections.abc import Generator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.application.dto.billing import (
    BillingOverviewResponse,
    CancelSubscriptionResponse,
    CreateCheckoutRequest,
    CreateCheckoutResponse,
    PlanResponse,
    PortalSessionResponseDTO,
    RecordUsageRequest,
    SubscriptionResponse,
    UsageResponse,
)
from app.application.interfaces.payment_provider import PaymentProvider
from app.domain.entities.billing_entities import Plan
from app.domain.exceptions.billing_errors import (
    PlanNotFoundError,
    SubscriptionAlreadyExistsError,
    SubscriptionNotFoundError,
)
from app.infrastructure.config.settings import Settings, get_settings
from app.infrastructure.payments.payment_providers import MockPaymentProvider, StripePaymentProvider
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_billing_repositories import (
    SQLAlchemyCheckoutRepository,
    SQLAlchemyPlanRepository,
    SQLAlchemySubscriptionRepository,
    SQLAlchemyUsageRepository,
    SQLAlchemyWebhookRepository,
)
from app.presentation.api.dependencies.auth import CurrentUser

router = APIRouter(prefix="/billing", tags=["Billing"])


def _get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_billing_settings() -> Settings:
    return get_settings()


def _plan_to_response(plan: Plan) -> PlanResponse:
    return PlanResponse(
        id=str(plan.id),
        name=plan.name,
        tier=plan.tier.value,
        price_monthly_cents=plan.price_monthly_cents,
        price_yearly_cents=plan.price_yearly_cents,
        currency=plan.currency,
        features=plan.features,
        limits=plan.limits,
    )


def _get_payment_provider(settings: Settings) -> PaymentProvider:
    if settings.stripe_secret_key and settings.stripe_webhook_secret:
        return StripePaymentProvider(
            secret_key=settings.stripe_secret_key,
            webhook_secret=settings.stripe_webhook_secret,
            publishable_key=settings.stripe_publishable_key,
        )
    if settings.app_env not in ("development", "test"):
        raise ValueError(
            "Stripe credentials must be configured in non-development environments."
        )
    return MockPaymentProvider(
        publishable_key=settings.stripe_publishable_key,
        webhook_secret=settings.stripe_webhook_secret or "whsec_mock",
    )


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans(
    session: Annotated[Session, Depends(_get_session)],
) -> list[PlanResponse]:
    repo = SQLAlchemyPlanRepository(session)
    plans = await repo.list_active()
    return [_plan_to_response(p) for p in plans]


@router.get("/subscription", response_model=SubscriptionResponse | None)
async def get_subscription(
    current_user: CurrentUser,
    session: Annotated[Session, Depends(_get_session)],
) -> SubscriptionResponse | None:
    from app.application.use_cases.get_subscription import GetSubscriptionUseCase
    use_case = GetSubscriptionUseCase(
        SQLAlchemySubscriptionRepository(session),
        SQLAlchemyPlanRepository(session),
    )
    subscription, _ = await use_case.execute(current_user.id)
    return subscription


@router.get("/usage", response_model=list[UsageResponse])
async def get_usage(
    current_user: CurrentUser,
    session: Annotated[Session, Depends(_get_session)],
) -> list[UsageResponse]:
    from app.application.use_cases.get_usage import GetUsageUseCase
    use_case = GetUsageUseCase(
        SQLAlchemyUsageRepository(session),
        SQLAlchemySubscriptionRepository(session),
        SQLAlchemyPlanRepository(session),
    )
    return await use_case.execute(current_user.id, current_user.tenant_id)


@router.get("/overview", response_model=BillingOverviewResponse)
async def get_billing_overview(
    current_user: CurrentUser,
    session: Annotated[Session, Depends(_get_session)],
) -> BillingOverviewResponse:
    from app.application.use_cases.get_subscription import GetSubscriptionUseCase
    from app.application.use_cases.get_usage import GetUsageUseCase

    sub_use_case = GetSubscriptionUseCase(
        SQLAlchemySubscriptionRepository(session),
        SQLAlchemyPlanRepository(session),
    )
    subscription, plan = await sub_use_case.execute(current_user.id)

    usage: list[UsageResponse] = []
    if plan:
        usage_use_case = GetUsageUseCase(
            SQLAlchemyUsageRepository(session),
            SQLAlchemySubscriptionRepository(session),
            SQLAlchemyPlanRepository(session),
        )
        usage = await usage_use_case.execute(current_user.id, current_user.tenant_id)

    return BillingOverviewResponse(plan=plan, subscription=subscription, usage=usage)


@router.post(
    "/checkout",
    response_model=CreateCheckoutResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_checkout(
    request: CreateCheckoutRequest,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(_get_session)],
    settings: Annotated[Settings, Depends(get_billing_settings)],
) -> CreateCheckoutResponse:
    provider = _get_payment_provider(settings)
    from app.application.use_cases.create_checkout_session import CreateCheckoutSessionUseCase
    use_case = CreateCheckoutSessionUseCase(
        SQLAlchemyPlanRepository(session),
        SQLAlchemySubscriptionRepository(session),
        SQLAlchemyCheckoutRepository(session),
        provider,
    )
    try:
        return await use_case.execute(request, current_user.id, current_user.tenant_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SubscriptionAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/cancel", response_model=CancelSubscriptionResponse)
async def cancel_subscription(
    current_user: CurrentUser,
    session: Annotated[Session, Depends(_get_session)],
) -> CancelSubscriptionResponse:
    from app.application.use_cases.cancel_subscription import CancelSubscriptionUseCase
    use_case = CancelSubscriptionUseCase(SQLAlchemySubscriptionRepository(session))
    try:
        return await use_case.execute(current_user.id)
    except SubscriptionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/webhook")
async def billing_webhook(
    request: Request,
    session: Annotated[Session, Depends(_get_session)],
    settings: Annotated[Settings, Depends(get_billing_settings)],
) -> dict[str, str]:
    payload = await request.body()
    signature = request.headers.get("Stripe-Signature", "")
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing signature header.",
        )

    provider = _get_payment_provider(settings)
    from app.application.use_cases.handle_webhook import HandleWebhookUseCase
    use_case = HandleWebhookUseCase(
        SQLAlchemyWebhookRepository(session),
        SQLAlchemySubscriptionRepository(session),
        SQLAlchemyCheckoutRepository(session),
        SQLAlchemyPlanRepository(session),
        provider,
    )
    try:
        await use_case.execute(payload, signature, settings.stripe_webhook_secret or "")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"status": "ok"}


@router.get("/publishable-key")
async def get_publishable_key(
    settings: Annotated[Settings, Depends(get_billing_settings)],
) -> dict[str, str | None]:
    provider = _get_payment_provider(settings)
    return {"publishableKey": provider.get_publishable_key()}


@router.post("/portal", response_model=PortalSessionResponseDTO)
async def create_portal_session(
    current_user: CurrentUser,
    session: Annotated[Session, Depends(_get_session)],
    settings: Annotated[Settings, Depends(get_billing_settings)],
) -> PortalSessionResponseDTO:
    provider = _get_payment_provider(settings)
    checkout_repo = SQLAlchemyCheckoutRepository(session)
    checkout = await checkout_repo.get_by_user_id(current_user.id)
    customer_id = checkout.customer_id if checkout else None
    try:
        result = await provider.create_portal_session(
            current_user.id, current_user.tenant_id, customer_id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return PortalSessionResponseDTO(url=result.url, expires_at=result.expires_at)


@router.post("/usage", response_model=dict[str, object])
async def record_usage(
    request: RecordUsageRequest,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(_get_session)],
) -> dict[str, object]:
    from app.application.use_cases.record_usage import RecordUsageUseCase

    use_case = RecordUsageUseCase(
        SQLAlchemyUsageRepository(session),
        SQLAlchemySubscriptionRepository(session),
        SQLAlchemyPlanRepository(session),
    )
    return await use_case.execute(
        current_user.id,
        current_user.tenant_id,
        request.resource_type,
        request.quantity,
    )
