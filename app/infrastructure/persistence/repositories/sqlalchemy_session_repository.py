import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, select

from app.domain.entities.user_session import UserSession
from app.domain.services.identity_services import SessionService
from app.infrastructure.persistence.models.identity_models import UserSessionModel

logger = logging.getLogger(__name__)


class SQLAlchemySessionService(SessionService):
    def __init__(self, session: Any) -> None:
        self._session = session

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _compare_expires_at(expires_at: datetime, now: datetime) -> bool:
        if expires_at.tzinfo is None:
            return expires_at < now.replace(tzinfo=None)
        return expires_at < now

    async def create_session(
        self,
        user_id: UUID,
        *,
        device_info: str | None = None,
        ip_address: str | None = None,
        ttl_seconds: int,
    ) -> tuple[str, datetime]:
        import secrets

        session_id = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        session = UserSession(
            session_id=session_id,
            user_id=user_id,
            device_info=device_info,
            ip_address=ip_address,
            created_at=datetime.now(UTC),
            last_used_at=datetime.now(UTC),
            expires_at=expires_at,
        )
        model = UserSessionModel(
            session_id=session.session_id,
            user_id=session.user_id,
            device_info=session.device_info,
            ip_address=session.ip_address,
            created_at=session.created_at,
            last_used_at=session.last_used_at,
            expires_at=session.expires_at,
        )
        self._session.add(model)
        self._session.flush()
        return session_id, expires_at

    async def validate_session(self, session_id: str) -> UUID | None:
        model = self._session.scalar(
            select(UserSessionModel).where(UserSessionModel.session_id == session_id)
        )
        now = self._utcnow()
        if model is None or model.revoked or self._compare_expires_at(model.expires_at, now):
            return None
        model.last_used_at = datetime.now(UTC)
        self._session.flush()
        return cast(UUID, model.user_id)

    async def is_session_active(self, session_id: str) -> bool:
        model = self._session.scalar(
            select(UserSessionModel).where(UserSessionModel.session_id == session_id)
        )
        now = self._utcnow()
        return not (
            model is None
            or model.revoked
            or self._compare_expires_at(model.expires_at, now)
        )

    async def revoke_session(self, session_id: str, *, user_id: UUID | None = None) -> bool:
        model = self._session.scalar(
            select(UserSessionModel).where(UserSessionModel.session_id == session_id)
        )
        if model is None:
            return False
        if user_id is not None and model.user_id != user_id:
            return False
        model.revoked = True
        model.revoked_at = datetime.now(UTC)
        self._session.flush()
        return True

    async def revoke_all_sessions(self, user_id: UUID) -> int:
        models = self._session.scalars(
            select(UserSessionModel).where(UserSessionModel.user_id == user_id)
        ).all()
        now = datetime.now(UTC)
        for model in models:
            if not model.revoked:
                model.revoked = True
                model.revoked_at = now
        self._session.flush()
        return len(models)

    async def get_active_sessions(self, user_id: UUID) -> list[dict[str, str]]:
        models = self._session.scalars(
            select(UserSessionModel).where(UserSessionModel.user_id == user_id)
        ).all()
        now = self._utcnow()
        result = []
        for model in models:
            if model.revoked or self._compare_expires_at(model.expires_at, now):
                continue
            result.append(
                {
                    "session_id": model.session_id,
                    "device_info": model.device_info or "",
                    "ip_address": model.ip_address or "",
                    "created_at": model.created_at.isoformat(),
                    "last_used_at": model.last_used_at.isoformat(),
                    "expires_at": model.expires_at.isoformat(),
                }
            )
        return result

    async def touch_session(self, session_id: str) -> None:
        model = self._session.scalar(
            select(UserSessionModel).where(UserSessionModel.session_id == session_id)
        )
        if model is not None and not model.revoked:
            model.last_used_at = datetime.now(UTC)
            self._session.flush()

    async def cleanup_expired(self) -> int:
        now = self._utcnow()
        result = self._session.execute(
            delete(UserSessionModel).where(UserSessionModel.expires_at < now)
        )
        self._session.flush()
        return result.rowcount if result.rowcount is not None else 0
