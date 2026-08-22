import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select

from app.domain.entities.email_verification_token import EmailVerificationToken
from app.domain.repositories.reset_repository import EmailVerificationRepository
from app.infrastructure.persistence.models.identity_models import EmailVerificationTokenModel

logger = logging.getLogger(__name__)


class SQLAlchemyEmailVerificationRepository(EmailVerificationRepository):
    def __init__(self, session: Any) -> None:
        self._session = session

    async def create(self, token: EmailVerificationToken) -> EmailVerificationToken:
        model = EmailVerificationTokenModel(
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

    async def get_by_token_hash(self, token_hash: str) -> EmailVerificationToken | None:
        model = self._session.scalar(
            select(EmailVerificationTokenModel).where(
                EmailVerificationTokenModel.token_hash == token_hash
            )
        )
        if model is None:
            return None
        return self._to_entity(model)

    async def mark_used(self, token_id: UUID, used_at: datetime) -> EmailVerificationToken | None:
        model = self._session.scalar(
            select(EmailVerificationTokenModel).where(EmailVerificationTokenModel.id == token_id)
        )
        if model is None:
            return None
        model.used = True
        model.used_at = used_at
        self._session.flush()
        return self._to_entity(model)

    async def delete_expired(self, before: datetime) -> int:
        result = self._session.execute(
            delete(EmailVerificationTokenModel).where(
                EmailVerificationTokenModel.expires_at < before
            )
        )
        self._session.flush()
        return result.rowcount or 0

    @staticmethod
    def _to_entity(model: EmailVerificationTokenModel) -> EmailVerificationToken:
        return EmailVerificationToken(
            id=model.id,
            user_id=model.user_id,
            token_hash=model.token_hash,
            expires_at=model.expires_at,
            used=model.used,
            created_at=model.created_at,
            used_at=model.used_at,
        )
