import hashlib

from app.application.interfaces.password_hasher import PasswordHasher
from app.domain.exceptions.domain_errors import AuthenticationError
from app.domain.repositories.user_repository import UserRepository
from app.domain.services.identity_services import PasswordResetService


class RequestPasswordResetUseCase:
    def __init__(
        self,
        user_repository: UserRepository,
        reset_service: PasswordResetService,
        token_ttl_seconds: int = 3600,
    ) -> None:
        self._user_repository = user_repository
        self._reset_service = reset_service
        self._token_ttl_seconds = token_ttl_seconds

    async def execute(self, email: str) -> str:
        user = await self._user_repository.get_by_email(email)
        if user is None:
            return "If the account exists, a password reset link has been sent."
        token = await self._reset_service.create_token(user.id, self._token_ttl_seconds)
        return token


class ConfirmPasswordResetUseCase:
    def __init__(
        self,
        user_repository: UserRepository,
        reset_service: PasswordResetService,
        password_hasher: PasswordHasher,
    ) -> None:
        self._user_repository = user_repository
        self._reset_service = reset_service
        self._password_hasher = password_hasher

    async def execute(self, token: str, new_password: str) -> None:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        user_id = await self._reset_service.validate_token(token_hash)
        if user_id is None:
            raise AuthenticationError("Invalid or expired password reset token.")

        user = await self._user_repository.get_by_id(user_id)
        if user is None:
            raise AuthenticationError("User not found.")

        hashed = self._password_hasher.hash(new_password)
        await self._user_repository.update_password(user.id, hashed)
        await self._reset_service.mark_consumed(token_hash)
