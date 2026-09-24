from __future__ import annotations

import pytest

from app.infrastructure.observability.opentelemetry_integration import (
    OpenTelemetryIntegration,
    otel,
)


def test_default_instance_not_enabled_without_packages():
    assert otel.enabled is False


def test_record_counter_noop_when_disabled():
    otel.record_counter("test.counter", value=5)
    assert otel.enabled is False


def test_record_histogram_noop_when_disabled():
    otel.record_histogram("test.histogram", value=0.5)
    assert otel.enabled is False


def test_start_span_returns_noop_when_disabled():
    with otel.start_span("test.span") as span:
        span.set_attribute("key", "value")
    assert otel.enabled is False


def test_shutdown_noop_when_disabled():
    otel.shutdown()
    assert otel.enabled is False


def test_custom_service_name():
    integration = OpenTelemetryIntegration(service_name="custom-service")
    assert integration._service_name == "custom-service"
