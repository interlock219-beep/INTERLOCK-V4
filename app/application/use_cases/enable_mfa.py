from datetime import UTC, datetime
from uuid import UUID

from app.application.dto.mfa import MFAEnableResponse
from app.domain.exceptions.domain_errors import (
    AccountLockedError,
    AuthenticationError,
    InactiveUserError,
)
from app.domain.repositories.user_repository import UserRepository
from app.domain.services.identity_services import MFAService


class EnableMFAUseCase:
    def __init__(
        self,
        user_repository: UserRepository,
        mfa_service: MFAService,
    ) -> None:
        self._user_repository = user_repository
        self._mfa_service = mfa_service

    async def execute(self, user_id: UUID) -> MFAEnableResponse:
        user = await self._user_repository.get_by_id(user_id)
        if user is None:
            raise AuthenticationError("User not found.")
        if not user.is_active:
            raise InactiveUserError("User account is inactive.")
        if user.locked_until is not None:
            locked_until = user.locked_until
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=UTC)
            if datetime.now(UTC) < locked_until:
                raise AccountLockedError("Account is locked.")

        response = await self._mfa_service.setup(user_id)
        if response.result.value == "already_enabled":
            raise AuthenticationError("MFA is already enabled.")

        return MFAEnableResponse(
            secret=response.secret or "",
            provisioning_uri=response.provisioning_uri or "",
            backup_codes=response.backup_codes or [],
        )
