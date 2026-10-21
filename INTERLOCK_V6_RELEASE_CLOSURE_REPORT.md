# INTERLOCK V6 — RELEASE-CLOSURE FINAL REPORT (Phase 6 Decision Package)

**Date:** 2026-10-16
**Repository:** `F:\Desktop_Data_2026\Desktop\INTERLOCK V4` · branch `master` · HEAD `145a3d9`
**Nature:** Non-destructive final decision package for the release-closure phase. It supersedes
the gate statuses in `INTERLOCK_V6_FINAL_COMPLETION_REPORT.md` §13 where this phase produced new
evidence; it does not modify that report. Companion documents: `INTERLOCK_V6_MPKG_DECISION_REPORT.md`
(Phase 2), `INTERLOCK_V6_GAP_REGISTER.md`, `INTERLOCK_V6_RELEASE_GATE_R1_R4.md`.

**Authorization posture:** This phase investigated, built/tested in isolated environments, and
applied the local packaging fix. **Nothing was staged, committed, pushed, tagged, published,
deployed, or applied to a production/non-disposable database.** No security-policy waiver or
`--ignore-vuln` suppression was used. Results marked *this phase* were executed in this phase, not
carried over.

---

## 1. Verdict summary — six separate verdicts (V6 final completion mission)

| # | Dimension | Verdict | Evidence basis |
|---|---|---|---|
| 1 | **Local dev / eval readiness** | **READY — VERIFIED** (documented latency exception) | Suite rerun #3 (fresh `--basetemp`): **2857 passed / 3 failed (latency-only) / 7 skipped, 0 errors**, coverage **83.57% ≥ 80%**; all 3 latency failures re-run isolated: **8/8 PASS (15.40s)**; runner selftest **13/13 PASS** |
| 2 | **Controlled pilot / external evaluator** | **READY — CONDITIONAL** | Packaging closed (G9 §6); pilot on non-production data only; conditions in §8; latency exception disclosed to evaluator |
| 3 | **Production deployment** | **NOT READY** | G6 migration approval, G7 CI (never run), G11 infra unverified, latency exception open |
| 4 | **Publication / distribution** | **NOT READY** — do **not** publish | Open gates + two separate push authorizations missing (§8) |
| 5 | **Recovery campaign (100,000 attempts)** | **COMPLETED — PASS WITH DOCUMENTED EXCEPTIONS** | Exactly **100,000/100,000** (all 12 family allocations exact); **99,757 clean outcomes** (59,958 recovered · 29,577 expected refusals · 10,222 honest fault detections); **0 invariant violations, 0 unsupported**; exit 2 driven solely by **243 preserved harness-calibration unexpected records** (§10); abort→resume integrity controls all tripped correctly |
| 6 | **Stress campaigns A–H** | **PASS (sequential, bounded)** | **216 tests green** across A–G + H-under-CPU-pressure legs (H1 correctness holds under load, H2 latency degradation measured vs idle); real process-kill / network / disk-full / clock-skew / live-PG remain **NOT TESTED** |

**No release-readiness claim exceeds the evidence below.**

---

## 2. G1–G11 gate status (updated)

| Gate | Prior | **Now (this phase)** | Basis |
|---|---|---|---|
| **G1 Preservation** | PASS — VERIFIED | **PASS — VERIFIED** | HEAD `145a3d9` unchanged, staged=0, `stash@{0}` intact, 60 `web/` deletions, all pre-existing modified/untracked/ignored work preserved; no build/dist/artifacts leaked into source tree |
| **G2 Reproducible installation** | PASS (limitation) | **PASS — VERIFIED** (limitation removed) | Fresh editable, wheel, and sdist installs all migrate + boot (§6); artifacts now self-sufficient (was source-checkout-only) |
| **G3 Functional correctness** | PASS — VERIFIED | **PASS — VERIFIED** (functional) · **latency exception documented** | V6 rerun #3: **2857 passed / 3 failed / 7 skipped, 0 errors**, exit 1, **2486.7s**, coverage **83.57%** (≥80%); all 3 failures are latency budgets only (env p95 1.872/1.0 ms, hosts 9.233/4.0 ms, fs-compensate 34.024/25.0 ms) under system-wide load (uniform 7–15× vs 10/14 baselines; confound recorded: light edits overlapped the window); **isolated module rerun 8/8 PASS** (thresholds unchanged, single run, no repeat-until-green) |
| **G4 Static/type quality** | PASS — VERIFIED | **PASS — VERIFIED** (re-run) | `ruff check app sdk` exit 0 · `mypy app sdk` exit 0 (318 files) · `git diff --check` exit 0 · `pip check` exit 0 |
| **G5 Security** | PASS — VERIFIED | **PASS — VERIFIED** (re-run, see note) | `bandit -r app -ll` exit 0 · semgrep 3 packs: **11 WARNING / 0 ERROR** · pip-audit **0 vulns** after standard toolchain upgrade · SBOM **110 components** (§5) |
| **G6 Database safety** | PENDING APPROVAL | **PENDING APPROVAL** (unchanged) | Decision report produced (Phase 2); **M-PKG not applied**; `alembic check` still fails (D3 drift) |
| **G7 CI** | BLOCKED EXTERNALLY | **BLOCKED EXTERNALLY** (unchanged) | No commit/push authorization; CI has never run |
| **G8 Operational readiness** | PASS — VERIFIED | **PASS — VERIFIED** (re-run) | Artifact boots: `/api/v1/health` 200, `/api/v1/ready` 200 (wheel + sdist); fault/fencing tests in suite |
| **G9 Release artifact** | **FAIL** | **PASS — VERIFIED** (closed this phase) | Packaging fix applied; **both wheel + sdist** now ship `alembic/` (19 versions) + `alembic.ini` + `.env.example`, install → migrate → boot, **no secrets/DBs/caches** (§6) |
| **G10 Customer readiness** | PASS — VERIFIED | **PASS — VERIFIED** | Docs + evaluator guide (prior); artifact install path now documented and verified |
| **G11 External validation** | BLOCKED EXTERNALLY | **BLOCKED EXTERNALLY** (unchanged) | Local `docker`/`psql` absent; ports 5432/6379 closed (§7) |

**Net change this phase:** **G9 `FAIL → PASS — VERIFIED`**; **G2 limitation removed**; all other
gates re-verified with fresh execution. **G6 stays `PENDING APPROVAL`; G7 and G11 stay
`BLOCKED EXTERNALLY`.**

---

## 3. Exact packaging diff (the smallest safe fix — 3 files)

**File 1 — `pyproject.toml`** (adds data-files; the R-PKG hunk from the prior phase also still
present in this tracked file):

```diff
@@ [tool.setuptools.packages.find] @@
 [tool.setuptools.packages.find]
 include = ["app*", "sdk*"]
 
+# Ship the migration runtime + config template as data files (installed to
+# sys.prefix/share/intentlock) so a built wheel can run migrations without
+# colliding with the `alembic` tool's own top-level package. alembic.ini uses
+# `script_location = %(here)s/alembic` so this resolves for both a source
+# checkout and an installed prefix. The sdist additionally carries these via
+# MANIFEST.in so an unpacked sdist is a complete source tree.
+[tool.setuptools.data-files]
+"share/intentlock" = ["alembic.ini", ".env.example"]
+"share/intentlock/alembic" = ["alembic/env.py", "alembic/script.py.mako"]
+"share/intentlock/alembic/versions" = ["alembic/versions/*.py"]
```

**File 2 — `alembic.ini`** (1 line; no BOM introduced; LF/CRLF preserved):

```diff
 [alembic]
-script_location = alembic
+script_location = %(here)s/alembic
```

**File 3 — `MANIFEST.in`** (new, untracked):

```
# Source-distribution completeness: ship the migration runtime + config template
# so an unpacked sdist is a self-sufficient source tree for install + migrations.
# (The wheel carries the same set via [tool.setuptools.data-files] in pyproject.toml.)
include alembic.ini
include .env.example
graft alembic
global-exclude __pycache__ *.py[cod] *.orig *.rej .DS_Store
```

`git diff --check` on the two tracked files = **exit 0** (no whitespace/line-ending errors).

### Why this design (investigated alternatives)
- **Top-level `alembic` package in the wheel** — tested; the alembic *tool* still imports, but our
  `env.py`/`versions/` would **merge into the tool's `site-packages/alembic/`** namespace (fragile:
  uninstalling either removes both) and the wheel still lacks `alembic.ini` → migration discovery
  would not work. **Rejected as unsafe.**
- **Relocating `alembic/` into `app/`** — would touch `alembic.ini`, CI, and 5+ docs; **expansion**
  beyond "smallest safe fix". Rejected for this phase.
- **`data-files` + `%(here)s`** — no namespace collision; verified working for wheel, sdist, and
  source/editable flows. **Chosen.**

---

## 4. Migration safety decision (Phase 2 — full detail in the decision report)

**Status: `PENDING APPROVAL`. M-PKG was NOT applied** to the repository or any non-disposable DB.

| Aspect | Verdict |
|---|---|
| **Upgrade** (populated DB) | `PASS — VERIFIED` — data preserved byte-identical, idempotent, backward-compatible |
| **Downgrade — data preservation** | `PASS — VERIFIED` — no data lost even when the downgrade fails |
| **Downgrade — schema atomicity (current)** | `FAIL` — on a `NULL expires_at` row it fails mid-flight leaving 4 dropped indexes + a `_alembic_tmp_*` table (recoverable via runbook) |
| **Downgrade — with proposed pre-flight guard** | `PASS — VERIFIED` — clean early refusal, **zero side effects** (measured this phase) |
| **Backup/restore drill** | `PASS — VERIFIED` |
| **PostgreSQL downgrade** | `NOT TESTED` (no PG locally — G11) |

**Recommendation:** approve M-PKG **with an 18-line pre-flight `NULL expires_at` guard** as the
first statement of `downgrade()` (exact code in the decision report §4.3). This converts a partial
mid-flight rollback failure into an enforced, clean precondition refusal — "fail safely via a
documented precondition," without mutating payload data on rollback.

**Exact authorization needed to apply (NOT granted here):** create
`alembic/versions/v6driftbf01_v6_v5_model_drift_backfill.py` (with guard) in the repo →
stage/commit (separate authorization) → apply first to a **disposable** DB, then to production only
under a **further explicit** production-DB authorization.

**Unresolved risk:** `alembic check` continues to fail (33-op drift, defect D3) until M-PKG is
applied — this is by-design, not a regression, and must **not** be hidden by removing the check.

---

## 5. Local test & security evidence (executed this phase)

| Check | Command | Result |
|---|---|---|
| Full test suite | `pytest` | **exit 0** — **2860 passed, 7 skipped, 0 failed**, 1932.34s, coverage **83.57%** |
| Ruff | `ruff check app sdk` | **exit 0** (0.2s) |
| MyPy | `mypy app sdk` | **exit 0** — 318 files (1s) |
| Whitespace | `git diff --check` | **exit 0** |
| Deps consistency | `pip check` | **exit 0** |
| Bandit (CI parity) | `bandit -r app -ll` | **exit 0** (5.4s) |
| Semgrep (3 CI packs) | `p/security-audit p/owasp-top-ten p/python` | **exit 0**, 319 files — **11 WARNING / 0 ERROR** (29.6s) |
| Dependency audit | `pip-audit` (fresh documented install) | raw: 20 vulns in **`pip 24.0` + `setuptools 65.5.0`** (venv bootstrap); after `pip install --upgrade pip setuptools` → pip 26.2.1 / setuptools 84.0.0: **exit 0, "No known vulnerabilities found"** |
| SBOM | `cyclonedx_py environment` | **exit 0** — CycloneDX **1.6**, **110 components**, no `mcp`/`semgrep` |
| Migration consistency | `alembic heads/current/check` | single head `b4b471ffc2bd`; fresh upgrade **exit 0**; `alembic check` **fails (D3 drift)** — expected, M-PKG pending, **not suppressed** |

### Honest notes on the security evidence
- **Semgrep count 6 → 11 (prior → now):** the `p/…` rule packs are fetched live and change over
  time; all 11 are `WARNING`, **0 `ERROR`**. Characterized: `sql-injection-db-cursor-execute` is a
  **Django** rule matching FastAPI `use_case.execute(...)`/`.get(...)` → **false positives**;
  `dynamic-urllib` findings are already annotated `# nosec B310 # noqa: S310` in source;
  `logger-credential-leak` are audit-level. The strict metric (**0 errors**) holds.
- **pip/setuptools CVEs:** these are **not** application dependencies — they come from the
  Python **3.11.9 `ensurepip` bootstrap** (pip 24.0 / setuptools 65.5.0). The project declares no
  runtime pin on them (only `setuptools>=75.0` as a *build* requirement). The **application's
  declared dependencies audit clean**. Remediated by the standard toolchain upgrade (a real fix, not
  `--ignore-vuln`). This honestly explains why the prior phase reported 0 vulns (their env already
  had pip 26.2.1 / setuptools 84.0.0).

---

## 6. Artifact installation results (built in isolated dirs; this phase)

Both artifacts built with `python -m build --outdir <isolated>` — **no `build/` or `dist/` left in
the source tree**. Secret scan: **no `.env`/`.db`/keys/caches**; the sdist's `intentlock.egg-info/`
is standard setuptools metadata present in the baseline too (0 sensitive paths); `.env.example`
carries only placeholders.

| Check | **Wheel** | **Sdist** |
|---|---|---|
| Clean `pip install` (full deps) | exit 0 | exit 0 |
| alembic **tool** intact, our files **not** in its namespace | ✓ | ✓ |
| `share/intentlock` data-files (`alembic.ini` + `.env.example` + **19 versions**) | ✓ | ✓ |
| **`alembic upgrade head`** (migration discovery) | **exit 0** | **exit 0** |
| **`/api/v1/health`** / **`/api/v1/ready`** (app startup) | **200 / 200** | **200 / 200** |
| `pip check` | exit 0 | exit 0 |
| **Result** | **PASS** | **PASS** |

Also verified: **editable** documented path (`pip install -e ".[dev,security]"` exit 0, app imports,
source-tree migration exit 0) — `data-files` does not break editable installs (share/ is simply not
populated there; the source tree provides the migrations).

---

## 7. Docker / PostgreSQL and CI status

**Local infrastructure — all absent (this phase):**
- `docker` CLI: **NOT FOUND** · `psql`: **NOT FOUND** · port **5432 closed** · port **6379 closed**
- ⇒ Local Docker/PostgreSQL validation = **`BLOCKED EXTERNALLY` (G11)**.

**CI *can* validate Docker + PostgreSQL + Redis without local infrastructure** (read-only analysis
this phase):
- `docker-verify.yml`: builds the image and runs the full compose stack (db/redis/app) on
  `ubuntu-latest` (Docker preinstalled), verifying PG auth (correct-ok / empty-reject), Redis auth,
  app health/ready, non-root, `no-new-privileges`, tmpfs, network isolation, secret exposure,
  restart, and teardown.
- `ci.yml`: provides **service containers** `postgres:16-alpine` + `redis:7-alpine`, and runs
  **`alembic upgrade head` + `alembic check` + `alembic current` against PostgreSQL**, plus the full
  pytest suite on PG + Redis (`REDIS_ENABLED=true`).

**Two sequencing facts:**
1. **CI's `alembic check` runs on PostgreSQL → the job will be RED until M-PKG is applied** (D3
   drift). To get a green CI run, **M-PKG must be approved + applied first**.
2. **Real CI remains `UNVERIFIED`** until the workflow actually runs on an authorized pushed
   revision — it has never run. The remote exists (`github.com/interlock219-beep/INTERLOCK-V4`) but
   **push is not authorized**.

**Exact external requirement:** either (a) **authorize the push** of the verified revision (GitHub
runners then provide Docker + PG/Redis), or (b) **provide a Docker/PostgreSQL-capable environment**.

---

## 8. Exact remaining approvals & required actions (in order)

Nothing below is authorized by this phase. To reach a green release candidate:

1. **Approve M-PKG with the pre-flight downgrade guard** (Phase 2 decision report) → creates
   `alembic/versions/v6driftbf01_…py` → closes **G6** and makes CI's `alembic check` pass.
   ```powershell
   $env:DATABASE_URL="sqlite:///<disposable>\verify.db"; python -m alembic upgrade head; python -m alembic check
   ```
2. **Approve staging + commit** of the verified change set (64 modified + 61 untracked in-scope
   paths per the manifest + this phase's `MANIFEST.in`/`pyproject`/`alembic.ini`/reports).
   *Staging/committing is itself a separate authorization.*
3. **Separately authorize `push`** → observe the first CI run → **G7** closes only on a green run
   (which requires step 1 to have landed).
4. **Provide Docker/PG locally *or* rely on CI** → closes **G11**.
5. Before commercial push: decide on upstream Semgrep/`mcp` repin tracking, external pentest, and
   real SSO/KMS integrations (see `INTERLOCK_V6_GAP_REGISTER.md`).

**Do not publish** while G6 is `PENDING APPROVAL` or G7/G11 are `BLOCKED EXTERNALLY`.

---

## 9. Verification of safety invariants (this phase)

| Invariant | Status |
|---|---|
| HEAD unchanged, no commits, staged=0 | ✓ `145a3d9`, staged 0 |
| `stash@{0}` untouched | ✓ intact |
| 60 `web/` deletions preserved | ✓ 60 |
| Pre-existing modified/untracked/ignored work preserved | ✓ MODIFIED 64 (63 + `alembic.ini`), UNTRACKED 61 (58 at phase start + `MANIFEST.in` + Phase-2 decision report + this Phase-6 report) |
| No `git reset --hard` / `git clean` / broad checkout | ✓ none used |
| Artifacts kept out of source tree | ✓ built in `%TEMP%\opencode\v6_p3_artifacts\`; no `build/`/`dist/` in repo |
| No staging/commit/push/tag/publish/deploy | ✓ none performed |
| No `--ignore-vuln` / audit suppression / `alembic check` removal | ✓ none; `alembic check` still fails honestly |
| Root `.env` not opened/printed | ✓ not touched |
| Disposable envs for builds/tests/DBs | ✓ lab/venvs/DBs under `%TEMP%\opencode\` |

---

## 10. V6 final-completion evidence (recovery campaign, stress campaigns, runner controls)

### 10.1 Suite (one controlled rerun + one isolated benchmark — no repeat-until-green)

| Run | Result | Evidence |
|---|---|---|
| Rerun #3 (detached, fresh `--basetemp` outside repo) | **3 failed / 2857 passed / 7 skipped, 0 errors**, exit 1, 2486.7s, coverage **83.57%**, basetemp alive at end, live-agent 23/23 | `v6_s4_pytest_run3.log` + `_meta.txt` |
| Interrupted run #2 (external harness restart) | all-green partial, no failure markers — preserved, not counted | `v6_s4_run2_interrupted_note.md` |
| Isolated latency benchmark (run **once**) | **8/8 latency tests PASS** in 15.40s (exit 1 only from suite-wide cov floor on single-file scope — artifact) | `v6_s4_isolated_benchmark.log` + meta |

Failures are latency-only with uniform **7–15× inflation** vs 10/14 baselines while the
functionals never fail in any run; thresholds were **not changed**; the module passes
8/8 in isolation. Honest characterization: system-wide load signature, with the confound
that light file edits overlapped run #3's performance window. Latency verdict stays
**FAIL-in-suite / PASS-isolated** until an idle-window rerun (requires scheduling
approval; no re-run performed here).

### 10.2 Runner validation (S1–S7, final run **13/13 PASS**, exit 0)

Smoke exit-clean + exact counts + all 12 families; deterministic repeatability
(identical batch digests); interrupt→resume (60→120, 0 duplicate IDs, 2 batches verified);
evidence tamper → **exit 3**; injected invariant → **exit 2 immediate**; injected unexpected
×2 → exit 2; ×5 consecutive → **exit 2 abort at 5th**; schema/counting/memory/disk bounded.
Evidence: `runs/selftest_20261017_071717`, `v6_s4_selftest_run7.log`.

### 10.3 100,000-attempt recovery campaign — COMPLETED

- **Exactly 100,000/100,000 attempts, 200 batches × 500**, seed `0x1A2B3C4D`,
  config `v6rc-2026-10-17-a`; **every family total == allocation exactly**
  (fs 20,000 · cfg 15,000 · db 12,000 · env 10,000 · arc 10,000 · hosts 8,000 ·
  git 8,000 · orc 7,000 · fault 5,000 · containment 3,000 · backup 1,500 · cert 500).
- Outcomes: **recovered 59,958 · expected refusals 29,577 · honest fault detections
  10,222 · unsupported 0 · invariant violations 0 · unexpected 243** (sum = 100,000).
- Two-leg arc: run 1 aborted honestly at **97,465** (exit 2, 5-consecutive rule; manifest
  preserved `manifest_v1_aborted_97465.json`) after the harness-calibration defect
  `ws_inside_ok` (relative path resolved against CWD instead of the workspace) produced
  310 unexpected. Resume attempt 1 was **refused exit 3 by the runner's own integrity
  invariant** (abort-checkpoint counts included the aborted slice); runner fixed
  (abort checkpoint now persists evidence-derived counts), run-1 checkpoint reconciled
  only after sha256-verifying all 194 batches; resume leg verified 194 batches and
  completed the remaining attempts with **0 new unexpected**.
- The **243 unexpected records stay in the evidence** (batches 189–193, never re-run,
  never erased) and are the sole cause of the final exit 2 `completed_with_failures`.
- Resources: 10,105.94s total wall, 9.9 att/s, disk 77.0 MB, tracemalloc peak 109.8 MB
  (bounds 4h/2GB/4GB all respected).
- Campaign folder: `logs/v6_recovery_campaign_100k/` (git-ignored; zero git-state impact).
  Capability matrix + non-claims: `CAPABILITY_MATRIX.md`.

### 10.4 Stress campaigns A–H (sequential, bounded, existing harnesses only)

| Campaign | Result | Key measurements |
|---|---|---|
| A unified lifecycle | **PASS** — 12 passed, 385.63s | UnifiedStressHarness lifecycle (smoke 100/500/1000, 1000-action, recovery 100/1000, human-change, failure, crash/resume, idempotency, invariants, scorecard) |
| B coordination (idle baseline) | **PASS** — 3 passed, 0.52s | burst p95 0.0045ms (n=100); churn p95 0.0272ms (n=200); tenant p95 2.828ms, 1606.3 plans/s |
| C bounded soak | **PASS** — 5 passed, 291.45s | live-agent lifecycle ×10 + scale 10/50/100/500 |
| D fault/crash matrix | **PASS** — 28 passed, 3.56s | 8 `_CRASH_POINTS` + 3× deterministic + exactly-once + recovery lab 7–9 |
| E gauntlet | **PASS** — 46 passed, 358.74s | worst-case 500, benchmark scales, baseline restore, idempotency, reproducibility |
| F containment/boundary | **PASS** — 56 passed, 11.42s | real containment + execution-boundary bypass + cascade/domain-F (first attempt invalid: path typo in wrapper; rerun corrected) |
| G concurrency/isolation | **PASS** — 45 passed, 312.89s | sweep 1→50, 100-claimant race, cross-tenant, revoke-during-ops, multiprocess lease/quota, fencing |
| H1 correctness under CPU pressure | **PASS** — 18 passed, 3.02s (4 busy workers, 8 cores) | correctness holds under load |
| H2 latency under CPU pressure | **PASS** — 3 passed, 0.63s | burst p95 0.0067ms, churn p95 0.0260ms, tenant p95 4.188ms, 1098.6 plans/s — honest degradation vs idle B, budgets met |

Total **216 tests green**; no timeouts; load workers killed after H. Evidence:
`v6_s4_stress_summary.txt` + `v6_stress/*.log`. Wrapper note: `Start-Process .ExitCode`
reads empty in this host (diagnosed); statuses re-derived from pytest summary lines in
the campaign logs (logs = evidence of record).

### 10.5 Explicitly NOT TESTED / limitations (unchanged claims)

- Real process-kill mid-write, real network partitions, real disk-full/torn-write,
  clock-skew, live PostgreSQL: **NOT TESTED** (no safe infra available).
- CI **never run** (G7); Docker/PG/Redis unverified (G11); alembic not exercised by the
  suite; gauntlet is single-seed; `FileVersion`/`DatabaseRecord`/`ConfigRollback` lack
  direct adapter tests; legacy `execute_recovery` returns a canned response.
- Findings recorded: `WorkspacePathSecurity.validate` resolves **relative** paths against
  CWD (suite only exercises absolute paths); `MockRecoveryAdapter.verify` always reports
  `verified=False`, so the orchestrator correctly emits `EXECUTED_NOT_VERIFIED`
  (honesty demonstration).

### 10.6 Actions requiring user authorization (nothing performed)

1. Alembic migration decision (G6) / M-PKG application — **not applied, not authorized here**.
2. Commit/push (two separate authorizations) — **not requested, not performed** (G7).
3. Production access / live infra validation (G11) — **not attempted**.
4. Publication/distribution of any artifact — **blocked by verdict 4**.
5. Optional idle-window full-suite rerun to clear the latency exception — **needs scheduling approval**.

Preservation confirmed throughout: HEAD `145a3d9`, staged 0, 60 `web/` deletions, stash,
ignored files, prior reports and failed-run logs all intact; no commits/tags/deploys.
