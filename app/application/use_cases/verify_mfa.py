from uuid import UUID

from app.application.dto.mfa import MFAResponse
from app.domain.entities.user_mfa import UserMFA
from app.domain.exceptions.domain_errors import AuthenticationError
from app.domain.services.identity_services import MFAService


class VerifyMFAUseCase:
    def __init__(self, mfa_service: MFAService) -> None:
        self._mfa_service = mfa_service

    async def execute(self, user_id: UUID, code: str) -> MFAResponse:
        valid = await self._mfa_service.verify(user_id, code)
        if not valid:
            raise AuthenticationError("Invalid MFA code.")
        return MFAResponse(is_enabled=True)


class ConfirmMFAUseCase:
    def __init__(self, mfa_service: MFAService) -> None:
        self._mfa_service = mfa_service

    async def execute(self, user_id: UUID, code: str) -> MFAResponse:
        mfa: UserMFA = await self._mfa_service.confirm(user_id, code)
        return MFAResponse(
            is_enabled=mfa.is_enabled,
            confirmed_at=mfa.confirmed_at.isoformat() if mfa.confirmed_at else None,
        )
