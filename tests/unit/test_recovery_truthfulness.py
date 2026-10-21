"""Batch 2: recovery truthfulness - no silent damage, no forged success.

Covers the audit findings:

- **RE-03** a truncated before-state must never be restored over a file
  (a truncated capture would shrink the user's file and still report success).
- **RE-12** verification must not claim byte-exactness it did not establish
  (a deletion compares no bytes; a rename without a hash compares no bytes).
- **RE-19** verification must not load whole files into memory.
- **RE-06** a delete must re-check the file's identity immediately before
  unlinking it, exactly like a content restore does.

Every test uses a temporary workspace; no project file is touched.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import pytest

from app.domain.entities.protected_action import ActionStatus, ProtectedAction, Reversibility
from app.domain.entities.surgical_recovery_types import ExecutionState
from app.infrastructure.recovery.filesystem_recovery_adapter import FilesystemRecoveryAdapter


def _make_fs_action(
    action_id: str = "act-truth-1",
    action_type: str = "modify",
    resource: str = "file:test.txt",
    tool_arguments: dict | None = None,
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
        tool_arguments=tool_arguments or {"path": resource},
        status=ActionStatus.EXECUTED,
        decision_reason="test",
        evaluated_at=None,
        executed_at=None,
        created_at=None,
    )


# --------------------------------------------------------------------------- #
# RE-03: a truncated before-state must never be restored
# --------------------------------------------------------------------------- #


class TestTruncatedBeforeStateIsRefused:
    """A capture that was truncated cannot restore the original bytes, so it
    must be refused instead of silently shrinking the user's file."""

    @pytest.mark.asyncio
    async def test_restore_refuses_a_truncated_before_state(self, tmp_path: Path) -> None:
        base = tmp_path / "fs"
        base.mkdir()
        target = base / "big.txt"
        original = b"0123456789" * 20  # 200 bytes
        target.write_bytes(original)

        # The before-state was captured with a tiny limit -> truncated capture.
        small = FilesystemRecoveryAdapter(base_path=base, max_file_size_bytes=16)
        action = _make_fs_action(action_type="modify", resource="file:big.txt")
        captured = await small.capture_recovery_evidence(action)
        before = captured.compensation_payload["before_snapshot"]
        assert before["truncated"] is True
        assert before["byte_exact"] is False
        # The snapshot is honest about the truncation but still records the
        # full size - which is exactly what made the restore destructive.
        assert before["size"] == len(original)

        # The agent then damages the file.
        target.write_bytes(b"DAMAGED")

        # The plan is made against the damaged state, with the truncated
        # before-state as the recovery source.
        adapter = FilesystemRecoveryAdapter(base_path=base)
        evidence = await adapter.capture_recovery_evidence(action, before_snapshot=before)
        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is False, "a truncated before-state must not be restored"
        assert result.execution_state == ExecutionState.FAILED
        assert "truncat" in (result.error or "").lower()
        # The user's file must NOT have been shrunk to the captured prefix.
        assert target.read_bytes() == b"DAMAGED"

    @pytest.mark.asyncio
    async def test_verification_fails_closed_for_a_truncated_before_state(
        self, tmp_path: Path
    ) -> None:
        base = tmp_path / "fs"
        base.mkdir()
        target = base / "big.txt"
        target.write_bytes(b"0123456789" * 20)

        small = FilesystemRecoveryAdapter(base_path=base, max_file_size_bytes=16)
        action = _make_fs_action(action_type="modify", resource="file:big.txt")
        captured = await small.capture_recovery_evidence(action)
        before = captured.compensation_payload["before_snapshot"]

        adapter = FilesystemRecoveryAdapter(base_path=base)
        evidence = await adapter.capture_recovery_evidence(action, before_snapshot=before)
        compensation = await adapter.generate_compensation(action, evidence)
        verification = await adapter.verify(compensation)

        assert verification.verified is False
        assert "truncat" in str(verification.details.get("reason", "")).lower()

    @pytest.mark.asyncio
    async def test_a_complete_before_state_still_restores(self, tmp_path: Path) -> None:
        """The refusal must not break the normal path."""
        base = tmp_path / "fs"
        base.mkdir()
        target = base / "small.txt"
        original = b"hello world\n"
        target.write_bytes(original)

        adapter = FilesystemRecoveryAdapter(base_path=base)
        action = _make_fs_action(action_type="modify", resource="file:small.txt")
        captured = await adapter.capture_recovery_evidence(action)
        before = captured.compensation_payload["before_snapshot"]
        assert before["truncated"] is False

        # The agent damages the file, then the plan is made.
        target.write_bytes(b"damaged\n")
        evidence = await adapter.capture_recovery_evidence(action, before_snapshot=before)
        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is True
        assert target.read_bytes() == original
        verification = await adapter.verify(compensation)
        assert verification.verified is True


# --------------------------------------------------------------------------- #
# RE-12: verification must not claim byte-exactness it did not establish
# --------------------------------------------------------------------------- #


class TestVerificationClaimsAreHonest:
    @pytest.mark.asyncio
    async def test_delete_verification_does_not_claim_byte_exact(self, tmp_path: Path) -> None:
        base = tmp_path / "fs"
        base.mkdir()
        target = base / "created.txt"
        target.write_bytes(b"agent created this\n")

        adapter = FilesystemRecoveryAdapter(base_path=base)
        action = _make_fs_action(action_type="create", resource="file:created.txt")
        evidence = await adapter.capture_recovery_evidence(action)
        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)
        assert result.success is True
        assert not target.exists()

        verification = await adapter.verify(compensation)
        # The deletion IS verified - by the file's absence.
        assert verification.verified is True
        # But no bytes were compared, so byte-exactness must not be claimed.
        assert verification.details.get("byte_exact") is not True

    @pytest.mark.asyncio
    async def test_rename_back_without_a_hash_does_not_claim_byte_exact(
        self, tmp_path: Path
    ) -> None:
        base = tmp_path / "fs"
        base.mkdir()
        target = base / "renamed.txt"
        target.write_bytes(b"content\n")

        adapter = FilesystemRecoveryAdapter(base_path=base)
        action = _make_fs_action(
            action_type="rename",
            resource="file:renamed.txt",
            tool_arguments={"path": "file:renamed.txt", "new_path": "file:other.txt"},
        )
        evidence = await adapter.capture_recovery_evidence(action)
        compensation = await adapter.generate_compensation(action, evidence)
        # No hash was captured -> the content cannot be compared.
        compensation.compensation_payload["before_snapshot"] = {
            "exists": True,
            "hash": None,
            "content_b64": None,
        }

        verification = await adapter.verify(compensation)
        assert verification.verified is True
        assert verification.details.get("byte_exact") is not True

    @pytest.mark.asyncio
    async def test_rename_back_with_a_hash_compares_the_bytes(self, tmp_path: Path) -> None:
        base = tmp_path / "fs"
        base.mkdir()
        target = base / "renamed.txt"
        original = b"content\n"
        target.write_bytes(original)

        adapter = FilesystemRecoveryAdapter(base_path=base)
        action = _make_fs_action(
            action_type="rename",
            resource="file:renamed.txt",
            tool_arguments={"path": "file:renamed.txt", "new_path": "file:other.txt"},
        )
        evidence = await adapter.capture_recovery_evidence(action)
        compensation = await adapter.generate_compensation(action, evidence)

        verification = await adapter.verify(compensation)
        assert verification.verified is True
        assert verification.details.get("byte_exact") is True


# --------------------------------------------------------------------------- #
# RE-19: verification must not read whole files into memory
# --------------------------------------------------------------------------- #


class TestVerificationIsBounded:
    @pytest.mark.asyncio
    async def test_verification_does_not_read_whole_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        base = tmp_path / "fs"
        base.mkdir()
        target = base / "big.bin"
        target.write_bytes(b"x" * 4096)

        adapter = FilesystemRecoveryAdapter(base_path=base)
        action = _make_fs_action(action_type="modify", resource="file:big.bin")
        evidence = await adapter.capture_recovery_evidence(action)
        compensation = await adapter.generate_compensation(action, evidence)

        def _forbidden(self: Path) -> bytes:
            raise AssertionError("verification must not load the whole file into memory")

        monkeypatch.setattr(Path, "read_bytes", _forbidden)
        verification = await adapter.verify(compensation)
        assert verification.verified is True


# --------------------------------------------------------------------------- #
# RE-06: a delete must re-check identity immediately before unlinking
# --------------------------------------------------------------------------- #


class TestDeleteRechecksIdentity:
    @pytest.mark.asyncio
    async def test_delete_is_refused_when_the_file_changed_since_the_plan(
        self, tmp_path: Path
    ) -> None:
        base = tmp_path / "fs"
        base.mkdir()
        target = base / "created.txt"
        target.write_bytes(b"agent created this\n")

        adapter = FilesystemRecoveryAdapter(base_path=base)
        action = _make_fs_action(action_type="create", resource="file:created.txt")
        evidence = await adapter.capture_recovery_evidence(action)
        compensation = await adapter.generate_compensation(action, evidence)

        # A human edits the file after the plan was made.
        target.write_bytes(b"human edited this\n")
        human_bytes = target.read_bytes()

        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is False
        assert result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT
        # The human's file must still be there.
        assert target.read_bytes() == human_bytes

    @pytest.mark.asyncio
    async def test_delete_still_works_when_nothing_changed(self, tmp_path: Path) -> None:
        base = tmp_path / "fs"
        base.mkdir()
        target = base / "created.txt"
        target.write_bytes(b"agent created this\n")

        adapter = FilesystemRecoveryAdapter(base_path=base)
        action = _make_fs_action(action_type="create", resource="file:created.txt")
        evidence = await adapter.capture_recovery_evidence(action)
        compensation = await adapter.generate_compensation(action, evidence)

        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)
        assert result.success is True
        assert not target.exists()


# --------------------------------------------------------------------------- #
# Content integrity of the restored bytes (guard against a weakened restore)
# --------------------------------------------------------------------------- #


class TestRestoredContentIsExact:
    @pytest.mark.asyncio
    async def test_binary_content_round_trips_byte_for_byte(self, tmp_path: Path) -> None:
        base = tmp_path / "fs"
        base.mkdir()
        target = base / "data.bin"
        original = bytes(range(256)) * 4
        target.write_bytes(original)

        adapter = FilesystemRecoveryAdapter(base_path=base)
        action = _make_fs_action(action_type="modify", resource="file:data.bin")
        captured = await adapter.capture_recovery_evidence(action)
        before = captured.compensation_payload["before_snapshot"]

        # The agent corrupts the file, then the plan is made.
        target.write_bytes(b"corrupted")
        evidence = await adapter.capture_recovery_evidence(action, before_snapshot=before)
        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)
        assert result.success is True
        assert target.read_bytes() == original
        assert (
            hashlib.sha256(target.read_bytes()).hexdigest()
            == evidence.compensation_payload["before_snapshot"]["hash"]
        )
        stored = evidence.compensation_payload["before_snapshot"]["content_b64"]
        assert base64.b64decode(stored) == original
