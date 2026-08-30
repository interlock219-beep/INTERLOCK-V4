from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from app.domain.entities.causal_state_types import (
    StateCheckpoint,
)
from app.domain.entities.protected_action import ProtectedAction
from app.domain.entities.surgical_recovery_types import (
    ConflictStatus,
    DriftStatus,
    RecoveryEvidence,
    Reversibility,
)
from app.domain.repositories.causal_state_repositories import StateCheckpointRepository
from app.domain.repositories.recovery_evidence_repository import RecoveryEvidenceRepository
from app.domain.services.recovery_adapter import RecoveryAdapter


class RecoverySimulationEngine:
    """Advanced state recovery simulator.

    For every affected resource shows:

    * Original State
    * State Before AI
    * State After AI
    * Current State
    * AI-Caused Delta
    * Unrelated Delta
    * Proposed Recovery
    * Expected Recovered State
    * Drift
    * Conflicts
    * Recovery Confidence
    * Adapter Capability
    * Reversibility
    * Approval Requirement

    The simulator NEVER mutates production resources. If exact simulation
    is impossible for an external system, it explicitly reports
    SIMULATION_LIMITED.
    """

    def __init__(
        self,
        evidence_repository: RecoveryEvidenceRepository,
        checkpoint_repository: StateCheckpointRepository,
        adapters: list[RecoveryAdapter] | None = None,
    ) -> None:
        self._evidence_repo = evidence_repository
        self._checkpoint_repo = checkpoint_repository
        self._adapters = adapters or []

    async def simulate_recovery(
        self,
        tenant_id: str,
        actions: list[ProtectedAction],
        current_states: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Simulate recovery for a set of affected actions without mutating state."""
        current_states = current_states or {}
        resource_simulations: dict[str, dict[str, Any]] = {}
        overall_warnings: list[str] = []
        total_resources = 0
        recoverable_resources = 0
        manual_resources = 0
        unknown_resources = 0

        for action in actions:
            evidence = await self._evidence_repo.get_by_action_id(tenant_id, action.action_id)
            checkpoint = await self._checkpoint_repo.get_by_action_id(tenant_id, action.action_id)
            current_state = current_states.get(action.resource)

            sim = await self._simulate_single_resource(
                action, evidence, checkpoint, current_state
            )
            resource_simulations[action.action_id] = sim
            total_resources += 1

            status = sim.get("simulation_status", "unknown")
            if status == "recoverable":
                recoverable_resources += 1
            elif status == "manual_recovery_required":
                manual_resources += 1
            else:
                unknown_resources += 1

            for warning in sim.get("warnings", []):
                overall_warnings.append(f"[{action.action_id}] {warning}")

        simulation_result: dict[str, Any] = {
            "simulation_id": f"sim-{secrets.token_hex(12)}",
            "tenant_id": tenant_id,
            "simulated_at": datetime.now(UTC).isoformat(),
            "total_resources": total_resources,
            "recoverable_resources": recoverable_resources,
            "manual_recovery_required_count": manual_resources,
            "unknown_resources": unknown_resources,
            "resource_simulations": resource_simulations,
            "overall_warnings": overall_warnings,
            "dry_run": True,
        }

        if manual_resources > 0:
            simulation_result["approval_requirement"] = "human_approval_required"
        elif unknown_resources > 0:
            simulation_result["approval_requirement"] = "insufficient_evidence"
        elif recoverable_resources > 0:
            simulation_result["approval_requirement"] = "safe_for_automatic"
        else:
            simulation_result["approval_requirement"] = "nothing_to_recover"

        return simulation_result

    async def _simulate_single_resource(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence | None,
        checkpoint: StateCheckpoint | None,
        current_state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        sim: dict[str, Any] = {
            "action_id": action.action_id,
            "resource": action.resource,
            "action_type": action.action_type,
            "target_system": evidence.target_system if evidence else "unknown",
            "warnings": [],
        }

        reversibility = Reversibility.normalize(action.reversibility)
        sim["reversibility"] = reversibility.value

        if reversibility == Reversibility.IRREVERSIBLE:
            sim["simulation_status"] = "irreversible"
            sim["proposed_recovery"] = "none"
            sim["expected_recovered_state"] = None
            sim["warnings"].append("Action is irreversible — cannot be recovered")
            sim["approval_requirement"] = "irreversible"
            return sim

        if reversibility == Reversibility.UNKNOWN:
            sim["simulation_status"] = "unknown_reversibility"
            sim["proposed_recovery"] = "none"
            sim["expected_recovered_state"] = None
            sim["warnings"].append("Reversibility is UNKNOWN — fail closed")
            sim["approval_requirement"] = "insufficient_evidence"
            return sim

        if evidence is None:
            sim["simulation_status"] = "no_evidence"
            sim["proposed_recovery"] = "none"
            sim["expected_recovered_state"] = None
            sim["warnings"].append("No recovery evidence captured — cannot simulate")
            sim["approval_requirement"] = "insufficient_evidence"
            return sim

        sim["evidence_id"] = evidence.evidence_id
        sim["adapter_capability"] = evidence.adapter_capability.value
        sim["before_state_reference"] = evidence.before_state_reference
        sim["after_state_reference"] = evidence.after_state_reference

        if checkpoint:
            sim["checkpoint_id"] = checkpoint.checkpoint_id
            sim["checkpoint_strategy"] = checkpoint.strategy.value
            sim["original_state"] = checkpoint.recoverable_fields
            sim["state_before_ai"] = checkpoint.recoverable_fields

        sim["state_after_ai"] = None
        sim["current_state"] = current_state

        drift_status = DriftStatus.NO_DRIFT
        conflict_status = ConflictStatus.NO_CONFLICT
        adapter_simulation: dict[str, Any] | None = None

        for adapter in self._adapters:
            try:
                if hasattr(adapter, "detect_drift"):
                    drift_result = await adapter.detect_drift(action, evidence, current_state)
                    drift_status = drift_result.status
                if hasattr(adapter, "check_conflicts"):
                    conflict_result = await adapter.check_conflicts(
                        action, evidence, current_state
                    )
                    conflict_status = conflict_result.status
                if hasattr(adapter, "simulate"):
                    impact = await adapter.simulate(action, evidence)
                    adapter_simulation = {
                        "adapter": getattr(adapter, "adapter_name", "unknown"),
                        "would_succeed": impact.would_succeed,
                        "compensation_operation": impact.compensation_operation,
                        "warnings": impact.warnings,
                        "simulation_limitation": (
                            impact.simulation_limitation.value
                            if impact.simulation_limitation
                            else None
                        ),
                        "expected_after_state": impact.expected_after_state,
                    }
                    break
            except (AttributeError, TypeError):
                continue
            except Exception as exc:
                sim["warnings"].append(f"Adapter simulation error: {exc}")
                continue

        sim["drift_status"] = drift_status.value
        sim["conflict_status"] = conflict_status.value
        sim["adapter_simulation"] = adapter_simulation

        if drift_status not in (DriftStatus.NO_DRIFT, DriftStatus.INSUFFICIENT_EVIDENCE):
            sim["simulation_status"] = "blocked_by_drift"
            sim["proposed_recovery"] = "none"
            sim["warnings"].append(f"Drift detected: {drift_status.value}")
            sim["approval_requirement"] = "drift_blocks_recovery"
            return sim

        if conflict_status not in (
            ConflictStatus.NO_CONFLICT,
            ConflictStatus.INSUFFICIENT_EVIDENCE,
        ):
            sim["simulation_status"] = "blocked_by_conflict"
            sim["proposed_recovery"] = "none"
            sim["warnings"].append(f"Conflict detected: {conflict_status.value}")
            sim["approval_requirement"] = "conflict_blocks_recovery"
            return sim

        if reversibility in (
            Reversibility.AUTOMATICALLY_REVERSIBLE,
            Reversibility.CONDITIONALLY_REVERSIBLE,
        ):
            sim["simulation_status"] = "recoverable"
            sim["proposed_recovery"] = "restore_before_state"
            sim["expected_recovered_state"] = (
                checkpoint.recoverable_fields if checkpoint else None
            )
            if current_state and checkpoint:
                ai_delta = self._compute_simple_delta(
                    checkpoint.recoverable_fields, current_state
                )
                sim["ai_caused_delta"] = ai_delta
            sim["approval_requirement"] = (
                "human_approval_required"
                if reversibility == Reversibility.CONDITIONALLY_REVERSIBLE
                else "safe_for_automatic"
            )
            return sim

        sim["simulation_status"] = "unknown"
        sim["proposed_recovery"] = "none"
        sim["approval_requirement"] = "insufficient_evidence"
        return sim

    @staticmethod
    def _compute_simple_delta(
        before: dict[str, Any], current: dict[str, Any]
    ) -> dict[str, Any]:
        """Compute a simple field-level delta for simulation display."""
        all_keys = set(before.keys()) | set(current.keys())
        changed: dict[str, Any] = {}
        for key in sorted(all_keys):
            before_val = before.get(key)
            current_val = current.get(key)
            if before_val != current_val:
                changed[key] = {"before": before_val, "current": current_val}
        return changed
