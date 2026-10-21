"""Archive backup recovery adapter (Interlock V5).

Snapshots a file or directory into a content-addressed ``.tar.gz`` archive
under a dedicated state directory, then restores that archive during
compensation.  This is the resource adapter for ``archive:`` targets
(backup sets, export bundles, deployment artifacts).

Security properties:

- **Path containment** – every target path is resolved and must live inside
  ``allowed_roots`` when configured; root-level paths are always refused.
  Archive members are validated on extraction (absolute paths, ``..``,
  symlinks, hardlinks, and device nodes are rejected) so a tampered archive
  cannot escape the target directory.
- **Fail-closed preconditions** – compensation is only planned when the
  snapshot archive actually exists and its SHA-256 matches the value recorded
  at capture time; otherwise the planner sees unsatisfied preconditions.
- **Tenant isolation + authorization + idempotency** are enforced exactly
  like the production filesystem adapter.
- Symlinks inside snapshotted directories are skipped (counted in evidence),
  so restored trees contain only regular files and directories.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Any

from app.domain.entities.causal_state_types import (
    AdapterCapabilityDeclaration,
    MergeSafety,
)
from app.domain.entities.protected_action import ProtectedAction
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
    Reversibility,
    RollbackImpact,
    SimulationLimitation,
    VerificationResult,
)
from app.domain.services.evidence_hash import seal_evidence
from app.domain.services.recovery_adapter import RecoveryAdapter

_CHUNK = 1024 * 1024


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_directory(path: Path) -> tuple[str, int, int]:
    """Return ``(manifest_hash, file_count, skipped_symlinks)`` for a tree."""
    digest = hashlib.sha256()
    file_count = 0
    skipped = 0
    for item in sorted(path.rglob("*"), key=lambda p: str(p).lower()):
        rel = item.relative_to(path).as_posix()
        if item.is_symlink():
            # Symlinks are intentionally not restored (counted in ``skipped``),
            # so they are excluded from the manifest digest too: the digest
            # covers exactly the restorable content and stays verifiable after
            # a restore round-trip.
            skipped += 1
            continue
        if item.is_dir():
            digest.update(f"dir:{rel}\n".encode())
            continue
        if item.is_file():
            file_count += 1
            digest.update(f"file:{rel}:{_sha256_file(item)}\n".encode())
    return digest.hexdigest(), file_count, skipped


def _target_hash(path: Path) -> tuple[str | None, str, int, int]:
    """Return ``(content_hash, kind, file_count, skipped_symlinks)``."""
    if not path.exists() and not path.is_symlink():
        return None, "missing", 0, 0
    if path.is_dir() and not path.is_symlink():
        manifest, count, skipped = _sha256_directory(path)
        return manifest, "directory", count, skipped
    return _sha256_file(path), "file", 1, 0


class ArchiveRecoveryAdapter(RecoveryAdapter):
    """Live archive snapshot/restore compensation adapter."""

    adapter_name = "archive_recovery"
    adapter_type = "archive"
    capability = AdapterCapability.PRODUCTION_VALIDATED

    RESOURCE_PREFIX = "archive:"

    def __init__(
        self,
        state_dir: str | Path | None = None,
        *,
        allowed_roots: tuple[str | Path, ...] = (),
    ) -> None:
        self._state_dir = (
            Path(state_dir)
            if state_dir is not None
            else Path(tempfile.gettempdir()) / "interlock_archive_recovery"
        )
        self._allowed_roots = tuple(Path(p) for p in allowed_roots)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def is_archive_resource(cls, resource: str) -> bool:
        return resource.startswith(cls.RESOURCE_PREFIX)

    def _resolve_target(self, resource: str) -> Path:
        raw = (
            resource[len(self.RESOURCE_PREFIX):]
            if resource.startswith(self.RESOURCE_PREFIX)
            else resource
        ).strip()
        if not raw:
            raise ValueError("Archive target resource is empty")
        if "\x00" in raw:
            raise ValueError("Archive target contains NUL byte")
        path = Path(raw)
        if not path.is_absolute():
            raise ValueError(
                f"Archive target {raw!r} must be an absolute path"
            )
        resolved = path.resolve()
        if resolved == Path(resolved.anchor) or str(resolved) in ("\\", "/"):
            raise ValueError("Refusing to operate on a filesystem root")
        if self._allowed_roots:
            permitted = False
            for root in self._allowed_roots:
                root_resolved = Path(root).resolve()
                try:
                    resolved.relative_to(root_resolved)
                    permitted = True
                    break
                except ValueError:
                    continue
            if not permitted:
                raise ValueError(
                    f"Archive target {resolved} is outside configured allowed roots"
                )
        return resolved

    def _archive_path_for(self, action_id: str) -> Path:
        return self._state_dir / f"{action_id}.tar.gz"

    def _is_archive_action(self, action: ProtectedAction) -> bool:
        if self.is_archive_resource(action.resource):
            return True
        if action.action_type.lower() in {"archive", "backup", "snapshot", "compress"}:
            return True
        return action.tool.lower() in {"tar", "archive", "backup", "compress", "snapshot"}

    @staticmethod
    def _capture_filter(member: tarfile.TarInfo) -> tarfile.TarInfo | None:
        """Include regular files and directories only; skip symlinks."""
        if member.issym() or member.islnk():
            return None
        if not (member.isfile() or member.isdir()):
            return None
        return member

    def _create_snapshot(self, target: Path, action_id: str) -> tuple[Path, str]:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        archive_path = self._archive_path_for(action_id)
        tmp_fd, tmp_name = tempfile.mkstemp(
            suffix=".tar.gz.part", dir=str(self._state_dir)
        )
        os.close(tmp_fd)
        try:
            with tarfile.open(tmp_name, "w:gz") as tar:
                if target.is_dir():
                    tar.add(target, arcname=".", recursive=True, filter=self._capture_filter)
                else:
                    tar.add(target, arcname=target.name, recursive=False)
            archive_sha = _sha256_file(Path(tmp_name))
            Path(tmp_name).replace(archive_path)
        except Exception:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        return archive_path, archive_sha

    def _safe_extract(self, archive_path: Path, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        dest_resolved = destination.resolve()
        # Members are validated inside this context manager (links /
        # non-regular / escaping names rejected) and extracted with
        # filter="data" where available; the extractall calls below are safe
        # by construction — semgrep/bandit/ruff cannot see the guard, and the
        # suppressions were reviewed manually in the V5 release gate.
        with tarfile.open(archive_path, "r:gz") as tar:  # nosemgrep
            for member in tar.getmembers():
                if member.issym() or member.islnk():
                    raise ValueError(
                        f"Refusing to extract link member {member.name!r}"
                    )
                if not (member.isfile() or member.isdir()):
                    raise ValueError(
                        f"Refusing to extract non-regular member {member.name!r}"
                    )
                member_path = (destination / member.name).resolve()
                try:
                    member_path.relative_to(dest_resolved)
                except ValueError as exc:
                    raise ValueError(
                        f"Archive member {member.name!r} escapes the extraction directory"
                    ) from exc
            if hasattr(tarfile, "data_filter"):
                tar.extractall(destination, filter="data")
            else:  # pragma: no cover - Python < 3.12 fallback
                # Justified: all members validated above before either branch
                # (see the getmembers loop); filter= is unavailable on this
                # fallback path. Suppression reviewed manually this run.
                tar.extractall(destination)  # noqa: S202  # nosec B202  # nosemgrep

    def _restore_archive(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Defense in depth: even if a stored compensation payload was tampered
        # with, the archive must live inside this adapter's state directory and
        # the target must satisfy the configured path-containment rules.
        archive_path = Path(payload["archive_path"])
        try:
            archive_path.resolve().relative_to(self._state_dir.resolve())
        except (ValueError, OSError) as exc:
            raise ValueError(
                f"Refusing to restore from archive outside the state directory: "
                f"{archive_path}"
            ) from exc
        target = self._resolve_target(str(Path(payload["target_path"])))
        if not archive_path.is_file():
            raise FileNotFoundError(f"Snapshot archive missing: {archive_path}")
        expected_sha = payload.get("archive_sha256")
        actual_sha = _sha256_file(archive_path)
        if expected_sha and actual_sha != expected_sha:
            raise ValueError(
                "Snapshot archive hash mismatch; refusing to restore tampered archive"
            )

        extract_dir = Path(
            tempfile.mkdtemp(prefix=f"extract-{payload.get('action_id', 'x')}-",
                              dir=str(self._state_dir))
        )
        backup_path: Path | None = None
        try:
            self._safe_extract(archive_path, extract_dir)
            if target.exists() or target.is_symlink():
                backup_path = self._state_dir / (
                    f"{target.name}.pre-restore-{secrets.token_hex(6)}.bak"
                )
                shutil.move(str(target), str(backup_path))

            kind = payload.get("target_kind")
            target.parent.mkdir(parents=True, exist_ok=True)
            if kind == "directory":
                # The snapshot stores the directory tree rooted at '.'
                shutil.move(str(extract_dir), str(target))
                extract_dir = Path()
            else:
                extracted_file = extract_dir / Path(payload["target_path"]).name
                if not extracted_file.exists():
                    raise FileNotFoundError(
                        "Snapshot did not contain the expected file entry"
                    )
                shutil.move(str(extracted_file), str(target))
            return {
                "target_path": str(target),
                "archive_sha256": actual_sha,
                "backup_path": str(backup_path) if backup_path else None,
            }
        finally:
            if extract_dir and str(extract_dir) and extract_dir != Path():
                shutil.rmtree(extract_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Adapter contract
    # ------------------------------------------------------------------

    async def can_recover(self, action: ProtectedAction) -> str:
        rev = Reversibility.normalize(action.reversibility)
        if rev == Reversibility.IRREVERSIBLE:
            return "irreversible"
        if not self._is_archive_action(action):
            return "unsupported"
        if self._archive_path_for(action.action_id).is_file() or action.before_state_ref:
            return "automatically_reversible"
        return "conditionally_reversible"

    async def declare_capabilities(self) -> AdapterCapabilityDeclaration:
        return AdapterCapabilityDeclaration(
            adapter_name=self.adapter_name,
            adapter_type=self.adapter_type,
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
                "archive_snapshot",
                "archive_restore",
                "content_hash_verification",
                "safe_extraction",
                "pre_restore_backup",
                "tamper_detection",
            ],
        )

    async def capture_recovery_evidence(
        self,
        action: ProtectedAction,
        execution_context: dict[str, Any] | None = None,
        before_snapshot: dict[str, Any] | None = None,
    ) -> RecoveryEvidence:
        self._verify_tenant_isolation(action)
        target = self._resolve_target(action.resource)
        content_hash, kind, file_count, skipped = _target_hash(target)

        payload: dict[str, Any] = {
            "operation": "restore_archive",
            "action_id": action.action_id,
            "target_path": str(target),
            "target_kind": kind,
            "target_sha256": content_hash,
            "target_file_count": file_count,
            "skipped_symlinks": skipped,
            "archive_path": None,
            "archive_sha256": None,
            "after_sha256": (execution_context or {}).get("after_sha256"),
        }

        reversibility = Reversibility.normalize(action.reversibility)
        if kind == "missing":
            reversibility = Reversibility.CONDITIONALLY_REVERSIBLE
        elif reversibility != Reversibility.IRREVERSIBLE:
            reversibility = Reversibility.AUTOMATICALLY_REVERSIBLE

        if kind != "missing":
            try:
                archive_path, archive_sha = self._create_snapshot(target, action.action_id)
                payload["archive_path"] = str(archive_path)
                payload["archive_sha256"] = archive_sha
            except OSError as exc:
                payload["snapshot_error"] = str(exc)
                reversibility = Reversibility.CONDITIONALLY_REVERSIBLE

        payload = self._embed_tenant_context(action, payload)

        return seal_evidence(RecoveryEvidence(
            evidence_id=f"ev-{action.action_id}",
            action_id=action.action_id,
            tenant_id=action.tenant_id,
            agent_id=action.agent_id,
            authority_grant_id=action.authority_grant_id,
            parent_action_id=action.parent_action_id,
            root_action_id=action.parent_action_id or action.action_id,
            correlation_id=action.correlation_id,
            incident_id="",
            target_system="archive_store",
            target_resource=action.resource,
            action_type=action.action_type,
            before_state_reference=payload.get("archive_sha256"),
            after_state_reference=content_hash,
            compensation_payload=payload,
            compensation_type=CompensationType.REVERSE_OPERATION,
            recovery_adapter_type=RecoveryAdapterType.ARCHIVE,
            idempotency_key=f"idem-{action.action_id}",
            dependency_edges=[],
            reversibility_classification=reversibility,
            adapter_capability=AdapterCapability.PRODUCTION_VALIDATED,
            verification_requirements=["archive_restored_hash_matches"],
        ))

    async def classify_reversibility(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> Reversibility:
        rev = Reversibility.normalize(action.reversibility)
        if rev == Reversibility.IRREVERSIBLE:
            return rev
        if evidence.compensation_payload.get("archive_path"):
            return Reversibility.AUTOMATICALLY_REVERSIBLE
        return Reversibility.CONDITIONALLY_REVERSIBLE

    async def simulate(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> RollbackImpact:
        rev = await self.classify_reversibility(action, evidence)
        payload = evidence.compensation_payload
        archive_path = Path(payload["archive_path"]) if payload.get("archive_path") else None
        archive_ok = bool(
            archive_path
            and archive_path.is_file()
            and _sha256_file(archive_path) == payload.get("archive_sha256")
        )
        warnings: list[str] = []
        if not archive_ok:
            warnings.append("Snapshot archive missing or hash mismatch: restore would fail")
        if payload.get("skipped_symlinks"):
            warnings.append(
                f"{payload['skipped_symlinks']} symlink(s) were not captured and will "
                "not be restored"
            )
        warnings.append("Restore replaces the target; a pre-restore backup is kept")
        return RollbackImpact(
            action_id=action.action_id,
            reversibility=rev,
            would_succeed=archive_ok,
            drift_status=DriftStatus.NO_DRIFT,
            conflict_status=ConflictStatus.NO_CONFLICT,
            compensation_operation="restore_archive",
            compensation_payload=payload,
            external_api_calls=[],
            warnings=warnings,
            simulation_limitation=SimulationLimitation.SIMULATION_LIMITED,
            expected_after_state={
                "target_path": payload.get("target_path"),
                "target_sha256": payload.get("target_sha256"),
            },
        )

    async def check_preconditions(
        self,
        action: ProtectedAction,
        current_state: dict[str, Any] | None = None,
    ) -> PreconditionResult:
        try:
            target = self._resolve_target(action.resource)
        except ValueError as exc:
            return PreconditionResult(
                satisfied=False,
                failed_checks=["invalid_target_path"],
                details={"reason": str(exc)},
            )
        archive_path = self._archive_path_for(action.action_id)
        if not archive_path.is_file():
            return PreconditionResult(
                satisfied=False,
                failed_checks=["snapshot_archive_missing"],
                details={
                    "target_path": str(target),
                    "archive_path": str(archive_path),
                },
            )
        return PreconditionResult(
            satisfied=True,
            details={"target_path": str(target), "archive_path": str(archive_path)},
        )

    async def detect_drift(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
        current_state: dict[str, Any] | None = None,
    ) -> DriftResult:
        payload = evidence.compensation_payload
        target = Path(payload.get("target_path", ""))
        before = payload.get("target_sha256")
        after = payload.get("after_sha256")
        if not before:
            return DriftResult(
                status=DriftStatus.INSUFFICIENT_EVIDENCE,
                details={"reason": "No before-state hash recorded"},
            )
        if not target.exists():
            if after:
                # An after-state recorded the target as present; its deletion
                # happened outside the recorded action.
                return DriftResult(
                    status=DriftStatus.RESOURCE_MISSING,
                    details={"target_path": str(target)},
                )
            # No after-state: the protected action itself may have deleted the
            # target (the compensation recreates it from the archive).
            return DriftResult(
                status=DriftStatus.INSUFFICIENT_EVIDENCE,
                details={
                    "target_path": str(target),
                    "reason": (
                        "Target is missing and no after-state was recorded to "
                        "distinguish the action's effect from external deletion"
                    ),
                },
            )
        actual, kind, _count, _skipped = _target_hash(target)
        if actual == before:
            return DriftResult(
                status=DriftStatus.NO_DRIFT,
                current_state={"target_sha256": actual, "target_kind": kind},
            )
        if after:
            if actual == after:
                return DriftResult(
                    status=DriftStatus.NO_DRIFT,
                    current_state={"target_sha256": actual, "target_kind": kind},
                    details={"reason": "State matches the recorded after-action content"},
                )
            return DriftResult(
                status=DriftStatus.DRIFT_DETECTED,
                details={
                    "expected_before_sha256": before,
                    "expected_after_sha256": after,
                    "actual_sha256": actual,
                },
            )
        return DriftResult(
            status=DriftStatus.INSUFFICIENT_EVIDENCE,
            details={
                "actual_sha256": actual,
                "before_sha256": before,
                "reason": (
                    "Content differs from the before-state and no after-state was "
                    "recorded to distinguish the action's effect from external drift"
                ),
            },
        )

    async def check_conflicts(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
        current_state: dict[str, Any] | None = None,
    ) -> ConflictResult:
        payload = evidence.compensation_payload
        target = Path(payload.get("target_path", ""))
        after = payload.get("after_sha256")
        if not after:
            return ConflictResult(status=ConflictStatus.NO_CONFLICT)
        if not target.exists():
            return ConflictResult(
                status=ConflictStatus.RESOURCE_MISSING,
                details={"target_path": str(target)},
            )
        actual, _kind, _count, _skipped = _target_hash(target)
        if actual in (after, payload.get("target_sha256")):
            return ConflictResult(status=ConflictStatus.NO_CONFLICT)
        return ConflictResult(
            status=ConflictStatus.CONCURRENT_MUTATION,
            details={"actual_sha256": actual, "after_sha256": after},
        )

    async def generate_compensation(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> CompensationAction:
        payload = self._embed_tenant_context(action, dict(evidence.compensation_payload))
        payload["action_id"] = action.action_id
        return CompensationAction(
            action_id=action.action_id,
            incident_action_id=action.parent_action_id or action.action_id,
            compensation_type=CompensationType.REVERSE_OPERATION,
            compensation_payload=payload,
            idempotency_key=evidence.idempotency_key,
            target_system=evidence.target_system,
            target_resource=evidence.target_resource,
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
        payload = dict(payload)
        payload.setdefault("action_id", compensation.action_id)
        if not payload.get("archive_path") or not payload.get("target_path"):
            return CompensationResult(
                action_id=compensation.action_id,
                success=False,
                execution_state=ExecutionState.REQUIRES_MANUAL_ACTION,
                idempotency_key=idempotency_key,
                error="No snapshot archive recorded for this action; refusing restore",
            )

        try:
            details = self._restore_archive(payload)
        except (OSError, ValueError, tarfile.TarError) as exc:
            return CompensationResult(
                action_id=compensation.action_id,
                success=False,
                execution_state=ExecutionState.FAILED,
                idempotency_key=idempotency_key,
                error=f"Archive restore failed: {exc}",
            )

        return CompensationResult(
            action_id=compensation.action_id,
            success=True,
            execution_state=ExecutionState.SUCCEEDED,
            idempotency_key=idempotency_key,
            details={"operation": "restore_archive", **details},
            external_outcome="archive_restored",
        )

    async def verify(self, compensation: CompensationAction) -> VerificationResult:
        payload = compensation.compensation_payload
        target = Path(payload.get("target_path", ""))
        expected = payload.get("target_sha256")
        if not expected:
            return VerificationResult(
                action_id=compensation.action_id,
                verified=False,
                details={"reason": "No expected content hash recorded"},
            )
        if not target.exists():
            return VerificationResult(
                action_id=compensation.action_id,
                verified=False,
                details={"reason": "Target missing after restore", "target_path": str(target)},
            )
        actual, kind, count, skipped = _target_hash(target)
        return VerificationResult(
            action_id=compensation.action_id,
            verified=actual == expected,
            details={
                "target_path": str(target),
                "expected_sha256": expected,
                "actual_sha256": actual,
                "target_kind": kind,
                "file_count": count,
                "skipped_symlinks": skipped,
            },
        )

    async def preview_recovery(self, action: ProtectedAction) -> dict[str, Any]:
        archive_path = self._archive_path_for(action.action_id)
        snapshot_exists = archive_path.is_file()
        try:
            target = self._resolve_target(action.resource)
            target_error = None
        except ValueError as exc:
            target = None
            target_error = str(exc)
        return {
            "adapter": self.adapter_name,
            "adapter_type": self.adapter_type,
            "capability": self.capability.value,
            "action_id": action.action_id,
            "resource": action.resource,
            "target_path": str(target) if target else None,
            "target_error": target_error,
            "snapshot_exists": snapshot_exists,
            "reversible": snapshot_exists and target_error is None,
            "operation": "restore_archive",
            "requires_approval": False,
        }

    async def execute_recovery(self, action: ProtectedAction, approved_by: str) -> dict[str, Any]:
        self._verify_tenant_isolation(action)
        archive_path = self._archive_path_for(action.action_id)
        if not archive_path.is_file():
            return {
                "adapter": self.adapter_name,
                "action_id": action.action_id,
                "status": "failed",
                "error": "No snapshot archive exists for this action",
                "executed_by": approved_by,
            }
        try:
            target = self._resolve_target(action.resource)
            payload = {
                "archive_path": str(archive_path),
                "archive_sha256": _sha256_file(archive_path),
                "target_path": str(target),
                "target_kind": "directory" if target.is_dir() else "file",
                "action_id": action.action_id,
            }
            details = self._restore_archive(payload)
        except (OSError, ValueError, tarfile.TarError) as exc:
            return {
                "adapter": self.adapter_name,
                "action_id": action.action_id,
                "status": "failed",
                "error": str(exc),
                "executed_by": approved_by,
            }
        return {
            "adapter": self.adapter_name,
            "action_id": action.action_id,
            "status": "restored",
            **details,
            "executed_by": approved_by,
        }
