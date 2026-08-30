from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.application.use_cases.authenticate_user import AuthenticateUserUseCase
from app.domain.exceptions.domain_errors import (
    AccountLockedError,
    AuthenticationError,
    InactiveUserError,
)


class StubUserRepository:
    def __init__(self, user=None) -> None:
        self._user = user
        self.incremented = None
        self.locked = None
        self.reset = None

    async def get_by_email(self, email):
        return self._user

    async def increment_failed_login(self, user_id):
        self.incremented = user_id
        if self._user is not None:
            self._user.failed_login_attempts += 1
        return self._user

    async def lock_account(self, user_id, lockout_until):
        self.locked = (user_id, lockout_until)
        if self._user is not None:
            self._user.locked_until = lockout_until
        return self._user

    async def reset_failed_login(self, user_id):
        self.reset = user_id
        if self._user is not None:
            self._user.failed_login_attempts = 0
            self._user.locked_until = None
        return self._user


class StubPasswordHasher:
    def __init__(self) -> None:
        self._expected = "password"

    def verify(self, password, hashed):
        return password == self._expected

    def hash(self, password):
        return "hashed"


class StubTokenService:
    def create_access_token(self, *, user_id, email, session_id):
        return f"access-{user_id}"


class StubSessionService:
    def __init__(self) -> None:
        self.created = None

    async def create_session(self, *, user_id, ttl_seconds):
        self.created = (user_id, ttl_seconds)
        return f"session-{user_id}", "2025-01-01T00:00:00Z"


@pytest.mark.asyncio
async def test_authenticate_user_success_with_session() -> None:
    user_id = str(uuid4())
    user = type("User", (), {
        "id": user_id,
        "email": "user@example.com",
        "is_active": True,
        "role": "user",
        "tenant_id": "tenant-1",
        "hashed_password": "hashed",
        "failed_login_attempts": 0,
        "locked_until": None,
    })()
    repo = StubUserRepository(user=user)
    hasher = StubPasswordHasher()
    token_service = StubTokenService()
    session_service = StubSessionService()
    use_case = AuthenticateUserUseCase(
        repo, hasher, token_service,
        session_service=session_service,
        session_ttl_seconds=3600,
    )
    from app.application.dto.auth import LoginRequest
    request = LoginRequest(email="user@example.com", password="password")
    result = await use_case.execute(request)
    assert result.access_token == f"access-{user_id}"
    assert result.refresh_token == f"session-{user_id}"
    assert session_service.created is not None


@pytest.mark.asyncio
async def test_authenticate_user_success_without_session() -> None:
    user_id = str(uuid4())
    user = type("User", (), {
        "id": user_id,
        "email": "user@example.com",
        "is_active": True,
        "role": "user",
        "tenant_id": "tenant-1",
        "hashed_password": "hashed",
        "failed_login_attempts": 0,
        "locked_until": None,
    })()
    repo = StubUserRepository(user=user)
    hasher = StubPasswordHasher()
    token_service = StubTokenService()
    use_case = AuthenticateUserUseCase(repo, hasher, token_service)
    from app.application.dto.auth import LoginRequest
    request = LoginRequest(email="user@example.com", password="password")
    result = await use_case.execute(request)
    assert result.access_token == f"access-{user_id}"
    assert result.refresh_token is None


@pytest.mark.asyncio
async def test_authenticate_user_invalid_password() -> None:
    user_id = str(uuid4())
    user = type("User", (), {
        "id": user_id,
        "email": "user@example.com",
        "is_active": True,
        "role": "user",
        "tenant_id": "tenant-1",
        "hashed_password": "hashed",
        "failed_login_attempts": 0,
        "locked_until": None,
    })()
    repo = StubUserRepository(user=user)
    hasher = StubPasswordHasher()
    token_service = StubTokenService()
    use_case = AuthenticateUserUseCase(repo, hasher, token_service)
    from app.application.dto.auth import LoginRequest
    request = LoginRequest(email="user@example.com", password="wrong")
    with pytest.raises(AuthenticationError, match="Invalid email or password"):
        await use_case.execute(request)
    assert repo.incremented == user_id


@pytest.mark.asyncio
async def test_authenticate_user_locked_account() -> None:
    user_id = str(uuid4())
    locked_until = datetime.now(UTC) + timedelta(minutes=5)
    user = type("User", (), {
        "id": user_id,
        "email": "user@example.com",
        "is_active": True,
        "role": "user",
        "tenant_id": "tenant-1",
        "hashed_password": "hashed",
        "failed_login_attempts": 5,
        "locked_until": locked_until,
    })()
    repo = StubUserRepository(user=user)
    hasher = StubPasswordHasher()
    token_service = StubTokenService()
    use_case = AuthenticateUserUseCase(repo, hasher, token_service)
    from app.application.dto.auth import LoginRequest
    request = LoginRequest(email="user@example.com", password="password")
    with pytest.raises(AccountLockedError, match="Account is locked"):
        await use_case.execute(request)


@pytest.mark.asyncio
async def test_authenticate_user_inactive() -> None:
    user_id = str(uuid4())
    user = type("User", (), {
        "id": user_id,
        "email": "user@example.com",
        "is_active": False,
        "role": "user",
        "tenant_id": "tenant-1",
        "hashed_password": "hashed",
        "failed_login_attempts": 0,
        "locked_until": None,
    })()
    repo = StubUserRepository(user=user)
    hasher = StubPasswordHasher()
    token_service = StubTokenService()
    use_case = AuthenticateUserUseCase(repo, hasher, token_service)
    from app.application.dto.auth import LoginRequest
    request = LoginRequest(email="user@example.com", password="password")
    with pytest.raises(InactiveUserError, match="User account is inactive"):
        await use_case.execute(request)


@pytest.mark.asyncio
async def test_authenticate_user_naive_locked_until() -> None:
    user_id = str(uuid4())
    locked_until = datetime.now() + timedelta(minutes=5)  # noqa: DTZ005
    user = type("User", (), {
        "id": user_id,
        "email": "user@example.com",
        "is_active": True,
        "role": "user",
        "tenant_id": "tenant-1",
        "hashed_password": "hashed",
        "failed_login_attempts": 5,
        "locked_until": locked_until,
    })()
    repo = StubUserRepository(user=user)
    hasher = StubPasswordHasher()
    token_service = StubTokenService()
    use_case = AuthenticateUserUseCase(repo, hasher, token_service)
    from app.application.dto.auth import LoginRequest
    request = LoginRequest(email="user@example.com", password="password")
    with pytest.raises(AccountLockedError, match="Account is locked"):
        await use_case.execute(request)
