from datetime import UTC, datetime
from uuid import uuid4

from app.application.dto.auth import AuthResponse, RegisterRequest, UserResponse
from app.application.interfaces.password_hasher import PasswordHasher
from app.application.interfaces.token_service import TokenService
from app.domain.entities.user import User
from app.domain.exceptions.domain_errors import DuplicateEmailError
from app.domain.repositories.user_repository import UserRepository
from app.domain.services.password_policy import PasswordPolicy
from app.domain.value_objects.email_address import EmailAddress


class RegisterUserUseCase:
    """Register a new user with hashed credentials."""

    def __init__(
        self,
        user_repository: UserRepository,
        password_hasher: PasswordHasher,
        token_service: TokenService,
        password_policy: PasswordPolicy | None = None,
    ) -> None:
        self._user_repository = user_repository
        self._password_hasher = password_hasher
        self._token_service = token_service
        self._password_policy = password_policy or PasswordPolicy()

    async def execute(self, request: RegisterRequest) -> AuthResponse:
        email = str(EmailAddress(str(request.email)))

        if await self._user_repository.exists_by_email(email):
            raise DuplicateEmailError(f"Email already registered: {email}")

        self._password_policy.validate(request.password)

        tenant_id = getattr(request, "tenant_id", None)
        now = datetime.now(tz=UTC)
        user = User(
            id=uuid4(),
            email=email,
            hashed_password=self._password_hasher.hash(request.password),
            is_active=True,
            created_at=now,
            role="viewer",
            tenant_id=tenant_id,
            password_changed_at=now,
        )
        saved_user = await self._user_repository.save(user)

        access_token = self._token_service.create_access_token(
            user_id=saved_user.id,
            email=saved_user.email,
        )
        return AuthResponse(
            access_token=access_token,
            user=UserResponse(
                id=saved_user.id,
                email=saved_user.email,
                is_active=saved_user.is_active,
                role=saved_user.role,
                tenant_id=saved_user.tenant_id,
            ),
        )
