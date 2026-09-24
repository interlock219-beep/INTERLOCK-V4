"""Domain C behavioral security tests for features 21-30."""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.services.behavioral_security_service import BehavioralSecurityService
from app.domain.services.session_baseline_service import SessionBaseline, SessionBaselineService


def _make_action(tool="search", resource="res-1", action="read", timestamp=None):
    return {
        "tool": tool,
        "resource": resource,
        "action": action,
        "timestamp": timestamp or 1700000000,
    }


def test_establish_baseline_creates_profile():
    service = BehavioralSecurityService()
    actions = [_make_action("search", "res-1", "read"), _make_action("write", "res-2", "write")]
    baseline = service.establish_baseline("agent-1", "session-1", actions)
    assert baseline["agent_id"] == "agent-1"
    assert baseline["session_id"] == "session-1"
    assert "typical_tools" in baseline
    assert "typical_resources" in baseline


def test_establish_baseline_computes_statistics():
    service = BehavioralSecurityService()
    base_ts = 1700000000
    actions = [
        _make_action("search", "res-1", "read", base_ts),
        _make_action("search", "res-1", "read", base_ts + 10),
        _make_action("search", "res-1", "read", base_ts + 20),
    ]
    baseline = service.establish_baseline("agent-1", "session-1", actions)
    assert baseline["total_actions"] == 3
    assert "avg_velocity" in baseline
    assert "velocity_stddev" in baseline


def test_compare_to_baseline_detects_new_tool():
    service = BehavioralSecurityService()
    actions = [_make_action("search", "res-1", "read")]
    baseline = service.establish_baseline("agent-1", "session-1", actions)
    new_actions = [_make_action("drop_table", "res-1", "delete")]
    signals = service.compare_to_baseline("agent-1", "session-1", new_actions)
    assert len(signals) == 1
    assert signals[0]["signal_type"] == "new_tool_usage"


def test_compare_to_baseline_detects_new_resource():
    service = BehavioralSecurityService()
    actions = [_make_action("search", "res-1", "read")]
    baseline = service.establish_baseline("agent-1", "session-1", actions)
    new_actions = [_make_action("search", "res-99", "read")]
    signals = service.compare_to_baseline("agent-1", "session-1", new_actions)
    assert len(signals) == 1
    assert signals[0]["signal_type"] == "new_resource_targeting"


def test_detect_drift_high_score_when_divergent():
    service = BehavioralSecurityService()
    baseline = {
        "typical_tools": ["search"],
        "typical_resources": ["res-1"],
        "avg_velocity": 5.0,
        "typical_action_types": ["read"],
    }
    current = {
        "tools_used": ["drop_table", "delete"],
        "resources_targeted": ["res-1", "res-2", "res-3"],
        "velocity": 50.0,
        "action_types": ["delete", "drop"],
    }
    result = service.detect_drift("agent-1", "session-1", baseline, current)
    assert result["drift_score"] > 0.5
    assert result["is_drifted"] is True


def test_detect_drift_low_score_when_similar():
    service = BehavioralSecurityService()
    baseline = {
        "typical_tools": ["search", "read"],
        "typical_resources": ["res-1", "res-2"],
        "avg_velocity": 5.0,
        "typical_action_types": ["read"],
    }
    current = {
        "tools_used": ["search"],
        "resources_targeted": ["res-1"],
        "velocity": 6.0,
        "action_types": ["read"],
    }
    result = service.detect_drift("agent-1", "session-1", baseline, current)
    assert result["drift_score"] < 0.5
    assert result["is_drifted"] is False


def test_detect_drift_generates_signals():
    service = BehavioralSecurityService()
    baseline = {"typical_tools": ["search"], "typical_resources": ["res-1"], "avg_velocity": 5.0, "typical_action_types": ["read"]}
    current = {"tools_used": ["drop_table"], "resources_targeted": ["res-1"], "velocity": 50.0, "action_types": ["delete"]}
    result = service.detect_drift("agent-1", "session-1", baseline, current)
    assert len(result["drift_signals"]) > 0
    assert result["drift_confidence"] >= 0.0


def test_detect_action_sequence_anomaly_unknown_sequence():
    service = BehavioralSecurityService()
    seq = ["read", "write", "delete", "drop"]
    known = [["read", "write"], ["search", "read"]]
    result = service.detect_action_sequence_anomaly(seq, known)
    assert result["is_anomalous"] is True
    assert result["anomaly_score"] >= 0.5


def test_detect_action_sequence_anomaly_known_sequence():
    service = BehavioralSecurityService()
    seq = ["read", "write"]
    known = [["read", "write"], ["search", "read"]]
    result = service.detect_action_sequence_anomaly(seq, known)
    assert result["is_anomalous"] is False
    assert result["anomaly_score"] < 0.5


def test_detect_unusual_tool_selection_new_tool():
    service = BehavioralSecurityService()
    result = service.detect_unusual_tool_selection(
        ["drop_table"], {"search", "read"}, {"search", "read", "drop_table"}
    )
    assert result["unusual_tools"] == ["drop_table"]
    assert result["risk_multiplier"] > 1.0


def test_detect_unusual_tool_selection_known_tool():
    service = BehavioralSecurityService()
    result = service.detect_unusual_tool_selection(["search"], {"search", "read"}, {"search", "read"})
    assert result["unusual_tools"] == []
    assert result["risk_multiplier"] == 1.0


def test_detect_unusual_target_selection_new_resource():
    service = BehavioralSecurityService()
    result = service.detect_unusual_target_selection(["res-99"], {"res-1", "res-2"})
    assert result["unusual_targets"] == ["res-99"]
    assert result["risk_multiplier"] > 1.0


def test_detect_unusual_target_selection_known_resource():
    service = BehavioralSecurityService()
    result = service.detect_unusual_target_selection(["res-1"], {"res-1", "res-2"})
    assert result["unusual_targets"] == []
    assert result["risk_multiplier"] == 1.0


def test_detect_unusual_velocity_high_z_score():
    service = BehavioralSecurityService()
    result = service.detect_unusual_velocity(100.0, 10.0, 5.0)
    assert result["is_anomalous"] is True
    assert result["velocity_z_score"] > 3.0


def test_detect_unusual_velocity_normal_z_score():
    service = BehavioralSecurityService()
    result = service.detect_unusual_velocity(11.0, 10.0, 5.0)
    assert result["is_anomalous"] is False


def test_detect_privilege_escalation_scope_increase():
    service = BehavioralSecurityService()
    result = service.detect_privilege_escalation("admin", ["read", "write"], [])
    assert result["escalation_detected"] is True
    assert len(result["escalation_details"]) > 0


def test_detect_privilege_escalation_no_escalation():
    service = BehavioralSecurityService()
    result = service.detect_privilege_escalation("read", ["read", "write"], [])
    assert result["escalation_detected"] is False


def test_detect_runaway_behavior_repeated_actions():
    service = BehavioralSecurityService()
    actions = [_make_action("drop_table", "res-1", "delete", 1700000000 + i) for i in range(6)]
    result = service.detect_runaway_behavior(actions)
    assert result["is_runaway"] is True
    assert result["repetition_count"] >= 5


def test_detect_runaway_behavior_normal_rate():
    service = BehavioralSecurityService()
    actions = [_make_action("search", "res-1", "read", 1700000000 + i) for i in range(3)]
    result = service.detect_runaway_behavior(actions)
    assert result["is_runaway"] is False


def test_detect_autonomous_escalation_unauthorized():
    service = BehavioralSecurityService()
    action_history = [
        {"action_type": "grant_admin", "scope": "admin", "timestamp": 1700000000},
        {"action_type": "delete", "scope": "admin", "timestamp": 1700000001},
    ]
    authorization_history = [
        {"scope": "read", "authorized": True},
    ]
    result = service.detect_autonomous_escalation(action_history, authorization_history)
    assert result["escalation_detected"] is True
    assert len(result["escalation_chain"]) > 0


def test_detect_autonomous_escalation_authorized():
    service = BehavioralSecurityService()
    action_history = [
        {"action_type": "grant_admin", "scope": "admin", "timestamp": 1700000000},
    ]
    authorization_history = [
        {"scope": "admin", "authorized": True},
    ]
    result = service.detect_autonomous_escalation(action_history, authorization_history)
    assert result["escalation_detected"] is False


def test_detect_intent_action_mismatch_conflict():
    service = BehavioralSecurityService()
    actions = [_make_action("delete", "res-1", "delete"), _make_action("drop_table", "res-2", "delete")]
    result = service.detect_intent_action_mismatch("read data for analysis", actions)
    assert result["mismatch_detected"] is True
    assert result["mismatch_score"] > 0.0
    assert len(result["evidence"]) > 0


def test_detect_intent_action_match_aligned():
    service = BehavioralSecurityService()
    actions = [_make_action("search", "res-1", "read")]
    result = service.detect_intent_action_mismatch("search and read data", actions)
    assert result["mismatch_detected"] is False


def test_session_baseline_service_establish():
    service = SessionBaselineService()
    actions = [_make_action("search", "res-1", "read"), _make_action("write", "res-2", "write")]
    baseline = service.establish_baseline("agent-1", "session-1", actions)
    assert isinstance(baseline, SessionBaseline)
    assert baseline.agent_id == "agent-1"
    assert "search" in baseline.typical_tools


def test_session_baseline_peak_hours_computed():
    service = SessionBaselineService()
    ts1 = int(datetime(2024, 1, 1, 9, 0, tzinfo=UTC).timestamp())
    ts2 = int(datetime(2024, 1, 1, 9, 30, tzinfo=UTC).timestamp())
    ts3 = int(datetime(2024, 1, 1, 14, 0, tzinfo=UTC).timestamp())
    actions = [
        _make_action("search", "res-1", "read", ts1),
        _make_action("search", "res-1", "read", ts2),
        _make_action("search", "res-1", "read", ts3),
    ]
    baseline = service.establish_baseline("agent-1", "session-1", actions)
    assert len(baseline.peak_action_hours) > 0
    assert 9 in baseline.peak_action_hours


def test_behavioral_report_anomalous_when_high_score():
    service = BehavioralSecurityService()
    baseline = {"typical_tools": ["search"], "typical_resources": ["res-1"], "avg_velocity": 5.0, "typical_action_types": ["read"]}
    current = {"tools_used": ["drop_table"], "resources_targeted": ["res-1"], "velocity": 50.0, "action_types": ["delete"]}
    result = service.detect_drift("agent-1", "session-1", baseline, current)
    assert result["is_drifted"] is True


def test_behavioral_report_normal_when_low_score():
    service = BehavioralSecurityService()
    baseline = {"typical_tools": ["search"], "typical_resources": ["res-1"], "avg_velocity": 5.0, "typical_action_types": ["read"]}
    current = {"tools_used": ["search"], "resources_targeted": ["res-1"], "velocity": 5.5, "action_types": ["read"]}
    result = service.detect_drift("agent-1", "session-1", baseline, current)
    assert result["is_drifted"] is False


def test_drift_signal_severity_levels():
    service = BehavioralSecurityService()
    baseline = {"typical_tools": ["search"], "typical_resources": ["res-1"], "avg_velocity": 5.0, "typical_action_types": ["read"]}
    current = {"tools_used": ["drop_table"], "resources_targeted": ["res-1", "res-2", "res-3"], "velocity": 50.0, "action_types": ["delete"]}
    result = service.detect_drift("agent-1", "session-1", baseline, current)
    severities = [s["severity"] for s in result["drift_signals"]]
    assert all(s in ("low", "medium", "high", "critical") for s in severities)


def test_runaway_behavior_threshold_configurable():
    service = BehavioralSecurityService()
    actions = [_make_action("drop_table", "res-1", "delete", 1700000000 + i) for i in range(3)]
    result = service.detect_runaway_behavior(actions, repetition_threshold=10)
    assert result["is_runaway"] is False


def test_cross_agent_baseline_isolation():
    service = BehavioralSecurityService()
    actions1 = [_make_action("search", "res-1", "read")]
    actions2 = [_make_action("drop_table", "res-2", "delete")]
    service.establish_baseline("agent-1", "session-1", actions1)
    service.establish_baseline("agent-2", "session-2", actions2)
    signals = service.compare_to_baseline("agent-1", "session-1", actions1)
    assert len(signals) == 0


def test_intent_mismatch_score_computation():
    service = BehavioralSecurityService()
    actions = [
        _make_action("delete", "res-1", "delete"),
        _make_action("drop_table", "res-2", "delete"),
        _make_action("update", "res-3", "update"),
    ]
    result = service.detect_intent_action_mismatch("read data for analysis", actions)
    assert 0.0 <= result["mismatch_score"] <= 1.0
    assert result["mismatch_detected"] is True


def test_velocity_z_score_computation():
    service = BehavioralSecurityService()
    result = service.detect_unusual_velocity(100.0, 10.0, 10.0)
    assert abs(result["velocity_z_score"] - 9.0) < 0.01
    assert result["is_anomalous"] is True
