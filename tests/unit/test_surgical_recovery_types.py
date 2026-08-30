from __future__ import annotations

from app.domain.entities.surgical_recovery_types import (
    AdapterCapability,
    CompensationType,
    ConflictStatus,
    DriftStatus,
    ExecutionState,
    RecoveryAdapterType,
    Reversibility,
    SimulationLimitation,
)


def test_reversibility_normalize_legacy_strings():
    assert Reversibility.normalize("reversible") == Reversibility.AUTOMATICALLY_REVERSIBLE
    assert (
        Reversibility.normalize("reversible_with_approval")
        == Reversibility.CONDITIONALLY_REVERSIBLE
    )
    assert Reversibility.normalize("irreversible") == Reversibility.IRREVERSIBLE


def test_reversibility_normalize_legacy_enum():
    assert (
        Reversibility.normalize(Reversibility.REVERSIBLE)
        == Reversibility.AUTOMATICALLY_REVERSIBLE
    )
    assert (
        Reversibility.normalize(Reversibility.REVERSIBLE_WITH_APPROVAL)
        == Reversibility.CONDITIONALLY_REVERSIBLE
    )


def test_reversibility_normalize_unknown_string():
    assert Reversibility.normalize("unknown") == Reversibility.UNKNOWN


def test_reversibility_normalize_canonical_enum():
    assert (
        Reversibility.normalize(Reversibility.AUTOMATICALLY_REVERSIBLE)
        == Reversibility.AUTOMATICALLY_REVERSIBLE
    )


def test_reversibility_is_auto_reversible():
    assert Reversibility.is_auto_reversible("reversible") is True
    assert Reversibility.is_auto_reversible("conditionally_reversible") is False


def test_reversibility_is_conditional():
    assert Reversibility.is_conditional("reversible_with_approval") is True
    assert Reversibility.is_conditional("reversible") is False


def test_reversibility_is_manual():
    assert Reversibility.is_manual("manually_recoverable") is True
    assert Reversibility.is_manual("irreversible") is False


def test_reversibility_blocks_automatic_execution():
    assert Reversibility.blocks_automatic_execution("irreversible") is True
    assert Reversibility.blocks_automatic_execution("reversible") is False
    assert Reversibility.blocks_automatic_execution("unknown") is True
    assert Reversibility.blocks_automatic_execution("manually_recoverable") is True


def test_recovery_adapter_type_values():
    assert RecoveryAdapterType.DATABASE_SQL.value == "database_sql"
    assert RecoveryAdapterType.UNSUPPORTED.value == "unsupported"


def test_adapter_capability_values():
    assert AdapterCapability.PRODUCTION_VALIDATED.value == "production_validated"
    assert AdapterCapability.MOCK.value == "mock"


def test_compensation_type_values():
    assert CompensationType.REVERSE_OPERATION.value == "reverse_operation"
    assert CompensationType.CUSTOM.value == "custom"


def test_conflict_status_values():
    assert ConflictStatus.NO_CONFLICT.value == "no_conflict"
    assert ConflictStatus.VERSION_MISMATCH.value == "version_mismatch"


def test_drift_status_values():
    assert DriftStatus.NO_DRIFT.value == "no_drift"
    assert DriftStatus.INSUFFICIENT_EVIDENCE.value == "insufficient_evidence"


def test_execution_state_values():
    assert ExecutionState.PENDING.value == "pending"
    assert ExecutionState.SUCCEEDED.value == "succeeded"
    assert ExecutionState.BLOCKED_BY_CONFLICT.value == "blocked_by_conflict"


def test_simulation_limitation_values():
    assert SimulationLimitation.SIMULATION_LIMITED.value == "simulation_limited"
    assert SimulationLimitation.SIMULATION_COMPLETE.value == "simulation_complete"
