from __future__ import annotations

from typing import Any

import pytest

from app.domain.services.toolchain_security_service import (
    ToolCallRecord,
    ToolCapability,
    ToolchainSecurityService,
    ToolManifest,
    ToolPermission,
)
from app.domain.value_objects.authorization_decision import AuthorizationDecision


@pytest.fixture()
def service() -> ToolchainSecurityService:
    return ToolchainSecurityService()


def _make_manifest(
    tool_id: str = "tool-1",
    capabilities: list[ToolCapability] | None = None,
    permissions: list[ToolPermission] | None = None,
    resource_constraints: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
) -> ToolManifest:
    return ToolManifest(
        tool_id=tool_id,
        name="ReadFile",
        version="1.0.0",
        description="Read files from disk",
        owner="platform",
        capabilities=capabilities if capabilities is not None else [ToolCapability.READ_FILES],
        permissions=permissions if permissions is not None else [ToolPermission.READ],
        argument_schema={"required": ["path"], "types": {"path": "string"}},
        output_schema=output_schema,
        signature_hash="abc123",
        resource_constraints=resource_constraints if resource_constraints is not None else {},
    )


def test_register_tool_creates_manifest(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest()
    result = service.register_tool(manifest)
    assert result.tool_id == "tool-1"
    assert "tool-1" in service._tool_manifests


def test_get_tool_provenance_returns_record(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest()
    service.register_tool(manifest)
    provenance = service.get_tool_provenance("tool-1")
    assert provenance is not None
    assert provenance["tool_id"] == "tool-1"
    assert provenance["name"] == "ReadFile"
    assert provenance["version"] == "1.0.0"
    assert provenance["owner"] == "platform"
    assert provenance["signature_hash"] == "abc123"


def test_record_tool_call_creates_audit_trail(service: ToolchainSecurityService) -> None:
    service.register_tool(_make_manifest())
    record = ToolCallRecord(
        call_id="call-1",
        tool_id="tool-1",
        agent_id="agent-1",
        tenant_id="tenant-1",
        arguments={"path": "/tmp/x"},
        result_hash="res1",
        permission_grant_id="grant-1",
    )
    result = service.record_tool_call(record)
    assert result.call_id == "call-1"
    assert len(service._tool_call_history["tool-1"]) == 1


def test_compute_tool_signature_deterministic(service: ToolchainSecurityService) -> None:
    sig1 = service.compute_tool_signature("implementation")
    sig2 = service.compute_tool_signature("implementation")
    assert sig1 == sig2
    assert len(sig1) == 64


def test_verify_tool_signature_valid(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest()
    service.register_tool(manifest)
    valid, reason = service.verify_tool_signature("tool-1", "abc123")
    assert valid is True
    assert reason == "Signature valid"


def test_verify_tool_signature_mismatch(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest()
    service.register_tool(manifest)
    valid, reason = service.verify_tool_signature("tool-1", "bad-signature")
    assert valid is False
    assert "signature mismatch" in reason


def test_tool_signature_unregistered_tool(service: ToolchainSecurityService) -> None:
    valid, reason = service.verify_tool_signature("missing", "abc")
    assert valid is False
    assert "not registered" in reason


def test_track_tool_version_records_change(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest()
    service.register_tool(manifest)
    result = service.track_tool_version("tool-1", "2.0.0", "Added feature")
    assert result["old_version"] == "1.0.0"
    assert result["new_version"] == "2.0.0"
    assert result["change_description"] == "Added feature"
    assert "updated_at" in result


def test_get_tool_version_history(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest()
    service.register_tool(manifest)
    history = service.get_tool_version_history("tool-1")
    assert len(history) == 1
    assert history[0]["version"] == "1.0.0"


def test_check_tool_permission_allows_matching(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest()
    service.register_tool(manifest)
    allowed, reason = service.check_tool_permission("tool-1", ToolPermission.READ, [{"permission": "read"}])
    assert allowed is True


def test_check_tool_permission_denies_insufficient(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest()
    service.register_tool(manifest)
    allowed, reason = service.check_tool_permission("tool-1", ToolPermission.ADMIN, [{"permission": "read"}])
    assert allowed is False


def test_tool_permission_hierarchy_enforcement(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest(permissions=[ToolPermission.READ, ToolPermission.WRITE])
    service.register_tool(manifest)
    allowed, _ = service.check_tool_permission("tool-1", ToolPermission.WRITE, [{"permission": "read"}])
    assert allowed is False
    allowed, _ = service.check_tool_permission("tool-1", ToolPermission.WRITE, [{"permission": "write"}])
    assert allowed is True


def test_validate_capability_use_allows_declared(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest()
    service.register_tool(manifest)
    valid, reason = service.validate_capability_use("tool-1", ToolCapability.READ_FILES, {})
    assert valid is True


def test_validate_capability_use_denies_undeclared(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest()
    service.register_tool(manifest)
    valid, reason = service.validate_capability_use("tool-1", ToolCapability.NETWORK_ACCESS, {})
    assert valid is False


def test_capability_resource_constraints(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest(
        capabilities=[ToolCapability.NETWORK_ACCESS],
        resource_constraints={"network_access": False},
    )
    service.register_tool(manifest)
    valid, reason = service.validate_capability_use("tool-1", ToolCapability.NETWORK_ACCESS, {})
    assert valid is False


def test_validate_tool_arguments_required_params(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest()
    service.register_tool(manifest)
    valid, error = service.validate_tool_arguments("tool-1", {})
    assert valid is False
    assert "Missing required parameter" in (error or "")


def test_validate_tool_arguments_type_check(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest()
    service.register_tool(manifest)
    valid, error = service.validate_tool_arguments("tool-1", {"path": 123})
    assert valid is False
    assert "type mismatch" in (error or "")


def test_validate_tool_output_type_check(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest(output_schema={"type": "string"})
    service.register_tool(manifest)
    valid, error = service.validate_tool_output("tool-1", 123)
    assert valid is False
    assert "type mismatch" in (error or "")


def test_validate_tool_output_size_limit(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest(output_schema={"type": "string", "max_size_bytes": 5})
    service.register_tool(manifest)
    valid, error = service.validate_tool_output("tool-1", "too long output")
    assert valid is False
    assert "exceeds max size" in (error or "")


def test_output_schema_max_size_enforced(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest(output_schema={"max_size_bytes": 4})
    service.register_tool(manifest)
    valid, error = service.validate_tool_output("tool-1", "hello")
    assert valid is False
    assert "exceeds max size" in (error or "")


def test_authorize_tool_call_allows_valid(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest()
    service.register_tool(manifest)
    decision, reason = service.authorize_tool_call(
        "tool-1",
        "agent-1",
        "tenant-1",
        {"path": "/tmp/x"},
        [{"permission": "read"}],
    )
    assert decision == AuthorizationDecision.ALLOW


def test_authorize_tool_call_denies_unregistered_tool(service: ToolchainSecurityService) -> None:
    decision, reason = service.authorize_tool_call(
        "missing",
        "agent-1",
        "tenant-1",
        {},
        [],
    )
    assert decision == AuthorizationDecision.DENY
    assert "not registered" in reason


def test_authorize_tool_call_denies_invalid_args(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest()
    service.register_tool(manifest)
    decision, reason = service.authorize_tool_call(
        "tool-1",
        "agent-1",
        "tenant-1",
        {},
        [{"permission": "read"}],
    )
    assert decision == AuthorizationDecision.DENY
    assert "Invalid arguments" in reason


def test_authorize_tool_call_denies_tenant_restricted(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest(
        resource_constraints={"tenant_restricted": True, "allowed_tenants": ["tenant-2"]}
    )
    service.register_tool(manifest)
    decision, reason = service.authorize_tool_call(
        "tool-1",
        "agent-1",
        "tenant-1",
        {"path": "/tmp/x"},
        [{"permission": "read"}],
    )
    assert decision == AuthorizationDecision.DENY
    assert "not available for tenant" in reason


def test_authorize_tool_call_permission_grant_check(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest(permissions=[ToolPermission.EXECUTE])
    service.register_tool(manifest)
    decision, reason = service.authorize_tool_call(
        "tool-1",
        "agent-1",
        "tenant-1",
        {"path": "/tmp/x"},
        [{"permission": "read"}],
    )
    assert decision == AuthorizationDecision.DENY
    assert "Permission denied" in reason


def test_detect_tool_anomalies_high_frequency(service: ToolchainSecurityService) -> None:
    service.register_tool(_make_manifest())
    calls = [
        ToolCallRecord(
            call_id=f"call-{i}",
            tool_id="tool-1",
            agent_id="agent-1",
            tenant_id="tenant-1",
            arguments={"x": i},
            result_hash=None,
            permission_grant_id=None,
        )
        for i in range(101)
    ]
    signals = service.detect_tool_anomalies("tool-1", calls)
    assert any(s.signal_type == "unusual_frequency" for s in signals)


def test_detect_tool_anomalies_repeated_calls(service: ToolchainSecurityService) -> None:
    service.register_tool(_make_manifest())
    calls = [
        ToolCallRecord(
            call_id=f"call-{i}",
            tool_id="tool-1",
            agent_id="agent-1",
            tenant_id="tenant-1",
            arguments={"same": True},
            result_hash=None,
            permission_grant_id=None,
        )
        for i in range(11)
    ]
    signals = service.detect_tool_anomalies("tool-1", calls)
    assert any(s.signal_type == "repeated_identical_calls" for s in signals)


def test_detect_tool_anomalies_privilege_escalation(service: ToolchainSecurityService) -> None:
    service.register_tool(
        _make_manifest(capabilities=[ToolCapability.SYSTEM_COMMAND], permissions=[ToolPermission.EXECUTE])
    )
    calls = [
        ToolCallRecord(
            call_id="call-1",
            tool_id="tool-1",
            agent_id="agent-1",
            tenant_id="tenant-1",
            arguments={"admin": True},
            result_hash=None,
            permission_grant_id=None,
        )
    ]
    signals = service.detect_tool_anomalies("tool-1", calls)
    assert any(s.signal_type == "privilege_escalation_in_args" for s in signals)


def test_tool_anomaly_no_calls_returns_empty(service: ToolchainSecurityService) -> None:
    signals = service.detect_tool_anomalies("tool-1", [])
    assert signals == []


def test_contain_mcp_tool_restricts_capabilities(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest(
        capabilities=[ToolCapability.READ_FILES, ToolCapability.WRITE_FILES, ToolCapability.SYSTEM_COMMAND]
    )
    service.register_tool(manifest)
    result = service.contain_mcp_tool("tool-1", "suspicious activity")
    assert result["contained"] is True
    assert ToolCapability.READ_FILES.value in result["contained_capabilities"]
    assert ToolCapability.SYSTEM_COMMAND.value not in result["contained_capabilities"]


def test_get_mcp_containment_status(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest()
    service.register_tool(manifest)
    status = service.get_mcp_containment_status("tool-1")
    assert status["tool_id"] == "tool-1"
    assert status["is_contained"] is False
    assert ToolCapability.READ_FILES.value in status["active_capabilities"]


def test_mcp_containment_preserves_read_only(service: ToolchainSecurityService) -> None:
    manifest = _make_manifest(
        capabilities=[ToolCapability.READ_FILES, ToolCapability.WRITE_FILES]
    )
    service.register_tool(manifest)
    result = service.contain_mcp_tool("tool-1", "test")
    assert ToolCapability.READ_FILES.value in result["contained_capabilities"]
    assert ToolCapability.WRITE_FILES.value not in result["contained_capabilities"]
