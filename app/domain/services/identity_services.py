from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID

import pyotp

from app.domain.entities.email_verification_token import EmailVerificationToken
from app.domain.entities.password_reset_token import PasswordResetToken
from app.domain.entities.user_mfa import UserMFA
from app.domain.exceptions.domain_errors import AuthenticationError
from app.domain.repositories.reset_repository import (
    EmailVerificationRepository,
    PasswordResetRepository,
)
from app.domain.repositories.session_repository import MFARepository
from app.domain.repositories.user_repository import UserRepository


class MFASetupResult(StrEnum):
    CREATED = "created"
    ALREADY_ENABLED = "already_enabled"


@dataclass(frozen=True)
class MFASetupResponse:
    result: MFASetupResult
    secret: str | None = None
    backup_codes: list[str] | None = None
    provisioning_uri: str | None = None


class MFAService(ABC):
    @abstractmethod
    async def setup(self, user_id: UUID) -> MFASetupResponse: ...

    @abstractmethod
    async def confirm(self, user_id: UUID, code: str) -> UserMFA: ...

    @abstractmethod
    async def verify(self, user_id: UUID, code: str) -> bool: ...

    @abstractmethod
    async def disable(self, user_id: UUID, code: str | None = None) -> None: ...

    @abstractmethod
    async def regenerate_backup_codes(self, user_id: UUID) -> list[str]: ...


class PasswordResetService(ABC):
    @abstractmethod
    async def create_token(self, user_id: UUID, ttl_seconds: int) -> str: ...

    @abstractmethod
    async def validate_token(self, token_hash: str) -> UUID | None: ...

    @abstractmethod
    async def mark_consumed(self, token_hash: str) -> None: ...


class EmailVerificationService(ABC):
    @abstractmethod
    async def create_token(self, user_id: UUID, ttl_seconds: int) -> str: ...

    @abstractmethod
    async def validate_token(self, token_hash: str) -> UUID | None: ...

    @abstractmethod
    async def mark_consumed(self, token_hash: str) -> None: ...


class SessionService(ABC):
    @abstractmethod
    async def create_session(
        self,
        user_id: UUID,
        *,
        device_info: str | None = None,
        ip_address: str | None = None,
        ttl_seconds: int,
    ) -> tuple[str, datetime]: ...

    @abstractmethod
    async def validate_session(self, session_id: str) -> UUID | None: ...

    @abstractmethod
    async def is_session_active(self, session_id: str) -> bool: ...

    @abstractmethod
    async def revoke_session(self, session_id: str, *, user_id: UUID | None = None) -> bool: ...

    @abstractmethod
    async def revoke_all_sessions(self, user_id: UUID) -> int: ...

    @abstractmethod
    async def get_active_sessions(self, user_id: UUID) -> list[dict[str, str]]: ...

    @abstractmethod
    async def touch_session(self, session_id: str) -> None: ...

    @abstractmethod
    async def cleanup_expired(self) -> int: ...


class PyOTPMFAService(MFAService):
    def __init__(self, repository: MFARepository, issuer_name: str = "IntentLock") -> None:
        self._repository = repository
        self._issuer_name = issuer_name

    async def setup(self, user_id: UUID) -> MFASetupResponse:
        existing = await self._repository.get_by_user_id(user_id)
        if existing is not None and existing.is_enabled:
            return MFASetupResponse(result=MFASetupResult.ALREADY_ENABLED)

        secret = pyotp.random_base32()
        backup_codes = [token_urlsafe(16) for _ in range(10)]
        provisioning_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            issuer_name=self._issuer_name,
            name=str(user_id),
        )

        mfa = UserMFA(
            user_id=user_id,
            secret=secret,
            backup_codes=backup_codes,
            is_enabled=False,
        )
        await self._repository.save(mfa)
        return MFASetupResponse(
            result=MFASetupResult.CREATED,
            secret=secret,
            backup_codes=backup_codes,
            provisioning_uri=provisioning_uri,
        )

    async def confirm(self, user_id: UUID, code: str) -> UserMFA:
        mfa = await self._repository.get_by_user_id(user_id)
        if mfa is None:
            raise ValueError("MFA is not set up.")

        totp = pyotp.TOTP(mfa.secret)
        if not totp.verify(code):
            raise ValueError("Invalid MFA code.")

        mfa = UserMFA(
            user_id=mfa.user_id,
            secret=mfa.secret,
            backup_codes=mfa.backup_codes,
            is_enabled=True,
            confirmed_at=datetime.now(UTC),
            created_at=mfa.created_at,
            updated_at=datetime.now(UTC),
        )
        await self._repository.save(mfa)
        return mfa

    async def verify(self, user_id: UUID, code: str) -> bool:
        mfa = await self._repository.get_by_user_id(user_id)
        if mfa is None:
            return False

        totp = pyotp.TOTP(mfa.secret)
        if totp.verify(code):
            return True

        for backup_code in mfa.backup_codes:
            if backup_code == code:
                mfa = UserMFA(
                    user_id=mfa.user_id,
                    secret=mfa.secret,
                    backup_codes=[c for c in mfa.backup_codes if c != code],
                    is_enabled=mfa.is_enabled,
                    confirmed_at=mfa.confirmed_at,
                    created_at=mfa.created_at,
                    updated_at=datetime.now(UTC),
                )
                await self._repository.save(mfa)
                return True

        return False

    async def disable(self, user_id: UUID, code: str | None = None) -> None:
        if code is not None:
            valid = await self.verify(user_id, code)
            if not valid:
                raise AuthenticationError("Invalid MFA code.")
        await self._repository.delete(user_id)

    async def regenerate_backup_codes(self, user_id: UUID) -> list[str]:
        mfa = await self._repository.get_by_user_id(user_id)
        if mfa is None:
            raise ValueError("MFA is not set up.")

        backup_codes = [token_urlsafe(16) for _ in range(10)]
        mfa = UserMFA(
            user_id=mfa.user_id,
            secret=mfa.secret,
            backup_codes=backup_codes,
            is_enabled=mfa.is_enabled,
            confirmed_at=mfa.confirmed_at,
            created_at=mfa.created_at,
            updated_at=datetime.now(UTC),
        )
        await self._repository.save(mfa)
        return backup_codes


class DefaultPasswordResetService(PasswordResetService):
    def __init__(
        self,
        repository: PasswordResetRepository,
        user_repository: UserRepository,
    ) -> None:
        self._repository = repository
        self._user_repository = user_repository

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _is_expired(expires_at: datetime, now: datetime) -> bool:
        if expires_at.tzinfo is None:
            return expires_at < now.replace(tzinfo=None)
        return expires_at < now

    async def create_token(self, user_id: UUID, ttl_seconds: int) -> str:
        raw_token = token_urlsafe(32)
        token_hash = sha256(raw_token.encode("utf-8")).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        token = PasswordResetToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        await self._repository.create(token)
        return raw_token

    async def validate_token(self, token_hash: str) -> UUID | None:
        token = await self._repository.get_by_token_hash(token_hash)
        now = self._utcnow()
        if token is None or token.used or self._is_expired(token.expires_at, now):
            return None
        return token.user_id

    async def mark_consumed(self, token_hash: str) -> None:
        token = await self._repository.get_by_token_hash(token_hash)
        if token is None:
            return
        await self._repository.mark_used(token.id, datetime.now(UTC))


class DefaultEmailVerificationService(EmailVerificationService):
    def __init__(self, repository: EmailVerificationRepository) -> None:
        self._repository = repository

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _is_expired(expires_at: datetime, now: datetime) -> bool:
        if expires_at.tzinfo is None:
            return expires_at < now.replace(tzinfo=None)
        return expires_at < now

    async def create_token(self, user_id: UUID, ttl_seconds: int) -> str:
        raw_token = token_urlsafe(32)
        token_hash = sha256(raw_token.encode("utf-8")).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        token = EmailVerificationToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        await self._repository.create(token)
        return raw_token

    async def validate_token(self, token_hash: str) -> UUID | None:
        token = await self._repository.get_by_token_hash(token_hash)
        now = self._utcnow()
        if token is None or token.used or self._is_expired(token.expires_at, now):
            return None
        return token.user_id

    async def mark_consumed(self, token_hash: str) -> None:
        token = await self._repository.get_by_token_hash(token_hash)
        if token is None:
            return
        await self._repository.mark_used(token.id, datetime.now(UTC))
