from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.dto.mfa import MFAEnableResponse, MFAResponse
from app.application.dto.password_reset import (
    EmailVerificationConfirm,
    EmailVerificationRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
)
from app.application.use_cases.disable_mfa import DisableMFAUseCase
from app.application.use_cases.email_verification import (
    ConfirmEmailVerificationUseCase,
    RequestEmailVerificationUseCase,
)
from app.application.use_cases.enable_mfa import EnableMFAUseCase
from app.application.use_cases.password_reset import (
    ConfirmPasswordResetUseCase,
    RequestPasswordResetUseCase,
)
from app.application.use_cases.verify_mfa import ConfirmMFAUseCase, VerifyMFAUseCase
from app.domain.exceptions.domain_errors import AuthenticationError
from app.domain.services.identity_services import MFAService
from app.presentation.api.dependencies.auth import (
    CurrentUser,
    get_password_hasher,
    get_user_repository,
)
from app.presentation.api.dependencies.security import (
    get_email_verification_service,
    get_mfa_service,
    get_password_reset_service,
)

mfa_router = APIRouter(prefix="/mfa", tags=["MFA"])


def _get_enable_mfa(
    user_repository: Annotated[Any, Depends(get_user_repository)],
    mfa_service: Annotated[Any, Depends(get_mfa_service)],
) -> EnableMFAUseCase:
    return EnableMFAUseCase(user_repository, mfa_service)


def _get_verify_mfa(
    mfa_service: Annotated[Any, Depends(get_mfa_service)],
) -> VerifyMFAUseCase:
    return VerifyMFAUseCase(mfa_service)


def _get_confirm_mfa(
    mfa_service: Annotated[Any, Depends(get_mfa_service)],
) -> ConfirmMFAUseCase:
    return ConfirmMFAUseCase(mfa_service)


def _get_disable_mfa(
    user_repository: Annotated[Any, Depends(get_user_repository)],
    mfa_service: Annotated[Any, Depends(get_mfa_service)],
) -> DisableMFAUseCase:
    return DisableMFAUseCase(user_repository, mfa_service)


def _get_request_password_reset(
    user_repository: Annotated[Any, Depends(get_user_repository)],
    password_reset_service: Annotated[Any, Depends(get_password_reset_service)],
) -> RequestPasswordResetUseCase:
    settings = __import__(
        "app.infrastructure.config.settings",
        fromlist=["get_settings"],
    ).get_settings()
    return RequestPasswordResetUseCase(
        user_repository,
        password_reset_service,
        token_ttl_seconds=settings.password_reset_token_ttl_seconds,
    )


def _get_confirm_password_reset(
    user_repository: Annotated[Any, Depends(get_user_repository)],
    password_reset_service: Annotated[Any, Depends(get_password_reset_service)],
    password_hasher: Annotated[Any, Depends(get_password_hasher)],
) -> ConfirmPasswordResetUseCase:
    return ConfirmPasswordResetUseCase(
        user_repository,
        password_reset_service,
        password_hasher,
    )


def _get_request_email_verification(
    user_repository: Annotated[Any, Depends(get_user_repository)],
    email_verification_service: Annotated[Any, Depends(get_email_verification_service)],
) -> RequestEmailVerificationUseCase:
    settings = __import__(
        "app.infrastructure.config.settings",
        fromlist=["get_settings"],
    ).get_settings()
    return RequestEmailVerificationUseCase(
        user_repository,
        email_verification_service,
        token_ttl_seconds=settings.email_verification_token_ttl_seconds,
    )


def _get_confirm_email_verification(
    user_repository: Annotated[Any, Depends(get_user_repository)],
    email_verification_service: Annotated[Any, Depends(get_email_verification_service)],
) -> ConfirmEmailVerificationUseCase:
    return ConfirmEmailVerificationUseCase(user_repository, email_verification_service)


@mfa_router.post("/enable", response_model=MFAEnableResponse, status_code=status.HTTP_201_CREATED)
async def enable_mfa(
    use_case: Annotated[EnableMFAUseCase, Depends(_get_enable_mfa)],
    current_user: CurrentUser,
) -> MFAEnableResponse:
    try:
        return await use_case.execute(current_user.id)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@mfa_router.post("/confirm", response_model=MFAResponse)
async def confirm_mfa(
    body: dict[str, str],
    use_case: Annotated[ConfirmMFAUseCase, Depends(_get_confirm_mfa)],
    current_user: CurrentUser,
) -> MFAResponse:
    code = body.get("code", "")
    if not code:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Code is required.",
        )
    try:
        return await use_case.execute(current_user.id, code)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@mfa_router.post("/verify", response_model=MFAResponse)
async def verify_mfa(
    body: dict[str, str],
    use_case: Annotated[VerifyMFAUseCase, Depends(_get_verify_mfa)],
    current_user: CurrentUser,
) -> MFAResponse:
    code = body.get("code", "")
    if not code:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Code is required.",
        )
    try:
        return await use_case.execute(current_user.id, code)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@mfa_router.post("/disable", status_code=status.HTTP_204_NO_CONTENT)
async def disable_mfa(
    body: dict[str, str | None],
    use_case: Annotated[DisableMFAUseCase, Depends(_get_disable_mfa)],
    current_user: CurrentUser,
) -> None:
    code = body.get("code")
    if not code:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="MFA code is required to disable MFA.",
        )
    try:
        await use_case.execute(current_user.id, code)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@mfa_router.post("/backup-codes/regenerate", response_model=list[str])
async def regenerate_backup_codes(
    mfa_service: Annotated[MFAService, Depends(get_mfa_service)],
    current_user: CurrentUser,
) -> list[str]:
    try:
        return await mfa_service.regenerate_backup_codes(current_user.id)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


password_router = APIRouter(prefix="/password", tags=["Password"])


@password_router.post("/reset/request")
async def request_password_reset(
    body: PasswordResetRequest,
    use_case: Annotated[RequestPasswordResetUseCase, Depends(_get_request_password_reset)],
) -> dict[str, str]:
    await use_case.execute(body.email)
    return {"message": "If the account exists, a password reset link has been sent."}


@password_router.post("/reset/confirm")
async def confirm_password_reset(
    body: PasswordResetConfirm,
    use_case: Annotated[ConfirmPasswordResetUseCase, Depends(_get_confirm_password_reset)],
) -> dict[str, str]:
    try:
        await use_case.execute(body.token, body.new_password)
        return {"message": "Password reset successful."}
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


email_router = APIRouter(prefix="/email", tags=["Email"])


@email_router.post("/verify/request")
async def request_email_verification(
    body: EmailVerificationRequest,
    use_case: Annotated[RequestEmailVerificationUseCase, Depends(_get_request_email_verification)],
) -> dict[str, str]:
    await use_case.execute(body.email)
    return {"message": "If the account exists, a verification email has been sent."}


@email_router.post("/verify/confirm")
async def confirm_email_verification(
    body: EmailVerificationConfirm,
    use_case: Annotated[ConfirmEmailVerificationUseCase, Depends(_get_confirm_email_verification)],
) -> dict[str, str]:
    try:
        await use_case.execute(body.token)
        return {"message": "Email verified successfully."}
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
