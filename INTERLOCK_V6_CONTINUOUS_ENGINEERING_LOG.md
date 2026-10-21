# INTERLOCK V6 — CONTINUOUS ENGINEERING LOG

Versioned, append-only engineering log. Each session adds a new entry; prior
entries are never overwritten. All paths relative to the repository root unless
marked absolute. Venv python = `.venv/Scripts/python.exe`. Targeted runs use
`-o addopts=` (coverage off) and `-p no:cacheprovider`.

---

## Session 1 — 2026-10-17 (Continuous Engineering Excellence Mission, first pass)

### A. Criteria status (this session)

| Criterion | Status | Basis |
|---|---|---|
| R1 fix verification (regression + containment) | **PASS** | path-security dir 33 passed + property suite 5 passed + live-agent 23 passed (earlier this session), 68-passed combined run exit 0 |
| R3 reference-adapter contract tests verified | **PASS** (assertions re-inspected: honest refusal states, never-self-certify, idempotency-mismatch conflict, 4 drift states, simulate warnings, honest failure reporting) | `tests/unit/test_reference_adapter_contracts.py` 26 passed; per-file coverage measured (see §G) |
| R6 alembic safety tests verified | **PASS + honest xfail** | 4 passed / 3 xfailed (D-MIG-1, D-MIG-1b, D3), exit 0 |
| D-MIG-1 investigation (reproduce disposable-only) | **PASS — defect confirmed and ESCALATED** | two repro scripts, both disposable; new severity D-MIG-1b |
| D-MIG-1 repair proposal (data-loss/history/compat/rollback) | **PASS (proposal only — not implemented)** | `%TEMP%\opencode\v6_m8_lab\r10_d_mig1_repair_proposal.md` |
| Backlog R4/R5/R8/R11–R16 inspected & ranked | **PASS** | §D below; safe-now items implemented, rest approval-gated |
| Suite A/B manifests reviewed (hashes/allocations/classifications/verification logic) | **PASS (design review)** — still **NOT EXECUTED** (review gate) | §E below |
| External evidence inventory | **PASS (inventory)** — CI/Docker/PG/Redis/real-faults/frozen-campaigns/production remain **NOT RUN / BLOCKED** | §F below |
| Customer pilot (disposable demo, criteria, rollback) | **PASS — demo exit 0, 4/4 legs independently verified** | `scripts/pilot_demo_v1.py`, `logs/v6_pilot_demo_v1/evidence.json`, `INTERLOCK_V6_PILOT_PLAN.md` |
| R11 restore atomicity | **PASS — implemented + RED/GREEN** | §C below |
| R14 restore format gates | **PASS — implemented + tests** | §C below |
| R12 audit redaction | **PASS — implemented + RED/GREEN vs real HEAD** | §C below |
| Latency performance tests | **FAIL (known, unchanged)** | 3 open failures; idle-window rerun needs scheduling approval |
| CI workflows / container / PG / Redis / real process-kill-network-disk | **BLOCKED EXTERNALLY / NOT TESTED** | no authorization/infrastructure |

### B. Exact tests run this session (command → result)

1. `pytest tests/integration/test_workspace_protection/ tests/unit/test_reference_adapter_contracts.py tests/integration/test_alembic_migration_safety.py -o addopts= -q -p no:cacheprovider` → **68 passed, 1 skipped, 2 xfailed, exit 0** (115.66s) — R1/R3/R6 verification.
2. `pytest tests/integration/test_alembic_migration_safety.py …` → **4 passed, 3 xfailed, exit 0** (70.93s) — after adding D-MIG-1b test.
3. `pytest tests/unit/test_backup_restore_drill.py …` → **6 passed, exit 0** (R11), then **8 passed, exit 0** (R14).
4. `pytest tests/unit/test_audit_logger_redaction.py test_audit_logger_comprehensive.py test_compliance_export.py tests/integration/test_intent_audit_logging.py tests/unit/test_merkle_audit_log_service.py …` → **56 passed, exit 0**.
5. `pytest tests/unit -o addopts= -q -p no:cacheprovider` → **2396 passed, 1 skipped, exit 0** (367.54s).
6. Skip identification run (`-rs` on candidates) → the 1 skip = `tests/unit/test_regression_critical_fixes.py:304: Key manager not available` (environment-conditional, pre-existing, explained).
7. Scoped R3 coverage run → 55 passed, 1 skipped; per-file coverage in §G (its exit 1 is the pyproject 80% gate applied to a deliberately 3-file scope — a measurement-scope artifact, not a suite failure; full-suite numbers in §G).
8. Static: `ruff check` **exit 0** on every new/changed file; `mypy` **exit 0** on `backup_restore.py`, `audit_logger.py` (and earlier `path_security.py`). Two `noqa: T201` (CLI demo prints) + prior `noqa: S603/S311` are inline, config untouched.
9. Pilot demo run ×2 (initial buggy flow exit 1 preserved as evidence, corrected contract flow exit 0).
10. D-MIG-1 repros ×2 (disposable, deleted after evidence capture).

### C. Defects found, root causes, fixes implemented (with RED/GREEN)

1. **D-MIG-1b (NEW, escalated)** — a failed `alembic downgrade base` bricks the database in BOTH directions. Root causes: (RC1) `3cebbede5768.downgrade()` is `pass`; (RC2) model/migration schema drift D3 — boot's `create_all` re-creates the 8 dropped tables with model-schema indexes (`report_id unique=True` → SQLite autoindex, not `ix_recovery_reports_report_id`), so `0010.downgrade()` fails even on booted DBs; (RC3) unguarded `ADD COLUMN` makes re-upgrade die on `duplicate column name`. Reproduced on2 disposable DBs (`d_mig1_repro.py`, `d_mig1_booted_roundtrip.py`); pinned as xfail `test_failed_downgrade_must_not_brick_reupgrade`; full repair proposal written (approval-gated; historical migration untouched).
2. **R11 (fixed)** — `restore_backup` copied the snapshot onto the live DB BEFORE the restored-row chain check and non-atomically. Fixed: stage beside target → verify → `os.replace` (atomic swap). RED (verbatim pre-fix body) proved the healthy target was overwritten by a rejected snapshot (`target_untouched=False`); GREEN byte-identical, no staging leftover. Also closes the "crash mid-copy leaves torn DB" hole.
3. **R14 (fixed)** — restore ignored `manifest_version`/`dump_version`/`hash_spec`. Fixed: fail-closed format gates (v1/v1/v2 constants) +2 regression tests (unknown manifest version, future dump version, unknown hash spec — all rejected pre-materialization).
4. **R12 (fixed)** — `log_security_event`/`log_compliance_event` wrote `**details` verbatim despite the "Never logs secrets" docstring. Fixed: recursive key-marker + Bearer-value redaction applied BEFORE persistence and BEFORE the compliance hash (chain still verifies; tamper of redacted field still breaks chain). RED via pristine HEAD module leaked `hunter2-SECRET`/`s3cr3t-NESTED` into the JSONL; GREEN masked, benign fields intact.
5. **Pilot-demo flow defect (mine, not the product's)** — v1 of the demo captured evidence before the fault, so the adapter's conflict guard (`after_snapshot` hash vs current, `filesystem_recovery_adapter.py:1886-1894`) correctly refused. Root cause: demo mis-modeled the adapter contract (capture AFTER action with `before_snapshot` from a pre-action capture). Fixed the demo (not the product); added a human-change-preservation leg that now proves the guard. First failing run preserved in evidence history.

### D. Backlog ranking (safety impact → correctness → production risk)

1. **R10 / D-MIG-1b** (C-class) — migration rollback impossible + brick risk. Approval-gated; proposal ready.
2. **R5** — integrity verifier accepts tampered payloads (field-presence only). Approval-gated (schema/versioning).
3. **R13** — no executor deadlines/backoff/mid-plan cancellation. Approval-gated (behavior change).
4. **R15** — executor-layer bounds absent; circuit breaker not in recovery path; quota opt-in. Approval-gated (thresholds).
5. **R11 — DONE this session.**
6. **R14 — DONE this session.**
7. **R12 — DONE this session.**
8. **R4** — resume default alignment (fail-safe direction, behavior change). Approval-gated.
9. **R8** — legacy canned response replacement (product decision). Approval-gated.
10. **R16** — measured false-alarm budget (creates thresholds → prohibited without approval).

### E. Suite A/B manifest review findings (design gate)

- sha256 recompute matches `MANIFESTS.sha256` exactly (A `dc74ebd2…c5189b`, B `da45c22c…115d4c25`).
- Allocations exact: A 26 scenarios sum=100,000 (7000×5, 3800×3, 4500×3, 4000×2, 2500×3, 3000×3, 1500×3, 1600); B 31×1000=31,000. 0 duplicate IDs.
- Fields complete (A: 10 required incl. `independent_post_recovery_verification`; B: 12 incl. `independent_verification`, `unsafe_recovery_condition`, `false_success_condition`).
- Classifications: A all `recovered` (recovery-measurement); B 20 `expected_refusal` + 11 `expected_failure_detected`. Denominator rules forbid counting refusal as recovery; failures never excluded (new versioned manifest required instead).
- Review notes for authorization: (1) A-024 (`ws_inside_ok`) now depends on the **R1 fix** being present at execution time; (2) B-019 simulates a timeout *exception*; real deadline enforcement is absent (R13) — valid but limited; (3) A's primary-metric text states the 100000/100000 *target*; shortfalls are reported, not hidden; (4) A/B use different verification key names (cosmetic).

### F. External evidence inventory (not run — minimum requirement each)

| Evidence | State | Minimum requirement |
|---|---|---|
| CI runs (`.github/workflows/ci.yml`) | never run | two separate push authorizations (G7) |
| Container build/verify (`docker-verify.yml`) | never run | push authorization + Docker host in CI |
| Security workflow (`security.yml`) | never run | push authorization (local dated scans already clean) |
| Real PostgreSQL migrations/integration | never run | PG instance or CI service container |
| Real Redis rate-limit/lease backends | never run | Redis instance or CI service container |
| Frozen Suite A/B campaigns | designed, gated | scenario/criteria review approval + resource bounds run |
| Idle-window latency rerun (3 open failures) | blocked | scheduling approval for idle window |
| Real process-kill / network / disk-full / clock-skew | not tested | disposable VM/CI harness |
| Production/canary evidence | prohibited | explicit production authorization |

### G. R3 actual coverage (honest numbers)

Scoped to R3 alone: `file_version_adapter.py` **74%**, `database_record_adapter.py` **54%**, `config_rollback_adapter.py` **54%** (55 passed / 1 skipped; the run's exit 1 is the pyproject 80%-total gate applied to a 3-file scope — measurement artifact).
Full **unit-suite** scope: `file_version_adapter.py` **74%**, `database_record_adapter.py` **69%**, `config_rollback_adapter.py` **54%**, unit-total 77.44% (again below the 80% gate — the gate's authoritative scope is the whole `tests/` tree; unit-only exit 1 is the same scope artifact, not a regression). Uncovered adapter lines (full-unit): config_rollback 44-46, 108-113, 120-126, 151, 159-164, 172-174, 234; database_record 44-48, 116, 119, 131-132, 134->137, 162, 171, 200-209, 269, 281; file_version 45-47, 111, 151, 159-164, 172-174, 246.
Authoritative whole-suite coverage: **83.57%** at run #3 (2,867 collected, pre-this-session); current whole-suite re-measurement added in the session-1 addendum below.

### H. Files changed this session (complete, disclosed)

Product: `app/infrastructure/backup_restore.py` (R11 atomic verify-before-swap; R14 format gates), `app/infrastructure/logging/audit_logger.py` (R12 redaction).
Tests: `tests/unit/test_backup_restore_drill.py` (+3: R11 zero-side-effect, R14 manifest/dump gates), `tests/unit/test_audit_logger_redaction.py` (new, 3 tests), `tests/integration/test_alembic_migration_safety.py` (+1 xfail D-MIG-1b), `scripts/pilot_demo_v1.py` (new demo).
Docs: `INTERLOCK_V6_PILOT_PLAN.md`, this log, additive status section in `INTERLOCK_V6_PHASE1_BASELINE_AND_REMEDIATION_PLAN.md`.
Lab evidence (absolute, `%TEMP%\opencode\v6_m8_lab\`): `d_mig1_repro.py`, `d_mig1_booted_roundtrip.py`, `r10_d_mig1_repair_proposal.md`, `r11_red_check.py`, `r12_red_check.py`, `review_suite_scenarios.py`.
Nothing staged/committed/pushed; historical migrations, root `.env`, thresholds, markers, and config untouched.

### I. Repository preservation verification (end of session)

HEAD `145a3d9`; staged 0; stash 1; `web/` deletions 60; campaign/benchmark artifacts untracked. Porcelain growth fully explained (188 baseline → +7 session-1-mission files → 195 → +2 R12 files = 197).

### J. Remaining risks and required approvals (prioritized)

1. R10 migration downgrade repair (proposal ready; sequencing M-PKG → R10 → R5 → R4 → R8).
2. M-PKG/G6 application; D3 drift; two push authorizations (G7); CI/DB/cache externalization; idle-window rerun; frozen Suite A/B execution authorization; R13/R15/R16 design review (executor deadlines/backoff/cancellation, bounds, false-alarm budget).
3. Residual: duplicate-replay after successful restore reports `blocked_by_conflict` (safe direction, conservative status); `SQLAlchemyStateCheckpointRepository` still lacks a direct test; alert delivery untested.

### K. Next highest-priority action

Await approval decisions on R10 + M-PKG/G6 (the only C-class items). Meanwhile safely actionable: none of the remaining backlog qualifies without approval (R4/R5/R8/R13/R15/R16 all change behavior, contracts, or thresholds).

---

## Session 1 addendum — 2026-10-18 (authoritative whole-suite run + temp-dir incident)

### G-add. Authoritative whole-suite coverage (final)

Command: `python -m pytest tests -q -p no:cacheprovider --tb=short -rEf --cov-report=term` (full `tests/` tree, default addopts incl. the pyproject 80% gate).

- **Run #2 (authoritative): 2904 passed, 7 skipped, 3 xfailed, 0 failed, 0 errors, exit 0** in 1951.95s (32:31). **Total coverage 83.78%** (branch, `source = app, sdk`), gate `Required test coverage of 80.0% reached` → exit 0. Full log: `logs/v6_full_suite_v1/full_suite_run2_20261018.log` (also `%TEMP%\opencode\v6_m8_lab\full_suite_rerun.log`).
- Adapter files (whole-suite scope, final): `file_version_adapter.py` **74%**, `database_record_adapter.py` **69%**, `config_rollback_adapter.py` **54%**; `backup_restore.py` **90%**, `audit_logger.py` **99%**.
- 3 xfailed = the D-MIG-1/D-MIG-1b pair + 1 pre-existing; all kept visible, none asserted green.
- **Run #1 (superseded, kept on record): 2759 passed, 7 skipped, 3 xfailed, 145 errors, exit 1**, coverage gate itself passed at 81.32%. All 145 errors were at *fixture setup* (`tmp_path`), not in test bodies; 2759 + 145 = 2904 = exactly run #2's pass count, i.e. every errored test passed on immediate re-run with an identical command. Root cause was environmental, not the codebase — see §L: a temp-directory cleanup event during run #1 destroyed `%TEMP%\opencode\` (wiping the lab evidence) and pytest's `pytest-of-Dell` numbered dirs mid-run. Evidence: drill suite green standalone (8/8, exit 0) both before and after; disk had 126 GB free; identical command fully green in run #2; no repository file changed between runs.

### L. Incident: `%TEMP%` cleanup wiped lab evidence — recovered, disclosed

- **What:** between run #1 (started 17-10 23:01:36) and the run #2 relaunch (23:37), an external cleanup emptied `C:\Users\Dell\AppData\Local\Temp\opencode\`, deleting all 13 session-1 `v6_m8_lab` evidence files referenced by the remediation plan, mission report, and this log (§H). The relaunch initially failed with `DirectoryNotFoundException`, which surfaced it.
- **Recovery:** all 13 files reconstructed from the opencode session database (`session_message` rows: every file had been created via `write` tool calls, with 5 subsequent `edit` calls replayed in order — `oldString` matched exactly once in each case). Files restored byte-for-byte to their original documented paths.
- **Integrity proof:** (1) all 11 recovered `.py` files pass `py_compile`; (2) exhaustive scan of every shell command touching `v6_m8_lab` shows the only mutations were `Remove-Item` of two disposable `.db` repro databases — no `>>`/`Set-Content`/`Add-Content` ever modified evidence files outside write/edit tools; (3) SHA-256 manifest of all 13 restored files: `logs/v6_full_suite_v1/recovered_lab_evidence_SHA256.txt`.
- **Disclosure:** recovery scripts live in `%TEMP%\opencode\v6_m8_lab\` (`recover_lab_files.py`, `complete_recovery.py`, `verify_recovery.py`, `check_edits.py`, `inspect_msgs.py`) with a `recovered_lab\` copy of the raw reconstruction. This incident is why run #1's 145 errors occurred; it is recorded rather than silently re-run, per never-erase-failed-attempts.
- **Repo impact:** none. HEAD `145a3d9`, staged 0, stash 1, porcelain 200 throughout; `logs/v6_full_suite_v1/` is git-ignored (0 new porcelain entries).

### I-add. Repository preservation verification (end of session, re-checked after incident)

HEAD `145a3d9`; staged 0; stash 1; porcelain 200 = 67 modified tracked + 60 `web/` deletions + 73 untracked (67 + 60 + 73 = 200); `coverage.xml` unchanged/ignored; campaign artifacts, raw results, manifests untouched. Frozen Suite A/B **still not executed**.

## Session 2 - 2026-10-18 (Recovery hardening, real-world validation & beta readiness mission)

### M. Criteria status (this session)

- **Validation:** whole suite re-verified green (run #3 below); coverage gate 80 % met (83.81 %); migration index-name consistency promoted from untested to a live green guard; migration downgrade/re-upgrade remains RED with 4 visible xfails (R10 approval pending — files untouched).
- **Recovery:** 9 concrete defects (D-RH-1..9) found by end-to-end audit, each RED-tested against pre-fix code, then fixed with narrow fail-closed changes and re-run GREEN. Failed recovery attempts now leave no residue and stay retryable; backups are point-in-time consistent; the manifest is an exact-set trust root; every verification failure raises a typed error and provably leaves the live target byte-identical.
- **Production:** unchanged externally-blocked (CI×2, Docker/PG/Redis, audit, idle-window latency). Beta-readiness checklist created with per-criterion GREEN/RED/BLOCKED/KNOWN-LIMITATION status.
- **Security/privacy:** path traversal (manifest artifacts) and staging symlink-escape fixed + drilled; secrets provably absent from error text; no telemetry verified by grep; DNS-lookup disclosure recorded; POSIX backup-permission hardening registered as proposal R17 (not implemented blind — no POSIX test env).

### N. Exact tests/commands run this session (command → result)

- `pytest tests/unit/test_recovery_fault_injection.py tests/integration/test_alembic_migration_safety.py -o addopts= -p no:cacheprovider --tb=line -q -rxfX` (pre-fix) → **14 failed, 7 passed, 2 skipped, 4 xfailed, exit 1** — the RED evidence: 13 failures are D-RH-1..9 reproductions, 1 was a registration-order artifact (fixed by scoping the assertion, see P); the 2 skips are symlink drills (host forbids symlink creation — honest `pytest.skip`).
- Same command + drill + filesystem adapter files (post-fix) → **50 passed, 2 skipped, 4 xfailed, exit 0 (142.87 s)**.
- `pytest tests/integration/test_scenario_proofs_v6.py -o addopts= -p no:cacheprovider -q` → 10 passed.
- `ruff check` on the 4 changed/added files → clean; `mypy` (strict) on both changed app files → clean. `ruff format --check` deliberately not run into the tree: CI enforces only `ruff check app sdk`, and untouched repo files are not format-clean — reformatting would exceed narrow scope (disclosed decision).
- `python scripts/pilot_demo_v1.py` → 4/4 verdicts true, exit 0, evidence `logs/v6_pilot_demo_v1/evidence_20261017T203353Z.json` (fresh run exercising the NEW staging code path).
- Whole suite run #3: `pytest tests -q -p no:cacheprovider --tb=short -rEf` → **2922 passed, 9 skipped, 4 xfailed, exit 0, coverage 83.81 % (gate 80), 3719.82 s**. Deltas vs authoritative run #2 are exactly this session's additions: +18 passed (17 fault-injection drills + 1 index-name guard), +2 skips (symlink drills), +1 xfail (partial-downgrade) — no pre-existing test changed status. Log: `logs/v6_recovery_hardening_session2/full_suite_run3.log`.

### O. Defects found, root causes, fixes (all RED→GREEN; register `INTERLOCK_V6_RECOVERY_HARDENING_REGISTER.md`)

- **D-RH-1 (M-H, recovery correctness):** `_execute_restore_deleted_file` wrote directly onto the target; a failed/killed attempt left partial bytes there and every retry hit `BLOCKED_BY_CONFLICT` on its own residue. Fix: stage to `<target>.recovery_tmp` (O_EXCL), verify staged hash pre-swap, concurrent-creation recheck, `os.replace`; failure/kill leaves only staging, cleared on retry. Drills: failed-attempt retryable, stale-staging interruption.
- **D-RH-2 (M, torn backups):** export read the dump from the live DB after the snapshot (two points in time), and restore never cross-checked snapshot rows vs `evidence_count`. Fix: dump derived from the snapshot; strict count cross-check before the swap. Drills: race injection, row-removal-with-recomputed-manifest.
- **D-RH-3 (L-M, error contract):** corrupt manifest/dump JSON raised raw `JSONDecodeError`, malformed records raw `KeyError`/`AttributeError`. Fix: typed `BackupVerificationError` everywhere (file names only, no content).
- **D-RH-4 (M, trust root):** manifest `artifacts` unvalidated — traversal names were hashed outside the backup dir, omitted entries silently skipped verification. Fix: exact-set gate `{snapshot.sqlite3, evidence_dump.json}`.
- **D-RH-5 (L):** whole-file hashing → chunked 1 MiB loop (equivalence-drilled).
- **D-RH-6 (L-M, TOCTOU):** no staged-digest verification between copy and swap. Fix: staged sha256 must equal the manifest digest before any chain check or swap.
- **D-RH-7 (M hostile-workspace):** dangling symlink at a staging path was followed, writing outside `base_path`. Fix (both backup and adapter staging): `unlink(missing_ok=True)` + `O_CREAT|O_EXCL`. Drills skip on this host (no symlink privilege) — **execution on a privileged/POSIX host remains a release gate**.
- **D-RH-8 (L):** staging/replace `OSError` and unreadable-snapshot DBAPI errors surfaced raw. Fix: wrapped as `BackupVerificationError`, `PermissionError` keeps the "application to be stopped" guidance; drills assert live target byte-identical + no residue.
- **D-RH-9 (L-M):** re-export into an existing backup dir could destroy the previous last-known-good set on mid-failure. Fix: export refuses a dir containing `manifest.json`; drill proves the old artifacts stay byte-identical.

### P. D-MIG-1b independent verification and §5 tests (disposable DBs only; migrations untouched)

- Full repro re-ran and matched every prior claim (downgrade base exits 1 at `no such index: ix_recovery_reports_incident_id`; stuck at `fc5e7844e4dd`; re-upgrade duplicate-column; bricked both directions).
- **New evidence — partial-traversal variant:** `downgrade fc5e7844e4dd` **exits 0** crossing `3cebbede5768` (`downgrade()` = `pass`); `after_state_snapshot` remains present below the stamp; subsequent `upgrade head` fails on duplicate column. A *successful* rollback silently bricks forward recovery — worse operator-facing case than the failed downgrade. Codified as visible xfail `test_successful_partial_downgrade_must_not_brick_reupgrade` (strict=False, reason cites the exact observed evidence).
- Index-name consistency: probe found 30/30 registered tables consistent → live green guard `TestAlembicIndexConsistency.test_index_names_match_models_after_fresh_upgrade`. Note: whether the 8 migration-dropped tables appear in `Base.metadata` depends on process import order (0 vs 8) — deliberately not asserted; table-level drift stays under the D3 `alembic check` xfail.
- Probe scripts + outputs indexed in `logs/v6_recovery_hardening_session2/EVIDENCE_INDEX.md` (durable, git-ignored — the %TEMP% lesson).

### Q. Security & privacy review findings

Fixed+drilled: manifest path traversal, staging symlink escape, secret-free error text (sentinel drill). Verified: no telemetry/network egress in recovery paths (grep), no `subprocess`/`shell=True`/`os.system` in `app/`. Disclosed limitations: `tool_security._validate_host` performs real DNS lookups (intended SSRF defense); backup/temp POSIX permissions + mode-loosening across restore swap = proposal R17 (needs POSIX env); restore-vs-running-app enforcement is OS-dependent (U1). Minimum permissions documented in the beta checklist: local FS read/write inside explicitly protected workspaces + local SQLite files it owns; no admin, no network.

### R. Performance review (thresholds reviewed, NOT changed)

AuthZ 2.85 ms median / 7.97 ms p95 vs 1 ms mean threshold, coordination p95 5.99 ms vs 5.0 ms — both remain RED as documented; thresholds untouched; idle-window rerun still blocked (commands in §F). Only diagnostic improvement: chunked hashing removes whole-file memory spikes.

### S. Beta readiness (§9)

`INTERLOCK_V6_BETA_READINESS_CHECKLIST.md` created: per-criterion GREEN/RED/BLOCKED/KNOWN-LIMITATION. Verdict: recovery correctness for supported paths demonstrably stronger with reproducible evidence; beta gated on external blockers (CI, infra, audit, idle latency), R10 approval (4 visible migration xfails), privileged-host symlink drill, R17 POSIX permissions, and production checklist/runbook (external env needed).

### T. Files changed this session (complete, disclosed)

Modified: `app/infrastructure/backup_restore.py`, `app/infrastructure/recovery/filesystem_recovery_adapter.py`, `tests/integration/test_alembic_migration_safety.py`, this log. New (untracked): `INTERLOCK_V6_RECOVERY_HARDENING_REGISTER.md`, `INTERLOCK_V6_BETA_READINESS_CHECKLIST.md`, `tests/unit/test_recovery_fault_injection.py`. Git-ignored evidence under `logs/v6_recovery_hardening_session2/` and a new `logs/v6_pilot_demo_v1/evidence_20261017T203353Z.json`. No staged/committed/pushed/tagged content; no migration, threshold, dependency, config, or public-contract changes.

### U. Repository preservation verification (end of session)

HEAD `145a3d9` (master); staged 0; stash 1; porcelain **203 = 67 modified + 60 `web/` deletions + 76 untracked** — exactly the 200-entry baseline plus the 3 disclosed new files; remotes untouched; `alembic/versions/` untouched; frozen Suite A/B **still not executed** (manifests verified at session start: `dc74ebd…` / `da45c22…`).

### V. Remaining risks and required approvals (prioritized)

1. R10 migration repair + M-PKG/D3 (C-class) — proposal ready, approval pending; 4 visible xfails stand as honest evidence.
2. Privileged/POSIX host run of the two symlink drills (D-RH-7 release gate).
3. R17 POSIX backup/restore permission hardening (needs POSIX test env).
4. External: CI×2, Docker/PG/Redis, idle-window latency rerun, frozen Suite A/B execution, production access, external audit.
5. M1/M2: real process-kill / real disk-full drills still mocked-only (isolated authorized env needed).

### W. Next highest-priority action

On approval: implement R10 (repair migration `70d7de12a94b`, drop + rebuild indexes, FK enforcement) — then run the full migration matrix including the now-present partial-traversal xfail until it flips to green, and execute the privileged-host symlink drills as part of the same authorized window.


---

## Session 3 - 2026-10-18 (External validation & first beta users mission)

### X. Mission scope and baseline verification (read-only phase)

Mission: verify the reported baseline before relying on it, audit the beta-readiness checklist for independent reproducibility, build a reproducible first-run experience, verify recovery boundaries, prepare a controlled beta plan for 3-5 volunteers, and declare an honest acceptance verdict. Baseline reconciliation at session start matched the prior report exactly: HEAD `145a3d9` (master), staged 0, stash 1, porcelain **203 = 67 modified + 60 `web/` deletions + 76 untracked**, remotes unchanged, `core.autocrlf=true`. Frozen Suite A/B manifests re-verified byte-for-byte (`dc74ebd...` / `da45c22...`, MANIFESTS_OK=True) and were NOT executed. Run #3 evidence re-read from `logs/v6_recovery_hardening_session2/`: exit 0, 2922 passed / 9 skipped / 4 xfailed, coverage 83.81%, 3719.82 s. Independent reproduction of the regression claims (existing venv, 5-file subset of fault-injection + backup/restore drill + filesystem adapter + alembic safety + scenario proofs): **60 passed, 2 skipped, 4 xfailed, exit 0** - the 2 skips are the symlink-privilege drills, the 4 xfails are the documented migration defects.

### Y. Clean supported installation reproduced (new evidence)

A fresh virtual environment (Python 3.11.9) was created in temp and installed with the documented method `pip install -e ".[dev,security]"`: **exit 0**, `pip check` = "No broken requirements found", 110 packages, `import app.main, sdk.intentlock` ok (exit 0). The pilot demo and the hands-on recipe were then executed FROM that fresh venv: demo 4/4 verdicts true (exit 0, new versioned evidence `logs/v6_pilot_demo_v1/evidence_20261018T051433Z.json`); recipe exit 0 with byte-exact recovery (`state=succeeded`), independent SHA-256 `13372663edff22096ce10b1bef3c60b50f32dfd7ddb8f36d24964e7362511ecb`, workspace residue `['config.yaml']` only, duplicate delivery refused as `blocked_by_conflict`. Durable evidence in git-ignored `logs/v6_beta_install_check/` (venv creation, install log + exit code, pip check, import smoke). This satisfies the "clean supported installation reproduced" acceptance criterion for the first time with first-hand evidence. The temp venv was left in place (no destructive cleanup); it is outside the repository and will be removed with the temp workspace.

### Z. First-run workflow and hands-on recovery recipe

`docs/operations/BETA_FIRST_RUN.md` created: the full 8-step beta workflow (prerequisites, supported install, safe demo, documented failure, recovery, independent verification, change-scope explanation, safe reporting). Every command in it was executed on the reference host before being documented, with real observed output quoted. The hands-on recipe (adapter contract: pre-action capture -> agent fault -> post-action evidence with before-snapshot -> compensation -> execute -> tester-side SHA-256 verification -> residue check -> idempotent-replay refusal) was validated as a scratch script first and embedded only after it ran green twice (existing venv and fresh clean-install venv, identical hash output). Scope boundary stated in the doc: filesystem-family recovery on disposable projects only; migrations, SSO/KMS, web, PostgreSQL paths, and performance claims explicitly out of scope.

### AA. Readiness audit and controlled beta plan

`INTERLOCK_V6_BETA_READINESS_AUDIT.md` created: every checklist item re-derived from evidence (status, evidence, independently reproducible?, exact gap, blocks the controlled beta?, smallest next action, approval/dependency). Key finding: the production/CI/audit items are NOT required for a narrow disposable-project trial but remain required for GA; migration REDs are out of the declared beta scope by explicit exclusion with visible xfails standing. `INTERLOCK_V6_CONTROLLED_BETA_PLAN.md` created: tester slots T1 Windows / T2 macOS / T3 Linux (+ optional T4/T3.13, T5/3.12), verbatim consent and data boundaries, exact procedure including an opt-in real process-kill test on disposable data, expected outcomes, tester-performed verification (Get-FileHash/sha256sum outside Interlock), a minimal reporting template that excludes source/secrets/dumps, and immediate-pause criteria (write outside the disposable dir, any network attempt, secrets in output, two-volunteer crash). No one contacted, nothing published, no artifact distributed.

### AB. Small usability fixes (documentation only)

1) README stale numbers refreshed to the verified run #3: 2922 passed / 9 skipped / 4 xfailed / 0 failed (3719.82 s), coverage 83.81%, date 2026-10-18; "About the 7 skipped tests" rewritten as 9 with the two new symlink-escape drills called out and the 4 xfails explained. The alembic-head row was deliberately NOT touched (migration claims are approval-gated). 2) QUICKSTART duplicate "Option A / Option B" (identical commands) collapsed into a single supported-install section with a link to BETA_FIRST_RUN. 3) One discoverability bullet added each to README's Documentation list and docs/INDEX.md Operations section. No code, test, threshold, dependency, config, or public-contract change in this session.

### AC. Repository preservation verification (end of session)

HEAD `145a3d9` (master); staged 0; stash 1; porcelain **206 = 67 modified + 60 `web/` deletions + 79 untracked** - exactly the 203-entry state after session 2 plus the 3 disclosed new files (`INTERLOCK_V6_BETA_READINESS_AUDIT.md`, `INTERLOCK_V6_CONTROLLED_BETA_PLAN.md`, `docs/operations/BETA_FIRST_RUN.md`); all three links resolve. `alembic/` shows only the 4 pre-existing untracked migration files (unchanged); no migration applied or edited; frozen Suite A/B still not executed; no staging, commit, push, tag, remote, or secret change. Git-ignored evidence added under `logs/v6_beta_install_check/` and one new versioned pilot-demo evidence file.

### AD. Acceptance verdict and next action

**READY - for the declared, narrowly scoped controlled beta** (filesystem-family recovery, disposable projects, T1 + at least one POSIX slot), with disclosures in BETA_FIRST_RUN section 9 and pause criteria in the beta plan. **NOT READY** for production, any database/migration use, SSO/KMS, multi-user POSIX scenarios, or performance-sensitive deployment. Three biggest remaining risks: (1) no POSIX-first-hand execution yet - the 2 symlink drills skip on this host, so escape-proofing rests on code review plus mocked drills until a macOS/Linux volunteer reports; (2) D-MIG-1b/D3 remain unresolved and approval-gated - any beta tester touching migrations on a real DB would hit the brick-the-DB path, mitigated only by scope exclusion; (3) real process-kill/disk-full behavior is mocked-only (M1/M2), so real-world interruption resilience is unproven. Smallest next action with the most evidence: invite T1 + one POSIX slot and run `docs/operations/BETA_FIRST_RUN.md` verbatim - that single action converts the three biggest evidence gaps (second-machine clean install, POSIX symlink-drill execution, real-interruption opt-in) into first-hand reports without risking anything irreplaceable.


---

## Session 4 - 2026-10-18 (Final completion mission: controlled beta validation, release decision & handoff)

### AE. Baseline reconciliation (read-only first)

All reported session-3 results verified against the repository before any action: HEAD `145a3d9` (master), staged 0, stash 1, porcelain **206 = 67 M + 60 D + 79 ??**, remotes/config unchanged, 60 `web/` deletions intact, `alembic/` = 4 pre-existing untracked migrations only, frozen manifests byte-verified (`MANIFESTS_OK=True`), run #3 evidence intact, pilot evidence intact, install-check evidence intact, `ruff check app sdk` clean. One discrepancy disclosed and handled: the session-3 fresh venv artifact in temp had been **externally wiped** (recurring temp cleanup); its durable evidence in `logs/v6_beta_install_check/` was intact, so the clean-install claim stood on evidence - and the install was re-reproduced this session (AG) to restore a current-session datapoint. Symlink privilege probe: creation fails with "Administrator privilege required" on this non-elevated Windows 10.0.26300 host - the 2 privileged drills remain un-runnable here (BLOCKED, disclosed).

### AF. First-run workflow revalidation (documented procedure, unmodified)

`docs/operations/BETA_FIRST_RUN.md` executed as written, session 4: pilot demo 4/4 verdicts true, exit 0 (evidence `evidence_20261018T080635Z.json`); hands-on recipe exit 0 - `state=succeeded`, independent SHA-256 `13372663edff22096ce10b1bef3c60b50f32dfd7ddb8f36d24964e7362511ecb` (identical across 3 sessions / 2 venvs), workspace residue none, duplicate delivery `blocked_by_conflict`; prerequisites clean (Python 3.11.9, `pip check` no broken requirements). Mission step 4.9 verified: the newest demo evidence JSON was content-scanned - `CONTENT_LEAK=NONE`, keys are hashes/paths/metadata only. Mission step 4.3 recorded honestly: no console CLI exists (no `[project.scripts]`); interfaces are the Python API/SDK, `scripts/`, uvicorn. Regression subset re-run: **60 passed, 2 skipped, 4 xfailed, exit 0** (183.73 s) with all 4 migration xfails fully visible.

### AG. Clean install re-reproduced (session 4)

Fresh venv (Python 3.11.9) + documented `pip install -e ".[dev,security]"`: exit 0, pip check clean, imports ok (exit 0). Evidence: `logs/v6_beta_install_check/*_s4.*`. Justified re-run (not wasteful repetition): the session-3 venv artifact was externally deleted and the mission requires current-session install verification.

### AH. M1 REAL process-kill drill executed (user-authorized this session)

First real interruption evidence in the project's history. Attempt 1 failed due to a **drill setup bug** (child started with the file already faulted, so the pre-action capture correctly recorded faulted bytes - the adapter behaved correctly); failure log preserved as `m1_kill_drill_attempt1_failed.log`. Attempt 2 (`logs/v6_final_mission_session4/m1_real_kill_drill.py`): realistic sequence (original on disk -> pre-action capture records ORIGINAL -> agent fault -> post-action evidence -> execute), 20 hard `TerminateProcess` kills = 10 deterministic pre-swap-hook kills + 10 organic spray kills (1-60 ms), Windows 10.0.26300 non-elevated, Python 3.11.9, all I/O in disposable temp dirs. Result: **20/20 kills landed mid-recovery, 0 torn writes, 0 invariant violations, 20/20 retries succeeded**; pre-swap kills left exactly the documented single `*.recovery_tmp` staging residue with the target untouched; spray kills landed post-swap pre-exit. Evidence: `m1_kill_evidence.json` + `m1_kill_drill.log`. M1 upgraded from mocked-only to real-verified-on-Windows in the checklist, audit, and register (POSIX kill still untested; M2 disk-full still mocked-only - real procedure prepared, needs an isolated mount, never executed on the system drive).

### AI. Final status documents

`INTERLOCK_V6_BETA_INVITATION_PACKAGE.md` created (drafts only - no one contacted, nothing sent): invitation letter, frozen scope table, prerequisites/install, procedure pointer, files-and-permissions statement, known limitations, verbatim consent/privacy boundaries, structured bug-report template, explicit stop conditions; Windows slot T1 + POSIX slot T2/T3. `INTERLOCK_V6_FINAL_HANDOFF.md` created: single authoritative status doc linking README/first-run/audit/checklist/register/beta-plan/invitation/log, containing declared scope, verified install + demo/recovery procedures, exact evidence table with environments, known defects, "external validation: NONE" disclosure, outstanding approvals (incl. M2 procedure and R17 minimal implementation proposal with POSIX-only test sketches, both approval-gated), preservation verification, and the 9-category release decision.

### AJ. Release gate (evidence-derived, nothing forced)

1 Code/regression **PASS**; 2 filesystem recovery correctness in scope **PASS**; 3 installation/first-run reproducibility **PASS** (Windows/3.11.9); 4 Windows external validation **BLOCKED** (no volunteer); 5 POSIX external validation **BLOCKED** (no host/volunteer; privilege probe); 6 security/data-integrity **PARTIAL** (no external audit; R17 open; U5 accepted; M1 real-kill verified); 7 operational/infra **BLOCKED** (CI, Docker/PG/Redis, runbook, idle latency); 8 controlled-beta readiness **PASS** (scoped); 9 GA readiness **BLOCKED**. **Controlled beta RECOMMENDED** for the declared disposable-project scope with the invitation package's warnings/stop conditions; **GA BLOCKED**. No code, test, threshold, dependency, config, migration, or public-contract change this session; no staging/commit/push/tag/publish/deploy; no one contacted.

### AK. Preservation verification (end of session)

HEAD `145a3d9`; staged 0; stash 1; porcelain **208 = 67 M + 60 D + 81 ??** = the session-3 state (206) + the 2 disclosed new docs (`INTERLOCK_V6_BETA_INVITATION_PACKAGE.md`, `INTERLOCK_V6_FINAL_HANDOFF.md`); session-3 docs intact; `alembic/` untouched; frozen manifests intact; evidence versioned, never overwritten (failed drill attempt preserved). Minimum remaining steps toward broader launch are listed in the handoff section 10: invite T1 + POSIX slot; privileged-host symlink drills; isolated-volume M2; approve R10/R17; external infra + audit + Suite A/B execution.


---

## Session 5 - 2026-10-18 (First real self-recovery test + market readiness mission)

### AL. First real self-recovery test - PASS

Mission: recover a deliberately damaged disposable project with the EXISTING engine, independently verify, report honestly. Disposal project: `C:\Users\Dell\AppData\Local\Temp\opencode\v6_selftest_20261018T085000Z\project\` (4 synthetic files, outside the repository); immutable baseline manifest written first (`logs/v6_selftest_recovery_20261018T085000Z/baseline_manifest.json`). Canonical supported flow (same as `test_execute_restore_deleted_file`): pre-action capture (payload `operation=restore_deleted_file`, hash matches baseline) -> single controlled failure (`os.unlink` of `data/sample.txt`, no manual restore) -> `generate_compensation` -> `execute_compensation`: **success=True, state=succeeded, hash matches baseline, zero staging residue**. Independent verification by a SEPARATE stdlib-only process (`verify_independent.py`, zero engine imports): **4/4 files MATCH byte-for-byte**, no unexpected files, no residue -> PASS. Retry with same idempotency key: `blocked_by_conflict`, target unchanged (documented safe refusal). Confinement confirmed (test root contains only `project/`); repository preservation identical before/after (208 = 67 M + 60 D + 81 ??, HEAD `145a3d9`, stash 1, staged 0). Evidence + `report.md` in the unique dir; a first failed verifier draft (placeholder line) was fixed BEFORE execution - no failure was hidden, and the driver's attempt-1 record shows nothing was overwritten. Limitations stated: one scenario/one OS/one run; evidence-driven detection (not monitoring); no hazardous drills per mission order.

### AM. Market readiness - preservation, scope, consistency audit

Preservation re-verified at each phase. Product scope re-confirmed from live evidence (handoff section 1): filesystem recovery for disposable development projects only; production, migrations, universal-rollback claims excluded. Doc consistency audit: QUICKSTART single-install section coherent; README Limitations consistent with beta scope; README bandit claim VERIFIED ACCURATE (`bandit -ll -r app` reports "No issues identified"; the 7 findings are LOW severity/high confidence, exactly as documented); no `[project.scripts]` (no CLI) consistent across docs; test numbers match run #3. New security-review evidence: `pip audit` reports ONE advisory - `virtualenv 21.7.4 PYSEC-2026-4014` (fixed upstream 21.7.12) - **dev-toolchain only** (via pre-commit; absent from runtime `requirements.txt`); dependency change NOT authorized this mission, recommendation recorded. `intentlock` PyPI skip is expected (not published).

### AN. Product package additions (documentation only, no code changes)

New: `docs/operations/SAFETY_AND_LIMITATIONS.md` (verified capabilities vs explicit non-capabilities, each with evidence links); `docs/operations/TROUBLESHOOTING.md` (install/demo/test-suite/recovery-behavior failures with real diagnostics); `INTERLOCK_V6_CUSTOMER_DISCOVERY_PLAN.md` (prepared NOT executed: problem hypothesis, target personas, synthetic demo pointer, 5 neutral interview questions, gated paid-pilot proposal, evidence-based charge/change/stop rules, no invented numbers). Edits: README + docs/INDEX link the two new guides; beta plan gains section 10 (S1/S2/S3 severity triage, data-integrity always outranks). No code, test, threshold, dependency, config, migration, or contract change; no contact/publication.

### AO. Release gates A-I (market readiness framework)

A Installation/first-run reproducibility **PASS** (two clean installs + demo + recipe + self-test, Windows/3.11.9). B Recovery correctness + independent verification **PASS** (100k campaign + 19 drills + self-test independent PASS). C Data safety & failure handling **PARTIAL** (fail-closed drills + real-kill 20/20 + conflict/retry safety evidenced; real disk-full evidence missing - M2 mocked-only). D Security & privacy **PARTIAL** (traversal/sentinel/no-telemetry/no-shell verified; dev-toolchain advisory open; no external audit; POSIX perms R17 open; symlink execution pending privileged host). E Documentation & usability **PASS** (consistent docs, verified commands, new guides). F Windows validation **PASS** (all internal evidence on Windows). G POSIX validation **BLOCKED** (no host/volunteer). H Operational readiness **BLOCKED** (CI, Docker/PG/Redis, runbook, idle latency). I Customer demand **BLOCKED** (zero interviews; discovery plan prepared only). Controlled beta: still justified within the declared disposable-project scope; GA: still BLOCKED; market-ready: NOT claimed.

### AP. Preservation (end of session 5)

HEAD `145a3d9`; staged 0; stash 1; `web/` deletions 60; migrations untouched; frozen manifests intact; all prior evidence preserved (new evidence in unique dirs only). New untracked this session: `INTERLOCK_V6_CUSTOMER_DISCOVERY_PLAN.md`, `docs/operations/SAFETY_AND_LIMITATIONS.md`, `docs/operations/TROUBLESHOOTING.md` (self-test + kill-drill evidence lives under git-ignored `logs/`). Final porcelain verified after this append.


---

## Session 6 - 2026-10-18 (Release-gate closure mission: C, D, G, H, I)

### AR. Baseline and environment determination

Baseline verified exactly as reported: HEAD `145a3d9`, staged 0, stash 1, porcelain **211 = 67 M + 60 D + 84 ??**, 60 `web/` deletions. Environment probes decided the mission: volumes = C: (system) + F: (holds repository and user data); **no safe isolated volume**; **WSL not installed** (no POSIX); docker/psql/redis absent; shell non-elevated. These are the exact blockers now recorded per gate.

### AS. Gate C - M2 blocked with exact blocker; M3 real permission drill PASS

M2 (real disk-full) cannot be run safely here: a sized volume (VHD/loop) requires administrator rights; filling C: is forbidden (system drive); filling F: is forbidden (repository + user data live there); Windows offers no per-directory quota without elevation. PARTIAL retained; procedure unchanged; blocker sharpened in handoff section 7. Adjacent real-OS failure case executed instead (authorized scope): **M3 read-only-target permission drill** - real `PermissionError` at the atomic swap produced a typed fail-closed result (`success=False, state=failed`, no exception leak), target hash unchanged after failure (never torn), zero staging residue, and after clearing the read-only flag the SAME idempotency key retried to `succeeded` with the original bytes restored. Verdict PASS; evidence `logs/v6_gate_closure_20261018T092000Z/m3_permission_evidence.json`. Regression subset (fault-injection + backup/restore drill + filesystem adapter): **45 passed, 2 skipped (symlink privilege), exit 0**.

### AT. Gate D - full advisory audit (cross-checked vs OSV)

`pip audit -f json` (saved to evidence dir) + OSV lookup of PYSEC-2026-4014 + reverse-dependency tracing via `pip show`. Runtime core (fastapi, sqlalchemy, uvicorn, pyjwt, cryptography, redis, psycopg2, alembic, ...) has ZERO advisories. All 7 findings: `virtualenv 21.7.4` x4 (PYSEC-2026-4011/4012/4013/4014; fixes 21.7.11-21.7.13; via pre-commit, dev-only); `mcp 1.29.0` x1 (CVE-2026-59951, fix 1.30.0; via semgrep, dev-only; the vulnerable MCP HTTP-server surface is unused); `nltk 3.10.3` x1 (via safety, dev-only, no upstream fix); `python-jose 3.5.0` + `ecdsa 0.19.2` x2 (no upstream fixes; pinned in runtime requirements.txt but ORPHANED - no reverse-dependency, zero imports in app/sdk/scripts; legacy of the disclosed SSO placeholder; python3-saml requires only isodate/lxml/xmlsec). Remediation proposals prepared (approval-gated dependency changes, nothing changed): virtualenv>=21.7.13 + re-compile; mcp>=1.30.0; orphan cleanup of python-jose (+ evaluate dropping python3-saml from requirements.in). R17 unchanged: smallest fix identified (0o600 artifacts/0o700 dirs on POSIX, restore never more permissive than recorded mode, POSIX-only tests); requires explicit authorization + POSIX env (unavailable - no WSL). Gate D stays PARTIAL (external audit still required; R17 open; advisories exist albeit dev/orphan).

### AU. Gate G - POSIX remains BLOCKED, checklist prepared

WSL is not installed; no Linux/macOS exists on this host; installing WSL is a system change (admin + restart) and was NOT attempted. Windows results and code review are not POSIX evidence. Reproducible POSIX volunteer checklist added as invitation-package section J (uname/python record, first-run steps, symlink-drill execution expectation, optional M1 real-kill harness, permission observations for R17, stop conditions). Gate G stays BLOCKED.

### AV. Gate H - requirement classification (no new infrastructure)

For the declared filesystem-only beta, NONE of CI/Docker/PostgreSQL/Redis/idle-latency is required: the self-test, drills, demo, and recipe all run fully offline on one machine (evidence: sessions 3-6). All of them (plus runbook, external audit, Suite A/B execution, R10) are GA requirements. Missing access recorded: GitHub push authorization x2, Docker/PostgreSQL/Redis services, idle window, elevated session for M2. No infrastructure was installed solely to complete a checklist. Gate H stays BLOCKED (for GA) with the beta explicitly unaffected.

### AW. Gate I - execution checklist prepared (nothing executed)

Customer discovery plan gains section 8: T1/T2 slot execution steps (pointing to existing package sections A/G/H/J and first-run guide) and a 5-interviewee checklist with a neutral outreach message draft, verbatim questions, consent-bound note taking, and the counts-not-stories aggregation rule tied to the Section 6 decision rules. No messages sent, no contacts made, no data collected. Gate I stays BLOCKED.

### AX. Gate statuses (unchanged where evidence is unchanged; sharpened where it improved)

C PARTIAL (M3 real-permission PASS added; M2 exact blocker recorded); D PARTIAL (full audit + proposals; external audit + R17 open); G BLOCKED (checklist prepared); H BLOCKED (classified: beta unaffected, GA requirements itemized); I BLOCKED (checklist prepared). A/B/E/F remain PASS as previously evidenced. Controlled beta remains justified for the declared disposable-project scope; GA remains BLOCKED. No code, test, threshold, dependency, config, migration, or contract change this session; new evidence only in `logs/v6_gate_closure_20261018T092000Z/`.


---

## Session 7 - 2026-10-18 (Gate C & D closure mission)

### AY. Baseline, evidence review, and approval gates

Baseline verified identical (211 = 67 M + 60 D + 84 ??, HEAD `145a3d9`, staged 0, stash 1). Reviewed M1 (20/20, 0 torn, 0 violations) and M3 (PASS, intact, recovered) evidence. Two approval questions submitted to the owner: (1) one-time UAC elevation for the isolated 64 MB VHD to run the REAL disk-full drill; (2) the minimal dependency remediation. Answers: M2 = **unanswered (not authorized - not run)**; remediation = **approved (a)+(b)**.

### AZ. Gate C - M2 prepared with refusal guards; regressions green

Since elevation was not authorized, M2 was NOT improvised: the exact diskpart create/attach/format + cleanup + verification procedure and stop conditions were written (`logs/v6_gate_cd_20261018T100500Z/m2_procedure.md`), and a drill script (`m2_diskfull_drill.py`) was prepared that (a) REFUSES any target not on a disposable volume (hard-coded C:/F: exclusion), (b) fills the isolated volume to ~1 KB free, (c) captures the raw OS error (errno/ENOSPC flag, typed result or exception), (d) independently verifies target-integrity hash + staging-residue listing outside the engine, and (e) retries with the SAME idempotency key after freeing space. Gate C stays PARTIAL; the only missing item is owner approval of the UAC step. Regression subset: 45 passed, 2 skipped (symlink privilege), exit 0.

### BA. Gate D - full advisory re-classification with reachability tracing

Fresh full audit (machine-readable before/after/fresh-venv JSONs preserved) + OSV cross-check + reverse-dependency tracing + repo-wide import tracing + PyPI metadata verification. Corrections to earlier claims, recorded honestly: (1) python3-saml is NOT orphaned - `ProductionSAMLAdapter` lazily imports `python3_saml` via importlib (feature path, zero advisories of its own); (2) python-jose+ecdsa are a genuinely orphaned subtree in the runtime lock (no reverse-dependency, zero imports, real JWT path is pyjwt/EdDSA); (3) `mcp>=1.30.0` is **upstream-blocked** - semgrep pins `mcp==1.29.0` exactly (verified in installed 1.181.0 AND latest PyPI metadata), so the only path would be removing semgrep; (4) nltk/safety are undeclared manual-venv tools, not shipped (absent from the fresh venv); (5) the fresh venv additionally exposes the Python-3.11-seeded setuptools 65.5.0 (4 dev-time advisories; pyproject build-system requires >=75; working venv runs 84.0.0).

### BB. Approved remediation applied and validated

Owner approved (a)+(b). Applied: `requirements-dev.in` gained `virtualenv>=21.7.13,<22.0` (the session's ONLY tracked change); both lock files regenerated with the documented pip-compile process (dev lock needed `--upgrade-package semgrep` because the stale semgrep==1.173.0 pin conflicted with the direct pyjwt==2.15.0 runtime pin - a pre-existing lock inconsistency; 1.181.0 matches the installed state and pyjwt>=2.15); the entire python-jose orphan subtree (python-jose, ecdsa, pyasn1, rsa, six) pruned from both locks; working venv synced (orphans uninstalled; six reinstalled for two undeclared tooling chains - no advisories). Validation: pip check clean in working AND fresh venvs; audit 7 unique findings -> 2 (mcp upstream-blocked + nltk not-shipped), runtime-lock advisories 0; regression subset 45/2 exit 0; `ruff check app sdk` clean; engine+SDK imports OK in both venvs; `pre-commit run --all-files` executes all four hooks under virtualenv 21.14.11 (pre-commit compatibility proven) - the four hook failures are pre-existing and unrelated (ruff-format deliberately never run; repo-wide ruff-check findings in non-app/sdk fixtures; mypy optional opentelemetry stubs absent; bandit's 7 documented LOWs), and this session's only tracked change is non-Python which no hook processes. Recorded deviation: the dev lock's historical `--no-index` flag cannot resolve here; regeneration used the runtime file's documented command style (header now truthful).

### BC. Gate D verdict and R17

Gate D: **PASS at the declared controlled-beta scope / PARTIAL at GA**. Basis: actionable advisories remediated or proven non-actionable with recorded uncertainty; traversal/sentinel/confinement/no-teardown evidence intact + regression green; privacy documentation verified to match actual behavior (no network/telemetry code in recovery/backup paths); external audit documented as GA-mandatory-only per the project's own release criteria (no audit claimed; residual risks recorded). R17: full line-accurate diff + 4 POSIX-only tests + volunteer-executable validation procedure prepared (`r17_proposal.md`); NOT implemented (requires explicit authorization of the behavior change AND a POSIX environment; Windows tests must never stand in for POSIX evidence).

### BD. Gate statuses and preservation

C PARTIAL (M2 authorization-blocked, everything else proven; procedure+script one command away). D PASS (beta scope) / PARTIAL (GA). No code, test, threshold, migration, or contract change. Final preservation: porcelain 213 = 68 M + 60 D + 85 ?? (delta = requirements-dev.in + this evidence dir), HEAD `145a3d9`, staged 0, stash 1. New evidence only in `logs/v6_gate_cd_20261018T100500Z/` (audit JSONs before/after/fresh, classification matrix, M2 procedure + drill script, R17 proposal, regression + precommit logs, gate_results.json, final_report.md). Full report delivered to owner in-session.

### BE. Correction to BD (same-session, recorded rather than edited)

BD predicted porcelain 213 = 68 M + 60 D + 85 ?? on the assumption that the new evidence directory would appear as an untracked entry. Measured final state is **212 = 68 M + 60 D + 84 ??**: `logs/` is git-ignored, so `logs/v6_gate_cd_20261018T100500Z/` does not appear in porcelain at all. The delta from the 211 baseline is therefore exactly ONE tracked file: `requirements-dev.in` (+1 pin, the owner-approved change). `gate_results.json` and `final_report.md` in the evidence directory carry the corrected numbers. All other preservation facts in BD are unchanged (HEAD `145a3d9`, staged 0, stash 1, web deletions 60).


---

## Session 8 - 2026-10-18 (Final Gate C & D readiness mission)

### BF. Baseline and D1 revalidation

Baseline verified exactly as referenced: 212 = 68 M + 60 D + 84 ??, HEAD `145a3d9`, staged 0, stash 1, web deletions 60. D1 re-verified against current files/environment: dev lock consistent with the approved pin (virtualenv>=21.7.13 -> 21.14.11); runtime lock clean of dev tooling and the pruned orphan subtree; `pip check` clean in the working venv AND a freshly rebuilt 157-package shipped venv (current-session audit JSONs preserved); working-venv findings exactly 2 (mcp CVE-2026-59951 - semgrep exact pin `mcp==1.29.0` re-verified in installed 1.181.0 METADATA; nltk PYSEC-2026-3740 - via safety, undeclared anywhere, absent from fresh venv); fresh venv adds only the Python-3.11-seeded setuptools advisories (bootstrap-only; pyproject build requires >=75; working venv 84.0.0). D4 re-verified: no network/telemetry calls in recovery+backup paths; BETA_FIRST_RUN offline/disposable claims match behavior.

### BG. M2: presented for the second time, unanswered again -> not run

Re-presented the full procedure per the mission's C2 checklist (exact diskpart command; volume identification; refusal guards; expected behavior; cleanup + post-cleanup verification; risks) plus two hardening gaps found in review (a: no POSITIVE volume identification - proposed label INTERLOCK_M2 + total-size <=100MB check via GetVolumeInformationW/GetDiskFreeSpaceExW; b: drill-body exceptions could bypass evidence writing - proposed always-write wrapper). Authorization answered with NO DECISION again: neither the drill NOR the hardening diff was applied; Gate C remains PARTIAL with C-A3 (real ENOSPC) as the single missing criterion. Nothing was elevated; no system change occurred.

### BH. R17: approved and implemented (6 hunks + 5 tests)

Owner approved implementation. Applied minimal diff: filesystem_recovery_adapter.py - both staging `os.open(...)` calls now pass mode 0o600 (staging holds the user's pre-fault bytes); both post-swap chmod sites apply ONLY a recorded mode (removed the forced 0o644 default that could LIFT a private file to world-readable; with no recorded mode the staging file's owner-only mode survives). backup_restore.py - export_backup creates its directory with mode=0o700 and, POSIX-guarded, chmods snapshot/dump/manifest to 0o600 best-effort (contextlib.suppress(OSError): a chmod failure never invalidates an already hash-verified backup); +import contextlib. Honest contract correction recorded: chmod-failure behavior is SUPPRESSED BEST-EFFORT (not typed-FAILED as the authorization question loosely said) - a dedicated test now pins that documented contract (restore succeeds, content exact, no crash). Tests added: TestR17PosixPermissions (staging-mode spy 0o600; recorded-mode 0o640 applied; no-recorded-mode keeps 0o600 never 0o644; chmod-failure best-effort) + export_backup owner-only POSIX test; the 4 permission-assertion tests skip on Windows with explicit "POSIX mode semantics" reasons (never reported as passing).

### BI. Validation and an evidence-incident disclosure

Targeted: 29 passed, 4 skipped, exit 0. Regression subset (fault-injection + backup/restore + adapter): **46 passed, 6 skipped, exit 0**. ruff check clean on all 4 changed files; bandit -ll clean on changed app files; imports OK. INCIDENT: re-running the M3 drill to prove behavior-unchanged OVERWROTE the session-6 file logs/v6_gate_closure_20261018T092000Z/m3_permission_evidence.json - a violation of the never-overwrite rule. Repair executed immediately: the rerun (run_at 13:30:38Z, PASS) preserved as m3_rerun_after_r17.json in the new evidence dir, and the original file RESTORED VERBATIM from its recorded session-6 output (run_at 09:25:14Z; same verdict, same hashes). No claim depends on the difference; disclosed here and in gate_results.json.

### BJ. Gate decisions and preservation

Gate C: PARTIAL -> PARTIAL (C-A3 real M2 authorization-blocked; everything else proven: M1/M3 real-OS, independent checks, regressions green, no critical in-scope issue). Gate D: PASS (controlled-beta scope) retained and strengthened (R17 implemented; posture re-verified fresh); GA remains PARTIAL (POSIX validation of R17, external audit, plus Gate C's M2 and GA infra). Final preservation: porcelain 213 = 69 M + 60 D + 84 ?? (delta = exactly one newly-modified tracked file, test_filesystem_recovery_adapter.py, from the approved tests; the other three R17 files were already M/?? at baseline; requirements-dev.in remains the session-7 modification), HEAD `145a3d9`, staged 0, stash 1, web deletions 60. No elevation, no installs, no git operations, no contacts, no migrations/frozen-manifest changes. New evidence only in logs/v6_gate_cd_final_20261018T112500Z/.


---

## Session 9 - 2026-10-18 (Final cross-platform + commercial readiness + scoped commit)

### BK. Verification, defect-hunt, and one retraction

Baseline 213 = 69 M + 60 D + 84 ?? verified; all cited evidence files located and read (M3 original 09:25:14Z vs rerun 13:30:38Z both PASS, restoration claim verified). Defect hunt: a suspected dead-timestamp-branch defect at the delete-restore path was RETRACTED after inspection - `_stat_metadata` captures both float and ns keys, both restore paths live; no change made. TOCTOU micro-window between exists-check and os.replace documented as a known single-writer limitation (not "fixed" - would need platform-specific APIs; avoided overengineering). CI files (ci.yml/security.yml/docker-verify.yml) exist but never ran (no push since 2026-09-27) and covered ubuntu/3.11 only.

### BL. Cross-platform matrix + CI job

Added an additive service-free `recovery-cross-platform` job to .github/workflows/ci.yml: 3 OS (ubuntu/windows/macos) x 4 Pythons (3.11-3.14), pip install -e ".[test]", pip check, ruff, recovery subset. On POSIX runners the 2 symlink drills and 4 R17 permission tests EXECUTE (unprivileged symlink/chmod), converting locally-BLOCKED evidence to real POSIX evidence on first push. macOS arm64 xmlsec wheel availability recorded as the honest install risk cell. YAML validated (both jobs parse). ci.yml is a MIXED file (pre-existing modifications + new job) -> withheld from the commit. Wrote docs/operations/SUPPORTED_PLATFORMS.md: TESTED PRIMARY = Windows x64/NTFS/3.11.9; DECLARED CI-PENDING = Linux x64 + macOS arm64, 3.11-3.14; UNSUPPORTED = FAT32/exFAT/network dirs; UNTESTED = Windows ARM64, long paths.

### BM. Distributable + security verification

python -m build produced intentlock-4.0.0-py3-none-any.whl (579.6 KB) + sdist into a TEMP outdir (repo untouched); SHA-256 hashes recorded in artifact_hashes.txt. Clean-venv wheel install: imports resolve from SITE-PACKAGES (verified from a neutral cwd, defeating source-tree shadowing); functional recovery smoke PASS (byte-exact restore, zero residue); pip check clean. Fresh audit: same 2 documented findings (mcp upstream-blocked; nltk not shipped); bandit -r app -ll 0 issues; ruff clean; evidence secret-scan matches were scanner self-references only.

### BN. Scoped local commit (first commit of the V6 era)

Per mission section 11: staged EXACTLY requirements-dev.in (verified 1-line diff), docs/operations/SUPPORTED_PLATFORMS.md (new), INTERLOCK_V6_RELEASE_READINESS_REPORT.md (new); inspected git diff --cached (230 insertions, 0 deletions, nothing else); committed -> **624171eeebdf5931351234594653352a12fea7f3**. WITHHELD, with reasons: filesystem_recovery_adapter.py (pre-existing D-RH campaign work + R17 hunks - inseparable), backup_restore.py + test_backup_restore_drill.py (pre-existing untracked work + R17 additions), test_filesystem_recovery_adapter.py (kept with its engine for coherence), ci.yml (mixed). Post-commit: HEAD 624171e, staged 0, stash 1, porcelain 212 = 68 M + 60 D + 84 ??, web deletions 60 - all pre-existing work intact. Non-fatal anomaly disclosed: git auto-cleanup hit `failed to delete .git/worktrees/silver-willow: Permission denied` (stale admin dir from a previously-removed worktree); commit succeeded, fsck clean, history intact; nothing was deleted. A stale prunable worktree registration `Temp/ilock_baseline` (temp-wiped) also remains - untouched. Report amended post-commit with the hash (working copy differs from committed copy by that line only; recorded).

### BO. Commercial verdicts

Controlled beta: READY WITH CONDITIONS (BETA_FIRST_RUN verbatim, disposable projects only, M2 disclosed). Paid beta: NOT READY - zero demand evidence; recommend consent-based free pilot with 5 measurable progression criteria; trusted-adult guidance recorded (founder is 16). GA: NOT READY - M2, native POSIX, CI execution, external audit, R10, full-suite re-run for R17 delta, runbook. Next three actions: (1) authorize push -> 12-cell CI matrix + security workflows execute; (2) authorize M2 elevation -> closes Gate C; (3) send invitation package -> independent-installation evidence + 5 discovery interviews. Gate C PARTIAL (C-A3 only), Gate D PASS beta / PARTIAL GA. No push, tag, publish, deploy, elevation, install, or contact occurred this mission.


---

## Session 10 - 2026-10-19 (macOS availability mission)

### BP. Audit + the one real macOS-breaking defect

Baseline re-verified: HEAD 624171e, staged 0, stash 1, porcelain 213 = 69 M + 60 D + 84 ??, web deletions 60 (web/ dir absent from disk - pre-existing deletions PRESERVED, never restored). Website (Next.js) exists only in git HEAD. Static audit of app/ + sdk/: ZERO Windows-only API assumptions. NEW environment discovery: .venv314 (Python 3.14.7) exists - first 3.14 evidence. DEFECT FOUND + FIXED: ToolArgumentValidator.validate_path used os.path.isabs (platform-dependent) -> accepted C:\... on any POSIX host (test_tool_security.py:71 fails on macOS by construction) and, on Python 3.14, ntpath.isabs("/x") flipped False so rooted paths lost rejection everywhere. Fix: reject ntpath.isabs OR posixpath.isabs (strictly stronger on every OS; verdict now platform-independent). TDD: new cross-platform test RED pre-fix on py3.14 (1 failed, 58 passed, exit 1), GREEN post-fix on 3.11.9 AND 3.14.7 (59/59). Both edited files were clean at HEAD (diffs are exactly my changes: 11+/1- and 23+).

### BQ. Real dependency evidence for macOS without a Mac

pip download --only-binary --platform probes: ALL 58 locked pins publish macosx_11_0_arm64 wheels (incl. xmlsec 1.3.17 - the top risk, cryptography 50 abi3, psycopg2-binary, lxml, pydantic-core); cp314 arm64 wheels exist for all per-ABI pins. PyPI JSON: cryptography 50.0.0 has ZERO macOS x86_64 wheels -> macOS Intel is DEPENDENCY-BLOCKED (cryptography <=45 has x86_64 wheels: owner-approved pin change would unlock later). Evidence: logs/v6_macos_20261019T/mac_wheel_audit.txt.

### BR. Regression + distributable

Recovery+security subset (adapter, fault-injection, backup drill, tool security): 105 passed, 6 skipped (4 R17 POSIX + 2 privileged symlink - never counted as passing), exit 0 on BOTH py3.11.9 (62.44s) and py3.14.7 (61.16s). ruff app sdk clean, bandit -ll 0, mypy app clean (311 files). python -m build -> intentlock-4.0.0-py3-none-any.whl (579.8 KB) SHA-256 1e76d1f4acc38a3058f6b4dbb15821c0e809f450b29aa55e1ba5680968ff7f2e (sdist d1f758ab...e6d61a) from working tree at 624171e + uncommitted campaign changes; clean-venv install -> pip check clean -> neutral-cwd SITE-PACKAGES import -> security assertions PASS (3 absolutes rejected, relative accepted) -> functional recovery smoke PASS (byte-exact, zero residue), exit 0.

### BS. Deliverables (all local; nothing committed/pushed/published - not authorized this mission)

docs/operations/MACOS_INSTALL.md (arm64 install procedure: wheel + full-parity lock paths, checksum verification, uninstall, honest "NOT yet natively validated" banner, unsigned/unnotarized disclosure). docs/operations/SUPPORTED_PLATFORMS.md updated (macOS arm64 = dependency-resolved CI-pending; macOS Intel = UNSUPPORTED dependency-blocked; Python row now 3.11.9+3.14.7). ci.yml + separate macos-release-artifact job (macos-latest: build wheel, shasum, upload-artifact evidence, install+pip check from neutral cwd, macOS-native recovery+security subset) - YAML valid, 3 jobs; ci.yml remains a MIXED pre-existing-modified file (withheld). downloads/index.html + README.md: standalone platform-download section - Windows "verified, not hosted" + SHA-256, macOS "Validation in progress" (no button, no fake waitlist, no fake URL), macOS Intel unsupported, Linux declared/not validated - created as new files because restoring web/ would destroy the 60 preserved deletions. INTERLOCK_V6_MACOS_READINESS_REPORT.md (full 8-item mission report + release-gate table).

### BT. Gate status

macOS availability gate: native build BLOCKED (CI prepared, push unauthorized), clean install BLOCKED (procedure ready), native tests BLOCKED (tests prepared), destination BLOCKED (no hosting authorized), instructions prepared locally, signing honestly disclosed (unsigned, notarized: no - Gatekeeper irrelevant for pip packages). Next: (1) authorize push -> 3 CI jobs run incl. real macOS build + native tests; (2) authorize a publication destination -> enable the download button; (3) real-Mac run of MACOS_INSTALL.md; (4) optional approved cryptography<=45 pin to unlock Intel. No stage/commit/push/publish/tag/deploy/contact/elevation occurred.
