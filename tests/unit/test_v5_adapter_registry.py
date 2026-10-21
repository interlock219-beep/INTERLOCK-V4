"""Interlock V5 — recovery adapter capability registry tests.

Covers contract validation (fail-closed registration), capability
declaration capture, resource-kind selection, action-based selection with
production-validated preference, and the capability matrix used by the V5
adapter capability matrix + certification lab.
"""

from __future__ import annotations

import pytest

from app.domain.entities.causal_state_types import (
    AdapterCapabilityDeclaration,
    MergeSafety,
)
from app.domain.entities.protected_action import ProtectedAction
from app.domain.services.recovery_adapter import RecoveryAdapter
from app.domain.services.recovery_adapter_registry import (
    AdapterContractError,
    RecoveryAdapterRegistry,
)
from app.infrastructure.recovery.environment_recovery_adapter import (
    EnvironmentRecoveryAdapter,
)


def _action(**overrides) -> ProtectedAction:
    base = {
        "action_id": "act-1",
        "tenant_id": "tenant-1",
        "actor_user_id": None,
        "agent_id": "agent-1",
        "authority_grant_id": None,
        "tool": "environment",
        "resource": "env:REGISTRY_TEST_VAR",
        "action_type": "set_env",
    }
    base.update(overrides)
    return ProtectedAction(**base)


class _BrokenNamelessAdapter(EnvironmentRecoveryAdapter):
    """Adapter with an empty name — must be rejected by contract validation."""

    adapter_name = ""


class _NonAsyncAdapter(EnvironmentRecoveryAdapter):
    """Adapter exposing a sync protocol method — contract violation."""

    async def can_recover(self, action: ProtectedAction) -> str:  # noqa: D401
        return "automatically_reversible"

    def declare_capabilities(self):  # type: ignore[override]
        return AdapterCapabilityDeclaration(
            adapter_name="environment_recovery", adapter_type="environment"
        )


class _BadDeclarationAdapter(EnvironmentRecoveryAdapter):
    """Declaration whose adapter_name does not match the adapter."""

    async def declare_capabilities(self) -> AdapterCapabilityDeclaration:
        return AdapterCapabilityDeclaration(
            adapter_name="some_other_adapter", adapter_type="environment"
        )


class _WrongTypeDeclarationAdapter(EnvironmentRecoveryAdapter):
    async def declare_capabilities(self):  # type: ignore[override]
        return {"not": "a declaration"}


async def test_validate_contract_accepts_production_adapter():
    validation = RecoveryAdapterRegistry.validate_contract(EnvironmentRecoveryAdapter())
    assert validation.ok is True
    assert validation.problems == ()


async def test_validate_contract_rejects_missing_name():
    validation = RecoveryAdapterRegistry.validate_contract(_BrokenNamelessAdapter())
    assert validation.ok is False
    assert any("adapter_name" in problem for problem in validation.problems)


async def test_validate_contract_rejects_sync_protocol_method():
    validation = RecoveryAdapterRegistry.validate_contract(_NonAsyncAdapter())
    assert validation.ok is False
    assert any("declare_capabilities" in problem for problem in validation.problems)


async def test_strict_register_rejects_broken_adapter():
    registry = RecoveryAdapterRegistry(strict=True)
    with pytest.raises(AdapterContractError):
        await registry.register(_BrokenNamelessAdapter(), resource_kinds=("env:",))
    assert len(registry) == 0


async def test_non_strict_register_still_rejects_broken_declaration():
    registry = RecoveryAdapterRegistry(strict=False)
    # Declaration mismatch is a hard contract violation even in non-strict mode.
    with pytest.raises(AdapterContractError):
        await registry.register(
            _BadDeclarationAdapter(), resource_kinds=("env:",)
        )
    assert len(registry) == 0


async def test_register_rejects_declaration_type_mismatch():
    registry = RecoveryAdapterRegistry()
    with pytest.raises(AdapterContractError):
        await registry.register(
            _WrongTypeDeclarationAdapter(), resource_kinds=("env:",)
        )


async def test_register_requires_resource_kinds():
    registry = RecoveryAdapterRegistry()
    with pytest.raises(AdapterContractError):
        await registry.register(EnvironmentRecoveryAdapter())


async def test_register_duplicate_name_requires_replace():
    registry = RecoveryAdapterRegistry()
    await registry.register(EnvironmentRecoveryAdapter(), resource_kinds=("env:",))
    with pytest.raises(AdapterContractError):
        await registry.register(EnvironmentRecoveryAdapter(), resource_kinds=("env:",))
    # Replacement is allowed explicitly.
    registration = await registry.register(
        EnvironmentRecoveryAdapter(), resource_kinds=("env:", "process_env:"), replace=True
    )
    assert registration.resource_kinds == ("env:", "process_env:")


async def test_get_require_and_unregister():
    registry = RecoveryAdapterRegistry()
    await registry.register(EnvironmentRecoveryAdapter(), resource_kinds=("env:",))

    assert registry.get("environment_recovery") is not None
    assert registry.get("missing") is None
    assert "environment_recovery" in registry
    with pytest.raises(AdapterContractError):
        registry.require("missing")

    assert registry.unregister("environment_recovery") is True
    assert registry.unregister("environment_recovery") is False
    assert len(registry) == 0


async def test_resource_kind_selection_prefers_longest_prefix():
    registry = RecoveryAdapterRegistry()

    class _EnvAdapter(EnvironmentRecoveryAdapter):
        adapter_name = "env_general"

    class _SpecificAdapter(EnvironmentRecoveryAdapter):
        adapter_name = "env_production"

        async def can_recover(self, action: ProtectedAction) -> str:
            return "conditionally_reversible"

    await registry.register(_EnvAdapter(), resource_kinds=("env:",))
    await registry.register(_SpecificAdapter(), resource_kinds=("env:PROD_",))

    matches = registry.adapters_for_resource_kind("env:PROD_TOKEN")
    assert [a.adapter_name for a in matches] == ["env_production", "env_general"]

    matches = registry.adapters_for_resource_kind("env:OTHER")
    assert [a.adapter_name for a in matches] == ["env_general"]

    assert registry.adapters_for_resource_kind("unrelated:x") == []


async def test_select_for_action_prefers_production_validated():
    registry = RecoveryAdapterRegistry()

    class _ReferenceEnvAdapter(EnvironmentRecoveryAdapter):
        adapter_name = "env_reference"
        capability = "reference_implementation"

    await registry.register(
        _ReferenceEnvAdapter(),
        resource_kinds=("env:",),
        production_validated=False,
    )
    await registry.register(
        EnvironmentRecoveryAdapter(), resource_kinds=("env:",), production_validated=True
    )

    selected = await registry.select_for_action(_action())
    names = [a.adapter_name for a in selected]
    assert names == ["environment_recovery", "env_reference"]


async def test_select_for_action_skips_unsupporting_adapters():
    registry = RecoveryAdapterRegistry()

    class _Unsupporting(EnvironmentRecoveryAdapter):
        adapter_name = "env_unsupporting"

        async def can_recover(self, action: ProtectedAction) -> str:
            return "unsupported"

    await registry.register(EnvironmentRecoveryAdapter(), resource_kinds=("env:",))
    await registry.register(_Unsupporting(), resource_kinds=("other:",))

    selected = await registry.select_for_action(_action())
    assert [a.adapter_name for a in selected] == ["environment_recovery"]


async def test_capability_matrix_and_refresh_declaration():
    registry = RecoveryAdapterRegistry()
    registration = await registry.register(
        EnvironmentRecoveryAdapter(), resource_kinds=("env:",)
    )
    assert isinstance(registration.declaration, AdapterCapabilityDeclaration)
    assert registration.declaration.adapter_name == "environment_recovery"
    assert registration.production_validated is True
    assert registration.capability == "production_validated"

    matrix = await registry.capability_matrix()
    assert len(matrix) == 1
    assert matrix[0].can_compensate is True
    assert matrix[0].merge_safety in set(MergeSafety)

    refreshed = await registry.refresh_declaration("environment_recovery")
    assert refreshed.adapter_name == "environment_recovery"
    with pytest.raises(AdapterContractError):
        await registry.refresh_declaration("missing")


async def test_capability_declaration_false_by_default_for_missing_adapter():
    registry = RecoveryAdapterRegistry()
    await registry.register(EnvironmentRecoveryAdapter(), resource_kinds=("env:",))
    declaration = (await registry.capability_matrix())[0]
    # Capability flags must be truthful: this adapter does no versioning or
    # safe-merge and must not claim them.
    assert declaration.supports_versioning is False
    assert declaration.supports_safe_merge is False
    assert declaration.can_detect_drift is True


async def test_legacy_adapter_contract_surface_enforced():
    """RecoveryAdapter subclasses must keep the legacy three-method surface."""
    registry = RecoveryAdapterRegistry()

    class _LegacyBroken(RecoveryAdapter):
        adapter_name = "legacy_broken"
        adapter_type = "stub"
        capability = "stub"

        async def declare_capabilities(self) -> AdapterCapabilityDeclaration:
            return AdapterCapabilityDeclaration(
                adapter_name="legacy_broken", adapter_type="stub"
            )

        async def can_recover(self, action: ProtectedAction) -> str:
            return "unsupported"

        async def preview_recovery(self, action: ProtectedAction) -> dict:
            return {}

        # A missing ``execute_recovery`` would make this class abstract and
        # un-instantiable; stubbing it with a non-callable keeps the class
        # instantiable while still violating the legacy contract surface.
        execute_recovery = None  # type: ignore[assignment]

        async def supports(self, action: ProtectedAction) -> bool:
            return False

        async def capture_recovery_evidence(
            self, action, execution_context=None, before_snapshot=None
        ):
            raise NotImplementedError

        async def classify_reversibility(self, action, evidence):
            from app.domain.entities.surgical_recovery_types import Reversibility

            return Reversibility.UNKNOWN

        async def simulate(self, action, evidence):
            raise NotImplementedError

        async def check_preconditions(self, action, current_state=None):
            raise NotImplementedError

        async def detect_drift(self, action, evidence, current_state=None):
            raise NotImplementedError

        async def generate_compensation(self, action, evidence):
            raise NotImplementedError

        async def execute_compensation(self, compensation, idempotency_key):
            raise NotImplementedError

        async def verify(self, compensation):
            raise NotImplementedError

        async def check_conflicts(self, action, evidence, current_state=None):
            raise NotImplementedError

    validation = RecoveryAdapterRegistry.validate_contract(_LegacyBroken())
    assert validation.ok is False
    assert any("execute_recovery" in problem for problem in validation.problems)

    registry = RecoveryAdapterRegistry()
    with pytest.raises(AdapterContractError):
        await registry.register(_LegacyBroken(), resource_kinds=("stub:",))
