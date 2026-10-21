# INTERLOCK V6 — Beta-Readiness Checklist (honest, criteria-based)

Versioned 2026-10-18 (session 2). Companion to
`INTERLOCK_V6_CONTINUOUS_ENGINEERING_LOG.md` and
`INTERLOCK_V6_RECOVERY_HARDENING_REGISTER.md`. Status values:

- **GREEN** — criterion independently verified with reproducible evidence.
- **RED** — criterion failed or not demonstrated; exact blocker named.
- **BLOCKED** — cannot be executed from this environment; external dependency named.
- **KNOWN LIMITATION** — honest boundary, disclosed rather than hidden.

Nothing is marked GREEN without an artifact a reviewer can re-verify. Nothing
here changes a frozen threshold, public contract, or the protected history.

## 1. What Interlock V6 demonstrably is (scope honesty)

| Claim | Status | Evidence |
|---|---|---|
| Surgical compensation engine for code-level protected actions (filesystem/git/config/database adapters) | GREEN | 100,000-attempt campaign, 0 invariant violations; 853-file immutable campaign evidence |
| Byte-exact filesystem recovery incl. conflict protection of later human edits, traversal refusal, idempotent replay | GREEN | Pilot demo 4/4 (2026-10-18 fresh run, `logs/v6_pilot_demo_v1/evidence_20261017T203353Z.json`); frozen Suite A; unit tests |
| Sealed WP-1 v2 evidence chain with fail-closed local backup/restore utility | GREEN (hardened this session) | 19 fault-injection drills (`tests/unit/test_recovery_fault_injection.py`); drill suite; manifest SHA-256 |
| External compatibility (arbitrary third-party infra, Kubernetes, cloud failover) | **NOT CLAIMED** | Never tested outside the environments listed above |

## 2. Validation criteria

| Criterion | Status | Detail |
|---|---|---|
| Whole test suite green | GREEN | 2904 passed / 7 environment-conditional skips / 3 xfailed (run #2); run #3 re-verification in progress this session |
| Coverage gate ≥ 80 % | GREEN | 83.78 % (run #2); gate unchanged |
| Migration graph single head, fresh upgrade clean, index names consistent | GREEN | `TestAlembicGraph`, `TestAlembicFreshUpgrade`, new live guard `TestAlembicIndexConsistency` (30/30 tables, 0 mismatches) |
| Migration downgrade/re-upgrade roundtrip | RED (known, visible) | 3 xfails: D-MIG-1 (empty-DB roundtrip root cause), D-MIG-1b full downgrade brick, D-MIG-1b **partial-traversal** variant (successful `downgrade fc5e7844e4dd` exits 0 yet bricks re-upgrade) — repair = approval-gated R10; migration files untouched |
| Fault-injection drills fail closed and never destroy last-known-good state | GREEN | 17 runnable drills pass (2 symlink drills skip honestly — Windows privilege); every failure drill asserts live target byte-identical + no staging residue |
| Independent re-verification of defect reproductions | GREEN | D-MIG-1b reproduced twice this session on disposable DBs (`d_mig1_repro.py`, `d_mig1_partial_probe.py`) |

## 3. Recovery criteria

| Criterion | Status | Detail |
|---|---|---|
| Failed recovery attempts leave no residue and remain retryable | GREEN (defect D-RH-1 fixed) | staged-swap in `_execute_restore_deleted_file`; drill proves FAILED → no target → retry reaches operation |
| Snapshot/backup consistency verified before any destructive swap | GREEN (D-RH-2/6 fixed) | point-in-time export (dump derived from snapshot), manifest row-count cross-check, staged-digest pre-swap check |
| Manifest is an authenticated trust root | GREEN (D-RH-4 fixed) | exact artifact-set gate; traversal names refused; omitted entries refused |
| Malformed/hostile backup inputs fail closed with typed errors | GREEN (D-RH-3/8 fixed) | `BackupVerificationError` for corrupt JSON, non-object records, ENOSPC, permission failures, unreadable snapshots |
| Re-export cannot silently destroy the previous last-known-good backup | GREEN (D-RH-9 fixed) | export refuses a directory containing an existing manifest |
| Symlink escape via planted staging paths | GREEN in code (D-RH-7 fixed) | `O_EXCL` staging creation; live drills skip on this host (no symlink privilege) → **execution on a privileged host still required before release** |
| Real process-kill / real disk-full recovery drills | M1 GREEN-on-Windows / M3 GREEN-on-Windows / M2 RED | M1: real `TerminateProcess` drill 2026-10-18 — 20/20 hard kills mid-recovery, 0 torn writes, 0 invariant violations, 20/20 retries completed (Windows 10.0.26300, non-elevated, Python 3.11.9; evidence `logs/v6_final_mission_session4/m1_kill_evidence.json`); M3: real read-only-target permission failure — typed fail-closed result, target never torn, 0 residue, same-key retry succeeded (`logs/v6_gate_closure_20261018T092000Z/m3_permission_evidence.json`); M2: still mocked `ENOSPC` only — no isolated volume on this host; session 7: exact diskpart procedure + refusal-guarded drill script prepared (`logs/v6_gate_cd_20261018T100500Z/m2_procedure.md`), owner elevation requested and **unanswered → not authorized, not run** |
| POSIX restore-vs-running-app divergence (U1) | KNOWN LIMITATION | `os.replace` succeeds while the app holds the file open on POSIX; docs must require app-stopped on all platforms; untestable here (no POSIX host) |

## 4. Security & privacy criteria

| Criterion | Status | Detail |
|---|---|---|
| Path traversal in manifest artifact names | GREEN (fixed + drilled) | D-RH-4 |
| Symlink escape in staging | GREEN (fixed; privileged-host run pending) | D-RH-7 |
| Secrets never in error messages | GREEN | sentinel-leak drill asserts the secret never appears in verification errors |
| No telemetry / network egress from recovery paths | GREEN | verified by grep: no `requests`/`httpx`/`aiohttp`/`urllib.request` in recovery code |
| DNS lookups during host validation (SSRF defense) | KNOWN LIMITATION (disclosed) | `tool_security._validate_host` performs a real `getaddrinfo`; intended defense, local DNS resolution possible, no data leaves the host |
| Backup/temp file POSIX permissions (U2) | RED / proposal R17 | default-umask artifacts; restore swap can loosen a pre-existing `0600` target mode; needs POSIX test env — registered, not implemented blind |
| Shell interpolation / accidental command execution | GREEN | no `subprocess`/`shell=True`/`os.system` in `app/` |
| Minimum permissions Interlock requires | DOCUMENTED | local FS read/write inside explicitly protected workspaces; local SQLite files it owns; no admin, no network egress, no telemetry endpoints |

## 5. Production readiness (prior rating 6.5/10 — unchanged)

| Item | Status |
|---|---|
| CI×2 pushes + Docker/PostgreSQL/Redis infra | BLOCKED (external authorizations) |
| Idle-window latency rerun | BLOCKED (machine-busy window; exact commands in log §F) |
| Frozen Suite A (100k) / Suite B (31k) execution | BLOCKED (execution gate; manifests verified intact) |
| R10 migration repair + M-PKG/D3 drift | RED — proposal ready, approval pending |
| External zero-knowledge/production-readiness code audit | BLOCKED (external) |
| Operational runbook/rollback procedure | not produced (needs Docker/PG/Redis environment to exercise) |

## 6. Performance review (thresholds reviewed, NOT changed)

| Benchmark | Threshold | Measured | Status |
|---|---|---|---|
| AuthZ check latency | 1 ms mean, 1000 rps, ≤ 5 ms regression | 2.85 ms median, 7.97 ms p95 | RED vs 1 ms mean — known, documented, threshold left unchanged; idle-window rerun pending |
| Coordination lease p95 | ≤ 5.0 ms | 5.99 ms (p95), median 0.15 ms | RED vs p95 — documented; adaptive-load-test results (46.8 rps) are diagnostic, not threshold evidence |

Diagnostic-only improvements in this session: chunked artifact hashing
(D-RH-5) removes whole-file memory spikes; no threshold, gate, or public
contract was touched.

## 7. Verdict

Recovery correctness and fail-closed behavior for the **supported**
filesystem/local-backup paths are demonstrably stronger than at the prior
report, with reproducible evidence for every claim. Beta remains gated on the
external blockers in §5, the three honest migration xfails (R10 approval), the
privileged-host symlink drill, POSIX permission work (R17), and a green run #3
(this session's whole-suite re-verification).
