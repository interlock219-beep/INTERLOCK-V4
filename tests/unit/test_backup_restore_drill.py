"""V6 doc-WP-5: backup/restore drill (G-16).

Disposable-env drill in temp dirs: create plan + sealed evidence -> export
(SQLite snapshot + evidence dump with SHA-256 hash manifest) -> destroy the
database -> restore -> the evidence chain verifies (WP-1 v2 integrity).

Tamper drills must fail closed at the layer that owns the integrity:

- edited dump artifact            -> manifest hash mismatch;
- edited dump record + manifest   -> per-record v2 hash mismatch;
- removed dump record + manifest  -> evidence-count mismatch;
- edited snapshot row + manifest  -> restored-DB evidence chain mismatch.

Scope: new additive files only; no existing file is modified by the utility.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.domain.services.evidence_hash import compute_evidence_hash_v2, seal_evidence
from app.infrastructure.backup_restore import (
    DUMP_NAME,
    MANIFEST_NAME,
    SNAPSHOT_NAME,
    BackupVerificationError,
    export_backup,
    restore_backup,
)
from app.infrastructure.persistence.database import Base
from app.infrastructure.persistence.models.recovery_evidence_model import (
    RecoveryEvidenceModel,
)
from app.infrastructure.persistence.models.recovery_plan_model import RecoveryPlanModel
from app.infrastructure.persistence.repositories.sqlalchemy_recovery_evidence_repository import (
    SQLAlchemyRecoveryEvidenceRepository,
)
from tests.unit.recovery_lab.factories import make_action, make_evidence

TENANT = "t-backup-drill"
INCIDENT = "inc-backup-drill"
PLAN_ID = "plan-backup-drill"
EVIDENCE_ROWS = 2


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def _seed(db_path: Path) -> None:
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"timeout": 30})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        now = datetime.now(UTC)
        session.add(
            RecoveryPlanModel(
                plan_id=PLAN_ID,
                tenant_id=TENANT,
                incident_action_id="act-drill-0",
                created_at=now,
                updated_at=now,
                incident_id=INCIDENT,
            )
        )
        repo = SQLAlchemyRecoveryEvidenceRepository(session)
        for i in range(EVIDENCE_ROWS):
            action = make_action(
                action_id=f"act-drill-{i}", tenant_id=TENANT, agent_id="agent-drill"
            )
            evidence = make_evidence(action)
            evidence = replace(evidence, incident_id=INCIDENT)
            await repo.save(seal_evidence(evidence))
        session.commit()
    finally:
        session.close()
        engine.dispose()


async def _chain_from_db(db_path: Path) -> tuple[int, list[str]]:
    """Return (evidence rows read, evidence_ids whose v2 chain is broken)."""
    engine = create_engine(f"sqlite:///{db_path}")
    session = sessionmaker(bind=engine)()
    try:
        repo = SQLAlchemyRecoveryEvidenceRepository(session)
        entities, total = await repo.list_by_incident(TENANT, INCIDENT)
        broken = [
            e.evidence_id
            for e in entities
            if compute_evidence_hash_v2(replace(e, evidence_hash="")) != e.evidence_hash
        ]
        return total, broken
    finally:
        session.close()
        engine.dispose()


async def test_backup_restore_drill_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "drill.sqlite3"
    await _seed(db)

    # Pre-backup: the live evidence chain verifies (WP-1 v2).
    total, broken = await _chain_from_db(db)
    assert total == EVIDENCE_ROWS
    assert broken == []

    out = tmp_path / "backup"
    manifest = export_backup(db, out)
    assert set(manifest["artifacts"]) == {"snapshot.sqlite3", "evidence_dump.json"}
    assert manifest["evidence_count"] == EVIDENCE_ROWS
    for name, digest in manifest["artifacts"].items():
        assert _sha256(out / name) == digest

    # Destroy (disposable env).
    db.unlink()
    assert not db.exists()

    report = restore_backup(out, db)
    assert report["snapshot_restored"] is True
    assert report["evidence_verified"] == EVIDENCE_ROWS
    assert db.exists()

    # Restored evidence chain verifies via the repository's public API.
    total, broken = await _chain_from_db(db)
    assert total == EVIDENCE_ROWS
    assert broken == []

    # The plan row survived the snapshot round-trip.
    engine = create_engine(f"sqlite:///{db}")
    session = sessionmaker(bind=engine)()
    try:
        plan = session.scalar(
            select(RecoveryPlanModel).where(RecoveryPlanModel.plan_id == PLAN_ID)
        )
        assert plan is not None
        assert plan.tenant_id == TENANT
        # Evidence rows are present in the restored DB as rows too.
        rows = session.scalars(
            select(RecoveryEvidenceModel).where(
                RecoveryEvidenceModel.tenant_id == TENANT
            )
        ).all()
        assert len(rows) == EVIDENCE_ROWS
    finally:
        session.close()
        engine.dispose()


async def test_tampered_dump_artifact_fails_restore(tmp_path: Path) -> None:
    db = tmp_path / "drill.sqlite3"
    await _seed(db)
    out = tmp_path / "backup"
    export_backup(db, out)

    dump = out / "evidence_dump.json"
    text = dump.read_text(encoding="utf-8")
    tampered = text.replace('"evidence"', '"evidencE"')
    assert tampered != text, "tamper must actually change the artifact"
    dump.write_text(tampered, encoding="utf-8")

    with pytest.raises(BackupVerificationError, match="manifest mismatch"):
        restore_backup(out, tmp_path / "restored.sqlite3")


async def test_tampered_record_with_recomputed_manifest_fails_v2(
    tmp_path: Path,
) -> None:
    db = tmp_path / "drill.sqlite3"
    await _seed(db)
    out = tmp_path / "backup"
    export_backup(db, out)

    # Attacker edits a record's canonical preimage AND fixes the manifest
    # hash: only the per-record v2 check can catch this.
    payload = json.loads((out / "evidence_dump.json").read_text(encoding="utf-8"))
    record = payload["evidence"][0]
    doc = json.loads(record["canonical_json"])
    # Injecting any key guarantees the preimage bytes differ from what the
    # v2 hash was sealed over.
    doc["tampered_field"] = "injected"
    record["canonical_json"] = json.dumps(
        doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )
    (out / "evidence_dump.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    manifest["artifacts"]["evidence_dump.json"] = _sha256(out / "evidence_dump.json")
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    with pytest.raises(BackupVerificationError, match="v2 hash mismatch"):
        restore_backup(out, tmp_path / "restored.sqlite3")


async def test_removed_record_with_recomputed_manifest_fails_count(
    tmp_path: Path,
) -> None:
    db = tmp_path / "drill.sqlite3"
    await _seed(db)
    out = tmp_path / "backup"
    export_backup(db, out)

    payload = json.loads((out / "evidence_dump.json").read_text(encoding="utf-8"))
    payload["evidence"] = payload["evidence"][:1]
    (out / "evidence_dump.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    manifest["artifacts"]["evidence_dump.json"] = _sha256(out / "evidence_dump.json")
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    with pytest.raises(BackupVerificationError, match="evidence count"):
        restore_backup(out, tmp_path / "restored.sqlite3")


async def test_tampered_snapshot_row_fails_restored_chain(tmp_path: Path) -> None:
    db = tmp_path / "drill.sqlite3"
    await _seed(db)
    out = tmp_path / "backup"
    export_backup(db, out)

    # Attacker edits a row inside the snapshot and updates the manifest.
    snapshot = out / "snapshot.sqlite3"
    conn = sqlite3.connect(snapshot)
    try:
        conn.execute(
            "UPDATE recovery_evidence SET target_resource = 'tampered:resource'"
        )
        conn.commit()
    finally:
        conn.close()
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    manifest["artifacts"]["snapshot.sqlite3"] = _sha256(snapshot)
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    # Dump checks still pass (untampered); only the restored-DB chain
    # verification can reject the snapshot content.
    with pytest.raises(BackupVerificationError, match="chain broken"):
        restore_backup(out, tmp_path / "restored.sqlite3")


async def test_failed_restore_leaves_existing_db_untouched(tmp_path: Path) -> None:
    """R11 regression: a restore rejected by verification must have ZERO
    side effects on the target database.

    Before R11, restore_backup() copied the snapshot straight onto the live
    target and only then ran the restored-row chain check — a snapshot that
    failed verification had ALREADY overwritten the healthy database
    (truncate-then-write; also non-atomic, so a crash mid-copy left a torn
    file). After R11 the snapshot is staged beside the target, verified, and
    swapped in only with an atomic os.replace(); a rejection leaves the
    previous database byte-identical and no staging file behind.
    """
    db = tmp_path / "live.sqlite3"
    await _seed(db)
    out = tmp_path / "backup"
    export_backup(db, out)

    # Attacker edits a row inside the snapshot and updates the manifest so
    # artifact/count/dump checks all pass; only the restored-DB chain check
    # can reject it (same tamper as test_tampered_snapshot_row_fails_restored_chain).
    snapshot = out / "snapshot.sqlite3"
    conn = sqlite3.connect(snapshot)
    try:
        conn.execute(
            "UPDATE recovery_evidence SET target_resource = 'tampered:resource'"
        )
        conn.commit()
    finally:
        conn.close()
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    manifest["artifacts"]["snapshot.sqlite3"] = _sha256(snapshot)
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    before = _sha256(db)
    with pytest.raises(BackupVerificationError, match="chain broken"):
        restore_backup(out, db)

    # 1) The healthy live DB must be byte-identical after the rejection
    #    (RED before R11: it was overwritten with the tampered snapshot).
    assert _sha256(db) == before
    total, broken = await _chain_from_db(db)
    assert total == EVIDENCE_ROWS
    assert broken == []

    # 2) No staging file may survive a failed restore.
    assert not db.with_name(db.name + ".restore-tmp").exists()


async def test_future_manifest_version_rejected(tmp_path: Path) -> None:
    """R14 regression: an unknown manifest format is refused fail-closed
    BEFORE any materialization, instead of being read as the current format."""
    db = tmp_path / "live.sqlite3"
    await _seed(db)
    out = tmp_path / "backup"
    export_backup(db, out)

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    manifest["manifest_version"] = 99
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    target = tmp_path / "restored.sqlite3"
    with pytest.raises(
        BackupVerificationError, match="unsupported backup manifest version"
    ):
        restore_backup(out, target)
    # The gate runs before staging: the target was never created.
    assert not target.exists()
    assert not target.with_name(target.name + ".restore-tmp").exists()


async def test_future_dump_version_and_hash_spec_rejected(tmp_path: Path) -> None:
    """R14 regression: unknown evidence-dump versions/specs are refused even
    when the attacker recomputes the manifest artifact hashes (same tamper
    discipline as the other drills)."""
    db = tmp_path / "live.sqlite3"
    await _seed(db)
    out = tmp_path / "backup"
    export_backup(db, out)
    target = tmp_path / "restored.sqlite3"

    def _rewrite_dump(payload: dict) -> None:
        dump_path = out / "evidence_dump.json"
        dump_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        manifest["artifacts"]["evidence_dump.json"] = _sha256(dump_path)
        (out / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )

    dump_path = out / "evidence_dump.json"
    original = json.loads(dump_path.read_text(encoding="utf-8"))

    # Case 1: future dump_version.
    payload = dict(original)
    payload["dump_version"] = 99
    _rewrite_dump(payload)
    with pytest.raises(
        BackupVerificationError, match="unsupported evidence dump version"
    ):
        restore_backup(out, target)
    assert not target.exists()

    # Case 2: unknown hash spec (dump_version valid) — preimage interpretation
    # must not silently fall back to the current spec.
    payload = dict(original)
    payload["hash_spec"] = "wp1-future-spec"
    _rewrite_dump(payload)
    with pytest.raises(
        BackupVerificationError, match="unsupported evidence dump hash spec"
    ):
        restore_backup(out, target)
    assert not target.exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode semantics")
def test_export_backup_artifacts_owner_only_posix(tmp_path: Path) -> None:
    """R17: backup directory 0o700 and artifacts 0o600 on POSIX.

    Skips on Windows (reported as skipped, never as passing): Windows does
    not enforce POSIX mode bits.
    """
    db_path = tmp_path / "claims.sqlite3"
    sqlite3.connect(db_path).close()
    out_dir = tmp_path / "backup"

    manifest = export_backup(db_path, out_dir)

    assert manifest["evidence_count"] == 0
    assert stat.S_IMODE(out_dir.stat().st_mode) == 0o700
    for name in (SNAPSHOT_NAME, DUMP_NAME, MANIFEST_NAME):
        mode = stat.S_IMODE((out_dir / name).stat().st_mode)
        assert mode == 0o600, f"{name}: {oct(mode)}"
