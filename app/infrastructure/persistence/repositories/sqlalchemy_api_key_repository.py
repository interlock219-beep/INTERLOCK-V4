from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select

from app.domain.entities.api_key import ApiKey
from app.domain.repositories.api_key_repository import ApiKeyRepository
from app.infrastructure.persistence.models.api_key_model import ApiKeyModel


class SQLAlchemyApiKeyRepository(ApiKeyRepository):
    def __init__(self, session) -> None:
        self._session = session

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC)

    def _to_entity(self, model: ApiKeyModel) -> ApiKey:
        return ApiKey(
            id=model.id,
            key_id=model.key_id,
            key_hash=model.key_hash,
            user_id=model.user_id,
            tenant_id=model.tenant_id,
            name=model.name,
            expires_at=model.expires_at if model.expires_at.tzinfo is not None else model.expires_at.replace(tzinfo=UTC),
            created_at=model.created_at if model.created_at.tzinfo is not None else model.created_at.replace(tzinfo=UTC),
            last_used_at=model.last_used_at if model.last_used_at is None or model.last_used_at.tzinfo is not None else model.last_used_at.replace(tzinfo=UTC),
            revoked=model.revoked,
            revoked_at=model.revoked_at if model.revoked_at is None or model.revoked_at.tzinfo is not None else model.revoked_at.replace(tzinfo=UTC) if model.revoked_at is not None else None,
        )

    async def create(self, api_key: ApiKey) -> ApiKey:
        model = ApiKeyModel(
            id=api_key.id,
            key_id=api_key.key_id,
            key_hash=api_key.key_hash,
            user_id=api_key.user_id,
            tenant_id=api_key.tenant_id,
            name=api_key.name,
            expires_at=api_key.expires_at,
            created_at=api_key.created_at,
            last_used_at=api_key.last_used_at,
            revoked=api_key.revoked,
            revoked_at=api_key.revoked_at,
        )
        self._session.add(model)
        self._session.flush()
        return self._to_entity(model)

    async def get_by_key_hash(self, key_hash: str) -> ApiKey | None:
        model = self._session.scalar(
            select(ApiKeyModel).where(ApiKeyModel.key_hash == key_hash)
        )
        if model is None:
            return None
        return self._to_entity(model)

    async def get_by_key_id(self, key_id: str) -> ApiKey | None:
        model = self._session.scalar(
            select(ApiKeyModel).where(ApiKeyModel.key_id == key_id)
        )
        if model is None:
            return None
        return self._to_entity(model)

    async def get_by_user_id(self, user_id: UUID) -> list[ApiKey]:
        models = self._session.scalars(
            select(ApiKeyModel).where(ApiKeyModel.user_id == user_id)
        ).all()
        return [self._to_entity(m) for m in models]

    async def revoke(self, key_id: str, *, user_id: UUID | None = None) -> ApiKey | None:
        model = self._session.scalar(
            select(ApiKeyModel).where(ApiKeyModel.key_id == key_id)
        )
        if model is None:
            return None
        if user_id is not None and model.user_id != user_id:
            return None
        model.revoked = True
        model.revoked_at = datetime.now(UTC)
        self._session.flush()
        return self._to_entity(model)

    async def delete_expired(self, before: datetime) -> int:
        result = self._session.execute(
            select(ApiKeyModel).where(ApiKeyModel.expires_at < before)
        )
        models = result.scalars().all()
        count = len(models)
        for model in models:
            self._session.delete(model)
        self._session.flush()
        return count
