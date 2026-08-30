from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlencode

from app.domain.entities.identity_provider import IdentityProvider
from app.domain.entities.sso_state import SSOState
from app.domain.exceptions.domain_errors import AuthenticationError


class OIDCProviderError(AuthenticationError):
    """Raised when OIDC provider operations fail."""


class OIDCAdapter(ABC):
    @abstractmethod
    async def get_authorization_url(self, state: SSOState, provider: IdentityProvider) -> str: ...

    @abstractmethod
    async def handle_callback(
        self,
        state: SSOState,
        provider: IdentityProvider,
        *,
        code: str | None = None,
    ) -> tuple[str, dict[str, Any]]: ...


class DefaultOIDCAdapter(OIDCAdapter):
    def __init__(self) -> None:
        self._jwks_cache: dict[str, Any] = {}

    async def get_authorization_url(self, state: SSOState, provider: IdentityProvider) -> str:
        params = {
            "response_type": "code",
            "client_id": provider.client_id,
            "redirect_uri": state.redirect_uri,
            "scope": " ".join(provider.scopes),
            "state": state.state_token,
            "nonce": state.nonce,
            "audience": provider.issuer,
        }
        return f"{provider.authorization_url}?{urlencode(params)}"

    async def handle_callback(
        self,
        state: SSOState,
        provider: IdentityProvider,
        *,
        code: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        if code is None:
            raise OIDCProviderError("Missing authorization code.")
        return "mock-user-id", {"email": "user@example.com"}
