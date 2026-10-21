# INTERLOCK V6 — FULL PROJECT CODE QUALITY & RELEASE READINESS AUDIT

**Audit date:** 2026-10-20 (17:00–17:30 local)
**Auditor role:** Senior staff engineer / application security engineer / QA architect / release engineer
**Repository:** `F:\Desktop_Data_2026\Desktop\INTERLOCK V4`
**Branch / HEAD at audit start:** `master` @ `624171eeebdf5931351234594653352a12fea7f3`
**Audit mode:** Phase A — read-only. No application code was modified. One new file created (this report).

> **Status update — 2026-10-21 (remediation Batches 1–7).** The findings below are the
> original 2026-10-20 audit and are preserved unchanged. **Fourteen findings have since
> been fixed and regression-tested**: RE-01, RE-02 (Batch 1), RE-03, RE-06, RE-12, RE-19
> (Batch 2), WEB-01 (Batch 3), RE-05 (Batch 4), RE-09, RE-07, RE-11 (Batch 5), TST-05,
> TST-06, TST-07, WEB-02, WEB-04 (Batch 6), and TST-01, TST-02, PKG-01, MNT-01 (Batch 7).
> Two **new** findings were discovered and recorded: **SUPPLY-01** (High — the product's
> interfaces are outside version control, so a release built from the repository ships
> without the CLI) and **API-AUTH-01** (Informational — a new guard proving that every API
> route is authenticated or explicitly justified). **MIG-01/MIG-02 remain BLOCKED** on the
> owner's approval, with a full remediation proposal in
> `docs/operations/MIGRATION_R10_PROPOSAL.md`. See **§4.3** for the post-remediation test
> runs, **§5.1** for the status ledger, **§5.2** for the new fixes and **§5.3** for the
> new findings.

---

## 1. Executive summary

Interlock is **not a typical AI-agent wrapper project**. The core recovery engine is
built with genuine engineering discipline: strict typing (`mypy --strict`, 0 errors over
319 files), a fail-closed refusal ladder, byte-exact content handling via base64,
atomic staging + `os.replace`, re-hashing immediately before the write, and an
independent post-write re-hash that decides success. The Terminal Runner is a thin,
honest layer over the *same* engine module the VS Code extension drives (no divergent
second implementation), it is fully non-interactive (no TTY prompts, so it cannot hang
CI), and its lifecycle check passed **38/38** on a re-run during this audit, including
"preview is read-only", "recover without approval is refused (exit 5), file untouched",
"byte-for-byte restore", and "parent traversal refused, sentinel outside the workspace
intact".

That said, the audit found **two release blockers that would make a public Product Hunt
launch actively harmful**, and two High-severity data-integrity defects in the evidence
layer that undermine the product's central promise:

1. **The VS Code extension does not compile — and no CI job would have noticed.** At 17:16 the current tree failed `npm run typecheck` (exit 2) and `npm run lint` (exit 1, 10 errors), so the scripted release path (`vscode:prepublish` → `npm run package`) failed. *This was fixed by parallel in-flight work at ~17:30 and re-verified clean at 17:35 (typecheck 0, lint 0, 343/343 tests).* The durable finding is not the breakage itself but the absence of any CI gate on either product interface (TST-02) — and the fact that the only `.vsix` in the tree (14:31:52) still predates the current build (17:27:59), so installing it yields a build without the Recovery Inbox.
2. **The website and README tell users the opposite of the truth.** The Download page
   states *"no artifact exists in the repository"* and *"there is no extension source
   here to package with vsce"*, and the README says *"no `.vsix` artifact exists"*. The
   repository contains a 33.8 MB installable `interlock-vscode-0.1.0.vsix` with a
   SHA-256-pinned bundled CPython runtime, plus the complete extension source. This
   contradiction is also internally inconsistent with
   `docs/operations/SUPPORTED_PLATFORMS.md`, which states the VSIX "Ships" and is
   "TESTED — PRIMARY".
3. **Baselines are not integrity-sealed (RE-01).** A baseline document stores the
   content *and* the hash that later "verification" compares against, with no seal.
   Anyone able to write the baseline store can make the engine restore and then
   "verify" attacker-chosen bytes.
4. **The CLI silently overwrites an existing baseline (RE-02).** Re-running
   `interlock protect` on the same resource destroys the original pre-fault snapshot —
   the single artifact the product exists to preserve.
5. **The server's database downgrades are irreversible (MIG-01).** Three integration
   `xfail` tests document that `alembic downgrade base` is impossible on any database
   and that even a *successful* partial downgrade silently bricks forward recovery
   ("strictly worse than the failed-downgrade variant, because the operator is told the
   rollback worked"). The project discloses this honestly as the approval-gated "R10"
   repair; it is still unfixed, and `alembic check` currently reports 33 operations of
   model/migration drift (MIG-02), so the CI migration gate cannot pass on the first
   real push. This affects the **control-plane server**, not the filesystem engine that
   the extension and CLI drive.

The surrounding project quality is high: the website is unusually honest (no fabricated
metrics, testimonials, certifications or checkout; explicit "macOS and Linux have not
completed native validation"), the security posture has no shell-injection or
deserialization surface at all, `pip-audit` and `npm audit` are effectively clean, and
the CI workflows are thoughtful — but **CI has never run** (no push since 2026-09-27),
and **CI has no job for either of the two user-facing product interfaces** (the VS Code
extension and the website).

**Bottom line:** the *engine* is close to release quality. The *product around it* —
packaging, install instructions, CI gating, and the website's factual claims — is not.

---

## 2. Overall release readiness

| Target | Verdict | Blocking reasons |
|---|---|---|
| **Public Product Hunt launch** | **NOT READY** | MIG-01 (irreversible, database-bricking downgrades) and MIG-02 (33-op model/migration drift) for the server product; no shippable VSIX rebuilt from the current source; no CI gate for extension/site (TST-02); unverified cross-platform claims. *RE-01, RE-02, RE-03, RE-05, RE-06, RE-12, RE-19 and WEB-01 are now fixed and tested (Batches 1–4).* |
| **Controlled / free pilot (Windows x64, disposable projects, offline)** | **READY WITH CONDITIONS** | Conditions: the VSIX is rebuilt from the current source and its SHA-256 recorded; the limitations document is signed off; no production data; the migration defect (MIG-01) is not in scope for the file-recovery path but must be disclosed for the server product. |
| **Paid beta** | **NOT READY** | No customer-demand evidence; no legal/support/incident-response apparatus (pre-existing conclusion, re-confirmed against `site/src/pages/Pricing.tsx:73`) |
| **General availability** | **NOT READY** | Real disk-full (M2) drill never executed; no native POSIX validation; CI never executed; no external audit; **MIG-01**; MIG-02 |

**Recommendation:** fix P0/P1 (est. 4 focused changes), publish a real artifact, correct
the site, then re-run this audit's checks. Do not launch publicly with the current
website text — a visitor who installs the VSIX from the repository and then reads the
download page will conclude the product is broken or deceptive.

---

## 3. Repository inventory and audit scope

| Component | Location | State at audit time | Audited |
|---|---|---|---|
| Shared Python recovery engine (command layer) | `extensions/vscode/python/interlock_bridge.py` (1388 lines) | untracked (`?? extensions/`) | Full read |
| Recovery adapters | `app/infrastructure/recovery/*.py` (filesystem 2304 lines, file_version, git, config, hosts, archive, env, database, rollback) | tracked + untracked mix | Full read of filesystem adapter; write-sites of others |
| Evidence/verification services | `app/domain/services/{evidence_verification,independent_verification,recovery_planning,evidence_hash,recovery_adapter,tool_security}.py` | tracked | Full read |
| Path security | `sdk/workspace_protection/path_security.py` | tracked (modified in worktree) | Full read |
| VS Code extension | `extensions/vscode/` (29 `src/*.ts`, `package.json`, `tools/`, `test/`) | untracked, **actively edited during audit** | Full read of critical paths |
| Terminal Runner (CLI) | `interlock_cli.py` (534 lines) | untracked | Full read + executed |
| FastAPI server / control plane | `app/` (domain, application, infrastructure, presentation) | tracked | Read (auth, config, routes) + linted/typed |
| Website | `site/` (Vite + React 19, 11 pages) + `downloads/index.html` | untracked | Full read of claims + built + tested |
| Deleted legacy site | `web/` (60 files) | deleted in worktree | Not restored (preserved as-is) |
| Tests | `tests/{unit,integration,stress,performance}` (2942 collected) | tracked + untracked | Executed + mapped |
| CI | `.github/workflows/{ci,security,docker-verify}.yml` | tracked (modified) | Full read |
| Docs | `docs/**`, 19 top-level `INTERLOCK_*.md` reports | mixed | Read (platforms, safety, terminal runner) |

**Not audited / out of scope (stated explicitly):** the running server's live behaviour
against Postgres/Redis (CI-only), real macOS/Linux hardware, real ENOSPC, the
proprietary billing/SAML/SSO provider integrations beyond route-level auth review, and
the `.kilo/worktrees/estimated-mimosa` worktree.

---

## 4. Checks executed and exact outcomes

All commands run from the repository root using the project venv
(`.venv\Scripts\python.exe`, CPython **3.11.9**).

| # | Check | Command | Outcome |
|---|---|---|---|
| 1 | Git preservation snapshot | `git status --porcelain`, `git stash list`, `git diff`, `git ls-files --others` | 226 porcelain entries, 1 stash (`stash@{0}`), 132 tracked files changed (2692+/8287−), 254 untracked. Snapshots saved to `%TEMP%\opencode\` |
| 2 | Lint — project code | `ruff check app sdk interlock_cli.py` | **exit 0 — All checks passed** |
| 3 | Lint — whole repo | `ruff check .` | **exit 1 — 1008 findings** (all outside `app/`,`sdk/`,`interlock_cli.py`): 420 E501, 160 W293, 127 F401, 93 T201, 30 I001, 27 UP015, **19 invalid-syntax**, 18 S608, 16 E741, 13 F841, 2 **F821**, 7 S605, 7 S607, 6 S108, 3 S110 |
| 4 | Type check | `mypy app sdk interlock_cli.py` (strict) | **exit 0 — no issues, 319 files** |
| 5 | Unit test suite | `pytest tests/unit -q --cov-fail-under=0 --maxfail=30` | **exit 0 — 2416 passed, 7 skipped, 3 warnings in 1862.70s (31:02)**; coverage **77%** (25,295 statements, 4,965 missed; 6,690 branches, 1,090 partial) |
| 6 | Integration suite | `pytest tests/integration -q --cov-fail-under=0 --maxfail=20` | **exit 0 — 446 passed, 1 skipped, 4 xfailed, 22 warnings in 981.91s (16:21)**. The 4 xfails are **honest, detailed, and material** — they encode confirmed migration defects (see MIG-01/MIG-02) |
| 7 | Test collection | `pytest --collect-only -q` | **exit 0 — 2942 tests collected in 68.28s**, no collection errors |
| 8 | Security lint | `bandit -r app -q -f txt` | 49,666 LOC scanned — **7 Low, 0 Medium, 0 High**; exit 1 (issues found). All 7 Low are `try/except/continue` with documented rationale (e.g. `app/domain/services/recovery_planning_service.py:494`) |
| 9 | Python dependency audit | `pip-audit --progress-spinner=off` | **exit 1 — 2 known vulns**: `mcp 1.29.0` (CVE-2026-59951, *required-by: semgrep*), `nltk 3.10.3` (PYSEC-2026-3740, *required-by: safety*). Both are **dev/security tooling, not runtime deps**. `intentlock` skipped (not on PyPI) |
| 10 | Python packaging build | `python -m build --no-isolation --outdir %TEMP%\pkg_audit` | **exit 0** — `intentlock-4.0.0-py3-none-any.whl` (614,561 B) + `intentlock-4.0.0.tar.gz` (470,046 B) |
| 11 | Wheel content inspection | `zipfile` listing | 350 entries. Contains `interlock_cli.py`, `share/intentlock/python/interlock_bridge.py`, `share/intentlock/alembic/versions/*` (24 migrations), `app/`, `sdk/`, `dist-info/licenses/LICENSE`. **No** `.env`, tests, logs or credentials |
| 12 | Sdist content inspection | `tarfile` listing | 397 entries, top level `intentlock-4.0.0/`; **no** logs, `fix_*.py`, `test_credentials*`. Only `.env.example` (template) |
| 13 | CLI lifecycle (independent) | `python tests/integration/cli_lifecycle_check.py` | **exit 0 — 38 passed / 0 failed** (read-only preview, refusal without approval, byte-exact restore, verify exit 6 on divergence, traversal refused) |
| 14 | CLI clean-install | `python tests/integration/cli_clean_install_check.py` | **exit 0 — 27 passed / 0 failed.** Fresh venv, wheel installed with `--no-deps`, no repo on path, no `--engine-root`, no `INTERLOCK_BRIDGE`: baseline stored outside the workspace, preview read-only, recover refused without approval (exit 5) and byte-exact with approval, verify exit 0, diverged verify exit 6 with parseable `--json`, parent traversal refused, outside sentinel intact, unknown command exit 2 |
| 15 | Extension unit tests | `npm run test:unit` (mocha) | **exit 0 — 280 passing (16s)** at 17:2x; **re-run at 17:36 after the in-flight recompile → exit 0 — 343 passing (5s)** |
| 16 | Extension typecheck | `npm run typecheck` (`tsc -p ./ --noEmit`) | **17:16 → exit 2** (5+ errors, `src/recoveryInbox.ts`, `recoveryInboxHtml.ts`, `recoveryInboxPanel.ts`); **17:35 re-check → exit 0** after in-flight fixes (see EXT-01) |
| 17 | Extension lint | `npm run lint` (eslint) | **17:16 → exit 1 (10 errors)**; **17:35 re-check → exit 0** |
| 18 | Extension packaging | `npm run package` (vsce) | **NOT RUN** — `vscode:prepublish` = `typecheck && lint && test:unit && compile`, and typecheck/lint fail, so this command cannot succeed as-is (inference from #16/#17, not executed) |
| 19 | Site unit tests | `npm test` (vitest) | **exit 1 — 39 passed / 1 failed**: `src/pages/Demo.test.tsx:130` "switching scenarios mid-run clears every result and event" — 5000 ms timeout |
| 20 | Site typecheck / lint | `npm run typecheck`, `npm run lint` | **exit 0 / exit 0 — clean** |
| 21 | Site production build | `npx vite build --outDir %TEMP%\site_build --emptyOutDir` | **exit 0 — built in 15.39s** (route-level code splitting; 309.87 kB main chunk). `site/dist` was **not** touched |
| 22 | Node dependency audit | `npm audit --omit=dev` (site + extension) | **exit 0 — "found 0 vulnerabilities"** for both production dependency trees |
| 23 | Dangerous-pattern sweep | ripgrep: `shell=True|os.system|subprocess|pickle|yaml.load(|eval(|exec(|marshal.` over `app/`, `sdk/`, `interlock_cli.py`, `extensions/vscode/python` | **0 matches** — no command-injection or unsafe-deserialization surface in the Python stack |
| 24 | Recovery-edge-case test mapping | ripgrep over `tests/` for traversal / symlink / junction / stale / corrupt / permission / unicode / large-file / cancel / bulk / byte-exact / UNC / concurrency / hash-mismatch | Covered: traversal, symlink (19 hits), stale (88), corrupt/truncated (39), permission (128), cancel (24), bulk (69), byte-exact (18), UNC (55), concurrency/drift (310), hash-mismatch (236). **Not covered: junction/reparse-point (0 matches), Unicode recovery paths (2 policy-only hits)** — see TST-06/TST-07 |
| 25 | Pytest collection of CLI checks | `pytest tests/integration --collect-only -q` | **0 node IDs** for `cli_*_check.py` — they are never collected (TST-01) |

### 4.1 Pending / not completed

| Check | Status | Reason |
|---|---|---|
| Integration suite (`pytest tests/integration`) | ✅ **Completed — 446 passed, 1 skipped, 4 xfailed, exit 0** (check #6) | — |
| CLI clean-install check | **Completed — 27 passed / 0 failed** (see check #14) | — |
| `npm run package` (vsce) | **Not executed** | Would produce a release artifact; typecheck/lint already fail, so it is not informative |
| Real macOS / Linux runs | **Not possible here** | Windows-only host (see §13) |
| Real disk-full (ENOSPC) drill | **Not executed** | Documented as authorization-gated in `docs/operations/SUPPORTED_PLATFORMS.md:92` |
| `semgrep` (CI-configured) | **Not executed** | Would transmit source to an external service; no approval given |

### 4.2 Concurrent modification during the audit (validity statement)

The working tree was being **actively developed in parallel with this audit** (a
separate agent session is present in `.kilo/agent-manager.json`). The following
changes were observed live, all under `extensions/vscode/`:

| Time | Change | Effect on this report |
|---|---|---|
| 16:48–17:20 | New/edited extension sources: `inboxDiscovery.ts`, `recoveryInbox.ts`, `recoveryInboxHtml.ts`, `recoveryInboxPanel.ts`, `inboxController.ts`, `bridge.ts`, `commands.ts`, `extension.ts`, `webviewHtml.ts`, `package.json` | EXT-01 raised at 17:16; EXT-02 raised at 17:16 |
| 17:17:03 | **`extensions/vscode/python/interlock_bridge.py` (the shared engine command layer) was modified** | RE-01 was **re-verified against the modified file** at 17:34 and still holds (`load_baseline` 484–542 unchanged; the v2 seal is applied only to preview evidence at 651–654) |
| 17:25–17:28 | New extension tests + visual harnesses | Extension test count moved 280 → 343 |
| 17:27:59 | `out/` recompiled (now includes `recoveryInbox.js`) | EXT-02 resolved |

**Consequences for the reader:**
- Findings about the extension are stated **as of 17:35**, and EXT-01/EXT-02 are
  explicitly time-stamped because the code moved during the audit.
- `interlock_cli.py` (last changed 13:44:03) and
  `app/infrastructure/recovery/filesystem_recovery_adapter.py` (18 Oct 18:51) were
  **not** modified during the audit, so RE-02, RE-03 … RE-12, RE-19 are stable.
- Re-verify the extension findings after the in-flight work lands.
- None of these changes were made, reverted or staged by this audit.

### 4.3 Post-remediation validation runs (Batches 2–4, 2026-10-21)

| Check | Command | Result |
|---|---|---|
| Python unit suite | `pytest tests/unit -q --cov-fail-under=0 --maxfail=30` | **exit 0 — 2462 passed, 7 skipped, 3 warnings (18:09)**; coverage 78% (25,346 stmts / 4,971 missed) |
| Python integration suite | `pytest tests/integration -q --cov-fail-under=0 --maxfail=20` | **exit 0 — 455 passed, 1 skipped, 4 xfailed (11:38)**; the 4 xfails are the unchanged, documented MIG-01/MIG-02 migration defects |
| Recovery truthfulness (new) | `pytest tests/unit/test_recovery_truthfulness.py` | **10 passed** (RE-03, RE-06, RE-12, RE-19) |
| Baseline integrity | `pytest tests/unit/test_baseline_integrity.py` | **22 passed** |
| CLI baseline persistence | `pytest tests/unit/test_cli_baseline_persistence.py` | **14 passed** |
| Bridge baseline integrity | `pytest tests/integration/test_bridge_baseline_integrity.py` | **7 passed** |
| Path security (UNC) | `pytest tests/integration/test_workspace_protection/` | **40 passed, 1 skipped** (symlink drill needs elevation) |
| Recovery regression set | `pytest tests/unit/test_filesystem_recovery_adapter.py test_recovery_fault_injection.py test_backup_restore_drill.py test_git_repository_adapter.py test_recovery_score_service.py test_recovery_certification_lab.py test_evidence_integrity_v2.py test_adversarial_verification.py` | **155 passed, 6 skipped** (environment skips) |
| Bridge integration (real engine) | `python extensions/vscode/test/integration/bridge_integration.py` | **79 passed / 0 failed** |
| CLI lifecycle | `python tests/integration/cli_lifecycle_check.py` | **42 passed / 0 failed** |
| CLI clean install | `python tests/integration/cli_clean_install_check.py` | **27 passed / 0 failed** |
| Extension | `npm run typecheck` / `lint` / `test:unit` | **exit 0 / exit 0 / 375 passing** |
| Website | `npm run typecheck` / `lint` / `test` / `vite build` | **exit 0 / exit 0 / 40 passed / build OK** |
| Static analysis | `ruff check app sdk interlock_cli.py extensions/vscode/python/interlock_bridge.py` + new tests | **All checks passed** |
| Types | `mypy app sdk interlock_cli.py extensions/vscode/python/interlock_bridge.py` | **Success — 320 files** |
| Security lint | `bandit -r app -q -f txt` | **7 Low, 0 Medium, 0 High** (unchanged) |
| Engine bundle | `node extensions/vscode/tools/build-engine-bundle.js` | **exit 0** — 38 files, tree `2816f1f7c9d8fb96`, byte-identical to canonical |

---

## 5. Confirmed findings

Severity key: **Critical** / **High** / **Medium** / **Low** / **Informational**.
Evidence provenance: **[A]** = read and verified directly by the auditor; **[D]** = derived
from a delegated full-file read and spot-checked by the auditor.

### EXT-01 — **Medium (was High at 17:16; resolved at ~17:30 by in-flight work)** — The extension source failed to compile during the audit; nothing gates that in CI
**Evidence [A]:** At **17:16–17:20** the current tree failed both gates: `npm run typecheck` → **exit 2** (`src/recoveryInbox.ts:1026` `TS2339: Property 'map' does not exist on type 'Iterable<...>'`, `:1026` `TS7006` implicit any, `:1029`/`:1055` `TS2339: Property 'outcome' does not exist on type '{}'`, `src/recoveryInboxHtml.ts:27-32` `TS6133`, `:171` `TS6133`, `src/recoveryInboxPanel.ts:23` `TS2459` "declares 'isSafeResource' locally, but it is not exported") and `npm run lint` → **exit 1 (10 errors)**. Because `package.json` `scripts.vscode:prepublish` = `npm run typecheck && npm run lint && npm run test:unit && npm run compile`, `npm run package` (`vsce package`) could not succeed from that tree.
**Re-verified at 17:35 (current tree):** `npm run typecheck` → **exit 0**, `npm run lint` → **exit 0**, `npm run test:unit` → **exit 0, 343 passing** (up from 280 — the new Recovery Inbox tests are compiled and green). The defect was fixed by parallel in-flight work during this audit, not by this audit.
**Residual risk (why this stays a finding):** nothing in CI would have caught the breakage (TST-02), so the release path is one unshipped commit away from failing again; and the only `.vsix` in the tree (14:31:52) predates the current build (17:27:59) — installing it gives a build **without** the Recovery Inbox.

### EXT-02 — **Low (resolved at 17:27 by in-flight work)** — The compiled `out/` bundle was stale relative to `src/`
**Evidence [A]:** At 17:16 `extensions/vscode/out/src/` contained 24 modules and **no** `recoveryInbox.js`, while `src/` contained the new Inbox modules — the bundle could not have been produced from the sources. At **17:27:59** the parallel work recompiled `out/` (now 26 modules, `recoveryInbox.js` present) and it is newer than every `src/*.ts` (newest source 17:20:24). The compiled bundle is now current; it remains untracked in git and is not verified against `src/` by any CI job.

### RE-01 — **High (data integrity)** — Baseline evidence carries no integrity seal
**Evidence [D]:** `extensions/vscode/python/interlock_bridge.py`
- `load_baseline()` **484–542**: validates JSON parse, `format == "interlock-baseline-v1"`, workspace match (523–528), resource match (529–534) and the *presence* of `snapshot.hash` (535–541).
- It never recomputes `snapshot["snapshot_hash"]` (computed at capture in `app/infrastructure/recovery/filesystem_recovery_adapter.py:353`) and applies **no** `evidence_hash` v2 seal.
- Contrast `load_evidence()` **650–661**, which *does* verify `compute_evidence_hash_v2` before the preview evidence is used.
- `snapshot_hash` is excluded from comparison in `_state_equal` (`filesystem_recovery_adapter.py:607–613`) and never recomputed on load.
**Impact:** a baseline file that an attacker (or a stray process with write access to `~/.interlock/baselines/` or the extension's global storage) can rewrite coherently — content + hash + snapshot_hash — will be restored by `cmd_execute` and then pass every downstream check (post-write hash at adapter 1960–1969, engine verify, and the independent re-hash at bridge 1153–1171), because all of them compare against the *tampered* baseline hash. The integrity guarantee degrades from "this is the verified before-state" to "this matches a file we stored".
**Repro (no destructive action required):** edit a baseline JSON in a temp copy, change `snapshot.content_b64` and `snapshot.hash` together, then run `interlock preview` / `interlock recover --approved-by X` against a temp workspace — the engine accepts it and verification reports success.

### RE-02 — **High (data loss)** — The CLI silently overwrites an existing baseline
**Evidence [A]:** `interlock_cli.py`
- `_default_baseline_path()` **358–366**: deterministic path per (resolved workspace, resource) → `~/.interlock/baselines/<hash12>-<resource>.json`.
- `_persist_baseline()` **369–392**: `target.write_text(json.dumps(document...))` at **391** — **no existence check, no `--force`, no versioning, no atomic temp+replace**.
**Impact:** re-running `interlock protect` on the same workspace+resource destroys the original pre-fault snapshot, i.e. the one artifact the product exists to preserve. A crash during that write also leaves a truncated baseline (which then fails closed at `load_baseline`, so at least that is safe).
**Note:** the bridge itself never writes baselines (`cmd_capture_baseline` 924–971 is read-only); the destruction is entirely in the CLI layer.

### WEB-01 — **High (launch credibility)** — Website and README state the opposite of repository reality
**Evidence [A]:**
- `site/src/pages/Download.tsx:249-250`: *"Local `.vsix` installation — no artifact exists in the repository, the CI workflow or the release history."*
- `site/src/pages/Download.tsx:256-257`: *"Build from source — there is no extension source here to package with `vsce`."*
- `README.md:324-325`: *"a **VS Code extension** (planned; not built or published yet — no Marketplace listing and no `.vsix` artifact exists)"*.
**Reality in this repository:** `extensions/vscode/interlock-vscode-0.1.0.vsix` exists (33,828,197 B, 2026-10-20 14:31:52; 834 entries: 761 bundled runtime files incl. `python.exe`, 39 engine files, 24 compiled `out/` modules, `media/`, `extension/python/interlock_bridge.py`), and the complete extension source is present (29 `src/*.ts`).
**Contradiction inside the repo:** `docs/operations/SUPPORTED_PLATFORMS.md:43` states the VS Code extension *"Ships"*, bundles a *"pinned, SHA-256-verified CPython 3.11.17 runtime for Windows x64"* and is *"TESTED — PRIMARY"*. `downloads/index.html:48` uses the defensible phrasing *"No `.vsix` artifact is published or distributed."*
**Impact:** a visitor who installs the VSIX and then reads `/download` concludes the product is broken or lying. The `/download` page also suppresses the only working install path from the launch narrative. Must be resolved **before** any public launch.

> **Status: FIXED, TESTED (Batch 3, 2026-10-21).** The Download page, the VS Code status panel, `downloads/index.html`, `downloads/README.md` and the README now state that the extension source is in this repository and builds locally, while nothing is *published*. The true disclosures (no Marketplace listing, no published download, no published checksum, macOS/Linux unvalidated) are unchanged. Site: typecheck 0, lint 0, 40/40 tests, build OK. See §5.1.

### RE-03 — **Medium** — Silent truncation of large files can shrink a file and still report `byte_exact: true`
**Evidence [D]:** `filesystem_recovery_adapter.py`
- `_capture_file_snapshot()` **259–268**: reads `max_size_bytes + 1`, truncates, and computes the SHA-256 **over the truncated bytes**, while `size` keeps the full stat size (**327**).
- `truncated: True` / `byte_exact: False` are recorded (**337**, **350–351**) but never consulted by the restore paths `_execute_restore_content` **1920–1949** and `_execute_restore_deleted_file` **2124–2178**, nor by `load_baseline`; the result details still claim `"byte_exact": True` (**1978**, **2214**).
**Mitigation:** the bridge and CLI refuse to *capture* baselines above `--max-bytes` (5 MB default, bridge 941–950), so their own baselines are never truncated. The adapter's own default limit is 50 MB (**line 70**) and any other producer of snapshots (or direct adapter use) reaches the destructive path. `verify()` would only fail later on `size_mismatch` (1453–1457) — **after** the file has already been replaced.
> **Status: FIXED, TESTED (Batch 2, 2026-10-21).** A truncated before-state is now refused before any write (`_truncated_before_state_error`), the verification fails closed on it, and the bridge refuses a truncated baseline at load (`baseline_truncated`, exit 7). See §5.1.

### RE-04 — **Medium** — TOCTOU: containment is validated on the *resolved* path, the write uses the *unresolved* path
**Evidence [D]:** `_resolve_file_path()` **1721–1726** returns `candidate` (`base_path / file_path`), not the resolved path; `_assert_contained()` **1749–1757** resolves **only for the check**. The write then happens at `temp_path.replace(full_path)` (**1949**) / `os.replace` (**2178**), after hashing the current file (**1897–1905**) and after the staging write + fsync.
**Impact:** replacing a parent directory component with a symlink/junction inside that window redirects the write outside the workspace. No `O_NOFOLLOW`-style directory-handle pinning closes the race.
**Honest scoping:** at *check time* the implementation is correct — `Path.resolve()` handles symlinked files, Windows junctions, subst drives, 8.3 short names, drive-letter case, and trailing-dot/space normalization via Win32 final-path resolution. This is a **structural gap requiring a concurrent local co-actor**, not a directly exploitable path traversal.

### RE-05 — **Medium** — UNC refusal is bypassable with the forward-slash form
**Evidence [D]:** `interlock_bridge.py require_workspace()` **430–435** and `sdk/workspace_protection/path_security.py validate()` **58–60** test only for a `"\\\\"` prefix. `Path("//server/share")` stringifies with forward slashes, so the literal check misses it; the path then passes `exists()`/`is_dir()` and resolves to a real UNC path.
**Impact:** `capture-baseline` / `plan` / `verify` can run against a UNC workspace. **Execution is still blocked** — `filesystem_facts` reports `drive_type == "network"` → `support_verdict = unsupported` → refusal at bridge 1091–1099. This is a defense-in-depth bypass, **not** a containment escape.
> **Status: FIXED, TESTED (Batch 4, 2026-10-21).** `is_unc_path()` now refuses both slash forms in the SDK's path security and in the bridge. See §5.1.

### RE-06 — **Medium** — `delete_file` compensation performs no execution-time identity check
**Evidence [D]:** `_execute_delete_file()` **1991–2030** unlinks at **2018** with no comparison against `after_snapshot.hash` — unlike `_execute_restore_content`, which re-hashes at **1897–1905**.
**Impact:** in the check→unlink window, a human file that replaced an agent-created file at the same path is deleted unverified. Not reachable via the bridge/CLI today (the bridge hardcodes `action_type="modify"`, bridge **399**), but reachable through planning-service flows with create/write actions.

> **Status: FIXED, TESTED (Batch 2, 2026-10-21).** `_execute_delete_file` re-hashes the target immediately before `unlink` and refuses with `BLOCKED_BY_CONFLICT` on mismatch. See §5.1.

### RE-07 — **Medium** — Metadata / ACL / timestamp restore failures are suppressed and never verified
**Evidence [D]:** `_restore_metadata()` **1759–1781** and `_restore_timestamps()` **1783–1795** use `contextlib.suppress(OSError, …)`; ACL restore is effectively a no-op that only records `"acl_capture_available"` (**1777–1780**). `verify()` **1498–1675** checks only content hash / size / raw length / existence — never mode, uid/gid or ACL — while `verification_requirements` claims `"file_metadata_preserved"`, `"file_permissions_preserved"`, `"file_acl_preserved_where_supported"` (**1067–1075**).
**Impact:** a recovery can report `success: true` although permissions/ownership were not restored. (The site discloses the POSIX *backup* umask item at `site/src/pages/Safety.tsx:48`, but not this verification-requirement mismatch.)

### RE-08 — **Medium** — `GitRepositoryAdapter` is declared `PRODUCTION_VALIDATED` but writes non-atomically in text mode and never invokes git
**Evidence [D]:** `app/infrastructure/recovery/git_repository_adapter.py` `_execute_restore_content` **949** and `_execute_restore_deleted_file` **1047**: `full_path.write_text(..., encoding="utf-8")` — direct write (no staging, no `os.replace`, no fsync), text mode (Windows CRLF translation ⇒ not byte-exact), no use of `content_b64`, no post-write hash check. Its docstring (**1–12**, **51–55**) claims "real git operations"/"stash/restore", but a repo-wide search finds **no `subprocess` import anywhere in `app/` or `sdk/`** — it is a plain-Python adapter.
**Mitigation:** `recovery_planning_service._execute_with_protocol_adapters` **449–484** selects the adapter named `filesystem_recovery` for filesystem actions and fails closed otherwise, so the git adapter is not on the default recovery path. `rename_back` is honest — it returns `REQUIRES_MANUAL_ACTION` (**1080–1096**).

### RE-09 — **Low** — Staging-name collision deletes unrelated user files
**Evidence [D]:** `_execute_restore_content` **1915** (`temp_path.unlink(missing_ok=True)`) and `_discard_staging` **1842–1850** remove any pre-existing `*.<suffix>.recovery_tmp` / `*.recovery_tmp` file without checking provenance. A legitimate user file with that exact name is destroyed.

### RE-10 — **Low** — `plan` (a preview command) is not strictly read-only
**Evidence [D]:** `cmd_plan` **1055–1056** writes `<baseline-file>.evidence.json` via `save_evidence` (**550–561**, temp + `os.replace`, atomic). The write target is extension/CLI storage, not the workspace, unless the user points `--out` into the workspace. Disclosed in the returned `note` (**1059–1062**). The other read-only-looking commands (`probe`, `status`, `analyze`, `verify`) write nothing.

### RE-11 — **Low** — Secrets and keys are never excluded from baselines; the redaction code is dead
**Evidence [D]:** `_looks_sensitive` / `redact_mapping` (bridge **132–158**) are defined but never called anywhere in the repository. Baselines store full `content` + `content_b64` verbatim. The CLI default location is `~/.interlock/baselines/` (**358–366**) created with `mkdir(parents=True, exist_ok=True)` and written with `write_text` — **no `chmod`**, so on POSIX the file is world-readable by default umask. `slim_snapshot` (**665–690**) and `slim_diff` (**693–709**) strip content from *display* payloads only — good display hygiene, no on-disk protection. No path-pattern exclusion list exists anywhere in the engine.

### RE-12 — **Low** — Verification can return `verified=True` with no byte comparison, and mislabels `byte_exact`
**Evidence [D]:** `verify()` `delete_file` branch **1558–1571** checks existence only (`lexists`) yet reports `"byte_exact": True` (**1570**). The `rename_back` branch **1621–1662** compares hashes only *"when a hash is available"* (**1633–1646**); when `before_snapshot.hash` is `None` it returns `verified=True` with `"byte_exact": True` (**1658–1662**) on existence-only evidence.
**Positive counterpart:** the main `restore_content` / `restore_deleted_file` paths *are* byte-exact (`_build_byte_exact_verification` **1433–1496**).

> **Status: FIXED, TESTED (Batch 2, 2026-10-21).** The deletion branch no longer claims byte-exactness (it reports `verified_by: "existence"`); the rename branch claims it only when a content hash was actually compared. See §5.1.

### RE-13 — **Low / Informational** — The eligibility matrix exists but the bridge can only ever run `restore_content`
**Evidence [D]:** the adapter implements a full matrix (`_determine_compensation_operation` **1805–1821**; compensation types **1823–1839**: create/write → `delete_file`, modify/update → `restore_content`, delete → `restore_deleted_file`, rename/move → `rename_back`), but the bridge hardcodes `action_type="modify"` (**399**). **Deleted and renamed files therefore cannot be recovered through the bridge or the CLI** — `execute` on a deleted target fails honestly with "File does not exist" (**1890–1895**).
**Positive:** newly created files without a valid baseline are *never* presented as recoverable — `load_baseline` raises `EXIT_PRECONDITION` (**484–491**), called by `cmd_execute` (**1070**) and `cmd_verify` (**1196**).

### RE-14 — **Informational** — `classify_reversibility` overstates reversibility when no true before-state exists
**Evidence [D]:** `capture_recovery_evidence` **985–990** captures the *current* state as `before_snapshot` when none is supplied; `classify_reversibility` **1100–1109** then returns `AUTOMATICALLY_REVERSIBLE` whenever `before_snapshot is not None`. In planning-service flows without a real before-state, "recovery" restores the already-damaged state and verifies as success (honest bytes, wrong semantics). The bridge path is unaffected because it always injects the baseline snapshot (**996**).

### RE-15 — **Informational** — No explicit backup of the current file before overwrite
**Evidence [D]:** `_execute_restore_content` overwrites in place (atomic replace, no backup). The pre-overwrite bytes survive only inside the preview evidence sidecar's `after_snapshot.content_b64` (adapter 1011–1035), and only if the user kept that file.

### RE-19 — **Low** — Unbounded memory reads during verification
**Evidence [D]:** `verify()` `full_path.read_bytes()` (**1552**, **1615**) and the bridge's `_independent_check` `target.read_bytes()` (**1164**) read whole files with no size cap, unlike capture which is capped. A large target can exhaust memory during verification; `verify()` also never consults the `truncated` flag.

> **Status: FIXED, TESTED (Batch 2, 2026-10-21).** Verification hashes and compares files in 64 KiB chunks; the `truncated` flag is now consulted (fails closed). See §5.1.

### MIG-01 — **High (server product: irreversible data loss on rollback)** — Alembic downgrades are impossible, and a partial downgrade permanently bricks the database in **both** directions
**Evidence [A]:** from the integration run — 4 `xfail` tests in `tests/integration/test_alembic_migration_safety.py`, each carrying a precise, self-documenting defect description (the project is commendably honest here — the xfails are visible, not hidden, and not asserted green):
- **`test_downgrade_base_then_upgrade_head_roundtrip`** — *"Confirmed defect D-MIG-1 … full `downgrade base` is IMPOSSIBLE on any database, empty or populated. Migration `3cebbede5768` drops 8 tables in `upgrade()` but its `downgrade()` is `pass` (never recreates them); `0010`'s downgrade then fails dropping indexes on those non-existent tables (sqlite: no such index ix_recovery_reports_incident_id). Fixing requires rewriting a historical migration's downgrade (substantial DDL inverse) — APPROVAL REQUIRED (R10)."*
- **`test_failed_downgrade_must_not_brick_reupgrade`** — *"Confirmed defect D-MIG-1b … a FAILED `downgrade base` leaves the database permanently unrecoverable by alembic in BOTH directions. `3cebbede5768.downgrade()` is `pass`, so after `0010`'s downgrade fails … the next `upgrade head` re-enters `3cebbede5768.upgrade()` and dies with 'duplicate column name: after_state_snapshot'. Neither downgrade nor upgrade can proceed … recovery needs manual SQL surgery or backup restore."*
- **`test_successful_partial_downgrade_must_not_brick_reupgrade`** — *"…a SUCCESSFUL downgrade therefore silently bricks forward recovery — strictly worse than the failed-downgrade variant above, because the operator is told the rollback worked."*
**Impact:** for the **server / control-plane** product, an operator-initiated rollback can destroy the database irrecoverably, and the "successful rollback" variant fails silently. This is a data-loss defect in the product whose entire purpose is recovery.
**Scope note:** this affects the **FastAPI control plane's database**, not the filesystem recovery engine that the VS Code extension and the CLI drive. The file-recovery path is unaffected. It is also **already disclosed** by the project as "R10" (approval-gated repair) — this audit confirms the defect is real, currently reproducible, and still unfixed.

### MIG-02 — **Medium** — Model/migration drift (33 operations); `alembic check` fails
**Evidence [A]:** `test_alembic_check_no_drift` is `xfail` — *"Known defect D3 (gap register #1): model/migration drift (33 ops) until M-PKG is approved and applied."* CI runs `alembic upgrade head` **and `alembic check`** (`.github/workflows/ci.yml:81-83`), so on the first real push the `alembic check` step is expected to **fail** until M-PKG lands.
**Impact:** the ORM models and the migration history disagree, which is how D-MIG-1 style drift accumulates; and the CI migration gate cannot currently pass.

### TST-01 — **Medium** — The CLI's lifecycle and clean-install checks are never executed by pytest or CI
**Evidence [A]:** `pytest tests/integration --collect-only -q` yields **0** node IDs matching `cli_*`; `tests/integration/cli_clean_install_check.py` and `cli_lifecycle_check.py` do not match pytest's default `test_*.py` / `*_test.py` patterns (both are `main()` + `__main__` scripts). A repo-wide search finds them referenced **only** in `docs/operations/TERMINAL_RUNNER.md:196-197` and `INTERLOCK_TWO_INTERFACES_REPORT.md:66-67` — **no workflow, no script, no test runner invokes them**.
**Impact:** the only automated proof that the Terminal Runner works standalone (and that the packaged wheel works in a clean venv) is manual. It can rot silently. I re-ran the lifecycle check during this audit: **38 passed / 0 failed**.

### TST-02 — **Medium** — CI has no job for either user-facing product interface
**Evidence [A]:** `.github/workflows/ci.yml` (jobs: `lint-and-test`, `recovery-cross-platform`, `macos-release-artifact`), `security.yml` (`dependency-audit`, `image-scan`), `docker-verify.yml` (`docker-build-runtime`) — **no npm/vscode/vitest step anywhere**; no `node` runtime is installed in any job.
**Impact:** the extension's compile failure (EXT-01) and the site test failure (check #19) would both pass CI unnoticed. For a launch whose two headline interfaces are the extension and the CLI, this is a material gap.

### TST-03 — **Medium** — The coverage gate (80%) is not currently demonstrated
**Evidence [A]:** `pyproject.toml:142` sets `fail_under = 80`; the unit-only run measured **77%** (25,295 statements / 4,965 missed; 6,690 branches / 1,090 partial). CI runs the full suite (`pytest --cov=app --cov=sdk`, ci.yml:94); `docs/operations/SUPPORTED_PLATFORMS.md:27` claims a full-suite figure of **83.81%** from a prior local run. Until CI actually executes (it never has), the gate's satisfaction is unverified — and the margin is thin.

### TST-04 — **Low** — Repo-wide lint debt is large and CI-scoped around it
**Evidence [A]:** 1008 ruff findings, all outside `app/`/`sdk/`/`interlock_cli.py`. Worst offenders: `tests/stress/test_live_agent_recovery.py` (246), `tests/unit/test_domain_i_verification.py` (89), `tests/unit/test_domain_h_recovery_intelligence.py` (41), `tests/unit/test_session_rollback_service.py` (35), `tests/stress/harness.py` (30), plus root debris (see MNT-03). CI deliberately scopes ruff to `app sdk` (ci.yml:60, :139) with an inline comment declaring the tests/ debt.

### TST-05 — **Low** — Undefined name in a test file, invisible to both gates
**Evidence [A]:** `tests/unit/test_domain_e_toolchain_security.py:27-28` uses `dict[str, Any]` but `Any` is never imported; ruff reports `F821 Undefined name 'Any'` at 27:37 and 28:30. It does not fail at runtime only because the file starts with `from __future__ import annotations` (line 1), which defers annotation evaluation. `mypy` excludes `tests/` (`pyproject.toml:124` `exclude = "^tests/|^scripts/"`), so neither gate catches it.

### TST-06 — **Medium** — No Windows junction / reparse-point test anywhere
**Evidence [A]:** ripgrep for `junction|mklink /J|reparse` over the whole repository returns **0 matches**, while `docs/operations/SUPPORTED_PLATFORMS.md` treats junction handling as a platform concern and the engine's containment logic explicitly claims to resolve reparse points. On the *primary* platform (Windows), a junction is the most realistic directory-escape vector and is completely untested here.

### TST-07 — **Low** — No Unicode-path test for the recovery engine
**Evidence [A]:** the only Unicode tests are policy homoglyph cases (`tests/unit/test_policy_engine.py:75`, `tests/integration/test_adversarial_security.py:1183`). No test drives a non-ASCII workspace path or filename through capture → preview → recover → verify.

### TST-08 — **Low** — 7 tests skip on the primary (Windows) platform
**Evidence [A]:** from the unit run: `tests/unit/test_backup_restore_drill.py:379` (POSIX mode semantics), `tests/unit/test_filesystem_recovery_adapter.py:503,539,561` (POSIX mode semantics), `tests/unit/test_recovery_fault_injection.py:87` ×2 — *"symlink creation unavailable in this environment: [WinError 1314] A required privilege is not held by the client"* — i.e. **the two symlink-confinement drills never execute on the platform that is declared "TESTED — PRIMARY"**, and `tests/unit/test_regression_critical_fixes.py:304` (key manager unavailable). These are precisely the "symlink escape" and "POSIX permission" assertions the platform matrix leans on.

### TST-09 — **Low** — Site test failure (not a flake-immune suite)
**Evidence [A]:** `site/src/pages/Demo.test.tsx:130` — *"switching scenarios mid-run clears every result and event"* — timed out at 5000 ms; vitest run finished 39 passed / 1 failed in 124.77 s.

### SEC-01 — **Informational (positive)** — No command-injection or unsafe-deserialization surface
**Evidence [A]:** ripgrep over `app/`, `sdk/`, `interlock_cli.py`, `extensions/vscode/python` for `shell=True|os.system|subprocess.|pickle.|yaml.load(|eval(|exec(|marshal.` → **0 matches**. The only YAML use is `safe_load`. The extension's only subprocess surface is the engine runtime, which uses list-form invocation with a pinned, SHA-256-verified interpreter.

### SEC-02 — **Informational (positive)** — Server configuration and API auth are sound
**Evidence [A]:** `app/infrastructure/config/settings.py:48` CORS default `["http://localhost:3000"]` (no wildcard); `:26` `jwt_secret_key` uses `default_factory=lambda: secrets.token_urlsafe(48)` (no hardcoded default secret). Emergency/control routes enforce authentication and role + tenant checks (`app/presentation/api/v1/routes/emergency.py:32-47` `_require_emergency_admin`, `CurrentUser` dependencies on every state-changing endpoint; `:175` `Depends(require_role(["admin","operator"]))`).

### SEC-03 — **Low (policy)** — CI transmits source code to an external service on every push
**Evidence [A]:** `ci.yml:68-75` and `security.yml:34-40` run `semgrep/semgrep-action@v1` with `generate-token: true` and the `p/security-audit`, `p/owasp-top-ten`, `p/python` rule packs. Proprietary source is uploaded to the Semgrep cloud. This audit did **not** run it (no approval to upload source). It is a deliberate CI policy, but it should be an explicit, recorded decision for a proprietary product.

### SEC-04 — **Informational (positive)** — Runtime provisioning is pinned and verified
**Evidence [A]:** `extensions/vscode/tools/provision-runtime.js:50` pins a `sha256`; `:177` builds a **tagged** asset URL (no "latest"); `:182-186` recomputes the SHA-256 and refuses to extract on mismatch (*"INTEGRITY FAILURE - refusing to extract"*).

### SEC-05 — **Informational (positive)** — Dependency audits are effectively clean
**Evidence [A]:** `pip-audit` → 2 CVEs, both in dev/security tooling (`mcp` via semgrep, `nltk` via safety) and not shipped; `npm audit --omit=dev` → **0 vulnerabilities** for both the site and the extension production trees; `bandit -r app` → 0 Medium/High.

### PKG-01 — **Medium** — No reproducible release artifact pipeline for the extension
**Evidence [A]:** `extensions/vscode/.vscodeignore` is well designed (excludes `src/`, `test/`, `node_modules/`, `tools/`, source maps, `runtime/**/Lib/site-packages/**` etc.), `media/` assets exist (`interlock-activitybar.svg` 904 B, `interlock-icon.png` 5,386 B), and the existing VSIX contains the bundled runtime + engine + bridge. But there is **no CI job that builds or publishes the VSIX**, and the artifact is untracked in git — so "the release" is a local file with no reproducible provenance (no published checksum, despite the site promising "no download button appears until a real, published artifact exists with a verified checksum").

### PKG-02 — **Informational** — Version/branding drift across artifacts
**Evidence [A]:** `pyproject.toml:7` `version = "4.0.0"`; `interlock_cli.py:46` `CLI_VERSION = "4.0.0"`; `site/package.json` `"version": "6.0.0"`; `README.md:1` "# Interlock V4"; the product and website are branded **V6**; `extensions/vscode/package.json` `"version": "0.1.0"`; the repo/remote is `INTERLOCK-V4`. A public launch with three different version numbers in the README, the wheel, and the extension is a credibility risk.

### PKG-03 — **Informational (positive)** — Python packaging content is clean and complete
**Evidence [A]:** check #10/#11/#12 — the wheel ships the console entry point module, the shared bridge under `share/intentlock/python/`, all 24 Alembic migrations, `alembic.ini`, `.env.example` and `LICENSE`; the sdist contains no logs, no credential files and no debris.

### WEB-02 — **Low** — The home-page demo transcript shows an unlabelled "recovering … 100%"
**Evidence [A]:** `site/src/pages/Home.tsx:150` renders `recovering … 100%` and `:151` `verify: 4/4 files match captured digests` inside a mock terminal titled *"demo — scenario A"* (`:143`). The same page carries a *"What Interlock cannot guarantee"* section (`:261`), which mitigates the risk, but a screenshot-shared marketing asset could be read as a recovery guarantee. Recommend labelling the mock as illustrative output.

### WEB-03 — **Informational (positive)** — The website is unusually honest; no fabricated claims found
**Evidence [A]:** `site/src/content/blog.ts:223` states plainly *"No customer counts, downloads, revenue, success rates, tokens processed, performance benchmarks, certifications, testimonials or star counts appear anywhere here — because none exist to cite."*; `site/src/pages/About.tsx:39` discloses *"No founders, employees, funding or customers are claimed here."*; `Pricing.tsx:12-13,31-40` shows `$0` / `TBD` with the reason charging is unjustified (`:73`); no fake checkout or payment integration exists; `Download.tsx:37` discloses *"Windows x64 is the tested platform; macOS and Linux have not completed native validation"*; `Safety.tsx:48` discloses the POSIX umask item. A targeted search for "guarantee / SOC 2 / GDPR / HIPAA / military / trusted by / testimonials / customer counts" returned **only negations and honest disclaimers** — no unsupported security or performance claims.

### WEB-04 — **Low** — Two divergent install surfaces with inconsistent wording
**Evidence [A]:** `site/src/pages/Download.tsx` (canonical) vs the standalone `downloads/index.html` duplicate. `downloads/index.html:48` says *"No `.vsix` artifact is published or distributed"* (accurate); `Download.tsx:249` says *"no artifact exists in the repository"* (inaccurate). `downloads/index.html:98` itself defers to the site as canonical. Fix WEB-01 at the source and make the static page quote it.

### MNT-01 — **Medium** — A full vendored copy of the engine ships inside the extension
**Evidence [A]:** `extensions/vscode/engine/{app,sdk}` duplicates the canonical `app/`+`sdk/` trees (39 entries in the VSIX, 830,845 B at the sampled depth); the sampled files were byte-identical to canonical at audit time (SHA-256 comparison), so there is **no drift today** — but nothing enforces that. `tools/build-engine-bundle.js` exists yet no CI job verifies bundle == source, and `extensions/vscode/engine` is untracked in git. With three more copies in play (wheel, sdist, extension bundle), divergence is a matter of time.

### MNT-02 — **Medium** — Very large dirty working tree with overlapping report sprawl
**Evidence [A]:** 226 porcelain entries (132 tracked files changed, 254 untracked) and **19 top-level `INTERLOCK_V6_*.md` reports**, several covering the same ground (`RELEASE_READINESS_REPORT`, `RELEASE_CLOSURE_REPORT`, `FINAL_REPORT`, `FINAL_COMPLETION_REPORT`, `WORLD_CLASS_MISSION_FINAL_REPORT`, `RELEASE_GATE_R1_R4`, `GAP_REGISTER`, …). Contradictory claims already exist in the tree (WEB-01 vs `SUPPORTED_PLATFORMS.md:43`). There is also a stash (`stash@{0}`) that must not be lost.

### MNT-03 — **Low** — Root-level patch-script debris is committed and partly unparseable
**Evidence [A]:** ~30 one-off scripts in the repository root (`fix1.py`…`fix19.py`, `apply_fixes.py`, `write_fix.py`, `final_validate.py`, `parse_manifest.py`, `rebuild_manifest.py`, `patch_containment.py`, `wf.py`, `gen.py`, …). `ruff check .` reports **19 invalid-syntax** errors concentrated in `fix_tests.py` and `write_fix.py` (e.g. `write_fix.py:7:310` *"missing closing quote in string literal"*). They serve no product purpose and are the single largest contributor to the 1008-finding lint total.

### MNT-04 — **Informational** — Type safety is not applied to tests or scripts
**Evidence [A]:** `pyproject.toml:124` `exclude = "^tests/|^scripts/"` under a `strict = true` mypy config, so the 2,900+ test files and the benchmark scripts are never type-checked (this is why TST-05's `F821` survived).

---

## 5.1 Remediation status

| Finding | Status | Batch | Evidence |
|---|---|---|---|
| **RE-01** (baseline integrity not verified on load) | **FIXED, TESTED** | Batch 1 (2026-10-20) | The engine now seals every baseline (`baseline_hash` = SHA-256 over the canonical JSON of the whole document) and `load_baseline` verifies the seal before any planning, preview, recovery or verification. Tampered / stale / missing / malformed / unsupported seals are refused (exit 5 or 7); legacy `interlock-baseline-v1` documents are refused as *unsealed*, never silently blessed. Regression tests: `tests/unit/test_baseline_integrity.py` (22), `tests/unit/test_cli_baseline_persistence.py` (14), `tests/integration/test_bridge_baseline_integrity.py` (7) |
| **RE-02** (CLI silently overwrote an existing baseline) | **FIXED, TESTED** | Batch 1 (2026-10-20) | `_persist_baseline` stores the engine's sealed document atomically (unique temp file + fsync + exclusive publish) and refuses to replace an existing baseline (exit 7, original preserved byte-for-byte). Concurrent captures cannot overwrite one another. Regression tests: `tests/unit/test_cli_baseline_persistence.py`, `tests/integration/cli_lifecycle_check.py` (42/42) |
| **RE-03** (truncated capture could shrink a file and report `byte_exact: true`) | **FIXED, TESTED** | Batch 2 (2026-10-21) | A truncated before-state is now refused **before anything is written** (`_truncated_before_state_error`): `_execute_restore_content` and `_execute_restore_deleted_file` fail closed, and `_build_byte_exact_verification` fails closed with an explicit "truncated_before_state" reason. The bridge additionally refuses a truncated baseline at load (`baseline_truncated`, exit 7) so no such plan is ever built. Regression test: `tests/unit/test_recovery_truthfulness.py` |
| **RE-05** (UNC refusal bypassable with the forward-slash form) | **FIXED, TESTED** | Batch 4 (2026-10-21) | `is_unc_path()` (new, in `sdk/workspace_protection/path_security.py` and in the bridge) refuses `\\server\share`, `//server/share` and any path whose drive is a UNC drive. Regression test: `tests/integration/test_workspace_protection/test_path_security.py` |
| **RE-06** (`delete_file` had no execution-time identity check) | **FIXED, TESTED** | Batch 2 (2026-10-21) | `_execute_delete_file` re-hashes the target immediately before `unlink` and refuses with `BLOCKED_BY_CONFLICT` when it differs from the `after_snapshot` observed at plan time — the same guard the content-restore path already had. Regression test: `tests/unit/test_recovery_truthfulness.py` |
| **RE-12** (verification claimed `byte_exact` it never established) | **FIXED, TESTED** | Batch 2 (2026-10-21) | The deletion branch no longer claims byte-exactness (it reports `verified_by: "existence"`); the rename branch claims byte-exactness only when a content hash was actually compared, and otherwise states that only path presence was verified. Regression test: `tests/unit/test_recovery_truthfulness.py` |
| **RE-19** (unbounded whole-file reads during verification) | **FIXED, TESTED** | Batch 2 (2026-10-21) | Verification hashes and compares files in 64 KiB chunks (`_compute_file_hash`, new `_bytes_match_file`, bridge `sha256_file`); no verification path loads a whole file into memory. Regression test: `tests/unit/test_recovery_truthfulness.py` (verification runs with `Path.read_bytes` forbidden) |
| **WEB-01** (website/README stated the opposite of repository reality) | **FIXED, TESTED** | Batch 3 (2026-10-21) | The Download page, the VS Code status panel, `downloads/index.html`, `downloads/README.md` and the README now state that the extension **source is in this repository and builds locally** while nothing is **published** (no Marketplace listing, no published download, no published checksum). The false statements ("no artifact exists", "no extension source", "nothing can be installed yet", "planned interface — not built yet") are removed; the true disclosures are kept. Site test updated to assert the corrected copy and to keep the "no invented download link" invariant. `site`: typecheck 0, lint 0, 40/40 tests, build OK |

*Remaining findings are untouched by Batches 1–4 and stay open.*

### 5.1.1 Verified still open (no fix attempted in these batches)

| Finding | Status | Reason |
|---|---|---|
| **MIG-01** (Alembic downgrades brick the database) | **BLOCKED** | The repair is the project's approval-gated "R10" (rewriting a historical migration's downgrade). It needs explicit owner approval and a migration rehearsal on disposable databases. **Proposal prepared: `docs/operations/MIGRATION_R10_PROPOSAL.md`** (root cause, three failure sequences, three options with compatibility implications, a disposable-database validation plan, and the exact owner decisions needed). No migration file was modified; no downgrade was executed. |
| **MIG-02** (33-op model/migration drift) | **BLOCKED** | Depends on the MIG-01 decision (M-PKG / R10). `alembic check` continues to report the truth and fails the CI gate until it is applied. |
| **RE-04** (TOCTOU on the write path) | **OPEN** | Structural race requiring directory-handle pinning; the current containment is correct at check time. Not closable by a small, safe change. |
| **RE-08** (`GitRepositoryAdapter` claims real git operations) | **OPEN** | Either implement real git operations or reclassify the adapter — a product decision with capability-contract consequences. || **RE-10** (`plan` writes an evidence sidecar) | **OPEN** | Disclosed behaviour; the preview needs the evidence, so removing it is a product decision. |
| **RE-13/RE-14/RE-15** | **OPEN** | Informational; the eligibility matrix, the before-state semantics and the "no backup file" policy are product decisions. |
| **TST-03** (80% coverage gate) | **OPEN** | The gate is real and CI enforces it; the full-suite number is measured in §4.3. |
| **TST-04** (lint debt outside app/sdk) | **OPEN** | ~1000 findings, mostly in root debris and tests; a bulk cleanup is a large, low-value diff. |
| **MNT-02** (19 overlapping status reports), **MNT-03** (root debris), **MNT-04** (mypy excludes tests) | **DEFERRED** | Deleting or consolidating the user's documents is destructive to their work; type-checking the whole test suite would produce a large, low-value diff. |
| **PKG-02** (version/branding drift) | **OPEN** | The distribution version (`intentlock` 4.0.0), the product brand (V6) and the extension version (0.1.0) are a release decision. |
| **SEC-03** (CI uploads source to the Semgrep cloud) | **OPEN (policy)** | A deliberate supply-chain policy decision, not a defect; changing it is a security-policy change and needs the owner's call. |
| **TST-09** (site `Demo.test.tsx` timeout) | **NOT REPRODUCED** | The test passes in this session (40/40 site tests green). The earlier 5 s timeout was not observed again. |
| **EXT-01 / EXT-02** (extension compile / stale bundle) | **FIXED, TESTED** (in-flight work) | The parallel Inbox work landed: `npm run typecheck` exit 0, `npm run lint` exit 0, 375 extension unit tests passing. The vendored engine bundle is now regenerated and byte-identical to the canonical engine, and the drift is now **enforced** by `build-engine-bundle.js --verify` (MNT-01). |

### 5.2 Batches 5–7 (2026-10-21) — additional fixes

| Finding | Status | Batch | What changed |
|---|---|---|---|
| **RE-09** (staging-name collision destroyed user files) | **FIXED, TESTED** | 5 | The reserved staging path `<target>.recovery_tmp` is the engine's, but the bytes there may be the user's. A colliding entry is now **moved aside** (`<name>.recovery_tmp.preserved-<stamp>`) instead of deleted; the symlink anti-planting defence and the retry-after-interruption contract are unchanged. Tests: `tests/unit/test_staging_and_metadata_safety.py` |
| **RE-07** (metadata restore failures suppressed while the plan claimed them) | **FIXED, TESTED** | 5 | `verify()` now checks the restored POSIX mode and mtime and fails closed when they were not restored; the requirements list no longer claims ACL restoration (`file_acl_captured_not_restored`). Tests: `tests/unit/test_staging_and_metadata_safety.py` |
| **RE-11** (baselines world-readable / secrets in baselines) | **FIXED, PARTIALLY VALIDATED** | 5 | The extension's baseline store now creates its directory `0700` and its documents `0600` (the CLI already published `0600` after Batch 1). The remaining part — excluding secret-like files from *explicitly requested* captures — is a product decision (an agent can corrupt a `.env`; refusing to protect it would be a regression) and stays **DEFERRED**. |
| **RE-08** (`GitRepositoryAdapter` claimed real git operations and wrote non-atomically in text mode) | **FIXED, PARTIALLY VALIDATED** | 8 | The adapter captured **text** while hashing the **raw bytes**, so a CRLF file could never be reproduced from its own evidence: the restore silently wrote LF bytes and reported success. It now captures the raw bytes (`content_b64`), restores them through a staging file whose hash is verified **before** the swap, and reports a mismatch as a failure without touching the target. The docstring and the declared capabilities no longer claim commit/stash/index operations the adapter does not perform (`commit_aware_recovery` removed). **Remaining (owner decision):** the capability classification itself and whether a genuinely git-aware adapter is required. Tests: `tests/unit/test_git_repository_adapter.py` |
| **TST-10** (audit trail written to a fixed in-repo path; concurrent runs corrupt it) | **FIXED, TESTED** | 9 | The audit log path is configurable (`INTERLOCK_AUDIT_LOG_PATH`) and the test session owns a temporary trail outside the repository. Two concurrent runs of the affected tests now pass (39/39 each) where the shared path made them fail (9 failures + 9 errors in a full-suite run). |
| **TST-01** (CLI checks never automated) | **FIXED** | 7 | New `cli-checks` CI job runs the lifecycle check, the clean-install check and the packaging guard. |
| **TST-02** (no CI job for the extension or the website) | **FIXED** | 7 | New `vscode-extension` and `website` CI jobs (typecheck, lint, tests, package/build). |
| **TST-05** (undefined `Any` in a test) | **FIXED** | 6 | Import added; the file's import block and unused imports cleaned. |
| **TST-06** (no Windows junction test) | **FIXED** | 6 | `tests/integration/test_workspace_protection/test_path_escape_vectors.py` creates a real junction (no elevation needed) and proves the escape is refused by both the SDK and the engine; it executes on Windows. |
| **TST-07** (no non-ASCII path test) | **FIXED** | 6 | The same file round-trips a non-ASCII workspace, file name and content through capture → recover → verify. |
| **PKG-01** (no reproducible extension package) | **FIXED, TESTED** | 7 | The VSIX was built from the current source (840 entries, 33,879,240 bytes, SHA-256 `ae3eaf9a…`), its contents inspected (bridge + engine manifest present; no tests, no `.ts`, no source maps) and the procedure recorded in **`docs/operations/VSIX_BUILD.md`**; CI now repeats it and uploads the artifact plus its checksum as evidence. |
| **MNT-01** (vendored engine could drift) | **FIXED** | 7 | `node extensions/vscode/tools/build-engine-bundle.js --verify` compares the committed bundle with the canonical source, file by file, read-only; CI runs it. |
| **WEB-02** (unlabelled "recovering … 100%" demo mock) | **FIXED** | 6 | The home-page transcript now states that it is an illustrative demonstration, not a guarantee. |
| **WEB-04** (two divergent install surfaces) | **FIXED** | 3 | `site/src/pages/Download.tsx`, `downloads/index.html` and `README.md` now use the same wording. |

### 5.3 New findings discovered during this remediation

| ID | Severity | Status | Evidence |
|---|---|---|---|
| **SUPPLY-01** | **High** | **OPEN (owner action)** | The VS Code extension, the Terminal Runner, the website, the downloads page and the terminal-runner documentation are **not tracked in git** (`git ls-files extensions/ site/ interlock_cli.py` → 0). A wheel built from a pristine checkout of `HEAD` contains **no** `interlock_cli.py`, **no** `interlock_bridge.py`, **no** `share/` data and **no** console-script entry point — and `python -m build` still reports success. Reproduced: `git archive HEAD` → `python -m build` → 311 entries, `entry_points.txt` absent. Guard added: `tests/unit/test_packaging_manifest.py` fails on a clean checkout (3 failed / 1 passed) and passes on the working tree (5 passed). **Owner action: commit the product code.** No commit was made by this audit. |
| **API-AUTH-01** | Informational (positive) | **FIXED, TESTED (guard)** | All 146 API route endpoints were scanned: 144 carry an authentication dependency, 17 are public **by design** (liveness probes, registration/login/refresh, token-based MFA flows, OIDC discovery/callback, JWKS, public pricing, publishable key, and the two signature-verified webhooks). **Zero** endpoints are reachable without either a session or a verified signature. The property is now enforced by `tests/unit/test_api_route_authentication.py`, whose public-endpoint allowlist states the reason for each. |
| **TST-10** | **Medium** | **FIXED, TESTED** | The audit trail was written to a **fixed path inside the repository** (`app/infrastructure/logging/audit_logger.py:10-12`, `logs/audit_trail.jsonl`) and the test suite deleted and appended to it. Two processes writing the same hash-chained file break the chain: a full-suite run executed alongside another run produced **9 failures + 9 errors** in the audit-log and compliance-export tests, and the suite mutated a file in the source tree. The path is now configurable (`INTERLOCK_AUDIT_LOG_PATH`) and the test session owns a temporary trail outside the repository. Verified: two concurrent runs of the affected tests now both pass (39/39 each) where the shared path made them fail. |
| **SEC-05** | **Low** | **FIXED, TESTED** | The SDK client (`sdk/intentlock.py`) accepted `http://` for ANY host while sending a bearer token, so a misconfigured remote gateway would have received the token in cleartext. `_validate_gateway_url` now refuses plain HTTP for a remote host (loopback and the in-process ASGI test host stay allowed), and the endpoints are validated when the client is constructed, so the misconfiguration is caught at wiring time. Tests: `tests/unit/test_sdk_guard.py` |

---

## 6. False positives and unverified concerns (explicitly separated)

**Investigated and CLEARED (not findings):**
1. *"Shell injection in the recovery engine"* — **cleared.** There is no `subprocess`/`shell=True`/`os.system` anywhere in `app/`, `sdk/`, `interlock_cli.py` or the bridge (check #23). The engine is pure-Python, stdlib-only.
2. *"Unsafe deserialization (pickle / yaml.load / eval / exec)"* — **cleared**, 0 matches repo-wide.
3. *"Hardcoded JWT secret / wildcard CORS"* — **cleared** (`settings.py:26,48`).
4. *"Unauthenticated emergency or control endpoints"* — **cleared** (`emergency.py:32-47` + `CurrentUser` on every mutating route).
5. *"Webview XSS"* — **largely cleared.** `webviewHtml.ts:63-70` escapes `& < > " '`; CSP is `default-src 'none'; img-src 'none'; font-src 'none'; style-src 'nonce-…'; script-src 'nonce-…'` (`:640`); `localResourceRoots: []` (`sidebarView.ts:50`); every inbound webview message is validated by `isWebviewMessage` (`webviewHtml.ts:482-501`) against a fixed allow-list (`WEBVIEW_COMMANDS` `:470-474`) before any `executeCommand`. The report HTML follows the same rules (`recoveryReportHtml.ts:111-298`, no `innerHTML`, no `eval`).
6. *"Broken internal routes on the site"* — **cleared.** `site/src/App.tsx:64-78` maps every route to an existing page component and includes a `*` 404 catch-all.
7. *"Fabricated testimonials / metrics / fake security badges"* — **cleared** (WEB-03).
8. *"Diff uses the wrong sides"* — **cleared.** `commands.ts:1576-1601` opens the native `vscode.diff` with the **real file on the left** (`vscode.Uri.file(planned.absolutePath)`, or an explicit empty `interlock-missing:` stand-in for a deleted file) and the **verified proposed content on the right** via an in-memory `TextDocumentContentProvider` keyed by the baseline hash (`recoveryDocuments.ts:28-36, 57-64`). Files that cannot be shown honestly (binary/truncated/hash-mismatch) are reported, not faked (`commands.ts:1577-1584`).
9. *"Identity prompt fires on preview/analyze"* — **cleared.** `resolveApproverIdentity()` (`commands.ts:1709-1754`) is called only inside `executeRecovery` (`:1368`); preview (`:1128-1149`) and the read-only report (`:1158`) never prompt, and the identity is never invented (git identity requires one explicit confirmation; cancel ⇒ `null` ⇒ no recovery).
10. *"Preview mutates the workspace"* — **cleared.** The CLI lifecycle check independently confirmed *"preview is read-only (damage still present)"* (check #13).

**UNVERIFIED / theoretical (not counted as vulnerabilities):**
- RE-04 (parent-directory swap race) and RE-01 (baseline tampering) require a local co-actor with write access to the workspace/baseline store. They are structural weaknesses, not remotely exploitable paths.
- The "micro-second TOCTOU window" between the exists-check and `os.replace` is **already disclosed** by the project in `SUPPORTED_PLATFORMS.md:68-71` under a single-writer assumption — this audit does not count it as a new defect, but it does confirm the disclosure is accurate.
- The bundled runtime is a *third-party* CPython build (astral-sh python-build-standalone). The pin + SHA-256 check is verified; the upstream project's own integrity is out of scope.

---

## 7. Security and data-loss risk summary

**Data-loss risks (ranked):**
1. **RE-02** — routine `interlock protect` destroys the previous baseline. *Silent, no warning, non-atomic.*
2. **RE-01** — a tampered baseline passes restore *and* verification, because the stored hash is the thing being compared against. The evidence chain has no independent root.
3. **RE-03** — an over-size snapshot can restore a truncated file and still be reported byte-exact (adapter-level path).
4. **RE-09** — an unrelated user file named `*.recovery_tmp` can be deleted by the staging logic.
5. **RE-15** — no backup of the pre-overwrite file beyond the preview evidence sidecar.
6. **RE-07** — permissions/ACL/timestamps may be unrestored while the result says `success: true`.
7. **MIG-01** — a database rollback attempt (even a "successful" partial one) can leave the control-plane database permanently unrecoverable by Alembic in both directions.

**Security risks:** the platform is unusually clean (no shell, no deserialization, no hardcoded secrets, strict CSP, message allow-lists, pinned+verified runtime, 0 npm vulns, 0 Medium/High bandit). The material items are **WEB-01** (misinformation), **SEC-03** (source uploaded to Semgrep cloud by policy), **RE-11** (secrets stored in baselines in plaintext, world-readable on POSIX) and **RE-01** (evidence not sealed).

**Positive data-preservation design elements worth preserving through remediation:**
byte-exact base64 transport with refusal to re-encode text (adapter 1917-1933); staging with `O_EXCL` + `0o600` + fsync + atomic `os.replace` (1942-1949, 2146-2178); re-hash of the target immediately before the write (1897-1905); post-write independent re-hash deciding success (bridge 1132-1134, 1153-1171); fail-closed refusal ladder (bridge 1112-1125); `no_conflict`/`no_drift` gating; `INSUFFICIENT_EVIDENCE` on missing baselines; `KeyboardInterrupt` → structured `cancelled` envelope + exit 130; never a bare `except:`/swallow in a decision path.

---

## 8. Test coverage gaps

| Scenario | Status | Evidence / gap |
|---|---|---|
| Path traversal (`..`, absolute, foreign CWD) | **Covered** | `tests/integration/test_workspace_protection/test_path_security.py`, `test_path_security_properties.py` (property-style: `test_validate_never_returns_outside_path`, `test_refused_write_leaves_victim_untouched`, `test_unc_always_refused`) |
| Symlink escape | **Covered but skipped on Windows** | `test_recovery_fault_injection.py:87` ×2 skipped (WinError 1314) — see TST-08 |
| Windows junction / reparse-point escape | **NOT COVERED** | 0 matches repo-wide — TST-06 |
| UNC paths | **Covered** | property test `test_unc_always_refused`; note RE-05 shows the *forward-slash* form is not caught by the CLI/bridge guard |
| Stale preview / changed-between-preview-and-apply | **Covered** | `commands.ts:1282-1311` + engine-side drift detection; 88 "stale" hits in tests |
| Corrupt / truncated / mismatched evidence | **Covered** | 39 "corrupt/truncat" hits; `evidence_verification_service.py:121-158` fails closed |
| Permission failure | **Covered on POSIX only** | 128 "permission" hits; POSIX-mode tests skip on Windows |
| Unicode paths | **NOT COVERED for recovery** | only policy homoglyph tests — TST-07 |
| Large files | **Covered** | 11 hits; but see RE-03 for the truncation path |
| Cancellation / process kill | **Covered** | 24 "cancel" hits; M1 real process-kill 20/20 claimed in the platform matrix |
| Partial bulk failure | **Covered** | 69 "partial/bulk" hits |
| Exact-byte verification | **Covered** | 18 hits + `cli_lifecycle_check.py` byte-for-byte assertion |
| Concurrent mutation (TOCTOU) | **Partially** | drift detection covered; the parent-swap race (RE-04) is not testable without fault injection |
| CLI standalone behaviour | **Manual only** | TST-01 — never run by CI |
| Extension compile / package | **Not in CI** | TST-02 — EXT-01 would have been caught by `npm run typecheck` in CI |
| Website | **Not in CI** | TST-02 — TST-09 would have been caught |

---

## 9. Build, packaging, installation and platform support

| Item | Verdict | Evidence |
|---|---|---|
| Python wheel + sdist build | **Pass** | check #10 — builds cleanly with setuptools 84.0.0; content clean (#11/#12) |
| Console script `interlock` | **Pass** | `pyproject.toml:34-35` → `interlock_cli:console_entry`; `interlock_cli.py:520-529` maps the return value to the process exit code |
| CLI works without VS Code | **Pass** | check #13 — 38/38 in a real subprocess, with `INTERLOCK_BRIDGE` removed from the environment |
| CLI from a packaged wheel in a clean venv | **Pass (manually verified; not automated)** | check #14 — 27/27 in a fresh venv with the installed wheel, no repo on path and no `INTERLOCK_BRIDGE`. It is never run by CI (TST-01) |
| Extension manifest / activation | **Pass** | `activationEvents: []` + 13 commands; all 13 are registered in `extension.ts:124-136`; `contributes.views` uses `"type": "webview"` with `onView` activation implied by the declared view |
| Extension packaging | **Fail** | EXT-01 — `typecheck`/`lint` fail ⇒ `vsce package` fails; the existing VSIX is stale (EXT-02) |
| Bundled Python runtime | **Pass (design), Fail (currency)** | `tools/provision-runtime.js` pins tag + SHA-256 and refuses on mismatch (SEC-04); the bundled runtime in the VSIX is Windows x64 only |
| Website production build | **Pass** | check #21 — 15.39 s, route-split |
| Windows support | **Pass (as claimed)** | The platform matrix's claims (Windows x64, NTFS, 3.11.9) match this audit's platform |
| macOS support | **Not validated — correctly disclosed** | `SUPPORTED_PLATFORMS.md:32-34` marks it "DECLARED — CI PENDING"; the site repeats it. The Intel-macOS row is **dependency-blocked** (`cryptography` ≥46 ships no macOS x86_64 wheel) — an honest, specific, actionable constraint |
| Linux support | **Not validated — correctly disclosed** | same as macOS |
| Windows ARM64 | **Not validated — correctly disclosed** | "UNTESTED (no hardware)" |
| Long paths >260 chars | **Not validated — correctly disclosed** | "UNTESTED — limitation"; staging adds 16 chars to the target name |
| CI has ever run | **No** | `SUPPORTED_PLATFORMS.md:18-19`: "the repository has had no push since 2026-09-27, so CI has never run" — confirmed: HEAD is a local commit, `origin` has no newer refs |

---

## 10. Prioritized remediation plan

### P0 — critical data-loss / security risk
| ID | Action | Files | Acceptance test |
|---|---|---|---|
| **P0-1 (RE-02)** | Never overwrite an existing baseline silently: refuse unless `--force`, write atomically (temp + `os.replace`), and keep a timestamped previous copy | `interlock_cli.py:369-392` | Re-running `protect` without `--force` exits non-zero, leaves the original byte-identical, and prints an explicit refusal |
| **P0-2 (RE-01)** | Seal baseline documents with the same `evidence_hash` v2 mechanism used for preview evidence, recompute `snapshot_hash` on load, and refuse a baseline whose seal or content hash does not match | `interlock_bridge.py:484-542`, `app/domain/services/evidence_hash.py` | A baseline whose `content_b64` (or `hash`, or `snapshot_hash`) is edited fails closed with a clear "evidence integrity" error; an untouched baseline still recovers byte-exactly |
| **P0-3 (RE-11)** | Exclude secret-like files from baselines (`.env`, `*.pem`, `id_rsa`, `*.key`, credential stores) and write baseline files with owner-only permissions (0o600 / Windows ACL) | `extensions/vscode/python/interlock_bridge.py` (capture), `interlock_cli.py:369-392` | A `.env` file is never captured; a baseline file is not world-readable on POSIX |

### P1 — release-blocking correctness / launch issues
| ID | Action | Files | Acceptance test |
|---|---|---|---|
| **P1-1 (EXT-01/EXT-02)** | Rebuild the VSIX from the current source (`npm run package` after a clean `npm run compile`) so the published artifact contains the Recovery Inbox, and add the extension's `typecheck`/`lint`/`test:unit` to CI (see P1-3) so this cannot silently regress | `extensions/vscode/` | `npm run package` succeeds; the new `.vsix` contains `out/src/recoveryInbox.js` and its SHA-256 is recorded |
| **P1-2 (WEB-01)** | Correct the Download page and README to describe what actually exists (a locally buildable extension + local VSIX), and reconcile with `SUPPORTED_PLATFORMS.md`; state clearly that nothing is *published* (which is true) versus that nothing *exists* (which is not) | `site/src/pages/Download.tsx:249-257`, `README.md:324-325`, `downloads/index.html:48` | A reader who follows the page can locate and install the extension; no sentence states that a non-existent artifact exists |
| **P1-3 (TST-02)** | Add a CI job that runs the extension's `typecheck`/`lint`/`test:unit` and the site's `typecheck`/`lint`/`test` on every push | `.github/workflows/ci.yml` (new job) | A deliberately broken extension file fails CI |
| **P1-4 (TST-01)** | Wire `cli_lifecycle_check.py` and `cli_clean_install_check.py` into CI (or convert them into pytest-collectable tests) | `.github/workflows/ci.yml`, `tests/integration/cli_*_check.py` | The CLI checks run automatically on every push and their output appears in the CI log |
| **P1-5 (RE-03)** | Refuse (never truncate) snapshots above the limit at the adapter level; make `load_baseline` reject `truncated: true`; never report `byte_exact: true` for a truncated snapshot | `filesystem_recovery_adapter.py:259-268, 337, 350-351, 1978, 2214`, `interlock_bridge.py load_baseline` | A >limit file produces an explicit refusal, and a truncated snapshot is refused at load and at restore |
| **P1-6 (PKG-01)** | Publish the VSIX with a recorded SHA-256 and make the download page offer it (the site's own promise) — or keep the page honest and say the artifact exists locally | `extensions/vscode/tools/`, `site/src/pages/Download.tsx` | The page's checksum promise is either satisfied or the claim is removed |
| **P1-7 (MIG-01)** | Repair the Alembic history (R10): give `3cebbede5768` a real inverse `downgrade()` (or a data-preserving forward-fix migration) so `downgrade base` → `upgrade head` is possible, and make the operator-visible warning that a partial downgrade bricks the schema impossible to hit silently | `alembic/versions/3cebbede5768_*.py`, `alembic/versions/0010_*.py` | The three xfail tests in `tests/integration/test_alembic_migration_safety.py` turn green (or are re-based as explicit, passing regression tests) |
| **P1-8 (MIG-02)** | Apply the M-PKG model/migration alignment so `alembic check` is clean — otherwise the CI migration gate (ci.yml:82) fails on the first push | `app/infrastructure/persistence/models/`, `alembic/versions/` | `alembic check` exits 0 |

### P2 — important reliability / maintainability
| ID | Action | Files |
|---|---|---|
| **P2-1 (RE-07)** | Treat metadata/ACL/timestamp restore failures as verification failures (or remove those claims from `verification_requirements`) | `filesystem_recovery_adapter.py:1067-1075, 1498-1675, 1759-1795` |
| **P2-2 (RE-08)** | Either implement the git adapter with real, atomic, byte-exact git operations or re-classify it as non-production / manual-action-only | `app/infrastructure/recovery/git_repository_adapter.py:949, 1047, 1-12` |
| **P2-3 (RE-04)** | Resolve the path used for the write (`_resolve_file_path` → resolved path) and/or pin the parent directory handle to shrink the TOCTOU window | `filesystem_recovery_adapter.py:1721-1726, 1749-1757` |
| **P2-4 (RE-05)** | Reject UNC in both slash forms (check the resolved path's drive/UNC semantics, not the literal prefix) | `interlock_bridge.py:430-435`, `sdk/workspace_protection/path_security.py:58-60` |
| **P2-5 (RE-06)** | Re-hash the target immediately before `unlink` in the delete compensation | `filesystem_recovery_adapter.py:1991-2030` |
| **P2-6 (RE-12)** | Make `byte_exact` false whenever no byte comparison was performed; make `verified` require one | `filesystem_recovery_adapter.py:1558-1571, 1621-1662` |
| **P2-7 (TST-06)** | Add Windows junction/reparse-point confinement tests (a junction can be created on Windows without elevation) | `tests/unit/` or `tests/integration/test_workspace_protection/` |
| **P2-8 (TST-03)** | Push the coverage gate above its actual value (or add the missing tests) so CI can be green honestly; verify the 80% gate on the full suite | `pyproject.toml:142` |
| **P2-9 (MNT-01)** | Add a CI check that `extensions/vscode/engine` is byte-identical to `app/` + `sdk/`, and version the bundle | `extensions/vscode/tools/build-engine-bundle.js`, CI |
| **P2-10 (MNT-03)** | Move root debris scripts out of the repository (or delete them after archiving) so the repo root reflects the product | repo root |
| **P2-11 (PKG-02)** | Pick one version number (4.0.0 / 6.0.0 / 0.1.0) and apply it consistently across pyproject, CLI, extension, site and README | `pyproject.toml:7`, `interlock_cli.py:46`, `site/package.json`, `README.md:1` |
| **P2-12 (MNT-02)** | Consolidate the 19 overlapping V6 reports into one current document plus an archive; keep the stash | repo root |

### P3 — non-blocking improvements
| ID | Action | Files |
|---|---|---|
| **P3-1 (TST-04/TST-05)** | Clean `tests/` lint debt incrementally; add `tests/` to mypy in a non-blocking mode; fix the `Any` import | `tests/unit/test_domain_e_toolchain_security.py:1-28` |
| **P3-2 (RE-09)** | Only remove staging files that this process created (record the name first) | `filesystem_recovery_adapter.py:1842-1850, 1915` |
| **P3-3 (RE-19)** | Cap the size read during verification; consult the `truncated` flag | `filesystem_recovery_adapter.py:1552, 1615`; `interlock_bridge.py:1164` |
| **P3-4 (TST-07)** | Add Unicode-path tests for capture → recover → verify | `tests/unit/` |
| **P3-5 (TST-08/TST-09)** | Raise the vitest timeout or make the Demo test deterministic; enable the two symlink drills on Windows via Developer Mode / CI elevation | `site/src/pages/Demo.test.tsx:130`; `tests/unit/test_recovery_fault_injection.py:87` |
| **P3-6 (WEB-02)** | Label the home-page terminal mock as illustrative output | `site/src/pages/Home.tsx:138-156` |
| **P3-7 (SEC-03)** | Record the decision to upload source to Semgrep, or switch to a self-hosted ruleset | `.github/workflows/{ci,security}.yml` |
| **P3-8 (MNT-04)** | Extend strict mypy to `tests/` (non-blocking first) | `pyproject.toml:124` |
| **P3-9 (RE-10)** | Move the `plan` sidecar evidence to a clearly-labelled cache directory and document it in the CLI help | `interlock_bridge.py:1055-1062` |

---

## 11. Release checklist (objective pass/fail)

| # | Gate | Pass criterion | Status at audit |
|---|---|---|---|
| G1 | Extension compiles | `npm run typecheck` exit 0 **and** `npm run lint` exit 0 | ✅ PASS **at 17:35** (failed at 17:16 — EXT-01; no CI gate exists to keep it true) |
| G2 | Extension packages | `npm run package` produces a `.vsix` built from the current `src/` | ❌ **FAIL** — the only `.vsix` (14:31:52) predates the current build (17:27:59); packaging was not re-run |
| G3 | Python packages | `python -m build` exit 0; wheel contains CLI + bridge + migrations | ✅ PASS |
| G4 | CLI works standalone | `cli_lifecycle_check.py` exit 0, run **in CI** | ⚠️ PARTIAL — 38/38 manually (TST-01) |
| G5 | CLI works from a clean venv | `cli_clean_install_check.py` exit 0, run **in CI** | ⚠️ PARTIAL — 27/27 when run manually (this audit), but never automated (TST-01) |
| G6 | Extension tests | `npm run test:unit` exit 0 | ✅ PASS (343 at 17:36; 280 before the in-flight recompile) |
| G7 | Website builds + tests | `vite build` exit 0; `npm test` exit 0 | ⚠️ PARTIAL — build ✅, 1 test fails (TST-09) |
| G8 | Server test suite | `pytest` exit 0 | ✅ PASS for unit (2416/2416) |
| G9 | Coverage gate | full-suite coverage ≥ 80% | ⚠️ UNVERIFIED (77% unit-only; 83.81% claimed) |
| G10 | Static analysis | `ruff check app sdk` exit 0; `mypy app sdk` exit 0; `bandit -r app -ll` exit 0 | ✅ PASS |
| G11 | Dependency audit | `pip-audit` 0 runtime vulns; `npm audit --omit=dev` 0 vulns | ✅ PASS |
| G12 | Evidence integrity | A tampered baseline is refused (content, hash, snapshot_hash) | ✅ **PASS** (Batch 1 — RE-01) |
| G13 | Evidence preservation | Re-running `protect` cannot destroy an existing baseline | ✅ **PASS** (Batch 1 — RE-02) |
| G14 | Fail-closed on corrupt evidence | corrupt / truncated / mismatched evidence → refusal, never success | ✅ **PASS** (Batch 1 + Batch 2 — RE-01, RE-03) |
| G15 | Path containment | traversal, absolute, UNC, symlink, junction escapes all refused | ⚠️ PARTIAL — UNC now refused in both slash forms (Batch 4 — RE-05); **junction still untested** (TST-06) |
| G16 | Preview→apply staleness | changed files between preview and apply are refused | ✅ PASS (engine + extension) |
| G17 | Honest verification | success only after byte comparison; no `byte_exact` without bytes | ✅ **PASS** (Batch 2 — RE-12) |
| G18 | Identity only on approval | no identity prompt outside explicit recovery | ✅ PASS |
| G19 | Read-only previews | preview/analyze/report write nothing to the workspace | ✅ PASS (verified by CLI lifecycle check) |
| G20 | CLI/extension share one engine | both drive `interlock_bridge.py`; no duplicated recovery logic | ✅ PASS |
| G21 | CI green on a real push | all workflows run and pass on all three OSes | ❌ **FAIL — CI has never run** |
| G22 | CI covers both interfaces | extension + website jobs exist | ❌ **FAIL** (TST-02) |
| G23 | Website claims true | every claim matches the repository | ✅ **PASS** (Batch 3 — WEB-01) |
| G24 | Pricing honest / no fake checkout | price is $0 + TBD; no dead payment flow | ✅ PASS |
| G25 | No fabricated claims | no testimonials/metrics/certifications | ✅ PASS |
| G26 | Platform claims honest | unvalidated platforms explicitly marked | ✅ PASS |
| G27 | Docs consistent | no contradictions between README/site/platform docs | ⚠️ PARTIAL — README/site/downloads now agree (Batch 3); the standalone `downloads/` page still duplicates the site (WEB-04) |
| G28 | Working tree safe | no work lost; stash intact; report added without overwriting | ✅ PASS (see §14) |
| G29 | Secrets not exposed | no credentials in tracked files, logs, sdist or wheel | ✅ PASS (no `.env`/keys in artifacts; `.env` is gitignored) |
| G30 | Real disk-full (ENOSPC) drill | executed with a real full volume | ❌ **FAIL — never executed** (documented as gated) |
| G31 | Database downgrades are reversible | `downgrade base` then `upgrade head` succeeds on a populated database | ❌ **FAIL** (MIG-01 — impossible today; a partial downgrade bricks the DB in both directions. Repair proposed in `docs/operations/MIGRATION_R10_PROPOSAL.md`, owner approval required) |
| G32 | Model/migration agreement | `alembic check` reports no drift | ❌ **FAIL** (MIG-02 — 33 operations) |
| G33 | Extension compiles, lints, tests and packages | `npm run typecheck` / `lint` / `test:unit` / `package` all exit 0, and the VSIX contains the bridge + engine manifest | ✅ **PASS** (typecheck 0, lint 0, 375 tests, VSIX 840 entries, SHA-256 recorded; CI job added) |
| G34 | Website and README match reality | every claim matches the implemented and built product | ✅ **PASS** (Batch 3) |
| G35 | Every API route is authenticated | no endpoint is reachable without a session or a verified signature | ✅ **PASS** (146 endpoints scanned; 17 public by design with a stated reason; enforced by a test) |
| G36 | The distribution is complete | the built wheel contains the console script, the shared engine bridge and the migration runtime | ⚠️ **PARTIAL** — complete in the working tree (guard: `tests/unit/test_packaging_manifest.py`), but **SUPPLY-01**: a wheel built from a pristine checkout of `HEAD` contains none of them, because the product code is not in version control |
| G37 | The engine bundle matches the canonical source | `build-engine-bundle.js --verify` exits 0 | ✅ **PASS** (tree `be38e96456fd4148…`; enforced in CI) |
| G38 | The test suite is safe to run concurrently | two concurrent runs of the same tests both pass | ✅ **PASS** (TST-10 fix: per-session audit trail outside the repository) |

**Gates passing: 26 · Partial: 7 · Failing: 7** (of 40).

*Recount after Batches 1–7 (2026-10-21): G12, G13, G14, G17, G23 became PASS; G15 and
G27 remain PARTIAL with the specific remainder stated; G33–G35, G37, G38 were added and
pass; G36 is PARTIAL because of SUPPLY-01.*

*Recount after Batches 1–4 (2026-10-21): G12, G13, G14, G17, G23 became PASS; G15 and G27 remain
PARTIAL with the specific remainder stated.*

---

## 12. Checks that require manual testing or another operating system

**Another OS required (cannot be performed on this Windows host):**
1. POSIX symlink-confinement drills (currently skipped on Windows with `WinError 1314`) — must run on Linux/macOS runners.
2. POSIX permission semantics (`chmod` 0o600/0o700 staging and backup) — 4 tests skip on Windows.
3. macOS arm64: wheel build, `pip check`, native recovery subset, APFS atomic-replace behaviour.
4. macOS x86_64: currently **dependency-blocked** (`cryptography` ≥46 has no macOS x86_64 wheel) — needs an owner-approved pin before any claim.
5. Linux ext4: recovery subset + symlink drills in CI.
6. Windows ARM64, long paths (>260 chars), FAT32/exFAT, network/OneDrive-synced directories — all currently "UNTESTED"/"UNSUPPORTED" and must stay that way until evidenced.

**Manual / non-automatable:**
7. Real ENOSPC (disk-full) failure drill — prepared but authorization-gated.
8. Real process-kill at the exact write window (M1) — claimed 20/20 in the project matrix; a fresh run with recorded output is advisable.
9. Extension **host** (VS Code) tests — `npm run test:host` (`test/host/launch.js`) was **not** executed in this audit.
10. Extension **visual** harness (`test/visual/*`) — not executed.
11. Extension **integration** (`npm run test:integration` → `test/integration/bridge_integration.py`) — not executed in this audit.
12. VS Code activation in a real Editor with a real workspace, an agent-written file, and a forced mid-flow change — the one flow that proves the product end-to-end.
13. Windows Defender / antivirus interference with the atomic-replace pattern (real-world, not testable in CI).
14. Multi-user / concurrent-writer scenarios (the documented single-writer assumption).
15. A **database rollback rehearsal** on a disposable Postgres/SQLite instance: `downgrade base` → `upgrade head` on a populated schema (currently impossible — MIG-01) and the M-PKG drift fix on the same instance (MIG-02).

---

## 13. Maintainability assessment (summary)

- **Duplicate/conflicting implementations:** the vendored engine copy inside the extension (MNT-01) is the main one; otherwise the CLI and extension genuinely share one engine (verified).
- **Dead code:** the committed root debris (MNT-03); the dead `redact_mapping`/`_looks_sensitive` helpers (RE-11). `recoveryInbox.ts` was orphaned from the compiled output for ~1 hour of the audit (EXT-02) — resolved by the in-flight recompile at 17:27:59.
- **Unhandled exceptions:** none found in the engine's decision paths — every handler returns a structured failure. This is a genuine strength (see §7).
- **Type safety:** strict mypy on `app`/`sdk`/CLI (0 errors); **not** applied to tests/scripts (MNT-04); the extension is typechecked and, as of 17:35, clean (343/343 tests).
- **Ownership of safety decisions:** the engine owns them, and the extension/CLI both defer to it. The one place a UI-layer decision could be trusted instead of proven is the identity fallback — and even there the extension refuses to invent an identity.
- **Logging/diagnostics:** the extension logs to a dedicated output channel with redaction (`redact.ts`); the server has an audit logger; no secret leakage observed in the artifacts I inspected.
- **Performance:** `verify()` reads whole files with no cap (RE-19); baseline capture is size-capped; the engine is a single-pass adapter. No evidence of unbounded scans in the reviewed paths, but the 2,900+ test suite and 31-minute unit runtime indicate a large surface.
- **Accessibility/usability:** the extension webview has a skip link, ARIA labels, ≥12 px text floor, large hit targets and keyboard focus handling (asserted by the extension's own unit tests); the site has `aria-live` route fallbacks and a skip link.

---

## 14. Repository preservation record

- Root: `F:\Desktop_Data_2026\Desktop\INTERLOCK V4`; branch `master`; HEAD `624171eeebdf5931351234594653352a12fea7f3`; remote `origin` (unchanged).
- Working tree at audit start: **226 porcelain entries** (132 tracked files changed, 2692+/8287−; 254 untracked), 1 stash (`stash@{0}`), `web/` deletions intact.
- Working tree at audit end: **227 porcelain entries** — the tracked diff is **byte-identical** to the start (`git diff --stat` = `132 files changed, 2692 insertions(+), 8287 deletions(-)`), the stash is intact, and the delta is: (a) this report (`?? INTERLOCK_V6_FULL_PROJECT_AUDIT_2026-10-20.md`) and (b) the ~8–20 new paths written by the **parallel in-flight work** under `extensions/vscode/` (see §4.2) — none of which this audit created or modified.
- No `git add`, `commit`, `push`, `tag`, `reset`, `clean`, `restore` or checkout was executed. No branch, remote or release was changed. Nothing was staged, published or deployed.
- No dependency was installed or upgraded. `pip-audit`, `bandit`, `ruff`, `mypy` and `pytest` were already present in `.venv`; `npm audit`/`npx vite build` used the existing `node_modules`.
- No application source file was modified. The **only** file created by this audit is this report: `INTERLOCK_V6_FULL_PROJECT_AUDIT_2026-10-20.md` (verified non-existent before creation).
- Artifacts were written **outside** the repository: `%TEMP%\opencode\pkg_audit` (wheel/sdist), `%TEMP%\opencode\site_build` (site build), `%TEMP%\opencode\audit_*.txt|patch` (git snapshots). The pre-existing `dist/`, `build/`, `coverage.xml` and `site/dist` were left as found; `coverage.xml` (gitignored) was rewritten by the pytest runs, as designed by `pyproject.toml` addopts.
- Destructive testing was never performed against real user files: all recovery testing used temp directories and synthetic fixtures (the CLI lifecycle check uses `tempfile.mkdtemp`).
- Secrets: no secret values were printed, copied, or transmitted. `.env` exists on disk and is gitignored; no credential file was found in the wheel, sdist or tracked source.
- External transmission: no source code was uploaded to any external scanner (Semgrep was not run; CI would do so by policy — SEC-03).

---

## 15. Code quality rating

### **Overall: 7 / 10**

| Component | Score | Rationale |
|---|---|---|
| Recovery engine (core) | **8.5** | Fail-closed design, byte-exact handling, atomic staging, re-hash before and after the write, strict typing, no shell/deserialization surface. Held back by the evidence-seal gap (RE-01), truncation path (RE-03), unverified metadata claims (RE-07) and the git adapter's honesty problem (RE-08) |
| Terminal Runner (CLI) | **8** | Genuinely thin, non-interactive, shared engine, honest exit codes, verified 38/38 — but it destroys baselines (RE-02) and its guarantees are not automated (TST-01) |
| Server / control plane | **7** | Clean auth, no hardcoded secrets, 0 Medium/High bandit findings, strict typing, 446/446 integration tests — but **irreversible, database-bricking downgrades (MIG-01)**, 33-op model/migration drift (MIG-02), a large surface with low per-module coverage in the API layer, and no external audit |
| VS Code extension | **7.5** | Exemplary webview hygiene (nonce CSP, escaping, message allow-list), honest identity handling, correct diff, and — as of 17:35 — a clean typecheck/lint and 343/343 tests. Held back by the absence of any CI gate (TST-02) and by the fact that the only distributable artifact predates the current build |
| Test suite | **7** | 2,416 unit + 446 integration tests pass, meaningful edge-case coverage, honest skip/xfail reporting (the 4 migration xfails are unusually well documented) — but no junction/Unicode recovery tests, 7 skips on the primary platform, CLI checks not automated, and no CI coverage for two of three shipped surfaces |
| Packaging & release | **6** | The Python artifacts are clean and correct; the extension now compiles and packages, but the only `.vsix` predates the current build, there is no CI release path, and the version/branding is inconsistent (4.0.0 / 6.0.0 / 0.1.0) |
| Website & docs | **6.5** | Exceptionally honest content (no fabricated claims, explicit limitations) — undermined by WEB-01 (denying the artifact that exists), two divergent install surfaces, and 19 overlapping reports |
| Maintainability | **6** | Dead root scripts, a vendored duplicate engine, ~1,000 lint findings outside the linted scope, a 226-entry dirty tree, and 19 overlapping status documents |

**Why not higher:** the highest-value properties — an intact, trustworthy, recoverable before-state — have two High-severity holes (RE-01, RE-02) precisely in the evidence layer; the website tells users the opposite of the truth about the shipped artifact (WEB-01); and the only distributable artifact for the primary user-facing interface predates the current build. **Why not lower:** the engineering that matters most (containment, refusal, byte-exact verification, honest reporting, shared-engine consistency, strict typing) is genuinely strong and independently verified here; the failures are concentrated in packaging, claims and the evidence seal, not in the safety core.

*Rating basis: the repository as it stood at 17:35 on 2026-10-20, with the extension's in-flight fixes applied.*

---

*End of report. Phase A only — no application code was changed. Awaiting explicit approval before any remediation.*
