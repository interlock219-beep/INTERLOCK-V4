"""RE-01: baseline integrity - sealing, verification and the legacy policy.

A baseline is the only record of the before-state a recovery restores, so it is
sealed by the engine and verified by the engine before it may be used to plan,
preview, recover or verify.

Covers:
- seal/verify round trip
- tamper detection (content, hash, workspace, resource, capture time)
- stale seal detection (a seal that belongs to a different document)
- missing / malformed / unsupported seals (explicit compatibility policy)
- legacy (unsealed) baselines are refused, never silently blessed
- the loader refuses an unverifiable baseline before any planning happens
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BRIDGE_PATH = REPO_ROOT / "extensions" / "vscode" / "python" / "interlock_bridge.py"


def _load_bridge() -> Any:
    spec = importlib.util.spec_from_file_location("interlock_bridge_under_test", BRIDGE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bridge = _load_bridge()


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


def _sealed(
    workspace: str = "C:/ws",
    resource: str = "app.py",
    content: bytes = b"ORIGINAL = 1\r\n",
) -> dict[str, Any]:
    return bridge.build_baseline_document(
        workspace, resource, "2026-10-20T10:00:00+00:00", _snapshot(content)
    )


def _kind(excinfo: pytest.ExceptionInfo[Any]) -> str:
    return getattr(excinfo.value, "kind", "")


# --------------------------------------------------------------------------- #
# Sealing
# --------------------------------------------------------------------------- #


def test_seal_produces_a_verifiable_document() -> None:
    document = _sealed()
    assert document["format"] == bridge.BASELINE_FORMAT
    assert document["baseline_hash_spec"] == bridge.BASELINE_HASH_SPEC
    assert bridge._is_sha256_hex(document["baseline_hash"])
    # The seal must not be self-referential: recomputing it reproduces it.
    assert bridge.compute_baseline_hash(document) == document["baseline_hash"]
    # ...and the verified document is returned unchanged.
    assert bridge.verify_baseline_document(document) == document


def test_seal_does_not_mutate_the_input_document() -> None:
    document = {
        "format": bridge.BASELINE_FORMAT,
        "workspace": "C:/ws",
        "resource": "app.py",
        "captured_at": "2026-10-20T10:00:00+00:00",
        "snapshot": _snapshot(),
    }
    before = json.dumps(document, sort_keys=True)
    sealed = bridge.seal_baseline_document(document)
    assert json.dumps(document, sort_keys=True) == before
    assert sealed is not document
    assert bridge.BASELINE_HASH_FIELD not in document


def test_recomputing_a_seal_from_loaded_content_is_not_a_proof() -> None:
    """A seal recomputed from tampered content must not verify against the
    stored seal: verification compares, it never re-stamps."""
    document = _sealed()
    tampered = dict(document)
    tampered["snapshot"] = dict(document["snapshot"])
    tampered["snapshot"]["content_b64"] = base64.b64encode(b"EVIL\r\n").decode("ascii")
    # The attacker recomputes a matching seal: the document is now internally
    # consistent, which is exactly the documented limit of an unsigned seal.
    assert bridge.compute_baseline_hash(tampered) != document["baseline_hash"]
    with pytest.raises(bridge.BridgeError) as excinfo:
        bridge.verify_baseline_document(tampered)
    assert _kind(excinfo) == "baseline_integrity_failed"


# --------------------------------------------------------------------------- #
# Tamper detection
# --------------------------------------------------------------------------- #


def test_tampered_content_is_rejected() -> None:
    document = _sealed()
    document["snapshot"] = dict(document["snapshot"])
    document["snapshot"]["content_b64"] = base64.b64encode(b"EVIL\r\n").decode("ascii")
    document["snapshot"]["hash"] = hashlib.sha256(b"EVIL\r\n").hexdigest()
    with pytest.raises(bridge.BridgeError) as excinfo:
        bridge.verify_baseline_document(document)
    assert _kind(excinfo) == "baseline_integrity_failed"
    assert excinfo.value.exit_code == bridge.EXIT_REFUSED


def test_tampered_workspace_is_rejected() -> None:
    """A valid snapshot must not be transplantable to another workspace."""
    document = _sealed()
    document["workspace"] = "C:/other-ws"
    with pytest.raises(bridge.BridgeError) as excinfo:
        bridge.verify_baseline_document(document)
    assert _kind(excinfo) == "baseline_integrity_failed"


def test_tampered_resource_is_rejected() -> None:
    document = _sealed()
    document["resource"] = "other.py"
    with pytest.raises(bridge.BridgeError) as excinfo:
        bridge.verify_baseline_document(document)
    assert _kind(excinfo) == "baseline_integrity_failed"


def test_tampered_capture_time_is_rejected() -> None:
    document = _sealed()
    document["captured_at"] = "2020-01-01T00:00:00+00:00"
    with pytest.raises(bridge.BridgeError) as excinfo:
        bridge.verify_baseline_document(document)
    assert _kind(excinfo) == "baseline_integrity_failed"


def test_stale_seal_is_rejected() -> None:
    """A seal belonging to a different document must not verify this one."""
    document = _sealed()
    stale = _sealed(content=b"OTHER = 2\r\n")
    document["baseline_hash"] = stale["baseline_hash"]
    with pytest.raises(bridge.BridgeError) as excinfo:
        bridge.verify_baseline_document(document)
    assert _kind(excinfo) == "baseline_integrity_failed"


def test_snapshot_content_must_match_its_own_hash() -> None:
    """Self-consistency: the stored bytes must hash to the recorded hash."""
    document = _sealed()
    document["snapshot"] = dict(document["snapshot"])
    document["snapshot"]["content_b64"] = base64.b64encode(b"EVIL\r\n").decode("ascii")
    # Re-seal so the document-level seal is valid again: only the internal
    # consistency check can catch this.
    document = bridge.seal_baseline_document(document)
    with pytest.raises(bridge.BridgeError) as excinfo:
        bridge.verify_baseline_document(document)
    assert _kind(excinfo) == "baseline_integrity_failed"


# --------------------------------------------------------------------------- #
# Compatibility policy
# --------------------------------------------------------------------------- #


def test_legacy_unsealed_baseline_is_refused_and_never_blessed() -> None:
    legacy = {
        "format": bridge.LEGACY_BASELINE_FORMAT,
        "workspace": "C:/ws",
        "resource": "app.py",
        "captured_at": "2026-10-20T10:00:00+00:00",
        "snapshot": _snapshot(),
    }
    with pytest.raises(bridge.BridgeError) as excinfo:
        bridge.verify_baseline_document(legacy)
    assert _kind(excinfo) == "baseline_unsealed"
    assert excinfo.value.exit_code == bridge.EXIT_PRECONDITION
    # The message must tell the user how to proceed.
    assert "Capture a new baseline" in (excinfo.value.hint or "")


def test_missing_seal_is_refused() -> None:
    document = _sealed()
    del document["baseline_hash"]
    with pytest.raises(bridge.BridgeError) as excinfo:
        bridge.verify_baseline_document(document)
    assert _kind(excinfo) == "baseline_unsealed"


def test_malformed_seal_is_refused() -> None:
    document = _sealed()
    document["baseline_hash"] = "not-a-sha256"
    with pytest.raises(bridge.BridgeError) as excinfo:
        bridge.verify_baseline_document(document)
    assert _kind(excinfo) == "corrupt_baseline"


def test_missing_hash_field_is_treated_as_unsealed() -> None:
    document = _sealed()
    del document["baseline_hash"]
    with pytest.raises(bridge.BridgeError) as excinfo:
        bridge.verify_baseline_document(document)
    assert _kind(excinfo) == "baseline_unsealed"


def test_unsupported_integrity_version_is_refused() -> None:
    document = _sealed()
    document["baseline_hash_spec"] = "v99"
    with pytest.raises(bridge.BridgeError) as excinfo:
        bridge.verify_baseline_document(document)
    assert _kind(excinfo) == "unsupported_baseline_integrity"


def test_unknown_format_is_refused() -> None:
    document = _sealed()
    document["format"] = "something-else-v1"
    with pytest.raises(bridge.BridgeError) as excinfo:
        bridge.verify_baseline_document(document)
    assert _kind(excinfo) == "corrupt_baseline"


def test_non_object_document_is_refused() -> None:
    with pytest.raises(bridge.BridgeError) as excinfo:
        bridge.verify_baseline_document(["not", "an", "object"])
    assert _kind(excinfo) == "corrupt_baseline"


# --------------------------------------------------------------------------- #
# The loader every entry point uses
# --------------------------------------------------------------------------- #


def _write(tmp_path: Path, document: Any) -> Path:
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(document, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def test_loader_accepts_a_valid_baseline(tmp_path: Path) -> None:
    document = _sealed()
    path = _write(tmp_path, document)
    loaded = bridge.load_baseline(str(path), Path("C:/ws"), "app.py")
    assert loaded["resource"] == "app.py"
    assert loaded["baseline_hash"] == document["baseline_hash"]


def test_loader_refuses_a_tampered_baseline(tmp_path: Path) -> None:
    document = _sealed()
    document["snapshot"] = dict(document["snapshot"])
    document["snapshot"]["content_b64"] = base64.b64encode(b"EVIL\r\n").decode("ascii")
    document["snapshot"]["hash"] = hashlib.sha256(b"EVIL\r\n").hexdigest()
    path = _write(tmp_path, document)
    with pytest.raises(bridge.BridgeError) as excinfo:
        bridge.load_baseline(str(path), Path("C:/ws"), "app.py")
    assert _kind(excinfo) == "baseline_integrity_failed"


def test_loader_refuses_a_legacy_baseline(tmp_path: Path) -> None:
    legacy = {
        "format": bridge.LEGACY_BASELINE_FORMAT,
        "workspace": "C:/ws",
        "resource": "app.py",
        "captured_at": "2026-10-20T10:00:00+00:00",
        "snapshot": _snapshot(),
    }
    path = _write(tmp_path, legacy)
    with pytest.raises(bridge.BridgeError) as excinfo:
        bridge.load_baseline(str(path), Path("C:/ws"), "app.py")
    assert _kind(excinfo) == "baseline_unsealed"


def test_loader_refuses_a_baseline_of_another_workspace(tmp_path: Path) -> None:
    document = _sealed(workspace="C:/other")
    path = _write(tmp_path, document)
    with pytest.raises(bridge.BridgeError) as excinfo:
        bridge.load_baseline(str(path), Path("C:/ws"), "app.py")
    assert _kind(excinfo) == "not_authorized"


def test_loader_refuses_a_baseline_of_another_resource(tmp_path: Path) -> None:
    document = _sealed(resource="other.py")
    path = _write(tmp_path, document)
    with pytest.raises(bridge.BridgeError) as excinfo:
        bridge.load_baseline(str(path), Path("C:/ws"), "app.py")
    assert _kind(excinfo) == "not_authorized"


def test_loader_refuses_a_truncated_baseline(tmp_path: Path) -> None:
    document = _sealed()
    path = tmp_path / "baseline.json"
    path.write_text(
        json.dumps(document, ensure_ascii=False, default=str)[:200],
        encoding="utf-8",
    )
    with pytest.raises(bridge.BridgeError) as excinfo:
        bridge.load_baseline(str(path), Path("C:/ws"), "app.py")
    assert _kind(excinfo) == "corrupt_baseline"
