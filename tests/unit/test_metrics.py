from __future__ import annotations

from app.infrastructure.observability.metrics import SecurityMetrics


def test_metrics_increment_authorization_denial():
    metrics = SecurityMetrics()
    metrics.increment_authorization_denial("rate_limit")
    snapshot = metrics.get_metrics_snapshot()
    assert snapshot["authorization_denials"]["rate_limit"] == 1
    assert snapshot["authorization_denials_total"] == 1


def test_metrics_increment_hitl_event():
    metrics = SecurityMetrics()
    metrics.increment_hitl_event("approval_requested")
    snapshot = metrics.get_metrics_snapshot()
    assert snapshot["hitl_events"]["approval_requested"] == 1


def test_metrics_increment_policy_decision():
    metrics = SecurityMetrics()
    metrics.increment_policy_decision("allow")
    snapshot = metrics.get_metrics_snapshot()
    assert snapshot["policy_decisions"]["allow"] == 1


def test_metrics_increment_suspicious_tool_call():
    metrics = SecurityMetrics()
    metrics.increment_suspicious_tool_call("sql_injection")
    snapshot = metrics.get_metrics_snapshot()
    assert snapshot["suspicious_tool_calls"]["sql_injection"] == 1


def test_metrics_increment_authentication_failure():
    metrics = SecurityMetrics()
    metrics.increment_authentication_failure("invalid_password")
    snapshot = metrics.get_metrics_snapshot()
    assert snapshot["authentication_failures"]["invalid_password"] == 1


def test_metrics_increment_security_exception():
    metrics = SecurityMetrics()
    metrics.increment_security_exception("containment_executed")
    snapshot = metrics.get_metrics_snapshot()
    assert snapshot["security_exceptions"]["containment_executed"] == 1


def test_metrics_increment_execution_tokens():
    metrics = SecurityMetrics()
    metrics.increment_execution_tokens_issued()
    metrics.increment_execution_tokens_consumed()
    metrics.increment_execution_tokens_replayed()
    snapshot = metrics.get_metrics_snapshot()
    assert snapshot["execution_tokens_issued"] == 1
    assert snapshot["execution_tokens_consumed"] == 1
    assert snapshot["execution_tokens_replayed"] == 1


def test_metrics_increment_causal_graph_query():
    metrics = SecurityMetrics()
    metrics.increment_causal_graph_query("upstream")
    snapshot = metrics.get_metrics_snapshot()
    assert snapshot["causal_graph_queries"]["upstream"] == 1


def test_metrics_record_containment_cascade_depth():
    metrics = SecurityMetrics()
    metrics.record_containment_cascade_depth(3)
    snapshot = metrics.get_metrics_snapshot()
    assert snapshot["containment_cascade_depth"]["3"] == 1


def test_metrics_increment_recovery_adapter_call():
    metrics = SecurityMetrics()
    metrics.increment_recovery_adapter_call("database")
    snapshot = metrics.get_metrics_snapshot()
    assert snapshot["recovery_adapter_calls"]["database"] == 1


def test_metrics_record_durations():
    metrics = SecurityMetrics()
    metrics.record_blast_radius_calculation(0.5)
    metrics.record_recovery_preview_duration(0.3)
    snapshot = metrics.get_metrics_snapshot()
    assert snapshot["blast_radius_calculation_durations"] == [0.5]
    assert snapshot["recovery_preview_durations"] == [0.3]


def test_metrics_reset():
    metrics = SecurityMetrics()
    metrics.increment_authorization_denial("test")
    metrics.reset()
    snapshot = metrics.get_metrics_snapshot()
    assert snapshot["authorization_denials_total"] == 0
    assert snapshot["execution_tokens_issued"] == 0


def test_metrics_thread_safety():
    metrics = SecurityMetrics()
    import threading

    def increment():
        for _ in range(100):
            metrics.increment_authorization_denial("thread")

    threads = [threading.Thread(target=increment) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    snapshot = metrics.get_metrics_snapshot()
    assert snapshot["authorization_denials"]["thread"] == 500
    assert snapshot["authorization_denials_total"] == 500
