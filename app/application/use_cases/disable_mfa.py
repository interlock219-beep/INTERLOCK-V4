from uuid import UUID

from app.domain.exceptions.domain_errors import AuthenticationError
from app.domain.repositories.user_repository import UserRepository
from app.domain.services.identity_services import MFAService


class DisableMFAUseCase:
    def __init__(
        self,
        user_repository: UserRepository,
        mfa_service: MFAService,
    ) -> None:
        self._user_repository = user_repository
        self._mfa_service = mfa_service

    async def execute(self, user_id: UUID, code: str) -> None:
        user = await self._user_repository.get_by_id(user_id)
        if user is None:
            raise AuthenticationError("User not found.")
        await self._mfa_service.disable(user_id, code)
