from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.application.use_cases.enable_mfa import EnableMFAUseCase
from app.domain.exceptions.domain_errors import (
    AccountLockedError,
    AuthenticationError,
    InactiveUserError,
)
from app.domain.services.identity_services import MFASetupResponse, MFASetupResult


class StubUserRepository:
    def __init__(self, user=None, locked_until=None) -> None:
        self._user = user
        self._locked_until = locked_until

    async def get_by_id(self, user_id):
        if self._user is None:
            return None
        user = self._user
        user.locked_until = self._locked_until
        return user


class StubMFAService:
    def __init__(self, result=MFASetupResult.CREATED) -> None:
        self._result = result
        self.setup_called = False

    async def setup(self, user_id: UUID):
        self.setup_called = True
        return MFASetupResponse(
            result=self._result,
            secret="secret-123",
            provisioning_uri="otpauth://...",
            backup_codes=["code1", "code2"],
        )


@pytest.mark.asyncio
async def test_enable_mfa_success() -> None:
    user_id = uuid4()
    user = type("User", (), {"id": user_id, "is_active": True, "locked_until": None})()
    repo = StubUserRepository(user=user)
    mfa_service = StubMFAService(MFASetupResult.CREATED)
    use_case = EnableMFAUseCase(repo, mfa_service)
    result = await use_case.execute(user_id)
    assert result.secret == "secret-123"
    assert result.provisioning_uri == "otpauth://..."
    assert result.backup_codes == ["code1", "code2"]


@pytest.mark.asyncio
async def test_enable_mfa_already_enabled() -> None:
    user_id = uuid4()
    user = type("User", (), {"id": user_id, "is_active": True, "locked_until": None})()
    repo = StubUserRepository(user=user)
    mfa_service = StubMFAService(MFASetupResult.ALREADY_ENABLED)
    use_case = EnableMFAUseCase(repo, mfa_service)
    with pytest.raises(AuthenticationError, match="MFA is already enabled"):
        await use_case.execute(user_id)


@pytest.mark.asyncio
async def test_enable_mfa_user_not_found() -> None:
    user_id = uuid4()
    repo = StubUserRepository(user=None)
    mfa_service = StubMFAService()
    use_case = EnableMFAUseCase(repo, mfa_service)
    with pytest.raises(AuthenticationError, match="User not found"):
        await use_case.execute(user_id)


@pytest.mark.asyncio
async def test_enable_mfa_inactive_user() -> None:
    user_id = uuid4()
    user = type("User", (), {"id": user_id, "is_active": False, "locked_until": None})()
    repo = StubUserRepository(user=user)
    mfa_service = StubMFAService()
    use_case = EnableMFAUseCase(repo, mfa_service)
    with pytest.raises(InactiveUserError, match="User account is inactive"):
        await use_case.execute(user_id)


@pytest.mark.asyncio
async def test_enable_mfa_locked_account() -> None:
    user_id = uuid4()
    locked_until = datetime.now(UTC) + timedelta(minutes=5)
    user = type("User", (), {"id": user_id, "is_active": True, "locked_until": locked_until})()
    repo = StubUserRepository(user=user, locked_until=locked_until)
    mfa_service = StubMFAService()
    use_case = EnableMFAUseCase(repo, mfa_service)
    with pytest.raises(AccountLockedError, match="Account is locked"):
        await use_case.execute(user_id)


@pytest.mark.asyncio
async def test_enable_mfa_naive_locked_until() -> None:
    user_id = uuid4()
    locked_until = datetime.now() + timedelta(minutes=5)  # noqa: DTZ005
    user = type("User", (), {"id": user_id, "is_active": True, "locked_until": locked_until})()
    repo = StubUserRepository(user=user, locked_until=locked_until)
    mfa_service = StubMFAService()
    use_case = EnableMFAUseCase(repo, mfa_service)
    with pytest.raises(AccountLockedError, match="Account is locked"):
        await use_case.execute(user_id)
