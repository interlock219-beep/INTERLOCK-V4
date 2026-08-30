from __future__ import annotations

from unittest.mock import patch

import pytest

from app.infrastructure.sso.saml_adapter import (
    MockSAMLAdapter,
    ProductionSAMLAdapter,
    SAMLAdapter,
    SAMLProviderError,
)


class FakeState:
    def __init__(self, state_token="token-1"):  # noqa: S107 - benign test fixture default
        self.state_token = state_token


class FakeProvider:
    def __init__(self):
        pass


def test_mock_saml_adapter_generate_auth_request():
    adapter = MockSAMLAdapter()
    state = FakeState("relay-123")
    result = adapter.generate_auth_request(state, FakeProvider())
    assert "relay-123" in result
    assert "mock" in result


def test_mock_saml_adapter_parse_response():
    adapter = MockSAMLAdapter()
    result = adapter.parse_response("<saml>response</saml>")
    assert result["name_id"] == "user@example.com"


def test_production_saml_adapter_import_error():
    with patch(
        "builtins.__import__", side_effect=ImportError("No module")
    ), pytest.raises(SAMLProviderError, match="python3-saml is required"):
        ProductionSAMLAdapter()


def test_saml_adapter_abstract():
    with pytest.raises(TypeError):
        SAMLAdapter()
