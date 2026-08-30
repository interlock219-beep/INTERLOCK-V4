from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.application.use_cases.refresh_token import RefreshTokenUseCase
from app.domain.exceptions.domain_errors import (
    AccountLockedError,
    AuthenticationError,
    InactiveUserError,
)


class StubUserRepository:
    def __init__(self, user=None) -> None:
        self._user = user

    async def get_by_id(self, user_id):
        return self._user


class StubTokenService:
    def create_access_token(self, *, user_id, email, session_id):
        return f"access-{user_id}"


class StubSessionService:
    def __init__(self, valid=True, session_user_id=None) -> None:
        self._valid = valid
        self._session_user_id = session_user_id
        self.revoked = None
        self.created = None

    async def validate_session(self, session_id):
        return self._session_user_id

    async def revoke_session(self, session_id, *, user_id):
        self.revoked = (session_id, user_id)

    async def create_session(self, *, user_id, ttl_seconds):
        self.created = (user_id, ttl_seconds)
        return f"session-{user_id}", "2025-01-01T00:00:00Z"


@pytest.mark.asyncio
async def test_refresh_token_success() -> None:
    user_id = uuid4()
    user = type("User", (), {
        "id": user_id,
        "email": "user@example.com",
        "is_active": True,
        "locked_until": None,
    })()
    repo = StubUserRepository(user=user)
    token_service = StubTokenService()
    session_service = StubSessionService(valid=True, session_user_id=user_id)
    use_case = RefreshTokenUseCase(repo, token_service, session_service)
    result = await use_case.execute("session-1")
    assert result["access_token"] == f"access-{user_id}"
    assert result["refresh_token"] == f"session-{user_id}"
    assert session_service.revoked is not None
    assert session_service.revoked[0] == "session-1"


@pytest.mark.asyncio
async def test_refresh_token_invalid_session() -> None:
    user_id = uuid4()
    user = type("User", (), {
        "id": user_id,
        "email": "user@example.com",
        "is_active": True,
        "locked_until": None,
    })()
    repo = StubUserRepository(user=user)
    token_service = StubTokenService()
    session_service = StubSessionService(valid=False)
    use_case = RefreshTokenUseCase(repo, token_service, session_service)
    with pytest.raises(AuthenticationError, match="Invalid or expired refresh token"):
        await use_case.execute("bad-session")


@pytest.mark.asyncio
async def test_refresh_token_user_not_found() -> None:
    repo = StubUserRepository(user=None)
    token_service = StubTokenService()
    session_service = StubSessionService(valid=True, session_user_id=uuid4())
    use_case = RefreshTokenUseCase(repo, token_service, session_service)
    with pytest.raises(InactiveUserError, match="User account is inactive"):
        await use_case.execute("session-1")


@pytest.mark.asyncio
async def test_refresh_token_inactive_user() -> None:
    user_id = uuid4()
    user = type("User", (), {
        "id": user_id,
        "email": "user@example.com",
        "is_active": False,
        "locked_until": None,
    })()
    repo = StubUserRepository(user=user)
    token_service = StubTokenService()
    session_service = StubSessionService(valid=True, session_user_id=user_id)
    use_case = RefreshTokenUseCase(repo, token_service, session_service)
    with pytest.raises(InactiveUserError, match="User account is inactive"):
        await use_case.execute("session-1")


@pytest.mark.asyncio
async def test_refresh_token_locked_account() -> None:
    user_id = uuid4()
    locked_until = datetime.now(UTC) + timedelta(minutes=5)
    user = type("User", (), {
        "id": user_id,
        "email": "user@example.com",
        "is_active": True,
        "locked_until": locked_until,
    })()
    repo = StubUserRepository(user=user)
    token_service = StubTokenService()
    session_service = StubSessionService(valid=True, session_user_id=user_id)
    use_case = RefreshTokenUseCase(repo, token_service, session_service)
    with pytest.raises(AccountLockedError, match="Account is locked"):
        await use_case.execute("session-1")


@pytest.mark.asyncio
async def test_refresh_token_naive_locked_until() -> None:
    user_id = uuid4()
    locked_until = datetime.now() + timedelta(minutes=5)  # noqa: DTZ005
    user = type("User", (), {
        "id": user_id,
        "email": "user@example.com",
        "is_active": True,
        "locked_until": locked_until,
    })()
    repo = StubUserRepository(user=user)
    token_service = StubTokenService()
    session_service = StubSessionService(valid=True, session_user_id=user_id)
    use_case = RefreshTokenUseCase(repo, token_service, session_service)
    with pytest.raises(AccountLockedError, match="Account is locked"):
        await use_case.execute("session-1")
