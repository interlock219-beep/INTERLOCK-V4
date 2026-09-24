from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from app.domain.value_objects.authorization_decision import AuthorizationDecision

logger = logging.getLogger(__name__)


class ToolPermission(StrEnum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"
    NONE = "none"


class ToolCapability(StrEnum):
    READ_FILES = "read_files"
    WRITE_FILES = "write_files"
    EXECUTE_CODE = "execute_code"
    NETWORK_ACCESS = "network_access"
    DATABASE_ACCESS = "database_access"
    SYSTEM_COMMAND = "system_command"
    SECRETS_ACCESS = "secrets_access"


@dataclass(frozen=True, slots=True)
class ToolManifest:
    tool_id: str
    name: str
    version: str
    description: str
    owner: str
    capabilities: list[ToolCapability]
    permissions: list[ToolPermission]
    argument_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    signature_hash: str
    resource_constraints: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, str] = field(default_factory=dict)
    registered_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    call_id: str
    tool_id: str
    agent_id: str
    tenant_id: str
    arguments: dict[str, Any]
    result_hash: str | None
    permission_grant_id: str | None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ToolAnomalySignal:
    signal_type: str
    severity: str
    evidence: dict[str, Any]
    explanation: str


class ToolchainSecurityService:
    def __init__(self) -> None:
        self._tool_manifests: dict[str, ToolManifest] = {}
        self._tool_call_history: dict[str, list[ToolCallRecord]] = {}
        self._tool_baselines: dict[str, dict[str, Any]] = {}

    def register_tool(self, manifest: ToolManifest) -> ToolManifest:
        self._tool_manifests[manifest.tool_id] = manifest
        return manifest

    def get_tool_provenance(self, tool_id: str) -> dict[str, Any] | None:
        manifest = self._tool_manifests.get(tool_id)
        if not manifest:
            return None
        return {
            "tool_id": manifest.tool_id,
            "name": manifest.name,
            "version": manifest.version,
            "owner": manifest.owner,
            "signature_hash": manifest.signature_hash,
            "registered_at": manifest.registered_at.isoformat(),
            "capabilities": [c.value for c in manifest.capabilities],
            "permissions": [p.value for p in manifest.permissions],
        }

    def record_tool_call(self, record: ToolCallRecord) -> ToolCallRecord:
        key = record.tool_id
        if key not in self._tool_call_history:
            self._tool_call_history[key] = []
        self._tool_call_history[key].append(record)
        return record

    def compute_tool_signature(self, tool_implementation: str) -> str:
        return hashlib.sha256(tool_implementation.encode()).hexdigest()

    def verify_tool_signature(self, tool_id: str, presented_signature: str) -> tuple[bool, str]:
        manifest = self._tool_manifests.get(tool_id)
        if not manifest:
            return False, f"Tool {tool_id} not registered"
        if manifest.signature_hash != presented_signature:
            return False, f"Tool {tool_id} signature mismatch"
        return True, "Signature valid"

    def track_tool_version(self, tool_id: str, version: str, change_description: str = "") -> dict[str, Any]:
        manifest = self._tool_manifests.get(tool_id)
        if not manifest:
            return {"error": "Tool not registered"}
        old_version = manifest.version
        return {
            "tool_id": tool_id,
            "old_version": old_version,
            "new_version": version,
            "change_description": change_description,
            "updated_at": datetime.now(UTC).isoformat(),
        }

    def get_tool_version_history(self, tool_id: str) -> list[dict[str, Any]]:
        if tool_id in self._tool_manifests:
            return [{"tool_id": tool_id, "version": self._tool_manifests[tool_id].version}]
        return []

    def check_tool_permission(
        self,
        tool_id: str,
        requested_permission: ToolPermission,
        agent_grants: list[dict],
    ) -> tuple[bool, str]:
        manifest = self._tool_manifests.get(tool_id)
        if not manifest:
            return False, f"Tool {tool_id} not registered"
        if requested_permission not in manifest.permissions:
            return False, f"Permission {requested_permission.value} not in tool\'s allowed permissions"
        hierarchy = {"read": 1, "write": 2, "execute": 3, "admin": 4}
        max_granted = max(
            (hierarchy.get(g.get("permission", "none"), 0) for g in agent_grants),
            default=0,
        )
        required_level = hierarchy.get(requested_permission.value, 0)
        if max_granted < required_level:
            return False, f"Insufficient permission: required {requested_permission.value}, max granted lower"
        return True, "Permission check passed"

    def validate_capability_use(
        self,
        tool_id: str,
        capability: ToolCapability,
        context: dict[str, Any],
    ) -> tuple[bool, str]:
        manifest = self._tool_manifests.get(tool_id)
        if not manifest:
            return False, f"Tool {tool_id} not registered"
        if capability not in manifest.capabilities:
            return False, f"Tool {tool_id} does not declare capability {capability.value}"
        constraints = manifest.resource_constraints
        if constraints.get("network_access") is False and capability == ToolCapability.NETWORK_ACCESS:
            return False, "Tool manifest declares no network access"
        return True, "Capability validated"

    def validate_tool_arguments(self, tool_id: str, arguments: dict[str, Any]) -> tuple[bool, str | None]:
        manifest = self._tool_manifests.get(tool_id)
        if not manifest:
            return False, f"Tool {tool_id} not registered"
        schema = manifest.argument_schema
        required = schema.get("required", [])
        for param in required:
            if param not in arguments:
                return False, f"Missing required parameter: {param}"
        types = schema.get("types", {})
        for key, value in arguments.items():
            expected_type = types.get(key)
            if expected_type:
                if not self._check_type(value, expected_type):
                    return False, f"Parameter {key} type mismatch: expected {expected_type}"
        return True, None

    @staticmethod
    def _check_type(value: Any, expected_type: str) -> bool:
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        expected = type_map.get(expected_type)
        if expected is None:
            return True
        return isinstance(value, expected)

    def validate_tool_output(
        self,
        tool_id: str,
        output: Any,
        output_schema: dict[str, Any] | None = None,
    ) -> tuple[bool, str | None]:
        if output_schema is None:
            manifest = self._tool_manifests.get(tool_id)
            if manifest:
                output_schema = manifest.output_schema
        if output_schema is None:
            return True, None
        expected_type = output_schema.get("type")
        if expected_type:
            if not self._check_type(output, expected_type):
                return False, f"Tool output type mismatch: expected {expected_type}"
        max_size = output_schema.get("max_size_bytes")
        if max_size and isinstance(output, (str, bytes)):
            actual_size = len(output) if isinstance(output, str) else len(output)
            if actual_size > max_size:
                return False, f"Tool output exceeds max size: {actual_size} > {max_size}"
        return True, None

    def authorize_tool_call(
        self,
        tool_id: str,
        agent_id: str,
        tenant_id: str,
        arguments: dict[str, Any],
        authority_grants: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> tuple[AuthorizationDecision, str]:
        manifest = self._tool_manifests.get(tool_id)
        if not manifest:
            return AuthorizationDecision.DENY, f"Tool {tool_id} not registered"
        if manifest.resource_constraints.get("tenant_restricted"):
            allowed_tenants = manifest.resource_constraints.get("allowed_tenants", [])
            if tenant_id not in allowed_tenants:
                return AuthorizationDecision.DENY, f"Tool {tool_id} not available for tenant {tenant_id}"
        args_valid, args_error = self.validate_tool_arguments(tool_id, arguments)
        if not args_valid:
            return AuthorizationDecision.DENY, f"Invalid arguments: {args_error}"
        required_permission = (
            ToolPermission(manifest.permissions[0]) if manifest.permissions else ToolPermission.READ
        )
        perm_valid, perm_reason = self.check_tool_permission(tool_id, required_permission, authority_grants)
        if not perm_valid:
            return AuthorizationDecision.DENY, f"Permission denied: {perm_reason}"
        for capability in manifest.capabilities:
            cap_valid, cap_reason = self.validate_capability_use(tool_id, capability, context or {})
            if not cap_valid:
                return AuthorizationDecision.DENY, f"Capability denied: {cap_reason}"
        return AuthorizationDecision.ALLOW, "Tool call authorized"

    def detect_tool_anomalies(self, tool_id: str, recent_calls: list[ToolCallRecord]) -> list[ToolAnomalySignal]:
        signals = []
        if not recent_calls:
            return signals
        if len(recent_calls) > 100:
            signals.append(
                ToolAnomalySignal(
                    signal_type="unusual_frequency",
                    severity="high",
                    evidence={"call_count": len(recent_calls), "window": "recent"},
                    explanation=f"Tool {tool_id} called {len(recent_calls)} times recently",
                )
            )
        arg_sets = [tuple(sorted(call.arguments.items())) for call in recent_calls]
        unique_args = set(arg_sets)
        if len(unique_args) == 1 and len(recent_calls) > 10:
            signals.append(
                ToolAnomalySignal(
                    signal_type="repeated_identical_calls",
                    severity="medium",
                    evidence={"call_count": len(recent_calls), "unique_args": 1},
                    explanation=f"Tool {tool_id} called with identical arguments {len(recent_calls)} times",
                )
            )
        for call in recent_calls:
            args = call.arguments
            if isinstance(args, dict):
                if args.get("admin") or args.get("sudo") or args.get("root"):
                    signals.append(
                        ToolAnomalySignal(
                            signal_type="privilege_escalation_in_args",
                            severity="critical",
                            evidence={"call_id": call.call_id, "escalation_key": "admin/sudo/root"},
                            explanation="Privilege escalation keyword in tool arguments",
                        )
                    )
        return signals

    def contain_mcp_tool(self, tool_id: str, reason: str) -> dict[str, Any]:
        manifest = self._tool_manifests.get(tool_id)
        if not manifest:
            return {"error": f"Tool {tool_id} not found"}
        contained_caps = [c for c in manifest.capabilities if c in (ToolCapability.READ_FILES,)]
        contained_perms = [ToolPermission.READ]
        return {
            "tool_id": tool_id,
            "contained": True,
            "reason": reason,
            "original_capabilities": [c.value for c in manifest.capabilities],
            "contained_capabilities": [c.value for c in contained_caps],
            "original_permissions": [p.value for p in manifest.permissions],
            "contained_permissions": [p.value for p in contained_perms],
            "contained_at": datetime.now(UTC).isoformat(),
        }

    def get_mcp_containment_status(self, tool_id: str) -> dict[str, Any]:
        manifest = self._tool_manifests.get(tool_id)
        if not manifest:
            return {"error": "Tool not found"}
        return {
            "tool_id": tool_id,
            "is_contained": False,
            "active_capabilities": [c.value for c in manifest.capabilities],
            "active_permissions": [p.value for p in manifest.permissions],
        }
