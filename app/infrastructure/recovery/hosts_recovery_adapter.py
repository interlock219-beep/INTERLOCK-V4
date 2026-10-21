"""DNS hosts-file recovery adapter (Interlock V5).

Compensates protected DNS/host-entry mutations (``dns:<hostname>`` resources)
by restoring the exact set of hosts-file lines that previously resolved a
hostname.

Security properties:

- Hostname extraction validates a strict charset (letters, digits, ``.``,
  ``-``, ``_``); slashes, whitespace, NUL bytes, and ``#`` are rejected so a
  crafted resource cannot smuggle arbitrary lines into the file.
- The adapter only ever writes the hosts file it was configured with at
  construction time; a compensation payload pointing at a different path is
  rejected (fail closed) — evidence cannot redirect writes.
- Writes are atomic (temp file in the same directory + ``os.replace``) so a
  crash cannot truncate the hosts file.
- Tenant isolation, compensation authorization, and idempotency-key checks
  mirror the production filesystem adapter.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
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

_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,253}$")

_DNS_ACTION_TYPES = frozenset(
    {"dns_update", "dns_set", "hosts_update", "hosts_set", "hosts_delete", "dns_delete"}
)
_DNS_TOOLS = frozenset({"dns", "hosts", "hostsfile", "hosts_file", "resolve"})


def _default_hosts_path() -> Path:
    if os.name == "nt":
        # Windows env-var casing varies by version (os.environ lookups are
        # case-insensitive on win32) — keep the canonical mixed-case name.
        system_root = os.environ.get("SystemRoot", r"C:\Windows")  # noqa: SIM112
        return Path(system_root) / "System32" / "drivers" / "etc" / "hosts"
    return Path("/etc/hosts")


def _lines_digest(lines: list[str]) -> str:
    joined = "\n".join(lines)
    return hashlib.sha256(joined.encode("utf-8", errors="surrogateescape")).hexdigest()


def _file_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class HostsRecoveryAdapter(RecoveryAdapter):
    """Live hosts-file compensation adapter."""

    adapter_name = "hosts_recovery"
    adapter_type = "dns_hosts"
    capability = AdapterCapability.PRODUCTION_VALIDATED

    RESOURCE_PREFIX = "dns:"

    def __init__(self, hosts_path: str | Path | None = None) -> None:
        self._hosts_path = Path(hosts_path) if hosts_path is not None else _default_hosts_path()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def is_dns_resource(cls, resource: str) -> bool:
        return resource.startswith(cls.RESOURCE_PREFIX) or resource.startswith("hosts:")

    @classmethod
    def extract_hostname(cls, resource: str) -> str:
        if resource.startswith(cls.RESOURCE_PREFIX):
            raw = resource[len(cls.RESOURCE_PREFIX):]
        elif resource.startswith("hosts:"):
            raw = resource[len("hosts:"):]
        else:
            raw = resource
        hostname = raw.strip()
        if not _HOSTNAME_RE.match(hostname):
            raise ValueError(
                f"Invalid DNS resource hostname {hostname!r}: must be 1-253 chars of "
                "[A-Za-z0-9._-] with no slashes, whitespace, '#', or NUL bytes"
            )
        return hostname

    @staticmethod
    def _line_hostnames(line: str) -> list[str]:
        """Hostnames declared by one hosts-file line (comments ignored)."""
        code = line.split("#", 1)[0].strip()
        if not code:
            return []
        tokens = code.split()
        if len(tokens) < 2:
            return []
        return [t.lower() for t in tokens[1:]]

    @classmethod
    def _lines_for_hostname(cls, lines: list[str], hostname: str) -> list[str]:
        wanted = hostname.lower()
        return [line for line in lines if wanted in cls._line_hostnames(line)]

    @classmethod
    def _remove_hostname_lines(cls, lines: list[str], hostname: str) -> list[str]:
        wanted = hostname.lower()
        return [line for line in lines if wanted not in cls._line_hostnames(line)]

    @staticmethod
    def _reassemble(
        kept: list[str],
        previous: list[str],
        indices: list[int],
    ) -> list[str]:
        """Re-insert previous hostname lines at their recorded positions.

        Recorded indices make restore byte-order-faithful: the file returns to
        its exact pre-action content when no unrelated lines changed.  Legacy
        payloads without indices fall back to appending the block.
        """
        result = list(kept)
        if not previous:
            return result
        if not indices or len(indices) != len(previous):
            result.extend(previous)
            return result
        for offset, (index, line) in enumerate(zip(indices, previous, strict=False)):
            position = min(max(index + offset, 0), len(result))
            result[position:position] = [line]
        return result

    def _is_dns_action(self, action: ProtectedAction) -> bool:
        if self.is_dns_resource(action.resource):
            return True
        if action.action_type.lower() in _DNS_ACTION_TYPES:
            return True
        return action.tool.lower() in _DNS_TOOLS

    @staticmethod
    def _detect_newline(data: bytes) -> str:
        """Detect the dominant line ending so writes preserve byte fidelity."""
        crlf = data.count(b"\r\n")
        total_lf = data.count(b"\n")
        if crlf and crlf >= total_lf / 2:
            return "\r\n"
        return "\n"

    def _read_lines(self) -> tuple[bool, bytes, list[str]]:
        """Return ``(exists, raw_bytes, decoded_lines)`` for the hosts file."""
        if not self._hosts_path.is_file():
            return False, b"", []
        data = self._hosts_path.read_bytes()
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        return True, data, lines

    def _atomic_write(self, lines: list[str], newline: str = "\n") -> str:
        """Write hosts lines atomically; returns the SHA-256 of the new file."""
        content = newline.join(lines)
        if content:
            content += newline
        data = content.encode("utf-8")
        self._hosts_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=".hosts-", suffix=".tmp", dir=str(self._hosts_path.parent)
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self._hosts_path)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
            raise
        return _file_digest(data)

    # ------------------------------------------------------------------
    # Adapter contract
    # ------------------------------------------------------------------

    async def can_recover(self, action: ProtectedAction) -> str:
        rev = Reversibility.normalize(action.reversibility)
        if rev == Reversibility.IRREVERSIBLE:
            return "irreversible"
        if not self._is_dns_action(action):
            return "unsupported"
        if self._hosts_path.is_file():
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
            supports_versioning=False,
            supports_safe_merge=False,
            merge_safety=MergeSafety.MERGE_CONDITIONAL,
            declared_capabilities=[
                "dns_entry_restore",
                "hosts_file_atomic_write",
                "hostname_scoped_conflict_detection",
                "line_level_verification",
                "hostname_injection_guard",
            ],
        )

    async def capture_recovery_evidence(
        self,
        action: ProtectedAction,
        execution_context: dict[str, Any] | None = None,
        before_snapshot: dict[str, Any] | None = None,
    ) -> RecoveryEvidence:
        self._verify_tenant_isolation(action)
        hostname = self.extract_hostname(action.resource)

        file_exists, data, lines = self._read_lines()
        previous_lines = self._lines_for_hostname(lines, hostname)
        previous_indices = [
            index
            for index, line in enumerate(lines)
            if hostname.lower() in self._line_hostnames(line)
        ]
        after_lines = None
        if execution_context and "after_lines" in execution_context:
            after_lines = list(execution_context.get("after_lines") or [])

        payload = self._embed_tenant_context(
            action,
            {
                "operation": "restore_hosts_entry",
                "hosts_path": str(self._hosts_path),
                "hostname": hostname,
                "file_existed": file_exists,
                "file_sha256": _file_digest(data) if file_exists else None,
                "newline": self._detect_newline(data) if file_exists else "\n",
                "previous_lines": previous_lines,
                "previous_line_indices": previous_indices,
                "previous_lines_sha256": _lines_digest(previous_lines),
                "after_lines": after_lines,
                "after_lines_sha256": (
                    _lines_digest(after_lines) if after_lines is not None else None
                ),
            },
        )

        reversibility = Reversibility.normalize(action.reversibility)
        if not file_exists:
            reversibility = Reversibility.CONDITIONALLY_REVERSIBLE
        elif reversibility != Reversibility.IRREVERSIBLE:
            reversibility = Reversibility.AUTOMATICALLY_REVERSIBLE

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
            target_system="hosts_file",
            target_resource=action.resource,
            action_type=action.action_type,
            before_state_reference=(
                f"hosts:{hostname}:{payload['previous_lines_sha256']}"
                if file_exists
                else action.before_state_ref
            ),
            after_state_reference=(
                f"hosts:{hostname}:{payload['after_lines_sha256']}"
                if after_lines is not None
                else action.after_state_ref
            ),
            compensation_payload=payload,
            compensation_type=CompensationType.REVERSE_OPERATION,
            recovery_adapter_type=RecoveryAdapterType.DNS_HOSTS,
            idempotency_key=f"idem-{action.action_id}",
            dependency_edges=[],
            reversibility_classification=reversibility,
            adapter_capability=AdapterCapability.PRODUCTION_VALIDATED,
            verification_requirements=["hosts_entry_restored"],
        ))

    async def classify_reversibility(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> Reversibility:
        rev = Reversibility.normalize(action.reversibility)
        if rev == Reversibility.IRREVERSIBLE:
            return rev
        if evidence.compensation_payload.get("file_existed"):
            return Reversibility.AUTOMATICALLY_REVERSIBLE
        return Reversibility.CONDITIONALLY_REVERSIBLE

    async def simulate(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> RollbackImpact:
        rev = await self.classify_reversibility(action, evidence)
        payload = evidence.compensation_payload
        file_exists = self._hosts_path.is_file()
        warnings: list[str] = []
        if not file_exists:
            warnings.append("Hosts file does not exist: restore would fail")
        if not payload.get("file_existed"):
            warnings.append("No hosts file existed at capture time")
        warnings.append(
            f"Restore rewrites only '{payload.get('hostname')}' entries; other lines "
            "are preserved"
        )
        return RollbackImpact(
            action_id=action.action_id,
            reversibility=rev,
            would_succeed=file_exists and bool(payload.get("file_existed")),
            drift_status=DriftStatus.NO_DRIFT,
            conflict_status=ConflictStatus.NO_CONFLICT,
            compensation_operation="restore_hosts_entry",
            compensation_payload=payload,
            external_api_calls=[],
            warnings=warnings,
            simulation_limitation=SimulationLimitation.SIMULATION_LIMITED,
            expected_after_state={
                "hostname": payload.get("hostname"),
                "previous_lines_sha256": payload.get("previous_lines_sha256"),
            },
        )

    async def check_preconditions(
        self,
        action: ProtectedAction,
        current_state: dict[str, Any] | None = None,
    ) -> PreconditionResult:
        try:
            hostname = self.extract_hostname(action.resource)
        except ValueError as exc:
            return PreconditionResult(
                satisfied=False,
                failed_checks=["invalid_hostname"],
                details={"reason": str(exc)},
            )
        if not self._hosts_path.is_file():
            return PreconditionResult(
                satisfied=False,
                failed_checks=["hosts_file_missing"],
                details={"hosts_path": str(self._hosts_path)},
            )
        if not os.access(self._hosts_path, os.W_OK):
            return PreconditionResult(
                satisfied=False,
                failed_checks=["hosts_file_not_writable"],
                details={"hosts_path": str(self._hosts_path)},
            )
        return PreconditionResult(
            satisfied=True,
            details={"hostname": hostname, "hosts_path": str(self._hosts_path)},
        )

    async def detect_drift(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
        current_state: dict[str, Any] | None = None,
    ) -> DriftResult:
        payload = evidence.compensation_payload
        hostname = payload.get("hostname", "")
        previous = list(payload.get("previous_lines") or [])
        after = payload.get("after_lines")
        if not payload.get("file_existed"):
            return DriftResult(
                status=DriftStatus.INSUFFICIENT_EVIDENCE,
                details={"reason": "No hosts file snapshot recorded"},
            )
        file_exists, _data, lines = self._read_lines()
        if not file_exists:
            if after is not None:
                return DriftResult(
                    status=DriftStatus.RESOURCE_MISSING,
                    details={"hosts_path": str(self._hosts_path)},
                )
            # No after-state: the action itself may have removed the hosts
            # file (execution will surface REQUIRES_MANUAL_ACTION because the
            # full file content cannot be reconstructed from this evidence).
            return DriftResult(
                status=DriftStatus.INSUFFICIENT_EVIDENCE,
                details={"hosts_path": str(self._hosts_path)},
            )

        # Hostname-scoped comparison: unrelated entries changing must not read
        # as drift for this action's compensation.
        current_lines = self._lines_for_hostname(lines, hostname)
        if current_lines == previous:
            return DriftResult(
                status=DriftStatus.NO_DRIFT,
                current_state={"lines_sha256": _lines_digest(current_lines)},
            )
        if after is not None:
            if current_lines == list(after):
                return DriftResult(
                    status=DriftStatus.NO_DRIFT,
                    current_state={"lines_sha256": _lines_digest(current_lines)},
                    details={"reason": "Entries match the recorded after-action lines"},
                )
            return DriftResult(
                status=DriftStatus.DRIFT_DETECTED,
                details={
                    "hostname": hostname,
                    "previous_lines_sha256": _lines_digest(previous),
                    "after_lines_sha256": _lines_digest(list(after)),
                    "actual_lines_sha256": _lines_digest(current_lines),
                },
            )
        return DriftResult(
            status=DriftStatus.INSUFFICIENT_EVIDENCE,
            details={
                "hostname": hostname,
                "reason": (
                    "Entries differ from the before-state and no after-state was "
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
        hostname = payload.get("hostname", "")
        file_exists, _data, lines = self._read_lines()
        if not file_exists:
            after_lines = payload.get("after_lines")
            if after_lines is not None:
                return ConflictResult(
                    status=ConflictStatus.RESOURCE_MISSING,
                    details={"hosts_path": str(self._hosts_path)},
                )
            # No after-state recorded: the hosts file's removal may be the
            # action's own effect; execution decides whether an automatic
            # compensation is possible (it requires manual intervention for a
            # fully deleted file).
            return ConflictResult(
                status=ConflictStatus.NO_CONFLICT,
                details={"reason": "Hosts file missing; no after-state recorded"},
            )
        current_lines = self._lines_for_hostname(lines, hostname)
        previous = list(payload.get("previous_lines") or [])
        if current_lines == previous:
            return ConflictResult(status=ConflictStatus.NO_CONFLICT)
        after = payload.get("after_lines")
        if after is not None and current_lines == list(after):
            return ConflictResult(status=ConflictStatus.NO_CONFLICT)
        if after is not None:
            return ConflictResult(
                status=ConflictStatus.CONCURRENT_MUTATION,
                details={
                    "hostname": hostname,
                    "actual_lines_sha256": _lines_digest(current_lines),
                },
            )
        return ConflictResult(status=ConflictStatus.NO_CONFLICT)

    async def generate_compensation(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> CompensationAction:
        payload = self._embed_tenant_context(action, dict(evidence.compensation_payload))
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
        payload_hosts = payload.get("hosts_path")
        if payload_hosts and Path(payload_hosts) != self._hosts_path:
            return CompensationResult(
                action_id=compensation.action_id,
                success=False,
                execution_state=ExecutionState.BLOCKED_BY_CONFLICT,
                idempotency_key=idempotency_key,
                error=(
                    "Compensation payload targets a different hosts file than this "
                    "adapter is configured for; refusing write"
                ),
            )
        if not payload.get("file_existed"):
            return CompensationResult(
                action_id=compensation.action_id,
                success=False,
                execution_state=ExecutionState.REQUIRES_MANUAL_ACTION,
                idempotency_key=idempotency_key,
                error="No hosts file existed at capture time; refusing to recreate blindly",
            )

        hostname = payload.get("hostname")
        if not hostname:
            return CompensationResult(
                action_id=compensation.action_id,
                success=False,
                execution_state=ExecutionState.FAILED,
                idempotency_key=idempotency_key,
                error="Compensation payload has no hostname",
            )

        file_exists, _data, lines = self._read_lines()
        if not file_exists:
            # The whole file is gone.  Automatic compensation must not fabricate
            # a hosts file containing only the recorded hostname entries (every
            # other entry would silently vanish), so this requires a human.
            return CompensationResult(
                action_id=compensation.action_id,
                success=False,
                execution_state=ExecutionState.REQUIRES_MANUAL_ACTION,
                idempotency_key=idempotency_key,
                error=(
                    f"Hosts file missing: {self._hosts_path}. Automatic compensation "
                    "cannot recreate entries not recorded in evidence; manual "
                    "intervention required"
                ),
            )

        previous = list(payload.get("previous_lines") or [])
        kept = self._remove_hostname_lines(lines, hostname)
        restored = self._reassemble(
            kept, previous, list(payload.get("previous_line_indices") or [])
        )
        removed_count = len(lines) - len(kept)
        try:
            new_digest = self._atomic_write(
                restored, newline=payload.get("newline") or "\n"
            )
        except OSError as exc:
            return CompensationResult(
                action_id=compensation.action_id,
                success=False,
                execution_state=ExecutionState.FAILED,
                idempotency_key=idempotency_key,
                error=f"Hosts write failed: {exc}",
            )

        return CompensationResult(
            action_id=compensation.action_id,
            success=True,
            execution_state=ExecutionState.SUCCEEDED,
            idempotency_key=idempotency_key,
            details={
                "operation": "restore_hosts_entry",
                "hostname": hostname,
                "lines_removed": removed_count,
                "lines_restored": len(previous),
                "file_sha256": new_digest,
            },
            external_outcome="hosts_entry_restored",
        )

    async def verify(self, compensation: CompensationAction) -> VerificationResult:
        payload = compensation.compensation_payload
        hostname = payload.get("hostname")
        if not hostname:
            return VerificationResult(
                action_id=compensation.action_id,
                verified=False,
                details={"reason": "Compensation payload has no hostname"},
            )
        file_exists, _data, lines = self._read_lines()
        if not file_exists:
            return VerificationResult(
                action_id=compensation.action_id,
                verified=False,
                details={"reason": "Hosts file missing after restore"},
            )
        current = self._lines_for_hostname(lines, hostname)
        previous = list(payload.get("previous_lines") or [])
        return VerificationResult(
            action_id=compensation.action_id,
            verified=current == previous,
            details={
                "hostname": hostname,
                "expected_lines_sha256": _lines_digest(previous),
                "actual_lines_sha256": _lines_digest(current),
                "expected_line_count": len(previous),
                "actual_line_count": len(current),
            },
        )

    async def preview_recovery(self, action: ProtectedAction) -> dict[str, Any]:
        try:
            hostname = self.extract_hostname(action.resource)
            hostname_error = None
        except ValueError as exc:
            hostname = None
            hostname_error = str(exc)
        exists = self._hosts_path.is_file()
        return {
            "adapter": self.adapter_name,
            "adapter_type": self.adapter_type,
            "capability": self.capability.value,
            "action_id": action.action_id,
            "resource": action.resource,
            "hostname": hostname,
            "hostname_error": hostname_error,
            "hosts_path": str(self._hosts_path),
            "hosts_file_exists": exists,
            "reversible": exists and hostname_error is None,
            "operation": "restore_hosts_entry",
            "requires_approval": False,
        }

    async def execute_recovery(self, action: ProtectedAction, approved_by: str) -> dict[str, Any]:
        self._verify_tenant_isolation(action)
        try:
            hostname = self.extract_hostname(action.resource)
        except ValueError as exc:
            return {
                "adapter": self.adapter_name,
                "action_id": action.action_id,
                "status": "failed",
                "error": str(exc),
                "executed_by": approved_by,
            }
        snapshot = action.before_state_snapshot or {}
        if "lines" not in snapshot:
            return {
                "adapter": self.adapter_name,
                "action_id": action.action_id,
                "status": "failed",
                "error": "No previous hosts lines recorded for restore",
                "executed_by": approved_by,
            }
        previous = list(snapshot.get("lines") or [])
        file_exists, _data, lines = self._read_lines()
        if not file_exists:
            return {
                "adapter": self.adapter_name,
                "action_id": action.action_id,
                "status": "failed",
                "error": f"Hosts file missing: {self._hosts_path}",
                "executed_by": approved_by,
            }
        kept = self._remove_hostname_lines(lines, hostname)
        restored = self._reassemble(
            kept, previous, list(snapshot.get("line_indices") or [])
        )
        new_digest = self._atomic_write(
            restored, newline=self._detect_newline(_data) if file_exists else "\n"
        )
        return {
            "adapter": self.adapter_name,
            "action_id": action.action_id,
            "status": "restored",
            "hostname": hostname,
            "lines_restored": len(previous),
            "file_sha256": new_digest,
            "executed_by": approved_by,
        }
