"""Packaging completeness guard (SUPPLY-01).

The released artifact is assembled from paths that live OUTSIDE the Python
package: the Terminal Runner module, the shared engine command layer that the
CLI and the VS Code extension both drive, and the Alembic runtime.

The audit found that the extension, the CLI and the website are not tracked in
git at all, so a wheel built from a pristine checkout silently shipped with
NO console script, NO bridge and NO migration runtime - and the build still
reported success.

These tests make that class of gap loud instead of silent: every path the
packaging configuration references must exist in the tree that is being
packaged, and the console script must resolve to a real module.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"


@pytest.fixture(scope="module")
def pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _data_file_sources(pyproject: dict) -> list[str]:
    sources: list[str] = []
    for _target, patterns in (pyproject.get("tool", {}).get("setuptools", {})
                              .get("data-files", {})).items():
        sources.extend(patterns)
    return sources


def test_py_modules_exist(pyproject: dict) -> None:
    """Every top-level module the wheel declares must be present."""
    modules = pyproject.get("tool", {}).get("setuptools", {}).get("py-modules", [])
    assert modules, "the package should declare its top-level modules"
    missing = [name for name in modules if not (REPO_ROOT / f"{name}.py").is_file()]
    assert not missing, f"declared top-level modules are missing from the tree: {missing}"


def test_data_file_sources_exist(pyproject: dict) -> None:
    """Every file the wheel installs as data must exist in the tree."""
    missing: list[str] = []
    for pattern in _data_file_sources(pyproject):
        if "*" in pattern:
            if not list(REPO_ROOT.glob(pattern)):
                missing.append(pattern)
        elif not (REPO_ROOT / pattern).exists():
            missing.append(pattern)
    assert not missing, f"packaging data files are missing from the tree: {missing}"

def test_manifest_in_targets_exist() -> None:
    """MANIFEST.in must not reference paths that do not exist."""
    manifest = REPO_ROOT / "MANIFEST.in"
    if not manifest.is_file():
        pytest.skip("MANIFEST.in is not present")
    missing: list[str] = []
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("global-exclude"):
            continue
        if line.startswith(("include ", "graft ")):
            target = line.split(" ", 1)[1].strip()
            if "*" in target:
                if not list(REPO_ROOT.glob(target)):
                    missing.append(target)
            elif not (REPO_ROOT / target).exists():
                missing.append(target)
    assert not missing, f"MANIFEST.in references missing paths: {missing}"


def test_console_script_resolves_to_a_real_module(pyproject: dict) -> None:
    """``interlock = "interlock_cli:console_entry"`` must point at a callable."""
    scripts = pyproject.get("project", {}).get("scripts", {})
    assert scripts, "the package should declare its console script"
    for name, target in scripts.items():
        module_name, _, attribute = target.partition(":")
        module_path = REPO_ROOT / f"{module_name}.py"
        assert module_path.is_file(), (
            f"console script '{name}' targets a missing module: {module_name}"
        )
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        functions = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert attribute in functions, (
            f"console script '{name}' targets '{target}', but "
            f"'{attribute}' is not defined in {module_path.name}"
        )


def test_the_shared_engine_bridge_ships_with_the_package(pyproject: dict) -> None:
    """The CLI and the extension both drive ``interlock_bridge.py``.

    If that file is not part of the distribution, the installed CLI cannot
    find its engine and the extension cannot boot.
    """
    bridge = REPO_ROOT / "extensions" / "vscode" / "python" / "interlock_bridge.py"
    assert bridge.is_file(), "the shared engine command layer is missing from the tree"
    sources = _data_file_sources(pyproject)
    assert any("interlock_bridge.py" in source for source in sources), (
        "the shared engine command layer is not installed as package data"
    )
