import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.domain.entities.user_mfa import UserMFA
from app.domain.repositories.session_repository import MFARepository
from app.infrastructure.persistence.models.identity_models import UserMFAModel

logger = logging.getLogger(__name__)


class SQLAlchemyMFARepository(MFARepository):
    def __init__(self, session: Any) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: UUID) -> UserMFA | None:
        model = self._session.scalar(
            select(UserMFAModel).where(UserMFAModel.user_id == user_id)
        )
        if model is None:
            return None
        return UserMFA(
            user_id=model.user_id,
            secret=model.secret,
            backup_codes=model.backup_codes.split(","),
            is_enabled=model.is_enabled,
            confirmed_at=model.confirmed_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def save(self, mfa: UserMFA) -> UserMFA:
        model = self._session.scalar(
            select(UserMFAModel).where(UserMFAModel.user_id == mfa.user_id)
        )
        if model is None:
            model = UserMFAModel(user_id=mfa.user_id)
            self._session.add(model)
        model.secret = mfa.secret
        model.backup_codes = ",".join(mfa.backup_codes)
        model.is_enabled = mfa.is_enabled
        model.confirmed_at = mfa.confirmed_at
        model.created_at = mfa.created_at
        model.updated_at = mfa.updated_at
        self._session.flush()
        return UserMFA(
            user_id=model.user_id,
            secret=model.secret,
            backup_codes=model.backup_codes.split(","),
            is_enabled=model.is_enabled,
            confirmed_at=model.confirmed_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def delete(self, user_id: UUID) -> None:
        model = self._session.scalar(
            select(UserMFAModel).where(UserMFAModel.user_id == user_id)
        )
        if model is not None:
            self._session.delete(model)
            self._session.flush()
