import hashlib
import hmac
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class WebhookProcessingError(Exception):
    pass


class WebhookAdapter(ABC):
    @abstractmethod
    async def verify_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        pass

    @abstractmethod
    async def process_event(self, payload: dict[str, Any], event_id: str) -> dict[str, Any]:
        pass

    async def handle(
        self,
        payload: bytes,
        signature: str,
        secret: str,
        *,
        idempotency_key: str | None = None,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        if not await self.verify_signature(payload, signature, secret):
            raise WebhookProcessingError("Invalid webhook signature")
        parsed = self._parse_payload(payload)
        event_id = idempotency_key or parsed.get("id", "")
        if not event_id:
            raise WebhookProcessingError("Webhook event missing id")
        for attempt in range(max_retries):
            try:
                return await self.process_event(parsed, str(event_id))
            except WebhookProcessingError:
                raise
            except Exception as exc:
                logger.warning("Webhook processing attempt %d failed: %s", attempt + 1, exc)
                if attempt == max_retries - 1:
                    raise WebhookProcessingError(
                        f"Webhook processing failed after {max_retries} attempts: {exc}"
                    ) from exc
                time.sleep(2 ** attempt)
        return {}

    @staticmethod
    def _parse_payload(payload: bytes) -> dict[str, Any]:
        import json
        try:
            return json.loads(payload)  # type: ignore[no-any-return]
        except (ValueError, TypeError) as exc:
            raise WebhookProcessingError("Invalid webhook payload") from exc


class MockWebhookAdapter(WebhookAdapter):
    async def verify_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def process_event(self, payload: dict[str, Any], event_id: str) -> dict[str, Any]:
        return {
            "event_id": event_id,
            "status": "processed",
            "adapter": "mock",
            "payload_keys": list(payload.keys()),
        }
