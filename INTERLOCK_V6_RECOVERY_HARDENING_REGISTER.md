# INTERLOCK V6 — Recovery Hardening Defect Register (Session 2, 2026-10-18)

Versioned, append-only companion to `INTERLOCK_V6_CONTINUOUS_ENGINEERING_LOG.md`.
Status values: **CONFIRMED** (reproduced or proven by exact code inspection with a
concrete trigger), **RISK** (untested weakness), **MISSING** (capability gap, not a
defect), **IDEA** (future product idea). Each entry distinguishes confirmed defects
from absent features; nothing is registered as a defect solely because a feature
is absent.

## 0. Initial preservation state (baseline for this session)

| Item | Value |
|---|---|
| HEAD | `145a3d9` (master) |
| Staged | 0 |
| Stash | 1 (`stash@{0}` WIP on master) |
| Porcelain | 200 = 67 modified + 60 deleted (all under `web/`) + 73 untracked |
| Remotes | origin → github.com/interlock219-beep/INTERLOCK-V4.git (unchanged, untouched) |
| Evidence | manifests SHA-256 verified; 853 campaign files; pilot evidence present |
| Frozen Suite A/B | manifests verified, **not executed** |

All new work is compared against this baseline, not against a clean tree.
**New-baseline delta disclosed:** this session added the register itself,
`INTERLOCK_V6_BETA_READINESS_CHECKLIST.md`,
`tests/unit/test_recovery_fault_injection.py`, two new tests inside
`tests/integration/test_alembic_migration_safety.py`, and a fresh pilot-demo
evidence file under git-ignored `logs/`. Pre-existing work was never deleted to
hide a failing check.

## 1. Confirmed defects (priority order) — all FIXED 2026-10-18 (RED→GREEN)

Each fix was RED-tested first (test failed against the pre-fix code with the
expected failure mode), then implemented narrowly, then re-run GREEN. No
threshold, public contract, migration, or dependency was changed.

### D-RH-1 — `_execute_restore_deleted_file` leaves residue that blocks its own retry
- **Status:** **FIXED 2026-10-18** (staged-swap + pre-swap verification; drills
  `test_restore_deleted_file_failed_attempt_is_retryable`,
  `test_restore_deleted_file_clears_stale_staging_from_interruption` — both
  RED before the fix, GREEN after; existing adapter/drill suites stayed green).
- **Repro:** call `_execute_restore_deleted_file` with a payload whose write fails
  mid-way (simulated `ENOSPC`) or whose post-write hash check fails
  (`before_snapshot.hash` inconsistent with `content_b64`). The file now exists at
  the target with partial/wrong bytes. An immediate retry returns
  `BLOCKED_BY_CONFLICT "File already exists at target path"` — the recovery path is
  stuck until an operator manually deletes the residue.
- **Severity:** MEDIUM-HIGH (recovery correctness: a failed operation leaves the
  resource in a state that was neither the pre-op state — file absent — nor the
  post-op state, and blocks retry; a process kill mid-write does the same with no
  cleanup possible).
- **Evidence:** `app/infrastructure/recovery/filesystem_recovery_adapter.py`
  L2052 (pre-op guard proves "absent"), L2096 direct `write_bytes` onto the target,
  L2130-2137 hash-mismatch return leaves file, L2150 exception return leaves file.
  No existing test asserts residue-stays behavior.
- **Proposed minimal fix:** stage the restored bytes to
  `<target>.recovery_tmp` (created with `O_CREAT|O_EXCL`), verify staged hash vs
  `before_snapshot.hash`, re-check target still absent (concurrent-creation guard),
  then `os.replace()`. Any failure/kill leaves only a temp file which the next
  attempt clears (`unlink(missing_ok=True)`); the target never holds partial bytes.
- **Approval:** none required — containment only: it never touches pre-existing
  state (guard proves non-existence first) and cannot report success without a
  verified postcondition (mission §6 mandate). Rollback: revert the hunk; the two
  new tests go red.
- **Regression tests:** `tests/unit/test_recovery_fault_injection.py`
  (ENOSPC mid-write, hash mismatch, retry-reaches-operation).

### D-RH-2 — Torn backup accepted: export mixes two points in time; restore never
cross-checks snapshot row count
- **Status:** **FIXED 2026-10-18** (export dumps from the snapshot; restore
  cross-checks `snapshot rows == manifest.evidence_count` before the swap;
  drills `test_export_derives_dump_from_snapshot_point_in_time`,
  `test_snapshot_row_removed_with_recomputed_manifest_rejected` RED→GREEN).
- **Repro (a, export):** `export_backup` snapshots at T1 (`source.backup`) but
  reads the dump from the live DB at T2 (L117 `_dump_records(db_path)`). An
  evidence row inserted between T1 and T2 yields `snapshot=N` rows,
  `manifest.evidence_count=N+1`, `dump=N+1`.
  **Repro (b, restore):** remove one evidence row from a snapshot *and* recompute
  that artifact's manifest hash: every current layer passes (dump count == manifest,
  dump records self-chain, snapshot rows self-chain) and restore reports
  `snapshot_restored=True` with fewer rows than the manifest attests.
- **Severity:** MEDIUM (point-in-time inconsistency silently accepted; mission §7
  explicitly lists "missing, stale, or inconsistent snapshots").
- **Evidence:** `app/infrastructure/backup_restore.py` L117 (live-DB dump read),
  L202 (dump vs manifest only), L248-258 (chain check has no count cross-check).
- **Proposed minimal fix:** (a) export reads `_dump_records` from the **snapshot
  file** so both artifacts derive from one point in time (snapshot semantics);
  (b) restore step 5 additionally requires
  `snapshot rows == manifest.evidence_count`, fail closed before the swap.
- **Approval:** none — fail-closed verification + writer/reader consistency; output
  format unchanged; all existing drill tests stay green (they contain no concurrent
  writes, so counts remain equal).
- **Regression tests:** race-injection export test; row-removal tamper test.

### D-RH-3 — Malformed backup input raises raw `JSONDecodeError`/`KeyError`
- **Status:** **FIXED 2026-10-18** (`BackupVerificationError` wraps manifest/dump
  JSON parsing, non-object manifests/records, and missing `canonical_json`;
  drills `test_corrupt_manifest_json_raises_contract_error`,
  `test_dump_record_missing_canonical_json_fails_closed`,
  `test_non_object_dump_record_fails_closed` RED→GREEN).
- **Repro (was):** corrupt `manifest.json` bytes (truncated write) → `restore_backup`
  raised `json.JSONDecodeError`, not `BackupVerificationError`; dump record with
  `evidence_hash` but no `canonical_json` → `KeyError`.
- **Severity:** LOW-MEDIUM (still fails closed — exception propagates — but breaks
  the documented operator-facing error contract of the module; §6 error reporting).
- **Proposed minimal fix:** wrap both `json.loads` sites and record-field access,
  raising `BackupVerificationError` with file name only (no content — keeps
  secrets out of error text).
- **Approval:** none (error-type contract tightening; fail-closed preserved).
- **Regression tests:** corrupt-manifest, corrupt-dump, missing-field cases.

### D-RH-4 — Manifest `artifacts` section is unvalidated (traversal + silent
verification skip)
- **Status:** **FIXED 2026-10-18** (exact artifact-set gate
  `{snapshot, dump}`; drills `test_artifact_traversal_entry_rejected`,
  `test_omitted_artifact_entry_rejected` RED→GREEN; the traversal drill proved
  the old code silently hashed a file *outside* the backup dir).
- **Repro (a):** manifest with `"artifacts": {"../outside.db": "<hash>"}` →
  `backup_dir / name` escapes the backup dir and hashes an arbitrary file
  (absolute names replace the base path entirely in pathlib).
  **Repro (b):** `"artifacts": {}` → the snapshot and dump are never hash-checked
  against the manifest at all; the remaining checks are unkeyed self-consistency
  (attacker-editable), i.e. the trust root is silently skipped.
- **Severity:** MEDIUM (trust boundary: the manifest is untrusted input; §8 path
  traversal; fail-open on omission).
- **Proposed minimal fix:** require
  `set(artifacts) == {SNAPSHOT_NAME, DUMP_NAME}` exactly (export always writes
  exactly this set), naming missing/unexpected entries in the error.
- **Approval:** none (fail-closed format gate, same class as R14; no valid export
  can regress — asserted by existing roundtrip test).
- **Regression tests:** traversal-name test, omitted-entry test.

### D-RH-5 — `_sha256_file` reads entire files into memory
- **Status:** **FIXED 2026-10-18** (chunked 1 MiB read loop; equivalence drill
  `test_chunked_file_digest_matches_reference`).
- **Repro (was):** `_sha256_file` = `hashlib.sha256(path.read_bytes())` (L64-65): a
  multi-GB snapshot allocates multi-GB RAM (§8 unbounded resource consumption).
- **Severity:** LOW.
- **Proposed minimal fix:** chunked 1 MiB read loop, same digest.
- **Approval:** none (no observable behavior change; digest equivalence test).

### D-RH-6 — No staged-file verification between copy and atomic swap (TOCTOU)
- **Status:** **FIXED 2026-10-18** (staged digest vs manifest before the swap;
  drill `test_staged_snapshot_must_match_manifest_digest` RED→GREEN).
- **Repro (was):** modify `snapshot.sqlite3` after step-1 hash verification but before/during
  the staging copy → bytes different from the manifest-attested digest are staged;
  row chain check only proves self-consistency of whatever rows are present (unkeyed),
  then `os.replace` commits them.
- **Severity:** LOW-MEDIUM (concurrent modification during restore; §7).
- **Proposed minimal fix:** after staging + fsync, require
  `sha256(tmp) == manifest.artifacts[SNAPSHOT_NAME]`; mismatch →
  `BackupVerificationError` with live DB untouched (existing finally cleans tmp).
- **Approval:** none (fail-closed pre-swap postcondition; §6 mandate).
- **Regression tests:** post-verification mutation test.

### D-RH-7 — Dangling symlink at the `.recovery_tmp` staging path escapes base_path
- **Status:** **FIXED 2026-10-18** (both staging sites: `unlink(missing_ok=True)`
  clears dangling links; `O_CREAT|O_EXCL` refuses any re-planted entry). Drills
  `test_dangling_symlink_staging_cannot_escape`,
  `test_restore_content_dangling_symlink_staging_cannot_escape` currently
  **skip on this host** (Windows symlink privilege unavailable) — they run
  GREEN only on a privileged/POSIX host; that execution remains a release gate.
- **Repro:** attacker plants `file.txt.recovery_tmp` as a *dangling* symlink in the
  workspace. `_execute_restore_content` L1899 `temp_path.exists()` follows the link
  (False for dangling) → no unlink → `temp_path.write_bytes` follows the link and
  creates/overwrites the link's target **outside** `base_path` (§7/§8 symlink escape).
  Requires attacker write access to the workspace directory (hostile-project threat
  model, in scope per mission §8 trust boundaries).
- **Severity:** MEDIUM under hostile-workspace model; LOW for trusted projects.
- **Proposed minimal fix:** `temp_path.unlink(missing_ok=True)` (removes links,
  dangling or not) and create the staging file with
  `O_CREAT|O_EXCL|O_NOFOLLOW` (atomic refusal of any pre-planted entry).
- **Approval:** none (hardening of a staging detail; observable contract unchanged).
- **Regression tests:** dangling-symlink test (skip-if-unsupported), stale-temp
  replacement test.

### D-RH-8 — Failed/partial staging errors surface as raw `OSError` (disk-full,
permission)
- **Status:** **FIXED 2026-10-18** (staging `OSError` and sqlite/DBAPI failures
  wrapped as `BackupVerificationError`, `PermissionError` keeps the
  "application to be stopped" guidance; drills
  `test_disk_full_staging_fails_closed_with_contract_error`,
  `test_replace_permission_error_fails_closed_with_guidance`,
  `test_unreadable_snapshot_fails_closed_with_contract_error` RED→GREEN; every
  drill asserts the live target byte-identical + no staging residue).
- **Repro:** `ENOSPC` during the staging copy, or `PermissionError` from
  `os.replace` (target held open) → raw `OSError` propagates instead of the
  module's documented fail-closed exception type. Target is already safe
  (untouched, tmp cleaned) — this is an error-reporting contract gap only.
- **Severity:** LOW.
- **Proposed minimal fix:** catch `OSError` in the staging block, re-raise as
  `BackupVerificationError` (`from exc`) naming operation + `strerror`, keeping
  the existing "restore requires the application stopped" guidance for
  `PermissionError`.
- **Approval:** none (error-type contract; behavior unchanged otherwise).

### D-RH-9 — `export_backup` can destroy a previous valid backup on re-export
- **Status:** **FIXED 2026-10-18** (export refuses a directory containing
  `manifest.json`; drill `test_export_refuses_to_overwrite_existing_backup`
  RED→GREEN and asserts the previous backup's artifacts stayed byte-identical).
- **Repro (was):** export into a directory that already holds a backup; crash/failure
  after the new snapshot write but before the new manifest write → the old
  manifest no longer matches the new artifacts → the previous (last known-good)
  backup is unrecoverable (§6: never overwrite the last known-good state before
  the replacement is verified).
- **Severity:** LOW-MEDIUM (requires re-using an output directory; no in-repo
  caller does).
- **Proposed minimal fix:** refuse to export into a directory containing
  `manifest.json` (`BackupVerificationError`, operator picks a fresh directory or
  removes the old one explicitly).
- **Approval:** none (no caller/test re-exports into the same directory — verified
  by grep; safety-positive gate).
- **Regression tests:** second-export-refused test.

## 2. D-MIG-1b (migration `3cebbede5768`) — approval-gated, handled per mission §5

- **State:** historical migration files remain **untouched**. RC1
  (`downgrade()` = `pass`), RC2 (D3 model/migration drift), RC3 (unguarded
  `ADD COLUMN`) as previously proved on 2 disposable DBs.
- **This session — independent re-verification, disposable DBs only:**
  1. Full repro re-ran and matched every prior claim: `downgrade base` exits 1
     at `no such index: ix_recovery_reports_incident_id`, stamped
     `0010_causal_state_recovery` after the failure; all 8 tables missing;
     re-upgrade then dies on duplicate column; final state stuck at
     `fc5e7844e4dd` — bricked in both directions.
  2. **New partial-traversal variant confirmed** (probe
     `d_mig1_partial_probe.py`): `downgrade fc5e7844e4dd` **exits 0**
     (operator told the rollback worked) while crossing `3cebbede5768` whose
     `downgrade()` is `pass`; `after_state_snapshot` stays present below the
     new stamp; the next `upgrade head` **fails** on duplicate column. A
     *successful* downgrade silently bricks forward recovery.
  3. Index-name consistency probed on a fresh upgraded DB: 30 registered model
     tables, **0 index-name mismatches** → promoted to a live regression guard
     (`TestAlembicIndexConsistency.test_index_names_match_models_after_fresh_upgrade`).
- **Tests added** (`tests/integration/test_alembic_migration_safety.py`):
  - `test_successful_partial_downgrade_must_not_brick_reupgrade` — visible
    xfail, strict=False, reason states the exact observed evidence; never
    silently converted, never hidden.
  - `TestAlembicIndexConsistency` — live green guard (runs in the normal suite).
  Existing upgrade/downgrade/re-upgrade xfails unchanged.
- **Approval needed:** R10 repair proposal
  (`v6_m8_lab/r10_d_mig1_repair_proposal.md`) — C-class; not implemented without
  explicit approval. M-PKG/G6 likewise untouched.

## 3. Untested risks (documented, not defects yet)

| ID | Risk | Notes |
|---|---|---|
| U1 | POSIX `os.replace` succeeds while the app holds the DB open (unlike Windows) → app keeps writing to the replaced-away inode | Restore must require app stopped on **all** platforms; POSIX will not enforce it. Beta docs limitation; no POSIX environment available here to test. |
| U2 | Backup/temp file permissions: export artifacts get default umask (potentially world-readable on POSIX); restore's swap makes the target inherit the staging file's mode, which can loosen a pre-existing `0600` DB file | Proposal **R17** (chmod 0600 on export artifacts + preserve target mode across swap) needs a POSIX test environment; register only, not implemented blind. |
| U3 | `tool_security._validate_host` performs a real DNS lookup (`socket.getaddrinfo`) when validating hosts | Intended SSRF defense; disclosed in beta privacy notes (local DNS resolution possible; no telemetry, no uploads — verified by grep: no `requests/httpx/aiohttp/urllib.request` usage in recovery paths). |
| U4 | Restore-vs-running-app on Windows relies on the OS failing the replace, not on an explicit precondition check | Message guidance kept; explicit PID/liveness precondition would be a behavior change (approval-gated if desired). |
| U5 | Manifest integrity is unkeyed SHA-256: an attacker with write access to the backup directory can forge a *fully self-consistent* backup | Inherent to the design (tamper-evidence vs accidental/partial edits only). Keyed manifest signature = IDEA-1. |

## 4. Missing capabilities (not defects)

- **M1** ~~No real process-kill test of restore phases~~ — **closed on Windows
  2026-10-18** (session 4, user-authorized): real `TerminateProcess` kills
  mid-recovery, 20/20 iterations, 0 torn writes, 0 invariant violations,
  20/20 retries succeeded; deterministic pre-swap hook + organic spray;
  evidence `logs/v6_final_mission_session4/m1_kill_evidence.json` (failed
  attempt 1 preserved: drill setup bug, adapter behaved correctly). POSIX
  process-kill remains untested (M3).
- **M2** No real disk-full test (needs an isolated mount/quota; mocked `ENOSPC`
  used, explicitly not claimed as OS proof; reproducible procedure prepared in
  `INTERLOCK_V6_FINAL_HANDOFF.md`).
- **M3** No POSIX/macOS execution environment → U1/U2 untestable here; external
  compatibility not claimed.
- **M4** CI×2 (push authorizations), Docker/PostgreSQL/Redis, production access,
  idle-window latency rerun, frozen Suite A/B execution — external blockers
  (unchanged; exact commands recorded in log §F).

## 5. Future ideas (approval-gated product decisions)

- **IDEA-1** Keyed manifest signature (HMAC/signature over manifest) to
  authenticate backups against a full-directory attacker (extends R5 class).
- **IDEA-2** Explicit restore precondition API (verify application stopped) —
  behavior/contract change (R4 class).

## 6. Approval gates summary (nothing below is modified without authorization)

| Gate | Class | State |
|---|---|---|
| R10 migration repair + M-PKG/G6 | C | proposal ready, untouched |
| R4/R5/R8/R13/R15/R16 | behavior/contract/threshold | untouched (prior session) |
| R17 backup/restore POSIX permission hardening | new proposal, needs POSIX test env | register only |
| Frozen Suite A (100k) / Suite B (31k) execution | execution gate | not executed |
| CI pushes, Docker/PG/Redis, production, idle-window latency rerun | external | blocked |
| Historical migration files | protected | byte-identical |

## 7. Session execution order — results (2026-10-18)

1. **Done.** 19 fault-injection drills written and RED-verified against the
   pre-fix code (13 distinct current-defect failures + 2 honest symlink skips +
   3 pre-existing-behavior lock-ins + 1 equivalence lock).
2. **Done.** Both D-MIG repros independently re-run on disposable DBs; partial-
   traversal variant confirmed; §5 tests added (visible xfail + live index
   guard).
3. **Done.** Nine minimal fixes implemented; targeted GREEN:
   fault-injection (19), drill (8), filesystem adapter (all), alembic safety
   (11 passed + 4 xfailed), scenario proofs (10) — exit 0.
4. **Done.** `ruff check` clean on all four changed/added files; `mypy` strict
   clean on both changed app files; `ruff format` deliberately NOT run (CI
   enforces only `ruff check`, and untouched files are not format-clean —
   reformatting would exceed narrow scope).
5. **Done.** Beta-readiness checklist created; pilot demo re-run 4/4 with
   fresh versioned evidence (`evidence_20261017T203353Z.json`) — exercising
   the NEW staging code path.
6. **In progress at authoring time:** whole-suite re-verification run #3 +
   coverage; preservation re-check vs the 200-entry baseline; append-only log
   entry.
