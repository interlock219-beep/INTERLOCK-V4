from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.domain.services.identity_services import (
    DefaultEmailVerificationService,
    DefaultPasswordResetService,
    PyOTPMFAService,
)


class StubEmailVerificationRepository:
    def __init__(self) -> None:
        self.tokens = {}

    async def create(self, token):
        self.tokens[token.token_hash] = token

    async def get_by_token_hash(self, token_hash):
        return self.tokens.get(token_hash)

    async def mark_used(self, token_id, used_at):
        for key, t in list(self.tokens.items()):
            if t.id == token_id:
                self.tokens[key] = type(t)(
                    user_id=t.user_id,
                    token_hash=t.token_hash,
                    expires_at=t.expires_at,
                    used=True,
                    created_at=t.created_at,
                    used_at=used_at,
                )
                break


class StubPasswordResetRepository:
    def __init__(self) -> None:
        self.tokens = {}

    async def create(self, token):
        self.tokens[token.token_hash] = token

    async def get_by_token_hash(self, token_hash):
        return self.tokens.get(token_hash)

    async def mark_used(self, token_id, used_at):
        for key, t in list(self.tokens.items()):
            if t.id == token_id:
                self.tokens[key] = type(t)(
                    user_id=t.user_id,
                    token_hash=t.token_hash,
                    expires_at=t.expires_at,
                    used=True,
                    created_at=t.created_at,
                    used_at=used_at,
                )
                break


class StubMFARepository:
    def __init__(self, mfa=None) -> None:
        self._mfa = mfa

    async def get_by_user_id(self, user_id):
        return self._mfa

    async def save(self, mfa):
        self._mfa = mfa

    async def delete(self, user_id):
        self._mfa = None


@pytest.mark.asyncio
async def test_pyotp_mfa_setup_new():
    repo = StubMFARepository()
    service = PyOTPMFAService(repo)
    result = await service.setup(UUID(int=1))
    assert result.result.value == "created"
    assert result.secret is not None
    assert len(result.backup_codes) == 10


@pytest.mark.asyncio
async def test_pyotp_mfa_setup_already_enabled():
    existing = type("UserMFA", (), {
        "user_id": UUID(int=1),
        "secret": "secret",
        "backup_codes": [],
        "is_enabled": True,
    })()
    repo = StubMFARepository(mfa=existing)
    service = PyOTPMFAService(repo)
    result = await service.setup(UUID(int=1))
    assert result.result.value == "already_enabled"


@pytest.mark.asyncio
async def test_pyotp_mfa_confirm_success():
    import pyotp
    secret = pyotp.random_base32()
    existing = type("UserMFA", (), {
        "user_id": UUID(int=1),
        "secret": secret,
        "backup_codes": [],
        "is_enabled": False,
        "confirmed_at": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    })()
    repo = StubMFARepository(mfa=existing)
    service = PyOTPMFAService(repo)
    totp = pyotp.TOTP(secret)
    code = totp.now()
    result = await service.confirm(UUID(int=1), code)
    assert result.is_enabled is True
    assert result.confirmed_at is not None


@pytest.mark.asyncio
async def test_pyotp_mfa_confirm_invalid_code():
    existing = type("UserMFA", (), {
        "user_id": UUID(int=1),
        "secret": "invalid",
        "backup_codes": [],
        "is_enabled": False,
    })()
    repo = StubMFARepository(mfa=existing)
    service = PyOTPMFAService(repo)
    with pytest.raises(ValueError, match="Invalid MFA code"):
        await service.confirm(UUID(int=1), "000000")


@pytest.mark.asyncio
async def test_pyotp_mfa_confirm_not_setup():
    repo = StubMFARepository()
    service = PyOTPMFAService(repo)
    with pytest.raises(ValueError, match="MFA is not set up"):
        await service.confirm(UUID(int=1), "000000")


@pytest.mark.asyncio
async def test_pyotp_mfa_verify_with_backup_code():
    import pyotp

    existing = type("UserMFA", (), {
        "user_id": UUID(int=1),
        "secret": pyotp.random_base32(),
        "backup_codes": ["backup1", "backup2"],
        "is_enabled": False,
        "confirmed_at": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    })()
    repo = StubMFARepository(mfa=existing)
    service = PyOTPMFAService(repo)
    result = await service.verify(UUID(int=1), "backup1")
    assert result is True
    assert repo._mfa is not None
    assert "backup1" not in repo._mfa.backup_codes


@pytest.mark.asyncio
async def test_pyotp_mfa_disable_with_code():
    import pyotp

    secret = pyotp.random_base32()
    existing = type("UserMFA", (), {
        "user_id": UUID(int=1),
        "secret": secret,
        "backup_codes": [],
        "is_enabled": False,
    })()
    repo = StubMFARepository(mfa=existing)
    service = PyOTPMFAService(repo)
    totp = pyotp.TOTP(secret)
    code = totp.now()
    await service.disable(UUID(int=1), code)
    assert repo._mfa is None


@pytest.mark.asyncio
async def test_pyotp_mfa_disable_without_code():
    existing = type("UserMFA", (), {
        "user_id": UUID(int=1),
        "secret": "secret",
        "backup_codes": [],
        "is_enabled": False,
    })()
    repo = StubMFARepository(mfa=existing)
    service = PyOTPMFAService(repo)
    await service.disable(UUID(int=1))
    assert repo._mfa is None


@pytest.mark.asyncio
async def test_pyotp_mfa_regenerate_backup_codes():
    existing = type("UserMFA", (), {
        "user_id": UUID(int=1),
        "secret": "secret",
        "backup_codes": ["old"],
        "is_enabled": False,
        "confirmed_at": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    })()
    repo = StubMFARepository(mfa=existing)
    service = PyOTPMFAService(repo)
    codes = await service.regenerate_backup_codes(UUID(int=1))
    assert len(codes) == 10
    assert repo._mfa.backup_codes == codes


@pytest.mark.asyncio
async def test_email_verification_create_token():
    repo = StubEmailVerificationRepository()
    service = DefaultEmailVerificationService(repo)
    token = await service.create_token(UUID(int=1), 3600)
    assert len(token) > 0
    assert len(repo.tokens) == 1


@pytest.mark.asyncio
async def test_email_verification_validate_token():
    repo = StubEmailVerificationRepository()
    service = DefaultEmailVerificationService(repo)
    token = await service.create_token(UUID(int=1), 3600)
    import hashlib
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    user_id = await service.validate_token(token_hash)
    assert user_id == UUID(int=1)


@pytest.mark.asyncio
async def test_email_verification_mark_consumed():
    repo = StubEmailVerificationRepository()
    service = DefaultEmailVerificationService(repo)
    token = await service.create_token(UUID(int=1), 3600)
    import hashlib
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    await service.mark_consumed(token_hash)
    user_id = await service.validate_token(token_hash)
    assert user_id is None


@pytest.mark.asyncio
async def test_password_reset_create_token():
    repo = StubPasswordResetRepository()
    service = DefaultPasswordResetService(repo, None)
    token = await service.create_token(UUID(int=1), 3600)
    assert len(token) > 0


@pytest.mark.asyncio
async def test_password_reset_validate_token():
    repo = StubPasswordResetRepository()
    service = DefaultPasswordResetService(repo, None)
    token = await service.create_token(UUID(int=1), 3600)
    import hashlib
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    user_id = await service.validate_token(token_hash)
    assert user_id == UUID(int=1)


@pytest.mark.asyncio
async def test_password_reset_mark_consumed():
    repo = StubPasswordResetRepository()
    service = DefaultPasswordResetService(repo, None)
    token = await service.create_token(UUID(int=1), 3600)
    import hashlib
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    await service.mark_consumed(token_hash)
    user_id = await service.validate_token(token_hash)
    assert user_id is None
