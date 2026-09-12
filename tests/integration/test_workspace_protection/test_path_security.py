"""Tests for workspace path security."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from sdk.workspace_protection.path_security import PathSecurityError, WorkspacePathSecurity


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
