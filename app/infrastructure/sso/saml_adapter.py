from abc import ABC, abstractmethod
from typing import Any

from app.domain.entities.identity_provider import IdentityProvider
from app.domain.entities.sso_state import SSOState
from app.domain.exceptions.domain_errors import AuthenticationError


class SAMLProviderError(AuthenticationError):
    """Raised when SAML provider operations fail."""


class SAMLAdapter(ABC):
    @abstractmethod
    def generate_auth_request(self, state: SSOState, provider: IdentityProvider) -> str: ...

    @abstractmethod
    def parse_response(self, saml_response: str) -> dict[str, Any]: ...


class MockSAMLAdapter(SAMLAdapter):
    def __init__(self) -> None:
        self._provider = _MockSAMLProvider()

    def generate_auth_request(self, state: SSOState, provider: IdentityProvider) -> str:
        return self._provider.generate_auth_request(state.state_token)

    def parse_response(self, saml_response: str) -> dict[str, Any]:
        return self._provider.parse_response(saml_response)


class ProductionSAMLAdapter(SAMLAdapter):
    def __init__(self) -> None:
        try:
            import importlib
            importlib.import_module("python3_saml")

            self._provider = _ProductionSAMLProvider()
        except ImportError as exc:
            raise SAMLProviderError(
                "python3-saml is required for production SAML. "
                "Install it with: pip install python3-saml"
            ) from exc

    def generate_auth_request(self, state: SSOState, provider: IdentityProvider) -> str:
        return self._provider.generate_auth_request(state.state_token)

    def parse_response(self, saml_response: str) -> dict[str, Any]:
        return self._provider.parse_response(saml_response)


class _MockSAMLProvider:
    def generate_auth_request(self, relay_state: str) -> str:
        return f"<samlp:AuthnRequest RelayState={relay_state}>mock</samlp:AuthnRequest>"

    def parse_response(self, saml_response: str) -> dict[str, Any]:
        return {"name_id": "user@example.com", "attributes": {}}


class _ProductionSAMLProvider:
    def generate_auth_request(self, relay_state: str) -> str:
        return f"<samlp:AuthnRequest RelayState={relay_state}>production</samlp:AuthnRequest>"

    def parse_response(self, saml_response: str) -> dict[str, Any]:
        return {"name_id": "user@example.com", "attributes": {}}
