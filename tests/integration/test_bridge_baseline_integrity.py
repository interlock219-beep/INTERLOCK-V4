"""RE-01/RE-02 end to end through the real bridge process.

Proves the two properties that matter for data preservation:

1. A valid, sealed baseline still supports the whole flow (capture -> preview
   -> recover -> independent byte-exact verification).
2. A tampered (or legacy, unsealed) baseline is refused BEFORE any write, so
   it can never be restored into the workspace and never be reported as
   verified.

Everything happens in a temporary workspace; no project file is touched.
"""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BRIDGE_PATH = REPO_ROOT / "extensions" / "vscode" / "python" / "interlock_bridge.py"

ORIGINAL = b"ORIGINAL = 1\r\n"
DAMAGED = b"DAMAGED = 1\r\n"


def _bridge(command: str, *args: str) -> tuple[int, dict[str, Any]]:
    # Fixed interpreter + fixed script path, list-form arguments, no shell.
    proc = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(BRIDGE_PATH),
            command,
            "--engine-root",
            str(REPO_ROOT),
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:  # pragma: no cover - a broken bridge
        payload = {"ok": False, "error": {"kind": "no_json", "message": proc.stdout[-400:]}}
    return proc.returncode, payload


def _make_workspace(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "app.py"
    target.write_bytes(ORIGINAL)
    return workspace, target


def _capture(workspace: Path, resource: str = "app.py") -> dict[str, Any]:
    code, payload = _bridge(
        "capture-baseline", "--workspace", str(workspace), "--resource", resource
    )
    assert code == 0, payload
    result = payload["result"]
    document = result["baseline_document"]
    assert document["format"] == "interlock-baseline-v2"
    assert document["baseline_hash"]
    return document


def _write(path: Path, document: Any) -> Path:
    path.write_text(json.dumps(document, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def test_valid_baseline_recovers_byte_exactly(tmp_path: Path) -> None:
    workspace, target = _make_workspace(tmp_path)
    document = _capture(workspace)
    baseline = _write(tmp_path / "baseline.json", document)

    target.write_bytes(DAMAGED)

    code, payload = _bridge(
        "plan",
        "--workspace",
        str(workspace),
        "--resource",
        "app.py",
        "--baseline-file",
        str(baseline),
    )
    assert code == 0, payload
    assert payload["ok"] is True
    evidence = Path(str(baseline) + ".evidence.json")
    assert evidence.is_file()

    code, payload = _bridge(
        "execute",
        "--workspace",
        str(workspace),
        "--resource",
        "app.py",
        "--baseline-file",
        str(baseline),
        "--evidence-file",
        str(evidence),
        "--approved-by",
        "auditor",
    )
    assert code == 0, payload
    assert payload["ok"] is True
    assert payload["result"]["engine_verification"]["verified"] is True
    assert target.read_bytes() == ORIGINAL

    code, payload = _bridge(
        "verify",
        "--workspace",
        str(workspace),
        "--resource",
        "app.py",
        "--baseline-file",
        str(baseline),
    )
    assert code == 0, payload
    assert payload["result"]["verified"] is True


def test_tampered_baseline_is_refused_and_never_restored(tmp_path: Path) -> None:
    workspace, target = _make_workspace(tmp_path)
    document = _capture(workspace)

    # A coherent tamper: the content AND its hash are replaced with attacker
    # chosen bytes of exactly the same length, so only an integrity seal can
    # detect it.
    evil = b"TAMPERED = 2\r\n"
    assert len(evil) == len(ORIGINAL)
    document["snapshot"]["content_b64"] = base64.b64encode(evil).decode("ascii")
    document["snapshot"]["hash"] = hashlib.sha256(evil).hexdigest()
    baseline = _write(tmp_path / "baseline.json", document)

    target.write_bytes(DAMAGED)

    # 1) Planning refuses: no plan is built from an unverified baseline.
    code, payload = _bridge(
        "plan",
        "--workspace",
        str(workspace),
        "--resource",
        "app.py",
        "--baseline-file",
        str(baseline),
    )
    assert code == 5, payload
    assert payload["ok"] is False
    assert payload["error"]["kind"] == "baseline_integrity_failed"
    assert not Path(str(baseline) + ".evidence.json").exists()

    # 2) Execution refuses: nothing is written into the workspace.
    code, payload = _bridge(
        "execute",
        "--workspace",
        str(workspace),
        "--resource",
        "app.py",
        "--baseline-file",
        str(baseline),
        "--evidence-file",
        str(baseline),
        "--approved-by",
        "auditor",
    )
    assert code == 5, payload
    assert payload["ok"] is False
    assert payload["error"]["kind"] == "baseline_integrity_failed"
    assert target.read_bytes() == DAMAGED, "the file must not be touched at all"

    # 3) Verification refuses and never reports success.
    code, payload = _bridge(
        "verify",
        "--workspace",
        str(workspace),
        "--resource",
        "app.py",
        "--baseline-file",
        str(baseline),
    )
    assert code == 5, payload
    assert payload["ok"] is False
    assert payload["error"]["kind"] == "baseline_integrity_failed"


def test_legacy_unsealed_baseline_is_refused(tmp_path: Path) -> None:
    workspace, target = _make_workspace(tmp_path)
    document = _capture(workspace)
    legacy = {
        "format": "interlock-baseline-v1",
        "workspace": str(workspace),
        "resource": "app.py",
        "captured_at": document["captured_at"],
        "snapshot": document["snapshot"],
    }
    baseline = _write(tmp_path / "legacy.json", legacy)
    target.write_bytes(DAMAGED)

    code, payload = _bridge(
        "plan",
        "--workspace",
        str(workspace),
        "--resource",
        "app.py",
        "--baseline-file",
        str(baseline),
    )
    assert code == 7, payload
    assert payload["ok"] is False
    assert payload["error"]["kind"] == "baseline_unsealed"
    assert target.read_bytes() == DAMAGED


def test_a_truncated_baseline_is_refused(tmp_path: Path) -> None:
    """A baseline captured only partially can never restore the file, so it
    must be refused before a plan is built."""
    workspace, target = _make_workspace(tmp_path)
    document = _capture(workspace)
    snapshot = dict(document["snapshot"])
    prefix = base64.b64decode(snapshot["content_b64"])[:5]
    snapshot["content_b64"] = base64.b64encode(prefix).decode("ascii")
    snapshot["hash"] = hashlib.sha256(prefix).hexdigest()
    snapshot["raw_bytes_length"] = len(prefix)
    snapshot["truncated"] = True
    snapshot["byte_exact"] = False
    truncated = dict(document)
    truncated["snapshot"] = snapshot
    # Re-seal so the document is internally consistent: only the truncation
    # check can refuse it.
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "bridge_for_truncated_test",
        REPO_ROOT / "extensions" / "vscode" / "python" / "interlock_bridge.py",
    )
    assert spec is not None and spec.loader is not None
    bridge = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = bridge
    spec.loader.exec_module(bridge)
    truncated = bridge.seal_baseline_document(truncated)
    baseline = _write(tmp_path / "truncated.json", truncated)
    target.write_bytes(DAMAGED)

    code, payload = _bridge(
        "plan",
        "--workspace",
        str(workspace),
        "--resource",
        "app.py",
        "--baseline-file",
        str(baseline),
    )
    assert code == 7, payload
    assert payload["ok"] is False
    assert payload["error"]["kind"] == "baseline_truncated"
    assert target.read_bytes() == DAMAGED


def test_a_baseline_of_another_workspace_is_refused(tmp_path: Path) -> None:
    workspace, target = _make_workspace(tmp_path)
    document = _capture(workspace)
    baseline = _write(tmp_path / "baseline.json", document)

    other = tmp_path / "other-ws"
    other.mkdir()
    other_target = other / "app.py"
    other_target.write_bytes(ORIGINAL)

    code, payload = _bridge(
        "plan",
        "--workspace",
        str(other),
        "--resource",
        "app.py",
        "--baseline-file",
        str(baseline),
    )
    assert code == 4, payload
    assert payload["ok"] is False
    assert payload["error"]["kind"] == "not_authorized"


@pytest.mark.parametrize("command", ["plan", "verify"])
def test_every_entry_point_refuses_a_tampered_baseline(
    tmp_path: Path, command: str
) -> None:
    """The integrity gate is not specific to one command."""
    workspace, target = _make_workspace(tmp_path)
    document = _capture(workspace)
    document["snapshot"]["content_b64"] = base64.b64encode(b"TAMPERED = 2\r\n").decode("ascii")
    baseline = _write(tmp_path / "baseline.json", document)

    code, payload = _bridge(
        command,
        "--workspace",
        str(workspace),
        "--resource",
        "app.py",
        "--baseline-file",
        str(baseline),
    )
    assert code == 5, payload
    assert payload["error"]["kind"] == "baseline_integrity_failed"
    assert target.read_bytes() == ORIGINAL
