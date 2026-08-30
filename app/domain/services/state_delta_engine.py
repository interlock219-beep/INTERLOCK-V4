from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime
from typing import Any

from app.domain.entities.causal_state_types import (
    ChangeOrigin,
    DeltaType,
    ResourceVersion,
    StateCheckpoint,
    StateDelta,
)
from app.domain.repositories.causal_state_repositories import (
    ResourceVersionRepository,
    StateCheckpointRepository,
    StateDeltaRepository,
)


class StateDeltaEngine:
    """Adapter-aware engine for computing state differences.

    Compares BEFORE STATE with AFTER AI ACTION and CURRENT STATE to
    determine:

    * AI_DELTA = AFTER_AI_STATE - BEFORE_STATE
    * UNRELATED_DELTA = CURRENT_STATE - AFTER_AI_STATE

    The objective is:

    TARGET_RECOVERED_STATE = CURRENT_STATE - AI_CAUSED_DELTA

    BUT: every adapter must define how state differences are safely
    interpreted. Naive JSON subtraction is NOT applied to arbitrary data.

    If a safe delta cannot be computed, the engine reports
    MANUALLY_RECOVERABLE or UNKNOWN.
    """

    def __init__(
        self,
        checkpoint_repo: StateCheckpointRepository,
        version_repo: ResourceVersionRepository,
        delta_repo: StateDeltaRepository,
    ) -> None:
        self._checkpoint_repo = checkpoint_repo
        self._version_repo = version_repo
        self._delta_repo = delta_repo

    async def compute_ai_delta(
        self,
        tenant_id: str,
        resource_id: str,
        before_state: dict[str, Any] | None,
        after_state: dict[str, Any] | None,
        action_id: str = "",
    ) -> StateDelta:
        """Compute the AI-caused delta: AFTER_STATE - BEFORE_STATE."""
        delta_id = f"delta-{secrets.token_hex(12)}"
        created_at = datetime.now(UTC)

        if before_state is None or after_state is None:
            delta = StateDelta(
                delta_id=delta_id,
                tenant_id=tenant_id,
                resource_id=resource_id,
                delta_type=DeltaType.UNKNOWN,
                created_at=created_at,
                is_safe_delta=False,
                delta_metadata={
                    "reason": "Insufficient state to compute delta",
                    "before_available": before_state is not None,
                    "after_available": after_state is not None,
                },
            )
            return await self._delta_repo.save(delta)

        if isinstance(before_state, dict) and isinstance(after_state, dict):
            return await self._compute_dict_delta(
                tenant_id, resource_id, before_state, after_state, action_id, delta_id, created_at
            )

        delta = StateDelta(
            delta_id=delta_id,
            tenant_id=tenant_id,
            resource_id=resource_id,
            delta_type=DeltaType.UNKNOWN,
            created_at=created_at,
            is_safe_delta=False,
            delta_metadata={
                "reason": "Unsupported state type for delta computation",
                "before_type": type(before_state).__name__,
                "after_type": type(after_state).__name__,
            },
        )
        return await self._delta_repo.save(delta)

    async def compute_unrelated_delta(
        self,
        tenant_id: str,
        resource_id: str,
        after_ai_state: dict[str, Any] | None,
        current_state: dict[str, Any] | None,
    ) -> StateDelta:
        """Compute the unrelated delta: CURRENT_STATE - AFTER_AI_STATE."""
        delta_id = f"delta-{secrets.token_hex(12)}"
        created_at = datetime.now(UTC)

        if after_ai_state is None or current_state is None:
            delta = StateDelta(
                delta_id=delta_id,
                tenant_id=tenant_id,
                resource_id=resource_id,
                delta_type=DeltaType.UNKNOWN,
                created_at=created_at,
                is_safe_delta=False,
                delta_metadata={
                    "reason": "Insufficient state to compute unrelated delta",
                    "after_available": after_ai_state is not None,
                    "current_available": current_state is not None,
                },
            )
            return await self._delta_repo.save(delta)

        if isinstance(after_ai_state, dict) and isinstance(current_state, dict):
            return await self._compute_dict_delta(
                tenant_id, resource_id, after_ai_state, current_state,
                "", delta_id, created_at,
            )

        delta = StateDelta(
            delta_id=delta_id,
            tenant_id=tenant_id,
            resource_id=resource_id,
            delta_type=DeltaType.UNKNOWN,
            created_at=created_at,
            is_safe_delta=False,
        )
        return await self._delta_repo.save(delta)

    async def determine_target_recovered_state(
        self,
        tenant_id: str,
        resource_id: str,
        current_state: dict[str, Any],
        ai_delta: StateDelta,
    ) -> dict[str, Any]:
        """Determine the target recovered state: CURRENT_STATE - AI_DELTA.

        Only applies safe field-level subtraction. If the delta is not
        safe, returns the current state unchanged and reports that manual
        recovery is required.
        """
        if not ai_delta.is_safe_delta:
            return {
                "_recovery_status": "MANUALLY_RECOVERABLE",
                "_reason": "AI delta is not safe for automatic subtraction",
                "_current_state": current_state,
            }

        if ai_delta.delta_type == DeltaType.FIELD_LEVEL:
            recovered = dict(current_state)
            for field_name, before_value in ai_delta.before_values.items():
                if field_name in recovered:
                    recovered[field_name] = before_value
            for field_name in ai_delta.added_fields:
                recovered.pop(field_name, None)
            return recovered

        if ai_delta.delta_type == DeltaType.VERSION_RESTORE:
            return {
                "_recovery_status": "VERSION_RESTORE_REQUIRED",
                "_target_version": ai_delta.before_version_id,
                "_current_state": current_state,
            }

        return {
            "_recovery_status": "MANUALLY_RECOVERABLE",
            "_reason": f"Delta type {ai_delta.delta_type.value} requires manual interpretation",
            "_current_state": current_state,
        }

    async def record_resource_version(
        self,
        tenant_id: str,
        resource_id: str,
        resource_type: str,
        state: dict[str, Any] | None,
        change_origin: ChangeOrigin,
        action_id: str = "",
        agent_id: str = "",
        causal_owner: str = "",
    ) -> ResourceVersion:
        """Record a new version in the resource's lineage."""
        latest = await self._version_repo.get_latest_version(tenant_id, resource_id)
        version_number = (latest.version_number + 1) if latest else 1
        previous_id = latest.version_id if latest else None

        state_hash = self._compute_state_hash(state) if state else None

        version = ResourceVersion(
            version_id=f"ver-{secrets.token_hex(12)}",
            tenant_id=tenant_id,
            resource_id=resource_id,
            resource_type=resource_type,
            version_number=version_number,
            change_origin=change_origin,
            causal_owner=causal_owner or agent_id,
            created_at=datetime.now(UTC),
            state_hash=state_hash,
            action_id=action_id,
            agent_id=agent_id,
            previous_version_id=previous_id,
        )
        return await self._version_repo.save(version)

    async def create_checkpoint(
        self,
        tenant_id: str,
        action_id: str,
        agent_id: str,
        resource_id: str,
        resource_type: str,
        state: dict[str, Any] | None,
        strategy: str = "full_state",
        version_token: str | None = None,
        etag: str | None = None,
    ) -> StateCheckpoint:
        """Create a recovery checkpoint before a high-impact action."""
        checkpoint_id = f"cp-{secrets.token_hex(12)}"
        state_hash = self._compute_state_hash(state) if state else None

        recoverable_fields: dict[str, Any] = {}
        if isinstance(state, dict):
            recoverable_fields = dict(state)

        checkpoint = StateCheckpoint(
            checkpoint_id=checkpoint_id,
            tenant_id=tenant_id,
            action_id=action_id,
            agent_id=agent_id,
            resource_id=resource_id,
            resource_type=resource_type,
            strategy=strategy,  # type: ignore[arg-type]
            created_at=datetime.now(UTC),
            state_hash=state_hash,
            recoverable_fields=recoverable_fields,
            version_token=version_token,
            etag=etag,
            checkpoint_hash=self._compute_checkpoint_hash(
                checkpoint_id, action_id, resource_id, state_hash, recoverable_fields
            ),
        )
        return await self._checkpoint_repo.save(checkpoint)

    async def verify_checkpoint_integrity(
        self, tenant_id: str, checkpoint_id: str
    ) -> dict[str, Any]:
        """Verify that a checkpoint has not been tampered with."""
        checkpoint = await self._checkpoint_repo.get_by_checkpoint_id(tenant_id, checkpoint_id)
        if checkpoint is None:
            return {
                "valid": False,
                "reason": "Checkpoint not found",
            }

        expected_hash = self._compute_checkpoint_hash(
            checkpoint.checkpoint_id,
            checkpoint.action_id,
            checkpoint.resource_id,
            checkpoint.state_hash,
            checkpoint.recoverable_fields,
        )

        if checkpoint.checkpoint_hash and checkpoint.checkpoint_hash != expected_hash:
            return {
                "valid": False,
                "reason": "Checkpoint hash mismatch — possible tampering",
                "expected": expected_hash,
                "actual": checkpoint.checkpoint_hash,
            }

        if checkpoint.checkpoint_hash == "":
            return {
                "valid": False,
                "reason": "Checkpoint has no hash — cannot verify integrity",
            }

        return {
            "valid": True,
            "reason": "Checkpoint integrity verified",
        }

    async def _compute_dict_delta(
        self,
        tenant_id: str,
        resource_id: str,
        before: dict[str, Any],
        after: dict[str, Any],
        action_id: str,
        delta_id: str,
        created_at: datetime,
    ) -> StateDelta:
        all_keys = set(before.keys()) | set(after.keys())
        changed_fields: list[str] = []
        added_fields: list[str] = []
        removed_fields: list[str] = []
        before_values: dict[str, Any] = {}
        after_values: dict[str, Any] = {}

        for key in sorted(all_keys):
            in_before = key in before
            in_after = key in after
            if in_before and in_after:
                if before[key] != after[key]:
                    changed_fields.append(key)
                    before_values[key] = before[key]
                    after_values[key] = after[key]
            elif in_before and not in_after:
                removed_fields.append(key)
                before_values[key] = before[key]
            else:
                added_fields.append(key)
                after_values[key] = after[key]

        is_safe = len(changed_fields) > 0 or len(added_fields) > 0 or len(removed_fields) > 0

        delta = StateDelta(
            delta_id=delta_id,
            tenant_id=tenant_id,
            resource_id=resource_id,
            delta_type=DeltaType.FIELD_LEVEL if is_safe else DeltaType.UNKNOWN,
            created_at=created_at,
            changed_fields=changed_fields,
            added_fields=added_fields,
            removed_fields=removed_fields,
            before_values=before_values,
            after_values=after_values,
            is_safe_delta=is_safe,
            delta_metadata={
                "total_fields": len(all_keys),
                "changed_count": len(changed_fields),
                "added_count": len(added_fields),
                "removed_count": len(removed_fields),
                "action_id": action_id,
            },
        )
        return await self._delta_repo.save(delta)

    @staticmethod
    def _compute_state_hash(state: dict[str, Any]) -> str:
        payload = json.dumps(state, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _compute_checkpoint_hash(
        checkpoint_id: str,
        action_id: str,
        resource_id: str,
        state_hash: str | None,
        recoverable_fields: dict[str, Any],
    ) -> str:
        payload = json.dumps({
            "checkpoint_id": checkpoint_id,
            "action_id": action_id,
            "resource_id": resource_id,
            "state_hash": state_hash,
            "fields": recoverable_fields,
        }, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()
