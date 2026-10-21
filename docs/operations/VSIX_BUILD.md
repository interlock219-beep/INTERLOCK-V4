# Building the VS Code extension package (VSIX)

This is the reproducible procedure for the Interlock VS Code extension package.
It produces the artifact, records its SHA-256, and states exactly what the
package does and does not contain.

**Nothing here is published.** The artifact is a local build; there is no
Marketplace listing, no published download and no published checksum. The
SHA-256 below is a *checksum of one local build* — it is **not** a digital
signature and it is **not** proof of publisher identity.

## Prerequisites

- Node.js 20 (the version the CI job uses)
- Python 3.11–3.14 on `PATH` (the engine is standard-library only)
- The repository checked out with `extensions/vscode/` and `app/` + `sdk/`
  present — the extension ships a vendored copy of the engine, and the bundle
  step below rebuilds that copy from the canonical sources.

## Procedure

```bash
cd extensions/vscode

# 1. Dependencies (lockfile-driven, reproducible)
npm ci

# 2. The gates that must pass BEFORE packaging.
#    `vscode:prepublish` runs typecheck + lint + unit tests + compile, so
#    `npm run package` cannot produce an artifact from a broken tree.
npm run typecheck
npm run lint
npm run test:unit

# 3. The vendored engine bundle must match the canonical engine source.
#    This check is read-only and fails with a per-file diff when it does not.
node tools/build-engine-bundle.js --verify

# 4. Package (this re-runs the gates above, then builds the .vsix)
npm run package

# 5. Record the checksum of the EXACT artifact that was produced
sha256sum interlock-vscode-*.vsix | tee vsix-sha256.txt
```

## Recorded build

| Field | Value |
|---|---|
| Artifact | `interlock-vscode-0.1.0.vsix` |
| Size | 33,879,240 bytes |
| SHA-256 | `ae3eaf9adf9c5fdde32366ffc6f39f020a68b6c460808bac51ba2cf1dc9b49a8` |
| Built on | 2026-10-21, Windows x64, Node 20, from the working tree at that time |
| Package contents | 840 entries: 30 compiled `out/src` modules, `python/interlock_bridge.py`, the engine bundle (38 files + `manifest.json`), `media/`, and the pinned CPython runtime for Windows x64 (761 files) |
| Deliberately excluded | no `test/` files, no `.ts` sources, no source maps, no `node_modules` |

The checksum is only meaningful together with the tree it was built from: a
different commit produces a different artifact and a different checksum. The
CI job (`vscode-extension` in `.github/workflows/ci.yml`) repeats this exact
procedure on every push and uploads the artifact **and** its checksum as
build evidence, without publishing anything.

## What the packaged extension contains and does not contain

- The engine bundle inside the package is **verified against a SHA-256
  manifest** (`engine/manifest.json`) before any of it is used, and the
  installer refuses to proceed when a byte does not match.
- The bundled CPython runtime is pinned by version **and** SHA-256 and is
  **Windows x64 only**. On macOS and Linux the extension falls back to a
  system Python 3.11–3.14, and no runtime is provisioned for those
  platforms.
- The package contains no dependency tree (`vsce package --no-dependencies`):
  the extension talks to the engine over a local JSON bridge, not to
  third-party Node modules.
- The extension is **not published**. There is no Marketplace listing, no
  public download and no published checksum. The website says the same.

## If the bundle check fails

```
engine bundle is STALE - the extension would ship different code:
  - app/infrastructure/recovery/filesystem_recovery_adapter.py: committed copy differs from the canonical source
Fix: node tools/build-engine-bundle.js && commit extensions/vscode/engine/
```

The extension would otherwise ship code that differs from the repository.
Rebuild the bundle, re-run the gates, and re-record the checksum.
