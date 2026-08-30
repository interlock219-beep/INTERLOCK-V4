from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.application.dto.sso import (
    SSOAuthorizeRequest,
    SSOAuthorizeResponse,
    SSOCallbackRequest,
    SSOCallbackResponse,
    SSOProviderResponse,
)
from app.domain.services.sso_services import MockAccountLinkingService, SSOFlowResult, SSOService
from app.infrastructure.config.settings import get_settings as get_app_settings
from app.infrastructure.persistence.repositories.sqlalchemy_sso_repositories import (
    SQLAlchemyIdentityProviderRepository,
    SQLAlchemySSOStateRepository,
)
from app.presentation.api.dependencies.auth import _get_session

sso_router = APIRouter(prefix="/sso", tags=["SSO"])


def get_sso_service(
    session: Annotated[Session, Depends(_get_session)],
    settings: Annotated[Any, Depends(get_app_settings)],
) -> SSOService:
    from app.infrastructure.sso.sso_service import DefaultSSOService

    return DefaultSSOService(
        sso_state_repository=SQLAlchemySSOStateRepository(session),
        identity_provider_repository=SQLAlchemyIdentityProviderRepository(session),
        account_linking=MockAccountLinkingService(),
        state_ttl_seconds=settings.session_ttl_seconds,
    )


@sso_router.get("/providers", response_model=list[SSOProviderResponse])
async def list_providers(
    sso_service: Annotated[SSOService, Depends(get_sso_service)],
    tenant_id: str | None = None,
) -> list[SSOProviderResponse]:
    providers = await sso_service.get_providers(tenant_id)
    return [
        SSOProviderResponse(
            id=str(provider.id),
            name=provider.name,
            provider_type=provider.provider_type.value,
            status=provider.status.value,
            issuer=provider.issuer or None,
            authorization_url=provider.authorization_url or None,
        )
        for provider in providers
    ]


@sso_router.post("/authorize", response_model=SSOAuthorizeResponse)
async def authorize(
    request: SSOAuthorizeRequest,
    settings: Annotated[Any, Depends(get_app_settings)],
    sso_service: Annotated[SSOService, Depends(get_sso_service)],
) -> SSOAuthorizeResponse:
    redirect_uri = "http://localhost:8000/api/v1/sso/callback"
    result = await sso_service.initiate(
        provider_name=request.provider_name,
        tenant_id=None,
        redirect_uri=redirect_uri,
    )
    if result.result != SSOFlowResult.PENDING or not result.authorization_url or not result.state_token:  # noqa: E501
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error or "Failed to initiate SSO flow.",
        )
    return SSOAuthorizeResponse(
        authorization_url=result.authorization_url,
        state_token=result.state_token,
    )


@sso_router.post("/callback", response_model=SSOCallbackResponse)
async def callback(
    request: SSOCallbackRequest,
    session: Annotated[Session, Depends(_get_session)],
    settings: Annotated[Any, Depends(get_app_settings)],
    sso_service: Annotated[SSOService, Depends(get_sso_service)],
) -> SSOCallbackResponse:
    result = await sso_service.handle_callback(
        state_token=request.state_token,
        code=request.code,
    )
    if result.result != SSOFlowResult.AUTHORIZED or result.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result.error or "SSO authorization failed.",
        )

    from app.application.use_cases.oidc_auth import OIDCAuthUseCase
    from app.domain.repositories.user_repository import UserRepository
    from app.domain.services.identity_services import SessionService
    from app.infrastructure.persistence.repositories.sqlalchemy_user_repository import (
        SQLAlchemyUserRepository,
    )
    from app.infrastructure.security.jwt_token_service import JWTTokenService

    user_repository: UserRepository = SQLAlchemyUserRepository(session)
    token_service = JWTTokenService(
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expire_minutes=settings.jwt_access_token_expire_minutes,
        clock_skew_seconds=settings.jwt_clock_skew_seconds,
    )

    session_service: SessionService | None = None
    if settings.refresh_token_enabled:
        from app.infrastructure.persistence.repositories.sqlalchemy_session_repository import (
            SQLAlchemySessionService,
        )
        session_service = SQLAlchemySessionService(session)

    from app.infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher
    use_case = OIDCAuthUseCase(
        user_repository=user_repository,
        token_service=token_service,
        session_service=session_service,
        password_hasher=BcryptPasswordHasher(),
        account_linking=MockAccountLinkingService(),
    )

    tokens = await use_case.handle_callback(result)
    return SSOCallbackResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token"),
        token_type=tokens.get("token_type", "bearer"),
    )
