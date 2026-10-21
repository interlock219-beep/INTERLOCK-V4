"""Interlock V5 — archive recovery adapter tests.

Covers the adapter contract, file/directory snapshot + restore round-trips,
preconditions, path-containment guards (capture and execute time), tampered
archive refusal, symlink handling, drift/conflict semantics required by the
distributed orchestrator, idempotency, tenant isolation, and the legacy
``execute_recovery`` surface.
"""

from __future__ import annotations

import tarfile
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
from app.infrastructure.recovery.archive_recovery_adapter import ArchiveRecoveryAdapter


def _action(action_id: str, target: Path, **overrides) -> ProtectedAction:
    base = {
        "action_id": action_id,
        "tenant_id": "tenant-1",
        "actor_user_id": None,
        "agent_id": "agent-1",
        "authority_grant_id": None,
        "tool": "archive",
        "resource": f"archive:{target}",
        "action_type": "backup",
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
    validation = RecoveryAdapterRegistry.validate_contract(ArchiveRecoveryAdapter())
    assert validation.ok is True

    declaration = await ArchiveRecoveryAdapter().declare_capabilities()
    assert declaration.adapter_name == "archive_recovery"
    assert declaration.can_compensate is True
    assert declaration.can_detect_drift is True
    assert declaration.supports_idempotency is True


async def test_file_snapshot_and_restore_round_trip(tmp_path: Path):
    state_dir = tmp_path / "state"
    target = tmp_path / "artifact.txt"
    target.write_text("original-content", encoding="utf-8")
    adapter = ArchiveRecoveryAdapter(state_dir=state_dir)
    action = _action("act-file-1", target)

    precondition = await adapter.check_preconditions(action)
    assert precondition.satisfied is False  # no archive yet

    evidence = await adapter.capture_recovery_evidence(action)
    assert evidence.recovery_adapter_type == RecoveryAdapterType.ARCHIVE
    assert evidence.target_system == "archive_store"
    assert evidence.compensation_payload["target_kind"] == "file"
    assert evidence.compensation_payload["archive_path"]
    assert Path(evidence.compensation_payload["archive_path"]).is_file()
    assert evidence.reversibility_classification == Reversibility.AUTOMATICALLY_REVERSIBLE

    precondition = await adapter.check_preconditions(action)
    assert precondition.satisfied is True

    impact = await adapter.simulate(action, evidence)
    assert impact.would_succeed is True

    # Simulate the incident: mutate the target.
    target.write_text("mutated-by-agent", encoding="utf-8")

    comp = await adapter.generate_compensation(action, evidence)
    result = await adapter.execute_compensation(comp, evidence.idempotency_key)
    assert result.success is True
    assert result.execution_state == ExecutionState.SUCCEEDED
    assert target.read_text(encoding="utf-8") == "original-content"
    # A pre-restore backup of the mutated file is kept in the state dir.
    assert any(state_dir.glob("*.pre-restore-*.bak"))

    verification = await adapter.verify(comp)
    assert verification.verified is True


async def test_directory_snapshot_and_restore_with_symlink_skip(tmp_path: Path):
    state_dir = tmp_path / "state"
    target = tmp_path / "tree"
    target.mkdir()
    (target / "a.txt").write_text("a", encoding="utf-8")
    nested = target / "nested"
    nested.mkdir()
    (nested / "b.txt").write_text("b", encoding="utf-8")
    try:
        (target / "link").symlink_to(target / "a.txt")
        has_symlink = True
    except OSError:  # pragma: no cover - environments without symlink support
        has_symlink = False

    adapter = ArchiveRecoveryAdapter(state_dir=state_dir)
    action = _action("act-dir-1", target)
    evidence = await adapter.capture_recovery_evidence(action)
    assert evidence.compensation_payload["target_kind"] == "directory"
    if has_symlink:
        assert evidence.compensation_payload["skipped_symlinks"] == 1

    # Incident: delete the tree entirely.
    import shutil

    shutil.rmtree(target)
    assert not target.exists()

    comp = await adapter.generate_compensation(action, evidence)
    result = await adapter.execute_compensation(comp, evidence.idempotency_key)
    assert result.success is True
    assert (target / "a.txt").read_text(encoding="utf-8") == "a"
    assert (nested / "b.txt").read_text(encoding="utf-8") == "b"

    verification = await adapter.verify(comp)
    assert verification.verified is True


async def test_missing_target_is_conditional_and_fails_closed(tmp_path: Path):
    state_dir = tmp_path / "state"
    target = tmp_path / "never-existed.bin"
    adapter = ArchiveRecoveryAdapter(state_dir=state_dir)
    action = _action("act-missing-1", target)

    evidence = await adapter.capture_recovery_evidence(action)
    assert evidence.reversibility_classification == Reversibility.CONDITIONALLY_REVERSIBLE
    assert evidence.compensation_payload["archive_path"] is None

    # No snapshot exists: drift cannot be judged.
    drift = await adapter.detect_drift(action, evidence)
    assert drift.status == DriftStatus.INSUFFICIENT_EVIDENCE

    comp = await adapter.generate_compensation(action, evidence)
    result = await adapter.execute_compensation(comp, evidence.idempotency_key)
    assert result.success is False
    assert result.execution_state == ExecutionState.REQUIRES_MANUAL_ACTION
    assert "No snapshot archive" in (result.error or "")


async def test_tampered_archive_refused(tmp_path: Path):
    state_dir = tmp_path / "state"
    target = tmp_path / "artifact.txt"
    target.write_text("original", encoding="utf-8")
    adapter = ArchiveRecoveryAdapter(state_dir=state_dir)
    action = _action("act-tamper-1", target)

    evidence = await adapter.capture_recovery_evidence(action)
    archive_path = Path(evidence.compensation_payload["archive_path"])

    # Tamper with the stored snapshot.
    archive_path.write_bytes(b"not a tar.gz any more")
    target.write_text("mutated", encoding="utf-8")

    comp = await adapter.generate_compensation(action, evidence)
    result = await adapter.execute_compensation(comp, evidence.idempotency_key)
    assert result.success is False
    assert result.execution_state == ExecutionState.FAILED
    assert "tampered archive" in (result.error or "")
    # The target was not touched by the refused restore.
    assert target.read_text(encoding="utf-8") == "mutated"


async def test_target_path_redirection_refused(tmp_path: Path):
    state_dir = tmp_path / "state"
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    target = allowed_root / "artifact.txt"
    target.write_text("original", encoding="utf-8")

    adapter = ArchiveRecoveryAdapter(
        state_dir=state_dir, allowed_roots=(str(allowed_root),)
    )
    action = _action("act-redir-1", target)
    evidence = await adapter.capture_recovery_evidence(action)
    comp = await adapter.generate_compensation(action, evidence)

    # Even if the stored payload is tampered to point elsewhere, execution
    # must refuse to write outside the allowed roots.
    victim = tmp_path / "victim.txt"
    victim.write_text("victim-data", encoding="utf-8")
    payload = dict(comp.compensation_payload)
    payload["target_path"] = str(victim)
    redirected = _rebuild(comp, payload)

    result = await adapter.execute_compensation(redirected, redirected.idempotency_key)
    assert result.success is False
    assert result.execution_state == ExecutionState.FAILED
    assert "outside configured allowed roots" in (result.error or "")
    assert victim.read_text(encoding="utf-8") == "victim-data"


async def test_archive_path_redirection_refused(tmp_path: Path):
    state_dir = tmp_path / "state"
    target = tmp_path / "artifact.txt"
    target.write_text("original", encoding="utf-8")

    adapter = ArchiveRecoveryAdapter(state_dir=state_dir)
    action = _action("act-areredir-1", target)
    evidence = await adapter.capture_recovery_evidence(action)
    comp = await adapter.generate_compensation(action, evidence)

    # Plant a hostile archive outside the state directory.
    hostile = tmp_path / "hostile.tar.gz"
    with tarfile.open(hostile, "w:gz") as tar:
        info = tarfile.TarInfo(name="artifact.txt")
        data = b"hostile-content"
        info.size = len(data)
        import io

        tar.addfile(info, io.BytesIO(data))

    payload = dict(comp.compensation_payload)
    payload["archive_path"] = str(hostile)
    redirected = _rebuild(comp, payload)

    target.write_text("mutated", encoding="utf-8")
    result = await adapter.execute_compensation(redirected, redirected.idempotency_key)
    assert result.success is False
    assert "outside the state directory" in (result.error or "")
    assert target.read_text(encoding="utf-8") == "mutated"


async def test_path_guards_reject_bad_targets(tmp_path: Path):
    adapter = ArchiveRecoveryAdapter(state_dir=tmp_path / "state")

    # Relative path refused.
    action = _action("act-rel-1", Path("relative/file.txt"))
    precondition = await adapter.check_preconditions(action)
    assert precondition.satisfied is False
    assert "invalid_target_path" in precondition.failed_checks
    with pytest.raises(ValueError, match="absolute"):
        await adapter.capture_recovery_evidence(action)

    # NUL byte refused.
    with pytest.raises(ValueError, match="NUL"):
        adapter._resolve_target("archive:bad\x00path")

    # Forward-slash pseudo-root is not absolute on Windows: still refused.
    with pytest.raises(ValueError):
        adapter._resolve_target("archive:/")

    # Filesystem root refused.
    with pytest.raises(ValueError, match="root"):
        adapter._resolve_target(f"archive:{Path.cwd().anchor}")

    # Outside configured allowed roots refused.
    allowed = tmp_path / "in"
    allowed.mkdir()
    adapter2 = ArchiveRecoveryAdapter(
        state_dir=tmp_path / "state2", allowed_roots=(str(allowed),)
    )
    with pytest.raises(ValueError, match="outside configured allowed roots"):
        adapter2._resolve_target(str(tmp_path / "out" / "file.txt"))


async def test_idempotency_tenant_and_authorization_guards(tmp_path: Path):
    state_dir = tmp_path / "state"
    target = tmp_path / "artifact.txt"
    target.write_text("original", encoding="utf-8")
    adapter = ArchiveRecoveryAdapter(state_dir=state_dir)

    # Placeholder tenant refused at capture.
    with pytest.raises(ValueError, match="Tenant isolation"):
        await adapter.capture_recovery_evidence(
            _action("act-tenant-1", target, tenant_id="system")
        )

    action = _action("act-guard-1", target)
    evidence = await adapter.capture_recovery_evidence(action)
    comp = await adapter.generate_compensation(action, evidence)

    # Idempotency mismatch.
    result = await adapter.execute_compensation(comp, "wrong-key")
    assert result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT
    assert "Idempotency key mismatch" in (result.error or "")

    # Missing tenant context in the payload.
    payload = dict(comp.compensation_payload)
    payload.pop("_tenant_id", None)
    unauthorized = _rebuild(comp, payload)
    result = await adapter.execute_compensation(
        unauthorized, unauthorized.idempotency_key
    )
    assert result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT
    assert "Authorization denied" in (result.error or "")


async def test_drift_semantics_match_orchestrator_contract(tmp_path: Path):
    state_dir = tmp_path / "state"
    target = tmp_path / "artifact.txt"
    target.write_text("before", encoding="utf-8")
    adapter = ArchiveRecoveryAdapter(state_dir=state_dir)
    action = _action("act-drift-1", target)

    without_after = await adapter.capture_recovery_evidence(action)
    with_after = await adapter.capture_recovery_evidence(
        _action("act-drift-1-after", target),
        execution_context={"after_sha256": "after-recorded-hash"},
    )

    # Unchanged target: no drift.
    result = await adapter.detect_drift(action, without_after)
    assert result.status == DriftStatus.NO_DRIFT

    # Mutated target with no after recorded: insufficient evidence.
    target.write_text("changed", encoding="utf-8")
    result = await adapter.detect_drift(action, without_after)
    assert result.status == DriftStatus.INSUFFICIENT_EVIDENCE

    # After recorded but current matches before: no drift (already restored).
    target.write_text("before", encoding="utf-8")
    result = await adapter.detect_drift(action, with_after)
    assert result.status == DriftStatus.NO_DRIFT

    # After recorded, current matches after: no drift (expected action state).
    target.write_text("changed", encoding="utf-8")
    result = await adapter.detect_drift(
        _action("act-drift-1-after", target),
        with_after,
        current_state=None,
    )
    # current hash != recorded after (which was a fake hash), so this is a
    # third state -> drift detected.
    assert result.status == DriftStatus.DRIFT_DETECTED

    # Target deleted with no after recorded: insufficient evidence.
    target.unlink()
    result = await adapter.detect_drift(action, without_after)
    assert result.status == DriftStatus.INSUFFICIENT_EVIDENCE

    # Target deleted with after recorded: resource missing.
    result = await adapter.detect_drift(
        _action("act-drift-1-after", target), with_after
    )
    assert result.status == DriftStatus.RESOURCE_MISSING


async def test_conflict_semantics_match_orchestrator_contract(tmp_path: Path):
    state_dir = tmp_path / "state"
    target = tmp_path / "artifact.txt"
    target.write_text("before", encoding="utf-8")
    adapter = ArchiveRecoveryAdapter(state_dir=state_dir)

    without_after = await adapter.capture_recovery_evidence(
        _action("act-conf-1", target)
    )
    with_after = await adapter.capture_recovery_evidence(
        _action("act-conf-2", target),
        execution_context={"after_sha256": "after-hash"},
    )

    # No after recorded: nothing to conflict against.
    target.write_text("whatever", encoding="utf-8")
    result = await adapter.check_conflicts(
        _action("act-conf-1", target), without_after
    )
    assert result.status == ConflictStatus.NO_CONFLICT

    # After recorded: current matching after or before is fine.
    result = await adapter.check_conflicts(_action("act-conf-2", target), with_after)
    # current hash is "whatever" content; after recorded is fake hash, before
    # is the original hash -> third state -> concurrent mutation.
    assert result.status == ConflictStatus.CONCURRENT_MUTATION

    target.write_text("before", encoding="utf-8")
    result = await adapter.check_conflicts(_action("act-conf-2", target), with_after)
    assert result.status == ConflictStatus.NO_CONFLICT


async def test_legacy_execute_recovery(tmp_path: Path):
    state_dir = tmp_path / "state"
    target = tmp_path / "artifact.txt"
    target.write_text("original", encoding="utf-8")
    adapter = ArchiveRecoveryAdapter(state_dir=state_dir)

    action = _action("act-legacy-1", target)
    preview = await adapter.preview_recovery(action)
    assert preview["adapter"] == "archive_recovery"
    assert preview["snapshot_exists"] is False
    assert preview["reversible"] is False

    await adapter.capture_recovery_evidence(action)
    preview = await adapter.preview_recovery(action)
    assert preview["snapshot_exists"] is True
    assert preview["reversible"] is True

    target.write_text("mutated", encoding="utf-8")
    result = await adapter.execute_recovery(action, approved_by="user-1")
    assert result["status"] == "restored"
    assert target.read_text(encoding="utf-8") == "original"
    assert result["executed_by"] == "user-1"

    # Without a snapshot the legacy path fails instead of guessing.
    no_snapshot = _action("act-legacy-none", target)
    result = await adapter.execute_recovery(no_snapshot, approved_by="user-1")
    assert result["status"] == "failed"


async def test_can_recover_scoping(tmp_path: Path):
    target = tmp_path / "artifact.txt"
    target.write_text("x", encoding="utf-8")
    adapter = ArchiveRecoveryAdapter(state_dir=tmp_path / "state")

    assert await adapter.can_recover(_action("act-sc-1", target)) in (
        "automatically_reversible",
        "conditionally_reversible",
    )

    non_archive = ProtectedAction(
        action_id="act-sc-2",
        tenant_id="tenant-1",
        actor_user_id=None,
        agent_id="agent-1",
        authority_grant_id=None,
        tool="database",
        resource="db:public.users",
        action_type="query",
    )
    assert await adapter.can_recover(non_archive) == "unsupported"

    irreversible = _action(
        "act-sc-3", target, reversibility=Reversibility.IRREVERSIBLE
    )
    assert await adapter.can_recover(irreversible) == "irreversible"
