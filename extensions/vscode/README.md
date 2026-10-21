# Interlock

Workspace status, recovery-plan previews, and **verified** filesystem recovery
driven by the local **Interlock V6 engine** — a VS Code companion to the
[Interlock repository](https://github.com/interlock219-beep/INTERLOCK-V4).

> **This extension is a local control panel, not a recovery engine.** Every
> read and every state change is performed by the Interlock engine itself,
> invoked through a small Python bridge that ships inside this extension. The
> extension contains **no recovery logic of its own**.

---

## What it does

| Command | Effect |
| --- | --- |
| **Interlock: Check Installation** | Verifies the Python interpreter and imports the real engine; reports versions. |
| **Interlock: Check Status** | Read-only engine status: platform verdict, workspace authorization, evidence-seal support, incident history. |
| **Interlock: Analyze Workspace** | Read-only scan plus executed confinement probes (including a real traversal attempt that must be refused by the engine). |
| **Interlock: Capture Baseline (Before-State Snapshot)** | Captures the engine's before-state snapshot for one file, stored **only** in the extension's private storage. |
| **Interlock: Preview Recovery Plan** | **Read-only.** Shows the diff, conflict status, and approval requirement. Persists a sealed evidence sidecar that later executes must reuse. |
| **Interlock: Apply Recovery (Requires Approval)** | Runs only after an explicit confirmation dialog (you type/type-click the approver name), only from a previously captured preview, and only if no human edit happened in between. |
| **Interlock: Verify Recovery** | Independent, byte-exact verification of the restored file against the baseline. |
| **Interlock: Show Output Log** | Opens the structured output channel (secret-redacted). |
| **Interlock: Open Documentation** | Opens repository documentation from an allow-list of `https://` URLs only. |

The **Status & Recovery** activity-bar sidebar is a compact (~260–350 px)
security dashboard:

- **Header** — Interlock shield, wordmark, and refresh / settings actions.
- **Engine status card** — engine availability, Python version, and the
  engine's *independent* platform verdict, each shown as its own state. The
  status indicator turns green only when the engine genuinely reported
  available; "not checked yet" is shown until a real probe has run.
- **Workspace card** — the workspace folder *name* (the full path stays in a
  tooltip), confinement status, baseline count, and the read-only git signal.
- **Actions** — *Analyze Workspace* is the single highlighted primary action,
  followed by the inspection/preview/baseline actions, then the approval-gated
  *Apply Recovery* (visually separated, amber, marked "approval"), and
  *Verify Recovery* last. Recovery is never presented as one-click.
- **Verification summary** — exactly one accurate state: passed, failed, or
  "no verification recorded". Nothing is ever fabricated.
- **Warnings & errors**, **Recent incidents**, and **Documentation** — collapsible
  sections whose counts come from real data; incident history is reported as
  genuinely unavailable (the engine records none) rather than invented.

The view honours `prefers-reduced-motion`, is fully keyboard navigable, and
uses a restrictive content-security-policy (nonce-only style/script, no
external resources, no inline event handlers). To inspect the layout without
installing anything, generate the static preview from the production renderer:

```
npm run compile && node test/visual/generate-preview.js
# then open test/visual/preview.html in a browser
```

## Safety boundaries (enforced in code, not by convention)

- **Approval-gated writes.** `execute` refuses to run without both a recorded
  approver and a preview-time evidence file; the extension always shows the
  preview diff first, then requires a modal confirmation **and** a typed
  approver identity (recorded in the engine's result).
- **Conflict guard.** Evidence is captured *at preview time* and re-verified at
  execute time (seal checked with the engine's own
  `compute_evidence_hash_v2`). If a human edits the file after the preview, the
  execute is refused and the human's edit is left untouched.
- **Workspace confinement.** Resources must be workspace-relative; parent
  traversal, absolute paths, UNC paths, and drive letters are rejected before
  the engine is even called — and the engine refuses them again.
- **No shell strings.** Every bridge call is spawned with an argument array
  (`shell: false`); a subprocess receives a minimal allow-listed environment,
  never your full `process.env`.
- **Honest success.** The extension reports success **only** when the engine
  reported success *and* verification confirmed a byte-exact restore. Refusals,
  timeouts, and verification failures are reported distinctly — never as
  "done".
- **Secret-safe logging.** Everything written to the output channel passes
  through a redactor (bearer tokens, JWTs, `password=`/`token=` assignments,
  PEM private keys, AWS key ids).
- **No telemetry, no network calls.** The extension talks only to a local
  Python process. Nothing is uploaded; no analytics exist.

## Platform support (two different claims)

- **The extension package** is plain TypeScript/Node and installs wherever
  VS Code runs (Windows, macOS, Linux).
- **The Interlock engine** has its own, narrower support matrix. The sidebar
  and **Check Status** always show the engine's verdict separately:

  | Engine environment | Status |
  | --- | --- |
  | Windows x64 + NTFS (bundled runtime ships; no Python install needed) | **TESTED — PRIMARY** (the recorded validation environment) |
  | Windows ARM64 | UNTESTED |
  | macOS arm64 | DECLARED — CI PENDING |
  | macOS Intel | UNSUPPORTED (dependency-blocked) |
  | Linux x64 | DECLARED — CI PENDING |
  | FAT32/exFAT/network drives | UNSUPPORTED (no atomic-replace guarantee) |

"Installs here" is never presented as "validated here".

## Requirements

**Zero-configuration path (Windows x64):** nothing beyond VS Code 1.85+.
This build ships a bundled, SHA-256-verified CPython 3.11 runtime and the
engine files inside the VSIX, so the first use installs and health-checks the
engine automatically - no Python install, no repository checkout, no virtual
environment, no `pip`, and no settings to configure.

**Developer / other-platform path:** on platforms with no bundled runtime
(macOS, Linux, Windows ARM64) the extension instead detects a system Python
3.11-3.14 and either uses a local engine checkout or tells you exactly what is
missing. `interlock.pythonPath` / `interlock.engineRoot` remain available as
optional overrides and always win over automatic discovery.

The bundled runtime is provisioned at build time by
`tools/provision-runtime.js` from a pinned, hash-verified
python-build-standalone release; nothing is ever downloaded when a user
installs the VSIX.

## Install (local VSIX)

```powershell
code --install-extension interlock-vscode-0.1.0.vsix
```

Then open the Interlock sidebar (activity bar → Interlock) and run
**Interlock: Check Installation**.

### Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `interlock.pythonPath` | *(empty)* | Interpreter for the bridge. Empty ⇒ auto-detect (`.venv` in the engine root, then `python3`/`python` on `PATH`). |
| `interlock.engineRoot` | *(empty)* | Engine checkout root (directory containing `app`). Empty ⇒ auto-detect from the workspace. |
| `interlock.autoDetectEngine` | `true` | Allow automatic discovery. |
| `interlock.timeoutSeconds` | `60` | Per-call timeout; the child process is terminated on expiry. |
| `interlock.maxBaselineBytes` | `5242880` | Largest file for which a baseline (which includes content) may be captured. |
| `interlock.showGitChanges` | `true` | Show a read-only `git status` signal in the sidebar. This is **not** an Interlock incident record. |
| `interlock.allowedDocumentationUrls` | repository URL | `https://` URLs the documentation command may open. |

## Known limitations (stated honestly)

- **Incident history is unavailable.** The current engine exposes no incident
  store, so **Check Status** reports `incident history: unavailable` rather
  than inventing records.
- **`git status` in the sidebar is a plain git signal**, not an engine
  incident, and is labelled as such.
- **Baselines include file content** and are therefore stored only in the
  extension's private storage (`globalStorageUri`), never inside your
  workspace, and never echoed to the log.
- **Recovery targets a single file per run** — the scope the engine's adapter
  supports and verifies today.
- **Platform coverage is limited to the matrix above.** Nothing here
  compensates for an environment the engine has not validated.

## Development

```powershell
npm install
npm run typecheck     # tsc --noEmit
npm run lint          # eslint
npm run test:unit     # 86 unit tests (mocha)
npm run compile
```

Real-engine integration tests (uses the actual engine, no mocks — creates and
removes its own temporary workspace):

```powershell
.venv\Scripts\python.exe extensions\vscode\test\integration\bridge_integration.py
# → passed=52 failed=0
```

Package a VSIX:

```powershell
npm run package       # vsce package --no-dependencies
```

## License

See [LICENSE.md](LICENSE.md). Repository:
[interlock219-beep/INTERLOCK-V4](https://github.com/interlock219-beep/INTERLOCK-V4).
