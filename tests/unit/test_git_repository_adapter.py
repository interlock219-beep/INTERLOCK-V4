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
        original_hash = hashlib.sha256(test_file.read_bytes()).hexdigest()

        adapter = GitRepositoryAdapter(repo_path=repo_path)

        test_file.write_text("app:\n  name: hacked\n  debug: true\n")

        action = _make_git_action(
            action_id="act-e2e-1",
            action_type="modify",
            resource="file:config.yaml",
        )

        evidence = await adapter.capture_recovery_evidence(action)

        evidence.compensation_payload["before_content"] = {
            "exists": True,
            "content": original_content,
            "hash": original_hash,
            "size": len(original_content),
        }

        impact = await adapter.simulate(action, evidence)
        assert impact.would_succeed is True

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)
        assert result.success is True

        verification = await adapter.verify(compensation)
        assert verification.verified is True
        assert test_file.read_text() == original_content

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
