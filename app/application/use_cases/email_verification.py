import hashlib

from app.domain.exceptions.domain_errors import AuthenticationError
from app.domain.repositories.user_repository import UserRepository
from app.domain.services.identity_services import EmailVerificationService


class RequestEmailVerificationUseCase:
    def __init__(
        self,
        user_repository: UserRepository,
        verification_service: EmailVerificationService,
        token_ttl_seconds: int = 86400,
    ) -> None:
        self._user_repository = user_repository
        self._verification_service = verification_service
        self._token_ttl_seconds = token_ttl_seconds

    async def execute(self, email: str) -> str:
        user = await self._user_repository.get_by_email(email)
        if user is None:
            raise AuthenticationError("User not found.")
        token = await self._verification_service.create_token(user.id, self._token_ttl_seconds)
        return token


class ConfirmEmailVerificationUseCase:
    def __init__(
        self,
        user_repository: UserRepository,
        verification_service: EmailVerificationService,
    ) -> None:
        self._user_repository = user_repository
        self._verification_service = verification_service

    async def execute(self, token: str) -> None:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        user_id = await self._verification_service.validate_token(token_hash)
        if user_id is None:
            raise AuthenticationError("Invalid or expired verification token.")
        await self._verification_service.mark_consumed(token_hash)
