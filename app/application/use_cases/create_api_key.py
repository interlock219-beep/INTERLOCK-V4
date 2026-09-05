from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from uuid import UUID, uuid4

from app.application.dto.api_key import ApiKeyResponse, CreateApiKeyRequest, CreateApiKeyResponse
from app.domain.entities.api_key import ApiKey
from app.domain.exceptions.domain_errors import (
    ApiKeyError,
    AuthenticationError,
)
from app.domain.repositories.api_key_repository import ApiKeyRepository
from app.domain.repositories.user_repository import UserRepository


class CreateApiKeyUseCase:
    """Create a new API key credential with expiration."""

    def __init__(
        self,
        api_key_repository: ApiKeyRepository,
        user_repository: UserRepository,
    ) -> None:
        self._api_key_repository = api_key_repository
        self._user_repository = user_repository

    async def execute(self, user_id: UUID, request: CreateApiKeyRequest) -> CreateApiKeyResponse:
        user = await self._user_repository.get_by_id(user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("User is inactive or missing.")

        if request.expires_at and request.expires_in_days:
            raise ApiKeyError("Provide either expires_at or expires_in_days, not both.")
        if not request.expires_at and not request.expires_in_days:
            raise ApiKeyError("expires_at or expires_in_days is required.")

        if request.expires_at:
            expires_at = request.expires_at
        else:
            assert request.expires_in_days is not None
            expires_at = datetime.now(UTC) + timedelta(days=request.expires_in_days)

        now = datetime.now(UTC)
        if expires_at <= now:
            raise ApiKeyError("Expiration must be in the future.")

        raw_secret = "ik_" + token_urlsafe(32)
        key_hash = _hash_secret(raw_secret)
        key_id = "key_" + key_hash[:8]

        api_key = ApiKey(
            id=uuid4(),
            key_id=key_id,
            key_hash=key_hash,
            user_id=user.id,
            tenant_id=user.tenant_id,
            name=request.name,
            expires_at=expires_at,
            created_at=now,
        )

        saved = await self._api_key_repository.create(api_key)

        return CreateApiKeyResponse(
            api_key=ApiKeyResponse(
                key_id=saved.key_id,
                name=saved.name,
                expires_at=saved.expires_at,
                created_at=saved.created_at,
                last_used_at=saved.last_used_at,
                revoked=saved.revoked,
                revoked_at=saved.revoked_at,
            ),
            raw_secret=raw_secret,
        )


class ListApiKeysUseCase:
    """List active API keys for a user."""

    def __init__(self, api_key_repository: ApiKeyRepository) -> None:
        self._api_key_repository = api_key_repository

    async def execute(self, user_id: UUID) -> list[ApiKeyResponse]:
        keys = await self._api_key_repository.get_by_user_id(user_id)
        return [
            ApiKeyResponse(
                key_id=k.key_id,
                name=k.name,
                expires_at=k.expires_at,
                created_at=k.created_at,
                last_used_at=k.last_used_at,
                revoked=k.revoked,
                revoked_at=k.revoked_at,
            )
            for k in keys
        ]


class RevokeApiKeyUseCase:
    """Revoke an API key by its key_id."""

    def __init__(
        self,
        api_key_repository: ApiKeyRepository,
        user_repository: UserRepository,
    ) -> None:
        self._api_key_repository = api_key_repository
        self._user_repository = user_repository

    async def execute(self, key_id: str, user_id: UUID) -> ApiKeyResponse | None:
        existing = await self._api_key_repository.get_by_key_id(key_id)
        if existing is None or existing.user_id != user_id:
            return None

        user = await self._user_repository.get_by_id(user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("User is inactive or missing.")

        revoked = await self._api_key_repository.revoke(key_id, user_id=user_id)
        if revoked is None:
            return None

        return ApiKeyResponse(
            key_id=revoked.key_id,
            name=revoked.name,
            expires_at=revoked.expires_at,
            created_at=revoked.created_at,
            last_used_at=revoked.last_used_at,
            revoked=revoked.revoked,
            revoked_at=revoked.revoked_at,
        )


def _hash_secret(secret: str) -> str:
    import hashlib

    return hashlib.sha256(secret.encode("utf-8")).hexdigest()
