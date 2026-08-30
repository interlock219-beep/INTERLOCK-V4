from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.use_cases.email_verification import (
    ConfirmEmailVerificationUseCase,
    RequestEmailVerificationUseCase,
)
from app.domain.exceptions.domain_errors import AuthenticationError


class StubUserRepository:
    def __init__(self, user=None) -> None:
        self._user = user

    async def get_by_email(self, email: str):
        return self._user

    async def get_by_id(self, user_id):
        return self._user


class StubEmailVerificationService:
    def __init__(self, token=None) -> None:
        self._token = token
        self.created_for = None

    async def create_token(self, user_id, ttl_seconds):
        self.created_for = user_id
        return self._token or "token-123"

    async def validate_token(self, token_hash):
        return self._token and uuid4()

    async def mark_consumed(self, token_hash):
        pass


@pytest.mark.asyncio
async def test_request_email_verification_success() -> None:
    user_id = str(uuid4())
    user = type("User", (), {"id": user_id, "email": "user@example.com"})()
    repo = StubUserRepository(user)
    service = StubEmailVerificationService()
    use_case = RequestEmailVerificationUseCase(repo, service)
    token = await use_case.execute("user@example.com")
    assert token == "token-123"
    assert service.created_for == user_id


@pytest.mark.asyncio
async def test_request_email_verification_user_not_found() -> None:
    repo = StubUserRepository(None)
    service = StubEmailVerificationService()
    use_case = RequestEmailVerificationUseCase(repo, service)
    token = await use_case.execute("missing@example.com")
    assert token == "If the account exists, a verification email has been sent."


@pytest.mark.asyncio
async def test_confirm_email_verification_success() -> None:
    user_id = str(uuid4())
    user = type("User", (), {"id": user_id})()
    repo = StubUserRepository(user)
    service = StubEmailVerificationService("valid-token")
    use_case = ConfirmEmailVerificationUseCase(repo, service)
    await use_case.execute("valid-token")


@pytest.mark.asyncio
async def test_confirm_email_verification_invalid_token() -> None:
    repo = StubUserRepository(None)
    service = StubEmailVerificationService(None)
    use_case = ConfirmEmailVerificationUseCase(repo, service)
    with pytest.raises(AuthenticationError, match="Invalid or expired verification token"):
        await use_case.execute("bad-token")


@pytest.mark.asyncio
async def test_confirm_email_verification_user_not_found() -> None:
    repo = StubUserRepository(None)
    service = StubEmailVerificationService("valid-token")
    use_case = ConfirmEmailVerificationUseCase(repo, service)
    await use_case.execute("valid-token")
