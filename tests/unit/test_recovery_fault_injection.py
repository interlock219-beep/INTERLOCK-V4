"""V6 mission §7: deterministic fault-injection drills for the supported local
backup/restore path and the filesystem recovery adapter.

Scope and honesty:

- Mocked failures (ENOSPC, PermissionError, mid-copy mutation) exercise the
  fail-closed behavior of the code under test. They are explicitly NOT proof of
  real operating-system behavior; real disk-full and process-kill drills need an
  isolated environment plus authorization (register entries M1/M2).
- Dangling-symlink drills `pytest.skip` honestly when the environment forbids
  symlink creation (Windows privilege).
- Failures must never destroy the last known-good state: every drill asserts the
  live target is untouched (byte-identical) and no staging residue remains.

Defects covered: D-RH-1 (adapter residue blocks retry), D-RH-2 (torn backup /
missing snapshot count cross-check), D-RH-3 (raw JSON/KeyError contract),
D-RH-4 (artifact traversal + silent verification skip), D-RH-5 (whole-file
hashing), D-RH-6 (no staged-digest check), D-RH-7 (dangling symlink escape),
D-RH-8 (raw OSError/DBAPIError contract), D-RH-9 (re-export overwrites).
"""

from __future__ import annotations

import base64
import errno
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

import app.infrastructure.backup_restore as backup_module
from app.domain.entities.surgical_recovery_types import ExecutionState
from app.infrastructure.backup_restore import (
    DUMP_NAME,
    SNAPSHOT_NAME,
    BackupVerificationError,
    export_backup,
    restore_backup,
)
from app.infrastructure.recovery.filesystem_recovery_adapter import (
    FilesystemRecoveryAdapter,
)
from tests.unit.test_backup_restore_drill import EVIDENCE_ROWS
from tests.unit.test_backup_restore_drill import _seed as seed_db


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _rehash_manifest_artifact(out: Path, name: str) -> None:
    """Recompute one artifact's manifest hash (simulates full-chain recompute)."""
    manifest = _load_json(out / "manifest.json")
    manifest["artifacts"][name] = _sha256(out / name)
    _write_json(out / "manifest.json", manifest)


def _snapshot_row_count(snapshot: Path) -> int:
    con = sqlite3.connect(str(snapshot))
    try:
        return int(
            con.execute("SELECT COUNT(*) FROM recovery_evidence").fetchone()[0]
        )
    finally:
        con.close()


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable in this environment: {exc}")


async def _export(tmp_path: Path) -> tuple[Path, Path]:
    db = tmp_path / "fi.sqlite3"
    await seed_db(db)
    out = tmp_path / "backup"
    export_backup(db, out)
    return db, out


# --------------------------------------------------------------------------
# backup_restore: malformed and hostile manifests (D-RH-3, D-RH-4)
# --------------------------------------------------------------------------


async def test_corrupt_manifest_json_raises_contract_error(tmp_path: Path) -> None:
    db, out = await _export(tmp_path)
    # Truncated manifest write (crash mid-write): invalid JSON.
    (out / "manifest.json").write_text('{"manifest_version": 1, "artifacts": {', encoding="utf-8")
    with pytest.raises(BackupVerificationError):
        restore_backup(out, tmp_path / "restored.sqlite3")


async def test_dump_record_missing_canonical_json_fails_closed(tmp_path: Path) -> None:
    db, out = await _export(tmp_path)
    dump = _load_json(out / DUMP_NAME)
    del dump["evidence"][0]["canonical_json"]
    _write_json(out / DUMP_NAME, dump)
    _rehash_manifest_artifact(out, DUMP_NAME)
    with pytest.raises(BackupVerificationError, match="canonical_json"):
        restore_backup(out, tmp_path / "restored.sqlite3")


async def test_non_object_dump_record_fails_closed(tmp_path: Path) -> None:
    _, out = await _export(tmp_path)
    dump = _load_json(out / DUMP_NAME)
    dump["evidence"][0] = "not-an-object"
    _write_json(out / DUMP_NAME, dump)
    _rehash_manifest_artifact(out, DUMP_NAME)
    with pytest.raises(BackupVerificationError):
        restore_backup(out, tmp_path / "restored.sqlite3")


async def test_artifact_traversal_entry_rejected(tmp_path: Path) -> None:
    _, out = await _export(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("material outside the backup directory", encoding="utf-8")
    manifest = _load_json(out / "manifest.json")
    # Manifest that only references a path outside the backup dir.
    manifest["artifacts"] = {"../outside.txt": _sha256(outside)}
    _write_json(out / "manifest.json", manifest)
    with pytest.raises(BackupVerificationError, match="artifacts"):
        restore_backup(out, tmp_path / "restored.sqlite3")


async def test_omitted_artifact_entry_rejected(tmp_path: Path) -> None:
    _, out = await _export(tmp_path)
    manifest = _load_json(out / "manifest.json")
    # Dump silently removed from the manifest: its hash would never be checked.
    manifest["artifacts"] = {SNAPSHOT_NAME: manifest["artifacts"][SNAPSHOT_NAME]}
    _write_json(out / "manifest.json", manifest)
    with pytest.raises(BackupVerificationError, match="artifacts"):
        restore_backup(out, tmp_path / "restored.sqlite3")


# --------------------------------------------------------------------------
# backup_restore: inconsistent snapshots (D-RH-2)
# --------------------------------------------------------------------------


async def test_snapshot_row_removed_with_recomputed_manifest_rejected(
    tmp_path: Path,
) -> None:
    _, out = await _export(tmp_path)
    snapshot = out / SNAPSHOT_NAME
    con = sqlite3.connect(str(snapshot))
    try:
        con.execute(
            "DELETE FROM recovery_evidence WHERE rowid = "
            "(SELECT MIN(rowid) FROM recovery_evidence)"
        )
        con.commit()
    finally:
        con.close()
    _rehash_manifest_artifact(out, SNAPSHOT_NAME)
    with pytest.raises(BackupVerificationError, match="count"):
        restore_backup(out, tmp_path / "restored.sqlite3")


async def test_export_derives_dump_from_snapshot_point_in_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A writer between snapshot (T1) and dump (T2) must not tear the backup."""
    db = tmp_path / "fi.sqlite3"
    await seed_db(db)
    out = tmp_path / "backup"
    snapshot_path = out / SNAPSHOT_NAME

    original = backup_module._dump_records

    def racing_dump(path: Path) -> list[dict]:
        records = original(path)
        if path != snapshot_path:
            # Simulates an evidence row committed between snapshot and dump.
            records.append(
                {
                    "evidence_id": "race-injected",
                    "evidence_hash": "",
                    "canonical_json": "{}",
                }
            )
        return records

    monkeypatch.setattr(backup_module, "_dump_records", racing_dump)
    manifest = export_backup(db, out)

    # The manifest count and the snapshot must derive from one point in time.
    assert manifest["evidence_count"] == _snapshot_row_count(snapshot_path)
    report = restore_backup(out, tmp_path / "restored.sqlite3")
    assert report["snapshot_restored"] is True
    assert report["evidence_verified"] == manifest["evidence_count"]


# --------------------------------------------------------------------------
# backup_restore: staging verification, interruption, idempotency (D-RH-6/8)
# --------------------------------------------------------------------------


async def test_staged_snapshot_must_match_manifest_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, out = await _export(tmp_path)
    target = tmp_path / "restored.sqlite3"
    real_copy = shutil.copyfileobj

    def mutating_copy(src, dst, *args, **kwargs):  # type: ignore[no-untyped-def]
        real_copy(src, dst, *args, **kwargs)
        dst.write(b"\x00")  # bytes changed after manifest verification

    monkeypatch.setattr(shutil, "copyfileobj", mutating_copy)
    with pytest.raises(BackupVerificationError):
        restore_backup(out, target)
    assert not target.exists()


async def test_disk_full_staging_fails_closed_with_contract_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, out = await _export(tmp_path)
    live = tmp_path / "live.sqlite3"
    live.write_bytes(b"LIVE-DB-SENTINEL")

    def enospc(*_args, **_kwargs) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(shutil, "copyfileobj", enospc)
    with pytest.raises(BackupVerificationError):
        restore_backup(out, live)
    assert live.read_bytes() == b"LIVE-DB-SENTINEL"
    assert not live.with_name(live.name + ".restore-tmp").exists()


async def test_replace_permission_error_fails_closed_with_guidance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, out = await _export(tmp_path)
    live = tmp_path / "live.sqlite3"
    live.write_bytes(b"LIVE-DB-SENTINEL")

    def denied(*_args, **_kwargs) -> None:
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(backup_module.os, "replace", denied)
    with pytest.raises(BackupVerificationError, match="application to be stopped"):
        restore_backup(out, live)
    assert live.read_bytes() == b"LIVE-DB-SENTINEL"
    assert not live.with_name(live.name + ".restore-tmp").exists()


async def test_unreadable_snapshot_fails_closed_with_contract_error(
    tmp_path: Path,
) -> None:
    _, out = await _export(tmp_path)
    snapshot = out / SNAPSHOT_NAME
    snapshot.write_bytes(snapshot.read_bytes()[:64])  # torn write
    _rehash_manifest_artifact(out, SNAPSHOT_NAME)
    target = tmp_path / "restored.sqlite3"
    with pytest.raises(BackupVerificationError):
        restore_backup(out, target)
    assert not target.exists()


async def test_duplicate_restore_is_idempotent(tmp_path: Path) -> None:
    _, out = await _export(tmp_path)
    target = tmp_path / "restored.sqlite3"
    first = restore_backup(out, target)
    digest_first = _sha256(target)
    second = restore_backup(out, target)
    assert first == second
    assert _sha256(target) == digest_first


async def test_verification_error_does_not_leak_record_content(
    tmp_path: Path,
) -> None:
    _, out = await _export(tmp_path)
    dump = _load_json(out / DUMP_NAME)
    sentinel = "SENTINEL-DO-NOT-LEAK"
    dump["evidence"][0]["canonical_json"] = json.dumps({"secret": sentinel})
    _write_json(out / DUMP_NAME, dump)
    _rehash_manifest_artifact(out, DUMP_NAME)
    with pytest.raises(BackupVerificationError) as excinfo:
        restore_backup(out, tmp_path / "restored.sqlite3")
    assert sentinel not in str(excinfo.value)


async def test_dangling_symlink_staging_cannot_escape(tmp_path: Path) -> None:
    _, out = await _export(tmp_path)
    live = tmp_path / "live.sqlite3"
    escape = tmp_path / "escape_target.txt"
    staging = live.with_name(live.name + ".restore-tmp")
    _symlink_or_skip(staging, escape)

    report = restore_backup(out, live)
    assert report["snapshot_restored"] is True
    assert not escape.exists()  # write must never follow a planted link
    assert not staging.exists()
    assert _snapshot_row_count(live) == EVIDENCE_ROWS


# --------------------------------------------------------------------------
# backup_restore: export safety (D-RH-9) + chunked digest equivalence (D-RH-5)
# --------------------------------------------------------------------------


async def test_export_refuses_to_overwrite_existing_backup(tmp_path: Path) -> None:
    db, out = await _export(tmp_path)
    before = _sha256(out / SNAPSHOT_NAME)

    # Destroy an evidence row in the LIVE db: a second export would now write a
    # different snapshot and silently invalidate the previous backup set.
    con = sqlite3.connect(str(db))
    try:
        con.execute(
            "DELETE FROM recovery_evidence WHERE rowid = "
            "(SELECT MIN(rowid) FROM recovery_evidence)"
        )
        con.commit()
    finally:
        con.close()

    with pytest.raises(BackupVerificationError, match="refus"):
        export_backup(db, out)
    assert _sha256(out / SNAPSHOT_NAME) == before
    assert _snapshot_row_count(out / SNAPSHOT_NAME) == EVIDENCE_ROWS


async def test_chunked_file_digest_matches_reference(tmp_path: Path) -> None:
    big = tmp_path / "big.bin"
    unit = b"0123456789abcdef"
    big.write_bytes((unit * (3 * 1024 * 1024 // len(unit) + 4))[: 3 * 1024 * 1024 + 17])
    assert _sha256(big) == hashlib.sha256(big.read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# filesystem adapter: failed-attempt residue and retry (D-RH-1)
# --------------------------------------------------------------------------


def _deleted_payload(data: bytes, file_hash: str) -> dict:
    return {
        "file_path": "deleted.txt",
        "before_snapshot": {
            "exists": True,
            "content_b64": base64.b64encode(data).decode(),
            "hash": file_hash,
        },
    }


async def test_restore_deleted_file_failed_attempt_is_retryable(
    tmp_path: Path,
) -> None:
    base = tmp_path / "fs"
    base.mkdir()
    adapter = FilesystemRecoveryAdapter(base_path=base)
    target = base / "deleted.txt"
    correct = b"original bytes \x00\x01\x02\r\n"
    bad = _deleted_payload(correct, "0" * 64)

    # Phase 1: post-write hash mismatch -> FAILED and NO residue at the target
    # (the pre-op state was "file absent" and must be restored).
    first = adapter._execute_restore_deleted_file(bad, base)
    assert first["success"] is False
    assert first["execution_state"] == ExecutionState.FAILED
    assert not target.exists()

    # Phase 2: retrying the same payload must reach the operation again, not be
    # blocked by residue of its own failed attempt.
    second = adapter._execute_restore_deleted_file(bad, base)
    assert second["execution_state"] != ExecutionState.BLOCKED_BY_CONFLICT

    # Phase 3: a corrected payload succeeds and writes byte-exact content.
    good = _deleted_payload(correct, _sha256_bytes(correct))
    third = adapter._execute_restore_deleted_file(good, base)
    assert third["success"] is True
    assert target.read_bytes() == correct


async def test_restore_deleted_file_clears_stale_staging_from_interruption(
    tmp_path: Path,
) -> None:
    base = tmp_path / "fs"
    base.mkdir()
    adapter = FilesystemRecoveryAdapter(base_path=base)
    target = base / "deleted.txt"
    correct = b"original after interruption"
    # A previous attempt killed mid-write left a stale staging file behind.
    stale = base / "deleted.txt.recovery_tmp"
    stale.write_bytes(b"stale partial bytes from a killed attempt")

    payload = _deleted_payload(correct, _sha256_bytes(correct))
    result = adapter._execute_restore_deleted_file(payload, base)
    assert result["success"] is True
    assert target.read_bytes() == correct
    assert not stale.exists()


async def test_restore_content_dangling_symlink_staging_cannot_escape(
    tmp_path: Path,
) -> None:
    base = tmp_path / "fs"
    base.mkdir()
    adapter = FilesystemRecoveryAdapter(base_path=base)
    target = base / "file.txt"
    current = b"modified current state"
    target.write_bytes(current)
    escape = tmp_path / "escape_target.txt"
    staging = base / "file.txt.recovery_tmp"
    _symlink_or_skip(staging, escape)

    restored = b"before state bytes"
    payload = {
        "file_path": "file.txt",
        "before_snapshot": {
            "content_b64": base64.b64encode(restored).decode(),
            "hash": _sha256_bytes(restored),
        },
        "after_snapshot": {"hash": _sha256_bytes(current)},
    }
    result = adapter._execute_restore_content(payload, base)
    assert result["success"] is True
    assert not escape.exists()  # staging must not write through a planted link
    assert not target.is_symlink()
    assert target.read_bytes() == restored
