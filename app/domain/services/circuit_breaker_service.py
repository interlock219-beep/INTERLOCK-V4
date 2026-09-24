from __future__ import annotations

import logging
import time
from enum import StrEnum
from typing import Any

logger = logging.getLogger("intentlock.circuit_breaker")


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerService:
    """Thread-safe circuit breaker for external calls.

    States:
    - CLOSED: normal operation, calls pass through
    - OPEN: failure threshold exceeded, calls fail fast
    - HALF_OPEN: after recovery timeout, allow one test call

    Capabilities:
    - Configurable failure threshold and recovery timeout
    - Per-resource circuit state tracking
    - Success threshold for half-open recovery
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
        success_threshold: int = 2,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout_seconds
        self._success_threshold = success_threshold
        self._states: dict[str, CircuitState] = {}
        self._failure_counts: dict[str, int] = {}
        self._success_counts: dict[str, int] = {}
        self._last_failure_time: dict[str, float] = {}
        self._opened_at: dict[str, float] = {}

    def allow_request(self, resource: str) -> dict[str, Any]:
        """Check whether a request to *resource* is allowed.

        Returns a decision dict with the current state.
        """
        state = self._get_state(resource)
        if state == CircuitState.OPEN:
            if self._should_half_open(resource):
                self._transition(resource, CircuitState.HALF_OPEN)
                return {
                    "allowed": True,
                    "state": CircuitState.HALF_OPEN.value,
                    "resource": resource,
                }
            return {
                "allowed": False,
                "state": CircuitState.OPEN.value,
                "resource": resource,
                "retry_after_seconds": self._retry_after(resource),
            }
        if state == CircuitState.HALF_OPEN:
            return {
                "allowed": True,
                "state": CircuitState.HALF_OPEN.value,
                "resource": resource,
            }
        return {
            "allowed": True,
            "state": CircuitState.CLOSED.value,
            "resource": resource,
        }

    def record_success(self, resource: str) -> None:
        """Record a successful call for *resource*."""
        state = self._get_state(resource)
        if state == CircuitState.HALF_OPEN:
            self._success_counts[resource] = self._success_counts.get(resource, 0) + 1
            if self._success_counts[resource] >= self._success_threshold:
                count = self._success_counts[resource]
                self._transition(resource, CircuitState.CLOSED)
                self._reset_counts(resource)
                logger.info(
                    "Circuit closed for %s after %d successes",
                    resource, count,
                )
            return
        self._reset_counts(resource)

    def record_failure(self, resource: str) -> None:
        """Record a failed call for *resource*."""
        state = self._get_state(resource)
        if state == CircuitState.HALF_OPEN:
            self._transition(resource, CircuitState.OPEN)
            self._opened_at[resource] = time.time()
            logger.warning("Circuit re-opened for %s after half-open failure", resource)
            return
        self._failure_counts[resource] = self._failure_counts.get(resource, 0) + 1
        if self._failure_counts[resource] >= self._failure_threshold:
            self._transition(resource, CircuitState.OPEN)
            self._opened_at[resource] = time.time()
            logger.warning(
                "Circuit opened for %s after %d failures",
                resource, self._failure_counts[resource],
            )

    def get_state(self, resource: str) -> dict[str, Any]:
        """Get current circuit state for a resource."""
        state = self._get_state(resource)
        return {
            "resource": resource,
            "state": state.value,
            "failure_count": self._failure_counts.get(resource, 0),
            "success_count": self._success_counts.get(resource, 0),
            "last_failure_at": self._last_failure_time.get(resource),
            "opened_at": self._opened_at.get(resource),
        }

    def reset(self, resource: str) -> None:
        """Reset circuit state for a resource."""
        self._states.pop(resource, None)
        self._failure_counts.pop(resource, None)
        self._success_counts.pop(resource, None)
        self._last_failure_time.pop(resource, None)
        self._opened_at.pop(resource, None)
        logger.info("Circuit reset for %s", resource)

    def _get_state(self, resource: str) -> CircuitState:
        return self._states.get(resource, CircuitState.CLOSED)

    def _transition(self, resource: str, new_state: CircuitState) -> None:
        old_state = self._get_state(resource)
        self._states[resource] = new_state
        logger.debug(
            "Circuit transition: %s %s -> %s", resource, old_state.value, new_state.value,
        )

    def _should_half_open(self, resource: str) -> bool:
        opened_at = self._opened_at.get(resource, 0)
        return (time.time() - opened_at) >= self._recovery_timeout

    def _retry_after(self, resource: str) -> float:
        opened_at = self._opened_at.get(resource, 0)
        remaining = self._recovery_timeout - (time.time() - opened_at)
        return max(remaining, 0.0)

    def _reset_counts(self, resource: str) -> None:
        self._failure_counts.pop(resource, None)
        self._success_counts.pop(resource, None)
        self._last_failure_time.pop(resource, None)
