from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.use_cases.password_reset import (
    ConfirmPasswordResetUseCase,
    RequestPasswordResetUseCase,
)
from app.domain.exceptions.domain_errors import AuthenticationError


class StubUserRepository:
    def __init__(self, user=None) -> None:
        self._user = user
        self.updated_password = None

    async def get_by_email(self, email):
        return self._user

    async def get_by_id(self, user_id):
        return self._user

    async def update_password(self, user_id, hashed):
        self.updated_password = (user_id, hashed)


class StubPasswordHasher:
    def hash(self, password):
        return "hashed"


class StubPasswordResetService:
    def __init__(self, token=None) -> None:
        self._token = token

    async def create_token(self, user_id, ttl_seconds):
        return self._token or "token-123"

    async def validate_token(self, token_hash):
        return self._token and uuid4()

    async def mark_consumed(self, token_hash):
        pass


@pytest.mark.asyncio
async def test_request_password_reset_success() -> None:
    user_id = str(uuid4())
    user = type("User", (), {"id": user_id})()
    repo = StubUserRepository(user=user)
    service = StubPasswordResetService()
    use_case = RequestPasswordResetUseCase(repo, service)
    token = await use_case.execute("user@example.com")
    assert token == "token-123"


@pytest.mark.asyncio
async def test_request_password_reset_user_not_found() -> None:
    repo = StubUserRepository(None)
    service = StubPasswordResetService()
    use_case = RequestPasswordResetUseCase(repo, service)
    result = await use_case.execute("missing@example.com")
    assert "reset link has been sent" in result


@pytest.mark.asyncio
async def test_confirm_password_reset_success() -> None:
    user_id = str(uuid4())
    user = type("User", (), {"id": user_id})()
    repo = StubUserRepository(user=user)
    hasher = StubPasswordHasher()
    service = StubPasswordResetService("valid-token")
    use_case = ConfirmPasswordResetUseCase(repo, service, hasher)
    await use_case.execute("valid-token", "new-password")
    assert repo.updated_password == (user_id, "hashed")


@pytest.mark.asyncio
async def test_confirm_password_reset_invalid_token() -> None:
    repo = StubUserRepository(None)
    hasher = StubPasswordHasher()
    service = StubPasswordResetService(None)
    use_case = ConfirmPasswordResetUseCase(repo, service, hasher)
    with pytest.raises(AuthenticationError, match="Invalid or expired password reset token"):
        await use_case.execute("bad-token", "new-password")


@pytest.mark.asyncio
async def test_confirm_password_reset_user_not_found() -> None:
    repo = StubUserRepository(None)
    hasher = StubPasswordHasher()
    service = StubPasswordResetService("valid-token")
    use_case = ConfirmPasswordResetUseCase(repo, service, hasher)
    with pytest.raises(AuthenticationError, match="User not found"):
        await use_case.execute("valid-token", "new-password")
