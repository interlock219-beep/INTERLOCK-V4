"""Tests for production-grade filesystem recovery adapter."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.domain.entities.protected_action import ActionStatus, ProtectedAction, Reversibility
from app.domain.entities.surgical_recovery_types import ExecutionState
from app.infrastructure.recovery.filesystem_recovery_adapter import FilesystemRecoveryAdapter


def _make_fs_action(
    action_id: str = "act-fs-1",
    action_type: str = "modify",
    resource: str = "file:test.txt",
    reversibility: Reversibility = Reversibility.AUTOMATICALLY_REVERSIBLE,
    before_state_ref: str | None = "state:before:123",
    tool: str = "filesystem",
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


class TestFilesystemRecoveryAdapterDeclareCapabilities:
    """Test capability declaration."""

    @pytest.mark.asyncio
    async def test_declare_capabilities(self) -> None:
        adapter = FilesystemRecoveryAdapter()
        caps = await adapter.declare_capabilities()
        assert caps.adapter_name == "filesystem_recovery"
        assert caps.can_capture_before_state is True
        assert caps.can_compensate is True
        assert caps.can_verify is True
        assert "atomic_operations" in caps.declared_capabilities


class TestFilesystemRecoveryAdapterCanRecover:
    """Test can_recover classification."""

    @pytest.mark.asyncio
    async def test_can_recover_modify(self) -> None:
        adapter = FilesystemRecoveryAdapter()
        action = _make_fs_action(action_type="modify", before_state_ref="state:abc")
        result = await adapter.can_recover(action)
        assert result == "automatically_reversible"

    @pytest.mark.asyncio
    async def test_can_recover_irreversible(self) -> None:
        adapter = FilesystemRecoveryAdapter()
        action = _make_fs_action(reversibility=Reversibility.IRREVERSIBLE)
        result = await adapter.can_recover(action)
        assert result == "irreversible"

    @pytest.mark.asyncio
    async def test_can_recover_unsupported(self) -> None:
        adapter = FilesystemRecoveryAdapter()
        action = _make_fs_action(tool="email", action_type="send")
        result = await adapter.can_recover(action)
        assert result == "unsupported"


class TestFilesystemRecoveryAdapterCaptureEvidence:
    """Test evidence capture."""

    @pytest.mark.asyncio
    async def test_capture_evidence_with_file(self, tmp_path: Path) -> None:
        base_path = tmp_path / "fs"
        base_path.mkdir()
        test_file = base_path / "test.txt"
        test_file.write_text("Hello, World!")

        adapter = FilesystemRecoveryAdapter(base_path=base_path)
        action = _make_fs_action(resource="file:test.txt")
        evidence = await adapter.capture_recovery_evidence(action)

        assert evidence.action_id == "act-fs-1"
        assert evidence.target_system == "filesystem"
        assert evidence.compensation_payload["before_snapshot"]["exists"] is True
        assert evidence.compensation_payload["before_snapshot"]["content"] == "Hello, World!"

    @pytest.mark.asyncio
    async def test_capture_evidence_missing_file(self, tmp_path: Path) -> None:
        base_path = tmp_path / "fs"
        base_path.mkdir()

        adapter = FilesystemRecoveryAdapter(base_path=base_path)
        action = _make_fs_action(resource="file:missing.txt")
        evidence = await adapter.capture_recovery_evidence(action)

        assert evidence.compensation_payload["before_snapshot"]["exists"] is False


class TestFilesystemRecoveryAdapterExecuteCompensation:
    """Test compensation execution."""

    @pytest.mark.asyncio
    async def test_execute_restore_content(self, tmp_path: Path) -> None:
        base_path = tmp_path / "fs"
        base_path.mkdir()
        test_file = base_path / "test.txt"
        original_content = "Original content"
        test_file.write_text(original_content)

        adapter = FilesystemRecoveryAdapter(base_path=base_path)

        test_file.write_text("Modified by agent")

        action = _make_fs_action(action_type="modify", resource="file:test.txt")
        evidence = await adapter.capture_recovery_evidence(action)

        evidence.compensation_payload["before_snapshot"] = {
            "exists": True,
            "content": original_content,
            "hash": hashlib.sha256(original_content.encode()).hexdigest(),
            "size": len(original_content),
            "metadata": None,
        }

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is True
        assert result.execution_state == ExecutionState.SUCCEEDED
        assert test_file.read_text() == original_content

    @pytest.mark.asyncio
    async def test_execute_delete_file(self, tmp_path: Path) -> None:
        base_path = tmp_path / "fs"
        base_path.mkdir()
        test_file = base_path / "new_file.txt"
        test_file.write_text("New file content")

        adapter = FilesystemRecoveryAdapter(base_path=base_path)
        action = _make_fs_action(action_type="create", resource="file:new_file.txt")
        evidence = await adapter.capture_recovery_evidence(action)

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is True
        assert not test_file.exists()

    @pytest.mark.asyncio
    async def test_execute_restore_deleted_file(self, tmp_path: Path) -> None:
        base_path = tmp_path / "fs"
        base_path.mkdir()
        test_file = base_path / "deleted.txt"
        original_content = "Original content"
        test_file.write_text(original_content)

        adapter = FilesystemRecoveryAdapter(base_path=base_path)
        action = _make_fs_action(action_type="delete", resource="file:deleted.txt")
        evidence = await adapter.capture_recovery_evidence(action)

        test_file.unlink()
        assert not test_file.exists()

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is True
        assert test_file.exists()
        assert test_file.read_text() == original_content

    @pytest.mark.asyncio
    async def test_execute_conflict_blocks_recovery(self, tmp_path: Path) -> None:
        base_path = tmp_path / "fs"
        base_path.mkdir()
        test_file = base_path / "config.txt"
        original_content = "Original content"
        test_file.write_text(original_content)

        adapter = FilesystemRecoveryAdapter(base_path=base_path)
        action = _make_fs_action(action_type="modify", resource="file:config.txt")
        evidence = await adapter.capture_recovery_evidence(action)

        test_file.write_text("Agent modification")
        test_file.write_text("Human modification after agent")

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is False
        assert result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT


class TestFilesystemRecoveryAdapterVerify:
    """Test verification."""

    @pytest.mark.asyncio
    async def test_verify_restore_content(self, tmp_path: Path) -> None:
        base_path = tmp_path / "fs"
        base_path.mkdir()
        test_file = base_path / "test.txt"
        original_content = "Original content"
        test_file.write_text(original_content)

        adapter = FilesystemRecoveryAdapter(base_path=base_path)
        action = _make_fs_action(action_type="modify", resource="file:test.txt")
        evidence = await adapter.capture_recovery_evidence(action)

        compensation = await adapter.generate_compensation(action, evidence)
        verification = await adapter.verify(compensation)

        assert verification.verified is True

    @pytest.mark.asyncio
    async def test_verify_delete_file(self, tmp_path: Path) -> None:
        base_path = tmp_path / "fs"
        base_path.mkdir()

        adapter = FilesystemRecoveryAdapter(base_path=base_path)
        action = _make_fs_action(action_type="create", resource="file:created.txt")
        evidence = await adapter.capture_recovery_evidence(action)

        compensation = await adapter.generate_compensation(action, evidence)
        verification = await adapter.verify(compensation)

        assert verification.verified is True


class TestFilesystemRecoveryAdapterEndToEnd:
    """End-to-end recovery scenarios."""

    @pytest.mark.asyncio
    async def test_full_recovery_workflow(self, tmp_path: Path) -> None:
        base_path = tmp_path / "fs"
        base_path.mkdir()
        test_file = base_path / "app.conf"
        original_content = "debug=false\nport=8080\n"
        test_file.write_text(original_content)

        original_hash = hashlib.sha256(test_file.read_bytes()).hexdigest()

        adapter = FilesystemRecoveryAdapter(base_path=base_path)

        test_file.write_text("debug=true\nport=9999\n")

        action = _make_fs_action(
            action_id="act-e2e-fs",
            action_type="modify",
            resource="file:app.conf",
        )

        evidence = await adapter.capture_recovery_evidence(action)

        evidence.compensation_payload["before_snapshot"] = {
            "exists": True,
            "content": original_content,
            "hash": original_hash,
            "size": len(original_content),
            "metadata": None,
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
    async def test_conflict_preserves_human_changes(self, tmp_path: Path) -> None:
        base_path = tmp_path / "fs"
        base_path.mkdir()
        test_file = base_path / "settings.json"
        original_content = '{"key": "original"}'
        test_file.write_text(original_content)

        adapter = FilesystemRecoveryAdapter(base_path=base_path)
        action = _make_fs_action(action_type="modify", resource="file:settings.json")
        evidence = await adapter.capture_recovery_evidence(action)

        test_file.write_text('{"key": "agent_value"}')
        test_file.write_text('{"key": "human_value"}')

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is False
        assert test_file.read_text() == '{"key": "human_value"}'

    @pytest.mark.asyncio
    async def test_binary_file_recovery(self, tmp_path: Path) -> None:
        base_path = tmp_path / "fs"
        base_path.mkdir()
        test_file = base_path / "data.bin"
        original_bytes = bytes(range(256))
        test_file.write_bytes(original_bytes)

        adapter = FilesystemRecoveryAdapter(base_path=base_path)

        test_file.write_bytes(b"\x00" * 100)

        action = _make_fs_action(action_type="modify", resource="file:data.bin")
        evidence = await adapter.capture_recovery_evidence(action)

        original_hash = hashlib.sha256(original_bytes).hexdigest()
        import base64
        evidence.compensation_payload["before_snapshot"] = {
            "exists": True,
            "content": None,
            "content_b64": base64.b64encode(original_bytes).decode("ascii"),
            "hash": original_hash,
            "size": len(original_bytes),
            "metadata": None,
            "binary": True,
        }

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is True
        assert test_file.read_bytes() == original_bytes
