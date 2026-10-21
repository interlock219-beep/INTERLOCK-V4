#!/usr/bin/env python3
"""Interlock VS Code bridge - a thin, dedicated integration layer.

This script is the *only* integration surface between the Interlock VS Code
extension and the Interlock engine. It contains no recovery logic of its own:
every state-changing or advisory decision is delegated to the engine's own
classes (`FilesystemRecoveryAdapter`, `WorkspacePathSecurity`).

Design rules (enforced by review and by the extension's unit tests):
  * Read-only by default. Only the `execute` subcommand changes files, and it
    only runs after the engine's own simulation/conflict/drift checks pass and
    the extension has obtained explicit user approval (`--approved-by`).
  * One JSON envelope per invocation on stdout, never a bare traceback.
  * No network, no shell, no eval, no execution of instructions found in the
    inspected workspace.
  * Refuses workspaces/resources that fail the engine's own confinement rules.

Exit codes (the extension maps these to user-facing messages):
   0 success
   2 invalid invocation / invalid arguments
   3 engine unavailable (import failed or fingerprint mismatch)
   4 workspace or resource outside the authorized boundary
   5 engine refusal (conflict, drift, unsafe precondition, unsupported fs)
   6 verification failed
   7 missing precondition (e.g. no baseline captured)
   8 unexpected internal error

Run:  python interlock_bridge.py probe
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import hmac
import io
import json
import os
import platform
import sys
import traceback
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

BRIDGE_NAME = "interlock-vscode-bridge"
BRIDGE_VERSION = "0.1.0"
# Baseline document format. v2 adds the engine's integrity seal; the legacy
# v1 format carries no seal and is therefore refused (never silently blessed).
BASELINE_FORMAT = "interlock-baseline-v2"
LEGACY_BASELINE_FORMAT = "interlock-baseline-v1"
EVIDENCE_FORMAT = "interlock-evidence-v1"

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_ENGINE_UNAVAILABLE = 3
EXIT_NOT_AUTHORIZED = 4
EXIT_REFUSED = 5
EXIT_VERIFICATION_FAILED = 6
EXIT_PRECONDITION = 7
EXIT_INTERNAL = 8

TENANT_ID = "vscode-extension"
AGENT_ID = "vscode-extension"

# Filesystems the support matrix declares UNSUPPORTED (no atomic-replace guarantee).
UNSUPPORTED_FS = {"fat", "fat32", "exfat", "vfat", "msdos", "smbfs", "cifs", "nfs", "nfs4", "afp"}

MAX_DIFF_ENTRIES = 100
MAX_SCAN_ENTRIES = 300
SCAN_SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "site",
    "logs",
    "out",
    "dist",
    ".next",
}


class BridgeError(Exception):
    """Structured, user-presentable failure."""

    def __init__(
        self, kind: str, message: str, exit_code: int = EXIT_USAGE, hint: str = ""
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.hint = hint
        self.exit_code = exit_code


# --------------------------------------------------------------------------- #
# JSON helpers
# --------------------------------------------------------------------------- #
def jsonable(value: Any, depth: int = 0) -> Any:
    """Convert engine dataclasses/enums/paths into JSON-safe values."""
    if depth > 40:
        return f"[max depth: {type(value).__name__}]"
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return jsonable(value.value, depth + 1)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return base64.b64encode(bytes(value)).decode("ascii")
    if is_dataclass(value) and not isinstance(value, type):
        # dataclasses.fields() also covers frozen/slots dataclasses, which have
        # no __dict__ and would break vars().
        return jsonable(
            {f.name: getattr(value, f.name) for f in fields(value) if not f.name.startswith("_")},
            depth + 1,
        )
    if isinstance(value, dict):
        return {str(k): jsonable(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [jsonable(v, depth + 1) for v in value]
    return str(value)


def _looks_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(
        token in lowered
        for token in (
            "password",
            "secret",
            "token",
            "api_key",
            "apikey",
            "credential",
            "private_key",
        )
    )


def redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    """Drop obviously secret-shaped values from diagnostic payloads."""
    out: dict[str, Any] = {}
    for key, value in data.items():
        if _looks_sensitive(key):
            out[key] = "[redacted]"
        elif isinstance(value, dict):
            out[key] = redact_mapping(value)
        else:
            out[key] = value
    return out


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """SHA-256 of a file, read in chunks.

    Verification must stay bounded in memory: a recovered file can be large,
    so it is never loaded into memory as a whole.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# Engine loading (fingerprint-verified)
# --------------------------------------------------------------------------- #
class Engine:
    """Namespace of verified engine symbols."""

    def __init__(self) -> None:
        self.root: Path
        self.version: str | None
        self.ActionStatus: Any
        self.ProtectedAction: Any
        self.Reversibility: Any
        self.FilesystemRecoveryAdapter: Any
        self.WorkspacePathSecurity: Any
        self.PathSecurityError: Any


def load_engine() -> Engine:
    try:
        import app as app_pkg
        from app.domain.entities.protected_action import (
            ActionStatus,
            ProtectedAction,
            Reversibility,
        )
        from app.infrastructure.recovery.filesystem_recovery_adapter import (
            FilesystemRecoveryAdapter,
        )
        from sdk.workspace_protection.path_security import PathSecurityError, WorkspacePathSecurity
    except Exception as exc:  # noqa: BLE001 - reported as a structured error
        raise BridgeError(
            "engine_unavailable",
            f"Could not import the Interlock engine: {type(exc).__name__}: {exc}",
            EXIT_ENGINE_UNAVAILABLE,
            "Set `interlock.engineRoot` to the Interlock checkout (the directory "
            "containing the `app` package) or install the engine into the "
            "configured Python interpreter. See docs/operations/BETA_FIRST_RUN.md.",
        ) from exc

    # Fingerprint: a generic top-level `app` package must not be mistaken for
    # Interlock. All three modules above must import; this is the minimum set.
    engine = Engine()
    engine.root = Path(app_pkg.__file__).resolve().parent.parent
    engine.ActionStatus = ActionStatus
    engine.ProtectedAction = ProtectedAction
    engine.Reversibility = Reversibility
    engine.FilesystemRecoveryAdapter = FilesystemRecoveryAdapter
    engine.WorkspacePathSecurity = WorkspacePathSecurity
    engine.PathSecurityError = PathSecurityError
    engine.version = _installed_version()
    return engine


def _installed_version() -> str | None:
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return str(version("intentlock"))
        except PackageNotFoundError:
            return None
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# Platform / filesystem facts
# --------------------------------------------------------------------------- #
def filesystem_facts(target: Path) -> dict[str, Any]:
    """Best-effort filesystem facts, without spawning any subprocess."""
    facts: dict[str, Any] = {
        "filesystem": "unknown",
        "drive_type": "unknown",
        "long_paths_enabled": None,
        "target": str(target),
    }
    if os.name == "nt":
        try:
            import ctypes
            import winreg

            drive = os.path.splitdrive(str(Path(target).resolve()))[0] + "\\"
            if drive:
                volume_name = ctypes.create_unicode_buffer(261)
                fs_name = ctypes.create_unicode_buffer(261)
                ctypes.windll.kernel32.GetVolumeInformationW(
                    ctypes.c_wchar_p(drive),
                    volume_name,
                    261,
                    None,
                    None,
                    None,
                    fs_name,
                    261,
                )
                facts["filesystem"] = fs_name.value or "unknown"
                dtype = ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(drive))
                facts["drive_type"] = {
                    0: "unknown",
                    1: "invalid",
                    2: "removable",
                    3: "local",
                    4: "network",
                    5: "compact_disc",
                    6: "ram_disk",
                }.get(int(dtype), "unknown")
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Control\FileSystem",
                )
                value, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
                facts["long_paths_enabled"] = int(value)
                winreg.CloseKey(key)
            except OSError:
                facts["long_paths_enabled"] = None
        except Exception:  # noqa: BLE001
            facts["filesystem"] = "unknown"
    elif sys.platform.startswith("linux"):
        try:
            resolved = str(Path(target).resolve())
            best = ""
            best_fstype = "unknown"
            with open("/proc/mounts", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    parts = line.split()
                    if (
                        len(parts) >= 3
                        and resolved.startswith(parts[1])
                        and len(parts[1]) >= len(best)
                    ):
                        best, best_fstype = parts[1], parts[2]
            facts["filesystem"] = best_fstype
        except Exception:  # noqa: BLE001
            facts["filesystem"] = "unknown"
    elif sys.platform == "darwin":
        facts["filesystem"] = "apfs_or_hfs_plus"
    return facts


def support_verdict(facts: dict[str, Any]) -> dict[str, Any]:
    """Mirror docs/operations/SUPPORTED_PLATFORMS.md for the *engine*.

    The extension's own package installs everywhere; this verdict is about the
    engine's recovery support and is deliberately stricter than the extension's.
    """
    system = platform.system()
    machine = platform.machine().lower()
    fs_name = str(facts.get("filesystem") or "unknown").lower()
    drive_type = str(facts.get("drive_type") or "unknown").lower()
    warnings: list[str] = []
    status = "untested"
    detail = "No recorded evidence for this environment."

    if system == "Windows":
        if machine in {"amd64", "x86_64"}:
            status = "tested_primary"
            detail = "Windows x64 + NTFS + Python 3.11.9 is the recorded primary test environment."
        elif machine in {"arm64"}:
            status = "untested"
            detail = "Windows ARM64: no hardware evidence recorded."
        else:
            status = "untested"
            detail = f"Unrecognized Windows architecture: {machine}."
        if drive_type == "network" or fs_name in {"smbfs", "cifs", "nfs", "nfs4"}:
            status = "unsupported"
            detail = "Network/redirected drive: no local atomic-replace guarantee."
            warnings.append(
                "Workspace is on a network drive - the engine declares this UNSUPPORTED."
            )
        elif fs_name in UNSUPPORTED_FS:
            status = "unsupported"
            detail = (
                f"Filesystem {facts.get('filesystem')} does not guarantee "
                "rename durability/atomicity."
            )
            warnings.append(
                f"Filesystem {facts.get('filesystem')} is declared UNSUPPORTED "
                "by the engine support matrix."
            )
        if facts.get("long_paths_enabled") == 0:
            warnings.append(
                "Windows long paths are disabled (LongPathsEnabled=0); "
                "paths >260 chars are untested."
            )
        if len(str(facts.get("target") or "")) > 260:
            warnings.append(
                "Workspace path exceeds 260 characters - untested territory for the engine."
            )
    elif system == "Darwin":
        if machine in {"arm64", "aarch64"}:
            status = "declared_ci_pending"
            detail = (
                "macOS arm64: dependencies resolved, native engine validation still pending CI."
            )
            warnings.append("macOS engine support is DECLARED - not yet validated by executed CI.")
        else:
            status = "unsupported"
            detail = "macOS Intel: dependency-blocked (no cryptography wheel for x86_64)."
            warnings.append("macOS Intel is dependency-blocked for the engine.")
    elif system == "Linux":
        status = "declared_ci_pending"
        detail = "Linux x64: declared support; CI job encoded but never executed."
        warnings.append("Linux engine support is DECLARED - not yet validated by executed CI.")
    else:
        detail = f"Unrecognized platform: {system}."

    return {"status": status, "detail": detail, "warnings": warnings}


def python_facts() -> dict[str, Any]:
    version_info = sys.version_info
    valid = (3, 11) <= (version_info.major, version_info.minor) < (3, 15)
    return {
        "executable": sys.executable,
        "version": platform.python_version(),
        "in_supported_range": valid,
        "declared_range": ">=3.11,<3.15",
    }


# --------------------------------------------------------------------------- #
# Actions / workspace helpers
# --------------------------------------------------------------------------- #
def make_action(engine: Engine, action_id: str, resource: str) -> Any:
    """Build the ProtectedAction shape the engine's own tests and demos use."""
    return engine.ProtectedAction(
        action_id=action_id,
        tenant_id=TENANT_ID,
        agent_id=AGENT_ID,
        actor_user_id=None,
        authority_grant_id=None,
        tool="filesystem",
        resource=resource,
        action_type="modify",
        risk_score=0.5,
        policy_version="v1",
        correlation_id=f"vscode-{action_id}",
        parent_action_id=None,
        workflow_id=None,
        reversibility=engine.Reversibility.AUTOMATICALLY_REVERSIBLE,
        before_state_ref=f"state:before:{action_id}",
        after_state_ref=f"state:after:{action_id}",
        tool_arguments={"path": resource},
        status=engine.ActionStatus.EXECUTED,
        decision_reason="vscode extension",
        evaluated_at=None,
        executed_at=None,
        created_at=None,
    )


def stable_action_id(workspace: Path, resource: str) -> str:
    digest = sha256_bytes(f"{workspace.resolve()}|{resource}".encode())[:16]
    return f"vscode-{digest}"


def is_unc_path(raw: str | Path) -> bool:
    """True for a UNC / network path in EITHER slash form.

    ``Path("//server/share")`` keeps its forward slashes, so a check for a
    leading ``\\\\`` alone misses the forward-slash form and lets a network
    workspace through. The drive of a resolved UNC path is the reliable
    signal, so both forms are refused here.
    """
    text = str(raw)
    if text.startswith("\\\\") or text.startswith("//"):
        return True
    return Path(raw).drive.startswith("\\\\")


def require_workspace(raw: str | None) -> Path:
    if not raw:
        raise BridgeError(
            "no_workspace",
            "No workspace folder is open. Open a folder and try again.",
            EXIT_NOT_AUTHORIZED,
        )
    candidate = Path(raw)
    if is_unc_path(candidate):
        raise BridgeError(
            "not_authorized",
            "UNC/network workspace paths are not allowed.",
            EXIT_NOT_AUTHORIZED,
        )
    if not candidate.exists():
        raise BridgeError(
            "not_authorized",
            f"Workspace path does not exist: {candidate}",
            EXIT_NOT_AUTHORIZED,
        )
    if not candidate.is_dir():
        raise BridgeError(
            "not_authorized",
            f"Workspace path is not a directory: {candidate}",
            EXIT_NOT_AUTHORIZED,
        )
    return candidate.resolve()


def normalize_resource(engine: Engine, workspace: Path, raw: str | None) -> tuple[str, str]:
    """Return (resource_identifier, workspace_relative_path), validated.

    Validation is delegated to the engine's WorkspacePathSecurity; the bridge
    adds only syntax normalization on top of it.
    """
    if not raw or not str(raw).strip():
        raise BridgeError("invalid_resource", "No target resource was provided.", EXIT_USAGE)
    rel = str(raw).replace("\\", "/").strip()
    if rel.startswith("/"):
        raise BridgeError(
            "not_authorized",
            "Absolute resource paths are not allowed; use a workspace-relative path.",
            EXIT_NOT_AUTHORIZED,
        )
    if ".." in rel.split("/"):
        raise BridgeError(
            "not_authorized",
            "Parent traversal ('..') in a resource path is refused.",
            EXIT_NOT_AUTHORIZED,
        )
    try:
        security = engine.WorkspacePathSecurity(workspace)
        security.validate(workspace / rel)
    except Exception as exc:  # noqa: BLE001 - engine refusal is the result
        raise BridgeError(
            "not_authorized",
            f"Resource refused by the engine's path security: {exc}",
            EXIT_NOT_AUTHORIZED,
        ) from exc
    return f"file:{rel}", rel


# --------------------------------------------------------------------------- #
# Baseline integrity
# --------------------------------------------------------------------------- #
# A baseline is the ONLY record of the before-state a recovery restores. It is
# therefore sealed the same way the preview evidence is sealed (evidence hash
# spec v2): the seal is a SHA-256 over a canonical JSON rendering of the whole
# document - workspace, resource, capture time and the complete snapshot
# including the file contents - excluding only the seal field itself.
#
# Threat model (identical to the evidence v2 spec): the seal detects corruption
# and edits by an actor who cannot recompute the canonical hash. It is NOT a
# signature: an actor with write access to the baseline store can recompute a
# matching hash. Tamper-PROOF evidence requires signed receipts backed by
# external key management, which stays an external-validation blocker.
#
# The seal is produced by the engine (capture) and verified by the engine
# (load). No interface may write a baseline document the engine did not produce,
# and no interface may recover from a baseline whose seal does not verify.
BASELINE_HASH_FIELD = "baseline_hash"
BASELINE_HASH_SPEC_FIELD = "baseline_hash_spec"
BASELINE_HASH_SPEC = "v1"
_SHA256_HEX_LENGTH = 64


def _is_sha256_hex(value: Any) -> bool:
    """True when *value* is a 64-char lowercase sha256 hex string."""
    return (
        isinstance(value, str)
        and len(value) == _SHA256_HEX_LENGTH
        and all(char in "0123456789abcdef" for char in value)
    )


def _canonical_baseline_json(document: dict[str, Any]) -> str:
    """Canonical JSON preimage of a baseline document (the seal field excluded)."""
    payload = {key: value for key, value in document.items() if key != BASELINE_HASH_FIELD}
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )


def compute_baseline_hash(document: dict[str, Any]) -> str:
    """SHA-256 over the canonical baseline document (seal field excluded)."""
    return hashlib.sha256(_canonical_baseline_json(document).encode("utf-8")).hexdigest()


def seal_baseline_document(document: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *document* carrying the engine's integrity seal.

    The spec marker is part of the sealed payload, so a document cannot claim a
    different integrity version without breaking the seal.
    """
    sealed = {key: value for key, value in document.items() if key != BASELINE_HASH_FIELD}
    sealed[BASELINE_HASH_SPEC_FIELD] = BASELINE_HASH_SPEC
    sealed[BASELINE_HASH_FIELD] = compute_baseline_hash(sealed)
    return sealed


def build_baseline_document(
    workspace: Path | str,
    resource: str,
    captured_at: Any,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Build the sealed baseline document for one captured snapshot."""
    return seal_baseline_document(
        {
            "format": BASELINE_FORMAT,
            "workspace": str(workspace),
            "resource": resource,
            "captured_at": captured_at,
            "snapshot": snapshot,
        }
    )


def _verify_snapshot_consistency(snapshot: Any) -> None:
    """The snapshot's stored content must match the hash it records.

    This is a self-consistency check, not an authenticity proof: it catches a
    document whose seal verifies but whose content does not match its own hash
    (a broken writer, a partial write, a hand-edited file).
    """
    if not isinstance(snapshot, dict):
        raise BridgeError(
            "corrupt_baseline",
            "Baseline does not contain an engine snapshot.",
            EXIT_PRECONDITION,
        )
    content_b64 = snapshot.get("content_b64")
    expected = snapshot.get("hash")
    if content_b64 is None or expected is None:
        return
    try:
        raw = base64.b64decode(content_b64)
    except (ValueError, TypeError) as exc:
        raise BridgeError(
            "corrupt_baseline",
            f"Baseline content could not be decoded: {exc}",
            EXIT_PRECONDITION,
        ) from exc
    actual = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(actual, str(expected)):
        raise BridgeError(
            "baseline_integrity_failed",
            "Baseline content does not match the hash it records.",
            EXIT_REFUSED,
            "The baseline file was modified after it was captured. Interlock will not "
            "recover from an unverified baseline - capture a new one.",
        )


def verify_baseline_document(document: Any) -> dict[str, Any]:
    """Fail closed unless *document* carries a valid, current integrity seal.

    Every baseline consumer goes through this function (the bridge's
    ``load_baseline``), so the CLI, the VS Code extension, bulk recovery and
    direct bridge calls all get the same protection.
    """
    if not isinstance(document, dict):
        raise BridgeError(
            "corrupt_baseline",
            "Baseline document is not a JSON object.",
            EXIT_PRECONDITION,
        )
    typed: dict[str, Any] = document
    document_format = typed.get("format")
    if document_format == LEGACY_BASELINE_FORMAT:
        raise BridgeError(
            "baseline_unsealed",
            "This baseline predates integrity sealing and cannot be verified.",
            EXIT_PRECONDITION,
            "Capture a new baseline ('interlock protect' / 'Interlock: Capture Baseline'). "
            "The existing baseline file is left untouched.",
        )
    if document_format != BASELINE_FORMAT:
        raise BridgeError(
            "corrupt_baseline",
            "Baseline file has an unrecognised format.",
            EXIT_PRECONDITION,
        )
    spec = typed.get(BASELINE_HASH_SPEC_FIELD)
    if spec is None:
        raise BridgeError(
            "baseline_unsealed",
            "Baseline does not carry an integrity seal.",
            EXIT_PRECONDITION,
            "Capture a new baseline. The existing baseline file is left untouched.",
        )
    if spec != BASELINE_HASH_SPEC:
        raise BridgeError(
            "unsupported_baseline_integrity",
            f"Unsupported baseline integrity version: {spec!r}.",
            EXIT_PRECONDITION,
            "Capture a new baseline with the current engine.",
        )
    stored = typed.get(BASELINE_HASH_FIELD)
    if stored is None:
        raise BridgeError(
            "baseline_unsealed",
            "Baseline does not carry an integrity seal.",
            EXIT_PRECONDITION,
            "Capture a new baseline. The existing baseline file is left untouched.",
        )
    if not _is_sha256_hex(stored):
        raise BridgeError(
            "corrupt_baseline",
            "Baseline integrity seal is malformed.",
            EXIT_PRECONDITION,
            "Capture a new baseline. The existing baseline file is left untouched.",
        )
    recomputed = compute_baseline_hash(typed)
    if not hmac.compare_digest(recomputed, str(stored)):
        raise BridgeError(
            "baseline_integrity_failed",
            "Baseline integrity check failed: the baseline was modified after capture.",
            EXIT_REFUSED,
            "Interlock will not recover from an unverified baseline. Restore the original "
            "baseline file, or capture a new one.",
        )
    _verify_snapshot_consistency(typed.get("snapshot"))
    snapshot = typed.get("snapshot")
    if isinstance(snapshot, dict) and snapshot.get("truncated"):
        # A truncated capture holds only a prefix of the original file. It can
        # never restore the file, so it is refused here instead of producing a
        # plan that would shrink the file.
        raise BridgeError(
            "baseline_truncated",
            "This baseline was truncated at capture time and cannot restore the file.",
            EXIT_PRECONDITION,
            "Capture a new baseline for this file (a file above the size limit cannot be "
            "captured completely).",
        )
    return typed


def load_baseline(path: str | None, workspace: Path, rel_resource: str) -> dict[str, Any]:
    if not path:
        raise BridgeError(
            "no_baseline",
            f"No baseline is recorded for '{rel_resource}'.",
            EXIT_PRECONDITION,
            "Run 'Interlock: Capture Baseline' before an agent modifies the file.",
        )
    baseline_path = Path(path)
    if not baseline_path.is_file():
        raise BridgeError(
            "no_baseline",
            f"Baseline file not found: {baseline_path}",
            EXIT_PRECONDITION,
            "Re-run 'Interlock: Capture Baseline'.",
        )
    try:
        raw = baseline_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BridgeError(
            "corrupt_baseline",
            f"Baseline file could not be read: {exc}",
            EXIT_PRECONDITION,
            "Delete the stale baseline and capture it again.",
        ) from exc
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise BridgeError(
            "corrupt_baseline",
            f"Baseline file could not be read: {exc}",
            EXIT_PRECONDITION,
            "Delete the stale baseline and capture it again.",
        ) from exc
    # Integrity first: an unverifiable baseline is never used to plan, preview
    # or authorize a write. This is the single gate every entry point passes.
    data = verify_baseline_document(parsed)
    try:
        stored_workspace = Path(str(data.get("workspace", ""))).resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise BridgeError(
            "corrupt_baseline",
            f"Baseline workspace path is unreadable: {exc}",
            EXIT_PRECONDITION,
        ) from exc
    if stored_workspace != workspace.resolve():
        raise BridgeError(
            "not_authorized",
            "Baseline belongs to a different workspace; refusing to use it.",
            EXIT_NOT_AUTHORIZED,
        )
    if str(data.get("resource", "")) != rel_resource:
        raise BridgeError(
            "not_authorized",
            "Baseline resource does not match the requested resource; refusing.",
            EXIT_NOT_AUTHORIZED,
        )
    snapshot = data.get("snapshot")
    if not isinstance(snapshot, dict) or not snapshot.get("hash"):
        raise BridgeError(
            "corrupt_baseline",
            "Baseline does not contain an engine snapshot with a content hash.",
            EXIT_PRECONDITION,
        )
    return data


def evidence_file_path(baseline_file: str | Path) -> Path:
    """Deterministic sidecar path for the evidence captured by a preview."""
    return Path(str(baseline_file) + ".evidence.json")


def save_evidence(path: Path, workspace: Path, rel: str, evidence: Any) -> None:
    """Persist preview-time evidence atomically (extension-private storage)."""
    document = {
        "format": EVIDENCE_FORMAT,
        "workspace": str(workspace),
        "resource": rel,
        "evidence": jsonable(evidence),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def evidence_from_dict(data: dict[str, Any]) -> Any:
    """Rebuild the engine's RecoveryEvidence from persisted JSON."""
    from app.domain.entities.surgical_recovery_types import (
        AdapterCapability,
        CompensationType,
        RecoveryAdapterType,
        RecoveryEvidence,
        Reversibility,
    )

    allowed = {f.name for f in fields(RecoveryEvidence)}
    kwargs = {k: v for k, v in data.items() if k in allowed}
    created = kwargs.get("created_at")
    kwargs["created_at"] = datetime.fromisoformat(str(created)) if created else datetime.now(UTC)
    for key, enum_cls in (
        ("compensation_type", CompensationType),
        ("recovery_adapter_type", RecoveryAdapterType),
        ("reversibility_classification", Reversibility),
        ("adapter_capability", AdapterCapability),
    ):
        value = kwargs.get(key)
        if value is not None and not isinstance(value, enum_cls):
            kwargs[key] = enum_cls(value)
    return RecoveryEvidence(**kwargs)


def load_evidence(path_str: str | None, workspace: Path, rel: str) -> tuple[Any, dict[str, Any]]:
    """Load preview-time evidence and verify the engine's own seal hash."""
    if not path_str:
        raise BridgeError(
            "preview_required",
            "No preview evidence is recorded for this recovery.",
            EXIT_PRECONDITION,
            "Run 'Interlock: Preview Recovery Plan' immediately before applying recovery.",
        )
    path = Path(path_str)
    if not path.is_file():
        raise BridgeError(
            "preview_required",
            f"Preview evidence file not found: {path}",
            EXIT_PRECONDITION,
            "Re-run 'Interlock: Preview Recovery Plan'.",
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BridgeError(
            "corrupt_evidence",
            f"Preview evidence could not be read: {exc}",
            EXIT_PRECONDITION,
        ) from exc
    if not isinstance(document, dict) or document.get("format") != EVIDENCE_FORMAT:
        raise BridgeError(
            "corrupt_evidence",
            "Preview evidence has an unrecognised format.",
            EXIT_PRECONDITION,
        )
    if Path(str(document.get("workspace", ""))).resolve() != workspace.resolve():
        raise BridgeError(
            "not_authorized",
            "Preview evidence belongs to a different workspace; refusing.",
            EXIT_NOT_AUTHORIZED,
        )
    if str(document.get("resource", "")) != rel:
        raise BridgeError(
            "not_authorized",
            "Preview evidence resource does not match the requested resource; refusing.",
            EXIT_NOT_AUTHORIZED,
        )
    raw = document.get("evidence")
    if not isinstance(raw, dict):
        raise BridgeError(
            "corrupt_evidence",
            "Preview evidence does not contain an evidence record.",
            EXIT_PRECONDITION,
        )
    try:
        evidence = evidence_from_dict(raw)
    except Exception as exc:  # noqa: BLE001
        raise BridgeError(
            "corrupt_evidence",
            f"Preview evidence could not be reconstructed: {type(exc).__name__}: {exc}",
            EXIT_PRECONDITION,
            "Re-run 'Interlock: Preview Recovery Plan'.",
        ) from exc

    # Verify the engine's own evidence seal (spec v2) before using it.
    from app.domain.services.evidence_hash import compute_evidence_hash_v2

    stored = str(evidence.evidence_hash or "")
    recomputed = compute_evidence_hash_v2(evidence)
    if not stored or recomputed != stored:
        raise BridgeError(
            "corrupt_evidence",
            "Evidence seal verification failed - the evidence file was modified or truncated.",
            EXIT_PRECONDITION,
            "Re-run 'Interlock: Preview Recovery Plan' to capture fresh evidence.",
        )
    return evidence, document


def slim_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    """Remove file contents from a snapshot before it reaches the UI/log."""
    if not isinstance(snapshot, dict):
        return snapshot
    keep = (
        "schema_version",
        "captured_at",
        "resource",
        "exists",
        "type",
        "size",
        "hash",
        "binary",
        "encoding",
        "bom",
        "line_endings",
        "metadata",
        "permissions",
        "snapshot_hash",
        "truncated",
        "symlink_target",
    )
    slim = {k: jsonable(v) for k, v in snapshot.items() if k in keep}
    slim["content"] = "[omitted]"
    slim["content_b64"] = "[omitted]"
    return slim


def slim_diff(value: Any, depth: int = 0) -> Any:
    """Bounded, content-free diff rendering."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ("b64", "content", "bytes", "raw")):
                out[str(key)] = "[omitted]"
            else:
                out[str(key)] = slim_diff(item, depth + 1)
        return out
    if isinstance(value, list):
        trimmed = [slim_diff(v, depth + 1) for v in value[:MAX_DIFF_ENTRIES]]
        if len(value) > MAX_DIFF_ENTRIES:
            trimmed.append(f"... [{len(value) - MAX_DIFF_ENTRIES} more entries omitted]")
        return trimmed
    return jsonable(value)


def scan_workspace(workspace: Path) -> dict[str, Any]:
    """Read-only, bounded workspace scan for the sidebar target picker."""
    entries: list[dict[str, Any]] = []
    symlinks_outside: list[str] = []
    depth_cap = 8
    base = workspace.resolve()
    for current, dirs, files in os.walk(workspace, followlinks=False):
        rel_dir = Path(current).resolve().relative_to(base)
        if len(rel_dir.parts) >= depth_cap:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in SCAN_SKIP_DIRS]
        for name in files:
            if len(entries) >= MAX_SCAN_ENTRIES:
                break
            full = Path(current) / name
            try:
                if full.is_symlink():
                    try:
                        full.resolve().relative_to(base)
                    except ValueError:
                        symlinks_outside.append(str(full.relative_to(base)))
                    continue
                stat_info = full.lstat()
                entries.append(
                    {
                        "path": str(full.relative_to(base)).replace("\\", "/"),
                        "size": stat_info.st_size,
                        "mtime": stat_info.st_mtime,
                    }
                )
            except OSError:
                continue
        if len(entries) >= MAX_SCAN_ENTRIES:
            break
    entries.sort(key=lambda item: item["path"])
    return {
        "files": entries,
        "truncated": len(entries) >= MAX_SCAN_ENTRIES,
        "symlinks_pointing_outside": symlinks_outside,
    }


# --------------------------------------------------------------------------- #
# Subcommands
# --------------------------------------------------------------------------- #
async def cmd_probe(args: argparse.Namespace) -> dict[str, Any]:
    engine = load_engine()
    facts = (
        filesystem_facts(Path(args.workspace).resolve())
        if args.workspace
        else filesystem_facts(Path.cwd())
    )
    verdict = support_verdict(facts)
    return {
        "engine": {
            "available": True,
            "version": engine.version,
            "root": str(engine.root),
            "package": "app",
        },
        "python": python_facts(),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "platform": platform.platform(),
            **facts,
        },
        "support": verdict,
        "warnings": verdict["warnings"],
    }


async def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    probe = await cmd_probe(args)
    engine = load_engine()
    result: dict[str, Any] = {
        "probe": probe,
        "adapter": None,
        "workspace": None,
        "incident_history": {
            "available": False,
            "reason": (
                "The filesystem recovery adapter does not record incident history: "
                "filesystem actions carry an empty incident_id and no queryable "
                "incident store exists in the supported beta scope."
            ),
        },
        "documentation": [],
    }
    adapter = engine.FilesystemRecoveryAdapter()
    result["adapter"] = jsonable(await adapter.declare_capabilities())

    if args.workspace:
        workspace = require_workspace(args.workspace)
        try:
            security = engine.WorkspacePathSecurity(workspace)
            result["workspace"] = {
                "path": str(workspace),
                "authorized": True,
                "confinement_root": str(security.workspace_path),
            }
        except Exception as exc:  # noqa: BLE001
            result["workspace"] = {"path": str(workspace), "authorized": False, "error": str(exc)}

    for relative in (
        "docs/INDEX.md",
        "docs/operations/BETA_FIRST_RUN.md",
        "docs/operations/SAFETY_AND_LIMITATIONS.md",
        "docs/operations/SUPPORTED_PLATFORMS.md",
        "docs/operations/TROUBLESHOOTING.md",
    ):
        candidate = Path(args.engine_root or probe["engine"]["root"]) / relative
        if candidate.is_file():
            result["documentation"].append(str(candidate))
    return result


async def cmd_analyze(args: argparse.Namespace) -> dict[str, Any]:
    workspace = require_workspace(args.workspace)
    engine = load_engine()
    facts = filesystem_facts(workspace)
    verdict = support_verdict(facts)

    # 1) Engine confinement probes (read-only; nothing is created).
    probes: list[dict[str, Any]] = []

    async def record(label: str, expected: str, coro: Any) -> None:
        try:
            await coro
            actual, detail = "accepted", ""
        except Exception as exc:  # noqa: BLE001 - a refusal IS the result
            actual, detail = "refused", f"{type(exc).__name__}: {exc}"
        probes.append(
            {
                "probe": label,
                "expected": expected,
                "actual": actual,
                "pass": actual == expected,
                "detail": detail,
            }
        )

    async def call(fn: Any, *fn_args: Any) -> Any:
        return fn(*fn_args)

    security = engine.WorkspacePathSecurity(workspace)
    await record(
        "workspace-relative path accepted", "accepted", call(security.validate, "probe-target.txt")
    )
    await record("parent traversal refused", "refused", call(security.validate, "../outside.txt"))
    await record(
        "UNC path refused", "refused", call(security.validate, "\\\\server\\share\\file.txt")
    )
    outside_anchor = Path(os.path.abspath(os.sep)) / "interlock-outside-probe.txt"
    await record(
        "absolute path outside workspace refused",
        "refused",
        call(security.validate, outside_anchor),
    )

    adapter = engine.FilesystemRecoveryAdapter(base_path=workspace)
    traversal_action = make_action(engine, "vscode-probe-traversal", "file:../outside.txt")
    await record(
        "engine adapter traversal refusal",
        "refused",
        adapter.capture_recovery_evidence(traversal_action),
    )

    # 2) Engine capability for this workspace.
    can_recover = await adapter.can_recover(
        make_action(engine, "vscode-probe-capability", "file:probe.txt")
    )
    capabilities = await adapter.declare_capabilities()

    # 3) Read-only scan used by the sidebar target picker.
    scan = scan_workspace(workspace)

    findings: list[dict[str, str]] = []
    for warning in verdict["warnings"]:
        findings.append({"severity": "warning", "message": warning})
    if str(workspace).startswith("\\\\"):
        findings.append(
            {"severity": "error", "message": "Workspace is a UNC path - refused by the engine."}
        )
    if scan["symlinks_pointing_outside"]:
        findings.append(
            {
                "severity": "warning",
                "message": (
                    f"{len(scan['symlinks_pointing_outside'])} symlink(s) resolve "
                    "outside the workspace: " + ", ".join(scan["symlinks_pointing_outside"][:5])
                ),
            }
        )
    if scan["truncated"]:
        findings.append({"severity": "info", "message": "File listing truncated at the scan cap."})

    return {
        "workspace": str(workspace),
        "filesystem": facts,
        "support": verdict,
        "confinement_probes": probes,
        "confinement_pass": all(p["pass"] for p in probes),
        "adapter_can_recover": can_recover,
        "adapter_capabilities": jsonable(capabilities),
        "scan": scan,
        "findings": findings,
    }


async def cmd_capture_baseline(args: argparse.Namespace) -> dict[str, Any]:
    workspace = require_workspace(args.workspace)
    engine = load_engine()
    resource, rel = normalize_resource(engine, workspace, args.resource)
    target = workspace / rel
    if target.is_symlink():
        raise BridgeError(
            "precondition_failed",
            "Refusing to baseline a symbolic link; target the real file.",
            EXIT_PRECONDITION,
        )
    if not target.is_file():
        raise BridgeError(
            "precondition_failed",
            f"Target is not a regular file: {rel}",
            EXIT_PRECONDITION,
        )
    size = target.stat().st_size
    max_bytes = int(args.max_bytes)
    if size > max_bytes:
        raise BridgeError(
            "precondition_failed",
            f"File is {size} bytes; the baseline limit is {max_bytes} bytes.",
            EXIT_PRECONDITION,
            "Raise `interlock.maxBaselineBytes` if you intentionally want to store "
            "a larger before-state (it includes file contents) in extension storage.",
        )

    adapter = engine.FilesystemRecoveryAdapter(base_path=workspace)
    action = make_action(engine, stable_action_id(workspace, rel), resource)
    evidence = await adapter.capture_recovery_evidence(
        action, execution_context={"base_path": str(workspace)}
    )
    snapshot = evidence.compensation_payload.get("before_snapshot")
    if not isinstance(snapshot, dict) or not snapshot.get("hash"):
        raise BridgeError(
            "engine_refusal",
            "The engine did not return a usable before-snapshot.",
            EXIT_REFUSED,
        )
    snapshot_payload = jsonable(snapshot)
    # The engine seals the baseline document: every interface persists exactly
    # this document, and the engine re-verifies the seal before any use.
    baseline_document = build_baseline_document(
        workspace, rel, snapshot_payload.get("captured_at"), snapshot_payload
    )
    return {
        "workspace": str(workspace),
        "resource": rel,
        "captured_at": snapshot.get("captured_at"),
        "hash": snapshot.get("hash"),
        "size": snapshot.get("size"),
        "snapshot": snapshot_payload,
        "baseline_document": baseline_document,
    }


async def _build_plan(
    engine: Engine,
    workspace: Path,
    resource: str,
    rel: str,
    baseline: dict[str, Any],
    evidence_override: Any | None = None,
) -> dict[str, Any]:
    """Shared, read-only engine computation used by plan/execute/verify.

    With ``evidence_override`` the previously captured (preview-time) evidence
    is reused instead of re-capturing, so ``after_snapshot`` stays the observed
    post-fault state that the engine's conflict guard compares against.
    """
    adapter = engine.FilesystemRecoveryAdapter(base_path=workspace)
    action = make_action(engine, stable_action_id(workspace, rel), resource)
    if evidence_override is not None:
        evidence = evidence_override
    else:
        evidence = await adapter.capture_recovery_evidence(
            action,
            execution_context={"base_path": str(workspace)},
            before_snapshot=baseline["snapshot"],
        )
    simulation = await adapter.simulate(action, evidence)
    conflict = await adapter.check_conflicts(action, evidence)
    drift = await adapter.detect_drift(action, evidence)
    preview = await adapter.preview_recovery(action)
    compensation = await adapter.generate_compensation(action, evidence)
    payload = evidence.compensation_payload
    current = payload.get("current_snapshot") or {}
    before = payload.get("before_snapshot") or {}
    return {
        "adapter": adapter,
        "action": action,
        "evidence": evidence,
        "simulation": simulation,
        "conflict": conflict,
        "drift": drift,
        "preview": preview,
        "compensation": compensation,
        "payload": payload,
        "summary": {
            "resource": rel,
            "workspace": str(workspace),
            "operation": payload.get("operation"),
            "baseline": slim_snapshot(before),
            "current": slim_snapshot(current),
            "current_exists": bool(current.get("exists")),
            "matches_baseline": bool(current.get("hash"))
            and current.get("hash") == before.get("hash"),
            "reversibility": jsonable(simulation.reversibility),
            "would_succeed": bool(simulation.would_succeed),
            "conflict_status": jsonable(conflict.status),
            "drift_status": jsonable(drift.status),
            "simulation_limitation": jsonable(simulation.simulation_limitation),
            "warnings": list(simulation.warnings),
            "requires_approval": True,
            "adapter_preview": jsonable(preview),
            "diff": slim_diff(payload.get("diff")),
            "human_change_analysis": slim_diff(payload.get("human_change_analysis")),
            "concurrent_modification": slim_diff(payload.get("concurrent_modification")),
        },
    }


async def cmd_plan(args: argparse.Namespace) -> dict[str, Any]:
    workspace = require_workspace(args.workspace)
    engine = load_engine()
    resource, rel = normalize_resource(engine, workspace, args.resource)
    baseline = load_baseline(args.baseline_file, workspace, rel)
    plan = await _build_plan(engine, workspace, resource, rel, baseline)
    summary: dict[str, Any] = plan["summary"]
    summary["baseline_captured_at"] = baseline.get("captured_at")
    if not summary["matches_baseline"]:
        summary.setdefault("warnings", []).append(
            "Current file state differs from the captured baseline - "
            "this is what recovery would restore."
        )
    # Persist preview-time evidence: this capture IS the conflict guard used by
    # a later approval-gated execution (any change in between -> refused).
    evidence_path = evidence_file_path(args.baseline_file)
    save_evidence(evidence_path, workspace, rel, plan["evidence"])
    summary["evidence_file"] = str(evidence_path)
    summary["evidence_captured_at"] = jsonable(plan["evidence"].created_at)
    summary["note"] = (
        "Evidence captured now. If the file changes afterwards, execution will be "
        "refused - run Preview again to re-observe the current state."
    )
    return summary


async def cmd_plan_many(args: argparse.Namespace) -> dict[str, Any]:
    """Plan many files in one engine process (read-only unless --save-evidence).

    The manifest is written by the extension into its own private storage and
    lists ``{resource, baseline_file}`` pairs. Every entry is validated with
    the engine's own path security and the stored baseline before it is
    planned, exactly like a single-file ``plan`` call. A failure is reported
    for that entry only - the batch keeps going so partial results stay
    usable and honest.
    """
    workspace = require_workspace(args.workspace)
    engine = load_engine()

    manifest_path = getattr(args, "resources_file", None)
    if not manifest_path:
        raise BridgeError(
            "invalid_invocation",
            "plan-many requires --resources-file.",
            EXIT_USAGE,
        )
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BridgeError(
            "invalid_invocation",
            f"The resource manifest could not be read: {exc}",
            EXIT_USAGE,
        ) from exc
    if not isinstance(manifest, dict):
        raise BridgeError(
            "invalid_invocation",
            "The resource manifest is not a JSON object.",
            EXIT_USAGE,
        )
    declared = manifest.get("workspace")
    if isinstance(declared, str) and declared.strip():
        try:
            if Path(declared).resolve() != workspace:
                raise BridgeError(
                    "not_authorized",
                    "The resource manifest belongs to a different workspace.",
                    EXIT_NOT_AUTHORIZED,
                )
        except OSError:
            pass
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise BridgeError(
            "invalid_invocation",
            "The resource manifest has no entries.",
            EXIT_USAGE,
        )

    offset = max(0, int(getattr(args, "offset", 0) or 0))
    limit = int(getattr(args, "limit", 0) or 0)
    selected = entries[offset:] if limit <= 0 else entries[offset : offset + limit]
    persist_evidence = bool(getattr(args, "save_evidence", False))

    results: list[dict[str, Any]] = []
    for entry in selected:
        if not isinstance(entry, dict):
            results.append(
                {
                    "resource": "",
                    "ok": False,
                    "error": {
                        "kind": "invalid_invocation",
                        "message": "Manifest entry is not an object.",
                        "hint": "",
                    },
                }
            )
            continue
        raw_resource = entry.get("resource")
        baseline_file = entry.get("baseline_file")
        label = raw_resource if isinstance(raw_resource, str) else ""
        try:
            resource, rel = normalize_resource(engine, workspace, raw_resource)
            baseline = load_baseline(baseline_file, workspace, rel)
            plan = await _build_plan(engine, workspace, resource, rel, baseline)
            summary: dict[str, Any] = plan["summary"]
            summary["baseline_captured_at"] = baseline.get("captured_at")
            if not summary["matches_baseline"]:
                summary.setdefault("warnings", []).append(
                    "Current file state differs from the captured baseline - "
                    "this is what recovery would restore."
                )
            if persist_evidence:
                evidence_path = evidence_file_path(str(baseline_file))
                save_evidence(evidence_path, workspace, rel, plan["evidence"])
                summary["evidence_file"] = str(evidence_path)
                summary["evidence_captured_at"] = jsonable(plan["evidence"].created_at)
                summary["note"] = (
                    "Evidence captured now. If the file changes afterwards, execution will be "
                    "refused - review the recovery again to re-observe the current state."
                )
            results.append({"resource": rel, "ok": True, "summary": summary})
        except BridgeError as exc:
            results.append(
                {
                    "resource": label,
                    "ok": False,
                    "error": {"kind": exc.kind, "message": exc.message, "hint": exc.hint},
                }
            )
        except Exception as exc:  # noqa: BLE001 - one bad file must not kill the batch
            results.append(
                {
                    "resource": label,
                    "ok": False,
                    "error": {
                        "kind": "internal_error",
                        "message": f"{type(exc).__name__}: {exc}",
                        "hint": "",
                    },
                }
            )
    return {
        "total": len(entries),
        "offset": offset,
        "count": len(results),
        "entries": results,
    }


async def cmd_execute(args: argparse.Namespace) -> dict[str, Any]:
    workspace = require_workspace(args.workspace)
    engine = load_engine()
    resource, rel = normalize_resource(engine, workspace, args.resource)
    baseline = load_baseline(args.baseline_file, workspace, rel)
    evidence, _document = load_evidence(getattr(args, "evidence_file", None), workspace, rel)
    approved_by = (args.approved_by or "").strip()
    if not approved_by:
        raise BridgeError(
            "approval_required",
            "Recovery requires an explicit approver identity (--approved-by).",
            EXIT_REFUSED,
        )

    # The preview and the execution must describe the same before-state.
    preview_before = (evidence.compensation_payload or {}).get("before_snapshot") or {}
    baseline_before = baseline.get("snapshot") or {}
    if preview_before.get("hash") != baseline_before.get("hash"):
        raise BridgeError(
            "preview_required",
            "The recorded preview does not match the current baseline.",
            EXIT_PRECONDITION,
            "Re-run 'Interlock: Preview Recovery Plan'.",
        )

    facts = filesystem_facts(workspace)
    verdict = support_verdict(facts)
    if verdict["status"] == "unsupported":
        raise BridgeError(
            "unsupported_environment",
            f"Refusing recovery in this environment: {verdict['detail']}",
            EXIT_REFUSED,
            "See docs/operations/SUPPORTED_PLATFORMS.md.",
        )

    plan = await _build_plan(engine, workspace, resource, rel, baseline, evidence_override=evidence)
    summary = plan["summary"]

    # Fail closed on the engine's own simulation/conflict/drift verdicts.
    if not summary["would_succeed"]:
        raise BridgeError(
            "engine_refusal",
            "The engine's simulation says recovery would not succeed; refusing to run it.",
            EXIT_REFUSED,
            "; ".join(summary["warnings"]) or "See the preview for details.",
        )
    if summary["conflict_status"] != "no_conflict":
        raise BridgeError(
            "engine_refusal",
            f"Conflict detected ({summary['conflict_status']}); recovery is "
            "blocked to preserve later edits.",
            EXIT_REFUSED,
            "Inspect the file, re-capture a baseline if the current state is intended, then retry.",
        )
    if summary["drift_status"] != "no_drift":
        raise BridgeError(
            "engine_refusal",
            f"Drift detected ({summary['drift_status']}); refusing recovery.",
            EXIT_REFUSED,
        )

    adapter = plan["adapter"]
    compensation = plan["compensation"]
    result = await adapter.execute_compensation(compensation, plan["evidence"].idempotency_key)
    execution_state = str(getattr(result.execution_state, "value", result.execution_state))

    verification, engine_verified = await _safe_verify(adapter, compensation)
    independent = _independent_check(workspace, rel, baseline)
    verified = bool(result.success) and engine_verified and bool(independent["byte_exact"])

    outcome = {
        "resource": rel,
        "workspace": str(workspace),
        "approved_by": approved_by,
        "adapter_success": bool(result.success),
        "execution_state": execution_state,
        "adapter_error": str(result.error) if result.error else None,
        "engine_verification": verification,
        "independent_check": independent,
        "verified": engine_verified,
        "success": verified,
    }
    if not verified:
        raise EngineOutcome(EXIT_VERIFICATION_FAILED if result.success else EXIT_REFUSED, outcome)
    return outcome


def _independent_check(workspace: Path, rel: str, baseline: dict[str, Any]) -> dict[str, Any]:
    """Harness-owned check: adapter claims are never trusted."""
    target = workspace / rel
    expected = baseline["snapshot"].get("hash")
    if not target.is_file():
        return {
            "file_exists": False,
            "byte_exact": False,
            "expected_hash": expected,
            "actual_hash": None,
        }
    actual = sha256_file(target)
    return {
        "file_exists": True,
        "byte_exact": actual == expected,
        "expected_hash": expected,
        "actual_hash": actual,
        "size": target.stat().st_size,
    }


async def _safe_verify(adapter: Any, compensation: Any) -> tuple[dict[str, Any], bool]:
    """Run the engine's verification; an exception must never mask a verdict."""
    try:
        verification = await adapter.verify(compensation)
    except Exception as exc:  # noqa: BLE001 - reported as a failed verification
        return (
            {
                "verified": False,
                "details": {"reason": f"Verification raised: {type(exc).__name__}: {exc}"},
            },
            False,
        )
    data = jsonable(verification)
    if isinstance(data, dict):
        return data, bool(data.get("verified"))
    return {"verified": False, "details": {"reason": "Unrecognised verification result"}}, False


async def cmd_verify(args: argparse.Namespace) -> dict[str, Any]:
    workspace = require_workspace(args.workspace)
    engine = load_engine()
    resource, rel = normalize_resource(engine, workspace, args.resource)
    baseline = load_baseline(args.baseline_file, workspace, rel)
    plan = await _build_plan(engine, workspace, resource, rel, baseline)
    adapter = plan["adapter"]
    verification, engine_verified = await _safe_verify(adapter, plan["compensation"])
    independent = _independent_check(workspace, rel, baseline)
    outcome = {
        "resource": rel,
        "workspace": str(workspace),
        "engine_verification": verification,
        "independent_check": independent,
        "verified": engine_verified,
        "success": engine_verified and bool(independent["byte_exact"]),
        "matches_baseline": plan["summary"]["matches_baseline"],
        "conflict_status": plan["summary"]["conflict_status"],
    }
    if not outcome["success"]:
        raise EngineOutcome(EXIT_VERIFICATION_FAILED, outcome)
    return outcome


class EngineOutcome(Exception):
    """Carries a structured result with a non-zero exit code."""

    def __init__(self, exit_code: int, outcome: dict[str, Any]) -> None:
        super().__init__("engine outcome")
        self.exit_code = exit_code
        self.outcome = outcome


# --------------------------------------------------------------------------- #
# Argument parsing / envelope
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=BRIDGE_NAME, add_help=True)
    parser.add_argument(
        "command",
        choices=[
            "probe",
            "status",
            "analyze",
            "capture-baseline",
            "plan",
            "plan-many",
            "execute",
            "verify",
        ],
    )
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--resource", default=None)
    parser.add_argument("--baseline-file", default=None)
    parser.add_argument("--evidence-file", default=None)
    parser.add_argument("--approved-by", default=None)
    parser.add_argument("--engine-root", default=None)
    parser.add_argument("--max-bytes", type=int, default=5 * 1024 * 1024)
    parser.add_argument("--resources-file", default=None)
    parser.add_argument("--save-evidence", action="store_true")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    return parser


def emit(payload: dict[str, Any], exit_code: int, real_stdout: Any) -> None:
    json.dump(payload, real_stdout, ensure_ascii=False, default=str)
    real_stdout.write("\n")
    real_stdout.flush()


def apply_engine_root(args: argparse.Namespace) -> None:
    """Make the configured engine checkout importable, if one was given."""
    if not args.engine_root:
        return
    root = Path(str(args.engine_root)).expanduser()
    if not root.is_dir():
        raise BridgeError(
            "engine_unavailable",
            f"`interlock.engineRoot` is not a directory: {root}",
            EXIT_ENGINE_UNAVAILABLE,
        )
    if not (root / "app" / "__init__.py").is_file() and not (root / "app" / "main.py").is_file():
        raise BridgeError(
            "engine_unavailable",
            f"No `app` package found under `interlock.engineRoot`: {root}",
            EXIT_ENGINE_UNAVAILABLE,
            "Point interlock.engineRoot at the Interlock checkout root "
            "(the directory containing the `app` package).",
        )
    resolved = str(root.resolve())
    if resolved not in sys.path:
        sys.path.insert(0, resolved)


async def dispatch(args: argparse.Namespace) -> dict[str, Any]:
    apply_engine_root(args)
    if args.command == "probe":
        return await cmd_probe(args)
    if args.command == "status":
        return await cmd_status(args)
    if args.command == "analyze":
        return await cmd_analyze(args)
    if args.command == "capture-baseline":
        return await cmd_capture_baseline(args)
    if args.command == "plan":
        return await cmd_plan(args)
    if args.command == "plan-many":
        return await cmd_plan_many(args)
    if args.command == "execute":
        return await cmd_execute(args)
    if args.command == "verify":
        return await cmd_verify(args)
    raise BridgeError("invalid_invocation", f"Unknown command: {args.command}", EXIT_USAGE)


def main() -> int:
    real_stdout = sys.stdout
    # Anything the engine prints must never corrupt the JSON envelope.
    sys.stdout = io.StringIO()
    command = ""
    try:
        args = build_parser().parse_args()
        command = args.command
        result = asyncio.run(dispatch(args))
        envelope = {
            "bridge": BRIDGE_NAME,
            "bridge_version": BRIDGE_VERSION,
            "command": command,
            "ok": True,
            "result": jsonable(result),
            "error": None,
            "python": python_facts(),
        }
        sys.stdout = real_stdout
        emit(envelope, EXIT_OK, real_stdout)
        return EXIT_OK
    except EngineOutcome as outcome:
        envelope = {
            "bridge": BRIDGE_NAME,
            "bridge_version": BRIDGE_VERSION,
            "command": command,
            "ok": False,
            "result": jsonable(outcome.outcome),
            "error": {
                "kind": "verification_failed"
                if outcome.exit_code == EXIT_VERIFICATION_FAILED
                else "engine_refusal",
                "message": (
                    "Verification did not confirm a byte-exact restore."
                    if outcome.exit_code == EXIT_VERIFICATION_FAILED
                    else "The engine refused the recovery."
                ),
                "hint": "",
            },
            "python": python_facts(),
        }
        sys.stdout = real_stdout
        emit(envelope, outcome.exit_code, real_stdout)
        return outcome.exit_code
    except BridgeError as exc:
        envelope = {
            "bridge": BRIDGE_NAME,
            "bridge_version": BRIDGE_VERSION,
            "command": command,
            "ok": False,
            "result": None,
            "error": {"kind": exc.kind, "message": exc.message, "hint": exc.hint},
            "python": python_facts(),
        }
        sys.stdout = real_stdout
        emit(envelope, exc.exit_code, real_stdout)
        return exc.exit_code
    except KeyboardInterrupt:
        sys.stdout = real_stdout
        emit(
            {
                "bridge": BRIDGE_NAME,
                "bridge_version": BRIDGE_VERSION,
                "command": command,
                "ok": False,
                "result": None,
                "error": {"kind": "cancelled", "message": "Interrupted.", "hint": ""},
            },
            EXIT_INTERNAL,
            real_stdout,
        )
        return EXIT_INTERNAL
    except Exception as exc:  # noqa: BLE001 - last-resort structured reporting
        sys.stdout = real_stdout
        envelope = {
            "bridge": BRIDGE_NAME,
            "bridge_version": BRIDGE_VERSION,
            "command": command,
            "ok": False,
            "result": None,
            "error": {
                "kind": "internal_error",
                "message": f"{type(exc).__name__}: {exc}",
                "hint": "See the extension output channel for the traceback (stderr).",
            },
            "python": python_facts(),
        }
        emit(envelope, EXIT_INTERNAL, real_stdout)
        traceback.print_exc(file=sys.stderr)
        return EXIT_INTERNAL
    finally:
        sys.stdout = real_stdout


if __name__ == "__main__":
    raise SystemExit(main())
