from datetime import UTC, datetime

from app.application.interfaces.token_service import TokenService
from app.domain.exceptions.domain_errors import (
    AccountLockedError,
    AuthenticationError,
    InactiveUserError,
)
from app.domain.repositories.user_repository import UserRepository
from app.domain.services.identity_services import SessionService


class RefreshTokenUseCase:
    def __init__(
        self,
        user_repository: UserRepository,
        token_service: TokenService,
        session_service: SessionService,
        session_ttl_seconds: int = 604800,
    ) -> None:
        self._user_repository = user_repository
        self._token_service = token_service
        self._session_service = session_service
        self._session_ttl_seconds = session_ttl_seconds

    async def execute(self, refresh_token: str) -> dict[str, str]:
        user_id = await self._session_service.validate_session(refresh_token)
        if user_id is None:
            raise AuthenticationError("Invalid or expired refresh token.")

        user = await self._user_repository.get_by_id(user_id)
        if user is None or not user.is_active:
            raise InactiveUserError("User account is inactive.")

        if user.locked_until is not None:
            locked_until = user.locked_until
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=UTC)
            if datetime.now(UTC) < locked_until:
                raise AccountLockedError("Account is locked.")

        await self._session_service.revoke_session(refresh_token, user_id=user_id)

        new_session_id, _ = await self._session_service.create_session(
            user_id=user.id,
            ttl_seconds=self._session_ttl_seconds,
        )

        access_token = self._token_service.create_access_token(
            user_id=user.id,
            email=user.email,
            session_id=new_session_id,
        )
        return {
            "access_token": access_token,
            "refresh_token": new_session_id,
            "token_type": "bearer",
        }
