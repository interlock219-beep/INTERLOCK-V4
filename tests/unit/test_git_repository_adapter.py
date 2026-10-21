"""Tests for production-grade Git repository recovery adapter."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from app.domain.entities.protected_action import ActionStatus, ProtectedAction, Reversibility
from app.domain.entities.surgical_recovery_types import (
    ExecutionState,
)
from app.infrastructure.recovery.git_repository_adapter import GitRepositoryAdapter


def _make_git_action(
    action_id: str = "act-git-1",
    action_type: str = "modify",
    resource: str = "file:readme.txt",
    reversibility: Reversibility = Reversibility.AUTOMATICALLY_REVERSIBLE,
    before_state_ref: str | None = "state:before:123",
    tool: str = "git",
) -> ProtectedAction:
    return ProtectedAction(
        action_id=action_id,
        tenant_id="test-tenant",
        agent_id="agent-test",
        actor_user_id=None,
        authority_grant_id=None,
        tool=tool,
        resource=resource,
        action_type=action_type,
        risk_score=0.5,
        policy_version="v1",
        correlation_id="corr-1",
        parent_action_id=None,
        workflow_id=None,
        reversibility=reversibility,
        before_state_ref=before_state_ref,
        after_state_ref="state:after:456",
        tool_arguments={"path": resource},
        status=ActionStatus.EXECUTED,
        decision_reason="test",
        evaluated_at=None,
        executed_at=None,
        created_at=None,
    )


def _init_git_repo(path: Path) -> None:
    """Initialize a git repository at the given path."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, capture_output=True, check=True)  # noqa: S607
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],  # noqa: S607
        cwd=path, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],  # noqa: S607
        cwd=path, capture_output=True, check=True,
    )


class TestGitRepositoryAdapterDeclareCapabilities:
    """Test capability declaration."""

    @pytest.mark.asyncio
    async def test_declare_capabilities_returns_production_validated(self) -> None:
        adapter = GitRepositoryAdapter()
        caps = await adapter.declare_capabilities()
        assert caps.adapter_name == "git_repository"
        assert caps.can_capture_before_state is True
        assert caps.can_compensate is True
        assert caps.can_verify is True
        assert caps.can_detect_drift is True
        assert caps.can_simulate is True
        assert "file_modification_recovery" in caps.declared_capabilities


class TestGitRepositoryAdapterCanRecover:
    """Test can_recover classification."""

    @pytest.mark.asyncio
    async def test_can_recover_modify_with_before_state(self) -> None:
        adapter = GitRepositoryAdapter()
        action = _make_git_action(action_type="modify", before_state_ref="state:abc")
        result = await adapter.can_recover(action)
        assert result == "automatically_reversible"

    @pytest.mark.asyncio
    async def test_can_recover_irreversible(self) -> None:
        adapter = GitRepositoryAdapter()
        action = _make_git_action(
            action_type="modify",
            reversibility=Reversibility.IRREVERSIBLE,
        )
        result = await adapter.can_recover(action)
        assert result == "irreversible"

    @pytest.mark.asyncio
    async def test_can_recover_unsupported_tool(self) -> None:
        adapter = GitRepositoryAdapter()
        action = _make_git_action(tool="email", action_type="send")
        result = await adapter.can_recover(action)
        assert result == "unsupported"


class TestGitRepositoryAdapterCaptureEvidence:
    """Test evidence capture."""

    @pytest.mark.asyncio
    async def test_capture_evidence_with_real_file(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_git_repo(repo_path)
        test_file = repo_path / "readme.txt"
        test_file.write_text("Hello, World!")

        adapter = GitRepositoryAdapter(repo_path=repo_path)
        action = _make_git_action(resource="file:readme.txt")
        evidence = await adapter.capture_recovery_evidence(action)

        assert evidence.action_id == "act-git-1"
        assert evidence.target_system == "git_repository"
        assert evidence.before_state_reference is not None
        assert evidence.compensation_payload["operation"] == "restore_content"
        assert evidence.compensation_payload["before_content"]["exists"] is True
        assert evidence.compensation_payload["before_content"]["content"] == "Hello, World!"

    @pytest.mark.asyncio
    async def test_capture_evidence_missing_file(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_git_repo(repo_path)

        adapter = GitRepositoryAdapter(repo_path=repo_path)
        action = _make_git_action(resource="file:missing.txt")
        evidence = await adapter.capture_recovery_evidence(action)

        assert evidence.compensation_payload["before_content"]["exists"] is False


class TestGitRepositoryAdapterSimulate:
    """Test simulation."""

    @pytest.mark.asyncio
    async def test_simulate_restore_content(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_git_repo(repo_path)
        test_file = repo_path / "readme.txt"
        test_file.write_text("Original content")

        adapter = GitRepositoryAdapter(repo_path=repo_path)
        action = _make_git_action(action_type="modify", resource="file:readme.txt")
        evidence = await adapter.capture_recovery_evidence(action)
        impact = await adapter.simulate(action, evidence)

        assert impact.would_succeed is True
        assert impact.compensation_operation == "restore_content"

    @pytest.mark.asyncio
    async def test_simulate_delete_file(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_git_repo(repo_path)

        adapter = GitRepositoryAdapter(repo_path=repo_path)
        action = _make_git_action(action_type="create", resource="file:new.txt")
        evidence = await adapter.capture_recovery_evidence(action)
        impact = await adapter.simulate(action, evidence)

        assert impact.compensation_operation == "delete_file"


class TestGitRepositoryAdapterDetectDrift:
    """Test drift detection."""

    @pytest.mark.asyncio
    async def test_detect_drift_no_drift(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_git_repo(repo_path)
        test_file = repo_path / "readme.txt"
        test_file.write_text("Original content")

        adapter = GitRepositoryAdapter(repo_path=repo_path)
        action = _make_git_action(action_type="modify", resource="file:readme.txt")
        evidence = await adapter.capture_recovery_evidence(action)

        drift = await adapter.detect_drift(
            action, evidence, {"repo_path": str(repo_path)}
        )
        assert drift.status.value == "no_drift"

    @pytest.mark.asyncio
    async def test_detect_drift_content_changed(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_git_repo(repo_path)
        test_file = repo_path / "readme.txt"
        test_file.write_text("Original content")

        adapter = GitRepositoryAdapter(repo_path=repo_path)
        action = _make_git_action(action_type="modify", resource="file:readme.txt")
        evidence = await adapter.capture_recovery_evidence(action)

        test_file.write_text("Modified by agent")

        drift = await adapter.detect_drift(
            action, evidence, {"repo_path": str(repo_path)}
        )
        assert drift.status.value == "drift_detected"


class TestGitRepositoryAdapterExecuteCompensation:
    """Test compensation execution."""

    @pytest.mark.asyncio
    async def test_execute_restore_content(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_git_repo(repo_path)
        test_file = repo_path / "readme.txt"
        original_content = "Original content"
        test_file.write_text(original_content)

        adapter = GitRepositoryAdapter(repo_path=repo_path)

        test_file.write_text("Modified by agent")

        action = _make_git_action(action_type="modify", resource="file:readme.txt")
        evidence = await adapter.capture_recovery_evidence(action)

        evidence.compensation_payload["before_content"] = {
            "exists": True,
            "content": original_content,
            "hash": hashlib.sha256(original_content.encode()).hexdigest(),
            "size": len(original_content),
        }

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is True
        assert result.execution_state == ExecutionState.SUCCEEDED
        assert test_file.read_text() == original_content

    @pytest.mark.asyncio
    async def test_execute_delete_file(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_git_repo(repo_path)
        test_file = repo_path / "new_file.txt"
        test_file.write_text("New file content")

        adapter = GitRepositoryAdapter(repo_path=repo_path)
        action = _make_git_action(action_type="create", resource="file:new_file.txt")
        evidence = await adapter.capture_recovery_evidence(action)

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is True
        assert result.execution_state == ExecutionState.SUCCEEDED
        assert not test_file.exists()

    @pytest.mark.asyncio
    async def test_execute_restore_deleted_file(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_git_repo(repo_path)
        test_file = repo_path / "readme.txt"
        original_content = "Original content"
        test_file.write_text(original_content)

        adapter = GitRepositoryAdapter(repo_path=repo_path)
        action = _make_git_action(action_type="delete", resource="file:readme.txt")
        evidence = await adapter.capture_recovery_evidence(action)

        test_file.unlink()
        assert not test_file.exists()

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is True
        assert result.execution_state == ExecutionState.SUCCEEDED
        assert test_file.exists()
        assert test_file.read_text() == original_content

    @pytest.mark.asyncio
    async def test_execute_conflict_blocks_recovery(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_git_repo(repo_path)
        test_file = repo_path / "readme.txt"
        original_content = "Original content"
        test_file.write_text(original_content)

        adapter = GitRepositoryAdapter(repo_path=repo_path)
        action = _make_git_action(action_type="modify", resource="file:readme.txt")
        evidence = await adapter.capture_recovery_evidence(action)

        test_file.write_text("Agent modification")
        test_file.write_text("Human modification after agent")

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is False
        assert result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT


class TestGitRepositoryAdapterVerify:
    """Test verification."""

    @pytest.mark.asyncio
    async def test_verify_restore_content_success(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_git_repo(repo_path)
        test_file = repo_path / "readme.txt"
        original_content = "Original content"
        test_file.write_text(original_content)

        adapter = GitRepositoryAdapter(repo_path=repo_path)
        action = _make_git_action(action_type="modify", resource="file:readme.txt")
        evidence = await adapter.capture_recovery_evidence(action)

        compensation = await adapter.generate_compensation(action, evidence)
        verification = await adapter.verify(compensation)

        assert verification.verified is True

    @pytest.mark.asyncio
    async def test_verify_delete_file_success(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_git_repo(repo_path)

        adapter = GitRepositoryAdapter(repo_path=repo_path)
        action = _make_git_action(action_type="create", resource="file:created.txt")
        evidence = await adapter.capture_recovery_evidence(action)

        compensation = await adapter.generate_compensation(action, evidence)
        verification = await adapter.verify(compensation)

        assert verification.verified is True


class TestGitRepositoryAdapterIdempotency:
    """Test idempotency guarantees."""

    @pytest.mark.asyncio
    async def test_idempotency_key_mismatch(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_git_repo(repo_path)

        adapter = GitRepositoryAdapter(repo_path=repo_path)
        action = _make_git_action()
        evidence = await adapter.capture_recovery_evidence(action)
        compensation = await adapter.generate_compensation(action, evidence)

        result = await adapter.execute_compensation(compensation, "wrong-key")
        assert result.success is False
        assert result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT


class TestGitRepositoryAdapterEndToEnd:
    """End-to-end recovery scenarios."""

    @pytest.mark.asyncio
    async def test_full_recovery_workflow(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_git_repo(repo_path)
        test_file = repo_path / "config.yaml"
        original_content = "app:\n  name: myapp\n  debug: false\n"
        test_file.write_text(original_content)

        import hashlib
        original_bytes = test_file.read_bytes()
        original_hash = hashlib.sha256(original_bytes).hexdigest()

        adapter = GitRepositoryAdapter(repo_path=repo_path)
        action = _make_git_action(
            action_id="act-e2e-1",
            action_type="modify",
            resource="file:config.yaml",
        )

        # 1. The before-state is captured while the file still holds the
        #    original. The adapter stores the RAW BYTES, so the restore
        #    reproduces the recorded hash exactly (the previous text-only
        #    capture could not reproduce a CRLF file's hash).
        before_content = (await adapter.capture_recovery_evidence(action)).compensation_payload[
            "before_content"
        ]
        assert before_content["hash"] == original_hash
        assert before_content["content_b64"] is not None

        # 2. The agent damages the file.
        test_file.write_text("app:\n  name: hacked\n  debug: true\n")

        # 3. The plan is made against the damaged state, with the captured
        #    before-state as the recovery source.
        evidence = await adapter.capture_recovery_evidence(
            action, before_snapshot=before_content
        )
        impact = await adapter.simulate(action, evidence)
        assert impact.would_succeed is True

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)
        assert result.success is True

        verification = await adapter.verify(compensation)
        assert verification.verified is True
        # Byte for byte - not "the text happens to match".
        assert test_file.read_bytes() == original_bytes

    @pytest.mark.asyncio
    async def test_a_restore_that_cannot_reproduce_the_hash_fails_closed(
        self, tmp_path: Path
    ) -> None:
        """A before-state whose text cannot reproduce the recorded hash must be
        REFUSED, not silently written as different bytes.

        This is the defect the adapter used to have: it captured text (with
        universal-newline translation) while hashing the raw bytes, so a CRLF
        file was restored with LF endings and reported as a success.
        """
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_git_repo(repo_path)
        test_file = repo_path / "config.yaml"
        test_file.write_text("app:\n  name: myapp\n  debug: false\n")

        import hashlib
        original_bytes = test_file.read_bytes()
        original_hash = hashlib.sha256(original_bytes).hexdigest()

        adapter = GitRepositoryAdapter(repo_path=repo_path)
        action = _make_git_action(
            action_id="act-mismatch-1",
            action_type="modify",
            resource="file:config.yaml",
        )
        before_content = (await adapter.capture_recovery_evidence(action)).compensation_payload[
            "before_content"
        ]

        # A text-only before-state whose bytes do NOT match the recorded hash
        # (the byte form is missing, and the text has LF where the file had CRLF).
        lossy_before = dict(before_content)
        lossy_before["content_b64"] = None
        lossy_before["content"] = "app:\n  name: myapp\n  debug: false\n"

        damaged = b"app:\n  name: hacked\n  debug: true\n"
        test_file.write_text("app:\n  name: hacked\n  debug: true\n")
        damaged = test_file.read_bytes()

        evidence = await adapter.capture_recovery_evidence(action, before_snapshot=lossy_before)
        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is False
        assert result.execution_state == ExecutionState.FAILED
        assert "hash mismatch" in (result.error or "").lower()
        # The file was not silently rewritten with different bytes.
        assert test_file.read_bytes() == damaged
        assert original_hash != hashlib.sha256(damaged).hexdigest()

    @pytest.mark.asyncio
    async def test_conflict_prevents_blind_overwrite(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_git_repo(repo_path)
        test_file = tmp_path / "repo" / "settings.json"
        original_content = '{"key": "original"}'
        test_file.write_text(original_content)

        adapter = GitRepositoryAdapter(repo_path=repo_path)
        action = _make_git_action(
            action_id="act-conflict-1",
            action_type="modify",
            resource="file:settings.json",
        )

        evidence = await adapter.capture_recovery_evidence(action)

        test_file.write_text('{"key": "agent_value"}')

        test_file.write_text('{"key": "human_value"}')

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is False
        assert result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT
        assert test_file.read_text() == '{"key": "human_value"}'


class TestGitRepositoryAdapterPayloadContainment:
    """Tampered compensation payloads must never escape the repository root.

    Release-gate audit: execute/verify previously joined
    ``repo_path / payload['file_path']`` with no containment check, so an
    absolute path (or ``..`` segment) stored in a tampered evidence payload
    could delete or overwrite files outside the repository — the same defect
    class as the config-adapter traversal hardening (V5-9).
    """

    @pytest.mark.asyncio
    async def test_execute_refuses_path_traversal_payload(
        self, tmp_path: Path
    ) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_git_repo(repo_path)
        victim = tmp_path / "victim.txt"
        victim.write_text("user data")

        adapter = GitRepositoryAdapter(repo_path=repo_path)
        action = _make_git_action(action_type="create", resource="file:created.txt")
        evidence = await adapter.capture_recovery_evidence(action)
        evidence.compensation_payload["operation"] = "delete_file"
        evidence.compensation_payload["file_path"] = "../victim.txt"
        compensation = await adapter.generate_compensation(action, evidence)

        result = await adapter.execute_compensation(
            compensation, evidence.idempotency_key
        )

        assert result.success is False
        assert result.execution_state == ExecutionState.FAILED
        assert "traversal" in (result.error or "").lower()
        # User data outside the repository survives a tampered payload.
        assert victim.exists()
        assert victim.read_text() == "user data"

    @pytest.mark.asyncio
    async def test_execute_refuses_absolute_path_payload(
        self, tmp_path: Path
    ) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_git_repo(repo_path)
        victim = tmp_path / "victim.txt"
        victim.write_text("user data")

        adapter = GitRepositoryAdapter(repo_path=repo_path)
        action = _make_git_action(action_type="create", resource="file:created.txt")
        evidence = await adapter.capture_recovery_evidence(action)
        evidence.compensation_payload["operation"] = "delete_file"
        evidence.compensation_payload["file_path"] = str(victim)
        compensation = await adapter.generate_compensation(action, evidence)

        result = await adapter.execute_compensation(
            compensation, evidence.idempotency_key
        )

        assert result.success is False
        assert result.execution_state == ExecutionState.FAILED
        assert "absolute path refused" in (result.error or "").lower()
        assert victim.exists()
        assert victim.read_text() == "user data"

    @pytest.mark.asyncio
    async def test_verify_refuses_payload_outside_repository(
        self, tmp_path: Path
    ) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_git_repo(repo_path)
        victim = tmp_path / "victim.txt"
        victim.write_text("user data")
        victim_hash = hashlib.sha256(victim.read_bytes()).hexdigest()

        adapter = GitRepositoryAdapter(repo_path=repo_path)
        action = _make_git_action(action_type="modify", resource="file:readme.txt")
        evidence = await adapter.capture_recovery_evidence(action)
        evidence.compensation_payload["operation"] = "restore_content"
        evidence.compensation_payload["file_path"] = str(victim)
        evidence.compensation_payload["before_content"] = {
            "exists": True,
            "content": "user data",
            "hash": victim_hash,
            "size": len("user data"),
        }
        compensation = await adapter.generate_compensation(action, evidence)

        verification = await adapter.verify(compensation)

        # Verification must refuse to read (and self-certify) a path outside
        # the repository instead of comparing against the victim file.
        assert verification.verified is False
        assert "refused" in str(verification.details.get("reason", "")).lower()

    @pytest.mark.asyncio
    async def test_detect_drift_refuses_absolute_resource(
        self, tmp_path: Path
    ) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_git_repo(repo_path)
        (repo_path / "readme.txt").write_text("Original content")
        outside = tmp_path / "outside.txt"
        outside.write_text("Not in the repository")

        adapter = GitRepositoryAdapter(repo_path=repo_path)
        capture_action = _make_git_action(
            action_type="modify", resource="file:readme.txt"
        )
        evidence = await adapter.capture_recovery_evidence(capture_action)

        tampered_action = _make_git_action(
            action_type="modify", resource=f"file:{outside}"
        )
        with pytest.raises(ValueError, match="outside base path"):
            await adapter.detect_drift(
                tampered_action, evidence, {"repo_path": str(repo_path)}
            )


class TestGitRepositoryAdapterRenameHonesty:
    """The declared rename-recovery capability must not over-claim: rename
    reversal is not implemented (the original destination is not recorded in
    evidence), so drift must not assert NO_DRIFT, execution must demand manual
    action, and verification must not self-certify."""

    @pytest.mark.asyncio
    async def test_rename_drift_is_insufficient_evidence(
        self, tmp_path: Path
    ) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_git_repo(repo_path)
        (repo_path / "old.txt").write_text("content")

        adapter = GitRepositoryAdapter(repo_path=repo_path)
        action = _make_git_action(action_type="rename", resource="file:old.txt")
        evidence = await adapter.capture_recovery_evidence(action)

        drift = await adapter.detect_drift(
            action, evidence, {"repo_path": str(repo_path)}
        )

        assert drift.status.value == "insufficient_evidence"

    @pytest.mark.asyncio
    async def test_rename_back_requires_manual_action(
        self, tmp_path: Path
    ) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_git_repo(repo_path)
        (repo_path / "old.txt").write_text("content")

        adapter = GitRepositoryAdapter(repo_path=repo_path)
        action = _make_git_action(action_type="rename", resource="file:old.txt")
        evidence = await adapter.capture_recovery_evidence(action)
        compensation = await adapter.generate_compensation(action, evidence)

        result = await adapter.execute_compensation(
            compensation, evidence.idempotency_key
        )

        assert result.success is False
        assert result.execution_state == ExecutionState.REQUIRES_MANUAL_ACTION

        verification = await adapter.verify(compensation)
        assert verification.verified is False


class TestGitRepositoryAdapterBeforeSnapshot:
    """capture_recovery_evidence must honor the pre-action before snapshot
    (same contract as the config/filesystem adapters, V5-8): the live file is
    the post-action state, not both sides of the comparison."""

    @pytest.mark.asyncio
    async def test_capture_honors_before_snapshot(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_git_repo(repo_path)
        (repo_path / "readme.txt").write_text("after agent action")

        adapter = GitRepositoryAdapter(repo_path=repo_path)
        action = _make_git_action(action_type="modify", resource="file:readme.txt")
        snapshot = {
            "exists": True,
            "content": "original content",
            "hash": "snapshot-hash",
            "size": len("original content"),
        }

        evidence = await adapter.capture_recovery_evidence(
            action, before_snapshot=snapshot
        )

        payload = evidence.compensation_payload
        assert payload["before_content"]["content"] == "original content"
        assert payload["after_content"]["content"] == "after agent action"
