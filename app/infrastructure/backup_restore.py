"""Backup/restore utility for recovery plans and sealed evidence (V6 doc-WP-5).

Export produces a backup directory safe for disposable environments:

- ``snapshot.sqlite3`` — consistent SQLite snapshot (sqlite3 backup API),
  covering plans and evidence rows alike;
- ``evidence_dump.json`` — each evidence row's exact v2 canonical preimage
  (``canonical_json``) alongside its sealed ``evidence_hash``;
- ``manifest.json`` — SHA-256 hash manifest over both artifacts plus the
  evidence count.

Restore fails closed at whichever integrity layer is violated:

1. artifact hash mismatch — the dump or snapshot file was edited;
2. evidence-count mismatch — a record was removed with a recomputed manifest;
3. per-record v2 hash mismatch — a record's preimage was edited with a
   recomputed manifest (WP-1 integrity check on the dump);
4. restored-DB chain mismatch — a snapshot row was edited with a recomputed
   manifest (WP-1 integrity check over the restored rows).

New additive module: no existing file is modified; nothing is wired into
routes (operator-triggered utility, exercised by the temp-dir drill in
``tests/unit/test_backup_restore_drill.py``).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.domain.services.evidence_hash import (
    EVIDENCE_HASH_SPEC_V2,
    canonical_evidence_json,
    compute_evidence_hash_v2,
)
from app.infrastructure.persistence.models.recovery_evidence_model import (
    RecoveryEvidenceModel,
)
from app.infrastructure.persistence.repositories.sqlalchemy_recovery_evidence_repository import (
    SQLAlchemyRecoveryEvidenceRepository,
)

BACKUP_MANIFEST_VERSION = 1
EVIDENCE_DUMP_VERSION = 1
SNAPSHOT_NAME = "snapshot.sqlite3"
DUMP_NAME = "evidence_dump.json"
MANIFEST_NAME = "manifest.json"


class BackupVerificationError(RuntimeError):
    """Raised when a backup integrity check fails (fail closed, never silent)."""


def _sha256_file(path: Path) -> str:
    """Chunked digest (D-RH-5): never load a whole backup artifact into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dump_records(db_path: Path) -> list[dict[str, Any]]:
    """Serialize every evidence row as its sealed v2 preimage + hash."""
    engine = create_engine(f"sqlite:///{db_path}")
    session = sessionmaker(bind=engine)()
    try:
        rows = session.scalars(select(RecoveryEvidenceModel)).all()
        records: list[dict[str, Any]] = []
        for row in rows:
            # Reuse the repository's static row->entity converter (single
            # source of truth; a wrong mapping would already fail the
            # pre-backup chain self-check below).
            entity = SQLAlchemyRecoveryEvidenceRepository._to_entity(row)
            staged = replace(entity, evidence_hash="")
            if entity.evidence_hash:
                recomputed = compute_evidence_hash_v2(staged)
                if recomputed != entity.evidence_hash:
                    raise BackupVerificationError(
                        f"pre-backup evidence chain broken: {entity.evidence_id}"
                    )
            records.append(
                {
                    "evidence_id": entity.evidence_id,
                    "evidence_hash": entity.evidence_hash,
                    "canonical_json": canonical_evidence_json(staged),
                }
            )
        return records
    finally:
        session.close()
        engine.dispose()


def export_backup(db_path: Path, out_dir: Path) -> dict[str, Any]:
    """Create snapshot + evidence dump + hash manifest under *out_dir*.

    Refuses to write into a directory that already holds a manifest (D-RH-9):
    a failed re-export would otherwise destroy the previous last known-good
    backup (old manifest + new partial artifacts). The dump is derived from the
    SNAPSHOT itself (D-RH-2), so both artifacts always describe one point in
    time — a writer between snapshot and dump can no longer tear the backup.
    """
    if not db_path.is_file():
        raise BackupVerificationError(f"database file not found: {db_path}")
    if (out_dir / MANIFEST_NAME).exists():
        raise BackupVerificationError(
            f"refusing to overwrite an existing backup in {out_dir.name}: "
            "remove it explicitly or choose a fresh output directory"
        )
    # R17: the backup directory holds a database snapshot and an evidence
    # dump - owner-only when we create it (existing dirs are untouched).
    out_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    snapshot = out_dir / SNAPSHOT_NAME
    source = sqlite3.connect(str(db_path))
    try:
        target = sqlite3.connect(str(snapshot))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()

    records = _dump_records(snapshot)
    dump = out_dir / DUMP_NAME
    dump.write_text(
        json.dumps(
            {
                "dump_version": EVIDENCE_DUMP_VERSION,
                "hash_spec": EVIDENCE_HASH_SPEC_V2,
                "evidence": records,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    manifest: dict[str, Any] = {
        "manifest_version": BACKUP_MANIFEST_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "artifacts": {
            SNAPSHOT_NAME: _sha256_file(snapshot),
            DUMP_NAME: _sha256_file(dump),
        },
        "evidence_count": len(records),
    }
    (out_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    if os.name == "posix":
        # R17: backup artifacts hold database snapshots and evidence dumps -
        # owner-only on POSIX (no-op on Windows, where modes are not
        # enforced). Best-effort: a chmod failure must not invalidate an
        # already-written, hash-verified backup.
        with contextlib.suppress(OSError):
            os.chmod(snapshot, 0o600)
            os.chmod(dump, 0o600)
            os.chmod(out_dir / MANIFEST_NAME, 0o600)
    return manifest


def restore_backup(backup_dir: Path, db_path: Path) -> dict[str, Any]:
    """Verify every integrity layer, then materialize the snapshot at *db_path*."""
    manifest_path = backup_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        raise BackupVerificationError(f"backup manifest missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # D-RH-3: crash-truncated manifest
        raise BackupVerificationError(
            f"backup manifest is not valid JSON: {MANIFEST_NAME}"
        ) from exc
    if not isinstance(manifest, dict):
        raise BackupVerificationError("backup manifest is not a JSON object")

    # 0) Format-compatibility gate (R14): never read a backup written in an
    #    unknown/future manifest format as if it were the current one —
    #    fail closed with an explicit message instead.
    manifest_version = manifest.get("manifest_version")
    if manifest_version != BACKUP_MANIFEST_VERSION:
        raise BackupVerificationError(
            f"unsupported backup manifest version: {manifest_version!r} "
            f"(supported: {BACKUP_MANIFEST_VERSION})"
        )

    # 1) Artifact integrity: manifest SHA-256 over snapshot + dump.
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise BackupVerificationError("backup manifest has no artifacts section")
    # D-RH-4: the manifest must attest EXACTLY the two known artifacts. This
    # both refuses path-traversal names (backup_dir / name can then never
    # escape the backup directory) and refuses omitted entries, which would
    # silently skip hash verification of a file restore still trusts.
    required_names = {SNAPSHOT_NAME, DUMP_NAME}
    actual_names = set(artifacts)
    if actual_names != required_names:
        missing = sorted(required_names - actual_names)
        unexpected = sorted(actual_names - required_names)
        raise BackupVerificationError(
            f"backup manifest artifacts mismatch: missing={missing}, "
            f"unexpected={unexpected}"
        )
    verified: list[str] = []
    for name, expected in artifacts.items():
        artifact = backup_dir / name
        if not artifact.is_file():
            raise BackupVerificationError(f"backup artifact missing: {name}")
        actual = _sha256_file(artifact)
        if actual != expected:
            raise BackupVerificationError(
                f"manifest mismatch for {name}: stored {expected}, actual {actual}"
            )
        verified.append(name)

    # 2) Dump structure + count (removed records with a recomputed manifest).
    try:
        payload = json.loads((backup_dir / DUMP_NAME).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # D-RH-3: corrupt dump body
        raise BackupVerificationError(
            f"evidence dump is not valid JSON: {DUMP_NAME}"
        ) from exc
    if not isinstance(payload, dict):
        raise BackupVerificationError("evidence dump is not a JSON object")

    # 2b) Dump-format compatibility gates (R14): the record preimages below
    #     are interpreted strictly per the supported dump version/hash spec;
    #     a future (or unknown) format must be rejected, not misparsed.
    payload_dump_version = payload.get("dump_version")
    if payload_dump_version != EVIDENCE_DUMP_VERSION:
        raise BackupVerificationError(
            f"unsupported evidence dump version: {payload_dump_version!r} "
            f"(supported: {EVIDENCE_DUMP_VERSION})"
        )
    payload_hash_spec = payload.get("hash_spec")
    if payload_hash_spec != EVIDENCE_HASH_SPEC_V2:
        raise BackupVerificationError(
            f"unsupported evidence dump hash spec: {payload_hash_spec!r} "
            f"(supported: {EVIDENCE_HASH_SPEC_V2})"
        )

    records = payload.get("evidence")
    if not isinstance(records, list):
        raise BackupVerificationError("evidence dump has no evidence section")
    manifest_count = manifest.get("evidence_count")
    if len(records) != manifest_count:
        raise BackupVerificationError(
            f"evidence count mismatch: manifest {manifest_count}, "
            f"dump {len(records)}"
        )

    # 3) Per-record WP-1 v2 check: sha256(canonical preimage) == sealed hash.
    for record in records:
        if not isinstance(record, dict):  # D-RH-3: malformed record entry
            raise BackupVerificationError("evidence dump record is not a JSON object")
        expected = record.get("evidence_hash", "")
        if not expected:
            continue  # unsealed legacy row: nothing to verify
        canonical = record.get("canonical_json")
        if not isinstance(canonical, str):  # D-RH-3: malformed record field
            raise BackupVerificationError(
                "evidence dump record has no canonical_json: "
                f"{record.get('evidence_id', '<unknown>')}"
            )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if digest != expected:
            raise BackupVerificationError(
                f"evidence dump v2 hash mismatch for "
                f"{record.get('evidence_id', '<unknown>')}"
            )

    # 4) Materialize the snapshot VERIFIABLY and ATOMICALLY (R11, D-RH-6/7/8):
    #    a) stage it to a fresh O_EXCL file next to the target (same
    #       filesystem); a planted symlink at the staging path is cleared and a
    #       re-plant raced into the gap is refused by O_EXCL, never followed;
    #    b) verify the staged bytes against the manifest digest (catches an
    #       artifact modified after step 1 or a torn staging write);
    #    c) run the restored-row chain check AND the manifest row-count
    #       cross-check (D-RH-2) against the staged file first, so a snapshot
    #       that fails verification can never overwrite a healthy live database;
    #    d) only then swap it in with os.replace() — an OS-level atomic
    #       operation. A crash mid-restore leaves either the complete old
    #       database or the complete new one, never a half-written file
    #       (the previous shutil.copyfile straight onto the live path could
    #       truncate-then-partially-write).
    tmp_path = db_path.with_name(db_path.name + ".restore-tmp")
    verified_rows = 0
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            tmp_path.unlink(missing_ok=True)  # clear planted links/stale staging
            with open(backup_dir / SNAPSHOT_NAME, "rb") as src:
                fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
                with os.fdopen(fd, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                    dst.flush()
                    os.fsync(dst.fileno())
        except OSError as exc:
            raise BackupVerificationError(
                f"restore staging failed ({exc.__class__.__name__}: {exc}); "
                "the live database was left untouched"
            ) from exc

        staged_digest = _sha256_file(tmp_path)
        if staged_digest != artifacts[SNAPSHOT_NAME]:
            raise BackupVerificationError(
                "staged snapshot does not match the manifest digest "
                "(artifact modified during restore?); the live database was "
                "left untouched"
            )

        # 5) WP-1 integrity check over the restored rows themselves plus the
        #    manifest count cross-check (D-RH-2), both against the staged file;
        #    the live target is untouched until these pass.
        try:
            engine = create_engine(f"sqlite:///{tmp_path}")
            session = sessionmaker(bind=engine)()
            try:
                rows = session.scalars(select(RecoveryEvidenceModel)).all()
                if len(rows) != manifest_count:
                    raise BackupVerificationError(
                        f"snapshot evidence count mismatch: manifest "
                        f"{manifest_count}, snapshot {len(rows)}"
                    )
                for row in rows:
                    entity = SQLAlchemyRecoveryEvidenceRepository._to_entity(row)
                    if not entity.evidence_hash:
                        continue
                    staged = replace(entity, evidence_hash="")
                    if compute_evidence_hash_v2(staged) != entity.evidence_hash:
                        raise BackupVerificationError(
                            f"restored evidence chain broken: {entity.evidence_id}"
                        )
                    verified_rows += 1
            finally:
                session.close()
                engine.dispose()
        except DBAPIError as exc:
            raise BackupVerificationError(
                "staged snapshot is not a readable sqlite database "
                f"({exc.orig}); the live database was left untouched"
            ) from exc

        # Atomic swap; fails (e.g. PermissionError) if the target DB file is
        # still held open — restore requires the application to be stopped.
        os.replace(tmp_path, db_path)
    except OSError as exc:
        guidance = (
            " - restore requires the application to be stopped"
            if isinstance(exc, PermissionError)
            else ""
        )
        raise BackupVerificationError(
            f"restore failed ({exc.__class__.__name__}: {exc}); "
            f"the live database was left untouched{guidance}"
        ) from exc
    finally:
        # No-op after a successful replace; removes the staging file when any
        # verification step failed, leaving the previous live DB intact.
        tmp_path.unlink(missing_ok=True)

    return {
        "snapshot_restored": True,
        "artifacts_verified": verified,
        "evidence_verified": verified_rows,
    }
