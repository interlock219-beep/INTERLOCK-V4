from __future__ import annotations

import hashlib
import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.infrastructure.config.settings import get_settings
from app.infrastructure.integrations.webhook_adapter import WebhookAdapter
from app.infrastructure.logging.audit_logger import log_security_event
from app.infrastructure.observability.metrics import metrics

router = APIRouter(tags=["Webhook"])


def _get_webhook_adapter() -> WebhookAdapter:
    from app.infrastructure.integrations.webhook_adapter import MockWebhookAdapter
    return MockWebhookAdapter()


def _verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 webhook signature."""
    if not signature:
        return False
    expected = hmac.new(
        secret.encode("utf-8") if secret else b"",
        payload,
        hashlib.sha256,
    ).hexdigest()
    expected_prefix = f"sha256={expected}"
    if signature.startswith("sha256="):
        return hmac.compare_digest(signature, expected_prefix)
    return hmac.compare_digest(signature, expected)


@router.post("/ingest")
async def ingest_webhook(
    request: Request,
    adapter: Annotated[WebhookAdapter, Depends(_get_webhook_adapter)],
) -> dict[str, object]:
    settings = get_settings()
    secret = settings.webhook_hmac_secret or ""
    payload = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not signature:
        raise HTTPException(status_code=400, detail="Missing X-Hub-Signature-256 header")

    if not _verify_webhook_signature(payload, signature, secret):
        log_security_event(
            "webhook_signature_invalid",
            correlation_id=getattr(request.state, "correlation_id", ""),
        )
        metrics.increment_security_exception("webhook_signature_invalid")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    correlation_id = getattr(request.state, "correlation_id", "")
    timestamp = request.headers.get("X-Hub-Timestamp", "")
    if timestamp:
        try:
            import time
            event_time = int(timestamp)
            now = int(time.time())
            if abs(now - event_time) > 300:
                raise HTTPException(
                    status_code=401,
                    detail="Webhook timestamp outside acceptable window",
                )
        except (ValueError, TypeError):
            pass

    try:
        result = await adapter.handle(
            payload, signature, secret, idempotency_key=correlation_id or None
        )
    except Exception as exc:
        log_security_event(
            "webhook_ingest_failed",
            correlation_id=correlation_id,
            error=str(exc),
        )
        metrics.increment_security_exception("webhook_ingest_failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log_security_event(
        "webhook_ingested",
        correlation_id=correlation_id,
        event_id=result.get("event_id", ""),
        adapter=result.get("adapter", ""),
    )
    metrics.increment_security_exception("webhook_ingested")
    return result
