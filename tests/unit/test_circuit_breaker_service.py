from __future__ import annotations

import time

import pytest

from app.domain.services.circuit_breaker_service import (
    CircuitBreakerService,
    CircuitState,
)


@pytest.fixture
def service():
    return CircuitBreakerService(
        failure_threshold=3,
        recovery_timeout_seconds=1.0,
        success_threshold=2,
    )


def test_initial_state_is_closed(service):
    decision = service.allow_request("resource-1")
    assert decision["allowed"] is True
    assert decision["state"] == CircuitState.CLOSED.value


def test_opens_after_threshold_failures(service):
    for _ in range(3):
        service.record_failure("resource-1")

    state = service.get_state("resource-1")
    assert state["state"] == CircuitState.OPEN.value

    decision = service.allow_request("resource-1")
    assert decision["allowed"] is False
    assert decision["state"] == CircuitState.OPEN.value


def test_half_open_after_recovery_timeout(service):
    for _ in range(3):
        service.record_failure("resource-1")

    decision = service.allow_request("resource-1")
    assert decision["allowed"] is False

    time.sleep(1.1)

    decision = service.allow_request("resource-1")
    assert decision["allowed"] is True
    assert decision["state"] == CircuitState.HALF_OPEN.value


def test_closes_after_success_threshold_in_half_open(service):
    for _ in range(3):
        service.record_failure("resource-1")

    time.sleep(1.1)
    service.allow_request("resource-1")

    service.record_success("resource-1")
    state = service.get_state("resource-1")
    assert state["state"] == CircuitState.HALF_OPEN.value

    service.record_success("resource-1")
    state = service.get_state("resource-1")
    assert state["state"] == CircuitState.CLOSED.value


def test_reopens_on_failure_in_half_open(service):
    for _ in range(3):
        service.record_failure("resource-1")

    time.sleep(1.1)
    service.allow_request("resource-1")

    service.record_failure("resource-1")
    state = service.get_state("resource-1")
    assert state["state"] == CircuitState.OPEN.value


def test_success_does_not_close_below_threshold(service):
    service.record_success("resource-1")
    state = service.get_state("resource-1")
    assert state["state"] == CircuitState.CLOSED.value


def test_reset_clears_state(service):
    for _ in range(3):
        service.record_failure("resource-1")

    service.reset("resource-1")
    state = service.get_state("resource-1")
    assert state["state"] == CircuitState.CLOSED.value
    assert state["failure_count"] == 0


def test_get_state_returns_counts(service):
    service.record_failure("resource-1")
    service.record_failure("resource-1")

    state = service.get_state("resource-1")
    assert state["failure_count"] == 2
    assert state["success_count"] == 0
    assert state["resource"] == "resource-1"


def test_retry_after_seconds_positive_when_open(service):
    for _ in range(3):
        service.record_failure("resource-1")

    decision = service.allow_request("resource-1")
    assert decision["retry_after_seconds"] > 0
