import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select

from app.domain.entities.password_reset_token import PasswordResetToken
from app.domain.repositories.reset_repository import PasswordResetRepository
from app.infrastructure.persistence.models.identity_models import PasswordResetTokenModel

logger = logging.getLogger(__name__)


class SQLAlchemyPasswordResetRepository(PasswordResetRepository):
    def __init__(self, session: Any) -> None:
        self._session = session

    async def create(self, token: PasswordResetToken) -> PasswordResetToken:
        model = PasswordResetTokenModel(
            id=token.id,
            user_id=token.user_id,
            token_hash=token.token_hash,
            expires_at=token.expires_at,
            used=token.used,
            created_at=token.created_at,
            used_at=token.used_at,
        )
        self._session.add(model)
        self._session.flush()
        return self._to_entity(model)

    async def get_by_token_hash(self, token_hash: str) -> PasswordResetToken | None:
        model = self._session.scalar(
            select(PasswordResetTokenModel).where(
                PasswordResetTokenModel.token_hash == token_hash
            )
        )
        if model is None:
            return None
        return self._to_entity(model)

    async def mark_used(self, token_id: UUID, used_at: datetime) -> PasswordResetToken | None:
        model = self._session.scalar(
            select(PasswordResetTokenModel).where(PasswordResetTokenModel.id == token_id)
        )
        if model is None:
            return None
        model.used = True
        model.used_at = used_at
        self._session.flush()
        return self._to_entity(model)

    async def delete_expired(self, before: datetime) -> int:
        result = self._session.execute(
            delete(PasswordResetTokenModel).where(
                PasswordResetTokenModel.expires_at < before
            )
        )
        self._session.flush()
        return result.rowcount or 0

    @staticmethod
    def _to_entity(model: PasswordResetTokenModel) -> PasswordResetToken:
        return PasswordResetToken(
            id=model.id,
            user_id=model.user_id,
            token_hash=model.token_hash,
            expires_at=model.expires_at,
            used=model.used,
            created_at=model.created_at,
            used_at=model.used_at,
        )
