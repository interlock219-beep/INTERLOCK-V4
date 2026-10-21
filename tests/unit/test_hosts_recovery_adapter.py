"""Interlock V5 — DNS hosts-file recovery adapter tests.

Covers the adapter contract, byte-exact (CRLF-preserving) restore at recorded
positions, unrelated-entry preservation, hostname-scoped drift/conflict
semantics, hostname-injection and write-redirection guards, deletion handling,
idempotency, tenant isolation, and the legacy ``execute_recovery`` surface.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.domain.entities.protected_action import ProtectedAction
from app.domain.entities.surgical_recovery_types import (
    CompensationAction,
    ConflictStatus,
    DriftStatus,
    ExecutionState,
    RecoveryAdapterType,
    Reversibility,
)
from app.domain.services.recovery_adapter_registry import RecoveryAdapterRegistry
from app.infrastructure.recovery.hosts_recovery_adapter import HostsRecoveryAdapter

_ORIGINAL_CRLF = (
    b"# comment line\r\n"
    b"127.0.0.1 localhost\r\n"
    b"10.0.0.5 api.internal.example.com\r\n"
    b"10.0.0.6 legacy.example.com\r\n"
)


def _action(hostname: str = "api.internal.example.com", **overrides) -> ProtectedAction:
    base = {
        "action_id": "act-dns-1",
        "tenant_id": "tenant-1",
        "actor_user_id": None,
        "agent_id": "agent-1",
        "authority_grant_id": None,
        "tool": "dns",
        "resource": f"dns:{hostname}",
        "action_type": "dns_update",
    }
    base.update(overrides)
    return ProtectedAction(**base)


def _rebuild(comp: CompensationAction, payload: dict) -> CompensationAction:
    return CompensationAction(
        action_id=comp.action_id,
        incident_action_id=comp.incident_action_id,
        compensation_type=comp.compensation_type,
        compensation_payload=payload,
        idempotency_key=comp.idempotency_key,
        target_system=comp.target_system,
        target_resource=comp.target_resource,
        execution_order=comp.execution_order,
        reversibility=comp.reversibility,
        drift_status=comp.drift_status,
        conflict_status=comp.conflict_status,
        verification_requirements=comp.verification_requirements,
        dependency_edges=comp.dependency_edges,
    )


async def test_contract_valid_and_declaration_truthful():
    validation = RecoveryAdapterRegistry.validate_contract(HostsRecoveryAdapter())
    assert validation.ok is True

    declaration = await HostsRecoveryAdapter().declare_capabilities()
    assert declaration.adapter_name == "hosts_recovery"
    assert declaration.can_compensate is True
    assert declaration.supports_idempotency is True
    assert declaration.supports_versioning is False


async def test_full_round_trip_is_byte_exact(tmp_path: Path):
    hosts = tmp_path / "hosts"
    hosts.write_bytes(_ORIGINAL_CRLF)
    adapter = HostsRecoveryAdapter(hosts_path=hosts)
    action = _action()

    precondition = await adapter.check_preconditions(action)
    assert precondition.satisfied is True

    evidence = await adapter.capture_recovery_evidence(action)
    assert evidence.recovery_adapter_type == RecoveryAdapterType.DNS_HOSTS
    assert evidence.target_system == "hosts_file"
    payload = evidence.compensation_payload
    assert payload["previous_lines"] == ["10.0.0.5 api.internal.example.com"]
    assert payload["previous_line_indices"] == [2]
    assert payload["newline"] == "\r\n"
    assert payload["hostname"] == "api.internal.example.com"
    assert evidence.reversibility_classification == Reversibility.AUTOMATICALLY_REVERSIBLE

    # Simulate the DNS mutation.
    hosts.write_bytes(
        b"# comment line\r\n"
        b"127.0.0.1 localhost\r\n"
        b"10.9.9.9 api.internal.example.com\r\n"
        b"10.0.0.6 legacy.example.com\r\n"
    )

    impact = await adapter.simulate(action, evidence)
    assert impact.would_succeed is True

    comp = await adapter.generate_compensation(action, evidence)
    result = await adapter.execute_compensation(comp, evidence.idempotency_key)
    assert result.success is True
    # Byte-exact restore: identical to the capture-time file.
    assert hosts.read_bytes() == _ORIGINAL_CRLF

    verification = await adapter.verify(comp)
    assert verification.verified is True

    drift = await adapter.detect_drift(action, evidence)
    assert drift.status == DriftStatus.NO_DRIFT


async def test_unrelated_entries_preserved(tmp_path: Path):
    hosts = tmp_path / "hosts"
    hosts.write_bytes(_ORIGINAL_CRLF)
    adapter = HostsRecoveryAdapter(hosts_path=hosts)
    action = _action()

    evidence = await adapter.capture_recovery_evidence(action)

    # The action changes the hostname entry AND an unrelated entry appears.
    hosts.write_bytes(
        b"# comment line\r\n"
        b"127.0.0.1 localhost\r\n"
        b"10.9.9.9 api.internal.example.com\r\n"
        b"10.0.0.6 legacy.example.com\r\n"
        b"10.5.5.5 newcomer.example.com\r\n"
    )

    comp = await adapter.generate_compensation(action, evidence)
    result = await adapter.execute_compensation(comp, evidence.idempotency_key)
    assert result.success is True

    content = hosts.read_text(encoding="utf-8")
    assert "10.0.0.5 api.internal.example.com" in content
    assert "10.9.9.9 api.internal.example.com" not in content
    # The unrelated concurrent entry survives the compensation.
    assert "10.5.5.5 newcomer.example.com" in content
    assert "10.0.0.6 legacy.example.com" in content


async def test_remove_entry_when_hostname_was_absent(tmp_path: Path):
    hosts = tmp_path / "hosts"
    hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    adapter = HostsRecoveryAdapter(hosts_path=hosts)
    action = _action("new.host.example")

    evidence = await adapter.capture_recovery_evidence(action)
    assert evidence.compensation_payload["previous_lines"] == []

    # The action added the entry.
    hosts.write_text(
        "127.0.0.1 localhost\n1.2.3.4 new.host.example\n", encoding="utf-8"
    )

    comp = await adapter.generate_compensation(action, evidence)
    result = await adapter.execute_compensation(comp, evidence.idempotency_key)
    assert result.success is True
    assert "new.host.example" not in hosts.read_text(encoding="utf-8")
    assert "localhost" in hosts.read_text(encoding="utf-8")


async def test_hostname_injection_and_write_redirection_guards(tmp_path: Path):
    hosts = tmp_path / "hosts"
    hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    adapter = HostsRecoveryAdapter(hosts_path=hosts)

    for bad in ("dns:bad host", "dns:evil/name", "dns:with#hash", "dns:nul\x00byte"):
        with pytest.raises(ValueError, match="Invalid DNS resource hostname"):
            HostsRecoveryAdapter.extract_hostname(bad)

    action = _action()
    evidence = await adapter.capture_recovery_evidence(action)
    comp = await adapter.generate_compensation(action, evidence)

    # A tampered payload pointing at a different hosts file is refused.
    victim = tmp_path / "victim-hosts"
    payload = dict(comp.compensation_payload)
    payload["hosts_path"] = str(victim)
    redirected = _rebuild(comp, payload)

    result = await adapter.execute_compensation(redirected, redirected.idempotency_key)
    assert result.success is False
    assert result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT
    assert "different hosts file" in (result.error or "")
    assert not victim.exists()


async def test_deleted_hosts_file_requires_manual_intervention(tmp_path: Path):
    hosts = tmp_path / "hosts"
    hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    adapter = HostsRecoveryAdapter(hosts_path=hosts)
    action = _action()

    evidence = await adapter.capture_recovery_evidence(action)
    hosts.unlink()

    # Drift: no after-state recorded, deletion may be the action's effect.
    drift = await adapter.detect_drift(action, evidence)
    assert drift.status == DriftStatus.INSUFFICIENT_EVIDENCE

    comp = await adapter.generate_compensation(action, evidence)
    result = await adapter.execute_compensation(comp, evidence.idempotency_key)
    assert result.success is False
    assert result.execution_state == ExecutionState.REQUIRES_MANUAL_ACTION
    assert "manual" in (result.error or "").lower()
    # The adapter never fabricates a partial hosts file.
    assert not hosts.exists()


async def test_guards_idempotency_tenant_and_authorization(tmp_path: Path):
    hosts = tmp_path / "hosts"
    hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    adapter = HostsRecoveryAdapter(hosts_path=hosts)

    # Placeholder tenant refused at capture.
    with pytest.raises(ValueError, match="Tenant isolation"):
        await adapter.capture_recovery_evidence(_action(tenant_id="unknown"))

    action = _action()
    evidence = await adapter.capture_recovery_evidence(action)
    comp = await adapter.generate_compensation(action, evidence)

    result = await adapter.execute_compensation(comp, "wrong-key")
    assert result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT
    assert "Idempotency key mismatch" in (result.error or "")

    payload = dict(comp.compensation_payload)
    payload.pop("_tenant_id", None)
    unauthorized = _rebuild(comp, payload)
    result = await adapter.execute_compensation(
        unauthorized, unauthorized.idempotency_key
    )
    assert result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT
    assert "Authorization denied" in (result.error or "")


async def test_preconditions_fail_closed(tmp_path: Path):
    missing = tmp_path / "hosts"
    adapter = HostsRecoveryAdapter(hosts_path=missing)

    precondition = await adapter.check_preconditions(_action())
    assert precondition.satisfied is False
    assert "hosts_file_missing" in precondition.failed_checks

    missing.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    precondition = await adapter.check_preconditions(_action("bad host/name"))
    assert precondition.satisfied is False
    assert "invalid_hostname" in precondition.failed_checks


async def test_drift_semantics_hostname_scoped(tmp_path: Path):
    hosts = tmp_path / "hosts"
    hosts.write_bytes(_ORIGINAL_CRLF)
    adapter = HostsRecoveryAdapter(hosts_path=hosts)

    without_after = await adapter.capture_recovery_evidence(_action())
    with_after = await adapter.capture_recovery_evidence(
        _action(), execution_context={"after_lines": ["10.9.9.9 api.internal.example.com"]}
    )

    # Unchanged hostname entries: no drift.
    result = await adapter.detect_drift(_action(), without_after)
    assert result.status == DriftStatus.NO_DRIFT

    # Unrelated entries changing must not read as drift (hostname-scoped).
    hosts.write_bytes(
        b"# comment line\r\n"
        b"127.0.0.1 localhost\r\n"
        b"10.0.0.5 api.internal.example.com\r\n"
        b"10.0.0.6 legacy.example.com\r\n"
        b"10.7.7.7 other.example.com\r\n"
    )
    result = await adapter.detect_drift(_action(), without_after)
    assert result.status == DriftStatus.NO_DRIFT

    # Hostname entries changed with no after recorded: insufficient evidence.
    hosts.write_bytes(
        b"127.0.0.1 localhost\r\n"
        b"10.9.9.9 api.internal.example.com\r\n"
    )
    result = await adapter.detect_drift(_action(), without_after)
    assert result.status == DriftStatus.INSUFFICIENT_EVIDENCE

    # With an after-state matching the current entries: no drift.
    result = await adapter.detect_drift(_action(), with_after)
    assert result.status == DriftStatus.NO_DRIFT

    # A third state with an after-state recorded: drift detected.
    hosts.write_bytes(b"10.6.6.6 api.internal.example.com\n")
    result = await adapter.detect_drift(_action(), with_after)
    assert result.status == DriftStatus.DRIFT_DETECTED

    # File deleted with an after-state recorded: resource missing.
    hosts.unlink()
    result = await adapter.detect_drift(_action(), with_after)
    assert result.status == DriftStatus.RESOURCE_MISSING


async def test_conflict_semantics(tmp_path: Path):
    hosts = tmp_path / "hosts"
    hosts.write_bytes(_ORIGINAL_CRLF)
    adapter = HostsRecoveryAdapter(hosts_path=hosts)

    without_after = await adapter.capture_recovery_evidence(_action())
    with_after = await adapter.capture_recovery_evidence(
        _action(), execution_context={"after_lines": ["10.9.9.9 api.internal.example.com"]}
    )

    # No after-state: nothing to conflict against.
    result = await adapter.check_conflicts(_action(), without_after)
    assert result.status == ConflictStatus.NO_CONFLICT

    # Current entries equal to the after-state: no conflict.
    hosts.write_bytes(
        b"127.0.0.1 localhost\r\n10.9.9.9 api.internal.example.com\r\n"
    )
    result = await adapter.check_conflicts(_action(), with_after)
    assert result.status == ConflictStatus.NO_CONFLICT

    # Already restored (current == previous): no conflict.
    hosts.write_bytes(_ORIGINAL_CRLF)
    result = await adapter.check_conflicts(_action(), with_after)
    assert result.status == ConflictStatus.NO_CONFLICT

    # A third state with after recorded: concurrent mutation.
    hosts.write_bytes(b"10.6.6.6 api.internal.example.com\n")
    result = await adapter.check_conflicts(_action(), with_after)
    assert result.status == ConflictStatus.CONCURRENT_MUTATION

    # File deleted with after recorded: resource missing.
    hosts.unlink()
    result = await adapter.check_conflicts(_action(), with_after)
    assert result.status == ConflictStatus.RESOURCE_MISSING

    # File deleted without after recorded: no conflict (manual handling later).
    result = await adapter.check_conflicts(_action(), without_after)
    assert result.status == ConflictStatus.NO_CONFLICT


async def test_legacy_execute_recovery(tmp_path: Path):
    hosts = tmp_path / "hosts"
    hosts.write_bytes(_ORIGINAL_CRLF)
    adapter = HostsRecoveryAdapter(hosts_path=hosts)

    action = _action(before_state_snapshot={"lines": ["10.0.0.5 api.internal.example.com"]})
    preview = await adapter.preview_recovery(action)
    assert preview["adapter"] == "hosts_recovery"
    assert preview["reversible"] is True
    assert preview["hostname"] == "api.internal.example.com"

    hosts.write_bytes(
        b"# comment line\r\n127.0.0.1 localhost\r\n10.9.9.9 api.internal.example.com\r\n"
    )
    result = await adapter.execute_recovery(action, approved_by="user-1")
    assert result["status"] == "restored"
    content = hosts.read_text(encoding="utf-8")
    assert "10.0.0.5 api.internal.example.com" in content
    expected_digest = hashlib.sha256(hosts.read_bytes()).hexdigest()
    assert result["file_sha256"] == expected_digest

    # Without recorded lines the legacy path fails instead of guessing.
    no_snapshot = _action("other.example.com")
    result = await adapter.execute_recovery(no_snapshot, approved_by="user-1")
    assert result["status"] == "failed"


async def test_can_recover_scoping(tmp_path: Path):
    hosts = tmp_path / "hosts"
    hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    adapter = HostsRecoveryAdapter(hosts_path=hosts)

    assert await adapter.can_recover(_action()) == "automatically_reversible"

    gone = HostsRecoveryAdapter(hosts_path=tmp_path / "absent")
    assert await gone.can_recover(_action()) == "conditionally_reversible"

    non_dns = ProtectedAction(
        action_id="act-x",
        tenant_id="tenant-1",
        actor_user_id=None,
        agent_id="agent-1",
        authority_grant_id=None,
        tool="database",
        resource="db:public.users",
        action_type="query",
    )
    assert await adapter.can_recover(non_dns) == "unsupported"

    irreversible = _action(reversibility=Reversibility.IRREVERSIBLE)
    assert await adapter.can_recover(irreversible) == "irreversible"


async def test_evidence_hash_and_references_redacted(tmp_path: Path):
    hosts = tmp_path / "hosts"
    hosts.write_bytes(_ORIGINAL_CRLF)
    adapter = HostsRecoveryAdapter(hosts_path=hosts)

    first = await adapter.capture_recovery_evidence(_action())
    second = await adapter.capture_recovery_evidence(_action("legacy.example.com"))
    assert first.evidence_hash != second.evidence_hash
    # State references are hash references, never raw lines.
    assert "10.0.0.5" not in first.before_state_reference
    assert first.before_state_reference.startswith("hosts:")
