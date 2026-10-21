"""Windows path-escape vectors and non-ASCII paths (TST-06, TST-07).

Two gaps the audit found in the coverage map:

- **TST-06** no test drives a Windows *junction* (a directory reparse point
  that does NOT need elevation, unlike a symlink) through the containment
  checks. A junction is the most realistic directory-escape vector on the
  platform Interlock declares as "tested - primary".
- **TST-07** no test drives a non-ASCII path through capture -> recover ->
  verify. Recovery is byte-exact, so a path that cannot be expressed must
  fail loudly rather than corrupt a file.

Everything happens in a temporary workspace.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from app.domain.entities.protected_action import ActionStatus, ProtectedAction, Reversibility
from app.infrastructure.recovery.filesystem_recovery_adapter import FilesystemRecoveryAdapter
from sdk.workspace_protection.path_security import PathSecurityError, WorkspacePathSecurity

windows_only = pytest.mark.skipif(os.name != "nt", reason="Windows path semantics")


def _make_junction(link: Path, target: Path) -> bool:
    """Create a directory junction (no elevation required on Windows)."""
    result = subprocess.run(  # noqa: S603 - fixed tool, fixed argument list
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],  # noqa: S607 - mklink is a cmd builtin
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return result.returncode == 0


@windows_only
class TestJunctionEscapeIsRefused:
    """A junction inside the workspace must not become an exit door."""

    def test_junction_out_of_the_workspace_is_refused(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("must not be reachable", encoding="utf-8")

        junction = workspace / "link"
        if not _make_junction(junction, outside):
            pytest.skip("junction creation unavailable in this environment")

        security = WorkspacePathSecurity(workspace)
        with pytest.raises(PathSecurityError):
            security.validate("link/secret.txt")

        adapter = FilesystemRecoveryAdapter(base_path=workspace)
        with pytest.raises(ValueError):
            adapter._resolve_file_path("link/secret.txt", workspace)

    def test_junction_to_a_sibling_inside_the_workspace_is_allowed(
        self, tmp_path: Path
    ) -> None:
        """The check is about ESCAPE, not about junctions themselves."""
        workspace = tmp_path / "ws"
        (workspace / "inner").mkdir(parents=True)
        (workspace / "inner" / "ok.txt").write_text("inside", encoding="utf-8")
        junction = workspace / "link"
        if not _make_junction(junction, workspace / "inner"):
            pytest.skip("junction creation unavailable in this environment")

        security = WorkspacePathSecurity(workspace)
        resolved = security.validate("link/ok.txt")
        assert resolved.name == "ok.txt"


class TestNonAsciiPaths:
    """A non-ASCII workspace and file name must recover byte-for-byte."""

    @pytest.mark.asyncio
    async def test_unicode_path_round_trips(self, tmp_path: Path) -> None:
        base = tmp_path / "wörk späce-日本"
        base.mkdir()
        target = base / "café-ünïcode.txt"
        original = "ORIGINAL = 'café'  # 日本語\n".encode()
        target.write_bytes(original)

        adapter = FilesystemRecoveryAdapter(base_path=base)
        action = ProtectedAction(
            action_id="act-unicode-1",
            tenant_id="test-tenant",
            agent_id="agent-test",
            actor_user_id=None,
            authority_grant_id=None,
            tool="filesystem",
            resource="file:café-ünïcode.txt",
            action_type="modify",
            risk_score=0.5,
            policy_version="v1",
            correlation_id="corr-1",
            parent_action_id=None,
            workflow_id=None,
            reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
            before_state_ref="state:before:1",
            after_state_ref="state:after:1",
            tool_arguments={"path": "file:café-ünïcode.txt"},
            status=ActionStatus.EXECUTED,
            decision_reason="test",
            evaluated_at=None,
            executed_at=None,
            created_at=None,
        )

        captured = await adapter.capture_recovery_evidence(action)
        before = captured.compensation_payload["before_snapshot"]
        assert before["hash"] == hashlib.sha256(original).hexdigest()

        # The agent damages the file; the plan is made against that state.
        target.write_bytes(b"DAMAGED = 1\n")
        evidence = await adapter.capture_recovery_evidence(action, before_snapshot=before)
        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is True
        assert target.read_bytes() == original
        verification = await adapter.verify(compensation)
        assert verification.verified is True
