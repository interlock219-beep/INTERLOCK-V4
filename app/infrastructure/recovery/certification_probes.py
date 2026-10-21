"""Behavioral certification probes for self-contained recovery adapters.

Each probe receives an isolated temporary working directory, constructs its
own adapter instances against that directory, and runs real
capture -> drift -> simulate -> compensate -> verify round-trips plus
adversarial checks (injection, payload redirection, tampered snapshots,
idempotency, tenant isolation).  Probes never touch real system files or
real external services; adapters requiring live systems are certified
contract-only by :mod:`app.domain.services.recovery_certification_lab`.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from app.domain.entities.protected_action import ProtectedAction
from app.domain.entities.surgical_recovery_types import (
    ConflictStatus,
    DriftStatus,
    ExecutionState,
    Reversibility,
)
from app.domain.services.recovery_certification_lab import (
    ProbeResult,
    probe,
    run_probe_check,
)
from app.infrastructure.recovery.archive_recovery_adapter import ArchiveRecoveryAdapter
from app.infrastructure.recovery.config_recovery_adapter import ConfigRecoveryAdapter
from app.infrastructure.recovery.environment_recovery_adapter import (
    EnvironmentRecoveryAdapter,
)
from app.infrastructure.recovery.filesystem_recovery_adapter import (
    FilesystemRecoveryAdapter,
)
from app.infrastructure.recovery.hosts_recovery_adapter import HostsRecoveryAdapter

_TENANT = "cert-tenant"


def _action(
    action_id: str,
    tool: str,
    resource: str,
    action_type: str,
    **overrides: Any,
) -> ProtectedAction:
    base: dict[str, Any] = {
        "action_id": action_id,
        "tenant_id": _TENANT,
        "actor_user_id": None,
        "agent_id": "cert-agent",
        "authority_grant_id": None,
        "tool": tool,
        "resource": resource,
        "action_type": action_type,
        "reversibility": Reversibility.AUTOMATICALLY_REVERSIBLE,
        "before_state_ref": "state:before:cert",
    }
    base.update(overrides)
    return ProtectedAction(**base)


# ---------------------------------------------------------------------------
# Environment probe
# ---------------------------------------------------------------------------


async def probe_environment(_workdir: Path) -> list[ProbeResult]:
    environ: dict[str, str] = {"CERT_V5_VAR": "post-action"}
    adapter = EnvironmentRecoveryAdapter(environ=environ)
    action = _action("cert-env-1", "environment", "env:CERT_V5_VAR", "set_env")
    results: list[ProbeResult] = []

    async def capture_check() -> ProbeResult:
        evidence = await adapter.capture_recovery_evidence(
            action, execution_context={"before_value": "original-secret"}
        )
        payload = evidence.compensation_payload
        ok = (
            payload.get("before_value_present") is True
            and payload.get("before_value") == "original-secret"
            and "original-secret" not in (evidence.before_state_reference or "")
            and evidence.reversibility_classification
            == Reversibility.AUTOMATICALLY_REVERSIBLE
        )
        return probe("capture_before_state", ok, evidence_hash=evidence.evidence_hash[:16])

    async def drift_check() -> ProbeResult:
        with_after = await adapter.capture_recovery_evidence(
            action,
            execution_context={"before_value": "original", "after_value": "post"},
        )
        without_after = await adapter.capture_recovery_evidence(
            action, execution_context={"before_value": "original"}
        )
        at_before = await adapter.detect_drift(
            action, with_after, current_state={"value": "original"}
        )
        at_after = await adapter.detect_drift(
            action, with_after, current_state={"value": "post"}
        )
        third = await adapter.detect_drift(
            action, with_after, current_state={"value": "tampered"}
        )
        unknown = await adapter.detect_drift(
            action, without_after, current_state={"value": "changed"}
        )
        ok = (
            at_before.status == DriftStatus.NO_DRIFT
            and at_after.status == DriftStatus.NO_DRIFT
            and third.status == DriftStatus.DRIFT_DETECTED
            and unknown.status == DriftStatus.INSUFFICIENT_EVIDENCE
        )
        return probe(
            "drift_contract",
            ok,
            at_before=at_before.status.value,
            at_after=at_after.status.value,
            third=third.status.value,
            unknown=unknown.status.value,
        )

    async def compensate_check() -> ProbeResult:
        evidence = await adapter.capture_recovery_evidence(
            action, execution_context={"before_value": "original-secret"}
        )
        impact = await adapter.simulate(action, evidence)
        comp = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(comp, evidence.idempotency_key)
        ok = (
            impact.would_succeed is True
            and result.success is True
            and result.execution_state == ExecutionState.SUCCEEDED
            and environ.get("CERT_V5_VAR") == "original-secret"
        )
        return probe("compensate_restores_value", ok)

    async def verify_check() -> ProbeResult:
        evidence = await adapter.capture_recovery_evidence(
            action, execution_context={"before_value": "original-secret"}
        )
        comp = await adapter.generate_compensation(action, evidence)
        await adapter.execute_compensation(comp, evidence.idempotency_key)
        verification = await adapter.verify(comp)
        return probe("verify_after_compensation", verification.verified is True)

    async def redaction_check() -> ProbeResult:
        evidence = await adapter.capture_recovery_evidence(
            action, execution_context={"before_value": "original-secret"}
        )
        comp = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(comp, evidence.idempotency_key)
        visible = (
            str(result.details)
            + str(result.error or "")
            + str(evidence.before_state_reference)
        )
        return probe(
            "value_redaction", "original-secret" not in visible, visible=visible[:80]
        )

    async def injection_check() -> ProbeResult:
        raised = False
        try:
            EnvironmentRecoveryAdapter.extract_var_name("env:BADCERT=NAME")
        except ValueError:
            raised = True
        return probe("var_name_injection_guard", raised)

    async def idempotency_check() -> ProbeResult:
        evidence = await adapter.capture_recovery_evidence(
            action, execution_context={"before_value": "original-secret"}
        )
        comp = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(comp, "wrong-key")
        return probe(
            "idempotency_guard",
            result.success is False
            and result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT,
            state=result.execution_state.value,
        )

    async def tenant_check() -> ProbeResult:
        raised = False
        try:
            await adapter.capture_recovery_evidence(
                _action(
                    "cert-env-tenant",
                    "environment",
                    "env:CERT_V5_VAR",
                    "set_env",
                    tenant_id="null",
                )
            )
        except ValueError:
            raised = True
        return probe("tenant_isolation_guard", raised)

    for name, fn in (
        ("capture_before_state", capture_check),
        ("drift_contract", drift_check),
        ("compensate_restores_value", compensate_check),
        ("verify_after_compensation", verify_check),
        ("value_redaction", redaction_check),
        ("var_name_injection_guard", injection_check),
        ("idempotency_guard", idempotency_check),
        ("tenant_isolation_guard", tenant_check),
    ):
        results.append(await run_probe_check(name, fn))
    return results


# ---------------------------------------------------------------------------
# Archive probe
# ---------------------------------------------------------------------------


async def probe_archive(workdir: Path) -> list[ProbeResult]:
    state_dir = workdir / "archive-state"
    target = workdir / "artifact.txt"
    target.write_text("original-artifact-content", encoding="utf-8")
    adapter = ArchiveRecoveryAdapter(state_dir=state_dir)
    action = _action("cert-arc-1", "archive", f"archive:{target}", "backup")
    results: list[ProbeResult] = []

    async def snapshot_check() -> ProbeResult:
        evidence = await adapter.capture_recovery_evidence(action)
        payload = evidence.compensation_payload
        archive_ok = (
            payload.get("archive_path") is not None
            and Path(payload["archive_path"]).is_file()
            and payload.get("target_kind") == "file"
        )
        return probe("snapshot_created", archive_ok)

    async def round_trip() -> ProbeResult:
        evidence = await adapter.capture_recovery_evidence(action)
        target.write_text("mutated-by-incident", encoding="utf-8")
        comp = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(comp, evidence.idempotency_key)
        restored = target.read_text(encoding="utf-8") == "original-artifact-content"
        return probe(
            "round_trip_restores_content",
            result.success is True and restored,
            state=result.execution_state.value,
        )

    async def verify_check() -> ProbeResult:
        evidence = await adapter.capture_recovery_evidence(action)
        target.write_text("mutated-by-incident", encoding="utf-8")
        comp = await adapter.generate_compensation(action, evidence)
        await adapter.execute_compensation(comp, evidence.idempotency_key)
        verification = await adapter.verify(comp)
        return probe("verify_after_compensation", verification.verified is True)

    async def tamper_check() -> ProbeResult:
        tamper_action = _action("cert-arc-tamper", "archive", f"archive:{target}", "backup")
        evidence = await adapter.capture_recovery_evidence(tamper_action)
        Path(evidence.compensation_payload["archive_path"]).write_bytes(b"corrupted")
        target.write_text("mutated-again", encoding="utf-8")
        comp = await adapter.generate_compensation(tamper_action, evidence)
        result = await adapter.execute_compensation(comp, evidence.idempotency_key)
        refused = (
            result.success is False
            and "tampered" in (result.error or "")
            and target.read_text(encoding="utf-8") == "mutated-again"
        )
        return probe("tampered_snapshot_refusal", refused)

    async def containment_check() -> ProbeResult:
        limited = ArchiveRecoveryAdapter(
            state_dir=state_dir, allowed_roots=(str(workdir),)
        )
        raised = False
        try:
            limited._resolve_target(str(Path(workdir).parent / "outside.txt"))
        except ValueError:
            raised = True
        return probe("path_containment_guard", raised)

    async def drift_check() -> ProbeResult:
        evidence = await adapter.capture_recovery_evidence(action)
        target.write_text("mutated-by-incident", encoding="utf-8")
        drift = await adapter.detect_drift(action, evidence)
        return probe(
            "drift_insufficient_without_after",
            drift.status == DriftStatus.INSUFFICIENT_EVIDENCE,
            status=drift.status.value,
        )

    async def tenant_check() -> ProbeResult:
        raised = False
        try:
            await adapter.capture_recovery_evidence(
                _action(
                    "cert-arc-tenant",
                    "archive",
                    f"archive:{target}",
                    "backup",
                    tenant_id="system",
                )
            )
        except ValueError:
            raised = True
        return probe("tenant_isolation_guard", raised)

    for name, fn in (
        ("snapshot_created", snapshot_check),
        ("round_trip_restores_content", round_trip),
        ("verify_after_compensation", verify_check),
        ("tampered_snapshot_refusal", tamper_check),
        ("path_containment_guard", containment_check),
        ("drift_insufficient_without_after", drift_check),
        ("tenant_isolation_guard", tenant_check),
    ):
        results.append(await run_probe_check(name, fn))
    return results


# ---------------------------------------------------------------------------
# Hosts probe
# ---------------------------------------------------------------------------

_HOSTS_CRLF = (
    b"# cert comment\r\n"
    b"127.0.0.1 localhost\r\n"
    b"10.0.0.5 api.cert.example.com\r\n"
    b"10.0.0.6 legacy.cert.example.com\r\n"
)


async def probe_hosts(workdir: Path) -> list[ProbeResult]:
    hosts = workdir / "hosts"
    hosts.write_bytes(_HOSTS_CRLF)
    adapter = HostsRecoveryAdapter(hosts_path=hosts)
    action = _action("cert-dns-1", "dns", "dns:api.cert.example.com", "dns_update")
    results: list[ProbeResult] = []

    async def byte_exact_check() -> ProbeResult:
        evidence = await adapter.capture_recovery_evidence(action)
        hosts.write_bytes(
            b"# cert comment\r\n"
            b"127.0.0.1 localhost\r\n"
            b"10.9.9.9 api.cert.example.com\r\n"
            b"10.0.0.6 legacy.cert.example.com\r\n"
        )
        comp = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(comp, evidence.idempotency_key)
        exact = hosts.read_bytes() == _HOSTS_CRLF
        return probe(
            "byte_exact_crlf_restore",
            result.success is True and exact,
            state=result.execution_state.value,
        )

    async def verify_check() -> ProbeResult:
        evidence = await adapter.capture_recovery_evidence(action)
        hosts.write_bytes(
            b"# cert comment\r\n127.0.0.1 localhost\r\n10.9.9.9 api.cert.example.com\r\n"
        )
        comp = await adapter.generate_compensation(action, evidence)
        await adapter.execute_compensation(comp, evidence.idempotency_key)
        verification = await adapter.verify(comp)
        return probe("verify_after_compensation", verification.verified is True)

    async def drift_check() -> ProbeResult:
        evidence = await adapter.capture_recovery_evidence(action)
        # Unrelated entry changes must not read as drift (hostname-scoped).
        hosts.write_bytes(
            b"# cert comment\r\n"
            b"127.0.0.1 localhost\r\n"
            b"10.0.0.5 api.cert.example.com\r\n"
            b"10.0.0.6 legacy.cert.example.com\r\n"
            b"10.7.7.7 unrelated.cert.example.com\r\n"
        )
        unrelated = await adapter.detect_drift(action, evidence)
        # Hostname entries changed with no after-state: insufficient evidence.
        hosts.write_bytes(b"127.0.0.1 localhost\r\n10.9.9.9 api.cert.example.com\r\n")
        changed = await adapter.detect_drift(action, evidence)
        ok = (
            unrelated.status == DriftStatus.NO_DRIFT
            and changed.status == DriftStatus.INSUFFICIENT_EVIDENCE
        )
        return probe(
            "hostname_scoped_drift",
            ok,
            unrelated=unrelated.status.value,
            changed=changed.status.value,
        )

    async def conflict_check() -> ProbeResult:
        evidence = await adapter.capture_recovery_evidence(action)
        conflict = await adapter.check_conflicts(action, evidence)
        return probe(
            "conflict_without_after_is_clear",
            conflict.status == ConflictStatus.NO_CONFLICT,
            status=conflict.status.value,
        )

    async def injection_check() -> ProbeResult:
        raised = False
        try:
            HostsRecoveryAdapter.extract_hostname("dns:bad host")
        except ValueError:
            raised = True
        return probe("hostname_injection_guard", raised)

    async def redirection_check() -> ProbeResult:
        evidence = await adapter.capture_recovery_evidence(action)
        comp = await adapter.generate_compensation(action, evidence)
        payload = dict(comp.compensation_payload)
        victim = workdir / "victim-hosts"
        payload["hosts_path"] = str(victim)
        import dataclasses

        redirected = dataclasses.replace(comp, compensation_payload=payload)
        result = await adapter.execute_compensation(
            redirected, redirected.idempotency_key
        )
        refused = (
            result.success is False
            and result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT
            and not victim.exists()
        )
        return probe("write_redirection_guard", refused)

    for name, fn in (
        ("byte_exact_crlf_restore", byte_exact_check),
        ("verify_after_compensation", verify_check),
        ("hostname_scoped_drift", drift_check),
        ("conflict_without_after_is_clear", conflict_check),
        ("hostname_injection_guard", injection_check),
        ("write_redirection_guard", redirection_check),
    ):
        results.append(await run_probe_check(name, fn))
    return results


# ---------------------------------------------------------------------------
# Config probe
# ---------------------------------------------------------------------------


async def probe_config(workdir: Path) -> list[ProbeResult]:
    config_dir = workdir / "config"
    config_dir.mkdir()
    config_file = config_dir / "settings.json"
    original = '{"app": "cert", "debug": false, "port": 8080}'
    config_file.write_text(original, encoding="utf-8")
    adapter = ConfigRecoveryAdapter(config_dir=config_dir)
    action = _action(
        "cert-cfg-1", "config", "config:settings.json", "modify"
    )
    results: list[ProbeResult] = []

    async def content_restore() -> ProbeResult:
        # Evidence contract for config: capture happens AFTER the action with
        # the pre-action before-state supplied by the pipeline; the conflict
        # check then requires current == after (capture-time) state.
        config_file.write_text('{"app": "hacked"}', encoding="utf-8")
        evidence = await adapter.capture_recovery_evidence(
            action,
            before_snapshot={
                "exists": True,
                "content": original,
                "hash": hashlib.sha256(original.encode("utf-8")).hexdigest(),
                "size": len(original.encode("utf-8")),
            },
        )
        comp = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(comp, evidence.idempotency_key)
        restored = config_file.read_text(encoding="utf-8") == original
        return probe(
            "content_restore_round_trip",
            result.success is True and restored,
            state=result.execution_state.value,
        )

    async def verify_check() -> ProbeResult:
        config_file.write_text('{"app": "hacked"}', encoding="utf-8")
        evidence = await adapter.capture_recovery_evidence(
            action,
            before_snapshot={
                "exists": True,
                "content": original,
                "hash": hashlib.sha256(original.encode("utf-8")).hexdigest(),
                "size": len(original.encode("utf-8")),
            },
        )
        comp = await adapter.generate_compensation(action, evidence)
        await adapter.execute_compensation(comp, evidence.idempotency_key)
        verification = await adapter.verify(comp)
        return probe("verify_after_compensation", verification.verified is True)

    async def drift_unchanged() -> ProbeResult:
        evidence = await adapter.capture_recovery_evidence(action)
        drift = await adapter.detect_drift(action, evidence)
        return probe(
            "drift_no_drift_unchanged",
            drift.status == DriftStatus.NO_DRIFT,
            status=drift.status.value,
        )

    async def drift_changed() -> ProbeResult:
        evidence = await adapter.capture_recovery_evidence(action)
        config_file.write_text('{"app": "hacked"}', encoding="utf-8")
        drift = await adapter.detect_drift(action, evidence)
        config_file.write_text(original, encoding="utf-8")
        return probe(
            "drift_detected_after_mutation",
            drift.status == DriftStatus.DRIFT_DETECTED,
            status=drift.status.value,
        )

    async def delete_restore() -> ProbeResult:
        delete_action = _action(
            "cert-cfg-del", "config", "config:settings.json", "delete"
        )
        evidence = await adapter.capture_recovery_evidence(delete_action)
        config_file.unlink()
        comp = await adapter.generate_compensation(delete_action, evidence)
        result = await adapter.execute_compensation(comp, evidence.idempotency_key)
        restored = config_file.exists() and config_file.read_text() == original
        return probe(
            "restore_deleted_config",
            result.success is True and restored,
            state=result.execution_state.value,
        )

    async def traversal_guard() -> ProbeResult:
        raised = False
        try:
            adapter._extract_config_file("config:../evil.yaml")
        except ValueError:
            raised = True
        return probe("path_traversal_guard", raised)

    for name, fn in (
        ("content_restore_round_trip", content_restore),
        ("verify_after_compensation", verify_check),
        ("drift_no_drift_unchanged", drift_unchanged),
        ("drift_detected_after_mutation", drift_changed),
        ("restore_deleted_config", delete_restore),
        ("path_traversal_guard", traversal_guard),
    ):
        results.append(await run_probe_check(name, fn))
    return results


# ---------------------------------------------------------------------------
# Filesystem probe
# ---------------------------------------------------------------------------


async def probe_filesystem(workdir: Path) -> list[ProbeResult]:
    base_path = workdir / "fs"
    base_path.mkdir()
    fs_file = base_path / "data.txt"
    original = "Original certified content"
    fs_file.write_text(original, encoding="utf-8")
    adapter = FilesystemRecoveryAdapter(base_path=base_path)
    action = _action("cert-fs-1", "filesystem", "file:data.txt", "modify")
    results: list[ProbeResult] = []

    async def content_restore() -> ProbeResult:
        # Evidence contract for the filesystem adapter: capture happens AFTER
        # the action with the pre-action before-state supplied by the pipeline.
        fs_file.write_text("Modified by incident", encoding="utf-8")
        evidence = await adapter.capture_recovery_evidence(
            action,
            before_snapshot={
                "exists": True,
                "content": original,
                "hash": hashlib.sha256(original.encode("utf-8")).hexdigest(),
                "size": len(original.encode("utf-8")),
                "metadata": None,
            },
        )
        comp = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(comp, evidence.idempotency_key)
        restored = fs_file.read_text(encoding="utf-8") == original
        return probe(
            "content_restore_round_trip",
            result.success is True and restored,
            state=result.execution_state.value,
        )

    async def verify_check() -> ProbeResult:
        fs_file.write_text("Modified by incident", encoding="utf-8")
        evidence = await adapter.capture_recovery_evidence(
            action,
            before_snapshot={
                "exists": True,
                "content": original,
                "hash": hashlib.sha256(original.encode("utf-8")).hexdigest(),
                "size": len(original.encode("utf-8")),
                "metadata": None,
            },
        )
        comp = await adapter.generate_compensation(action, evidence)
        await adapter.execute_compensation(comp, evidence.idempotency_key)
        verification = await adapter.verify(comp)
        return probe("verify_after_compensation", verification.verified is True)

    async def restore_deleted() -> ProbeResult:
        del_action = _action("cert-fs-del", "filesystem", "file:data.txt", "delete")
        fs_file.write_text(original, encoding="utf-8")
        evidence = await adapter.capture_recovery_evidence(del_action)
        fs_file.unlink()
        comp = await adapter.generate_compensation(del_action, evidence)
        result = await adapter.execute_compensation(comp, evidence.idempotency_key)
        restored = fs_file.exists() and fs_file.read_text(encoding="utf-8") == original
        return probe(
            "restore_deleted_file",
            result.success is True and restored,
            state=result.execution_state.value,
        )

    async def idempotency_check() -> ProbeResult:
        evidence = await adapter.capture_recovery_evidence(action)
        comp = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(comp, "wrong-key")
        return probe(
            "idempotency_guard",
            result.success is False
            and result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT,
            state=result.execution_state.value,
        )

    async def traversal_guard() -> ProbeResult:
        raised = False
        try:
            adapter._resolve_file_path("file:../secrets.txt", base_path)
        except ValueError:
            raised = True
        return probe("path_traversal_guard", raised)

    for name, fn in (
        ("content_restore_round_trip", content_restore),
        ("verify_after_compensation", verify_check),
        ("restore_deleted_file", restore_deleted),
        ("idempotency_guard", idempotency_check),
        ("path_traversal_guard", traversal_guard),
    ):
        results.append(await run_probe_check(name, fn))
    return results


def standard_behavioral_probes() -> dict[str, Any]:
    """Probe registry keyed by adapter_name for all locally-testable adapters."""
    return {
        "environment_recovery": probe_environment,
        "archive_recovery": probe_archive,
        "hosts_recovery": probe_hosts,
        "config_recovery": probe_config,
        "filesystem_recovery": probe_filesystem,
    }
