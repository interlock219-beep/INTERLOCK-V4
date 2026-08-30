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
    correlation_id = getattr(request.state, "correlation_id", "")
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
