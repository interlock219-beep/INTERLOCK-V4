"""Property-based (seeded, dependency-free) containment tests for path security.

Phase 5: 'property-based and state-machine tests where useful'. `hypothesis` is
not installed and adding a new dependency requires approval, so these use the
campaign's established deterministic seeded-RNG pattern instead.

Core safety property (tested over hundreds of generated inputs):
    For ANY generated path — relative, absolute, traversal-heavy, UNC-like,
    drive-changing, unicode, deep-nesting — `WorkspacePathSecurity.validate`
    either RAISES PathSecurityError or returns a resolved path STRICTLY INSIDE
    the workspace. It must never return an outside path.

A second property covers protected write/delete tools: a refused path leaves
the outside sentinel byte-identical.
"""

from __future__ import annotations

import random
from pathlib import Path, PureWindowsPath

import pytest

from sdk.workspace_protection.path_security import PathSecurityError, WorkspacePathSecurity

SEED = 0x5EC0A11
N_PATHS = 500


def _generate_paths(rng: random.Random, workspace: Path, outside: Path) -> list[str]:
    """Adversarial path corpus: every family that has ever escaped containment."""
    names = [
        "file.txt", "nested/ok.txt", "a/b/c/d.txt", "../x.txt", "..\\x.txt",
        "....//x.txt", "con.txt", "nul", "é/文件.txt", "space dir/f.txt",
        "trailing.", "x" * 200 + ".txt", ".hidden", "a" * 30 + "/b" * 30 + ".txt",
    ]
    paths: list[str] = []
    for _ in range(N_PATHS):
        strategy = rng.randrange(6)
        if strategy == 0:  # pure relative, random depth of traversal prefix
            depth = rng.randrange(0, 6)
        elif strategy == 1:  # absolute inside workspace
            paths.append(str(workspace / rng.choice(names)))
            continue
        elif strategy == 2:  # absolute outside (victim tree)
            paths.append(str(outside / rng.choice(names)))
            continue
        elif strategy == 3:  # drive-relative / drive-change (Windows-specific)
            drive = rng.choice(["C", "D", "Z"]) + ":"
            paths.append(drive + rng.choice(["\\x.txt", "x.txt", "\\"]))
            continue
        elif strategy == 4:  # UNC-like
            paths.append("\\\\server\\share\\" + rng.choice(names))
            continue
        else:  # joined traversal mix
            parts = [rng.choice(["..", ".", "seg", "seg2", ""]) for _ in range(rng.randrange(1, 8))]
            paths.append("/".join(p for p in parts if p) or ".")
            continue
        if strategy == 0:
            prefix = "/".join([".."] * depth)
            paths.append((prefix + "/" if prefix else "") + rng.choice(names))
    return paths


@pytest.fixture()
def trees(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "ws"
    outside = tmp_path / "outside"
    (workspace / "nested").mkdir(parents=True)
    outside.mkdir()
    (outside / "victim.txt").write_text("VICTIM", encoding="utf-8")
    return workspace, outside


class TestContainmentProperty:
    def test_validate_never_returns_outside_path(self, trees: tuple[Path, Path]) -> None:
        workspace, outside = trees
        rng = random.Random(SEED)  # noqa: S311 - deterministic seeded test corpus, not crypto
        security = WorkspacePathSecurity(workspace)
        accepted = 0
        refused = 0
        for raw in _generate_paths(rng, workspace, outside):
            try:
                resolved = security.validate(raw)
            except PathSecurityError:
                refused += 1
                continue
            accepted += 1
            # THE property: anything accepted is strictly inside the workspace.
            resolved.relative_to(workspace.resolve())
        # Sanity: the corpus must exercise both branches (no trivial all-refuse).
        assert accepted > 0, "property test degenerated: every path refused"
        assert refused > 0, "property test degenerated: nothing refused"

    def test_refused_write_leaves_victim_untouched(self, trees: tuple[Path, Path]) -> None:
        """Second property: refusal ⇒ zero side effects on outside sentinels."""
        from sdk.workspace_protection.protected_tools import ProtectedFilesystemTools

        workspace, outside = trees
        rng = random.Random(SEED ^ 0xFF)  # noqa: S311 - deterministic seeded test corpus
        tools = ProtectedFilesystemTools(
            path_security=WorkspacePathSecurity(workspace), gateway_url="http://test"
        )
        victim = outside / "victim.txt"
        before = victim.read_bytes()
        escapes = 0
        for raw in _generate_paths(rng, workspace, outside):
            resolved = Path(raw)
            is_outside = not _is_inside(resolved, workspace)
            if not is_outside:
                continue
            escapes += 1
            # Path validation runs BEFORE any gateway call, so outside paths
            # raise PathSecurityError without network I/O (no mocks needed).
            with pytest.raises(PathSecurityError):
                tools.write_file(
                    path=raw,
                    content="attacker content",
                    agent_id="agent-1",
                    session_id="ses-1",
                    correlation_id="corr-1",
                    binary=False,
                )
            with pytest.raises(PathSecurityError):
                tools.delete_file(
                    path=raw,
                    agent_id="agent-1",
                    session_id="ses-1",
                    correlation_id="corr-1",
                )
        assert escapes > 0
        assert victim.read_bytes() == before, "victim modified by a refused operation"


def _is_inside(candidate: Path, workspace: Path) -> bool:
    # Mirror the R1 semantics: relative inputs are workspace-relative.
    if not candidate.is_absolute():
        candidate = workspace / candidate
    try:
        candidate.resolve().relative_to(workspace.resolve())
        return True
    except (ValueError, OSError):
        return False


class TestWindowsSpecificProperties:
    def test_drive_change_always_refused_or_inside(self, trees: tuple[Path, Path]) -> None:
        workspace, _ = trees
        security = WorkspacePathSecurity(workspace)
        for drive in ["C", "D", "E", "Z"]:
            for tail in ["\\Windows\\System32\\config", "\\victim.txt", "\\"]:
                raw = drive + tail
                try:
                    resolved = security.validate(raw)
                except PathSecurityError:
                    continue
                # If accepted at all, it must be inside the workspace.
                resolved.relative_to(workspace.resolve())

    def test_unc_always_refused(self, trees: tuple[Path, Path]) -> None:
        workspace, _ = trees
        security = WorkspacePathSecurity(workspace)
        for raw in ["\\\\srv\\share\\f.txt", "\\\\?\\C:\\f.txt", "\\\\1.2.3.4\\x"]:
            with pytest.raises(PathSecurityError):
                security.validate(raw)

    def test_pure_windows_path_construction_not_confused(self, trees: tuple[Path, Path]) -> None:
        """Guard the fix itself: workspace-anchoring uses PureWindowsPath join
        semantics; ensure a mixed separator input still lands inside or refuses."""
        workspace, _ = trees
        security = WorkspacePathSecurity(workspace)
        mixed = str(PureWindowsPath("nested") / "ok.txt")
        try:
            resolved = security.validate(mixed)
        except PathSecurityError:
            return
        resolved.relative_to(workspace.resolve())
