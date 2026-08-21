from datetime import UTC, datetime, timedelta

from app.application.dto.auth import AuthResponse, LoginRequest, UserResponse
from app.application.interfaces.password_hasher import PasswordHasher
from app.application.interfaces.token_service import TokenService
from app.domain.exceptions.domain_errors import (
    AccountLockedError,
    AuthenticationError,
    InactiveUserError,
)
from app.domain.repositories.user_repository import UserRepository
from app.domain.value_objects.email_address import EmailAddress


class AuthenticateUserUseCase:
    """Authenticate a user and issue an access token."""

    def __init__(
        self,
        user_repository: UserRepository,
        password_hasher: PasswordHasher,
        token_service: TokenService,
        lockout_threshold: int = 5,
        lockout_duration_minutes: int = 15,
    ) -> None:
        self._user_repository = user_repository
        self._password_hasher = password_hasher
        self._token_service = token_service
        self._lockout_threshold = lockout_threshold
        self._lockout_duration = timedelta(minutes=lockout_duration_minutes)

    async def execute(self, request: LoginRequest) -> AuthResponse:
        email = str(EmailAddress(str(request.email)))
        user = await self._user_repository.get_by_email(email)

        if user is None or not self._password_hasher.verify(request.password, user.hashed_password):
            if user is not None:
                updated = await self._user_repository.increment_failed_login(user.id)
                if updated is not None:
                    user = updated
                    if user.failed_login_attempts >= self._lockout_threshold:
                        lockout_until = datetime.now(tz=UTC) + self._lockout_duration
                        user = await self._user_repository.lock_account(user.id, lockout_until)
            raise AuthenticationError("Invalid email or password.")

        if not user.is_active:
            raise InactiveUserError("User account is inactive.")

        if user.locked_until is not None:
            locked_until = user.locked_until
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=UTC)
            if datetime.now(tz=UTC) < locked_until:
                raise AccountLockedError(
                    "Account is locked due to multiple failed login attempts. "
                    "Try again later."
                )

        reset_user = await self._user_repository.reset_failed_login(user.id)
        if reset_user is None:
            raise AuthenticationError("Invalid email or password.")
        user = reset_user

        access_token = self._token_service.create_access_token(
            user_id=user.id,
            email=user.email,
        )
        return AuthResponse(
            access_token=access_token,
            user=UserResponse(
                id=user.id,
                email=user.email,
                is_active=user.is_active,
                role=user.role,
                tenant_id=user.tenant_id,
            ),
        )
