"""Experimental Interlock workspace protection integration.

This module provides Interlock-protected filesystem tools for coding-agent
workflows. Every filesystem mutation is authorized through Interlock before
touching the filesystem.

Usage::

    from sdk.workspace_protection import (
        WorkspacePathSecurity,
        ProtectedFilesystemTools,
        WorkspaceExperiment,
    )

WARNING: This integration is experimental. Do not use in production without
thorough security review.
"""

from sdk.workspace_protection.experiment import WorkspaceExperiment
from sdk.workspace_protection.path_security import (
    PathSecurityError,
    WorkspacePathSecurity,
)
from sdk.workspace_protection.protected_tools import (
    ProtectedFilesystemError,
    ProtectedFilesystemTools,
)

__all__ = [
    "PathSecurityError",
    "ProtectedFilesystemError",
    "ProtectedFilesystemTools",
    "WorkspaceExperiment",
    "WorkspacePathSecurity",
]
