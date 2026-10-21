"""WP-1: canonical evidence integrity v2 — sealing, verification, compatibility.

Covers:
- canonical equivalence (metadata ordering, recompute stability)
- tamper detection on every hashed field (field-omission guard)
- malformed / missing / unsupported v2 evidence rejected safely
- legacy v1 evidence keeps field-presence path and never claims v2
- adapter parity: all production adapters seal captured evidence as v2
- persistence round-trip through SQLAlchemy repository
- documented downgrade limitation (marker removal reclassifies as v1)
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta
from enum import Enum
from typing import Any
from uuid import uuid4

import pytest

from app.domain.entities.protected_action import (
    ActionStatus,
    ProtectedAction,
    Reversibility,
)
from app.domain.entities.surgical_recovery_types import RecoveryEvidence
from app.domain.services.evidence_hash import (
    EVIDENCE_HASH_SPEC_KEY,
    EVIDENCE_HASH_SPEC_V2,
    canonical_evidence_json,
    compute_evidence_hash_v2,
    seal_evidence,
)
from app.domain.services.evidence_verification_service import EvidenceVerificationService


def _evidence(**overrides: Any) -> RecoveryEvidence:
    base: dict[str, Any] = dict(
        evidence_id="ev-1",
        action_id="act-1",
        tenant_id="t-1",
        agent_id="agent-1",
        authority_grant_id=None,
        parent_action_id=None,
        root_action_id="act-1",
        correlation_id="corr-1",
        incident_id=None,
        target_system="database",
        target_resource="public.records",
        action_type="insert",
        before_state_reference="state:before:123",
        after_state_reference="state:after:456",
        compensation_payload={"operation": "restore", "target": "public.records"},
        reversibility_classification=Reversibility.AUTOMATICALLY_REVERSIBLE,
    )
    base.update(overrides)
    return RecoveryEvidence(**base)


def _verify(evidence: RecoveryEvidence) -> dict[str, Any]:
    return EvidenceVerificationService().verify_evidence_integrity(evidence)


def _make_action(
    action_id: str = "act-1",
    reversibility: Reversibility = Reversibility.AUTOMATICALLY_REVERSIBLE,
    before_state_ref: str | None = "state:before:123",
    after_state_ref: str | None = "state:after:456",
    resource: str = "record:1",
) -> ProtectedAction:
    return ProtectedAction(
        action_id=action_id,
        tenant_id="test-tenant",
        actor_user_id=uuid4(),
        agent_id="agent-1",
        authority_grant_id=None,
        tool="database",
        resource=resource,
        action_type="insert",
        reversibility=reversibility,
        parent_action_id=None,
        correlation_id="corr-1",
        tool_arguments={"key": "value"},
        before_state_ref=before_state_ref,
        after_state_ref=after_state_ref,
        policy_version="v1",
        status=ActionStatus.EXECUTED,
    )


def _mutate(value: Any) -> Any:
    """Return a semantically different value of the same general shape."""
    if value is None:
        return "no-longer-absent"
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, str):
        return value + "!"
    if isinstance(value, datetime):
        return value + timedelta(seconds=1)
    if isinstance(value, dict):
        return {**value, "__mutated__": True}
    if isinstance(value, list):
        return [*value, "__mutated__"]
    if isinstance(value, Enum):
        for member in type(value):
            if member != value:
                return member
    return object()  # pragma: no cover - unexpected field type


class TestSealing:
    def test_seal_sets_marker_and_64hex_hash(self) -> None:
        sealed = seal_evidence(_evidence())
        assert sealed.recovery_metadata[EVIDENCE_HASH_SPEC_KEY] == EVIDENCE_HASH_SPEC_V2
        assert len(sealed.evidence_hash) == 64
        int(sealed.evidence_hash, 16)  # valid hex

    def test_sealed_evidence_verifies_as_v2(self) -> None:
        result = _verify(seal_evidence(_evidence()))
        assert result["integrity_ok"] is True
        assert result["hash_spec"] == "v2"

    def test_seal_preserves_existing_metadata(self) -> None:
        sealed = seal_evidence(_evidence(recovery_metadata={"origin": "test"}))
        assert sealed.recovery_metadata["origin"] == "test"
        assert sealed.recovery_metadata[EVIDENCE_HASH_SPEC_KEY] == EVIDENCE_HASH_SPEC_V2

    def test_seal_does_not_mutate_original(self) -> None:
        original = _evidence()
        seal_evidence(original)
        assert EVIDENCE_HASH_SPEC_KEY not in original.recovery_metadata
        assert original.evidence_hash == ""

    def test_recompute_matches_sealed_hash(self) -> None:
        sealed = seal_evidence(_evidence())
        assert compute_evidence_hash_v2(sealed) == sealed.evidence_hash

    def test_canonical_json_is_deterministic(self) -> None:
        a = _evidence(recovery_metadata={"b": 2, "a": 1})
        b = _evidence(recovery_metadata={"a": 1, "b": 2})
        assert canonical_evidence_json(a) == canonical_evidence_json(b)
        assert compute_evidence_hash_v2(a) == compute_evidence_hash_v2(b)

    def test_none_versus_empty_string_are_distinct(self) -> None:
        # Absent optional fields are serialized as explicit JSON null;
        # absent != empty by design.
        with_none = compute_evidence_hash_v2(_evidence(state_version=None))
        with_empty = compute_evidence_hash_v2(_evidence(state_version=""))
        assert with_none != with_empty

    def test_hash_covers_every_field_except_itself(self) -> None:
        sealed = seal_evidence(_evidence())
        for spec in dataclasses.fields(RecoveryEvidence):
            if spec.name == "evidence_hash":
                continue
            mutated = _mutate(getattr(sealed, spec.name))
            candidate = dataclasses.replace(sealed, **{spec.name: mutated})
            assert compute_evidence_hash_v2(candidate) != sealed.evidence_hash, (
                f"field {spec.name} is not covered by the v2 hash"
            )


class TestTamperDetection:
    def test_tampered_target_resource_detected(self) -> None:
        sealed = seal_evidence(_evidence())
        tampered = dataclasses.replace(sealed, target_resource="public.secrets")
        result = _verify(tampered)
        assert result["integrity_ok"] is False
        assert any("hash" in issue.lower() for issue in result["issues"])

    def test_tampered_compensation_payload_detected(self) -> None:
        sealed = seal_evidence(_evidence())
        tampered = dataclasses.replace(
            sealed, compensation_payload={"operation": "drop_table"}
        )
        assert _verify(tampered)["integrity_ok"] is False

    def test_tampered_tenant_detected(self) -> None:
        # Cross-tenant evidence rewriting must invalidate the hash.
        sealed = seal_evidence(_evidence())
        tampered = dataclasses.replace(sealed, tenant_id="t-evil")
        assert _verify(tampered)["integrity_ok"] is False

    def test_tampered_timestamp_detected(self) -> None:
        # Deterministic mutation: back-to-back datetime.now() calls can share
        # a clock tick on Windows (~15.6ms granularity), so never use now()
        # as the "tampered" value.
        sealed = seal_evidence(_evidence())
        tampered = dataclasses.replace(
            sealed, created_at=sealed.created_at + timedelta(minutes=5)
        )
        assert _verify(tampered)["integrity_ok"] is False

    def test_tampered_metadata_detected(self) -> None:
        sealed = seal_evidence(_evidence())
        tampered = dataclasses.replace(
            sealed, recovery_metadata={**sealed.recovery_metadata, "extra": 1}
        )
        assert _verify(tampered)["integrity_ok"] is False


class TestMalformedV2Evidence:
    def test_missing_hash_rejected(self) -> None:
        sealed = seal_evidence(_evidence())
        broken = dataclasses.replace(sealed, evidence_hash="")
        result = _verify(broken)
        assert result["integrity_ok"] is False

    def test_non_hex_hash_rejected(self) -> None:
        sealed = seal_evidence(_evidence())
        broken = dataclasses.replace(sealed, evidence_hash="not-a-real-hash")
        result = _verify(broken)
        assert result["integrity_ok"] is False

    def test_wrong_length_hash_rejected(self) -> None:
        sealed = seal_evidence(_evidence())
        broken = dataclasses.replace(sealed, evidence_hash="ab" * 31)
        assert _verify(broken)["integrity_ok"] is False

    def test_unsupported_spec_version_rejected(self) -> None:
        sealed = seal_evidence(_evidence())
        broken = dataclasses.replace(
            sealed,
            recovery_metadata={**sealed.recovery_metadata, EVIDENCE_HASH_SPEC_KEY: "v9"},
        )
        result = _verify(broken)
        assert result["integrity_ok"] is False
        assert any("unsupported" in issue.lower() for issue in result["issues"])

    def test_non_string_spec_version_rejected(self) -> None:
        sealed = seal_evidence(_evidence())
        broken = dataclasses.replace(
            sealed,
            recovery_metadata={**sealed.recovery_metadata, EVIDENCE_HASH_SPEC_KEY: 2},
        )
        result = _verify(broken)
        assert result["integrity_ok"] is False
        assert any("unsupported" in issue.lower() for issue in result["issues"])

    def test_non_dict_metadata_rejected(self) -> None:
        # Corrupted storage (metadata column not an object) must fail closed.
        sealed = seal_evidence(_evidence())
        broken = dataclasses.replace(sealed, recovery_metadata=None)  # type: ignore[arg-type]
        result = _verify(broken)
        assert result["integrity_ok"] is False


class TestLegacyV1Compatibility:
    def test_legacy_evidence_verifies_via_field_presence_only(self) -> None:
        legacy = _evidence(evidence_hash="0" * 64)  # no spec marker
        result = _verify(legacy)
        assert result["integrity_ok"] is True
        assert result["hash_spec"] == "v1-legacy"
        assert result["hash_spec"] != "v2"

    def test_legacy_missing_required_field_still_fails(self) -> None:
        legacy = _evidence(evidence_hash="0" * 64, target_resource="")
        result = _verify(legacy)
        assert result["integrity_ok"] is False

    def test_legacy_never_reports_v2(self) -> None:
        legacy = _evidence(evidence_hash="deadbeef")
        assert _verify(legacy)["hash_spec"] == "v1-legacy"

    def test_stripping_marker_reclassifies_to_v1_not_v2(self) -> None:
        # Documented limitation: without a signing key, an actor who can edit
        # evidence storage can strip the v2 marker. The verifier must still be
        # honest about which spec was applied (v1-legacy, never "v2").
        sealed = seal_evidence(_evidence())
        stripped = dataclasses.replace(
            sealed, recovery_metadata=dict(sealed.recovery_metadata)
        )
        stripped.recovery_metadata.pop(EVIDENCE_HASH_SPEC_KEY)  # type: ignore[union-attr]
        result = _verify(stripped)
        assert result["hash_spec"] == "v1-legacy"

    def test_sealing_a_legacy_record_upgrades_to_v2(self) -> None:
        legacy = _evidence(evidence_hash="0" * 64)
        upgraded = seal_evidence(legacy)
        assert upgraded.recovery_metadata[EVIDENCE_HASH_SPEC_KEY] == EVIDENCE_HASH_SPEC_V2
        assert _verify(upgraded)["integrity_ok"] is True


ADAPTER_CLASSES = [
    ("mock", "MockRecoveryAdapter", {}, "record:1"),
    ("file_version", "FileVersionAdapter", {}, "record:1"),
    ("git", "GitRepositoryAdapter", {}, "record:1"),
    ("filesystem", "FilesystemRecoveryAdapter", {}, "record:1"),
    ("database", "DatabaseRecoveryAdapter", {}, "record:1"),
    ("database_record", "DatabaseRecordAdapter", {}, "record:1"),
    ("environment", "EnvironmentRecoveryAdapter", {}, "INTERLOCK_V6_PARITY_VAR"),
    ("archive", "ArchiveRecoveryAdapter", {}, None),  # absolute path from tmp_path
    ("config", "ConfigRecoveryAdapter", {}, "record:1"),
    ("config_rollback", "ConfigRollbackAdapter", {}, "record:1"),
    ("hosts", "HostsRecoveryAdapter", {}, None),  # hostname + tmp hosts file
]

_MODULE_FOR_CLASS = {
    "MockRecoveryAdapter": "app.infrastructure.recovery.mock_adapter",
    "FileVersionAdapter": "app.infrastructure.recovery.file_version_adapter",
    "GitRepositoryAdapter": "app.infrastructure.recovery.git_repository_adapter",
    "FilesystemRecoveryAdapter": "app.infrastructure.recovery.filesystem_recovery_adapter",
    "DatabaseRecoveryAdapter": "app.infrastructure.recovery.database_recovery_adapter",
    "DatabaseRecordAdapter": "app.infrastructure.recovery.database_record_adapter",
    "EnvironmentRecoveryAdapter": "app.infrastructure.recovery.environment_recovery_adapter",
    "ArchiveRecoveryAdapter": "app.infrastructure.recovery.archive_recovery_adapter",
    "ConfigRecoveryAdapter": "app.infrastructure.recovery.config_recovery_adapter",
    "ConfigRollbackAdapter": "app.infrastructure.recovery.config_rollback_adapter",
    "HostsRecoveryAdapter": "app.infrastructure.recovery.hosts_recovery_adapter",
}


class TestAdapterParity:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("label", "cls_name", "kwargs", "resource"), ADAPTER_CLASSES
    )
    async def test_adapter_seals_captured_evidence_as_v2(
        self,
        label: str,
        cls_name: str,
        kwargs: dict[str, Any],
        resource: str | None,
        tmp_path: Any,
    ) -> None:
        import importlib

        if label == "archive":
            target = tmp_path / "v6-archive-target"
            target.mkdir()
            (target / "a.txt").write_text("payload", encoding="utf-8")
            resource = str(target)
        elif label == "hosts":
            hosts_file = tmp_path / "hosts"
            hosts_file.write_text("127.0.0.1 localhost\n", encoding="utf-8")
            kwargs = {**kwargs, "hosts_path": str(hosts_file)}
            resource = "example.com"

        module = importlib.import_module(_MODULE_FOR_CLASS[cls_name])
        adapter = getattr(module, cls_name)(**kwargs)
        evidence = await adapter.capture_recovery_evidence(
            _make_action(resource=resource or "record:1")
        )
        assert evidence.recovery_metadata.get(EVIDENCE_HASH_SPEC_KEY) == (
            EVIDENCE_HASH_SPEC_V2
        ), f"{label} did not seal captured evidence as v2"
        assert len(evidence.evidence_hash) == 64, f"{label} hash not 64-hex"
        assert compute_evidence_hash_v2(evidence) == evidence.evidence_hash, (
            f"{label} stored hash does not match canonical recomputation"
        )
        result = _verify(evidence)
        assert result["integrity_ok"] is True, f"{label}: {result['issues']}"

    @pytest.mark.asyncio
    async def test_base_class_capture_seals_v2(self) -> None:
        from app.domain.services.recovery_adapter import RecoveryAdapter

        class _Minimal(RecoveryAdapter):
            async def can_recover(self, action: ProtectedAction) -> str:
                return "reversible"  # pragma: no cover - trivial

            async def preview_recovery(self, action: ProtectedAction) -> dict[str, Any]:
                return {"reversible": True}  # pragma: no cover - trivial

            async def execute_recovery(self, action: ProtectedAction) -> Any:
                return None  # pragma: no cover - trivial

        evidence = await _Minimal().capture_recovery_evidence(_make_action())
        assert evidence.recovery_metadata.get(EVIDENCE_HASH_SPEC_KEY) == (
            EVIDENCE_HASH_SPEC_V2
        )
        assert _verify(evidence)["integrity_ok"] is True


class TestPersistenceRoundTrip:
    @pytest.mark.asyncio
    async def test_v2_evidence_survives_sqlalchemy_round_trip(
        self, db_session: Any
    ) -> None:
        from app.infrastructure.persistence.repositories.sqlalchemy_recovery_evidence_repository import (
            SQLAlchemyRecoveryEvidenceRepository,
        )

        repo = SQLAlchemyRecoveryEvidenceRepository(db_session)
        sealed = seal_evidence(_evidence(evidence_id=f"ev-v2-{uuid4().hex}"))
        await repo.save(sealed)
        fetched = await repo.get_by_evidence_id(sealed.tenant_id, sealed.evidence_id)
        assert fetched is not None
        assert fetched.evidence_hash == sealed.evidence_hash
        assert fetched.recovery_metadata.get(EVIDENCE_HASH_SPEC_KEY) == (
            EVIDENCE_HASH_SPEC_V2
        )
        result = _verify(fetched)
        assert result["integrity_ok"] is True
        assert result["hash_spec"] == "v2"

    @pytest.mark.asyncio
    async def test_corrupt_metadata_column_rejected_after_load(
        self, db_session: Any
    ) -> None:
        # Simulate storage corruption: the recovery_metadata column contains
        # unparseable bytes. Loading must fail closed (reject), never silently
        # downgrade to the legacy field-presence path.
        from sqlalchemy import text

        from app.infrastructure.persistence.repositories.sqlalchemy_recovery_evidence_repository import (
            SQLAlchemyRecoveryEvidenceRepository,
        )

        repo = SQLAlchemyRecoveryEvidenceRepository(db_session)
        sealed = seal_evidence(_evidence(evidence_id=f"ev-corrupt-{uuid4().hex}"))
        await repo.save(sealed)
        db_session.execute(
            text("UPDATE recovery_evidence SET recovery_metadata = :raw WHERE evidence_id = :eid"),
            {"raw": "{not valid json", "eid": sealed.evidence_id},
        )
        db_session.flush()
        fetched = await repo.get_by_evidence_id(sealed.tenant_id, sealed.evidence_id)
        assert fetched is not None
        result = _verify(fetched)
        assert result["integrity_ok"] is False
        assert result["hash_spec"] == "corrupt-storage"

    @pytest.mark.asyncio
    async def test_v1_evidence_survives_round_trip_and_stays_v1(
        self, db_session: Any
    ) -> None:
        from app.infrastructure.persistence.repositories.sqlalchemy_recovery_evidence_repository import (
            SQLAlchemyRecoveryEvidenceRepository,
        )

        repo = SQLAlchemyRecoveryEvidenceRepository(db_session)
        legacy = _evidence(
            evidence_id=f"ev-v1-{uuid4().hex}", evidence_hash="a" * 64
        )
        await repo.save(legacy)
        fetched = await repo.get_by_evidence_id(legacy.tenant_id, legacy.evidence_id)
        assert fetched is not None
        result = _verify(fetched)
        assert result["integrity_ok"] is True
        assert result["hash_spec"] == "v1-legacy"
