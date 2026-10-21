"""R12 regression tests: audit records must mask secret-bearing values.

Before R12, ``log_security_event`` / ``log_compliance_event`` wrote
caller-supplied ``**details`` verbatim while their docstrings claimed
"Never logs secrets, tokens, or sensitive request data" — a
documentation-vs-behavior gap found by the Phase 2 property assessment
(property 11: no general redaction pass over audit payloads).

All existing production call sites pass benign keys (ids, counts, routes);
redaction is additive defense-in-depth for future callers, applied BEFORE
persistence and BEFORE the compliance hash preimage is computed.
"""

from __future__ import annotations

import json

import pytest

from app.infrastructure.logging.audit_logger import (
    LOG_PATH,
    _verify_hash_chain,
    log_compliance_event,
    log_security_event,
)


@pytest.fixture(autouse=True)
def _clear_audit_log() -> None:
    if LOG_PATH.exists():
        LOG_PATH.unlink()
    yield
    if LOG_PATH.exists():
        LOG_PATH.unlink()


def _read_records() -> list[dict]:
    with LOG_PATH.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def test_security_event_redacts_sensitive_keys_and_bearer_values() -> None:
    log_security_event(
        "test_sensitive",
        correlation_id="corr-r12",
        session_id="sess-1",  # benign: must remain raw
        failure_count=2,  # benign: must remain raw
        password="hunter2",  # masked by key
        api_key="sk-live-123",  # masked by key
        Authorization="Bearer eyJhbGciOi.header.sigtok",  # masked by key
        nested={"client_secret": "s3cr3t", "route": "/x"},  # nested dict visited
        items=[{"refresh_token": "rt-1"}],  # nested list visited
        error="failed with Authorization: Bearer abc.def.ghi",  # masked by value shape
    )
    raw = LOG_PATH.read_text(encoding="utf-8")
    record = _read_records()[0]

    # Nothing secret may reach the file at all (nor the stdout log line,
    # which serializes the same redacted record).
    for leaked in (
        "hunter2",
        "sk-live-123",
        "eyJhbGciOi",
        "s3cr3t",
        "rt-1",
        "abc.def.ghi",
    ):
        assert leaked not in raw, f"secret leaked into audit trail: {leaked}"

    assert record["password"] == "[REDACTED]"
    assert record["api_key"] == "[REDACTED]"
    assert record["Authorization"] == "[REDACTED]"
    assert record["nested"]["client_secret"] == "[REDACTED]"
    assert record["items"][0]["refresh_token"] == "[REDACTED]"
    assert "Bearer [REDACTED]" in record["error"]

    # No over-redaction: benign audit fields keep flowing through.
    assert record["session_id"] == "sess-1"
    assert record["failure_count"] == 2
    assert record["nested"]["route"] == "/x"


def test_compliance_event_redacts_before_hashing() -> None:
    log_compliance_event(
        "test_compliance", access_token="tok-SECRET-1", user_id="u-1"
    )
    raw = LOG_PATH.read_text(encoding="utf-8")
    # The secret must not reach the file NOR the hash preimage.
    assert "tok-SECRET-1" not in raw
    records = _read_records()
    assert records[0]["access_token"] == "[REDACTED]"
    assert records[0]["user_id"] == "u-1"
    # The tamper-evident chain still verifies over the redacted content.
    assert _verify_hash_chain(records) is True


def test_redaction_happens_before_hash_so_post_hoc_edits_still_break_chain() -> None:
    """Redaction must not weaken tamper evidence: the chain hash is computed
    over the already-redacted record, so editing a field afterwards is still
    detected."""
    log_compliance_event("test_compliance_a", client_secret="cs-1")
    records = _read_records()
    tampered = [dict(records[0], client_secret="changed")]
    assert _verify_hash_chain(tampered) is False
