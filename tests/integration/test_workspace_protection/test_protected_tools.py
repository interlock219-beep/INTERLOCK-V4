"""Tests for protected filesystem tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from sdk.workspace_protection.path_security import PathSecurityError, WorkspacePathSecurity
from sdk.workspace_protection.protected_tools import (
    ProtectedFilesystemError,
    ProtectedFilesystemTools,
)


def _mock_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = path.rstrip("/") or "/"
    if normalized == "/api/v1/actions":
        return {"action_id": "act-test-123", "status": "pending"}
    if normalized.endswith("/evaluate"):
        return {"action_id": "act-test-123", "status": "permitted"}
    if normalized == "/api/v1/intent/verify":
        return {"ephemeral_token": "token-123"}
    if normalized == "/api/v1/intent/execute":
        return {"status": "executed"}
    if normalized == "/api/v1/intent/authorize-mutation":
        return {"status": "mutation_authorized"}
    return {}


def _mock_get(path: str) -> dict[str, Any]:
    return {"items": []}


def _mock_patch(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    if "/api/v1/actions/" in path and path.endswith("/execution"):
        return {"status": "executed"}
    return {}


class TestProtectedFilesystemTools:
    def test_write_file_authorized(self, tmp_path: Path) -> None:
        security = WorkspacePathSecurity(tmp_path)
        tools = ProtectedFilesystemTools(path_security=security, gateway_url="http://test")

        with patch.object(tools, "_post_json", side_effect=_mock_post), \
             patch.object(tools, "_patch_json", side_effect=_mock_patch):
            result = tools.write_file(
                path=tmp_path / "test.txt",
                content="hello",
                agent_id="agent-1",
                session_id="ses-1",
                correlation_id="corr-1",
            )

        assert result["status"] == "written"
        assert result["action_id"] == "act-test-123"
        assert (tmp_path / "test.txt").read_text(encoding="utf-8") == "hello"

    def test_write_file_path_outside_workspace_rejected(self, tmp_path: Path) -> None:
        security = WorkspacePathSecurity(tmp_path)
        tools = ProtectedFilesystemTools(path_security=security, gateway_url="http://test")

        with pytest.raises(PathSecurityError, match="outside workspace"):
            tools.write_file(
                path="/etc/passwd",
                content="bad",
                agent_id="agent-1",
                session_id="ses-1",
                correlation_id="corr-1",
            )

    def test_write_file_denied_by_interlock(self, tmp_path: Path) -> None:
        security = WorkspacePathSecurity(tmp_path)
        tools = ProtectedFilesystemTools(path_security=security, gateway_url="http://test")

        def deny_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
            normalized = path.rstrip("/") or "/"
            if normalized == "/api/v1/actions":
                return {"action_id": "act-test-123", "status": "pending"}
            if normalized.endswith("/evaluate"):
                return {
                    "action_id": "act-test-123",
                    "status": "denied",
                    "decision_reason": "policy",
                }
            return {}

        with patch.object(tools, "_post_json", side_effect=deny_post), \
             pytest.raises(ProtectedFilesystemError, match="Interlock denied"):
            tools.write_file(
                    path=tmp_path / "test.txt",
                    content="hello",
                    agent_id="agent-1",
                    session_id="ses-1",
                    correlation_id="corr-1",
                )

        assert not (tmp_path / "test.txt").exists()

    def test_edit_file_creates_parent_dirs(self, tmp_path: Path) -> None:
        security = WorkspacePathSecurity(tmp_path)
        tools = ProtectedFilesystemTools(path_security=security, gateway_url="http://test")
        target = tmp_path / "deep" / "nested" / "file.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("original", encoding="utf-8")

        with patch.object(tools, "_post_json", side_effect=_mock_post), \
             patch.object(tools, "_patch_json", side_effect=_mock_patch):
            result = tools.edit_file(
                path=target,
                new_content="modified",
                agent_id="agent-1",
                session_id="ses-1",
                correlation_id="corr-1",
            )

        assert result["status"] == "edited"
        assert target.read_text(encoding="utf-8") == "modified"

    def test_edit_file_missing_raises(self, tmp_path: Path) -> None:
        security = WorkspacePathSecurity(tmp_path)
        tools = ProtectedFilesystemTools(path_security=security, gateway_url="http://test")
        target = tmp_path / "missing.txt"

        with pytest.raises(ProtectedFilesystemError, match="File does not exist"):
            tools.edit_file(
                path=target,
                new_content="hello",
                agent_id="agent-1",
                session_id="ses-1",
                correlation_id="corr-1",
            )

    def test_delete_file(self, tmp_path: Path) -> None:
        security = WorkspacePathSecurity(tmp_path)
        tools = ProtectedFilesystemTools(path_security=security, gateway_url="http://test")
        target = tmp_path / "delete_me.txt"
        target.write_text("temp", encoding="utf-8")

        with patch.object(tools, "_post_json", side_effect=_mock_post), \
             patch.object(tools, "_patch_json", side_effect=_mock_patch):
            result = tools.delete_file(
                path=target,
                agent_id="agent-1",
                session_id="ses-1",
                correlation_id="corr-1",
            )

        assert result["status"] == "deleted"
        assert not target.exists()

    def test_rename_file(self, tmp_path: Path) -> None:
        security = WorkspacePathSecurity(tmp_path)
        tools = ProtectedFilesystemTools(path_security=security, gateway_url="http://test")
        source = tmp_path / "old.txt"
        source.write_text("hello", encoding="utf-8")
        dest = tmp_path / "new.txt"

        with patch.object(tools, "_post_json", side_effect=_mock_post), \
             patch.object(tools, "_patch_json", side_effect=_mock_patch):
            result = tools.rename_file(
                old_path=source,
                new_path=dest,
                agent_id="agent-1",
                session_id="ses-1",
                correlation_id="corr-1",
            )

        assert result["status"] == "renamed"
        assert not source.exists()
        assert dest.read_text(encoding="utf-8") == "hello"

    def test_rename_file_missing_source_raises(self, tmp_path: Path) -> None:
        security = WorkspacePathSecurity(tmp_path)
        tools = ProtectedFilesystemTools(path_security=security, gateway_url="http://test")
        source = tmp_path / "missing.txt"
        dest = tmp_path / "dest.txt"

        with pytest.raises(ProtectedFilesystemError, match="does not exist"):
            tools.rename_file(
                old_path=source,
                new_path=dest,
                agent_id="agent-1",
                session_id="ses-1",
                correlation_id="corr-1",
            )

    def test_authorization_denial_blocks_operation(self, tmp_path: Path) -> None:
        security = WorkspacePathSecurity(tmp_path)
        tools = ProtectedFilesystemTools(path_security=security, gateway_url="http://test")
        target = tmp_path / "test.txt"
        target.write_text("original", encoding="utf-8")

        call_count = 0

        def deny_after_create(path: str, payload: dict[str, Any]) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            normalized = path.rstrip("/") or "/"
            if normalized == "/api/v1/actions":
                return {"action_id": "act-test-123", "status": "pending"}
            if normalized.endswith("/evaluate"):
                return {"action_id": "act-test-123", "status": "denied"}
            return {}

        with patch.object(tools, "_post_json", side_effect=deny_after_create), \
             pytest.raises(ProtectedFilesystemError, match="Interlock denied"):
            tools.edit_file(
                    path=target,
                    new_content="modified",
                    agent_id="agent-1",
                    session_id="ses-1",
                    correlation_id="corr-1",
                )

        assert target.read_text(encoding="utf-8") == "original"

    def test_frozen_session_blocks_mutation(self, tmp_path: Path) -> None:
        security = WorkspacePathSecurity(tmp_path)
        tools = ProtectedFilesystemTools(path_security=security, gateway_url="http://test")
        target = tmp_path / "frozen.txt"

        def block_mutation(path: str, payload: dict[str, Any]) -> dict[str, Any]:
            normalized = path.rstrip("/") or "/"
            if normalized == "/api/v1/actions":
                return {"action_id": "act-frozen", "status": "pending"}
            if normalized.endswith("/evaluate"):
                return {"action_id": "act-frozen", "status": "permitted"}
            if normalized == "/api/v1/intent/verify":
                return {"ephemeral_token": "token-frozen"}
            if normalized == "/api/v1/intent/execute":
                return {"status": "executed"}
            if normalized == "/api/v1/intent/authorize-mutation":
                raise ProtectedFilesystemError("Session is frozen.")
            return {}

        with patch.object(tools, "_post_json", side_effect=block_mutation), \
             patch.object(tools, "_patch_json", return_value={"status": "executed"}), \
             pytest.raises(ProtectedFilesystemError, match="Session is frozen"):
                tools.write_file(
                    path=target,
                    content="blocked",
                    agent_id="agent-1",
                    session_id="ses-frozen",
                    correlation_id="corr-1",
                )

        assert not target.exists()

    def test_revoked_agent_blocks_mutation(self, tmp_path: Path) -> None:
        security = WorkspacePathSecurity(tmp_path)
        tools = ProtectedFilesystemTools(path_security=security, gateway_url="http://test")
        target = tmp_path / "revoked.txt"

        def block_mutation(path: str, payload: dict[str, Any]) -> dict[str, Any]:
            normalized = path.rstrip("/") or "/"
            if normalized == "/api/v1/actions":
                return {"action_id": "act-revoked", "status": "pending"}
            if normalized.endswith("/evaluate"):
                return {"action_id": "act-revoked", "status": "permitted"}
            if normalized == "/api/v1/intent/verify":
                return {"ephemeral_token": "token-revoked"}
            if normalized == "/api/v1/intent/execute":
                return {"status": "executed"}
            if normalized == "/api/v1/intent/authorize-mutation":
                raise ProtectedFilesystemError("Agent is revoked.")
            return {}

        with patch.object(tools, "_post_json", side_effect=block_mutation), \
             patch.object(tools, "_patch_json", return_value={"status": "executed"}), \
             pytest.raises(ProtectedFilesystemError, match="Agent is revoked"):
                tools.write_file(
                    path=target,
                    content="blocked",
                    agent_id="agent-revoked",
                    session_id="ses-1",
                    correlation_id="corr-1",
                )

        assert not target.exists()

    def test_quarantined_agent_blocks_mutation(self, tmp_path: Path) -> None:
        security = WorkspacePathSecurity(tmp_path)
        tools = ProtectedFilesystemTools(path_security=security, gateway_url="http://test")
        target = tmp_path / "quarantined.txt"

        def block_mutation(path: str, payload: dict[str, Any]) -> dict[str, Any]:
            normalized = path.rstrip("/") or "/"
            if normalized == "/api/v1/actions":
                return {"action_id": "act-quarantined", "status": "pending"}
            if normalized.endswith("/evaluate"):
                return {"action_id": "act-quarantined", "status": "permitted"}
            if normalized == "/api/v1/intent/verify":
                return {"ephemeral_token": "token-quarantined"}
            if normalized == "/api/v1/intent/execute":
                return {"status": "executed"}
            if normalized == "/api/v1/intent/authorize-mutation":
                raise ProtectedFilesystemError("Agent is quarantined.")
            return {}

        with patch.object(tools, "_post_json", side_effect=block_mutation), \
             patch.object(tools, "_patch_json", return_value={"status": "executed"}), \
             pytest.raises(ProtectedFilesystemError, match="Agent is quarantined"):
                tools.write_file(
                    path=target,
                    content="blocked",
                    agent_id="agent-quarantined",
                    session_id="ses-1",
                    correlation_id="corr-1",
                )

        assert not target.exists()

    def test_token_issued_before_freeze_blocks_mutation(self, tmp_path: Path) -> None:
        security = WorkspacePathSecurity(tmp_path)
        tools = ProtectedFilesystemTools(path_security=security, gateway_url="http://test")
        target = tmp_path / "race.txt"

        def block_authorize(path: str, payload: dict[str, Any]) -> dict[str, Any]:
            normalized = path.rstrip("/") or "/"
            if normalized == "/api/v1/actions":
                return {"action_id": "act-race", "status": "pending"}
            if normalized.endswith("/evaluate"):
                return {"action_id": "act-race", "status": "permitted"}
            if normalized == "/api/v1/intent/verify":
                return {"ephemeral_token": "token-race"}
            if normalized == "/api/v1/intent/execute":
                return {"status": "executed"}
            if normalized == "/api/v1/intent/authorize-mutation":
                raise ProtectedFilesystemError("Session is frozen.")
            return {}

        with patch.object(tools, "_post_json", side_effect=block_authorize), \
             patch.object(tools, "_patch_json", return_value={"status": "executed"}), \
             pytest.raises(ProtectedFilesystemError, match="Session is frozen"):
                tools.write_file(
                    path=target,
                    content="blocked",
                    agent_id="agent-race",
                    session_id="ses-race",
                    correlation_id="corr-race",
                )

        assert not target.exists()

    def test_concurrent_freeze_blocks_action_b(self, tmp_path: Path) -> None:
        security = WorkspacePathSecurity(tmp_path)
        tools = ProtectedFilesystemTools(path_security=security, gateway_url="http://test")
        target_a = tmp_path / "action_a.txt"
        target_b = tmp_path / "action_b.txt"

        call_log: list[str] = []

        def freeze_during_action(path: str, payload: dict[str, Any]) -> dict[str, Any]:
            normalized = path.rstrip("/") or "/"
            if normalized == "/api/v1/actions":
                return {"action_id": "act-concurrent", "status": "pending"}
            if normalized.endswith("/evaluate"):
                return {"action_id": "act-concurrent", "status": "permitted"}
            if normalized == "/api/v1/intent/verify":
                return {"ephemeral_token": "token-concurrent"}
            if normalized == "/api/v1/intent/execute":
                return {"status": "executed"}
            if normalized == "/api/v1/intent/authorize-mutation":
                call_log.append("authorize-mutation")
                if len(call_log) > 1:
                    raise ProtectedFilesystemError("Session is frozen.")
                return {"status": "mutation_authorized"}
            return {}

        with patch.object(tools, "_post_json", side_effect=freeze_during_action), \
             patch.object(tools, "_patch_json", return_value={"status": "executed"}):
            tools.write_file(
                path=target_a,
                content="a",
                agent_id="agent-concurrent",
                session_id="ses-concurrent",
                correlation_id="corr-a",
            )
            assert target_a.exists()

            with pytest.raises(ProtectedFilesystemError, match="Session is frozen"):
                tools.write_file(
                    path=target_b,
                    content="b",
                    agent_id="agent-concurrent",
                    session_id="ses-concurrent",
                    correlation_id="corr-b",
                )
            assert not target_b.exists()
