# INTERLOCK V6 — Beta-Readiness Audit (external validation mission, 2026-10-18)

Independent re-audit of `INTERLOCK_V6_BETA_READINESS_CHECKLIST.md` against
reproducible evidence, for the purpose of a **narrowly scoped controlled beta**
(3–5 volunteers, filesystem-family recovery, disposable projects). Statuses
were re-derived from evidence, not carried over; no status was raised to look
ready. Columns: claimed status → evidence → independently reproducible? →
exact gap → blocks the controlled beta? → smallest next action → dependency.

## 1. Scope claims (checklist §1)

| Item | Status | Evidence | Reproducible? | Gap / blocks? | Next action |
|---|---|---|---|---|---|
| Surgical compensation engine at scale | GREEN | 100k campaign, 0 invariant violations, 853-file immutable evidence, manifest `dc74ebd…`/`da45c22…` re-verified this session | Evidence immutable; re-run needs Suite A execution authorization | Does not block | none |
| Byte-exact filesystem recovery + conflict protection + idempotency | GREEN | Pilot demo 4/4 — re-run **twice** this session (existing venv + fresh clean-install venv), evidence `evidence_20261017T203353Z.json`, `evidence_20261018T051433Z.json` | Yes — any checkout: `python scripts/pilot_demo_v1.py` | none | none |
| Sealed WP-1 v2 backup/restore, fail-closed | GREEN | 19 fault-injection drills + full suite run #3 (log: `logs/v6_recovery_hardening_session2/full_suite_run3.log`) | Yes — pytest subset, reproduced today (60 passed/2 skipped/4 xfailed, exit 0) | none | none |
| External compatibility | NOT CLAIMED | — | — | correctly excluded | none |

## 2. Validation criteria (checklist §2)

| Item | Status | Evidence | Reproducible? | Gap / blocks? | Next action |
|---|---|---|---|---|---|
| Whole suite green | GREEN | run #3: 2922 passed / 9 skipped / 4 xfailed, exit 0, 3719.82 s, coverage 83.81 % | Yes (`pytest tests`, ~62 min) | none | none |
| Coverage gate ≥ 80 % | GREEN | 83.81 % enforced by addopts | Yes | none | none |
| Fresh upgrade clean, index names consistent | GREEN | live guard re-run today | Yes | none | none |
| Downgrade/re-upgrade roundtrip | **RED (visible)** | 4 xfails with full reasons (D-MIG-1, D-MIG-1b ×2, D3) — re-run today | Yes | **Does not block the filesystem-recovery beta** (migrations excluded from scope, §0 of BETA_FIRST_RUN); blocks any DB/migration beta and production | R10 repair on approval (C-class) |
| Fault-injection drills fail closed | GREEN | reproduced today: 17 runnable drills pass; 2 symlink drills skip honestly (privilege) | Yes | Symlink execution moved into the trial (POSIX slots) | POSIX volunteers run `pytest tests/unit/test_recovery_fault_injection.py -q` |
| Independent defect re-verification | GREEN | both D-MIG repros re-run this session; evidence index in `logs/v6_recovery_hardening_session2/` | Yes (disposable DBs) | none | none |

## 3. Recovery criteria (checklist §3)

| Item | Status | Evidence | Reproducible? | Gap / blocks? | Next action |
|---|---|---|---|---|---|
| Failed attempts leave no residue, retryable (D-RH-1) | GREEN | drills re-run today | Yes | none | none |
| Point-in-time backups + count cross-check (D-RH-2) | GREEN | drills re-run today | Yes | none | none |
| Exact-set manifest trust root (D-RH-4) | GREEN | drills re-run today | Yes | none | none |
| Typed fail-closed errors (D-RH-3/8) | GREEN | drills re-run today | Yes | none | none |
| Re-export cannot destroy last-known-good (D-RH-9) | GREEN | drill re-run today | Yes | none | none |
| Staging symlink escape (D-RH-7) | GREEN in code | drills **skip** on unprivileged Windows (reproduced today) | Execution evidence missing on POSIX | Does not block start; **must be captured during the trial** (plan §4.3, slots T2/T3) | POSIX volunteer run |
| Real process-kill / disk-full | **M1 GREEN-on-Windows / M2 RED (M2 only)** | M1 upgraded 2026-10-18: real `TerminateProcess` drill, 20/20 hard kills mid-recovery, 0 torn writes, 0 invariant violations, 20/20 retries succeeded (`logs/v6_final_mission_session4/m1_kill_evidence.json`; failed attempt 1 preserved as drill-bug evidence). M2 disk-full remains mocked-only — real drill needs isolated mount; procedure prepared | Windows real-kill evidence exists; POSIX kill + real disk-full do not | Does not block the disposable-data trial; POSIX kill opt-in in plan §4.4; disk-full isolated env | POSIX volunteer kill opt-in; isolated volume for M2 |
| POSIX restore-vs-running-app (U1) | KNOWN LIMITATION | code-reviewed; untestable here | Needs POSIX host | Does not block (recipe runs headless, app stopped); disclosed | document in trial notes (done) |

## 4. Security & privacy (checklist §4)

| Item | Status | Evidence | Reproducible? | Gap / blocks? | Next action |
|---|---|---|---|---|---|
| Manifest traversal refused | GREEN | drill re-run today | Yes | none | none |
| Secrets never in error text | GREEN | sentinel drill re-run today | Yes | none | none |
| No telemetry / egress in recovery paths | GREEN | grep verification + trial pause criteria | Yes | none | none |
| DNS lookup in host validation | KNOWN LIMITATION | documented; not exercised by the beta workflow | — | Does not block | none |
| POSIX backup permissions (U2/R17) | **RED (proposal)** | register entry | Needs POSIX env | Does not block single-user disposable trial; disclosed | R17 on approval |
| Shell interpolation / accidental execution | GREEN | grep: no `subprocess`/`shell=True` in `app/` | Yes | none | none |
| Minimum permissions documented | GREEN | BETA_FIRST_RUN §1/§7/§9 (new this session, commands all pre-executed) | Yes | none | keep current with findings |

## 5. Production items (checklist §5) — assessed, not required for this beta

| Item | Status | Assessment for the controlled beta |
|---|---|---|
| CI ×2 pushes | BLOCKED (external) | Not required for a local, disposable-data trial; required before GA |
| Docker/PostgreSQL/Redis | BLOCKED (external) | Out of beta scope (SQLite/filesystem only) |
| Idle-window latency rerun | BLOCKED | Out of scope (performance not claimed in beta) |
| Frozen Suite A/B execution | BLOCKED (gate) | Out of scope; manifests re-verified intact |
| R10 + M-PKG/D3 | RED, approval-gated | Out of scope **by explicit exclusion**; visible xfails stand |
| External code audit | BLOCKED | Required before GA, not before a 3–5 volunteer trial |
| Runbook | not produced | Not required for the trial; required before GA |

## 6. Performance (checklist §6)

AuthZ 2.85 ms median vs 1 ms mean threshold and coordination p95 5.99 ms vs
5.0 ms remain **RED**; thresholds untouched; performance is explicitly not a
beta claim. Does not block the recovery trial.

## 7. Acceptance criteria (mission §7) — verdict

| Criterion | Result | Basis |
|---|---|---|
| Clean, supported installation reproduced | **MET** | Fresh venv (Python 3.11.9) + documented `pip install -e ".[dev,security]"`: exit 0, `pip check` clean, 110 packages, `import app.main, sdk.intentlock` ok — evidence `logs/v6_beta_install_check/`; demo + recipe then run **from that fresh venv** (both exit 0) |
| Disposable-project recovery performed and independently verified | **MET** | Hands-on recipe executed twice (both venvs): `state=succeeded`, tester-side SHA-256 `13372663…` matches, workspace contains only the single file, duplicate delivery `blocked_by_conflict` |
| Regression tests for the fixed defects pass | **MET** | 60 passed / 2 skipped / 4 xfailed, exit 0 (regression subset re-run today; full run #3 green) |
| Permissions and data handling documented | **MET** | `docs/operations/BETA_FIRST_RUN.md` §1/§7/§9, plan §3 |
| Limitations and safe failure procedures understandable | **MET** | BETA_FIRST_RUN §8/§9; plan §8 pause criteria |
| No critical/high defect unresolved within declared beta scope | **MET** | D-RH-1..9 fixed and regression-protected; D-MIG-1b/D3 are outside the declared scope, visible as 4 xfails |
| All relevant external blockers explicitly assessed | **MET** | §5 above |
| Repository and prior evidence preserved | **MET** | initial = final: HEAD `145a3d9`, staged 0, stash 1, porcelain 200 baseline; new files disclosed as additions (final counts in the session log entry) |

**VERDICT: READY — for the declared, narrowly scoped controlled beta**
(filesystem-family recovery, disposable projects, T1 + at least one POSIX
slot), subject to the trial's pause criteria and the disclosures in
BETA_FIRST_RUN §9.

**NOT READY** for: production deployment, any database/migration use, SSO/KMS,
multi-user POSIX permission scenarios, or performance-sensitive deployments —
each for the exact reasons listed above.

## 8. Smallest next action with the most evidence

Invite T1 + one POSIX slot (T2 or T3) and run
`docs/operations/BETA_FIRST_RUN.md` verbatim. That single action converts the
three largest remaining evidence gaps (clean-install on a second machine,
POSIX symlink-drill execution, real-interruption opt-in test) into first-hand
reports without touching anything the project cannot afford to lose.
