from collections.abc import Generator
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.application.dto.auth import UserResponse
from app.application.interfaces.password_hasher import PasswordHasher
from app.application.interfaces.token_service import TokenService
from app.application.use_cases.authenticate_user import AuthenticateUserUseCase
from app.application.use_cases.get_current_user import GetCurrentUserUseCase
from app.application.use_cases.refresh_token import RefreshTokenUseCase
from app.application.use_cases.register_user import RegisterUserUseCase
from app.domain.exceptions.domain_errors import (
    AccountLockedError,
    ApiKeyExpiredError,
    ApiKeyRevokedError,
    AuthenticationError,
    InactiveUserError,
    UserNotFoundError,
)
from app.domain.repositories.api_key_repository import ApiKeyRepository
from app.domain.repositories.user_repository import UserRepository
from app.domain.services.identity_services import SessionService
from app.domain.services.password_policy import PasswordPolicy
from app.infrastructure.config.settings import Settings, get_settings
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_api_key_repository import (
    SQLAlchemyApiKeyRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_user_repository import (
    SQLAlchemyUserRepository,
)
from app.infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher
from app.infrastructure.security.jwt_token_service import JWTTokenService

_bearer_scheme = HTTPBearer(auto_error=False)


def get_app_settings() -> Settings:
    return get_settings()


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


def get_user_repository(
    session: Annotated[Session, Depends(_get_session)],
) -> UserRepository:
    return SQLAlchemyUserRepository(session)


def get_api_key_repository(
    session: Annotated[Session, Depends(_get_session)],
) -> ApiKeyRepository:
    return SQLAlchemyApiKeyRepository(session)


def get_password_hasher(settings: Annotated[Settings, Depends(get_app_settings)]) -> PasswordHasher:
    return BcryptPasswordHasher(rounds=settings.bcrypt_rounds)


def get_token_service(settings: Annotated[Settings, Depends(get_app_settings)]) -> TokenService:
    return JWTTokenService(
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expire_minutes=settings.jwt_access_token_expire_minutes,
        clock_skew_seconds=settings.jwt_clock_skew_seconds,
    )


def get_register_user_use_case(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
    password_hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> RegisterUserUseCase:
    return RegisterUserUseCase(
        user_repository,
        password_hasher,
        token_service,
        password_policy=PasswordPolicy(
            min_length=settings.password_min_length,
            require_uppercase=settings.password_require_uppercase,
            require_lowercase=settings.password_require_lowercase,
            require_digit=settings.password_require_digit,
            require_special=settings.password_require_special,
        ),
    )


def get_current_user_use_case(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> GetCurrentUserUseCase:
    return GetCurrentUserUseCase(user_repository)


def get_session_service_dependency(
    session: Annotated[Session, Depends(_get_session)],
) -> SessionService:
    from app.infrastructure.persistence.repositories.sqlalchemy_session_repository import (
        SQLAlchemySessionService,
    )
    return SQLAlchemySessionService(session)


def get_authenticate_user_use_case(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
    password_hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    session_service: Annotated[SessionService, Depends(get_session_service_dependency)],
) -> AuthenticateUserUseCase:
    return AuthenticateUserUseCase(
        user_repository,
        password_hasher,
        token_service,
        lockout_threshold=settings.account_lockout_threshold,
        lockout_duration_minutes=settings.account_lockout_duration_minutes,
        session_service=session_service if settings.refresh_token_enabled else None,
        session_ttl_seconds=settings.session_ttl_seconds,
    )


async def _validate_api_key(
    raw_key: str,
    api_key_repository: ApiKeyRepository,
) -> UUID:
    import hashlib

    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    api_key = await api_key_repository.get_by_key_hash(key_hash)

    if api_key is None:
        raise AuthenticationError("Invalid API key.")

    if api_key.revoked:
        raise ApiKeyRevokedError("API key has been revoked.")

    now = datetime.now(UTC)
    expires_at = api_key.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if now >= expires_at:
        raise ApiKeyExpiredError("API credential expired.")

    return api_key.user_id


async def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
    session_service: Annotated[SessionService, Depends(get_session_service_dependency)],
    api_key_repository: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
    x_api_key: Annotated[str | None, Header()] = None,
) -> UUID:
    if credentials is not None and credentials.scheme.lower() == "bearer":
        try:
            payload = token_service.decode_access_token(credentials.credentials)
        except AuthenticationError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        if payload.sid and not await session_service.is_session_active(payload.sid):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has been revoked or expired.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return payload.sub

    if x_api_key is not None:
        try:
            return await _validate_api_key(x_api_key, api_key_repository)
        except (AuthenticationError, ApiKeyExpiredError, ApiKeyRevokedError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid authorization header.",
        headers={"WWW-Authenticate": "Bearer"},
    )


CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]


async def get_current_user(
    user_id: CurrentUserId,
    use_case: Annotated[GetCurrentUserUseCase, Depends(get_current_user_use_case)],
) -> UserResponse:
    try:
        return await use_case.execute(user_id)
    except (UserNotFoundError, InactiveUserError, AccountLockedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


CurrentUser = Annotated[UserResponse, Depends(get_current_user)]


def get_refresh_token_use_case(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    session: Annotated[Session, Depends(_get_session)],
) -> RefreshTokenUseCase:
    from app.infrastructure.persistence.repositories.sqlalchemy_session_repository import (
        SQLAlchemySessionService,
    )
    session_service = SQLAlchemySessionService(session)
    return RefreshTokenUseCase(
        user_repository,
        token_service,
        session_service,
        session_ttl_seconds=settings.session_ttl_seconds,
    )


def require_hitl_approver(
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> UserResponse:
    """Ensure the authenticated user holds an HITL approver role.

    Returns the current user when authorized.
    Raises 403 when the user's role is not in the configured approver set.
    """
    if current_user.role not in settings.hitl_approver_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to approve or reject HITL requests.",
        )
    return current_user


def require_recovery_executor(
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> UserResponse:
    """Ensure the authenticated user is authorized to execute recovery plans.

    Returns the current user when authorized.
    Raises 403 when the user's role is not in the configured recovery executor set.
    """
    recovery_roles = getattr(settings, "recovery_executor_roles", ["admin", "operator"])
    if current_user.role not in recovery_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to execute recovery plans.",
        )
    return current_user


def get_user_tenant_id(current_user: CurrentUser) -> str:
    """Return the current user's tenant ID, enforcing tenant assignment.

    Raises 403 if the user has no tenant assignment to prevent cross-tenant access.
    When authorization_require_tenant is disabled, returns an empty string instead
    so that repository queries return no rows rather than raising.
    """
    if not current_user.tenant_id:
        settings = get_settings()
        if not settings.authorization_require_tenant:
            return ""
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant assignment required for this operation.",
        )
    return current_user.tenant_id




