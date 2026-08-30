from typing import Any

from app.application.interfaces.password_hasher import PasswordHasher
from app.application.interfaces.token_service import TokenService
from app.domain.exceptions.domain_errors import AuthenticationError
from app.domain.repositories.user_repository import UserRepository
from app.domain.services.identity_services import SessionService
from app.domain.services.sso_services import AccountLinkingService, SSOCallbackResult


class OIDCAuthUseCase:
    def __init__(
        self,
        user_repository: UserRepository,
        token_service: TokenService,
        session_service: SessionService | None,
        password_hasher: PasswordHasher,
        account_linking: AccountLinkingService,
        session_ttl_seconds: int = 604800,
    ) -> None:
        self._user_repository = user_repository
        self._token_service = token_service
        self._session_service = session_service
        self._password_hasher = password_hasher
        self._account_linking = account_linking
        self._session_ttl_seconds = session_ttl_seconds

    async def handle_callback(self, result: SSOCallbackResult) -> dict[str, Any]:
        if result.result != "authorized" or result.user_id is None:
            raise AuthenticationError(result.error or "SSO authorization failed.")

        user = await self._user_repository.get_by_id(result.user_id)
        if user is None:
            raise AuthenticationError("SSO user not found.")

        refresh_token = None
        if self._session_service is not None:
            session_id, _ = await self._session_service.create_session(
                user_id=user.id,
                ttl_seconds=self._session_ttl_seconds,
            )
            refresh_token = session_id

        access_token = self._token_service.create_access_token(
            user_id=user.id,
            email=user.email,
            session_id=refresh_token,
        )
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",  # nosec B105 - standard OAuth2 token_type value
            "user": {
                "id": user.id,
                "email": user.email,
                "is_active": user.is_active,
                "role": user.role,
                "tenant_id": user.tenant_id,
            },
        }
