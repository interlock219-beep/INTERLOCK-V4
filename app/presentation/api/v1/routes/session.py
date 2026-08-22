from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.dto.session import SessionResponse
from app.application.use_cases.session_management import (
    CreateSessionUseCase,
    ListSessionsUseCase,
    RevokeSessionUseCase,
)
from app.domain.exceptions.domain_errors import AuthenticationError
from app.infrastructure.config.settings import get_settings as get_app_settings
from app.presentation.api.dependencies.auth import CurrentUser, get_user_repository
from app.presentation.api.dependencies.security import get_session_service

session_router = APIRouter(prefix="/sessions", tags=["Sessions"])


def _get_create_session_use_case(
    user_repository: Annotated[Any, Depends(get_user_repository)],
    session_service: Annotated[Any, Depends(get_session_service)],
    settings: Annotated[Any, Depends(get_app_settings)],
) -> CreateSessionUseCase:
    from app.infrastructure.security.jwt_token_service import JWTTokenService

    token_service = JWTTokenService(
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expire_minutes=settings.jwt_access_token_expire_minutes,
        clock_skew_seconds=settings.jwt_clock_skew_seconds,
    )
    return CreateSessionUseCase(
        user_repository,
        session_service,
        token_service,
        session_ttl_seconds=settings.session_ttl_seconds,
    )


def _get_revoke_session_use_case(
    user_repository: Annotated[Any, Depends(get_user_repository)],
    session_service: Annotated[Any, Depends(get_session_service)],
) -> RevokeSessionUseCase:
    return RevokeSessionUseCase(user_repository, session_service)


def _get_list_sessions_use_case(
    user_repository: Annotated[Any, Depends(get_user_repository)],
    session_service: Annotated[Any, Depends(get_session_service)],
) -> ListSessionsUseCase:
    return ListSessionsUseCase(user_repository, session_service)


@session_router.post("", response_model=dict[str, str])
async def create_session(
    use_case: Annotated[CreateSessionUseCase, Depends(_get_create_session_use_case)],
    current_user: CurrentUser,
    body: dict[str, str | None] | None = None,
) -> dict[str, str]:
    device_info = (body or {}).get("device_info")
    ip_address = (body or {}).get("ip_address")
    try:
        result = await use_case.execute(
            current_user.id,
            device_info=device_info,
            ip_address=ip_address,
        )
        return {"session_id": result["session_id"], "expires_at": result["expires_at"]}
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@session_router.get("", response_model=list[SessionResponse])
async def list_sessions(
    use_case: Annotated[ListSessionsUseCase, Depends(_get_list_sessions_use_case)],
    current_user: CurrentUser,
) -> list[SessionResponse]:
    try:
        sessions = await use_case.execute(current_user.id)
        return [
            SessionResponse(
                session_id=s["session_id"],
                device_info=s["device_info"],
                ip_address=s["ip_address"],
                created_at=s["created_at"],
                last_used_at=s["last_used_at"],
                expires_at=s["expires_at"],
            )
            for s in sessions
        ]
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@session_router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: str,
    use_case: Annotated[RevokeSessionUseCase, Depends(_get_revoke_session_use_case)],
    current_user: CurrentUser,
) -> None:
    try:
        await use_case.execute(current_user.id, session_id)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
