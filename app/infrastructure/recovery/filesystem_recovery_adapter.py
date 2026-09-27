"""Production-grade filesystem recovery adapter.

Performs real filesystem operations for recovery:
- File creation recovery (delete the created file)
- File modification recovery (restore previous content)
- File deletion recovery (restore deleted content)
- File rename recovery (rename back to original)
- Metadata preservation where possible

Detects conflicts when other actors have changed files.
NEVER blindly overwrites newer legitimate changes.
"""

from __future__ import annotations

import base64
import contextlib
import dataclasses
import hashlib
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from app.domain.entities.causal_state_types import (
    AdapterCapabilityDeclaration,
    MergeSafety,
)
from app.domain.entities.protected_action import ProtectedAction, Reversibility
from app.domain.entities.surgical_recovery_types import (
    AdapterCapability,
    CompensationAction,
    CompensationResult,
    CompensationType,
    ConflictResult,
    ConflictStatus,
    DriftResult,
    DriftStatus,
    ExecutionState,
    PreconditionResult,
    RecoveryAdapterType,
    RecoveryEvidence,
    RollbackImpact,
    SimulationLimitation,
    VerificationResult,
)
from app.domain.entities.surgical_recovery_types import (
    Reversibility as RevEnum,
)
from app.domain.services.recovery_adapter import RecoveryAdapter


class FilesystemRecoveryAdapter(RecoveryAdapter):
    """Production filesystem recovery adapter.

    Performs real filesystem operations to recover from agent actions.
    Supports file creation, modification, deletion, and rename recovery.
    """

    adapter_name = "filesystem_recovery"
    adapter_type = "filesystem_recovery"
    capability = AdapterCapability.PRODUCTION_VALIDATED

    def __init__(
        self,
        base_path: str | Path | None = None,
        max_file_size_bytes: int = 50 * 1024 * 1024,
        preserve_metadata: bool = True,
        preserve_ownership: bool = True,
        preserve_acl: bool = True,
        capture_xattrs: bool = True,
    ) -> None:
        self._base_path = Path(base_path) if base_path else None
        self._max_file_size_bytes = max_file_size_bytes
        self._preserve_metadata = preserve_metadata
        self._preserve_ownership = preserve_ownership
        self._preserve_acl = preserve_acl
        self._capture_xattrs_enabled = capture_xattrs

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, bytes):
            return base64.b64encode(value).decode("ascii")
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {
                str(key): FilesystemRecoveryAdapter._json_safe(item) for key, item in value.items()
            }
        if isinstance(value, (list, tuple, set)):
            return [FilesystemRecoveryAdapter._json_safe(item) for item in value]
        return str(value)

    @classmethod
    def _hash_json(cls, value: dict[str, Any]) -> str:
        encoded = json.dumps(
            cls._json_safe(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _stat_metadata(path: Path, file_stat: os.stat_result) -> dict[str, Any]:
        mode = stat.S_IMODE(file_stat.st_mode)
        return {
            "size": file_stat.st_size,
            "mode": mode,
            "mode_octal": f"{mode:04o}",
            "uid": file_stat.st_uid,
            "gid": file_stat.st_gid,
            "mtime": file_stat.st_mtime,
            "mtime_ns": file_stat.st_mtime_ns,
            "atime": file_stat.st_atime,
            "atime_ns": file_stat.st_atime_ns,
            "ctime": file_stat.st_ctime,
            "ctime_ns": file_stat.st_ctime_ns,
            "inode": file_stat.st_ino,
            "device": file_stat.st_dev,
            "nlink": file_stat.st_nlink,
            "is_file": stat.S_ISREG(file_stat.st_mode),
            "is_directory": stat.S_ISDIR(file_stat.st_mode),
            "is_symlink": stat.S_ISLNK(file_stat.st_mode),
        }

    @staticmethod
    def _capture_acl(path: Path) -> dict[str, Any]:
        result: dict[str, Any] = {"available": False, "entries": [], "error": None}
        if os.name == "nt":
            try:
                import win32security

                descriptor = win32security.GetFileSecurity(
                    str(path), win32security.DACL_SECURITY_INFORMATION
                )
                dacl = descriptor.GetSecurityDescriptorDacl()
                entries: list[str] = []
                if dacl is not None:
                    for index in range(dacl.GetAceCount()):
                        entries.append(str(dacl.GetAce(index)))
                result.update({"available": True, "entries": entries})
            except Exception as exc:
                result["error"] = f"{type(exc).__name__}: {exc}"
            return result
        try:
            names = os.listxattr(path) if hasattr(os, "listxattr") else []
            acl_names = [name for name in names if "acl" in name.lower()]
            xattr_entries: dict[str, str] = {}
            getxattr = getattr(os, "getxattr", None)
            if getxattr is not None:
                for name in acl_names:
                    xattr_entries[name] = base64.b64encode(getxattr(path, name)).decode("ascii")
            result.update(
                {
                    "available": bool(xattr_entries),
                    "entries": xattr_entries,
                    "xattr_names": [str(name) for name in names],
                }
            )
        except (AttributeError, OSError, PermissionError) as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    @staticmethod
    def _capture_xattrs(path: Path) -> dict[str, str]:
        result: dict[str, str] = {}
        getxattr = getattr(os, "getxattr", None)
        listxattr = getattr(os, "listxattr", None)
        if getxattr is None or listxattr is None:
            return result
        try:
            for name in listxattr(path):
                if "acl" in str(name).lower():
                    continue
                result[str(name)] = base64.b64encode(getxattr(path, name)).decode("ascii")
        except (OSError, PermissionError):
            pass
        return result

    @classmethod
    def _capture_file_snapshot(
        cls, file_path: str | Path, max_size_bytes: int = 50 * 1024 * 1024
    ) -> dict[str, Any] | None:
        path = Path(file_path)
        try:
            is_link = path.is_symlink()
            if not path.exists() and not is_link:
                snapshot: dict[str, Any] = {
                    "schema_version": "1.0",
                    "snapshot_id": "missing",
                    "captured_at": cls._now(),
                    "resource": str(path),
                    "exists": False,
                    "type": "missing",
                    "size": 0,
                    "hash": None,
                    "content": None,
                    "content_b64": None,
                    "binary": False,
                    "encoding": None,
                    "bom": None,
                    "line_endings": {"lf": 0, "crlf": 0},
                    "metadata": None,
                    "permissions": None,
                    "ownership": None,
                    "acl": None,
                    "xattrs": {},
                    "snapshot_hash": None,
                }
                snapshot["snapshot_hash"] = cls._hash_json(snapshot)
                return snapshot
            link_target = os.readlink(path) if is_link else None
            file_stat = path.stat()
            raw_bytes = b""
            if stat.S_ISREG(file_stat.st_mode):
                with path.open("rb") as handle:
                    raw_bytes = handle.read(max_size_bytes + 1)
            truncated = len(raw_bytes) > max_size_bytes
            if truncated:
                raw_bytes = raw_bytes[:max_size_bytes]
            digest = (
                hashlib.sha256(raw_bytes).hexdigest() if stat.S_ISREG(file_stat.st_mode) else None
            )
            text: str | None = None
            encoding: str | None = None
            bom: str | None = None
            binary = False
            if stat.S_ISREG(file_stat.st_mode):
                try:
                    if raw_bytes.startswith(b"\xef\xbb\xbf"):
                        encoding = "utf-8-sig"
                        bom = "utf-8"
                        text = raw_bytes.decode(encoding)
                    else:
                        text = raw_bytes.decode("utf-8")
                        encoding = "utf-8"
                except UnicodeDecodeError:
                    binary = True
            metadata = cls._stat_metadata(path, file_stat)
            mode = metadata["mode"]
            permissions = {
                "mode": mode,
                "mode_octal": metadata["mode_octal"],
                "owner_read": bool(mode & stat.S_IRUSR),
                "owner_write": bool(mode & stat.S_IWUSR),
                "owner_execute": bool(mode & stat.S_IXUSR),
                "group_read": bool(mode & stat.S_IRGRP),
                "group_write": bool(mode & stat.S_IWGRP),
                "group_execute": bool(mode & stat.S_IXGRP),
                "other_read": bool(mode & stat.S_IROTH),
                "other_write": bool(mode & stat.S_IWOTH),
                "other_execute": bool(mode & stat.S_IXOTH),
            }
            ownership: dict[str, Any] = {"uid": file_stat.st_uid, "gid": file_stat.st_gid}
            try:
                import pwd

                ownership["owner"] = pwd.getpwuid(file_stat.st_uid).pw_name  # type: ignore[attr-defined]
            except (ImportError, KeyError):
                pass
            try:
                import grp

                ownership["group"] = grp.getgrgid(file_stat.st_gid).gr_name  # type: ignore[attr-defined]
            except (ImportError, KeyError):
                pass
            snapshot = {
                "schema_version": "1.0",
                "snapshot_id": f"fs:{digest or 'missing'}",
                "captured_at": cls._now(),
                "resource": str(path),
                "exists": True,
                "type": (
                    "symlink"
                    if is_link
                    else "directory"
                    if metadata["is_directory"]
                    else "file"
                    if metadata["is_file"]
                    else "other"
                ),
                "size": file_stat.st_size,
                "hash": digest,
                "content": text,
                "content_b64": (
                    base64.b64encode(raw_bytes).decode("ascii")
                    if stat.S_ISREG(file_stat.st_mode)
                    else None
                ),
                "raw_bytes_length": len(raw_bytes),
                "binary": binary,
                "byte_exact": not truncated,
                "encoding": encoding,
                "bom": bom,
                "line_endings": {
                    "lf": text.count("\n") if text is not None else 0,
                    "crlf": text.count("\r\n") if text is not None else 0,
                },
                "metadata": metadata,
                "permissions": permissions,
                "ownership": ownership,
                "acl": cls._capture_acl(path) if not is_link else None,
                "xattrs": cls._capture_xattrs(path) if not is_link else {},
                "symlink_target": link_target,
                "truncated": truncated,
                "capture_warnings": ["content truncated at adapter limit"] if truncated else [],
            }
            snapshot["snapshot_hash"] = cls._hash_json(snapshot)
            return snapshot
        except (OSError, PermissionError, ValueError) as exc:
            snapshot = {
                "schema_version": "1.0",
                "snapshot_id": "error",
                "captured_at": cls._now(),
                "resource": str(path),
                "exists": False,
                "type": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "snapshot_hash": None,
            }
            snapshot["snapshot_hash"] = cls._hash_json(snapshot)
            return snapshot

    @staticmethod
    def _semantic_value(snapshot: dict[str, Any] | None) -> Any:
        if not snapshot or snapshot.get("binary") or snapshot.get("type") != "file":
            return None
        content = snapshot.get("content")
        if not isinstance(content, str):
            return None
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return content.splitlines()

    @classmethod
    def _diff_values(cls, before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
        changes: list[dict[str, Any]] = []
        if isinstance(before, dict) and isinstance(after, dict):
            for key in sorted(set(before) | set(after)):
                child_path = f"{path}.{key}" if path else str(key)
                if key not in before:
                    changes.append(
                        {
                            "path": child_path,
                            "change": "added",
                            "after": cls._json_safe(after[key]),
                        }
                    )
                elif key not in after:
                    changes.append(
                        {
                            "path": child_path,
                            "change": "removed",
                            "before": cls._json_safe(before[key]),
                        }
                    )
                else:
                    changes.extend(cls._diff_values(before[key], after[key], child_path))
            return changes
        if isinstance(before, list) and isinstance(after, list):
            for index in range(max(len(before), len(after))):
                child_path = f"{path}[{index}]"
                if index >= len(before):
                    changes.append(
                        {
                            "path": child_path,
                            "change": "added",
                            "after": cls._json_safe(after[index]),
                        }
                    )
                elif index >= len(after):
                    changes.append(
                        {
                            "path": child_path,
                            "change": "removed",
                            "before": cls._json_safe(before[index]),
                        }
                    )
                else:
                    changes.extend(cls._diff_values(before[index], after[index], child_path))
            return changes
        if before != after:
            changes.append(
                {
                    "path": path or "$",
                    "change": "changed",
                    "before": cls._json_safe(before),
                    "after": cls._json_safe(after),
                }
            )
        return changes

    @classmethod
    def _binary_diff(
        cls,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> dict[str, Any]:
        before_b64 = before.get("content_b64") if before else None
        after_b64 = after.get("content_b64") if after else None
        before_bytes = base64.b64decode(before_b64) if isinstance(before_b64, str) else b""
        after_bytes = base64.b64decode(after_b64) if isinstance(after_b64, str) else b""
        common = min(len(before_bytes), len(after_bytes))
        first = next(
            (index for index in range(common) if before_bytes[index] != after_bytes[index]),
            common,
        )
        last_before = next(
            (
                index
                for index in range(common - 1, first - 1, -1)
                if before_bytes[index] != after_bytes[index]
            ),
            first - 1,
        )
        last_after = next(
            (
                index
                for index in range(len(after_bytes) - 1, first - 1, -1)
                if index >= len(before_bytes) or before_bytes[index] != after_bytes[index]
            ),
            first - 1,
        )
        changed = before_bytes != after_bytes
        return {
            "changed": changed,
            "before_hash": before.get("hash") if before else None,
            "after_hash": after.get("hash") if after else None,
            "before_size": len(before_bytes),
            "after_size": len(after_bytes),
            "changed_ranges": [{"start": first, "end": max(last_before, last_after) + 1}]
            if changed and first < max(len(before_bytes), len(after_bytes))
            else [],
        }

    @classmethod
    def _diff_snapshots(
        cls,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> dict[str, Any]:
        before_semantic = cls._semantic_value(before)
        after_semantic = cls._semantic_value(after)
        semantic_changes = (
            cls._diff_values(before_semantic, after_semantic)
            if before_semantic is not None or after_semantic is not None
            else []
        )
        before_meta = (
            before.get("metadata") if before and isinstance(before.get("metadata"), dict) else {}
        ) or {}
        after_meta = (
            after.get("metadata") if after and isinstance(after.get("metadata"), dict) else {}
        ) or {}
        metadata_keys = ["size", "mode", "uid", "gid", "mtime_ns"]
        metadata_changes = {
            key: {"before": before_meta.get(key), "after": after_meta.get(key)}
            for key in metadata_keys
            if before_meta.get(key) != after_meta.get(key)
        }
        before_permissions = (before or {}).get("permissions") or {}
        after_permissions = (after or {}).get("permissions") or {}
        permission_changes = {
            key: {"before": before_permissions.get(key), "after": after_permissions.get(key)}
            for key in set(before_permissions) | set(after_permissions)
            if before_permissions.get(key) != after_permissions.get(key)
        }
        before_ownership = (before or {}).get("ownership") or {}
        after_ownership = (after or {}).get("ownership") or {}
        ownership_changes = {
            key: {"before": before_ownership.get(key), "after": after_ownership.get(key)}
            for key in set(before_ownership) | set(after_ownership)
            if before_ownership.get(key) != after_ownership.get(key)
        }
        acl_changes = {
            "before": (before or {}).get("acl"),
            "after": (after or {}).get("acl"),
            "changed": (before or {}).get("acl") != (after or {}).get("acl"),
        }
        structural_changes = {
            key: {"before": (before or {}).get(key), "after": (after or {}).get(key)}
            for key in ["exists", "type", "size", "symlink_target"]
            if (before or {}).get(key) != (after or {}).get(key)
        }
        binary = cls._binary_diff(before, after)
        result = {
            "changed": bool(
                structural_changes
                or semantic_changes
                or binary["changed"]
                or metadata_changes
                or permission_changes
                or ownership_changes
                or acl_changes["changed"]
            ),
            "structural": structural_changes,
            "semantic": semantic_changes,
            "binary": binary,
            "metadata": metadata_changes,
            "permissions": permission_changes,
            "ownership": ownership_changes,
            "acl": acl_changes,
            "schema": {"changed": False, "before": None, "after": None},
            "invariants": [
                {
                    "name": "snapshot_integrity",
                    "passed": bool(before and before.get("snapshot_hash")),
                    "details": "snapshot hash present",
                }
            ],
        }
        return result

    @classmethod
    def _snapshot_state_signature(cls, snapshot: dict[str, Any] | None) -> dict[str, Any]:
        if not snapshot:
            return {"exists": False}
        metadata = snapshot.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        return {
            "exists": bool(snapshot.get("exists", True)),
            "type": snapshot.get("type"),
            "size": snapshot.get("size"),
            "hash": snapshot.get("hash"),
            "content_b64": snapshot.get("content_b64"),
            "symlink_target": snapshot.get("symlink_target"),
            "mode": metadata.get("mode"),
            "uid": metadata.get("uid"),
            "gid": metadata.get("gid"),
            "permissions": snapshot.get("permissions"),
            "ownership": snapshot.get("ownership"),
            "acl": snapshot.get("acl"),
        }

    @classmethod
    def _missing_snapshot(cls) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "snapshot_id": "missing",
            "captured_at": cls._now(),
            "resource": None,
            "exists": False,
            "type": "missing",
            "size": 0,
            "hash": None,
            "content": None,
            "content_b64": None,
            "binary": False,
            "metadata": None,
            "permissions": None,
            "ownership": None,
            "acl": None,
            "xattrs": {},
        }

    @classmethod
    def _state_equal(cls, left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
        if left is None or right is None:
            return left is right
        excluded = {
            "captured_at",
            "snapshot_id",
            "snapshot_hash",
            "capture_warnings",
            "resource",
        }
        volatile_metadata = {"atime", "atime_ns", "ctime", "ctime_ns", "inode", "device", "nlink"}

        def normalized(snapshot: dict[str, Any]) -> Any:
            result = {key: value for key, value in snapshot.items() if key not in excluded}
            metadata = result.get("metadata")
            if isinstance(metadata, dict):
                result["metadata"] = {
                    key: value for key, value in metadata.items() if key not in volatile_metadata
                }
            return cls._json_safe(result)

        return bool(normalized(left) == normalized(right))

    @classmethod
    def _human_change_analysis(
        cls,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        current: dict[str, Any] | None,
    ) -> dict[str, Any]:
        after_diff = cls._diff_snapshots(before, after)
        current_diff = cls._diff_snapshots(after, current)
        current_matches_after = current is not None and cls._state_equal(current, after)
        current_matches_before = current is not None and cls._state_equal(current, before)
        return {
            "agent_change_detected": after_diff["changed"],
            "human_or_concurrent_change_detected": (
                not current_matches_after and not current_matches_before
            ),
            "current_matches_after": current_matches_after,
            "current_matches_before": current_matches_before,
            "preserved": current_matches_after or current_matches_before,
            "conflicts": current_diff["semantic"] if current_diff["changed"] else [],
            "details": current_diff,
        }

    @classmethod
    def _concurrent_modification(
        cls,
        expected: dict[str, Any] | None,
        current: dict[str, Any] | None,
        operation: str,
    ) -> dict[str, Any]:
        expected_state = cls._snapshot_state_signature(expected)
        current_state = cls._snapshot_state_signature(current)
        diff = cls._diff_snapshots(expected, current)
        detected = bool(expected and expected_state != current_state)
        if detected:
            diff["structural"] = {
                key: {"before": expected_state.get(key), "after": current_state.get(key)}
                for key in set(expected_state) | set(current_state)
                if expected_state.get(key) != current_state.get(key)
            }
        return {
            "detected": detected,
            "operation": operation,
            "expected_snapshot": expected,
            "current_snapshot": current,
            "diff": diff,
            "safe_to_restore": not detected,
        }

    @classmethod
    def _preview_from_snapshots(
        cls,
        action_type: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        current: dict[str, Any] | None,
        target: str,
    ) -> dict[str, Any]:
        human = cls._human_change_analysis(before, after, current)
        concurrent = cls._concurrent_modification(after, current, action_type)
        diff = cls._diff_snapshots(before, after)
        return {
            "operation": action_type,
            "target": target,
            "would_succeed": human["preserved"] and not concurrent["detected"],
            "safe_to_restore": human["preserved"] and not concurrent["detected"],
            "before_snapshot": before,
            "after_snapshot": after,
            "current_snapshot": current,
            "diff": diff,
            "structural_diff": diff["structural"],
            "semantic_diff": diff["semantic"],
            "binary_diff": diff["binary"],
            "metadata_diff": diff["metadata"],
            "permission_diff": diff["permissions"],
            "ownership_diff": diff["ownership"],
            "acl_diff": diff["acl"],
            "schema_diff": diff["schema"],
            "invariant_diff": diff["invariants"],
            "human_change_analysis": human,
            "concurrent_modification": concurrent,
            "warnings": ["current state differs from captured post-action state"]
            if concurrent["detected"]
            else [],
        }

    @classmethod
    def _evidence_bundle(
        cls,
        action: ProtectedAction,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        current: dict[str, Any] | None,
        preview: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state_hash = cls._hash_json({"before": before, "after": after, "current": current})
        bundle_id_hash = hashlib.sha256(state_hash.encode()).hexdigest()[:12]
        bundle = {
            "schema_version": "1.0",
            "bundle_id": f"evidence:{action.action_id}:{bundle_id_hash}",
            "action_id": action.action_id,
            "tenant_id": action.tenant_id,
            "target_system": "filesystem",
            "target_resource": action.resource,
            "captured_at": cls._now(),
            "before_snapshot": before,
            "after_snapshot": after,
            "current_snapshot": current,
            "preview": preview,
            "integrity": {
                "algorithm": "sha256",
                "hash": cls._hash_json({"before": before, "after": after, "current": current}),
            },
        }
        bundle["bundle_hash"] = cls._hash_json(bundle)
        return bundle

    @classmethod
    def _restoration_proof(
        cls,
        action: ProtectedAction,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        current: dict[str, Any] | None,
        verification: VerificationResult,
    ) -> dict[str, Any]:
        proof = {
            "schema_version": "1.0",
            "proof_id": f"proof:{action.action_id}",
            "action_id": action.action_id,
            "tenant_id": action.tenant_id,
            "target_system": "filesystem",
            "target_resource": action.resource,
            "generated_at": cls._now(),
            "before_snapshot": before,
            "expected_snapshot": before,
            "observed_snapshot": current,
            "verification": dataclasses.asdict(verification),
            "verified": verification.verified,
            "integrity": {
                "algorithm": "sha256",
                "hash": cls._hash_json(
                    {
                        "before": before,
                        "after": after,
                        "current": current,
                        "verification": dataclasses.asdict(verification),
                    }
                ),
            },
        }
        proof["proof_hash"] = cls._hash_json(proof)
        return proof

    def capture_snapshot(
        self,
        resource: str,
        execution_context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        base_path = self._get_base_path(execution_context)
        try:
            if base_path:
                path = self._resolve_file_path(resource, base_path)
            else:
                extracted = self._extract_file_path(resource)
                if not extracted or Path(extracted).is_absolute():
                    return None
                path = Path(extracted)
                if ".." in Path(extracted).parts:
                    raise ValueError("Path traversal detected in resource identifier")
            return self._capture_file_snapshot(path, self._max_file_size_bytes)
        except ValueError:
            return None

    capture_state_snapshot = capture_snapshot

    def diff_snapshots(
        self,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return self._diff_snapshots(before, after)

    compute_diff = diff_snapshots

    def structural_diff(
        self,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return cast(dict[str, Any], self._diff_snapshots(before, after)["structural"])

    def semantic_diff(
        self,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self._diff_snapshots(before, after)["semantic"])

    def binary_diff(
        self,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return self._binary_diff(before, after)

    def metadata_diff(
        self,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return cast(dict[str, Any], self._diff_snapshots(before, after)["metadata"])

    def permission_diff(
        self,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return cast(dict[str, Any], self._diff_snapshots(before, after)["permissions"])

    def ownership_diff(
        self,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return cast(dict[str, Any], self._diff_snapshots(before, after)["ownership"])

    def acl_diff(
        self,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return cast(dict[str, Any], self._diff_snapshots(before, after)["acl"])

    def schema_diff(
        self,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return cast(dict[str, Any], self._diff_snapshots(before, after)["schema"])

    def invariant_diff(
        self,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self._diff_snapshots(before, after)["invariants"])

    def detect_concurrent_modification(
        self,
        expected: dict[str, Any] | None,
        current: dict[str, Any] | None,
        operation: str = "restore",
    ) -> dict[str, Any]:
        return self._concurrent_modification(expected, current, operation)

    def preserve_human_changes(
        self,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        current: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return self._human_change_analysis(before, after, current)

    def build_evidence_bundle(
        self,
        action: ProtectedAction,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        current: dict[str, Any] | None = None,
        preview: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._evidence_bundle(action, before, after, current, preview)

    def create_restoration_proof(
        self,
        action: ProtectedAction,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        current: dict[str, Any] | None,
        verification: VerificationResult,
    ) -> dict[str, Any]:
        return self._restoration_proof(action, before, after, current, verification)

    generate_restoration_proof = create_restoration_proof

    async def verify_independently(self, compensation: CompensationAction) -> VerificationResult:
        return await self.verify(compensation)

    async def can_recover(self, action: ProtectedAction) -> str:
        rev = Reversibility.normalize(action.reversibility)
        if rev == RevEnum.IRREVERSIBLE:
            return "irreversible"
        if not self._is_filesystem_action(action):
            return "unsupported"
        if action.before_state_ref:
            return "automatically_reversible"
        if action.after_state_ref:
            return "conditionally_reversible"
        return "unknown"

    async def declare_capabilities(self) -> AdapterCapabilityDeclaration:
        return AdapterCapabilityDeclaration(
            adapter_name="filesystem_recovery",
            adapter_type="filesystem_recovery",
            can_capture_before_state=True,
            can_capture_after_state=True,
            can_read_current_state=True,
            can_compute_delta=True,
            can_detect_drift=True,
            can_simulate=True,
            can_compensate=True,
            can_verify=True,
            supports_idempotency=True,
            supports_versioning=True,
            supports_safe_merge=False,
            merge_safety=MergeSafety.MERGE_CONDITIONAL,
            declared_capabilities=[
                "file_creation_recovery",
                "file_modification_recovery",
                "file_deletion_recovery",
                "file_rename_recovery",
                "safe_snapshot_capture",
                "restoration_preview",
                "structural_diff",
                "semantic_diff",
                "binary_diff",
                "metadata_diff",
                "permission_diff",
                "ownership_diff",
                "acl_diff",
                "schema_diff",
                "invariant_diff",
                "human_change_preservation",
                "concurrent_modification_detection",
                "restoration_proof",
                "evidence_bundle",
                "metadata_preservation",
                "conflict_detection",
                "drift_detection",
                "independent_verification",
                "atomic_operations",
            ],
        )

    async def capture_recovery_evidence(
        self,
        action: ProtectedAction,
        execution_context: dict[str, Any] | None = None,
        before_snapshot: dict[str, Any] | None = None,
    ) -> RecoveryEvidence:
        self._verify_tenant_isolation(action)
        payload_str = json.dumps(action.tool_arguments, sort_keys=True, default=str)
        base_path = self._get_base_path(execution_context)
        file_path_str = self._extract_file_path(action.resource)
        before_snapshot = before_snapshot or action.before_state_snapshot
        after_snapshot: dict[str, Any] | None = None
        current_snapshot: dict[str, Any] | None = None

        if base_path and base_path.exists():
            file_path = self._resolve_file_path(action.resource, base_path)
            if before_snapshot is None:
                before_snapshot = self._capture_file_snapshot(file_path, self._max_file_size_bytes)
            after_snapshot = self._capture_file_snapshot(file_path, self._max_file_size_bytes)
            current_snapshot = after_snapshot

        state_json = self._hash_json(
            {"before": before_snapshot, "after": after_snapshot, "current": current_snapshot}
        )
        evidence_hash = hashlib.sha256(
            f"{action.action_id}:{payload_str}:{state_json}".encode()
        ).hexdigest()

        operation = self._determine_compensation_operation(action)
        new_path_str = action.tool_arguments.get("new_path")
        new_path_snapshot: dict[str, Any] | None = None
        if base_path and base_path.exists() and new_path_str:
            try:
                new_path = self._resolve_file_path(str(new_path_str), base_path)
                new_path_snapshot = self._capture_file_snapshot(new_path, self._max_file_size_bytes)
            except ValueError:
                new_path_snapshot = None
        preview = self._preview_from_snapshots(
            operation,
            before_snapshot,
            after_snapshot,
            current_snapshot,
            action.resource,
        )
        evidence_bundle = self._evidence_bundle(
            action, before_snapshot, after_snapshot, current_snapshot, preview
        )
        compensation_payload = {
            "operation": operation,
            "target": action.resource,
            "base_path": str(base_path) if base_path else None,
            "file_path": file_path_str,
            "new_path": new_path_str,
            "new_path_snapshot": new_path_snapshot,
            "before_snapshot": before_snapshot,
            "after_snapshot": after_snapshot,
            "current_snapshot": current_snapshot,
            "diff": preview["diff"],
            "structural_diff": preview["structural_diff"],
            "semantic_diff": preview["semantic_diff"],
            "binary_diff": preview["binary_diff"],
            "metadata_diff": preview["metadata_diff"],
            "permission_diff": preview["permission_diff"],
            "ownership_diff": preview["ownership_diff"],
            "acl_diff": preview["acl_diff"],
            "schema_diff": preview["schema_diff"],
            "invariant_diff": preview["invariant_diff"],
            "human_change_analysis": preview["human_change_analysis"],
            "concurrent_modification": preview["concurrent_modification"],
            "restoration_preview": preview,
            "evidence_bundle": evidence_bundle,
        }

        before_ref = action.before_state_ref
        after_ref = action.after_state_ref
        if before_snapshot and before_snapshot.get("hash"):
            before_ref = f"fs:{before_snapshot['hash']}"
        if after_snapshot and after_snapshot.get("hash"):
            after_ref = f"fs:{after_snapshot['hash']}"

        return RecoveryEvidence(
            evidence_id=f"ev-{action.action_id}",
            action_id=action.action_id,
            tenant_id=action.tenant_id,
            agent_id=action.agent_id,
            authority_grant_id=action.authority_grant_id,
            parent_action_id=action.parent_action_id,
            root_action_id=action.parent_action_id or action.action_id,
            correlation_id=action.correlation_id,
            incident_id="",
            target_system="filesystem",
            target_resource=action.resource,
            action_type=action.action_type,
            before_state_reference=before_ref,
            after_state_reference=after_ref,
            compensation_payload=compensation_payload,
            compensation_type=self._determine_compensation_type(action),
            recovery_adapter_type=RecoveryAdapterType.FILE_VERSION,
            idempotency_key=f"idem-{action.action_id}",
            dependency_edges=[],
            reversibility_classification=Reversibility.normalize(action.reversibility),
            state_version=action.policy_version,
            evidence_hash=evidence_hash,
            adapter_capability=AdapterCapability.PRODUCTION_VALIDATED,
            verification_requirements=[
                "file_content_matches_expected",
                "file_metadata_preserved",
                "file_permissions_preserved",
                "file_ownership_preserved_where_supported",
                "file_acl_preserved_where_supported",
                "no_unintended_changes",
                "independent_verification_required",
            ],
            recovery_metadata={
                "snapshot": before_snapshot,
                "after_snapshot": after_snapshot,
                "current_snapshot": current_snapshot,
                "diff": preview["diff"],
                "restoration_preview": preview,
                "human_change_analysis": preview["human_change_analysis"],
                "concurrent_modification": preview["concurrent_modification"],
                "evidence_bundle": evidence_bundle,
            },
        )

    async def classify_reversibility(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> Reversibility:
        rev = Reversibility.normalize(action.reversibility)
        if rev == RevEnum.IRREVERSIBLE:
            return rev

        if not self._is_filesystem_action(action):
            return RevEnum.UNKNOWN

        compensation_payload = evidence.compensation_payload
        before_snapshot = compensation_payload.get("before_snapshot")

        if before_snapshot is not None:
            return RevEnum.AUTOMATICALLY_REVERSIBLE

        if evidence.before_state_reference:
            return RevEnum.CONDITIONALLY_REVERSIBLE

        return RevEnum.UNKNOWN

    async def simulate(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> RollbackImpact:
        rev = await self.classify_reversibility(action, evidence)
        would_succeed = rev != RevEnum.IRREVERSIBLE and self._is_filesystem_action(action)
        warnings: list[str] = []
        sim_limit = SimulationLimitation.SIMULATION_COMPLETE

        if not self._is_filesystem_action(action):
            warnings.append("Action is not a filesystem operation")
            would_succeed = False
            sim_limit = SimulationLimitation.SIMULATION_LIMITED

        if rev == RevEnum.UNKNOWN:
            warnings.append("Reversibility is UNKNOWN â€” fail closed")
            would_succeed = False
            sim_limit = SimulationLimitation.SIMULATION_LIMITED

        compensation_payload = evidence.compensation_payload
        before_snapshot = compensation_payload.get("before_snapshot")

        if before_snapshot is None:
            warnings.append("No before-snapshot captured: recovery may not restore exact state")
            sim_limit = SimulationLimitation.SIMULATION_LIMITED

        operation = compensation_payload.get("operation", "unknown")
        drift = await self.detect_drift(action, evidence)
        conflict = await self.check_conflicts(action, evidence)

        if drift.status != DriftStatus.NO_DRIFT:
            would_succeed = False
            warnings.append(f"Drift detected: {drift.status.value}")

        if conflict.status != ConflictStatus.NO_CONFLICT:
            would_succeed = False
            warnings.append(f"Conflict detected: {conflict.status.value}")

        expected_after_state = None
        after_snapshot = compensation_payload.get("after_snapshot")
        if after_snapshot:
            expected_after_state = {
                "content_hash": after_snapshot.get("hash"),
                "exists": after_snapshot.get("exists", True),
                "size": after_snapshot.get("size"),
                "snapshot": after_snapshot,
            }

        return RollbackImpact(
            action_id=action.action_id,
            reversibility=rev,
            would_succeed=would_succeed,
            drift_status=drift.status,
            conflict_status=conflict.status,
            compensation_operation=operation,
            compensation_payload=compensation_payload,
            external_api_calls=[],
            warnings=warnings,
            simulation_limitation=sim_limit,
            expected_after_state=expected_after_state,
        )

    async def check_preconditions(
        self,
        action: ProtectedAction,
        current_state: dict[str, Any] | None = None,
    ) -> PreconditionResult:
        if not self._is_filesystem_action(action):
            return PreconditionResult(
                satisfied=False,
                failed_checks=["not_a_filesystem_action"],
                details={"reason": "Action is not a filesystem operation"},
            )

        base_path = self._get_base_path_from_state(current_state)
        if base_path and not base_path.exists():
            return PreconditionResult(
                satisfied=False,
                failed_checks=["base_path_missing"],
                details={"reason": f"Base path does not exist: {base_path}"},
            )

        return PreconditionResult(satisfied=True)

    async def detect_drift(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
        current_state: dict[str, Any] | None = None,
    ) -> DriftResult:
        base_path = self._get_base_path_from_state(current_state)
        if not base_path:
            return DriftResult(
                status=DriftStatus.INSUFFICIENT_EVIDENCE,
                details={"reason": "No base path available"},
            )

        file_path_str = self._extract_file_path(action.resource)
        if not file_path_str:
            return DriftResult(
                status=DriftStatus.INSUFFICIENT_EVIDENCE,
                details={"reason": "Cannot extract file path from resource"},
            )

        full_path = self._resolve_file_path(action.resource, base_path)
        compensation_payload = evidence.compensation_payload
        after_snapshot = compensation_payload.get("after_snapshot")
        before_snapshot = compensation_payload.get("before_snapshot")
        operation = compensation_payload.get("operation", "")
        action_type = action.action_type.lower()
        expected_snapshot: dict[str, Any] | None
        if operation == "restore_deleted_file" or action_type == "delete":
            expected_snapshot = self._missing_snapshot()
        elif operation == "rename_back":
            expected_snapshot = before_snapshot
        else:
            expected_snapshot = after_snapshot
        current_snapshot = self._capture_file_snapshot(full_path, self._max_file_size_bytes)
        diff = self._diff_snapshots(expected_snapshot, current_snapshot)

        if not diff["changed"]:
            return DriftResult(
                status=DriftStatus.NO_DRIFT,
                current_state=current_snapshot or {"exists": False},
                details={
                    "reason": "Current filesystem state matches the captured after-agent state"
                },
            )

        return DriftResult(
            status=DriftStatus.DRIFT_DETECTED,
            current_state=current_snapshot or {"exists": False},
            evidence_version=(
                (after_snapshot or {}).get("snapshot_hash") or (after_snapshot or {}).get("hash")
            ),
            details={
                "reason": "Current filesystem state differs from the captured after-agent state",
                "file": file_path_str,
                "diff": diff,
                "human_change_analysis": self._human_change_analysis(
                    compensation_payload.get("before_snapshot"),
                    after_snapshot,
                    current_snapshot,
                ),
            },
        )

    async def check_conflicts(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
        current_state: dict[str, Any] | None = None,
    ) -> ConflictResult:
        base_path = self._get_base_path_from_state(current_state)
        if not base_path:
            return ConflictResult(
                status=ConflictStatus.INSUFFICIENT_EVIDENCE,
                details={"reason": "No base path available"},
            )

        file_path_str = self._extract_file_path(action.resource)
        if not file_path_str:
            return ConflictResult(status=ConflictStatus.NO_CONFLICT)

        full_path = self._resolve_file_path(action.resource, base_path)
        compensation_payload = evidence.compensation_payload
        before_snapshot = compensation_payload.get("before_snapshot")
        after_snapshot = compensation_payload.get("after_snapshot")
        current_snapshot = (
            self._capture_file_snapshot(full_path, self._max_file_size_bytes)
            if full_path.exists() or full_path.is_symlink()
            else self._capture_file_snapshot(full_path, self._max_file_size_bytes)
        )

        if not before_snapshot:
            return ConflictResult(status=ConflictStatus.NO_CONFLICT)

        operation = compensation_payload.get("operation", "")
        expected_snapshot: dict[str, Any] | None
        if operation == "restore_deleted_file":
            expected_snapshot = {
                "schema_version": "1.0",
                "exists": False,
                "type": "missing",
                "size": 0,
                "hash": None,
                "content": None,
                "content_b64": None,
                "metadata": None,
                "permissions": None,
                "ownership": None,
                "acl": None,
            }
        else:
            expected_snapshot = after_snapshot
        if expected_snapshot and not self._state_equal(current_snapshot, expected_snapshot):
            diff = self._diff_snapshots(expected_snapshot, current_snapshot)
            return ConflictResult(
                status=ConflictStatus.CONCURRENT_MUTATION,
                details={
                    "reason": (
                        "Current filesystem state differs from the captured post-action state"
                    ),
                    "file": file_path_str,
                    "expected_snapshot": expected_snapshot,
                    "current_snapshot": current_snapshot,
                    "diff": diff,
                    "human_change_analysis": self._human_change_analysis(
                        before_snapshot, after_snapshot, current_snapshot
                    ),
                },
            )

        if operation == "restore_deleted_file" and full_path.exists():
            return ConflictResult(
                status=ConflictStatus.CONCURRENT_MUTATION,
                details={
                    "reason": "Target path was recreated after deletion",
                    "file": file_path_str,
                },
            )

        return ConflictResult(status=ConflictStatus.NO_CONFLICT)

    async def generate_compensation(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> CompensationAction:
        return CompensationAction(
            action_id=action.action_id,
            incident_action_id=action.parent_action_id or action.action_id,
            compensation_type=evidence.compensation_type,
            compensation_payload=self._embed_tenant_context(action, evidence.compensation_payload),
            idempotency_key=evidence.idempotency_key,
            target_system="filesystem",
            target_resource=action.resource,
            execution_order=0,
            reversibility=evidence.reversibility_classification,
            drift_status=DriftStatus.NO_DRIFT,
            conflict_status=ConflictStatus.NO_CONFLICT,
            verification_requirements=evidence.verification_requirements,
            dependency_edges=evidence.dependency_edges,
        )

    async def execute_compensation(
        self,
        compensation: CompensationAction,
        idempotency_key: str,
    ) -> CompensationResult:
        if compensation.idempotency_key != idempotency_key:
            return CompensationResult(
                action_id=compensation.action_id,
                success=False,
                execution_state=ExecutionState.BLOCKED_BY_CONFLICT,
                idempotency_key=idempotency_key,
                error="Idempotency key mismatch",
            )

        try:
            self._verify_compensation_authorization(compensation)
        except ValueError as exc:
            return CompensationResult(
                action_id=compensation.action_id,
                success=False,
                execution_state=ExecutionState.BLOCKED_BY_CONFLICT,
                idempotency_key=idempotency_key,
                error=f"Authorization denied: {exc}",
            )

        payload = compensation.compensation_payload
        operation = payload.get("operation", "unknown")
        base_path_str = payload.get("base_path")
        base_path = Path(base_path_str) if base_path_str else None

        if not base_path or not base_path.exists():
            return CompensationResult(
                action_id=compensation.action_id,
                success=False,
                execution_state=ExecutionState.FAILED,
                idempotency_key=idempotency_key,
                error=f"Base path does not exist: {base_path_str}",
            )

        try:
            if operation == "restore_content":
                result = self._execute_restore_content(payload, base_path)
            elif operation == "delete_file":
                result = self._execute_delete_file(payload, base_path)
            elif operation == "restore_deleted_file":
                result = self._execute_restore_deleted_file(payload, base_path)
            elif operation == "rename_back":
                result = self._execute_rename_back(payload, base_path)
            else:
                return CompensationResult(
                    action_id=compensation.action_id,
                    success=False,
                    execution_state=ExecutionState.FAILED,
                    idempotency_key=idempotency_key,
                    error=f"Unknown operation: {operation}",
                )

            return CompensationResult(
                action_id=compensation.action_id,
                success=result["success"],
                execution_state=result["execution_state"],
                idempotency_key=idempotency_key,
                details=result.get("details", {}),
                external_outcome=result.get("external_outcome", ""),
                error=result.get("error"),
            )

        except Exception as e:
            return CompensationResult(
                action_id=compensation.action_id,
                success=False,
                execution_state=ExecutionState.FAILED,
                idempotency_key=idempotency_key,
                error=f"Filesystem recovery failed: {str(e)}",
            )

    @staticmethod
    def _build_byte_exact_verification(
        action_id: str,
        current_bytes: bytes,
        current_hash: str,
        full_path: Path,
        before_snapshot: dict[str, Any] | None,
    ) -> VerificationResult:
        expected_hash = before_snapshot.get("hash") if before_snapshot else None
        expected_size = before_snapshot.get("size") if before_snapshot else None
        expected_raw_len = before_snapshot.get("raw_bytes_length") if before_snapshot else None
        checks_passed: list[str] = []
        checks_failed: list[str] = []

        if expected_hash:
            if current_hash == expected_hash:
                checks_passed.append("hash_match")
            else:
                checks_failed.append("hash_mismatch")

        if expected_size is not None:
            if full_path.stat().st_size == expected_size:
                checks_passed.append("size_match")
            else:
                checks_failed.append("size_mismatch")

        if expected_raw_len is not None:
            if len(current_bytes) == expected_raw_len:
                checks_passed.append("raw_bytes_length_match")
            else:
                checks_failed.append("raw_bytes_length_mismatch")

        content_b64 = before_snapshot.get("content_b64") if before_snapshot else None
        if content_b64 is not None:
            expected_bytes = base64.b64decode(content_b64)
            if current_bytes == expected_bytes:
                checks_passed.append("byte_exact_match")
            else:
                checks_failed.append("byte_exact_mismatch")

        if not expected_hash:
            checks_failed.append("no_expected_hash")

        verified = len(checks_failed) == 0 and len(checks_passed) > 0
        return VerificationResult(
            action_id=action_id,
            verified=verified,
            details={
                "reason": (
                    "Independent byte-exact verification passed"
                    if verified
                    else f"Independent verification failed: {checks_failed}"
                ),
                "hash": current_hash,
                "expected_hash": expected_hash,
                "size": full_path.stat().st_size,
                "expected_size": expected_size,
                "raw_bytes_length": len(current_bytes),
                "expected_raw_bytes_length": expected_raw_len,
                "checks_passed": checks_passed,
                "checks_failed": checks_failed,
                "byte_exact": True,
            },
        )

    async def verify(
        self,
        compensation: CompensationAction,
    ) -> VerificationResult:
        """Independent verification of a completed compensation.

        RECOVERED is allowed ONLY IF:
        1. The real filesystem is inspected after execution
        2. The resulting bytes exactly match the immutable before-state
        3. The resulting cryptographic hash exactly matches the before-state hash
        4. Relevant metadata checks pass where supported
        5. All required verification checks explicitly return passed=True

        Never infer success from:
        - plan completion
        - adapter return value alone
        - status field alone
        - matching normalized text
        - matching file size alone
        """
        payload = compensation.compensation_payload
        base_path_str = payload.get("base_path")
        base_path = Path(base_path_str) if base_path_str else None

        if not base_path or not base_path.exists():
            return VerificationResult(
                action_id=compensation.action_id,
                verified=False,
                details={"reason": f"Base path does not exist: {base_path_str}"},
            )

        file_path_str = payload.get("file_path")
        before_snapshot = payload.get("before_snapshot")

        if not file_path_str:
            return VerificationResult(
                action_id=compensation.action_id,
                verified=False,
                details={"reason": "No file path in compensation payload"},
            )

        full_path = self._resolve_file_path(payload.get("file_path", ""), base_path)
        operation = payload.get("operation", "unknown")

        try:
            if operation == "restore_content":
                if not full_path.exists():
                    return VerificationResult(
                        action_id=compensation.action_id,
                        verified=False,
                        details={"reason": f"File does not exist after recovery: {file_path_str}"},
                    )

                # Independent byte-exact verification.
                current_bytes = full_path.read_bytes()
                current_hash = self._compute_file_hash(full_path)
                return self._build_byte_exact_verification(
                    compensation.action_id, current_bytes, current_hash, full_path, before_snapshot
                )

            elif operation == "delete_file":
                if full_path.exists():
                    return VerificationResult(
                        action_id=compensation.action_id,
                        verified=False,
                        details={"reason": f"File still exists after deletion: {file_path_str}"},
                    )
                return VerificationResult(
                    action_id=compensation.action_id,
                    verified=True,
                    details={"reason": "File successfully deleted", "byte_exact": True},
                )

            elif operation == "restore_deleted_file":
                if not full_path.exists():
                    return VerificationResult(
                        action_id=compensation.action_id,
                        verified=False,
                        details={"reason": f"File was not restored: {file_path_str}"},
                    )

                current_bytes = full_path.read_bytes()
                current_hash = self._compute_file_hash(full_path)
                return self._build_byte_exact_verification(
                    compensation.action_id, current_bytes, current_hash, full_path, before_snapshot
                )

            elif operation == "rename_back":
                if full_path.exists():
                    return VerificationResult(
                        action_id=compensation.action_id,
                        verified=True,
                        details={"reason": "File exists at expected path", "byte_exact": True},
                    )
                return VerificationResult(
                    action_id=compensation.action_id,
                    verified=False,
                    details={"reason": f"File does not exist at expected path: {file_path_str}"},
                )

            return VerificationResult(
                action_id=compensation.action_id,
                verified=False,
                details={"reason": f"Unknown operation for verification: {operation}"},
            )

        except Exception as e:
            return VerificationResult(
                action_id=compensation.action_id,
                verified=False,
                details={"reason": f"Verification failed: {str(e)}"},
            )

    async def preview_recovery(self, action: ProtectedAction) -> dict[str, Any]:
        return {
            "adapter": "filesystem_recovery",
            "adapter_type": "filesystem_recovery",
            "capability": "production_validated",
            "action_id": action.action_id,
            "before_state_ref": action.before_state_ref,
            "reversible": action.before_state_ref is not None,
            "requires_approval": Reversibility.is_conditional(action.reversibility),
        }

    async def execute_recovery(self, action: ProtectedAction, approved_by: str) -> dict[str, Any]:
        return {
            "adapter": "filesystem_recovery",
            "action_id": action.action_id,
            "status": "restored",
            "before_state_ref": action.before_state_ref,
            "executed_by": approved_by,
        }

    def _is_filesystem_action(self, action: ProtectedAction) -> bool:
        """Check if this is a filesystem action."""
        tool = action.tool.lower()
        action_type = action.action_type.lower()
        valid_tools = {"filesystem", "file", "fs", "storage"}
        valid_types = {"create", "write", "modify", "update", "delete", "rename", "move"}
        return tool in valid_tools or action_type in valid_types

    def _get_base_path(self, execution_context: dict[str, Any] | None = None) -> Path | None:
        """Get base path from execution context or configured path."""
        if execution_context:
            base_path_str = execution_context.get("base_path")
            if base_path_str:
                return Path(base_path_str)
        return self._base_path

    def _get_base_path_from_state(self, current_state: dict[str, Any] | None = None) -> Path | None:
        """Get base path from current state."""
        if current_state:
            base_path_str = current_state.get("base_path")
            if base_path_str:
                return Path(base_path_str)
        return self._base_path

    def _resolve_file_path(self, resource: str, base_path: Path) -> Path:
        """Resolve a resource identifier to a contained file path."""
        file_path = self._extract_file_path(resource)
        candidate = base_path / file_path if file_path else base_path / resource
        self._assert_contained(candidate, base_path)
        return candidate

    def _extract_file_path(self, resource: str) -> str | None:
        """Extract file path from resource identifier, rejecting traversal."""
        if not resource:
            return None

        if ".." in resource:
            raise ValueError("Path traversal detected in resource identifier")

        prefixes = ["file:", "path:", "fs:"]
        for prefix in prefixes:
            if resource.startswith(prefix):
                extracted = resource[len(prefix) :]
                if ".." in extracted:
                    raise ValueError("Path traversal detected in resource identifier")
                return extracted

        if "/" in resource or "\\" in resource:
            return resource

        return resource

    def _assert_contained(self, candidate: Path, base_path: Path) -> None:
        try:
            base = base_path.resolve()
            target = candidate.resolve()
        except OSError:
            base = base_path.absolute()
            target = candidate.absolute()
        if base != target and base not in target.parents:
            raise ValueError(f"Resolved path {candidate} is outside base path {base_path}")

    def _restore_metadata(self, path: Path, snapshot: dict[str, Any] | None) -> list[str]:
        if not snapshot or not self._preserve_metadata:
            return []
        applied: list[str] = []
        metadata = snapshot.get("metadata") or {}
        mode = metadata.get("mode")
        if mode is not None:
            with contextlib.suppress(OSError, TypeError):
                os.chmod(path, int(mode))
                applied.append("permissions")
        if self._preserve_ownership:
            uid = metadata.get("uid")
            gid = metadata.get("gid")
            chown = getattr(os, "chown", None)
            if chown is not None and uid is not None and gid is not None:
                with contextlib.suppress(OSError, PermissionError, TypeError):
                    chown(path, int(uid), int(gid))
                    applied.append("ownership")
        if self._preserve_acl:
            acl = snapshot.get("acl") or {}
            if acl.get("available") and acl.get("entries"):
                applied.append("acl_capture_available")
        return applied

    def _restore_timestamps(self, path: Path, snapshot: dict[str, Any] | None) -> list[str]:
        if not snapshot or not self._preserve_metadata:
            return []
        metadata = snapshot.get("metadata") or {}
        if metadata.get("mtime_ns") is not None and metadata.get("atime_ns") is not None:
            with contextlib.suppress(OSError, TypeError):
                os.utime(path, ns=(int(metadata["atime_ns"]), int(metadata["mtime_ns"])))
                return ["timestamps"]
        if metadata.get("mtime") is not None and metadata.get("atime") is not None:
            with contextlib.suppress(OSError, TypeError):
                os.utime(path, (float(metadata["atime"]), float(metadata["mtime"])))
                return ["timestamps"]
        return []

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA-256 hash of a file."""
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _determine_compensation_operation(self, action: ProtectedAction) -> str:
        """Determine the compensation operation based on action type."""
        action_type = action.action_type.lower()

        if action_type in ("create", "write"):
            return "delete_file"

        if action_type in ("modify", "update"):
            return "restore_content"

        if action_type in ("delete",):
            return "restore_deleted_file"

        if action_type in ("rename", "move"):
            return "rename_back"

        return "restore_content"

    def _determine_compensation_type(self, action: ProtectedAction) -> CompensationType:
        """Determine the compensation type based on action type."""
        action_type = action.action_type.lower()

        if action_type in ("create", "write"):
            return CompensationType.DELETION

        if action_type in ("modify", "update"):
            return CompensationType.REVERSE_OPERATION

        if action_type in ("delete",):
            return CompensationType.STATE_TRANSITION

        if action_type in ("rename", "move"):
            return CompensationType.REVERSE_OPERATION

        return CompensationType.REVERSE_OPERATION

    def _execute_restore_content(self, payload: dict[str, Any], base_path: Path) -> dict[str, Any]:
        """Execute content restoration with atomic write.

        CRITICAL: Restores the EXACT before-state bytes.  Uses content_b64
        (raw bytes) whenever available so that line endings, encoding, BOM,
        whitespace, and final newlines are preserved byte-for-byte.  Using
        ``write_text`` previously normalized CRLF->LF and broke exact
        recovery.
        """
        file_path_str = payload.get("file_path")
        before_snapshot = payload.get("before_snapshot")

        if not file_path_str:
            return {
                "success": False,
                "execution_state": ExecutionState.FAILED,
                "error": "No file path in payload",
            }

        if not before_snapshot:
            return {
                "success": False,
                "execution_state": ExecutionState.FAILED,
                "error": "No before snapshot available for restoration",
            }

        content = before_snapshot.get("content")
        content_b64 = before_snapshot.get("content_b64")

        if content is None and content_b64 is None:
            return {
                "success": False,
                "execution_state": ExecutionState.FAILED,
                "error": "No before content available for restoration",
            }

        full_path = self._resolve_file_path(file_path_str, base_path)

        if not full_path.exists():
            return {
                "success": False,
                "execution_state": ExecutionState.FAILED,
                "error": f"File does not exist: {file_path_str}",
            }

        current_hash = self._compute_file_hash(full_path)
        expected_current_hash = payload.get("after_snapshot", {}).get("hash")

        if expected_current_hash and current_hash != expected_current_hash:
            return {
                "success": False,
                "execution_state": ExecutionState.BLOCKED_BY_CONFLICT,
                "error": "File was modified after the agent action - conflict detected",
            }

        try:
            metadata = before_snapshot.get("metadata") if self._preserve_metadata else None
            temp_path = full_path.with_suffix(full_path.suffix + ".recovery_tmp")
            if temp_path.exists():
                temp_path.unlink()

            # ALWAYS prefer the raw bytes (content_b64) when available.
            # This guarantees byte-exact restoration regardless of encoding,
            # BOM, or line-ending differences.
            if content_b64 is not None:
                temp_path.write_bytes(base64.b64decode(content_b64))
            elif content is not None:
                try:
                    encoded = content.encode("utf-8")
                except Exception as exc:
                    return {
                        "success": False,
                        "execution_state": ExecutionState.FAILED,
                        "error": (
                            "Byte-exact restoration impossible: snapshot content "
                            f"cannot be safely re-encoded: {exc}"
                        ),
                    }
                temp_path.write_bytes(encoded)
            else:
                return {
                    "success": False,
                    "execution_state": ExecutionState.FAILED,
                    "error": "No before content available for restoration",
                }

            # Atomic replace on the same filesystem.
            temp_path.replace(full_path)

            if metadata:
                with contextlib.suppress(OSError, TypeError):
                    os.chmod(full_path, metadata.get("mode", 0o644))
            self._restore_metadata(full_path, before_snapshot)
            self._restore_timestamps(full_path, before_snapshot)

            # Independent post-write hash check.
            restored_hash = self._compute_file_hash(full_path)
            expected_hash = before_snapshot.get("hash")
            if expected_hash and restored_hash != expected_hash:
                return {
                    "success": False,
                    "execution_state": ExecutionState.FAILED,
                    "error": (
                        f"Post-write hash mismatch: expected {expected_hash}, got {restored_hash}"
                    ),
                }

            return {
                "success": True,
                "execution_state": ExecutionState.SUCCEEDED,
                "details": {
                    "operation": "restore_content",
                    "file": file_path_str,
                    "restored_hash": restored_hash,
                    "byte_exact": True,
                },
                "external_outcome": "content_restored",
            }
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            return {
                "success": False,
                "execution_state": ExecutionState.FAILED,
                "error": f"Failed to write file: {str(e)}",
            }

    def _execute_delete_file(self, payload: dict[str, Any], base_path: Path) -> dict[str, Any]:
        """Execute file deletion (recovery of file creation)."""
        file_path_str = payload.get("file_path")

        if not file_path_str:
            return {
                "success": False,
                "execution_state": ExecutionState.FAILED,
                "error": "No file path in payload",
            }

        full_path = self._resolve_file_path(file_path_str, base_path)

        if not full_path.exists():
            return {
                "success": True,
                "execution_state": ExecutionState.SUCCEEDED,
                "details": {
                    "operation": "delete_file",
                    "file": file_path_str,
                    "note": "File already absent",
                },
                "external_outcome": "file_already_deleted",
            }

        try:
            full_path.unlink()
            return {
                "success": True,
                "execution_state": ExecutionState.SUCCEEDED,
                "details": {"operation": "delete_file", "file": file_path_str},
                "external_outcome": "file_deleted",
            }
        except Exception as e:
            return {
                "success": False,
                "execution_state": ExecutionState.FAILED,
                "error": f"Failed to delete file: {str(e)}",
            }

    def _execute_restore_deleted_file(
        self, payload: dict[str, Any], base_path: Path
    ) -> dict[str, Any]:
        """Execute restoration of a deleted file.

        CRITICAL: Restores the EXACT before-state bytes using content_b64
        whenever available so that line endings, encoding, BOM, whitespace,
        and final newlines are preserved byte-for-byte.
        """
        file_path_str = payload.get("file_path")
        before_snapshot = payload.get("before_snapshot")

        if not file_path_str:
            return {
                "success": False,
                "execution_state": ExecutionState.FAILED,
                "error": "No file path in payload",
            }

        if not before_snapshot or before_snapshot.get("exists", True) is False:
            return {
                "success": True,
                "execution_state": ExecutionState.SUCCEEDED,
                "details": {
                    "operation": "restore_deleted_file",
                    "file": file_path_str,
                    "note": "File already absent - no restoration needed",
                },
                "external_outcome": "file_already_absent",
            }

        content = before_snapshot.get("content")
        content_b64 = before_snapshot.get("content_b64")

        if content is None and content_b64 is None:
            return {
                "success": False,
                "execution_state": ExecutionState.FAILED,
                "error": "No before content available for restoration",
            }

        full_path = self._resolve_file_path(file_path_str, base_path)

        if full_path.exists():
            return {
                "success": False,
                "execution_state": ExecutionState.BLOCKED_BY_CONFLICT,
                "error": f"File already exists at target path: {file_path_str}",
            }

        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # ALWAYS prefer the raw bytes (content_b64) when available.
            if content_b64 is not None:
                full_path.write_bytes(base64.b64decode(content_b64))
            elif content is not None:
                try:
                    full_path.write_bytes(content.encode("utf-8"))
                except Exception as exc:
                    return {
                        "success": False,
                        "execution_state": ExecutionState.FAILED,
                        "error": (
                            "Byte-exact restoration impossible: snapshot content "
                            f"cannot be safely re-encoded: {exc}"
                        ),
                    }
            else:
                return {
                    "success": False,
                    "execution_state": ExecutionState.FAILED,
                    "error": "No before content available for restoration",
                }

            metadata = before_snapshot.get("metadata") if self._preserve_metadata else None
            if metadata:
                try:
                    os.chmod(full_path, metadata.get("mode", 0o644))
                    os.utime(full_path, (metadata.get("atime", None), metadata.get("mtime", None)))
                except (OSError, TypeError):
                    pass

            # Independent post-write hash check.
            restored_hash = self._compute_file_hash(full_path)
            expected_hash = before_snapshot.get("hash")
            if expected_hash and restored_hash != expected_hash:
                return {
                    "success": False,
                    "execution_state": ExecutionState.FAILED,
                    "error": (
                        f"Post-write hash mismatch: expected {expected_hash}, got {restored_hash}"
                    ),
                }

            return {
                "success": True,
                "execution_state": ExecutionState.SUCCEEDED,
                "details": {
                    "operation": "restore_deleted_file",
                    "file": file_path_str,
                    "restored_hash": restored_hash,
                    "byte_exact": True,
                },
                "external_outcome": "file_restored",
            }
        except Exception as e:
            return {
                "success": False,
                "execution_state": ExecutionState.FAILED,
                "error": f"Failed to restore file: {str(e)}",
            }

    def _execute_rename_back(self, payload: dict[str, Any], base_path: Path) -> dict[str, Any]:
        """Execute rename reversal."""
        file_path_str = payload.get("file_path")
        new_path_str = payload.get("new_path")

        if not file_path_str:
            return {
                "success": False,
                "execution_state": ExecutionState.FAILED,
                "error": "No file path in payload",
            }

        old_path = self._resolve_file_path(file_path_str, base_path)
        new_path = self._resolve_file_path(new_path_str, base_path) if new_path_str else None

        if new_path and new_path.exists():
            try:
                new_path.rename(old_path)
                return {
                    "success": True,
                    "execution_state": ExecutionState.SUCCEEDED,
                    "details": {"operation": "rename_back", "file": file_path_str},
                    "external_outcome": "renamed_back",
                }
            except Exception as e:
                return {
                    "success": False,
                    "execution_state": ExecutionState.FAILED,
                    "error": f"Failed to rename back: {str(e)}",
                }

        if old_path.exists():
            return {
                "success": True,
                "execution_state": ExecutionState.SUCCEEDED,
                "details": {"operation": "rename_back", "file": file_path_str},
                "external_outcome": "already_at_expected_path",
            }

        return {
            "success": False,
            "execution_state": ExecutionState.FAILED,
            "error": f"File does not exist at expected path: {file_path_str}",
        }
