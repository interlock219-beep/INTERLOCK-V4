from __future__ import annotations

import hashlib
import hmac
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _sign(payload: bytes, secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8") if secret else b"",
        payload,
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def test_webhook_missing_signature():
    response = client.post("/api/v1/webhook/ingest", content=b"{}")
    assert response.status_code == 400
    assert "Missing X-Hub-Signature-256 header" in response.json()["detail"]


def test_webhook_invalid_signature():
    response = client.post(
        "/api/v1/webhook/ingest",
        content=b"{}",
        headers={"X-Hub-Signature-256": "sha256=invalid"},
    )
    assert response.status_code == 401


def test_webhook_valid_signature():
    payload = b'{"event": "test"}'
    secret = "test-secret"
    signature = _sign(payload, secret)

    response = client.post(
        "/api/v1/webhook/ingest",
        content=payload,
        headers={"X-Hub-Signature-256": signature},
    )
    assert response.status_code == 200


def test_webhook_stale_timestamp():
    payload = b'{"event": "test"}'
    secret = "test-secret"
    signature = _sign(payload, secret)

    old_ts = str(int(time.time()) - 600)
    response = client.post(
        "/api/v1/webhook/ingest",
        content=payload,
        headers={
            "X-Hub-Signature-256": signature,
            "X-Hub-Timestamp": old_ts,
        },
    )
    assert response.status_code == 401
    assert "outside acceptable window" in response.json()["detail"]
