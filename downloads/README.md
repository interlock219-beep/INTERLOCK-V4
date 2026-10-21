# `downloads/` — standalone install page (legacy-tree workaround)

## Why this folder exists

The original product website lived in `web/`. That tree was deleted (60 files removed) in
pre-existing, **preserved** work; the deletions are staged nowhere and must not be restored,
and the folder is not editable without destroying that history. This standalone `index.html`
is therefore the only place a static download/install page can live until the replacement
website (`site/`) is built and deployed.

## What it contains

- `index.html` — a self-contained "One engine. Two ways to work." page presenting the product's
  two intended installation paths:
  - **Install for VS Code** — an honest *not published* state. The extension source is in the
    repository and can be packaged locally, but there is no Marketplace link, no published
    download and no published checksum.
  - **Install for the terminal** — the real `intentlock` Python package installed from a
    repository checkout into a virtual environment (not published to PyPI yet).
  - An operating-system compatibility table (Windows tested, macOS arm64 validation in
    progress, macOS x86_64 unsupported, Linux unvalidated) and explicit honesty rules.
  - **Zero external links**: no download button, no URL, no fake artifact reference anywhere.

## Integration notes (for when `site/` ships)

- The canonical installation page is `site/src/pages/Download.tsx` (route `/download`) once
  that site is deployed; this file can then be retired.
- **No download button may be enabled** until ALL of the following are true:
  1. A native CI run produces the artifact (e.g. the `macos-release-artifact` workflow job
     uploads the platform wheel and posts its SHA-256),
  2. the artifact is **published** at a real, permanent URL (e.g. a GitHub Release asset),
  3. the SHA-256 shown on the page is taken from the CI step that published that exact file,
  4. signing/notarisation status is disclosed truthfully (currently: none exists).
- When those conditions are met, add a real `<a href>` per platform **with** its checksum
  next to it — never a bare button.

## Status

- 2026-10-19: page restructured from the OS-card download layout to the two-way
  installation layout (VS Code + terminal) per the installer-decommissioning mission;
  obsolete standalone OS download presentation removed; compatibility information retained.
- 2026-10-19 (macOS/Linux download-removal mission): verified — this page offers no
  macOS or Linux download option, no OS-specific button, and no external link of any
  kind; the compatibility table is status-only with no download actions, and the
  policy sentence "Standalone macOS and Linux downloads are not currently offered"
  was added. The canonical page (`site/src/pages/Download.tsx`) was restructured by
  the parallel worker to the same two-option model and verified green
  (typecheck/lint/34 tests/production build).
