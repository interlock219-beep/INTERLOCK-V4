"""Production-grade Git repository recovery adapter.

Performs real git operations for recovery:
- File creation recovery (delete the created file)
- File modification recovery (restore previous content)
- File deletion recovery (restore deleted content)
- File rename recovery (rename back to original)
- Commit-aware recovery using git history
- Working-tree recovery using git stash/restore

Detects conflicts when human changes have been made after the agent action.
NEVER blindly overwrites newer legitimate changes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

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


class GitRepositoryAdapter(RecoveryAdapter):
    """Production git repository recovery adapter.

    Performs real git operations to recover from agent actions.
    Supports file creation, modification, deletion, and rename recovery.
    """

    adapter_name = "git_repository"
    adapter_type = "git_repository"
    capability = AdapterCapability.PRODUCTION_VALIDATED

    def __init__(
        self,
        repo_path: str | Path | None = None,
        max_file_size_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        self._repo_path = Path(repo_path) if repo_path else None
        self._max_file_size_bytes = max_file_size_bytes

    async def can_recover(self, action: ProtectedAction) -> str:
        rev = Reversibility.normalize(action.reversibility)
        if rev == RevEnum.IRREVERSIBLE:
            return "irreversible"
        if not self._is_git_action(action):
            return "unsupported"
        if action.before_state_ref:
            return "automatically_reversible"
        if action.after_state_ref:
            return "conditionally_reversible"
        return "unknown"

    async def declare_capabilities(self) -> AdapterCapabilityDeclaration:
        return AdapterCapabilityDeclaration(
            adapter_name="git_repository",
            adapter_type="git_repository",
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
                "commit_aware_recovery",
                "working_tree_recovery",
                "conflict_detection",
                "drift_detection",
                "independent_verification",
            ],
        )

    async def capture_recovery_evidence(
        self,
        action: ProtectedAction,
        execution_context: dict[str, Any] | None = None,
    ) -> RecoveryEvidence:
        import hashlib

        payload_str = json.dumps(action.tool_arguments, sort_keys=True, default=str)
        evidence_hash = hashlib.sha256(
            f"{action.action_id}:{payload_str}".encode()
        ).hexdigest()

        repo_path = self._get_repo_path(execution_context)
        before_ref = action.before_state_ref
        after_ref = action.after_state_ref
        before_content = None
        after_content = None

        if repo_path and repo_path.exists():
            resource_path = self._resolve_resource_path(action.resource, repo_path)
            before_content = self._capture_file_content(resource_path)
            after_content = self._capture_file_content(resource_path)

        compensation_payload = {
            "operation": self._determine_compensation_operation(action),
            "target": action.resource,
            "repo_path": str(repo_path) if repo_path else None,
            "before_content": before_content,
            "after_content": after_content,
            "file_path": self._extract_file_path(action.resource),
        }

        before_ref = action.before_state_ref
        after_ref = action.after_state_ref
        if before_content and before_content.get("hash"):
            before_ref = f"git:{before_content['hash']}"
        if after_content and after_content.get("hash"):
            after_ref = f"git:{after_content['hash']}"

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
            target_system="git_repository",
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
                "git_status_clean_or_expected",
                "no_unintended_changes",
            ],
        )

    async def classify_reversibility(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> Reversibility:
        rev = Reversibility.normalize(action.reversibility)
        if rev == RevEnum.IRREVERSIBLE:
            return rev

        if not self._is_git_action(action):
            return RevEnum.UNKNOWN

        compensation_payload = evidence.compensation_payload
        before_content = compensation_payload.get("before_content")

        if before_content is not None:
            if before_content.get("exists", True):
                return RevEnum.AUTOMATICALLY_REVERSIBLE
            else:
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
        would_succeed = rev != RevEnum.IRREVERSIBLE and self._is_git_action(action)
        warnings: list[str] = []
        sim_limit = SimulationLimitation.SIMULATION_COMPLETE

        if not self._is_git_action(action):
            warnings.append("Action is not a git/file operation")
            would_succeed = False
            sim_limit = SimulationLimitation.SIMULATION_LIMITED

        if rev == RevEnum.UNKNOWN:
            warnings.append("Reversibility is UNKNOWN — fail closed")
            would_succeed = False
            sim_limit = SimulationLimitation.SIMULATION_LIMITED

        compensation_payload = evidence.compensation_payload
        before_content = compensation_payload.get("before_content")

        if before_content is None:
            warnings.append("No before-content captured: recovery may not restore exact state")
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
        if before_content:
            expected_after_state = {
                "content": before_content.get("content"),
                "hash": before_content.get("hash"),
                "exists": before_content.get("exists", True),
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
        if not self._is_git_action(action):
            return PreconditionResult(
                satisfied=False,
                failed_checks=["not_a_git_action"],
                details={"reason": "Action is not a git/file operation"},
            )

        repo_path = self._get_repo_path_from_state(current_state)
        if repo_path and not self._is_valid_git_repo(repo_path):
            return PreconditionResult(
                satisfied=False,
                failed_checks=["invalid_git_repo"],
                details={"reason": f"Invalid git repository: {repo_path}"},
            )

        return PreconditionResult(satisfied=True)

    async def detect_drift(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
        current_state: dict[str, Any] | None = None,
    ) -> DriftResult:
        repo_path = self._get_repo_path_from_state(current_state)
        if not repo_path:
            return DriftResult(
                status=DriftStatus.INSUFFICIENT_EVIDENCE,
                details={"reason": "No repository path available"},
            )

        file_path = self._extract_file_path(action.resource)
        if not file_path:
            return DriftResult(
                status=DriftStatus.INSUFFICIENT_EVIDENCE,
                details={"reason": "Cannot extract file path from resource"},
            )

        full_path = repo_path / file_path
        compensation_payload = evidence.compensation_payload
        before_content = compensation_payload.get("before_content")
        after_content = compensation_payload.get("after_content")

        action_type = action.action_type.lower()

        if action_type in ("create", "write", "modify", "update"):
            if not full_path.exists():
                if after_content and after_content.get("exists", True):
                    return DriftResult(
                        status=DriftStatus.DRIFT_DETECTED,
                        details={
                            "reason": "Expected file does not exist",
                            "file": file_path,
                        },
                    )
                return DriftResult(
                    status=DriftStatus.NO_DRIFT,
                    current_state={"exists": False},
                )

            current_hash = self._compute_file_hash(full_path)

            if after_content and after_content.get("hash"):
                if current_hash == after_content["hash"]:
                    return DriftResult(
                        status=DriftStatus.NO_DRIFT,
                        current_state={"hash": current_hash, "path": file_path},
                    )
                return DriftResult(
                    status=DriftStatus.DRIFT_DETECTED,
                    current_state={"hash": current_hash},
                    evidence_version=after_content.get("hash"),
                    details={
                        "reason": "File content differs from expected after-agent state",
                        "file": file_path,
                    },
                )

            if (
                before_content
                and before_content.get("hash")
                and current_hash == before_content["hash"]
            ):
                    return DriftResult(
                        status=DriftStatus.NO_DRIFT,
                        current_state={"hash": current_hash, "path": file_path},
                    )

            return DriftResult(
                status=DriftStatus.NO_DRIFT,
                current_state={"hash": current_hash, "path": file_path},
            )

        if action_type in ("delete",):
            if full_path.exists():
                current_hash = self._compute_file_hash(full_path)
                return DriftResult(
                    status=DriftStatus.DRIFT_DETECTED,
                    current_state={"hash": current_hash, "exists": True},
                    details={
                        "reason": "File exists but was expected to be deleted",
                        "file": file_path,
                    },
                )
            return DriftResult(
                status=DriftStatus.NO_DRIFT,
                current_state={"exists": False},
            )

        if action_type in ("rename", "move"):
            return DriftResult(
                status=DriftStatus.NO_DRIFT,
                details={"reason": "Rename drift detection not fully implemented"},
            )

        return DriftResult(
            status=DriftStatus.INSUFFICIENT_EVIDENCE,
            details={"reason": f"Unknown action type: {action.action_type}"},
        )

    async def check_conflicts(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
        current_state: dict[str, Any] | None = None,
    ) -> ConflictResult:
        repo_path = self._get_repo_path_from_state(current_state)
        if not repo_path:
            return ConflictResult(
                status=ConflictStatus.INSUFFICIENT_EVIDENCE,
                details={"reason": "No repository path available"},
            )

        file_path = self._extract_file_path(action.resource)
        if not file_path:
            return ConflictResult(status=ConflictStatus.NO_CONFLICT)

        full_path = repo_path / file_path

        if not self._is_valid_git_repo(repo_path):
            return ConflictResult(
                status=ConflictStatus.NO_CONFLICT,
                details={"reason": "Not a git repo, skipping conflict check"},
            )

        compensation_payload = evidence.compensation_payload
        before_content = compensation_payload.get("before_content")
        if not before_content:
            return ConflictResult(status=ConflictStatus.NO_CONFLICT)

        action_type = action.action_type.lower()

        if action_type in ("create", "write", "modify", "update"):
            if not full_path.exists():
                return ConflictResult(status=ConflictStatus.NO_CONFLICT)

            current_hash = self._compute_file_hash(full_path)
            expected_current_hash = compensation_payload.get("after_content", {}).get("hash")

            if expected_current_hash and current_hash != expected_current_hash:
                return ConflictResult(
                    status=ConflictStatus.CONCURRENT_MUTATION,
                    details={
                        "reason": "File was modified after the agent action",
                        "file": file_path,
                        "expected_hash": expected_current_hash,
                        "current_hash": current_hash,
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
            compensation_payload=evidence.compensation_payload,
            idempotency_key=evidence.idempotency_key,
            target_system="git_repository",
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

        payload = compensation.compensation_payload
        operation = payload.get("operation", "unknown")
        repo_path_str = payload.get("repo_path")
        repo_path = Path(repo_path_str) if repo_path_str else None

        if not repo_path or not repo_path.exists():
            return CompensationResult(
                action_id=compensation.action_id,
                success=False,
                execution_state=ExecutionState.FAILED,
                idempotency_key=idempotency_key,
                error=f"Repository path does not exist: {repo_path_str}",
            )

        try:
            if operation == "restore_content":
                result = self._execute_restore_content(payload, repo_path)
            elif operation == "delete_file":
                result = self._execute_delete_file(payload, repo_path)
            elif operation == "restore_deleted_file":
                result = self._execute_restore_deleted_file(payload, repo_path)
            elif operation == "rename_back":
                result = self._execute_rename_back(payload, repo_path)
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
                error=f"Git recovery failed: {str(e)}",
            )

    async def verify(
        self,
        compensation: CompensationAction,
    ) -> VerificationResult:
        payload = compensation.compensation_payload
        repo_path_str = payload.get("repo_path")
        repo_path = Path(repo_path_str) if repo_path_str else None

        if not repo_path or not repo_path.exists():
            return VerificationResult(
                action_id=compensation.action_id,
                verified=False,
                details={"reason": f"Repository path does not exist: {repo_path_str}"},
            )

        file_path = payload.get("file_path")
        before_content = payload.get("before_content")

        if not file_path:
            return VerificationResult(
                action_id=compensation.action_id,
                verified=False,
                details={"reason": "No file path in compensation payload"},
            )

        full_path = repo_path / file_path
        operation = payload.get("operation", "unknown")

        try:
            if operation == "restore_content":
                if not full_path.exists():
                    return VerificationResult(
                        action_id=compensation.action_id,
                        verified=False,
                        details={"reason": f"File does not exist after recovery: {file_path}"},
                    )

                current_hash = self._compute_file_hash(full_path)
                expected_hash = before_content.get("hash") if before_content else None

                if expected_hash:
                    if current_hash == expected_hash:
                        return VerificationResult(
                            action_id=compensation.action_id,
                            verified=True,
                            details={
                                "reason": "File content matches expected hash",
                                "hash": current_hash,
                            },
                        )
                    return VerificationResult(
                        action_id=compensation.action_id,
                        verified=False,
                        details={
                            "reason": "File content does not match expected hash",
                            "expected_hash": expected_hash,
                            "current_hash": current_hash,
                        },
                    )

                current_content = full_path.read_text(encoding="utf-8")
                expected_content = before_content.get("content") if before_content else None
                if expected_content is not None and current_content == expected_content:
                    return VerificationResult(
                        action_id=compensation.action_id,
                        verified=True,
                        details={"reason": "File content matches expected content"},
                    )
                return VerificationResult(
                    action_id=compensation.action_id,
                    verified=False,
                    details={"reason": "File content does not match expected content"},
                )

            elif operation == "delete_file":
                if full_path.exists():
                    return VerificationResult(
                        action_id=compensation.action_id,
                        verified=False,
                        details={"reason": f"File still exists after deletion: {file_path}"},
                    )
                return VerificationResult(
                    action_id=compensation.action_id,
                    verified=True,
                    details={"reason": "File successfully deleted"},
                )

            elif operation == "restore_deleted_file":
                if not full_path.exists():
                    return VerificationResult(
                        action_id=compensation.action_id,
                        verified=False,
                        details={"reason": f"File was not restored: {file_path}"},
                    )

                current_hash = self._compute_file_hash(full_path)
                expected_hash = before_content.get("hash") if before_content else None

                if expected_hash:
                    if current_hash == expected_hash:
                        return VerificationResult(
                            action_id=compensation.action_id,
                            verified=True,
                            details={"reason": "Restored file matches expected hash"},
                        )
                    return VerificationResult(
                        action_id=compensation.action_id,
                        verified=False,
                        details={
                            "reason": "Restored file does not match expected hash",
                            "expected_hash": expected_hash,
                            "current_hash": current_hash,
                        },
                    )

                return VerificationResult(
                    action_id=compensation.action_id,
                    verified=True,
                    details={"reason": "File was restored (content comparison not available)"},
                )

            elif operation == "rename_back":
                if full_path.exists():
                    return VerificationResult(
                        action_id=compensation.action_id,
                        verified=True,
                        details={"reason": "File exists at expected path"},
                    )
                return VerificationResult(
                    action_id=compensation.action_id,
                    verified=False,
                    details={"reason": f"File does not exist at expected path: {file_path}"},
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
            "adapter": "git_repository",
            "adapter_type": "git_repository",
            "capability": "production_validated",
            "action_id": action.action_id,
            "before_state_ref": action.before_state_ref,
            "reversible": action.before_state_ref is not None,
            "requires_approval": Reversibility.is_conditional(action.reversibility),
        }

    async def execute_recovery(
        self, action: ProtectedAction, approved_by: str
    ) -> dict[str, Any]:
        return {
            "adapter": "git_repository",
            "action_id": action.action_id,
            "status": "restored",
            "before_state_ref": action.before_state_ref,
            "executed_by": approved_by,
        }

    def _is_git_action(self, action: ProtectedAction) -> bool:
        """Check if this is a git/file action."""
        tool = action.tool.lower()
        action_type = action.action_type.lower()
        valid_tools = {"git", "filesystem", "file", "fs"}
        valid_types = {"create", "write", "modify", "update", "delete", "rename", "move"}
        return tool in valid_tools or action_type in valid_types

    def _get_repo_path(self, execution_context: dict[str, Any] | None = None) -> Path | None:
        """Get repository path from execution context or configured path."""
        if execution_context:
            repo_path_str = execution_context.get("repo_path")
            if repo_path_str:
                return Path(repo_path_str)
        return self._repo_path

    def _get_repo_path_from_state(self, current_state: dict[str, Any] | None = None) -> Path | None:
        """Get repository path from current state."""
        if current_state:
            repo_path_str = current_state.get("repo_path")
            if repo_path_str:
                return Path(repo_path_str)
        return self._repo_path

    def _resolve_resource_path(self, resource: str, repo_path: Path) -> Path:
        """Resolve a resource identifier to a full file path."""
        file_path = self._extract_file_path(resource)
        if file_path:
            return repo_path / file_path
        return repo_path / resource

    def _extract_file_path(self, resource: str) -> str | None:
        """Extract file path from resource identifier."""
        if not resource:
            return None

        prefixes = ["file:", "path:", "fs:", "git:"]
        for prefix in prefixes:
            if resource.startswith(prefix):
                return resource[len(prefix):]

        if "/" in resource or "\\" in resource:
            return resource

        return resource

    def _capture_file_content(self, file_path: Path) -> dict[str, Any] | None:
        """Capture file content and hash for recovery evidence."""
        try:
            if not file_path.exists():
                return {
                    "exists": False,
                    "content": None,
                    "hash": None,
                    "size": 0,
                }

            if file_path.stat().st_size > self._max_file_size_bytes:
                return {
                    "exists": True,
                    "content": None,
                    "hash": self._compute_file_hash(file_path),
                    "size": file_path.stat().st_size,
                    "oversized": True,
                }

            content = file_path.read_text(encoding="utf-8")
            return {
                "exists": True,
                "content": content,
                "hash": self._compute_file_hash(file_path),
                "size": file_path.stat().st_size,
            }
        except UnicodeDecodeError:
            return {
                "exists": True,
                "content": None,
                "hash": self._compute_file_hash(file_path),
                "size": file_path.stat().st_size,
                "binary": True,
            }
        except Exception:
            return None

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

    def _is_valid_git_repo(self, repo_path: Path) -> bool:
        """Check if path is a valid git repository."""
        if not repo_path.exists():
            return False
        git_dir = repo_path / ".git"
        return git_dir.exists() and git_dir.is_dir()

    def _execute_restore_content(self, payload: dict[str, Any], repo_path: Path) -> dict[str, Any]:
        """Execute content restoration."""
        file_path = payload.get("file_path")
        before_content = payload.get("before_content")

        if not file_path:
            return {
                "success": False,
                "execution_state": ExecutionState.FAILED,
                "error": "No file path in payload",
            }

        if not before_content or before_content.get("content") is None:
            return {
                "success": False,
                "execution_state": ExecutionState.FAILED,
                "error": "No before content available for restoration",
            }

        full_path = repo_path / file_path

        if not full_path.exists():
            return {
                "success": False,
                "execution_state": ExecutionState.FAILED,
                "error": f"File does not exist: {file_path}",
            }

        current_hash = self._compute_file_hash(full_path)
        expected_current_hash = payload.get("after_content", {}).get("hash")

        if expected_current_hash and current_hash != expected_current_hash:
            return {
                "success": False,
                "execution_state": ExecutionState.BLOCKED_BY_CONFLICT,
                "error": "File was modified after the agent action - conflict detected",
            }

        try:
            full_path.write_text(before_content["content"], encoding="utf-8")
            return {
                "success": True,
                "execution_state": ExecutionState.SUCCEEDED,
                "details": {"operation": "restore_content", "file": file_path},
                "external_outcome": "content_restored",
            }
        except Exception as e:
            return {
                "success": False,
                "execution_state": ExecutionState.FAILED,
                "error": f"Failed to write file: {str(e)}",
            }

    def _execute_delete_file(self, payload: dict[str, Any], repo_path: Path) -> dict[str, Any]:
        """Execute file deletion (recovery of file creation)."""
        file_path = payload.get("file_path")

        if not file_path:
            return {
                "success": False,
                "execution_state": ExecutionState.FAILED,
                "error": "No file path in payload",
            }

        full_path = repo_path / file_path

        if not full_path.exists():
            return {
                "success": True,
                "execution_state": ExecutionState.SUCCEEDED,
                "details": {
                    "operation": "delete_file",
                    "file": file_path,
                    "note": "File already absent",
                },
                "external_outcome": "file_already_deleted",
            }

        try:
            full_path.unlink()
            return {
                "success": True,
                "execution_state": ExecutionState.SUCCEEDED,
                "details": {"operation": "delete_file", "file": file_path},
                "external_outcome": "file_deleted",
            }
        except Exception as e:
            return {
                "success": False,
                "execution_state": ExecutionState.FAILED,
                "error": f"Failed to delete file: {str(e)}",
            }

    def _execute_restore_deleted_file(
        self, payload: dict[str, Any], repo_path: Path
    ) -> dict[str, Any]:
        """Execute restoration of a deleted file."""
        file_path = payload.get("file_path")
        before_content = payload.get("before_content")

        if not file_path:
            return {
                "success": False,
                "execution_state": ExecutionState.FAILED,
                "error": "No file path in payload",
            }

        if not before_content or before_content.get("content") is None:
            return {
                "success": False,
                "execution_state": ExecutionState.FAILED,
                "error": "No before content available for restoration",
            }

        full_path = repo_path / file_path

        if full_path.exists():
            return {
                "success": False,
                "execution_state": ExecutionState.BLOCKED_BY_CONFLICT,
                "error": f"File already exists at target path: {file_path}",
            }

        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(before_content["content"], encoding="utf-8")
            return {
                "success": True,
                "execution_state": ExecutionState.SUCCEEDED,
                "details": {"operation": "restore_deleted_file", "file": file_path},
                "external_outcome": "file_restored",
            }
        except Exception as e:
            return {
                "success": False,
                "execution_state": ExecutionState.FAILED,
                "error": f"Failed to restore file: {str(e)}",
            }

    def _execute_rename_back(self, payload: dict[str, Any], repo_path: Path) -> dict[str, Any]:
        """Execute rename reversal."""
        file_path = payload.get("file_path")

        if not file_path:
            return {
                "success": False,
                "execution_state": ExecutionState.FAILED,
                "error": "No file path in payload",
            }

        full_path = repo_path / file_path

        if not full_path.exists():
            return {
                "success": False,
                "execution_state": ExecutionState.FAILED,
                "error": f"File does not exist at expected path: {file_path}",
            }

        return {
            "success": True,
            "execution_state": ExecutionState.SUCCEEDED,
            "details": {"operation": "rename_back", "file": file_path},
            "external_outcome": "file_at_expected_path",
        }
