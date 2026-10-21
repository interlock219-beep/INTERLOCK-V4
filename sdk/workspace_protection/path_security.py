"""Workspace path security for Interlock-protected filesystem operations.

Ensures all filesystem operations remain within the configured workspace
directory. Uses robust path normalization and containment checks.
"""

from __future__ import annotations

from pathlib import Path


class PathSecurityError(Exception):
    """Raised when a path fails security validation."""


def is_unc_path(raw: str | Path) -> bool:
    """True for a UNC / network path in EITHER slash form.

    ``Path("//server/share")`` keeps its forward slashes, so a check for a
    leading ``\\\\`` alone misses the forward-slash form. The drive of a
    resolved UNC path is the reliable signal, so both forms are refused.
    """
    text = str(raw)
    if text.startswith("\\\\") or text.startswith("//"):
        return True
    return Path(raw).drive.startswith("\\\\")


class WorkspacePathSecurity:
    """Validates that all paths are within the allowed workspace.

    Rejects:
    - parent traversal (``..``)
    - symlink escapes
    - UNC paths (``\\\\``)
    - arbitrary absolute paths outside the workspace
    - drive changes

    Uses :py:meth:`Path.resolve` for normalization so simple string-prefix
    checks are not sufficient.
    """

    def __init__(self, workspace_path: str | Path) -> None:
        self._workspace_path = Path(workspace_path).resolve()
        if not self._workspace_path.exists():
            raise PathSecurityError(
                f"Workspace path does not exist: {self._workspace_path}"
            )
        if not self._workspace_path.is_dir():
            raise PathSecurityError(
                f"Workspace path is not a directory: {self._workspace_path}"
            )

    def validate(self, target_path: str | Path) -> Path:
        """Validate that ``target_path`` is within the workspace.

        Args:
            target_path: The path to validate.

        Returns:
            The resolved absolute path.

        Raises:
            PathSecurityError: If the path is outside the workspace or invalid.
        """
        target = Path(target_path)

        if not target_path or str(target_path).strip() == "":
            raise PathSecurityError("Empty path is not allowed")

        target_str = str(target_path)
        if is_unc_path(target_str):
            raise PathSecurityError(f"UNC paths are not allowed: {target_str}")

        if not target.is_absolute():
            # Relative inputs are workspace-relative. Anchoring them at the
            # workspace root (instead of the process CWD, which is arbitrary
            # for a library) can only convert false-rejects into correct
            # accepts: the post-resolve containment check below still enforces
            # the boundary for every path, relative or absolute.
            target = self._workspace_path / target

        try:
            resolved = target.resolve()
        except (OSError, RuntimeError) as exc:
            raise PathSecurityError(
                f"Cannot resolve path: {target_path} ({exc})"
            ) from exc

        try:
            resolved.relative_to(self._workspace_path)
        except ValueError as exc:
            raise PathSecurityError(
                f"Path is outside workspace: {target_path} (resolved: {resolved})"
            ) from exc

        if not resolved.exists():
            parent = resolved.parent
            try:
                parent.relative_to(self._workspace_path)
            except ValueError as exc:
                raise PathSecurityError(
                    f"Parent path is outside workspace: {parent} (resolved: {parent.resolve()})"
                ) from exc

        return resolved

    @property
    def workspace_path(self) -> Path:
        """The configured workspace root."""
        return self._workspace_path
