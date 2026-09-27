from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.domain.value_objects.authorization_context import AuthorizationContext
from app.domain.value_objects.authorization_decision import AuthorizationDecision
from app.infrastructure.config.settings import get_settings


class ConditionalRuntimeAuthorizationEvaluator:
    """Evaluates runtime conditions for authorization decisions.

    All conditions are configurable via settings.  Fails closed on unknown
    or missing conditions.
    """

    def __init__(self, settings: Any | None = None) -> None:
        self._settings = settings or get_settings()

    def evaluate_conditions(
        self, context: AuthorizationContext
    ) -> tuple[AuthorizationDecision, str]:
        """Evaluate all configured runtime conditions.

        Returns the most restrictive decision across all conditions.
        """
        time_decision, time_reason = self._check_time_of_day(context)
        if time_decision != AuthorizationDecision.ALLOW:
            return time_decision, time_reason

        ip_decision, ip_reason = self._check_ip_range(context)
        if ip_decision != AuthorizationDecision.ALLOW:
            return ip_decision, ip_reason

        session_age_decision, session_age_reason = self._check_session_age(context)
        if session_age_decision != AuthorizationDecision.ALLOW:
            return session_age_decision, session_age_reason

        concurrent_decision, concurrent_reason = self._check_concurrent_sessions(context)
        if concurrent_decision != AuthorizationDecision.ALLOW:
            return concurrent_decision, concurrent_reason

        return AuthorizationDecision.ALLOW, "All runtime conditions satisfied"

    def _check_time_of_day(
        self, context: AuthorizationContext
    ) -> tuple[AuthorizationDecision, str]:
        time_windows = getattr(self._settings, "authorization_time_windows", [])
        if not time_windows:
            return AuthorizationDecision.ALLOW, "No time windows configured"
        now = datetime.now(UTC)
        current_time = now.strftime("%H:%M")
        for window in time_windows:
            start = window.get("start", "")
            end = window.get("end", "")
            if not start or not end:
                continue
            if start <= current_time <= end:
                return AuthorizationDecision.ALLOW, "Within allowed time window"
        return AuthorizationDecision.DENY, "Outside allowed time window"

    def _check_ip_range(self, context: AuthorizationContext) -> tuple[AuthorizationDecision, str]:
        allowed_ips = getattr(self._settings, "authorization_allowed_ips", [])
        denied_ips = getattr(self._settings, "authorization_denied_ips", [])
        if not allowed_ips and not denied_ips:
            return AuthorizationDecision.ALLOW, "No IP restrictions configured"
        client_ip = getattr(context, "client_ip", None)
        if client_ip is None:
            return AuthorizationDecision.DENY, "Client IP is unknown"
        if denied_ips and client_ip in denied_ips:
            return AuthorizationDecision.DENY, f"Client IP {client_ip} is denied"
        if allowed_ips and client_ip not in allowed_ips:
            return AuthorizationDecision.DENY, f"Client IP {client_ip} is not in allowed range"
        return AuthorizationDecision.ALLOW, "IP address is within allowed range"

    def _check_session_age(
        self, context: AuthorizationContext
    ) -> tuple[AuthorizationDecision, str]:
        max_session_age = getattr(self._settings, "authorization_max_session_age_seconds", None)
        if max_session_age is None:
            return AuthorizationDecision.ALLOW, "No session age limit configured"
        session_created_at = getattr(context, "session_created_at", None)
        if session_created_at is None:
            return AuthorizationDecision.DENY, "Session creation time is unknown"
        now = datetime.now(UTC)
        session_age = (now - session_created_at).total_seconds()
        if session_age > max_session_age:
            return AuthorizationDecision.DENY, (
                f"Session age {session_age}s exceeds limit {max_session_age}s"
            )
        return AuthorizationDecision.ALLOW, "Session age is within limit"

    def _check_concurrent_sessions(
        self, context: AuthorizationContext
    ) -> tuple[AuthorizationDecision, str]:
        max_concurrent = getattr(self._settings, "authorization_max_concurrent_sessions", None)
        if max_concurrent is None:
            return AuthorizationDecision.ALLOW, "No concurrent session limit configured"
        active_sessions = getattr(context, "active_sessions", None)
        if active_sessions is None:
            return AuthorizationDecision.DENY, "Active session count is unknown"
        if active_sessions > max_concurrent:
            return AuthorizationDecision.DENY, (
                f"Active sessions {active_sessions} exceeds limit {max_concurrent}"
            )
        return AuthorizationDecision.ALLOW, "Concurrent session count is within limit"
