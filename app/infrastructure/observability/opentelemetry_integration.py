from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("intentlock.observability.otel")


class OpenTelemetryIntegration:
    """Optional OpenTelemetry integration for Interlock.

    Provides a consistent interface for distributed tracing and metrics
    export. Gracefully degrades when OpenTelemetry packages are not
    installed, so the core application does not require them.
    """

    def __init__(self, service_name: str = "intentlock") -> None:
        self._service_name = service_name
        self._tracer = None
        self._meter = None
        self._enabled = False
        self._try_init()

    def _try_init(self) -> None:
        try:
            from opentelemetry import metrics, trace
            from opentelemetry.sdk.trace import TracerProvider

            trace.set_tracer_provider(TracerProvider())
            self._tracer = trace.get_tracer(self._service_name)
            self._meter = metrics.get_meter(self._service_name)
            self._enabled = True
            logger.info("OpenTelemetry initialized for %s", self._service_name)
        except ImportError:
            logger.debug("OpenTelemetry packages not installed; tracing disabled")

    @property
    def enabled(self) -> bool:
        return self._enabled

    def start_span(self, name: str, attributes: dict[str, Any] | None = None) -> Any:
        """Start a new trace span if OTel is enabled."""
        if not self._enabled or self._tracer is None:
            return _NoOpSpan()
        span = self._tracer.start_as_current_span(name)
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        return span

    def record_counter(
        self,
        name: str,
        value: int = 1,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Record a counter metric if OTel is enabled."""
        if not self._enabled or self._meter is None:
            return
        try:
            counter = self._meter.create_counter(name)
            counter.add(value, attributes or {})
        except Exception as exc:
            logger.debug("Failed to record counter %s: %s", name, exc)

    def record_histogram(
        self,
        name: str,
        value: float,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Record a histogram metric if OTel is enabled."""
        if not self._enabled or self._meter is None:
            return
        try:
            histogram = self._meter.create_histogram(name)
            histogram.record(value, attributes or {})
        except Exception as exc:
            logger.debug("Failed to record histogram %s: %s", name, exc)

    def shutdown(self) -> None:
        """Flush and shutdown OTel providers."""
        if not self._enabled:
            return
        try:
            from opentelemetry.trace import get_tracer_provider

            provider = get_tracer_provider()
            if hasattr(provider, "shutdown"):
                provider.shutdown()
        except Exception as exc:
            logger.debug("OTel shutdown error: %s", exc)


class _NoOpSpan:
    """No-op span for when OpenTelemetry is not available."""

    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, status: Any) -> None:
        pass


otel = OpenTelemetryIntegration()
