from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from secrets import token_urlsafe
from uuid import UUID

from app.domain.entities.identity_provider import IdentityProvider, IdentityProviderType
from app.domain.entities.sso_state import SSOProviderType, SSOState, SSOStateStatus


class SSOFlowResult(StrEnum):
    AUTHORIZED = "authorized"
    PENDING = "pending"
    FAILED = "failed"


@dataclass(frozen=True)
class SSOInitiateResult:
    result: SSOFlowResult
    authorization_url: str | None = None
    state_token: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class SSOCallbackResult:
    result: SSOFlowResult
    user_id: UUID | None = None
    email: str | None = None
    error: str | None = None


class SSOService(ABC):
    @abstractmethod
    async def initiate(
        self,
        provider_name: str,
        tenant_id: str | None,
        redirect_uri: str,
    ) -> SSOInitiateResult: ...

    @abstractmethod
    async def handle_callback(
        self,
        state_token: str,
        *,
        code: str | None = None,
        saml_response: str | None = None,
    ) -> SSOCallbackResult: ...

    @abstractmethod
    async def get_providers(self, tenant_id: str | None = None) -> list[IdentityProvider]: ...


class AccountLinkingService(ABC):
    @abstractmethod
    async def link_sso_account(
        self,
        user_id: UUID,
        provider_type: IdentityProviderType,
        provider_user_id: str,
    ) -> None: ...

    @abstractmethod
    async def find_user_by_sso(
        self,
        provider_type: IdentityProviderType,
        provider_user_id: str,
    ) -> UUID | None: ...


class MockAccountLinkingService(AccountLinkingService):
    def __init__(self) -> None:
        self._links: dict[str, UUID] = {}

    async def link_sso_account(
        self,
        user_id: UUID,
        provider_type: IdentityProviderType,
        provider_user_id: str,
    ) -> None:
        key = f"{provider_type.value}:{provider_user_id}"
        self._links[key] = user_id

    async def find_user_by_sso(
        self,
        provider_type: IdentityProviderType,
        provider_user_id: str,
    ) -> UUID | None:
        key = f"{provider_type.value}:{provider_user_id}"
        return self._links.get(key)


class StateManager:
    def __init__(self, state_ttl_seconds: int = 600) -> None:
        self._state_ttl_seconds = state_ttl_seconds
        self._states: dict[str, SSOState] = {}

    def generate_state(
        self,
        provider_type: SSOProviderType,
        tenant_id: str | None,
        redirect_uri: str,
    ) -> SSOState:
        state_token = token_urlsafe(32)
        nonce = token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(seconds=self._state_ttl_seconds)
        state = SSOState(
            state_token=state_token,
            nonce=nonce,
            provider_type=provider_type,
            tenant_id=tenant_id,
            redirect_uri=redirect_uri,
            expires_at=expires_at,
        )
        self._states[state_token] = state
        return state

    def get_state(self, state_token: str) -> SSOState | None:
        state = self._states.get(state_token)
        if state is None:
            return None
        if datetime.now(UTC) > state.expires_at:
            del self._states[state_token]
            return None
        return state

    def mark_consumed(self, state_token: str, user_id: UUID) -> SSOState | None:
        state = self.get_state(state_token)
        if state is None:
            return None
        state = SSOState(
            state_token=state.state_token,
            nonce=state.nonce,
            provider_type=state.provider_type,
            tenant_id=state.tenant_id,
            redirect_uri=state.redirect_uri,
            status=SSOStateStatus.AUTHORIZED,
            user_id=user_id,
            id=state.id,
            created_at=state.created_at,
            expires_at=state.expires_at,
            consumed_at=datetime.now(UTC),
        )
        self._states[state_token] = state
        return state

    def mark_failed(self, state_token: str) -> SSOState | None:
        state = self.get_state(state_token)
        if state is None:
            return None
        state = SSOState(
            state_token=state.state_token,
            nonce=state.nonce,
            provider_type=state.provider_type,
            tenant_id=state.tenant_id,
            redirect_uri=state.redirect_uri,
            status=SSOStateStatus.FAILED,
            id=state.id,
            created_at=state.created_at,
            expires_at=state.expires_at,
            consumed_at=state.consumed_at,
        )
        self._states[state_token] = state
        return state

    def cleanup_expired(self) -> int:
        now = datetime.now(UTC)
        expired = [token for token, state in self._states.items() if now > state.expires_at]
        for token in expired:
            del self._states[token]
        return len(expired)
