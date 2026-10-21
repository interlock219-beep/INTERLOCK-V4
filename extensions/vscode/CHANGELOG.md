# Change Log

All notable changes to the Interlock VS Code extension are documented here.

## Unreleased

Zero-configuration installation.

- **Bundled engine + bundled runtime.** The VSIX now ships the engine files
  together with a pinned, SHA-256-verified CPython 3.11 runtime for Windows
  x64, so a new user installs and uses Interlock without installing Python,
  cloning the repository, creating a virtual environment, running `pip`, or
  configuring `interlock.engineRoot`. The runtime is provisioned at build time
  by `tools/provision-runtime.js` (pinned release + integrity check); nothing
  is downloaded when the extension runs.
- **Automatic, concurrency-safe engine setup** (`src/engineRuntime.ts`): on
  activation the extension installs the engine into extension-managed storage,
  verifies every file against the build-time SHA-256 manifest, runs a real
  `probe` health check, and only then records success atomically. Concurrent
  triggers collapse onto a single install run; a corrupted bundle or an
  interrupted setup is detected and repaired on the next attempt. A valid
  installation is reused across launches. Added **Install or Repair Engine**
  command and a read-only `getSetup()` API.
- **Discovery prefers the managed installation.** An intact managed engine is
  used automatically unless `interlock.pythonPath`/`interlock.engineRoot` are
  set explicitly, so a developer checkout keeps working unchanged.
- **Native side-by-side recovery preview** (`vscode.diff`) with
  hash-verified proposed contents, stale-preview invalidation, and the
  approval-gated execute/verify flow.
- Tests: unit coverage for bundled-runtime selection, the single-flight install
  guard, and real-subprocess zero-config install/repair; a clean-environment
  verifier (`tools/clean-env-verify.js`) that runs the whole lifecycle from the
  packaged VSIX with no Python on `PATH`; and a zero-configuration
  extension-host test (`test/host/launch-zerocfg.js`).

## 0.1.0

Initial unreleased build (local VSIX only - not published).

- Activity-bar icon and **Status & Recovery** sidebar: a compact webview
  security dashboard (engine status card, workspace card, primary/secondary/
  approval-gated action hierarchy, verification summary, collapsible
  warnings/incidents/documentation sections) rendered by a nonce-only-CSP
  view with no external resources. All states are projections of real engine
  results - "not checked yet" is shown until a real probe has run.
- Commands: Check Installation, Check Status, Analyze Workspace, Capture
  Baseline, Preview Recovery Plan, Apply Recovery (approval-gated), Verify
  Recovery, Open Documentation, Refresh, Show Output Log.
- Real integration with the local Interlock engine through a dedicated Python
  bridge (`python/interlock_bridge.py`) that imports the engine's own
  filesystem recovery adapter. The extension never implements its own
  recovery logic.
- Structured output channel with secret-safe logging, per-call timeouts,
  cancellation, and argument-array process spawning (no shell).
- Unit tests for activation-free registration, configuration validation,
  process invocation, timeout/cancellation, exit-code mapping, refusal and
  verification-failure handling, workspace confinement, platform detection and
  secret redaction.
