"""Tests for workspace path security."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from sdk.workspace_protection.path_security import (
    PathSecurityError,
    WorkspacePathSecurity,
    is_unc_path,
)


class TestWorkspacePathSecurity:
    def test_valid_path_within_workspace(self, tmp_path: Path) -> None:
        security = WorkspacePathSecurity(tmp_path)
        target = tmp_path / "subdir" / "file.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("hello", encoding="utf-8")
        resolved = security.validate(target)
        assert resolved.is_absolute()
        assert resolved.exists()

    def test_path_with_parent_traversal_rejected(self, tmp_path: Path) -> None:
        security = WorkspacePathSecurity(tmp_path)
        target = tmp_path / ".." / "outside.txt"
        with pytest.raises(PathSecurityError, match="outside workspace"):
            security.validate(target)

    def test_absolute_path_outside_workspace_rejected(self, tmp_path: Path) -> None:
        security = WorkspacePathSecurity(tmp_path)
        with pytest.raises(PathSecurityError, match="outside workspace"):
            security.validate("/etc/passwd")

    def test_unc_path_rejected(self, tmp_path: Path) -> None:
        security = WorkspacePathSecurity(tmp_path)
        with pytest.raises(PathSecurityError, match="UNC paths are not allowed"):
            security.validate(r"\\server\share\file.txt")

    def test_unc_path_rejected_in_forward_slash_form(self, tmp_path: Path) -> None:
        """``Path("//server/share")`` keeps its forward slashes.

        A check for a leading backslash alone missed this form and let a
        network path through, so both slash forms are refused.
        """
        security = WorkspacePathSecurity(tmp_path)
        with pytest.raises(PathSecurityError, match="UNC paths are not allowed"):
            security.validate("//server/share/file.txt")
        with pytest.raises(PathSecurityError, match="UNC paths are not allowed"):
            security.validate("//server/share")

    def test_unc_detection_helper_handles_both_forms(self) -> None:
        assert is_unc_path(r"\\server\share")
        assert is_unc_path("//server/share")
        assert is_unc_path("\\\\server\\share\\file.txt")
        assert not is_unc_path("C:/Users/someone/project")
        assert not is_unc_path("/home/user/project")

    def test_empty_path_rejected(self, tmp_path: Path) -> None:
        security = WorkspacePathSecurity(tmp_path)
        with pytest.raises(PathSecurityError, match="Empty path"):
            security.validate("")

    def test_nonexistent_parent_within_workspace_allowed(self, tmp_path: Path) -> None:
        """Creating files in new subdirectories within the workspace is allowed."""
        security = WorkspacePathSecurity(tmp_path)
        target = tmp_path / "new_subdir" / "deep" / "file.txt"
        resolved = security.validate(target)
        assert resolved.is_absolute()
        assert resolved.parent == tmp_path / "new_subdir" / "deep"

    def test_relative_path_inside_workspace_accepted_from_foreign_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Relative inputs are workspace-relative, not process-CWD-relative.

        Regression: a relative path pointing inside the workspace was rejected
        with `PathSecurityError` whenever the process CWD differed from the
        workspace root (553 unexpected records across both 100k campaign legs,
        all `ws_inside_ok`). Anchoring at the workspace root can only convert
        false-rejects into correct accepts; the post-resolve containment check
        still enforces the boundary.
        """
        workspace = tmp_path / "ws"
        (workspace / "nested").mkdir(parents=True)
        (workspace / "nested" / "ok.txt").write_text("ok", encoding="utf-8")
        foreign_cwd = tmp_path / "elsewhere"
        foreign_cwd.mkdir()
        monkeypatch.chdir(foreign_cwd)

        security = WorkspacePathSecurity(workspace)
        resolved = security.validate("nested/ok.txt")
        assert resolved == (workspace / "nested" / "ok.txt").resolve()

    def test_relative_parent_traversal_still_rejected_from_foreign_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Workspace-anchoring must not weaken the containment boundary."""
        workspace = tmp_path / "ws"
        workspace.mkdir()
        foreign_cwd = tmp_path / "elsewhere"
        foreign_cwd.mkdir()
        monkeypatch.chdir(foreign_cwd)

        security = WorkspacePathSecurity(workspace)
        with pytest.raises(PathSecurityError, match="outside workspace"):
            security.validate("../escape.txt")

    def test_absolute_path_outside_workspace_rejected_from_foreign_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Absolute-path semantics are unchanged by workspace-anchoring."""
        workspace = tmp_path / "ws"
        workspace.mkdir()
        victim = tmp_path / "victim.txt"
        victim.write_text("untouched", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        security = WorkspacePathSecurity(workspace)
        with pytest.raises(PathSecurityError, match="outside workspace"):
            security.validate(str(victim))

    @pytest.mark.skipif(os.name == "nt", reason="Symlinks require admin privileges on Windows")
    def test_symlink_escape_rejected(self, tmp_path: Path) -> None:
        security = WorkspacePathSecurity(tmp_path)
        with tempfile.NamedTemporaryFile(delete=False) as outside_file:
            outside_file.write(b"secret")
            outside_file_path = outside_file.name
        try:
            symlink = tmp_path / "escape"
            symlink.symlink_to(outside_file_path)
            with pytest.raises(PathSecurityError):
                security.validate(symlink)
        finally:
            os.unlink(outside_file_path)

    def test_workspace_path_does_not_exist(self) -> None:
        with pytest.raises(PathSecurityError, match="does not exist"):
            WorkspacePathSecurity("/nonexistent/path/12345")

    def test_workspace_path_not_directory(self, tmp_path: Path) -> None:
        file_path = tmp_path / "file.txt"
        file_path.write_text("hello", encoding="utf-8")
        with pytest.raises(PathSecurityError, match="not a directory"):
            WorkspacePathSecurity(file_path)
