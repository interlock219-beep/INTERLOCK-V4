# INTERLOCK V6 — FINAL HANDOFF (2026-10-18, session 4)

The single authoritative status document for the recovery-first phase. It
links — and does not duplicate — the living documents: [README](README.md),
[First Run](docs/operations/BETA_FIRST_RUN.md),
[Readiness Audit](INTERLOCK_V6_BETA_READINESS_AUDIT.md),
[Checklist](INTERLOCK_V6_BETA_READINESS_CHECKLIST.md),
[Register](INTERLOCK_V6_RECOVERY_HARDENING_REGISTER.md),
[Beta Plan](INTERLOCK_V6_CONTROLLED_BETA_PLAN.md),
[Invitation Package](INTERLOCK_V6_BETA_INVITATION_PACKAGE.md), and the
append-only [Engineering Log](INTERLOCK_V6_CONTINUOUS_ENGINEERING_LOG.md).

## 1. Declared product scope (frozen)

**Interlock Recovery — controlled beta for supported filesystem-family
recovery scenarios on disposable projects.** Out of scope: database/migration
recovery, production data, guaranteed-recovery claims, untested OS/configs,
performance-sensitive deployment, SSO/KMS, future platform layers.

## 2. Verified installation (Windows 10/11, Python 3.11.9)

```bash
git clone <repository-url> && cd interlock-v4
python -m venv .venv && .venv\Scripts\activate
pip install -e ".[dev,security]"
python -c "import app.main, sdk.intentlock; print('imports ok')"
python -m pip check          # "No broken requirements found"
```

Reproduced twice from tracked files (2026-10-18, sessions 3 and 4): install
exit 0, 110 packages, pip check clean, imports ok. Evidence:
`logs/v6_beta_install_check/` (`*_s4.*` = session 4). There is **no console
CLI** (no `[project.scripts]`); supported interfaces are the Python API/SDK,
`scripts/`, and `uvicorn app.main:app`.

## 3. Verified demo and recovery procedure

`python scripts/pilot_demo_v1.py` → 4/4 verdicts (recovery, safety,
human_change, idempotency), exit 0; latest evidence
`logs/v6_pilot_demo_v1/evidence_20261018T080635Z.json` — content-scanned:
hashes/paths/metadata only, **no file contents** (§4.9 of the mission
verified). Hands-on recipe (`BETA_FIRST_RUN.md` §§4–6): recovery
`succeeded`, independent SHA-256 `13372663edff…` reproducible across three
sessions and two virtual environments, workspace residue none, duplicate
delivery `blocked_by_conflict`.

## 4. Test evidence and environment (exact)

| Evidence | Result | When / where |
|---|---|---|
| Full suite run #3 | 2922 passed / 9 skipped / 4 xfailed, exit 0, coverage 83.81 %, 3719.82 s | session 2; `logs/v6_recovery_hardening_session2/full_suite_run3.log` (not re-run: zero code changes since) |
| Regression subset (5 files) | 60 passed / 2 skipped / 4 xfailed, exit 0 | re-run **sessions 3 and 4** (183.73 s, session 4) |
| `ruff check app sdk` | clean, exit 0 | session 4 |
| Clean install ×2 | exit 0, pip check clean, imports ok | sessions 3 and 4 |
| Pilot demo | 4/4, exit 0 | re-run sessions 3 and 4 |
| **M1 real process-kill drill** | **20/20 hard `TerminateProcess` kills, 0 torn writes, 0 invariant violations, 20/20 retries succeeded** | session 4, user-authorized; Windows 10.0.26300 non-elevated, Python 3.11.9; `logs/v6_final_mission_session4/m1_kill_evidence.json`; failed attempt 1 preserved (drill setup bug — adapter behaved correctly) |
| Frozen Suite A/B | manifests byte-verified (`dc74ebd…`/`da45c22…`), **not executed** | sessions 2–4 |
| Symlink privilege probe | creation fails: administrator privilege required | session 4 — the 2 privileged drills remain un-runnable on this host |
| **M3 real permission drill** | **PASS** — real read-only-target `PermissionError`: typed fail-closed (`failed`, no exception leak), target never torn, 0 residue, same-key retry `succeeded` | session 6 (gate closure); evidence `logs/v6_gate_closure_20261018T092000Z/m3_permission_evidence.json` |
| Dependency advisory audit (full) | 7 advisories across 5 packages — all dev-toolchain or unused orphans (matrix in §5); runtime core clean | session 6; evidence `logs/v6_gate_closure_20261018T092000Z/pip_audit_20261018.json` + OSV cross-check |

Environment: Windows 10.0.26300, Python 3.11.9, non-elevated, SQLite default,
no Docker/PostgreSQL/Redis. M1 harness
(`logs/v6_final_mission_session4/m1_real_kill_drill.py`) is POSIX-portable for
future volunteers.

## 5. Known defects and unsupported scenarios

- **D-MIG-1 / D-MIG-1b / D3** (approval-gated, R10): migration downgrade
  paths brick databases; 4 visible xfails; migrations prohibited in the beta.
- **Symlink-escape drills**: green in code, skip without symlink privilege;
  execution on a privileged/POSIX host is a release gate.
- **M2 real disk-full**: mocked `ENOSPC` only; real procedure prepared (§7),
  not executed — **exact blocker (session 6):** no isolated volume exists on
  this host (C: is the system drive; F: holds the repository and user data;
  creating a sized VHD/loop mount requires administrator rights, unavailable).
  Adjacent real-OS failure handling is now evidenced by the **M3 permission
  drill (PASS)**. **M3 POSIX**: no execution environment (WSL not installed);
  U1/U2/R17 untestable here. **POSIX process-kill**: untested (Windows-only
  M1 evidence).
- **Dependency advisories (session 6 full audit, cross-checked vs OSV):**
  runtime core (fastapi/sqlalchemy/uvicorn/pyjwt/cryptography/…) has **zero**
  advisories. All findings were dev-toolchain or unused orphans:
  `virtualenv 21.7.4` ×4 (fix 21.7.13, via pre-commit, dev-only);
  `mcp 1.29.0` ×1 (fix 1.30.0, via semgrep, dev-only, vulnerable HTTP-server
  surface unused); `nltk 3.10.3` ×1 (no fix, via safety, dev-only);
  `python-jose 3.5.0` + `ecdsa 0.19.2` ×2 (no upstream fixes, pinned in
  runtime requirements.txt but **orphaned** — no reverse-dependency, zero
  imports in app/sdk/scripts; legacy of the disclosed SSO placeholder).
  **Session 7 remediation (owner-approved):** virtualenv → **21.14.11**
  (all 4 advisories cleared); python-jose + ecdsa + pyasn1 + rsa **pruned**
  from both locks and uninstalled (runtime-lock advisories → **0**);
  `mcp` remains — **upstream-blocked** (semgrep pins `mcp==1.29.0` exactly,
  verified in installed 1.181.0 AND latest PyPI metadata; vulnerable surface
  = running an MCP HTTP server, never part of our workflows) — re-audit when
  semgrep relaxes the pin; `nltk`/`safety` are undeclared manual-venv tools
  (not shipped); fresh-venv audit additionally shows the Python-3.11-seeded
  `setuptools 65.5.0` (bootstrap-only, pyproject requires ≥75 for builds,
  working venv runs 84.0.0). Working + fresh venvs: `pip check` clean.
  Full matrix + before/after JSONs: `logs/v6_gate_cd_20261018T100500Z/`.
- U4 (OS-dependent running-app replace), U5 (unkeyed manifest — accepted,
  IDEA-1), DNS-lookup host validation (intended SSRF defense), performance
  thresholds RED vs 1 ms / 5.0 ms (idle-window rerun blocked).

## 6. External validation results

**None.** No volunteer has been contacted or executed. The invitation package
is a draft. A successful internal test is not external validation, customer
validation, or production readiness — and one Windows slot alone would not
establish POSIX compatibility.

## 7. Outstanding approvals and infrastructure dependencies

| Item | State | Needs |
|---|---|---|
| R10 migration repair | proposal ready, approval-gated | explicit authorization |
| R17 POSIX backup permissions | **IMPLEMENTED session 8 (owner-approved); POSIX validation pending** | 6 hunks: adapter staging `os.open(..., 0o600)` ×2 + recorded-mode-only chmod ×2 (no more forced `0o644`); backup `mkdir(mode=0o700)` + POSIX-guarded `chmod 0o600` on artifacts. 5 new tests: 4 POSIX-only (skip on Windows, reported as skipped) + 1 cross-platform chmod-best-effort (executed, passed on Windows). Targeted 29 passed/4 skipped; regression subset **46 passed/6 skipped** exit 0; ruff+bandit clean; M3 drill re-run PASS (behavior unchanged). Diff: `logs/v6_gate_cd_final_20261018T112500Z/`; POSIX execution of the 4 skipped tests: volunteer slot T2 (invitation §J) |
| M2 disk-full drill | **prepared; authorization requested and unanswered → not run** | **isolated volume — unavailable on this host (session 6):** a sized volume (VHD/loop) needs administrator rights; C: is the system drive; F: contains the repository and user data, so filling it is forbidden. Session 7: exact diskpart create/attach/format script, cleanup steps, verification and stop conditions documented in `logs/v6_gate_cd_20261018T100500Z/m2_procedure.md`; the drill itself (`m2_diskfull_drill.py`) hard-refuses any target not on a disposable volume and captures the raw OS ENOSPC, target-integrity hash, residue listing, and same-key retry. Owner approval of the one-time UAC step is the only missing item **(re-requested session 8 with the reviewed+hardened procedure — answered with no decision again; still not authorized, still not run)** |
| Dev-advisory remediations | **APPLIED session 7 (owner-approved "Approve (a)+(b)")** | (a) `virtualenv>=21.7.13,<22.0` added to `requirements-dev.in` → lock regenerated → **21.14.11** installed; all 4 virtualenv advisories cleared. (b) orphan subtree pruned from both locks (`python-jose`, `ecdsa`, `pyasn1`, `rsa`, `six`) and uninstalled from the working venv → runtime-lock advisories **0**. Side repair: dev-lock `semgrep` synced 1.173.0→1.181.0 (the stale pin conflicted with the direct `pyjwt==2.15.0` runtime pin — pre-existing inconsistency). `mcp` NOT changed: upstream-blocked (semgrep pins `mcp==1.29.0` exactly, installed and latest PyPI); `python3-saml` KEPT (lazily imported by `ProductionSAMLAdapter` — reachable feature, zero advisories of its own). Validation: pip check clean (working + fresh), regression subset 45/2 exit 0, `ruff check app sdk` clean, imports OK, hooks execute under new virtualenv. Evidence: `logs/v6_gate_cd_20261018T100500Z/` |
| Privileged/POSIX symlink drills | blocked on this host | macOS/Linux or elevated Windows host |
| CI ×2 pushes, Docker/PG/Redis, idle-window latency rerun, production access | external | infrastructure/authorizations |
| Frozen Suite A/B execution | gate-held | explicit execution authorization |
| External code audit, production runbook | not started | external party / env |

**R17 minimal proposal (do not implement without approval):** export backup
artifacts with `os.open(..., O_CREAT|O_EXCL, 0o600)` and the backup directory
at `0o700`; create restore staging at `0o600` and restore files never more
permissive than the mode recorded in the snapshot (fallback `0o600`). Tests
(POSIX-only, skipped on Windows): umask-0 export yields `0600` artifacts;
restored mode equals recorded mode; cross-user read raises. Contract shapes
unchanged. **Session 7: superseded by the line-accurate diff + 4-test plan +
validation procedure in `logs/v6_gate_cd_20261018T100500Z/r17_proposal.md`
(inspected the actual creation sites: adapter lines 1941/2143 staging
`os.open` without mode; 1952/2179 forced `0o644` default; backup_restore.py
line 122 `mkdir` default and artifact writes).** **Session 8: IMPLEMENTED
per owner approval** — 6 hunks (both staging `os.open` calls now pass
`0o600`; both restore-chmod sites apply only a RECORDED mode, never the
forced `0o644`; backup dir created `mode=0o700`; artifacts chmod `0o600`
POSIX-guarded best-effort) + 5 tests (4 POSIX-only — skip on Windows,
reported as skipped; 1 cross-platform chmod-best-effort — executed, passed);
regression subset 46 passed/6 skipped exit 0; evidence
`logs/v6_gate_cd_final_20261018T112500Z/`. POSIX execution of the 4 skipped
tests remains BLOCKED (no POSIX host) — volunteer slot T2.

## 8. Preservation verification (session 4, end)

HEAD `145a3d9` (master); staged 0; stash 1; porcelain **208 = 67 modified +
60 `web/` deletions + 81 untracked** — the session-3 state (206) plus this
session's 2 disclosed new docs (`INTERLOCK_V6_BETA_INVITATION_PACKAGE.md`,
`INTERLOCK_V6_FINAL_HANDOFF.md`); previously disclosed session-3 docs still
present; `alembic/` shows only the 4 pre-existing untracked migrations
(untouched); frozen manifests intact; evidence never overwritten (versioned
files; failed drill attempt preserved); no staging, commit, push, tag, remote,
secret, threshold, dependency, config, or public-contract change. Git-ignored
evidence added under `logs/v6_final_mission_session4/` and
`logs/v6_beta_install_check/` (`*_s4.*`).

## 9. Release decision (9 categories)

| # | Category | Verdict | Basis |
|---|---|---|---|
| 1 | Code and regression validation | **PASS** | run #3 green; subset reproduced sessions 3–4; ruff clean; zero code changes since |
| 2 | Filesystem recovery correctness (declared scope) | **PASS** | 100k campaign, 19 drills, pilot 4/4 ×3, recipe ×3, M1 real-kill 20/20 |
| 3 | Installation and first-run reproducibility | **PASS** (Windows, Python 3.11.9) | two clean installs from tracked files + demo/recipe from the fresh venv |
| 4 | Windows external validation | **BLOCKED** | no volunteer has executed anything |
| 5 | POSIX external validation | **BLOCKED** | no POSIX host or volunteer; symlink drills skip (privilege probe) |
| 6 | Security and data-integrity assurance | **PASS** (controlled-beta scope) / **PARTIAL** (GA) | traversal/sentinel/no-telemetry verified; M1 real-kill + M3 real-permission verified (M3 re-run PASS after R17); dependency posture re-verified session 8 (locks consistent, pip check clean, runtime-lock advisories 0, 2 unique findings both documented non-actionable); **R17 implemented session 8** (owner-approved; 5 tests added — 4 POSIX-only pending a POSIX run, 1 executed on Windows); external audit documented as GA-mandatory-only (scope decision + residuals recorded); U5 accepted |
| 7 | Operational and infrastructure readiness | **BLOCKED** | no CI, Docker/PG/Redis, runbook, idle-latency rerun — **classified session 6:** none of these is required by the declared filesystem-only beta (self-test and drills run fully offline); all are required for GA. Missing: GitHub push authorization, Docker/PostgreSQL/Redis services, idle window, elevated session for M2 |
| 8 | Controlled-beta readiness | **PASS** (scoped) | install + first-run + regression + limitations + pause criteria + invitation package (now incl. POSIX checklist §J) in place |
| 9 | General-availability readiness | **BLOCKED** | categories 4, 5, 7 BLOCKED and 6 PARTIAL; R10 open; perf RED |

**Controlled beta: RECOMMENDED** for the declared disposable-project scope,
with the warnings and stop conditions in the invitation package and first-run
guide. **General availability: BLOCKED.** The project is not "finished";
external validation has not occurred.

## 10. Minimum remaining steps toward broader launch

1. User invites slot T1 (Windows) + one POSIX slot; volunteers run
   `docs/operations/BETA_FIRST_RUN.md` verbatim → converts verdicts 4/5.
2. Privileged/POSIX host: execute the 2 symlink drills + POSIX kill opt-in.
3. Isolated volume: run the M2 disk-full procedure (§7).
4. On approval: R10 (then flip the migration xfails) and R17 (POSIX perms).
5. External: CI ×2, Docker/PG/Redis, idle-window latency rerun, frozen Suite
   A/B execution, external audit, production runbook.
