"""RE-02: the Terminal Runner must never replace a usable baseline silently.

Covers:
- the engine's sealed document is persisted verbatim (and only that document)
- an ordinary capture refuses to replace an existing baseline; the original
  bytes survive untouched
- a capture/serialization failure leaves the previous baseline intact
- an interrupted persistence never leaves a corrupt replacement behind and
  cleans up its own temporary files
- two concurrent captures cannot silently overwrite one another
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BRIDGE_PATH = REPO_ROOT / "extensions" / "vscode" / "python" / "interlock_bridge.py"
CLI_PATH = REPO_ROOT / "interlock_cli.py"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bridge = _load("interlock_bridge_under_test_cli", BRIDGE_PATH)
cli = _load("interlock_cli_under_test", CLI_PATH)


def _snapshot(content: bytes = b"ORIGINAL = 1\r\n") -> dict[str, Any]:
    return {
        "captured_at": "2026-10-20T10:00:00+00:00",
        "resource": "app.py",
        "exists": True,
        "type": "file",
        "size": len(content),
        "hash": hashlib.sha256(content).hexdigest(),
        "content": content.decode("utf-8"),
        "content_b64": base64.b64encode(content).decode("ascii"),
        "binary": False,
        "encoding": "utf-8",
        "raw_bytes_length": len(content),
        "truncated": False,
    }


def _capture_result(content: bytes = b"ORIGINAL = 1\r\n") -> dict[str, Any]:
    """A capture result exactly as the engine returns it."""
    document = bridge.build_baseline_document(
        "C:/ws", "app.py", "2026-10-20T10:00:00+00:00", _snapshot(content)
    )
    return {
        "workspace": "C:/ws",
        "resource": "app.py",
        "captured_at": "2026-10-20T10:00:00+00:00",
        "hash": document["snapshot"]["hash"],
        "size": document["snapshot"]["size"],
        "snapshot": document["snapshot"],
        "baseline_document": document,
    }


def _temp_files_in(directory: Path) -> list[Path]:
    return [path for path in directory.iterdir() if path.name.endswith(".tmp")]


# --------------------------------------------------------------------------- #
# Normal persistence
# --------------------------------------------------------------------------- #


def test_persist_writes_the_engines_sealed_document(tmp_path: Path) -> None:
    target = tmp_path / "baseline.json"
    result = _capture_result()
    written = cli._persist_baseline(result, str(target), bridge)
    assert written == target
    document = json.loads(target.read_text(encoding="utf-8"))
    assert document == result["baseline_document"]
    assert document["format"] == bridge.BASELINE_FORMAT
    assert document["baseline_hash"] == result["baseline_document"]["baseline_hash"]
    # The persisted document is usable by the engine.
    assert bridge.verify_baseline_document(document) == document


def test_persist_leaves_no_temporary_files(tmp_path: Path) -> None:
    target = tmp_path / "baseline.json"
    cli._persist_baseline(_capture_result(), str(target), bridge)
    assert _temp_files_in(tmp_path) == []


# --------------------------------------------------------------------------- #
# RE-02: an existing baseline is never replaced
# --------------------------------------------------------------------------- #


def test_persist_refuses_to_replace_an_existing_baseline(tmp_path: Path) -> None:
    target = tmp_path / "baseline.json"
    first = _capture_result(b"ORIGINAL = 1\r\n")
    cli._persist_baseline(first, str(target), bridge)
    original_bytes = target.read_bytes()

    # A second capture (the file changed, so the snapshot differs) must not
    # replace the last known-good before-state.
    second = _capture_result(b"CHANGED = 2\r\n")
    with pytest.raises(cli.BaselineExistsError):
        cli._persist_baseline(second, str(target), bridge)

    assert target.read_bytes() == original_bytes
    document = json.loads(target.read_text(encoding="utf-8"))
    assert document["snapshot"]["hash"] == first["baseline_document"]["snapshot"]["hash"]


def test_refusal_does_not_delete_the_existing_baseline(tmp_path: Path) -> None:
    target = tmp_path / "baseline.json"
    cli._persist_baseline(_capture_result(), str(target), bridge)
    original_bytes = target.read_bytes()
    with pytest.raises(cli.BaselineExistsError):
        cli._persist_baseline(_capture_result(b"OTHER\r\n"), str(target), bridge)
    assert target.is_file()
    assert target.read_bytes() == original_bytes
    assert _temp_files_in(tmp_path) == []


# --------------------------------------------------------------------------- #
# Failures never destroy the previous baseline
# --------------------------------------------------------------------------- #


def test_capture_without_a_sealed_document_writes_nothing(tmp_path: Path) -> None:
    target = tmp_path / "baseline.json"
    result = _capture_result()
    del result["baseline_document"]
    with pytest.raises(RuntimeError):
        cli._persist_baseline(result, str(target), bridge)
    assert not target.exists()
    assert _temp_files_in(tmp_path) == []


def test_an_unsealed_document_is_never_persisted(tmp_path: Path) -> None:
    """Even if a result carried a hand-made document, an unverifiable one is
    refused instead of being written to disk."""
    target = tmp_path / "baseline.json"
    result = _capture_result()
    result["baseline_document"] = {
        "format": bridge.LEGACY_BASELINE_FORMAT,
        "workspace": "C:/ws",
        "resource": "app.py",
        "captured_at": "2026-10-20T10:00:00+00:00",
        "snapshot": _snapshot(),
    }
    with pytest.raises(bridge.BridgeError):
        cli._persist_baseline(result, str(target), bridge)
    assert not target.exists()
    assert _temp_files_in(tmp_path) == []


def test_failed_serialization_leaves_the_prior_baseline_intact(tmp_path: Path) -> None:
    """A document that cannot be serialized must abort before anything is
    written: the previous baseline stays exactly as it was."""
    target = tmp_path / "baseline.json"
    cli._persist_baseline(_capture_result(), str(target), bridge)
    original_bytes = target.read_bytes()

    class Unserialisable:
        def __str__(self) -> str:
            raise RuntimeError("boom")

    result = _capture_result()
    result["baseline_document"] = dict(result["baseline_document"])
    result["baseline_document"]["snapshot"] = dict(result["baseline_document"]["snapshot"])
    result["baseline_document"]["snapshot"]["metadata"] = Unserialisable()
    with pytest.raises(RuntimeError):
        cli._persist_baseline(result, str(target), bridge)

    assert target.read_bytes() == original_bytes
    assert _temp_files_in(tmp_path) == []


def test_a_failed_write_leaves_the_prior_baseline_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure while creating the temporary file must not touch the target."""
    target = tmp_path / "baseline.json"
    cli._persist_baseline(_capture_result(), str(target), bridge)
    original_bytes = target.read_bytes()

    def _failing_open(*args: Any, **kwargs: Any) -> int:
        raise OSError("the disk is full")

    monkeypatch.setattr(cli.os, "open", _failing_open)
    with pytest.raises(OSError):
        cli._persist_baseline(_capture_result(b"CHANGED\r\n"), str(target), bridge)

    assert target.read_bytes() == original_bytes
    assert _temp_files_in(tmp_path) == []


def test_interrupted_persistence_leaves_no_corrupt_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure in the middle of publishing must not leave a half-written
    baseline behind, and must not destroy an existing one."""
    target = tmp_path / "baseline.json"

    # Force the fallback path (no hard links) and then fail the publish.
    def _no_links(*args: Any, **kwargs: Any) -> None:
        raise OSError("hard links are not supported here")

    def _failing_replace(*args: Any, **kwargs: Any) -> None:
        raise OSError("disk went away")

    monkeypatch.setattr(cli.os, "link", _no_links)
    monkeypatch.setattr(cli.os, "replace", _failing_replace)
    with pytest.raises(OSError):
        cli._persist_baseline(_capture_result(), str(target), bridge)

    assert not target.exists()
    assert _temp_files_in(tmp_path) == []


def test_interrupted_persistence_keeps_an_existing_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "baseline.json"
    cli._persist_baseline(_capture_result(), str(target), bridge)
    original_bytes = target.read_bytes()

    def _no_links(*args: Any, **kwargs: Any) -> None:
        raise OSError("hard links are not supported here")

    def _failing_replace(*args: Any, **kwargs: Any) -> None:
        raise OSError("disk went away")

    monkeypatch.setattr(cli.os, "link", _no_links)
    monkeypatch.setattr(cli.os, "replace", _failing_replace)
    # The existing baseline is refused before anything is published, so the
    # publish failure is never even reached.
    with pytest.raises(cli.BaselineExistsError):
        cli._persist_baseline(_capture_result(b"CHANGED\r\n"), str(target), bridge)

    assert target.read_bytes() == original_bytes
    assert _temp_files_in(tmp_path) == []


# --------------------------------------------------------------------------- #
# Concurrency
# --------------------------------------------------------------------------- #


def test_concurrent_captures_cannot_overwrite_one_another(tmp_path: Path) -> None:
    """Two captures racing for the same target: exactly one wins, the other is
    told the baseline exists. Neither can silently replace the other."""
    target = tmp_path / "baseline.json"
    results = _capture_result(b"ORIGINAL = 1\r\n"), _capture_result(b"CHANGED = 2\r\n")
    outcomes: list[str] = []
    barrier = threading.Barrier(2)
    lock = threading.Lock()

    def _worker(index: int) -> None:
        barrier.wait()
        try:
            cli._persist_baseline(results[index], str(target), bridge)
        except cli.BaselineExistsError:
            with lock:
                outcomes.append("exists")
        except Exception:  # pragma: no cover - unexpected failure
            with lock:
                outcomes.append("error")
        else:
            with lock:
                outcomes.append("written")

    threads = [threading.Thread(target=_worker, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(outcomes) == ["exists", "written"]
    document = json.loads(target.read_text(encoding="utf-8"))
    # The stored baseline is one of the two captures, intact and verifiable -
    # never a mixture of both.
    assert document["snapshot"]["hash"] in {
        results[0]["baseline_document"]["snapshot"]["hash"],
        results[1]["baseline_document"]["snapshot"]["hash"],
    }
    assert bridge.verify_baseline_document(document) == document
    assert _temp_files_in(tmp_path) == []


def test_concurrent_captures_to_different_targets_both_succeed(tmp_path: Path) -> None:
    """Different resources are different baselines: no interference."""
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    cli._persist_baseline(_capture_result(), str(first), bridge)
    cli._persist_baseline(_capture_result(b"OTHER\r\n"), str(second), bridge)
    assert first.is_file()
    assert second.is_file()
    assert first.read_bytes() != second.read_bytes()


# --------------------------------------------------------------------------- #
# The publish primitive itself
# --------------------------------------------------------------------------- #


def test_publish_is_atomic_and_exclusive(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "baseline.json"
    cli._publish_new_file(target, "payload-one")
    assert target.read_text(encoding="utf-8") == "payload-one"
    with pytest.raises(cli.BaselineExistsError):
        cli._publish_new_file(target, "payload-two")
    assert target.read_text(encoding="utf-8") == "payload-one"


def test_publish_creates_missing_directories(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "baseline.json"
    cli._publish_new_file(target, "payload")
    assert target.read_text(encoding="utf-8") == "payload"
    assert os.path.isdir(target.parent)
