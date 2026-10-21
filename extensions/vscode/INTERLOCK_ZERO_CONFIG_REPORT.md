# Interlock VS Code Extension — Zero-Configuration Implementation Report

Date: 2026-10-20 · Extension: `interlock-vscode@0.1.0` (publisher `interlock219-beep`)
Artifact of record: `interlock-vscode-0.1.0.vsix` — **830 files, 32.24 MB**

This report is evidence-based. Every command below was executed and its real
output recorded. No test, package, installation, or publication is claimed
unless it actually happened.

---

## 1. Executive summary

The extension already contained a well-designed but **unwired** zero-configuration
engine subsystem (`src/engineSetup.ts`), a native side-by-side diff subsystem,
and a shared Python recovery engine. This mission closed the two gaps that kept
the product from the stated Definition of Done:

1. **Zero-configuration installation.** The extension now ships a **bundled,
   SHA-256-verified CPython 3.11 runtime** alongside the **bundled engine
   files** inside the VSIX. On first use it installs the engine into
   extension-managed storage, verifies every file against a build-time
   manifest, runs a real health check, and records success atomically. A new
   Windows x64 user needs **no Python install, no repository checkout, no
   virtual environment, no `pip`, and no settings.** Nothing is downloaded at
   install or run time.
2. **Wiring + evidence.** The setup subsystem is now wired into activation
   (`src/engineRuntime.ts` → `src/extension.ts` → discovery), guarded by a
   single-flight concurrency lock, and proven by unit tests, a packaged-artifact
   clean-environment verifier (no Python on `PATH`), and a **real VS Code
   extension-host test that runs with zero Interlock configuration.**

The native side-by-side recovery preview (`vscode.diff`), automatic baseline
protection, approval-gated execute, and independent byte-exact verify were
already implemented by parallel work; this report verifies them end-to-end
against the packaged artifact and does not rewrite them.

**Definition of Done status (Windows x64):** met and machine-verified — install
the VSIX, open a folder, and the engine self-installs against the bundled
runtime and answers real Protect/Analyze/Preview/Apply/Verify calls, with no
Python configured (see §6, zero-config host test and §7 clean-environment run).

---

## 2. Zero-configuration runtime architecture

**Problem.** The engine's runtime import closure is **standard-library-only**
(previously proven by running the whole command surface in a bare venv), but it
still needs *some* Python interpreter. Shipping only Python *source* therefore
did not remove the "install Python first" step.

**Solution — bundle a real, pinned, integrity-checked runtime.**

- **Runtime source:** `python-build-standalone` (astral-sh), release tag
  `20261013`, asset `cpython-3.11.17+20261013-x86_64-pc-windows-msvc-install_only.tar.gz`.
- **Integrity:** the archive's SHA-256
  `7616ab1f74aab975bd91eb0a657a74a092a63a46cac38c5f3f9415c79fd781f5` was verified
  against the upstream release `SHA256SUMS` manifest **before** extraction.
- **Reproducibility:** `tools/provision-runtime.js` pins the tag, asset, and
  hash in one table, refuses targets with no pinned runtime, and strips
  build-time cruft after extraction. It is a **build-time** tool; the packaged
  extension never executes it and never downloads anything.
- **Placement:** `runtime/win32-x64/python/python.exe` inside the VSIX
  (104 MB after stripping; the extension looks only under
  `runtime/<platform>-<arch>/`).
- **Stripped for size and safety:** `site-packages` (pip/setuptools/wheel —
  shipping `pip` would invite arbitrary installs), `venv`, `ensurepip`,
  `idlelib`, `tcl`, `include`, `libs`, and all `__pycache__` — ~50 MB removed.
  The engine needs none of them (stdlib-only). `.vscodeignore` also excludes
  them as a second lock.

**Lifecycle (`src/engineRuntime.ts`, vscode-free and unit-testable):**

- `state()` — filesystem-only first paint; no subprocess on activation.
- `ensureInstalled()` — **single-flight**: every concurrent caller shares one
  install run. Installs by (a) verifying the bundled engine against its SHA-256
  manifest, (b) running a real `probe` health check through the bundled bridge,
  (c) cross-checking the reported version, then (d) atomically writing an
  install record. A record is written **only** after a passing health check.
- **Bundled fast path:** because the engine is stdlib-only and the runtime is
  already isolated, no virtual environment is created — the bundled interpreter
  *is* the managed environment (no pip/ensurepip involved).
- `resolve()`/`managed()` — an intact managed installation always wins; an
  explicit `interlock.pythonPath`/`engineRoot` still wins over it, so a
  developer checkout is unaffected.
- **Repair:** a missing interpreter or a corrupted engine file makes `state()`
  report incomplete/failed, so the next attempt re-installs; a corrupted bundle
  is refused (never reported ready).

**Wiring:**

- `src/extension.ts` — creates `EngineRuntime`, schedules a **deferred,
  non-blocking** auto-install ~1.5 s after activation (first paint completes
  first), registers **Interlock: Install or Repair Engine**, and exposes a
  read-only `getSetup()` on the activation API.
- `src/discovery.ts` — `detectEngine(...)` accepts an optional managed override
  that is used **before** workspace/PATH probing and **after** explicit config.
- `src/commands.ts` — `locate()` passes the managed installation as that
  override (two-line surgical change; explicit settings still win).

---

## 3. Recovery preview, approval, and verification (verified, not rewritten)

Verified end-to-end against the packaged artifact in a clean environment
(§7): preview is read-only; the plan never leaks file contents; `execute`
without an approver is **refused (exit 5)** and leaves the file untouched;
`execute` with an approver restores the file **byte-for-byte**, reports
`verified`, and passes an **independent byte-exact** check; `verify` then
confirms success. Parent-traversal capture is refused and a sentinel outside
the workspace stays intact. The native diff uses `vscode.diff` with
hash-verified proposed contents and stale-preview invalidation (parallel work,
confirmed wired: provider registered, `staleAgainstCurrent`, `executeCommand('vscode.diff', …)`).

---

## 4. Security and data integrity (P5) — preserved and validated

- Webview: nonce-only CSP, **no remote resources**, no `innerHTML`/`eval`/
  `document.write` (the single "innerHTML" occurrence is a comment stating it
  is never used).
- Process execution: `spawn(command, args, { shell: false })` — argument
  arrays only, allow-listed environment, timeouts, cancellation.
- Engine: workspace confinement, path-traversal refusal, approval gate,
  tampered-evidence rejection, independent post-recovery verification — all
  exercised by the 58-check integration run and the 42-check clean-environment
  run.
- Bundled runtime ships **no `pip`** (site-packages stripped), removing an
  arbitrary-install vector.

---

## 5. Files changed (this mission)

**Created**

| File | Purpose |
| --- | --- |
| `src/engineRuntime.ts` | Managed engine + bundled-runtime lifecycle, single-flight install, resolve/managed |
| `test/unit/engineRuntime.test.ts` | 14 tests: runtime selection, single-flight, resolve precedence, real-subprocess install/repair/corrupt-refusal |
| `test/host/activation-zerocfg.js` | Zero-config host assertions (setup ready, bundled engine, no config) |
| `test/host/launch-zerocfg.js` | Boots real VS Code with **no** Interlock settings |
| `tools/provision-runtime.js` | Pinned + SHA-256-verified runtime provisioning (build-time) |
| `tools/clean-env-verify.js` | Runs the full lifecycle from the packaged VSIX with no Python on `PATH` |

**Edited (surgical, additive)**

| File | Change |
| --- | --- |
| `src/discovery.ts` | Optional `EngineOverride`; managed-before-autodetect |
| `src/commands.ts` | Import + optional `EngineRuntime` ctor param; `locate()` passes the managed override |
| `src/extension.ts` | `EngineRuntime` wiring, deferred auto-install, `installEngine` command, `getSetup()` API |
| `package.json` | Declared `interlock.installEngine` command |
| `.vscodeignore` | Exclude `tools/**` + runtime cruft (second lock) |
| `.gitignore` | Ignore `runtime/` (~100 MB binaries; CI-provisioned) |
| `readme.md` | Requirements + platform row now reflect the bundled-runtime zero-config path |
| `CHANGELOG.md` | "Unreleased — zero-configuration installation" entry |

**Built artifacts:** `runtime/win32-x64/python/` (104 MB, gitignored) and
`interlock-vscode-0.1.0.vsix` (830 files, 32.24 MB).

VSIX inspection (all verified): bundled `python.exe` + `python311.dll` present;
38 engine `.py` files + `engine/manifest.json`; bridge; `out/src/engineRuntime.js`
and `out/src/extension.js`; activity-bar SVG + PNG icon. **Zero** leaks: no
`__pycache__`/`.pyc`, no `site-packages`/`ensurepip`/`venv`/`idlelib`/`tcl`, no
`.ts` sources, no source maps.

---

## 6. Test commands and real results

| # | Check | Command | Result |
| --- | --- | --- | --- |
| 1 | Typecheck | `npm run typecheck` | **exit 0** |
| 2 | Lint | `npm run lint` | **exit 0** |
| 3 | Unit tests | `npm run test:unit` (mocha) | **239 passing** (incl. 14 new engineRuntime tests) |
| 4 | Integration (bundled runtime) | `INTERLOCK_PYTHON=<bundled> … bridge_integration.py` | **58 passed / 0 failed, exit 0** |
| 5 | Visual layout & branding | `node test/visual/check-layout.js` | **18 passed (all green), exit 0** |
| 6 | Extension host (configured) | `node test/host/launch.js` | **35 passed / 0 failed, exit 0** |
| 7 | **Extension host (ZERO-CONFIG)** | `node test/host/launch-zerocfg.js` | **PASS — `setup status=ready version=4.0.0`, bundled engine, no Python configured, exit 0** |
| 8 | Packaged-artifact clean env (no system Python) | `node tools/clean-env-verify.js` | **42 passed / 0 failed, exit 0** |
| 9 | Package | `npm run package` | **830 files, 32.24 MB, exit 0** |
| 10 | Install (isolated dirs) | `code --install-extension … --extensions-dir <tmp>` | **successfully installed** |
| 11 | Install (real extensions dir) | `code --install-extension … --force` | **successfully installed** (`interlock219-beep.interlock-vscode-0.1.0`) |

Test #8 (clean environment) explicitly ran with `PATH="C:\Windows\System32;C:\Windows"`
(no Python), `PYTHONHOME`/`PYTHONPATH` unset, on a throwaway workspace, using
only the interpreter/bridge/engine extracted from the VSIX. It covered
probe → capture-baseline → analyze → plan → approval-gated execute → verify →
confinement, asserting the interpreter was the bundled one and that nothing was
downloaded.

---

## 7. Supported and tested platforms (honest)

| Platform | Extension package | Bundled runtime | Status |
| --- | --- | --- | --- |
| **Windows x64 (NTFS)** | installs | **yes (provisioned + integrity-verified)** | **TESTED here** (unit, integration, clean-env, host, zero-config host) |
| Windows ARM64 | installs | no | Falls back to system Python 3.11–3.14, else reports Python required. **Not tested.** |
| macOS arm64 | installs | no | Same fallback. **Not tested** (no native runtime provisioned). |
| Linux x64 | installs | no | Same fallback. **Not tested.** |
| macOS Intel | installs | no | Dependency-blocked (unchanged from prior findings). |

"Installs here" is never presented as "validated here." No platform is
advertised as bundled unless its runtime was really provisioned and verified —
`tools/provision-runtime.js --key darwin-arm64` exits with an explicit refusal.

---

## 8. Milestones (P8 — kept separate)

| Milestone | Status |
| --- | --- |
| Source implementation complete | **Yes** |
| Tests passed | **Yes** (all rows in §6) |
| VSIX packaged | **Yes** — 830 files, 32.24 MB |
| VSIX installed locally | **Yes** — isolated dirs and the real `~\.vscode\extensions` |
| Clean-environment installation verified | **Yes** — 42/42 with no system Python |
| **Marketplace publication completed** | **No** — not attempted; no publisher account and no authorization. The extension remains a local VSIX. |

---

## 9. Remaining limitations (stated honestly)

- **Windows x64 only** for the bundled-runtime (true no-Python) path. Other
  platforms fall back to a detected system Python or report that Python 3.11–3.14
  is required. Producing per-platform runtimes/VSIX is CI work that has not run.
- **Marketplace publication** is not done (no account/authorization).
- The zero-config GUI click-through ("click the shield → Protect") is covered by
  the automated zero-config host test, which activates the extension and drives
  the same commands (`installEngine`, `checkInstallation`) with **no** settings
  and asserts the engine becomes ready and available from the bundled files. A
  hand-driven screenshot of the click path was not captured.
- The engine reports `version: null` on probe; the manifest version (4.0.0) is
  used, and the health check tolerates a null reported version.
- Signing/notarization of the VSIX does not exist (disclosed, unchanged).

---

## 10. Git safety confirmation

- HEAD unchanged: `624171e`. Branch `master`. **Nothing staged, committed,
  pushed, tagged, published, or deployed. No remotes changed.**
- `git status --porcelain` = **221** (M=72, D=60, `??`=89), identical to the
  session baseline; all 60 deletions remain under `web/` (preserved, untouched).
- Stash `@{0}` preserved.
- The bundled `runtime/` is **gitignored** (it is ~100 MB of binaries provisioned
  by `tools/provision-runtime.js` at build/CI time), so a future `git add` of
  `extensions/` cannot accidentally commit it.
- No `git add .`/`-A`, no `reset --hard`, no `clean`, no broad checkout/restore.
- All pre-existing modified, deleted, untracked, and parallel `site/` work is
  preserved. Parallel work under `extensions/vscode/src` (notably the native
  diff subsystem) was verified, not overwritten.
