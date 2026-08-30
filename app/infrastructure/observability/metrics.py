import threading
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any


class SecurityMetrics:
    """Thread-safe security metrics collector.

    Tracks counters for authorization, HITL, policy, authentication,
    and execution token events.  Designed for observability dashboards
    and compliance reporting.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._authorization_denials: dict[str, int] = defaultdict(int)
        self._hitl_events: dict[str, int] = defaultdict(int)
        self._policy_decisions: dict[str, int] = defaultdict(int)
        self._suspicious_tool_calls: dict[str, int] = defaultdict(int)
        self._authentication_failures: dict[str, int] = defaultdict(int)
        self._security_exceptions: dict[str, int] = defaultdict(int)
        self._execution_tokens_issued: int = 0
        self._execution_tokens_consumed: int = 0
        self._execution_tokens_replayed: int = 0
        self._causal_graph_queries: dict[str, int] = defaultdict(int)
        self._containment_cascade_depth: dict[str, int] = defaultdict(int)
        self._recovery_adapter_calls: dict[str, int] = defaultdict(int)
        self._blast_radius_calculation_durations: list[float] = []
        self._recovery_preview_durations: list[float] = []

    def increment_authorization_denial(self, reason: str) -> None:
        with self._lock:
            self._authorization_denials[reason] += 1

    def increment_hitl_event(self, event_type: str) -> None:
        with self._lock:
            self._hitl_events[event_type] += 1

    def increment_policy_decision(self, effect: str) -> None:
        with self._lock:
            self._policy_decisions[effect] += 1

    def increment_suspicious_tool_call(self, tool_type: str) -> None:
        with self._lock:
            self._suspicious_tool_calls[tool_type] += 1

    def increment_authentication_failure(self, reason: str) -> None:
        with self._lock:
            self._authentication_failures[reason] += 1

    def increment_security_exception(self, exception_type: str) -> None:
        with self._lock:
            self._security_exceptions[exception_type] += 1

    def increment_execution_tokens_issued(self) -> None:
        with self._lock:
            self._execution_tokens_issued += 1

    def increment_execution_tokens_consumed(self) -> None:
        with self._lock:
            self._execution_tokens_consumed += 1

    def increment_execution_tokens_replayed(self) -> None:
        with self._lock:
            self._execution_tokens_replayed += 1

    def increment_causal_graph_query(self, query_type: str) -> None:
        with self._lock:
            self._causal_graph_queries[query_type] += 1

    def record_containment_cascade_depth(self, depth: int) -> None:
        with self._lock:
            self._containment_cascade_depth[str(depth)] += 1

    def increment_recovery_adapter_call(self, adapter_name: str) -> None:
        with self._lock:
            self._recovery_adapter_calls[adapter_name] += 1

    def record_blast_radius_calculation(self, duration_seconds: float) -> None:
        with self._lock:
            self._blast_radius_calculation_durations.append(duration_seconds)

    def record_recovery_preview_duration(self, duration_seconds: float) -> None:
        with self._lock:
            self._recovery_preview_durations.append(duration_seconds)

    def get_metrics_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "timestamp": datetime.now(tz=UTC).isoformat(),
                "authorization_denials": dict(self._authorization_denials),
                "authorization_denials_total": sum(self._authorization_denials.values()),
                "hitl_events": dict(self._hitl_events),
                "hitl_events_total": sum(self._hitl_events.values()),
                "policy_decisions": dict(self._policy_decisions),
                "policy_decisions_total": sum(self._policy_decisions.values()),
                "suspicious_tool_calls": dict(self._suspicious_tool_calls),
                "suspicious_tool_calls_total": sum(self._suspicious_tool_calls.values()),
                "authentication_failures": dict(self._authentication_failures),
                "authentication_failures_total": sum(self._authentication_failures.values()),
                "security_exceptions": dict(self._security_exceptions),
                "security_exceptions_total": sum(self._security_exceptions.values()),
                "execution_tokens_issued": self._execution_tokens_issued,
                "execution_tokens_consumed": self._execution_tokens_consumed,
                "execution_tokens_replayed": self._execution_tokens_replayed,
                "causal_graph_queries": dict(self._causal_graph_queries),
                "causal_graph_queries_total": sum(self._causal_graph_queries.values()),
                "containment_cascade_depth": dict(self._containment_cascade_depth),
                "recovery_adapter_calls": dict(self._recovery_adapter_calls),
                "recovery_adapter_calls_total": sum(self._recovery_adapter_calls.values()),
                "blast_radius_calculation_durations": list(
                    self._blast_radius_calculation_durations
                ),
                "recovery_preview_durations": list(self._recovery_preview_durations),
            }

    def reset(self) -> None:
        with self._lock:
            self._authorization_denials.clear()
            self._hitl_events.clear()
            self._policy_decisions.clear()
            self._suspicious_tool_calls.clear()
            self._authentication_failures.clear()
            self._security_exceptions.clear()
            self._execution_tokens_issued = 0
            self._execution_tokens_consumed = 0
            self._execution_tokens_replayed = 0
            self._causal_graph_queries.clear()
            self._containment_cascade_depth.clear()
            self._recovery_adapter_calls.clear()
            self._blast_radius_calculation_durations.clear()
            self._recovery_preview_durations.clear()


metrics = SecurityMetrics()
