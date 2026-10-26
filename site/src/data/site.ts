/**
 * Central content/data for the Interlock V6 website.
 *
 * Every value here was checked against repository evidence
 * (INTERLOCK_V6_RELEASE_READINESS_REPORT.md, docs/operations/SUPPORTED_PLATFORMS.md,
 * docs/operations/SAFETY_AND_LIMITATIONS.md, docs/operations/BETA_FIRST_RUN.md,
 * SECURITY.md, pyproject.toml) on 2026-10-19. Anything that is not evidenced
 * is labelled as proposed, simulated, or unavailable instead of being invented.
 */

export const SITE = {
  name: 'Interlock',
  version: 'V6',
  productName: 'Interlock V6',
  package: 'intentlock',
  packageVersion: '4.0.0',
  repoUrl: 'https://github.com/interlock219-beep/INTERLOCK-V4',
  repoLabel: 'interlock219-beep/INTERLOCK-V4',
  securityEmail: 'security@interlock.io',
  evidenceDate: '2026-10-18',
  // VS Code extension (published on the Microsoft Visual Studio Code Marketplace)
  vscodeMarketplaceId: 'interlock.interlock-vscode',
  vscodeMarketplaceUrl: 'https://marketplace.visualstudio.com/items?itemName=interlock.interlock-vscode',
  vscodeExtensionVersion: '0.1.3',
  // VSIX installer is published as a GitHub Release asset (upload required)
  vscodeVsixFilename: 'interlock-0.1.3.vsix',
  vscodeVsixReleaseUrl:
    'https://github.com/interlock219-beep/INTERLOCK-V4/releases/download/v0.1.3/interlock-0.1.3.vsix',
  vscodeVsixReleasesPage: 'https://github.com/interlock219-beep/INTERLOCK-V4/releases',
} as const;

export interface NavLink {
  label: string;
  to: string;
}

export const PRIMARY_NAV: NavLink[] = [
  { label: 'Home', to: '/' },
  { label: 'Features', to: '/features' },
  { label: 'Demo', to: '/demo' },
  { label: 'Docs', to: '/docs' },
  { label: 'Safety', to: '/safety' },
  { label: 'Pricing', to: '/pricing' },
  { label: 'Blog', to: '/blog' },
];

export const FOOTER_NAV: { title: string; links: NavLink[] }[] = [
  {
    title: 'Product',
    links: [
      { label: 'Features', to: '/features' },
      { label: 'Interactive demo', to: '/demo' },
      { label: 'Download & install', to: '/download' },
      { label: 'Pricing', to: '/pricing' },
    ],
  },
  {
    title: 'Learn',
    links: [
      { label: 'Documentation', to: '/docs' },
      { label: 'Safety & security', to: '/safety' },
      { label: 'Blog', to: '/blog' },
      { label: 'About', to: '/about' },
    ],
  },
  {
    title: 'Beta',
    links: [
      { label: 'Beta programme', to: '/beta' },
      { label: 'Supported platforms', to: '/download' },
      { label: 'Troubleshooting', to: '/docs/troubleshooting' },
      { label: 'Limitations', to: '/docs/limitations' },
    ],
  },
];

export type PlatformStatus = 'tested' | 'pending' | 'untested' | 'unsupported';

export interface PlatformInfo {
  id: string;
  name: string;
  status: PlatformStatus;
  statusLabel: string;
  arch: string;
  python: string;
  detail: string;
}

/** Mirrors docs/operations/SUPPORTED_PLATFORMS.md (verified 2026-10-18). */
export const PLATFORMS: PlatformInfo[] = [
  {
    id: 'windows-x64',
    name: 'Windows',
    status: 'tested',
    statusLabel: 'Tested — primary',
    arch: 'x64 · NTFS · non-elevated',
    python: 'Python 3.11.9 verified',
    detail:
      'Install, recovery and independent byte-exact verification exercised end-to-end, including a real 20/20 process-kill drill and a real permission-denial drill.',
  },
  {
    id: 'linux-x64',
    name: 'Linux',
    status: 'pending',
    statusLabel: 'Validation in progress',
    arch: 'x64 · ext4 (declared)',
    python: 'Python 3.11–3.14 declared',
    detail:
      'Declared by the package metadata and encoded in the CI matrix, but no native Linux execution is part of the current evidence set. Treat results as unverified until a run is recorded.',
  },
  {
    id: 'macos-arm64',
    name: 'macOS',
    status: 'pending',
    statusLabel: 'Validation in progress',
    arch: 'arm64 · APFS (declared)',
    python: 'Python 3.11–3.14 declared',
    detail:
      'Declared, not validated: no native macOS build, install, launch or recovery safety run has been recorded. No installer, signature or notarization exists.',
  },
  {
    id: 'windows-arm64',
    name: 'Windows ARM64',
    status: 'untested',
    statusLabel: 'Untested',
    arch: 'ARM64 · NTFS',
    python: 'Python 3.11+ (declared)',
    detail: 'No hardware available for this configuration, so no evidence exists in any form.',
  },
];

export const UNSUPPORTED_ENVIRONMENTS = [
  'FAT32 / exFAT volumes — rename durability and atomicity are not guaranteed.',
  'Network shares and OneDrive-synced directories — no local atomic-replace guarantee.',
  'Windows paths longer than 260 characters — untested; long-path enabling not verified.',
  'Production databases and migration paths — known defects, explicitly out of scope.',
];

/** Evidence-backed figures. These are test results, not customer metrics. */
export const EVIDENCE_STATS = [
  {
    value: '2,922',
    label: 'tests passed',
    caption: 'Full suite record on Windows x64 / Python 3.11.9 (run #3, coverage 83.81%).',
  },
  {
    value: '20/20',
    label: 'real process-kill drills',
    caption: 'Hard kill mid-recovery produced zero torn writes and zero invariant violations.',
  },
  {
    value: '4/4',
    label: 'safe-demo verdicts',
    caption: 'Recovery, traversal safety, human-change preservation, idempotent replay.',
  },
  {
    value: '0',
    label: 'network calls in recovery',
    caption: 'Recovery paths run offline. No telemetry, no uploads, no tracking scripts here either.',
  },
];

export const EVIDENCE_NOTE =
  'Source: INTERLOCK_V6_RELEASE_READINESS_REPORT.md and docs/operations/SUPPORTED_PLATFORMS.md (verified 2026-10-18). These are engineering test results — not customer, revenue or usage metrics.';

export interface FeatureEntry {
  id: string;
  icon: 'recovery' | 'verify' | 'conflict' | 'refuse' | 'platform' | 'developer';
  title: string;
  summary: string;
  what: string;
  why: string;
  how: string;
  notGuaranteed: string;
  status: 'verified' | 'partial' | 'proposed';
  statusLabel: string;
}

export const FEATURES: FeatureEntry[] = [
  {
    id: 'recovery',
    icon: 'recovery',
    title: 'Recovery',
    summary: 'Undo an AI agent’s file changes byte-exactly, from evidence captured before the action.',
    what: 'Restores files an agent modified or deleted to their exact pre-action bytes, using snapshots captured before the change.',
    why: 'Agent mistakes are usually discovered late. Being able to put a file back exactly — not “similarly” — is the difference between a incident you can shrug off and one you have to reconstruct by hand.',
    how: 'Before an action runs, the adapter records a before-snapshot (content hash plus bytes). The compensation is generated from that evidence and applied through a staging file that is atomically swapped into place on the same volume.',
    notGuaranteed:
      'It cannot recover a state it never observed, and it does not replace version control or independent backups.',
    status: 'verified',
    statusLabel: 'Verified on Windows x64',
  },
  {
    id: 'verification',
    icon: 'verify',
    title: 'Data-integrity verification',
    summary: 'Independent checks compare restored content against captured evidence — adapter claims are never trusted.',
    what: 'After a recovery, content is re-read and compared against the recorded digests. A mismatch is a typed failure, not a warning in a log.',
    why: 'A recovery that “looks” fine can still leave residue or partial writes. Verification is what turns “we ran it” into “we know the state”.',
    how: 'SHA-256 digests are recomputed from the bytes on disk and compared with the manifest. Verification failures fail closed and keep the evidence for inspection.',
    notGuaranteed:
      'Verification proves content matches the captured snapshot; it cannot prove the snapshot was the state you wanted.',
    status: 'verified',
    statusLabel: 'Verified on Windows x64',
  },
  {
    id: 'conflict',
    icon: 'conflict',
    title: 'Conflict detection',
    summary: 'Human edits made after an agent action are preserved, never silently overwritten.',
    what: 'Before restoring, the current bytes of each target are compared with the state the plan expects. Any drift blocks that restore.',
    why: 'The most common way recovery destroys work is by clobbering the fix a human applied after the agent broke things.',
    how: 'A content-hash compare plus existence and symlink guards runs immediately before the swap. A mismatch returns a typed `blocked_by_conflict` result and leaves the file untouched.',
    notGuaranteed:
      'A micro-second window between the existence check and the swap remains; the design assumes a single writer.',
    status: 'verified',
    statusLabel: 'Verified on Windows x64',
  },
  {
    id: 'refusal',
    icon: 'refuse',
    title: 'Safe refusal',
    summary: 'Path traversal, missing evidence and malformed backups produce a refusal, not an attempted write.',
    what: 'Requests that fall outside the confinement boundary — or that lack the evidence required to restore safely — are refused with typed errors and zero side effects.',
    why: 'A tool that sometimes guesses is worse than a tool that says no. Refusal is the behaviour you want when the safe answer is unclear.',
    how: 'Path normalisation and boundary checks run before any work; evidence presence is checked before a plan can be created; hostile backup artifacts fail closed during import.',
    notGuaranteed:
      'Refusal protects against the checked conditions — it is not a guarantee that every unsafe operation is detectable.',
    status: 'verified',
    statusLabel: 'Verified on Windows x64',
  },
  {
    id: 'platform',
    icon: 'platform',
    title: 'Platform support',
    summary: 'Windows x64 is the tested primary platform. Linux and macOS are declared, still validating.',
    what: 'The recovery code is pure Python (`pathlib`/`os`) and declares support for Python 3.11–3.14 across Windows, Linux and macOS.',
    why: 'Honest platform status matters more than a badge: a filesystem guarantee you have not tested is not a guarantee.',
    how: 'Windows x64 / NTFS / Python 3.11.9 is exercised end-to-end with recorded evidence. A cross-platform CI matrix is defined for Linux and macOS; those cells have not produced evidence yet.',
    notGuaranteed:
      'macOS and Linux have not completed native validation. FAT32, exFAT, network shares and ARM64 Windows are untested or unsupported.',
    status: 'partial',
    statusLabel: 'Windows tested · POSIX pending',
  },
  {
    id: 'developer',
    icon: 'developer',
    title: 'Developer integration',
    summary: 'Python API, typed SDK, FastAPI control plane, LangChain adapter and REST endpoints.',
    what: 'Integrate at the level you need: call the recovery adapter directly, wrap tools with the SDK guard, or run the FastAPI gateway and use its REST endpoints.',
    why: 'Recovery only helps if it sits in the path your agents already run through, with the same typed errors you handle everywhere else.',
    how: '`sdk.intentlock` provides `IntentLockGuard` and the `@guard_tool` decorator; `app.main:app` serves `/api/v1/*`; adapters live under `app/infrastructure/recovery/`.',
    notGuaranteed:
      'There is no published package, no hosted service, no VS Code extension and no sign-in system in this site — install runs from a checkout.',
    status: 'verified',
    statusLabel: 'In repository',
  },
];

export const WORKFLOW_STEPS = [
  {
    n: 1,
    title: 'Detect',
    body: 'Agent actions are recorded with before/after state references, tool, resource and risk score.',
  },
  {
    n: 2,
    title: 'Analyse',
    body: 'Changed files are classified: modified, deleted, human-edited, or missing pre-action evidence.',
  },
  {
    n: 3,
    title: 'Plan',
    body: 'A recovery plan lists restore and skip operations with reasons. Preconditions are checked here.',
  },
  {
    n: 4,
    title: 'Approve',
    body: 'Nothing runs without explicit approval. Approval cannot override a failed safety precondition.',
  },
  {
    n: 5,
    title: 'Recover',
    body: 'Restores are staged next to the target and swapped atomically on the same volume.',
  },
  {
    n: 6,
    title: 'Verify',
    body: 'Content is re-read and compared with captured digests. Success is reported only if the checks pass.',
  },
];

export interface InstallStep {
  n: number;
  title: string;
  body: string;
  command?: string;
}

export const INSTALL_STEPS: InstallStep[] = [
  {
    n: 1,
    title: 'Clone the repository',
    body: 'There is no published package or installer. The supported install path is a checkout from the public repository.',
    command: `git clone ${SITE.repoUrl}.git\ncd INTERLOCK-V4`,
  },
  {
    n: 2,
    title: 'Create a virtual environment',
    body: 'Python 3.11 or newer, below 3.15. No Docker, PostgreSQL, Redis, admin rights or network needed at run time.',
    command: `python -m venv .venv\n.venv\\Scripts\\activate   # macOS/Linux: source .venv/bin/activate`,
  },
  {
    n: 3,
    title: 'Install with the dev and security extras',
    body: 'This resolves the runtime dependencies plus pytest, ruff, mypy, bandit, pip-audit and the SBOM generator.',
    command: 'pip install -e ".[dev,security]"',
  },
  {
    n: 4,
    title: 'Run the safe demonstration',
    body: 'Fully disposable: it works in a temp directory it deletes afterwards, touches no repository file and makes no network call.',
    command: 'python scripts/pilot_demo_v1.py',
  },
];

export const VERIFY_COMMANDS = [
  { cmd: 'python --version', note: 'must print 3.11.x or newer, below 3.15' },
  { cmd: 'python -c "import app.main, sdk.intentlock; print(\'imports ok\')"', note: 'prints: imports ok' },
  { cmd: 'python -m pip check', note: 'prints: No broken requirements found' },
];

export const RUN_COMMANDS = [
  { cmd: 'uvicorn app.main:app --reload --host 0.0.0.0 --port 8000', note: 'starts the control plane' },
  { cmd: 'curl http://localhost:8000/api/v1/health', note: 'prints: {"status":"ok"}' },
];

export const TEST_COMMAND = `pytest tests/unit/test_recovery_fault_injection.py \\
       tests/unit/test_backup_restore_drill.py \\
       tests/unit/test_filesystem_recovery_adapter.py \\
       tests/integration/test_alembic_migration_safety.py \\
       tests/integration/test_scenario_proofs_v6.py -q`;

export const TEST_RESULT =
  'Reference-host result (2026-10-18): 60 passed, 2 skipped, 4 xfailed. The skips are Windows symlink-privilege skips; the four xfails are the documented migration defects that are supposed to stay visible.';

export const SAFETY_CAN = [
  'Restore a file an AI agent deleted — byte-exactly, from captured evidence.',
  'Undo an agent’s overwrite of a file and re-verify the result independently.',
  'Refuse to overwrite a human edit made after the agent’s action (`blocked_by_conflict`).',
  'Never double-apply a duplicate delivery of the same compensation.',
  'Refuse path traversal (`file:../…`) with zero side effects.',
  'Survive a hard process kill mid-recovery without torn writes (Windows, 20/20 drills).',
  'Fail closed on malformed or hostile backups with typed errors.',
];

export const SAFETY_CANNOT = [
  'Guarantee recovery for every file, filesystem or failure mode.',
  'Recover a state it never observed — it is evidence-driven, not a backup daemon.',
  'Handle database or migration recovery; those paths carry known, documented defects.',
  'Claim real disk-full behaviour — the ENOSPC drill is mocked and has not been executed.',
  'Claim POSIX guarantees: macOS and Linux have not completed native validation.',
  'Replace version control, independent backups, or human review before you act.',
];

export interface FaqItem {
  q: string;
  a: string;
}

export const FAQS: FaqItem[] = [
  {
    q: 'Is Interlock production-ready?',
    a: 'Not as a claim we make. The release-readiness report marks general availability as NOT READY: real disk-full testing, native POSIX validation, an external audit and an operational runbook are still open. A controlled beta on disposable Windows projects is the supported scope today.',
  },
  {
    q: 'Does it send my data anywhere?',
    a: 'No. The tested recovery workflow reads and writes only inside the project directory you point it at, plus a local evidence file under logs/. It makes no network calls during the workflow and there is no telemetry. If you ever observe a network attempt during the workflow, that is a finding worth reporting.',
  },
  {
    q: 'Do I need an account to try it?',
    a: 'No. There is no hosted service, no sign-in and no dashboard to register for. You clone the repository and run it locally. This website has no account system either, and the interactive demo runs entirely in your browser.',
  },
  {
    q: 'What happens if recovery detects a conflict?',
    a: 'It stops for that file and reports `blocked_by_conflict`. The current content is left exactly as it is. Treat that as the feature it is: your edit, or someone else’s, is being preserved rather than overwritten.',
  },
  {
    q: 'What if it fails halfway?',
    a: 'Restores are staged next to the target and swapped atomically, so an interrupted attempt leaves at most a `*.recovery_tmp` staging file — never partial bytes at your target. The real process-kill drill ran 20 times on Windows with zero torn writes.',
  },
];

export const BLOG_CATEGORIES = ['All', 'Engineering', 'Safety', 'Project'] as const;

/* ------------------------------------------------------------------ *
 * The two installation interfaces (VS Code / terminal)
 *
 * Verified against this repository on 2026-10-21:
 *   - the VS Code extension source, manifest and a local `.vsix` build DO
 *     exist under `extensions/vscode/`, and the extension installs and
 *     verifies its own bundled engine + pinned runtime. Nothing is
 *     PUBLISHED: there is no Marketplace listing, no published download and
 *     no published checksum, so the page never offers one;
 *   - `pyproject.toml` exposes the `interlock` console script and the
 *     `intentlock` package is not on PyPI -> the terminal route installs
 *     from a checkout into a virtual environment.
 * Nothing below invents a URL, artifact, publisher, version or command.
 * ------------------------------------------------------------------ */

export interface InstallOption {
  id: 'vscode' | 'terminal';
  icon: 'vscode' | 'terminal';
  title: string;
  description: string;
  primaryLabel: string;
  /** Real in-page target — no `href="#"`. */
  primaryTarget: string;
  secondaryLabel: string;
  secondaryTarget: string;
  statusLabel: string;
  statusTone: 'green' | 'amber';
  statusNote: string;
}

export const INSTALL_OPTIONS: InstallOption[] = [
  {
    id: 'vscode',
    icon: 'vscode',
    title: 'Install for VS Code',
    description: 'Bring Interlock into your development workflow.',
    primaryLabel: 'Install from VS Code Marketplace',
    primaryTarget: SITE.vscodeMarketplaceUrl,
    secondaryLabel: 'View installation instructions',
    secondaryTarget: '#install-vscode',
    statusLabel: 'Published on Marketplace',
    statusTone: 'green',
    statusNote:
      'Published on the official Microsoft Visual Studio Code Marketplace (extension id ' +
      SITE.vscodeMarketplaceId +
      ', version ' +
      SITE.vscodeExtensionVersion +
      '). Install directly from VS Code, or download the VSIX installer below for manual installation.',
  },
  {
    id: 'terminal',
    icon: 'terminal',
    title: 'Run in Terminal',
    description: 'Use Interlock directly from your command line.',
    primaryLabel: 'View Terminal Instructions',
    primaryTarget: '#install-terminal',
    secondaryLabel: 'View CLI documentation',
    secondaryTarget: '/docs/cli-api',
    statusLabel: 'Validated on Windows x64',
    statusTone: 'green',
    statusNote:
      'Installable only from source — the `intentlock` package is not published to PyPI. Clone the repository into a virtual environment; POSIX platforms are still in validation.',
  },
];

/** Published VS Code extension status. */
export const VS_CODE_STATUS = {
  badge: 'Published on the VS Code Marketplace',
  headline:
    'INTERLOCK is published on the official Microsoft Visual Studio Code Marketplace. Install it directly from VS Code, or download the VSIX installer for manual installation.',
  facts: [
    'Marketplace listing: ' + SITE.vscodeMarketplaceUrl,
    'Extension identifier: ' + SITE.vscodeMarketplaceId + ' (publisher: interlock, name: interlock-vscode).',
    'Published version: ' + SITE.vscodeExtensionVersion + '.',
    'The extension bundles a SHA-256-pinned CPython 3.11 runtime and a manifest-verified engine for Windows x64; on macOS/Linux/Windows ARM64 it falls back to a detected system Python 3.11–3.14.',
    'A VSIX installer (' +
      SITE.vscodeVsixFilename +
      ') is also provided for manual installation via "Install from VSIX...".',
  ],
  capabilitiesTitle: 'What the extension does today',
  capabilities: [
    'Open Interlock from the VS Code Activity Bar or Command Palette.',
    'Check engine installation and status from inside the editor.',
    'Analyze the current workspace for agent-made changes.',
    'Preview a recovery plan before anything is written.',
    'Require explicit approval before any recovery operation.',
    'Verify the result independently after recovery completes.',
  ],
  engineNote:
    'One engine, two interfaces: recovery, security and verification logic stay in the shared Python engine (`intentlock`). The editor is a thin interface over it. The Windows x64 package bundles a SHA-256-pinned CPython runtime and a manifest-verified engine that the extension installs and verifies itself; on macOS and Linux no runtime is bundled and a system Python 3.11–3.14 is required instead.',
  diagnostics: [
    {
      check: 'Engine import check (runs today, no extension needed)',
      code: 'python -c "import app.main, sdk.intentlock; print(\'imports ok\')"',
      note: 'Expected output: `imports ok`. Any traceback means the environment, not an extension, needs fixing.',
    },
    {
      check: 'Broken dependency check',
      code: 'python -m pip check',
      note: 'Expected output: `No broken requirements found`.',
    },
    {
      check: 'Extension present in the Extensions view?',
      code: null,
      note:
        'Search for "Interlock" in the Extensions view, or open ' +
        SITE.vscodeMarketplaceUrl +
        '. The extension id is ' +
        SITE.vscodeMarketplaceId +
        '.',
    },
  ],
} as const;

/** Real, copyable commands — each one appears in BETA_FIRST_RUN.md / the docs. */
export const TERMINAL_COMMANDS = {
  clone: `git clone ${SITE.repoUrl}.git\ncd INTERLOCK-V4`,
  venv: 'python -m venv .venv',
  activateWindows: '.venv\\Scripts\\activate',
  activatePosix: 'source .venv/bin/activate',
  install: 'pip install -e ".[dev,security]"',
  verify: 'python --version\npython -c "import app.main, sdk.intentlock; print(\'imports ok\')"\npython -m pip check',
  usage: 'python scripts/pilot_demo_v1.py',
  server: 'uvicorn app.main:app --reload --host 0.0.0.0 --port 8000',
  upgrade: 'git pull\npip install -e ".[dev,security]"',
  uninstall: 'pip uninstall intentlock',
} as const;

export const TERMINAL_STATUS = {
  validated: [
    'Windows 10/11 x64, NTFS, non-elevated shell, Python 3.11.9 (declared range 3.11–3.14).',
    'Install, recovery and independent byte-exact verification exercised end-to-end on this platform.',
    'Package name `intentlock` 4.0.0, installed editable from a checkout — it is not published to PyPI.',
    'No console script: the interfaces are Python, the SDK, `scripts/`, and the FastAPI app.',
  ],
  pending: [
    'macOS (arm64) and Linux: declared by package metadata, native validation still in progress.',
    'Windows ARM64: untested — no hardware, so no evidence in any form.',
    'A local wheel can be built and verified, but nothing is hosted: publishing requires explicit release authorization.',
  ],
  commonErrors: [
    {
      error: '`pip install -e ".[dev,security]"` fails resolving a dependency',
      fix: 'Stop and report it rather than improvising a workaround — the install path is itself part of what the beta validates. See troubleshooting.',
      href: '/docs/troubleshooting',
      linkLabel: 'Troubleshooting guide',
    },
    {
      error: '`python` is 3.10 or older, or 3.15+',
      fix: 'The declared range is `>=3.11,<3.15`; 3.11.9 is the verified interpreter. Recreate the virtual environment with a supported interpreter.',
      href: '/docs/installation',
      linkLabel: 'Installation doc',
    },
    {
      error: 'ModuleNotFoundError: No module named `app`',
      fix: 'The editable install was skipped or the virtual environment is not active. Re-run step 3 inside the activated environment.',
      href: '/docs/installation',
      linkLabel: 'Installation doc',
    },
  ],
} as const;
