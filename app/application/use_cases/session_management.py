from typing import Any
from uuid import UUID

from app.domain.exceptions.domain_errors import AuthenticationError
from app.domain.repositories.user_repository import UserRepository
from app.domain.services.identity_services import SessionService


class CreateSessionUseCase:
    def __init__(
        self,
        user_repository: UserRepository,
        session_service: SessionService,
        token_service: Any,
        session_ttl_seconds: int = 604800,
    ) -> None:
        self._user_repository = user_repository
        self._session_service = session_service
        self._token_service = token_service
        self._session_ttl_seconds = session_ttl_seconds

    async def execute(
        self,
        user_id: UUID,
        *,
        device_info: str | None = None,
        ip_address: str | None = None,
    ) -> dict[str, str]:
        user = await self._user_repository.get_by_id(user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("User not found or inactive.")

        session_id, expires_at = await self._session_service.create_session(
            user_id=user_id,
            device_info=device_info,
            ip_address=ip_address,
            ttl_seconds=self._session_ttl_seconds,
        )
        return {
            "session_id": session_id,
            "expires_at": expires_at.isoformat(),
        }


class RevokeSessionUseCase:
    def __init__(
        self,
        user_repository: UserRepository,
        session_service: SessionService,
    ) -> None:
        self._user_repository = user_repository
        self._session_service = session_service

    async def execute(self, user_id: UUID, session_id: str) -> None:
        user = await self._user_repository.get_by_id(user_id)
        if user is None:
            raise AuthenticationError("User not found.")
        revoked = await self._session_service.revoke_session(session_id, user_id=user_id)
        if not revoked:
            raise AuthenticationError("Session not found or does not belong to user.")


class ListSessionsUseCase:
    def __init__(
        self,
        user_repository: UserRepository,
        session_service: SessionService,
    ) -> None:
        self._user_repository = user_repository
        self._session_service = session_service

    async def execute(self, user_id: UUID) -> list[dict[str, str]]:
        user = await self._user_repository.get_by_id(user_id)
        if user is None:
            raise AuthenticationError("User not found.")
        return await self._session_service.get_active_sessions(user_id)
