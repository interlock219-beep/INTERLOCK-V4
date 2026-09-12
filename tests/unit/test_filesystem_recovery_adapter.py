"""Tests for production-grade filesystem recovery adapter."""

from __future__ import annotations

import base64
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


class TestFilesystemRecoveryAdapterExactBytePreservation:
    """Regression tests for byte-exact file state capture and restoration."""

    @pytest.mark.asyncio
    async def test_capture_snapshot_preserves_lf_and_crlf(self, tmp_path: Path) -> None:
        base_path = tmp_path / "fs"
        base_path.mkdir()

        lf_file = base_path / "lf.txt"
        lf_file.write_bytes(b"alpha\nbeta\ngamma\n")

        crlf_file = base_path / "crlf.txt"
        crlf_file.write_bytes(b"alpha\r\nbeta\r\ngamma\r\n")

        adapter = FilesystemRecoveryAdapter(base_path=base_path)

        lf_snapshot = adapter._capture_file_snapshot(lf_file)
        crlf_snapshot = adapter._capture_file_snapshot(crlf_file)

        assert lf_snapshot is not None
        assert crlf_snapshot is not None
        assert lf_snapshot["content_b64"] != crlf_snapshot["content_b64"]
        assert lf_snapshot["hash"] != crlf_snapshot["hash"]
        assert (
            lf_snapshot["content_b64"]
            == base64.b64encode(b"alpha\nbeta\ngamma\n").decode("ascii")
        )
        assert (
            crlf_snapshot["content_b64"]
            == base64.b64encode(b"alpha\r\nbeta\r\ngamma\r\n").decode("ascii")
        )

    @pytest.mark.asyncio
    async def test_capture_snapshot_preserves_utf8_bom_and_empty_file(self, tmp_path: Path) -> None:
        base_path = tmp_path / "fs"
        base_path.mkdir()

        utf8_file = base_path / "utf8.txt"
        utf8_file.write_bytes("café".encode())

        bom_file = base_path / "bom.txt"
        bom_file.write_bytes("\ufeffhello\n".encode("utf-8-sig"))

        empty_file = base_path / "empty.txt"
        empty_file.write_bytes(b"")

        adapter = FilesystemRecoveryAdapter(base_path=base_path)

        utf8_snapshot = adapter._capture_file_snapshot(utf8_file)
        bom_snapshot = adapter._capture_file_snapshot(bom_file)
        empty_snapshot = adapter._capture_file_snapshot(empty_file)

        assert utf8_snapshot is not None
        assert bom_snapshot is not None
        assert empty_snapshot is not None
        assert utf8_snapshot["hash"] == hashlib.sha256("café".encode()).hexdigest()
        assert bom_snapshot["hash"] == hashlib.sha256(
            "\ufeffhello\n".encode("utf-8-sig")
        ).hexdigest()
        assert empty_snapshot["hash"] == hashlib.sha256(b"").hexdigest()
        assert empty_snapshot["size"] == 0

    @pytest.mark.asyncio
    async def test_restore_exact_bytes_for_whitespace_and_trailing_newline_changes(
        self, tmp_path: Path
    ) -> None:
        base_path = tmp_path / "fs"
        base_path.mkdir()

        original = "  hello\n\n"
        mutated = "  hello\n"
        whitespace_only = " \t \n"

        cases = {
            "trailing_newline.txt": (original.encode("utf-8"), mutated.encode("utf-8")),
            "spaces.txt": (whitespace_only.encode("utf-8"), b"\t\n"),
        }

        adapter = FilesystemRecoveryAdapter(base_path=base_path)

        for name, (original_bytes, mutated_bytes) in cases.items():
            original_file = base_path / name
            original_file.write_bytes(mutated_bytes)

            action = _make_fs_action(
                action_id=f"act-{name}",
                action_type="modify",
                resource=f"file:{name}",
            )
            evidence = await adapter.capture_recovery_evidence(action)
            before_content = original_bytes.decode("utf-8")
            evidence.compensation_payload["before_snapshot"] = {
                "exists": True,
                "content": before_content,
                "content_b64": base64.b64encode(original_bytes).decode("ascii"),
                "hash": hashlib.sha256(original_bytes).hexdigest(),
                "size": len(original_bytes),
                "metadata": None,
                "binary": False,
                "byte_exact": True,
            }

            compensation = await adapter.generate_compensation(action, evidence)
            result = await adapter.execute_compensation(compensation, evidence.idempotency_key)
            assert result.success is True, f"Failed to recover {name}"
            assert original_file.read_bytes() == original_bytes


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
        original_bytes = b"debug=false\nport=8080\n"
        test_file.write_bytes(original_bytes)

        original_hash = hashlib.sha256(original_bytes).hexdigest()

        adapter = FilesystemRecoveryAdapter(base_path=base_path)

        mutated_bytes = b"debug=true\nport=9999\n"
        test_file.write_bytes(mutated_bytes)

        action = _make_fs_action(
            action_id="act-e2e-fs",
            action_type="modify",
            resource="file:app.conf",
        )

        evidence = await adapter.capture_recovery_evidence(action)

        evidence.compensation_payload["before_snapshot"] = {
            "exists": True,
            "content": original_bytes.decode("utf-8"),
            "content_b64": base64.b64encode(original_bytes).decode("ascii"),
            "hash": original_hash,
            "size": len(original_bytes),
            "raw_bytes_length": len(original_bytes),
            "metadata": None,
            "binary": False,
            "byte_exact": True,
        }

        impact = await adapter.simulate(action, evidence)
        assert impact.would_succeed is True

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)
        assert result.success is True

        verification = await adapter.verify(compensation)
        assert verification.verified is True
        assert test_file.read_bytes() == original_bytes

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


class TestFilesystemRecoveryAdapterContainment:
    """Path-containment and traversal rejection tests."""

    @pytest.mark.asyncio
    async def test_resolve_file_path_rejects_traversal(self, tmp_path: Path) -> None:
        base_path = tmp_path / "fs"
        base_path.mkdir()
        adapter = FilesystemRecoveryAdapter(base_path=base_path)
        with pytest.raises(ValueError, match="Path traversal detected in resource identifier"):
            adapter._resolve_file_path("file:../secrets.txt", base_path)

    @pytest.mark.asyncio
    async def test_execute_restore_content_rejects_traversal(self, tmp_path: Path) -> None:
        base_path = tmp_path / "fs"
        base_path.mkdir()
        adapter = FilesystemRecoveryAdapter(base_path=base_path)
        payload = {
            "operation": "restore_content",
            "file_path": "../secrets.txt",
            "before_snapshot": {
                "exists": True,
                "content": "secret",
                "content_b64": __import__("base64").b64encode(b"secret").decode("ascii"),
                "hash": hashlib.sha256(b"secret").hexdigest(),
                "size": 6,
                "metadata": None,
            },
        }
        with pytest.raises(ValueError, match="Path traversal detected in resource identifier"):
            adapter._execute_restore_content(payload, base_path)

