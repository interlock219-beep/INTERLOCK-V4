from collections.abc import Generator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.application.dto.api_key import (
    ApiKeyListResponse,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
)
from app.application.use_cases.create_api_key import (
    CreateApiKeyUseCase,
    ListApiKeysUseCase,
    RevokeApiKeyUseCase,
)
from app.domain.exceptions.domain_errors import ApiKeyError, AuthenticationError
from app.infrastructure.persistence.database import SessionLocal
from app.presentation.api.dependencies.auth import CurrentUser, get_user_repository


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


router = APIRouter(prefix="/api-keys", tags=["API Keys"])


def _get_create_use_case(
    user_repository: Annotated[Any, Depends(get_user_repository)],
    session: Annotated[Session, Depends(_get_session)],
) -> CreateApiKeyUseCase:
    from app.infrastructure.persistence.repositories.sqlalchemy_api_key_repository import (
        SQLAlchemyApiKeyRepository,
    )

    return CreateApiKeyUseCase(
        api_key_repository=SQLAlchemyApiKeyRepository(session),
        user_repository=user_repository,
    )


def _get_list_use_case(
    session: Annotated[Session, Depends(_get_session)],
) -> ListApiKeysUseCase:
    from app.infrastructure.persistence.repositories.sqlalchemy_api_key_repository import (
        SQLAlchemyApiKeyRepository,
    )

    return ListApiKeysUseCase(api_key_repository=SQLAlchemyApiKeyRepository(session))


def _get_revoke_use_case(
    user_repository: Annotated[Any, Depends(get_user_repository)],
    session: Annotated[Session, Depends(_get_session)],
) -> RevokeApiKeyUseCase:
    from app.infrastructure.persistence.repositories.sqlalchemy_api_key_repository import (
        SQLAlchemyApiKeyRepository,
    )

    return RevokeApiKeyUseCase(
        api_key_repository=SQLAlchemyApiKeyRepository(session),
        user_repository=user_repository,
    )


@router.post(
    "",
    response_model=CreateApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API key",
    description=(
        "Create a new customer API key with an explicit expiration. "
        "The raw secret is returned only once and must be stored securely."
    ),
)
async def create_api_key(
    request: CreateApiKeyRequest,
    use_case: Annotated[CreateApiKeyUseCase, Depends(_get_create_use_case)],
    current_user: CurrentUser,
) -> CreateApiKeyResponse:
    try:
        return await use_case.execute(current_user.id, request)
    except ApiKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc


@router.get(
    "",
    response_model=ApiKeyListResponse,
    summary="List API keys for the current user",
)
async def list_api_keys(
    use_case: Annotated[ListApiKeysUseCase, Depends(_get_list_use_case)],
    current_user: CurrentUser,
) -> ApiKeyListResponse:
    keys = await use_case.execute(current_user.id)
    return ApiKeyListResponse(api_keys=keys)


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API key",
)
async def revoke_api_key(
    key_id: str,
    use_case: Annotated[RevokeApiKeyUseCase, Depends(_get_revoke_use_case)],
    current_user: CurrentUser,
) -> None:
    result = await use_case.execute(key_id, current_user.id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found.",
        )
