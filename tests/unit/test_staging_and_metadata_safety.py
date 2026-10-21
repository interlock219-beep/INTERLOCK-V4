"""Batch 5: no silent destruction of user data, and honest metadata claims.

Covers the audit findings:

- **RE-09** the reserved staging path (``<target>.recovery_tmp``) belongs to
  the engine, but the bytes sitting there may be the USER's: a colliding
  entry is now moved aside, never deleted.
- **RE-07** the engine declares ``file_permissions_preserved``; on POSIX the
  verification now actually checks the restored mode and timestamps, so a
  recovery that restored the bytes but not the metadata cannot report success.

Every test uses a temporary workspace; no project file is touched.
"""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

import pytest

from app.domain.entities.protected_action import ActionStatus, ProtectedAction, Reversibility
from app.infrastructure.recovery.filesystem_recovery_adapter import FilesystemRecoveryAdapter

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX mode semantics")


def _make_fs_action(
    action_id: str = "act-batch5-1",
    action_type: str = "modify",
    resource: str = "file:test.txt",
) -> ProtectedAction:
    return ProtectedAction(
        action_id=action_id,
        tenant_id="test-tenant",
        agent_id="agent-test",
        actor_user_id=None,
        authority_grant_id=None,
        tool="filesystem",
        resource=resource,
        action_type=action_type,
        risk_score=0.5,
        policy_version="v1",
        correlation_id="corr-1",
        parent_action_id=None,
        workflow_id=None,
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
        before_state_ref="state:before:1",
        after_state_ref="state:after:1",
        tool_arguments={"path": resource},
        status=ActionStatus.EXECUTED,
        decision_reason="test",
        evaluated_at=None,
        executed_at=None,
        created_at=None,
    )


# --------------------------------------------------------------------------- #
# RE-09: a user file at the staging path is preserved, not destroyed
# --------------------------------------------------------------------------- #


class TestStagingCollisionPreservesUserData:
    @pytest.mark.asyncio
    async def test_user_file_at_the_staging_path_is_preserved(self, tmp_path: Path) -> None:
        base = tmp_path / "fs"
        base.mkdir()
        target = base / "file.txt"
        original = b"the original bytes"
        target.write_bytes(original)

        adapter = FilesystemRecoveryAdapter(base_path=base)
        action = _make_fs_action(resource="file:file.txt")
        captured = await adapter.capture_recovery_evidence(action)
        before = captured.compensation_payload["before_snapshot"]

        # A file the USER created with the engine's reserved staging name.
        user_file = base / "file.txt.recovery_tmp"
        user_bytes = b"the user's own file - must not be deleted"
        user_file.write_bytes(user_bytes)

        # The agent damages the file; the plan is made against that state.
        target.write_bytes(b"agent damage")
        evidence = await adapter.capture_recovery_evidence(action, before_snapshot=before)
        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is True
        # The recovery did its job.
        assert target.read_bytes() == original
        # The user's bytes were NOT destroyed: they were moved aside.
        assert not user_file.exists()
        preserved = list(base.glob("file.txt.recovery_tmp.preserved-*"))
        assert len(preserved) == 1, "the colliding entry must be preserved under a new name"
        assert preserved[0].read_bytes() == user_bytes
        # And the result says so.
        assert result.details.get("staging_preserved_as")

    @pytest.mark.asyncio
    async def test_planted_symlink_at_the_staging_path_is_still_moved_not_followed(
        self, tmp_path: Path
    ) -> None:
        """The anti-planting defence is unchanged: a link is moved, never
        followed, so its target is never written to."""
        base = tmp_path / "fs"
        base.mkdir()
        target = base / "file.txt"
        original = b"the original bytes"
        target.write_bytes(original)
        escape = tmp_path / "escape_target.txt"
        escape.write_bytes(b"must not change")

        adapter = FilesystemRecoveryAdapter(base_path=base)
        action = _make_fs_action(resource="file:file.txt")
        captured = await adapter.capture_recovery_evidence(action)
        before = captured.compensation_payload["before_snapshot"]

        staging = base / "file.txt.recovery_tmp"
        try:
            staging.symlink_to(escape)
        except (OSError, NotImplementedError):  # pragma: no cover - needs elevation
            pytest.skip("symlink creation unavailable in this environment")

        target.write_bytes(b"agent damage")
        evidence = await adapter.capture_recovery_evidence(action, before_snapshot=before)
        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is True
        assert target.read_bytes() == original
        assert escape.read_bytes() == b"must not change"
        assert not target.is_symlink()

    @pytest.mark.asyncio
    async def test_stale_residue_from_a_killed_attempt_is_still_cleared(
        self, tmp_path: Path
    ) -> None:
        """The retry-after-interruption contract (D-RH-1) is preserved."""
        base = tmp_path / "fs"
        base.mkdir()
        adapter = FilesystemRecoveryAdapter(base_path=base)
        stale = base / "deleted.txt.recovery_tmp"
        stale.write_bytes(b"stale partial bytes from a killed attempt")

        payload = {
            "file_path": "deleted.txt",
            "before_snapshot": {
                "content_b64": None,
                "content": "original after interruption",
                "hash": hashlib.sha256(b"original after interruption").hexdigest(),
            },
            "after_snapshot": {"hash": None},
        }
        result = adapter._execute_restore_deleted_file(payload, base)
        assert result["success"] is True
        assert (base / "deleted.txt").read_bytes() == b"original after interruption"
        assert not stale.exists()


# --------------------------------------------------------------------------- #
# RE-07: the metadata the engine claims is actually verified
# --------------------------------------------------------------------------- #


class TestMetadataClaimsAreVerified:
    @pytest.mark.asyncio
    async def test_requirements_do_not_claim_acl_restoration(self, tmp_path: Path) -> None:
        """The engine captures ACLs but cannot restore them portably, so the
        requirement list must not claim it."""
        base = tmp_path / "fs"
        base.mkdir()
        adapter = FilesystemRecoveryAdapter(base_path=base)
        action = _make_fs_action(resource="file:test.txt")
        evidence = await adapter.capture_recovery_evidence(action)
        compensation = await adapter.generate_compensation(action, evidence)
        requirements = compensation.verification_requirements
        assert "file_acl_preserved_where_supported" not in requirements
        assert "file_acl_captured_not_restored" in requirements
        assert "file_permissions_preserved" in requirements

    @posix_only
    @pytest.mark.asyncio
    async def test_verification_fails_when_the_mode_was_not_restored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A restore whose chmod silently failed must not report success."""
        base = tmp_path / "fs"
        base.mkdir()
        target = base / "file.txt"
        original = b"the original bytes"
        target.write_bytes(original)
        os.chmod(target, 0o644)

        adapter = FilesystemRecoveryAdapter(base_path=base)
        action = _make_fs_action(resource="file:file.txt")
        captured = await adapter.capture_recovery_evidence(action)
        before = captured.compensation_payload["before_snapshot"]
        assert before["metadata"]["mode"] == 0o644

        target.write_bytes(b"agent damage")
        evidence = await adapter.capture_recovery_evidence(action, before_snapshot=before)
        compensation = await adapter.generate_compensation(action, evidence)

        # Fault injection: the permission restore fails silently.
        monkeypatch.setattr(os, "chmod", lambda *args, **kwargs: None)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)
        assert result.success is True  # the bytes were restored

        verification = await adapter.verify(compensation)
        assert verification.verified is False
        assert "permissions_mismatch" in str(verification.details.get("reason", ""))

    @posix_only
    @pytest.mark.asyncio
    async def test_verification_passes_when_the_mode_was_restored(self, tmp_path: Path) -> None:
        base = tmp_path / "fs"
        base.mkdir()
        target = base / "file.txt"
        original = b"the original bytes"
        target.write_bytes(original)
        os.chmod(target, 0o640)

        adapter = FilesystemRecoveryAdapter(base_path=base)
        action = _make_fs_action(resource="file:file.txt")
        captured = await adapter.capture_recovery_evidence(action)
        before = captured.compensation_payload["before_snapshot"]

        target.write_bytes(b"agent damage")
        evidence = await adapter.capture_recovery_evidence(action, before_snapshot=before)
        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)
        assert result.success is True

        assert stat.S_IMODE(target.stat().st_mode) == 0o640
        verification = await adapter.verify(compensation)
        assert verification.verified is True
        assert "permissions_match" in verification.details.get("metadata_checks_passed", [])
