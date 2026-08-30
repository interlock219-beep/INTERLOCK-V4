from __future__ import annotations

import hashlib
import hmac

import pytest

from app.infrastructure.integrations.webhook_adapter import (
    MockWebhookAdapter,
    WebhookAdapter,
    WebhookProcessingError,
)


class TestWebhookAdapter(WebhookAdapter):
    async def verify_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        return True

    async def process_event(
        self, payload: dict[str, object], event_id: str
    ) -> dict[str, object]:
        return {"event_id": event_id, "status": "ok"}


@pytest.mark.asyncio
async def test_webhook_adapter_handle_success():
    adapter = TestWebhookAdapter()
    payload = b'{"id": "evt-1", "data": "test"}'
    secret = "secret"
    signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    result = await adapter.handle(payload, signature, secret)
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_webhook_adapter_handle_invalid_signature():
    adapter = MockWebhookAdapter()
    payload = b'{"id": "evt-1"}'
    with pytest.raises(WebhookProcessingError, match="Invalid webhook signature"):
        await adapter.handle(payload, "bad-signature", "secret")


@pytest.mark.asyncio
async def test_webhook_adapter_handle_missing_id():
    adapter = TestWebhookAdapter()
    payload = b'{"data": "test"}'
    secret = "secret"
    signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    with pytest.raises(WebhookProcessingError, match="missing id"):
        await adapter.handle(payload, signature, secret)


@pytest.mark.asyncio
async def test_webhook_adapter_handle_retry_then_success():
    class FailingThenSucceedingAdapter(WebhookAdapter):
        attempt = 0

        async def verify_signature(self, payload: bytes, signature: str, secret: str) -> bool:
            return True

        async def process_event(
            self, payload: dict[str, object], event_id: str
        ) -> dict[str, object]:
            self.attempt += 1
            if self.attempt < 2:
                raise RuntimeError("transient error")
            return {"event_id": event_id, "status": "ok"}

    adapter = FailingThenSucceedingAdapter()
    payload = b'{"id": "evt-1"}'
    secret = "secret"
    signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    result = await adapter.handle(payload, signature, secret)
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_webhook_adapter_handle_max_retries_exceeded():
    class AlwaysFailingAdapter(WebhookAdapter):
        async def verify_signature(self, payload: bytes, signature: str, secret: str) -> bool:
            return True

        async def process_event(
            self, payload: dict[str, object], event_id: str
        ) -> dict[str, object]:
            raise RuntimeError("permanent error")

    adapter = AlwaysFailingAdapter()
    payload = b'{"id": "evt-1"}'
    secret = "secret"
    signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    with pytest.raises(WebhookProcessingError, match="failed after 3 attempts"):
        await adapter.handle(payload, signature, secret)


def test_webhook_adapter_parse_payload():
    adapter = MockWebhookAdapter()
    result = adapter._parse_payload(b'{"key": "value"}')
    assert result == {"key": "value"}


def test_webhook_adapter_parse_payload_invalid_json():
    adapter = MockWebhookAdapter()
    with pytest.raises(WebhookProcessingError, match="Invalid webhook payload"):
        adapter._parse_payload(b"not json")


@pytest.mark.asyncio
async def test_mock_webhook_adapter_verify_signature():
    adapter = MockWebhookAdapter()
    payload = b'{"id": "1"}'
    secret = "secret"
    signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert await adapter.verify_signature(payload, signature, secret) is True
    assert await adapter.verify_signature(payload, "bad", secret) is False


@pytest.mark.asyncio
async def test_mock_webhook_adapter_process_event():
    adapter = MockWebhookAdapter()
    result = await adapter.process_event({"id": "1", "data": "x"}, "evt-1")
    assert result["status"] == "processed"
    assert result["adapter"] == "mock"


def test_webhook_adapter_abstract():
    with pytest.raises(TypeError):
        WebhookAdapter()
