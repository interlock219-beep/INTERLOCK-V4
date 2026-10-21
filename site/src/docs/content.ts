/**
 * Documentation content.
 *
 * Every command and behaviour described here was checked against the
 * repository (docs/operations/BETA_FIRST_RUN.md, docs/developer/QUICKSTART.md,
 * docs/operations/SUPPORTED_PLATFORMS.md, docs/operations/SAFETY_AND_LIMITATIONS.md,
 * pyproject.toml) before being written down. No command in this file is
 * invented: if an interface does not exist, the article says so.
 */

export type Block =
  | { kind: 'p'; text: string }
  | { kind: 'h2'; id: string; text: string }
  | { kind: 'h3'; id: string; text: string }
  | { kind: 'ul'; items: string[] }
  | { kind: 'ol'; items: string[] }
  | { kind: 'code'; code: string; language?: string; filename?: string }
  | { kind: 'callout'; type: 'info' | 'warn' | 'danger' | 'tip'; title?: string; text: string }
  | { kind: 'table'; head: string[]; rows: string[][] };

export interface DocArticle {
  slug: string;
  title: string;
  summary: string;
  group: string;
  blocks: Block[];
}

const REPO = 'https://github.com/interlock219-beep/INTERLOCK-V4';

export const DOC_GROUPS = [
  'Getting started',
  'Recovery',
  'Safety & limitations',
  'Reference',
] as const;

export const DOCS: DocArticle[] = [
  {
    slug: 'introduction',
    title: 'Introduction',
    summary: 'What Interlock is, how it fits into an AI agent workflow, and what it deliberately does not do.',
    group: 'Getting started',
    blocks: [
      {
        kind: 'p',
        text: 'Interlock is a Python control plane for AI agent actions. It records what an agent did to a resource before and after the action, can surgically undo a bad file modification byte-exactly, refuses to overwrite human edits made afterwards, and independently verifies the resulting state.',
      },
      { kind: 'p', text: 'The product name in the repository is `intentlock` (version 4.0.0); the release line is Interlock V6.' },
      { kind: 'h2', id: 'three-jobs', text: 'Three jobs, in order' },
      {
        kind: 'ol',
        items: [
          '**Observe** — capture before/after state references, tool, resource, risk score and authority context for every protected action.',
          '**Recover** — generate a compensation from the captured evidence and apply it through a staged, atomic swap confined to the configured project directory.',
          '**Verify** — re-read the result, compare digests against the captured evidence, and fail closed with typed errors on any mismatch.',
        ],
      },
      {
        kind: 'callout',
        type: 'info',
        title: 'Control. Contain. Recover. Verify.',
        text: 'Recovery is the visible feature, but verification is the one that makes it trustworthy: a recovery claim without an independent check is only a promise.',
      },
      { kind: 'h2', id: 'what-it-is-not', text: 'What Interlock is not' },
      {
        kind: 'ul',
        items: [
          'Not a backup daemon — it can only restore states it captured before the action.',
          'Not a database recovery tool — migration paths carry known, documented defects and are out of beta scope.',
          'Not a hosted service — there is no sign-in, no dashboard, no API keys to register for.',
          'Not production-ready — the release-readiness report marks general availability as NOT READY.',
          'Not a replacement for version control or your own independent backups.',
        ],
      },
      { kind: 'h2', id: 'where-to-start', text: 'Where to start' },
      {
        kind: 'ul',
        items: [
          'New here? Run the [interactive demo](/demo) — a browser-only simulation of the whole workflow.',
          'Ready to try it? Follow [Installation](/docs/installation) on a disposable project.',
          'Careful reader? Start with [Safety model](/docs/safety-model) and [Limitations](/docs/limitations).',
        ],
      },
      {
        kind: 'callout',
        type: 'warn',
        title: 'Beta scope',
        text: 'The supported scope today is byte-exact filesystem recovery on disposable projects, on Windows x64. Everything else is declared, untested, or explicitly unsupported.',
      },
    ],
  },
  {
    slug: 'installation',
    title: 'Installation',
    summary: 'The only supported install path: clone, virtual environment, editable install with the dev and security extras.',
    group: 'Getting started',
    blocks: [
      {
        kind: 'p',
        text: 'There is no PyPI package, no installer, and no container image published for Interlock. Installation is from a checkout of the public repository.',
      },
      { kind: 'h2', id: 'prerequisites', text: 'Prerequisites' },
      {
        kind: 'ul',
        items: [
          'Python `>=3.11,<3.15` — 3.11.9 is the verified version.',
          '`git` and `pip`.',
          'About 2 GB of free disk for the virtual environment.',
          'Windows x64 on NTFS is the tested primary platform.',
          'Not required: Docker, PostgreSQL, Redis, admin/root, network access at run time.',
        ],
      },
      { kind: 'h2', id: 'install', text: 'Install' },
      {
        kind: 'code',
        language: 'bash',
        code: `git clone ${REPO}.git\ncd INTERLOCK-V4\n\npython -m venv .venv\n.venv\\Scripts\\activate        # Windows\n# source .venv/bin/activate   # macOS/Linux\n\npip install -e ".[dev,security]"`,
      },
      {
        kind: 'callout',
        type: 'danger',
        title: 'Do not improvise workarounds',
        text: 'If `pip install` fails, stop and report it. The install path is part of what the controlled beta validates — a workaround hides the failure instead of fixing it.',
      },
      { kind: 'h2', id: 'verify', text: 'Verify the install' },
      {
        kind: 'code',
        language: 'bash',
        code: `python --version                        # 3.11.x or newer, below 3.15\npython -c "import app.main, sdk.intentlock; print('imports ok')"   # imports ok\npython -m pip check                      # No broken requirements found`,
      },
      { kind: 'h2', id: 'first-run', text: 'First run' },
      {
        kind: 'code',
        language: 'bash',
        code: 'python scripts/pilot_demo_v1.py',
      },
      {
        kind: 'p',
        text: 'The demo runs in a fresh temp directory it deletes afterwards, touches no repository file, makes no network call, and writes a versioned evidence file under `logs/v6_pilot_demo_v1/`.',
      },
      {
        kind: 'code',
        language: 'json',
        filename: 'observed output',
        code: `{
  "verdicts": {
    "recovery": true,
    "safety": true,
    "human_change": true,
    "idempotency": true
  },
  "overall_pass": true,
  "exit_code": 0
}`,
      },
      { kind: 'h2', id: 'troubleshooting', text: 'If something goes wrong' },
      { kind: 'p', text: 'See [Troubleshooting](/docs/troubleshooting) for the common failure modes and what to include in a report.' },
    ],
  },
  {
    slug: 'quickstart',
    title: 'Quick start',
    summary: 'From a fresh checkout to a verified recovery on a disposable project.',
    group: 'Getting started',
    blocks: [
      { kind: 'p', text: 'This walkthrough follows the controlled-beta first-run guide. Every command in it was executed on the reference host before being documented.' },
      { kind: 'h2', id: 'step-1', text: '1. Install' },
      { kind: 'p', text: 'Follow [Installation](/docs/installation), then confirm the three sanity checks pass.' },
      { kind: 'h2', id: 'step-2', text: '2. Run the safe demo' },
      { kind: 'code', language: 'bash', code: 'python scripts/pilot_demo_v1.py' },
      { kind: 'p', text: 'Four verdicts must be `true`: recovery, safety, human_change, idempotency. If any is false, stop and report it.' },
      { kind: 'h2', id: 'step-3', text: '3. Trigger one supported failure on your own disposable file' },
      {
        kind: 'p',
        text: 'The recipe below is the validated hands-on snippet: it creates a disposable directory, records pre-action evidence, simulates an agent overwrite, recovers, and then verifies with an independent hash.',
      },
      {
        kind: 'code',
        language: 'python',
        filename: 'beta_recipe.py (abridged)',
        code: `from app.infrastructure.recovery.filesystem_recovery_adapter import (
    FilesystemRecoveryAdapter,
)
\nadapter = FilesystemRecoveryAdapter(base_path=work)
pre = await adapter.capture_recovery_evidence(action)     # ORIGINAL bytes\n# ... agent "fault": target.write_bytes(b"AGENT OVERWROTE THIS FILE")\nevidence = await adapter.capture_recovery_evidence(action, before_snapshot=before)\ncompensation = await adapter.generate_compensation(action, evidence)\nresult = await adapter.execute_compensation(compensation, evidence.idempotency_key)\nassert target.read_bytes() == original                     # independent check`,
      },
      {
        kind: 'callout',
        type: 'tip',
        title: 'Verify with your own tool',
        text: 'Use `Get-FileHash` (PowerShell) or `sha256sum` (Linux/macOS) on the restored file. Adapter claims are never trusted by the harness, and you should not trust them either.',
      },
      { kind: 'h2', id: 'step-4', text: '4. Confirm nothing else moved' },
      {
        kind: 'code',
        language: 'python',
        code: "names = sorted(p.name for p in work.iterdir())\nassert names == ['config.yaml']   # no staging residue",
      },
      { kind: 'h2', id: 'step-5', text: '5. Run the regression subset' },
      {
        kind: 'code',
        language: 'bash',
        code: `pytest tests/unit/test_recovery_fault_injection.py \\\n       tests/unit/test_backup_restore_drill.py \\\n       tests/unit/test_filesystem_recovery_adapter.py \\\n       tests/integration/test_alembic_migration_safety.py \\\n       tests/integration/test_scenario_proofs_v6.py -q`,
      },
      { kind: 'p', text: 'Reference-host result (2026-10-18): `60 passed, 2 skipped, 4 xfailed`. The skips are Windows symlink-privilege skips; the four xfails are the documented migration defects, which are meant to stay visible.' },
      { kind: 'callout', type: 'warn', title: 'Stop conditions', text: 'If anything changes outside your disposable directory, a network attempt occurs, secrets appear in output, or the same crash repeats twice — stop and report it.' },
    ],
  },
  {
    slug: 'how-recovery-works',
    title: 'How recovery works',
    summary: 'Evidence capture, compensation generation, staged atomic restore and the execution states you will see.',
    group: 'Recovery',
    blocks: [
      { kind: 'p', text: 'Interlock is evidence-driven. Recovery is only possible for states it captured before the action ran — there is no heuristic reconstruction of “what the file probably looked like”.' },
      { kind: 'h2', id: 'pipeline', text: 'The pipeline' },
      { kind: 'ol', items: [
        '**Capture** — before the action executes, the adapter records a before-snapshot (content hash, size, timestamps, mode) for each target.',
        '**Attribute** — the action is stored with tool, resource, reversibility class, risk score and correlation identifiers.',
        '**Plan** — a compensation is generated from the evidence: which files to restore, which to skip and why.',
        '**Gate** — preconditions are evaluated: evidence present, path inside the confinement boundary, no drift at the target.',
        '**Restore** — content is written to a staging file created *in the target directory*, then swapped with `os.replace`.',
        '**Verify** — the target is re-read, digests are recomputed and compared, and the result is typed.',
      ] },
      { kind: 'h2', id: 'atomicity', text: 'Why staging + os.replace' },
      { kind: 'p', text: 'Staging files are created in the same directory as the target (named `*.recovery_tmp`) and swapped with `os.replace`, which is atomic on the same volume for NTFS, APFS and ext4. Cross-device swaps cannot occur by construction, so a crash mid-restore never leaves partial bytes at your target — at worst a staging file is left behind.' },
      {
        kind: 'callout',
        type: 'info',
        title: 'Real crash evidence',
        text: 'A real process-kill drill ran 20 times on Windows with zero torn writes and zero invariant violations. That evidence covers Windows only.',
      },
      { kind: 'h2', id: 'execution-states', text: 'Execution states' },
      { kind: 'table', head: ['State', 'Meaning'], rows: [
        ['succeeded', 'Restore applied and verified against captured evidence.'],
        ['blocked_by_conflict', 'Current content differs from the expected state; the file was left untouched.'],
        ['refused', 'A precondition failed: path outside the boundary, missing evidence, or a malformed backup.'],
        ['verification_failed', 'Typed fail-closed result; evidence is preserved for inspection.'],
        ['interrupted', 'The operation did not complete. Verify before making any claim about the result.'],
      ] },
      { kind: 'h2', id: 'adapters', text: 'Adapters' },
      { kind: 'p', text: 'The adapter protocol is shared by filesystem, git, config, database-record and mock adapters under `app/infrastructure/recovery/`. Each adapter implements capture, compensation generation, execution and verification for its own resource type; the filesystem adapter is the one exercised by the controlled beta.' },
      { kind: 'callout', type: 'warn', title: 'Not covered', text: 'Database and migration recovery carry known defects (D-MIG-1b and friends) and are explicitly out of beta scope.' },
    ],
  },
  {
    slug: 'verification',
    title: 'Verification',
    summary: 'How results are checked, why adapter claims are not trusted, and how to verify independently.',
    group: 'Recovery',
    blocks: [
      { kind: 'p', text: 'Verification is the step that turns a recovery attempt into a known state. It re-reads the target content and compares it against the digests recorded in the evidence manifest.' },
      { kind: 'h2', id: 'independent', text: 'Independent by design' },
      { kind: 'ul', items: [
        'The harness never trusts an adapter’s success flag; it recomputes SHA-256 from the bytes on disk.',
        'Verification failure is a typed, fail-closed error — not a warning buried in a log.',
        'Error messages are content-free by design: a regression test asserts that secrets never appear in them. They do contain file names, so redact paths if your filenames are sensitive.',
        'Evidence is preserved after a failure so you can inspect what happened.',
      ] },
      { kind: 'h2', id: 'do-it-yourself', text: 'Verify it yourself' },
      { kind: 'code', language: 'powershell', filename: 'Windows', code: '(Get-FileHash .\\config.yaml -Algorithm SHA256).Hash' },
      { kind: 'code', language: 'bash', filename: 'macOS / Linux', code: 'sha256sum ./config.yaml' },
      { kind: 'p', text: 'Compare the digest with the value recorded in your evidence file. Content-based checks, not trust-based ones.' },
      { kind: 'h2', id: 'what-it-proves', text: 'What verification proves — and what it does not' },
      { kind: 'table', head: ['Proves', 'Does not prove'], rows: [
        ['The file bytes now match the captured pre-action snapshot.', 'That the snapshot was the state you actually wanted.'],
        ['No unintended content remains at the target.', 'That nothing outside the confinement boundary changed.'],
        ['Staging residue is absent (or reported).', 'That an unrelated process is not concurrently writing the same file.'],
      ] },
      { kind: 'callout', type: 'tip', title: 'In the demo', text: 'The [interactive demo](/demo) computes digests over its fictional files in your browser and only shows “verified” when the comparison passes — try the interrupted scenario to see a failed check.' },
    ],
  },
  {
    slug: 'conflict-handling',
    title: 'Conflict handling',
    summary: 'Why `blocked_by_conflict` is a success condition, how drift is detected, and what to do next.',
    group: 'Recovery',
    blocks: [
      { kind: 'p', text: 'A conflict means the current content of a target differs from the state the recovery plan expects — usually because a human edited the file after the agent acted.' },
      { kind: 'h2', id: 'detection', text: 'How drift is detected' },
      { kind: 'ul', items: [
        'Content-hash compare of the current bytes against the expected pre-restore state.',
        '`exists()` and `is_symlink()` guards immediately before the swap.',
        'Symlink containment checks so a planted link cannot move the write outside the boundary.',
      ] },
      { kind: 'h2', id: 'behaviour', text: 'What happens' },
      { kind: 'ol', items: [
        'The file is **not** written. Current content stays byte-for-byte as it is.',
        'The compensation result is typed `blocked_by_conflict`.',
        'A duplicate delivery of the same compensation is likewise refused — never double-applied.',
        'You decide: review the human edit, re-plan, or reset.',
      ] },
      {
        kind: 'callout',
        type: 'tip',
        title: 'Treat it as a feature',
        text: '`blocked_by_conflict` means a human or external change is being preserved. It is not recovery failing — it is recovery declining to destroy work it does not understand.',
      },
      { kind: 'h2', id: 'known-window', text: 'A known, documented window' },
      { kind: 'p', text: 'There is a micro-second TOCTOU window between the existence check and `os.replace`. A file appearing exactly in that window would be replaced. The design assumes a single writer; concurrent-writer behaviour is mocked-only in tests and is listed as an unverified scenario.' },
      { kind: 'h2', id: 'in-the-demo', text: 'See it in the browser' },
      { kind: 'p', text: 'Scenario B of the [interactive demo](/demo) is exactly this case: a developer edits `src/config.ts` after the agent, the pre-flight check finds the drift, and the normal recovery path is blocked until you review or reset.' },
    ],
  },
  {
    slug: 'safety-model',
    title: 'Safety model',
    summary: 'Confinement, preconditions, refusal conditions and the fail-closed principles behind them.',
    group: 'Safety & limitations',
    blocks: [
      { kind: 'p', text: 'Interlock is designed so that the unsafe answer is the unreachable one: when a precondition cannot be proven, the operation refuses rather than guesses.' },
      { kind: 'h2', id: 'confinement', text: 'Confinement' },
      { kind: 'ul', items: [
        'Reads and writes only inside the configured project directory.',
        'Path normalisation rejects traversal such as `file:../outside.txt` with zero side effects.',
        'Staging refuses to follow planted symlinks (`O_EXCL` plus a pre-unlink).',
        'No network sockets are opened during the tested recovery workflow.',
        'No telemetry exists; nothing is collected automatically.',
      ] },
      { kind: 'h2', id: 'preconditions', text: 'Preconditions that block a plan' },
      { kind: 'table', head: ['Precondition', 'Behaviour when it fails'], rows: [
        ['Pre-action evidence exists for the target', 'Plan refused — restoring without evidence would mean inventing content.'],
        ['Target path resolves inside the confinement boundary', 'Refused with a typed error; no side effects.'],
        ['Current bytes match the expected pre-restore state', 'Typed `blocked_by_conflict`; the file is untouched.'],
        ['Backup manifest is well-formed and untampered', 'Import fails closed with a typed error; 19 fault-injection drills cover this.'],
        ['Idempotency key has not already been applied', 'Duplicate delivery refused — never double-applied.'],
      ] },
      { kind: 'h2', id: 'fail-closed', text: 'Fail closed, keep evidence' },
      { kind: 'p', text: 'Verification failures produce typed errors and preserve the evidence for inspection. There is no “best effort success” path: a mismatch is reported as a mismatch, even when that means the overall run fails.' },
      { kind: 'callout', type: 'danger', title: 'Never bypass a refusal', text: 'If Interlock refuses, the correct response is to investigate — not to re-run with the check disabled. A refusal you have to argue your way past provides no protection.' },
      { kind: 'h2', id: 'permissions', text: 'Permissions and elevation' },
      { kind: 'p', text: 'Ordinary user read/write only: no admin/root, no registry edits, no services, no cron, no firewall changes. Backup artifacts use default umask on POSIX — a known open item (proposal R17) with POSIX tests that skip on Windows by design.' },
      { kind: 'h2', id: 'reporting', text: 'Reporting a safety problem' },
      { kind: 'p', text: 'Security reports go to the address in `SECURITY.md` (`security@interlock.io`) or through the repository’s security advisory page. Include the exact step, the exact command and the complete error text — never source files, secrets or database dumps.' },
    ],
  },
  {
    slug: 'limitations',
    title: 'Limitations',
    summary: 'The honest list: what is untested, mocked-only, out of scope, or simply not claimed.',
    group: 'Safety & limitations',
    blocks: [
      { kind: 'callout', type: 'warn', title: 'Read this before installing', text: 'Nothing on this site or in this documentation should be read as a guarantee of recovery, zero data loss, or universal compatibility.' },
      { kind: 'h2', id: 'platform', text: 'Platform limits' },
      { kind: 'ul', items: [
        '**Windows x64 / NTFS / Python 3.11.9** — tested primary.',
        '**macOS, Linux** — declared, CI pending, no native validation recorded.',
        '**Windows ARM64** — untested, no hardware.',
        '**FAT32, exFAT, network shares, OneDrive-synced directories** — unsupported: no atomic-replace guarantee.',
        '**Paths longer than 260 characters on Windows** — untested; staging adds a 16-character suffix to target paths.',
        '**Python 3.12–3.14** — declared by package metadata, not locally verified.',
      ] },
      { kind: 'h2', id: 'capability', text: 'Capability limits' },
      { kind: 'ul', items: [
        'Recovery only for states captured before the action — no reconstruction from thin air.',
        'Database and migration recovery: known defects, out of beta scope.',
        'Real disk-full (ENOSPC) behaviour is mocked-only; the real drill is prepared but has never been authorised to run.',
        'POSIX symlink and permission drills have not executed on macOS/Linux.',
        'A micro-second TOCTOU window exists before the atomic swap; the design assumes a single writer.',
        'Manifest integrity is unkeyed SHA-256 — tamper-evidence, not tamper-proofing.',
      ] },
      { kind: 'h2', id: 'product', text: 'Product limits' },
      { kind: 'ul', items: [
        'No published package, installer, container image or release artifact.',
        'No web dashboard, no SSO/KMS integration, no hosted API.',
        'No account system — including on this website.',
        'No customer references, usage metrics or performance benchmarks are claimed, because none exist.',
      ] },
      { kind: 'callout', type: 'danger', title: 'Keep your own backup', text: 'Interlock complements version control; it does not replace it. Never point it at data you cannot afford to lose.' },
    ],
  },
  {
    slug: 'troubleshooting',
    title: 'Troubleshooting',
    summary: 'Common failures, safe next steps, and how to file a report that does not expose your project.',
    group: 'Safety & limitations',
    blocks: [
      { kind: 'h2', id: 'install-fails', text: '`pip install -e ".[dev,security]"` fails' },
      { kind: 'p', text: 'Stop and report it — do not improvise a workaround. Include your OS, `python --version`, the exact command and the complete error text. The install path itself is part of what the beta validates.' },
      { kind: 'h2', id: 'import-error', text: 'Import errors after install' },
      { kind: 'code', language: 'bash', code: `python -c "import app.main, sdk.intentlock; print('imports ok')"\npython -m pip check` },
      { kind: 'p', text: 'If `pip check` reports broken requirements, your environment has conflicting pins — recreate the virtual environment rather than forcing packages.' },
      { kind: 'h2', id: 'blocked', text: 'Result is `blocked_by_conflict`' },
      { kind: 'p', text: 'Expected behaviour when a human edit landed after the agent action, or when a duplicate delivery arrives. Inspect the file, decide which content you want, and re-plan. Nothing was changed by the refused run.' },
      { kind: 'h2', id: 'permission', text: 'Permission denied during the swap' },
      { kind: 'p', text: 'A real permission-denial drill is part of the evidence set and behaves as designed: the failure is typed and the target is not corrupted. Check whether the file is locked by another process or owned by a different user.' },
      { kind: 'h2', id: 'staging-left', text: 'A `*.recovery_tmp` file is left behind' },
      { kind: 'p', text: 'That is the intended crash behaviour: a staging file instead of partial bytes at your target. Verify the target content first, then remove the staging file manually.' },
      { kind: 'h2', id: 'symlink-skips', text: 'Tests skip on Windows' },
      { kind: 'p', text: 'The symlink-escape drills skip in unprivileged Windows shells and the POSIX permission tests skip on Windows by design. Skips are recorded as skips — never reported as passes.' },
      { kind: 'h2', id: 'reporting', text: 'What to send in a report' },
      { kind: 'ol', items: [
        'OS and `python --version` output, plus the checkout commit.',
        'The exact step number and the exact command you ran.',
        'The complete error text (messages contain file names and IDs, not file contents).',
        'For backup/restore tests: `manifest.json` fields and artifact SHA-256 digests — not the snapshot files themselves.',
        'Whether the failure reproduces.',
      ] },
      { kind: 'callout', type: 'danger', title: 'Do not send', text: 'Source files, `.env` values, database dumps, or full `logs/` directories without review. If in doubt, leave it out.' },
    ],
  },
  {
    slug: 'supported-platforms',
    title: 'Supported platforms',
    summary: 'The bounded support matrix: tested, declared, untested and unsupported — with the reason for each.',
    group: 'Reference',
    blocks: [
      { kind: 'p', text: 'A “supported” row means the declared controlled-beta scope (filesystem-family recovery on disposable projects) has been exercised end-to-end: install → recovery → independent byte-exact verification.' },
      { kind: 'h2', id: 'matrix', text: 'Matrix' },
      { kind: 'table', head: ['Platform', 'Python', 'Status', 'Basis'], rows: [
        ['Windows x64 / NTFS', '3.11.9 verified', 'TESTED — PRIMARY', 'Full suite 2922 passed; real kill 20/20; real permission-denial PASS; wheel install verified.'],
        ['Windows ARM64', '3.11+ declared', 'UNTESTED', 'No hardware available.'],
        ['Windows, long paths (>260)', '3.11.9', 'UNTESTED', 'Staging adds a 16-char suffix; requires LongPathsEnabled.'],
        ['FAT32 / exFAT / network dirs', '3.11.9', 'UNSUPPORTED', 'Rename durability and atomicity not guaranteed.'],
        ['Linux x64 / ext4', '3.11–3.14 declared', 'DECLARED — CI PENDING', 'Encoded in the CI matrix; no native execution recorded.'],
        ['macOS arm64 / APFS', '3.11–3.14 declared', 'DECLARED — CI PENDING', 'Encoded in the CI matrix; no native execution recorded.'],
        ['macOS x64 / APFS', '3.11–3.14 declared', 'UNTESTED', 'No evidence in any form.'],
      ] },
      { kind: 'h2', id: 'python', text: 'Declared Python range' },
      { kind: 'p', text: '`requires-python = ">=3.11,<3.15"` — that is 3.11 through 3.14. Only 3.11.9 has been locally verified; the others must not be described as tested until matrix cells are green with recorded runs.' },
      { kind: 'h2', id: 'behaviour', text: 'Platform-dependent behaviour' },
      { kind: 'ul', items: [
        'Atomicity: staging files are created in the target directory and swapped with `os.replace` — same-volume atomic on NTFS/APFS/ext4.',
        'Permissions: staging opened with `0o600`, recorded-mode-only restore, backup `0o700`/`0o600` POSIX-guarded — asserted on POSIX only.',
        'Symlinks: escaping drills execute where symlink creation is permitted (POSIX runners; Windows needs elevation).',
        'Timestamps: capture stores both float and nanosecond keys; both restore paths are live.',
        'Case sensitivity: the engine compares bytes and hashes, not names.',
        'Unicode and long paths: `pathlib` throughout; content travels as base64, so encoding is independent.',
      ] },
      { kind: 'h2', id: 'excluded', text: 'What “supported” excludes everywhere' },
      { kind: 'p', text: 'Production databases, migrations, in-use files, live-user data, cross-device moves, network shares, and any promise of zero data loss.' },
    ],
  },
  {
    slug: 'cli-api',
    title: 'CLI & API reference',
    summary: 'The interfaces that actually exist: Python API, SDK, REST endpoints and scripts — and the ones that do not.',
    group: 'Reference',
    blocks: [
      {
        kind: 'callout',
        type: 'info',
        title: 'One console command',
        text: 'Installing the package from source also provides the `interlock` command (the Terminal Runner). It is a thin layer over the same engine the VS Code extension drives; it is not published as a standalone binary.',
      },
      { kind: 'h2', id: 'python', text: 'Python API' },
      { kind: 'code', language: 'python', code: `from app.infrastructure.recovery.filesystem_recovery_adapter import (
    FilesystemRecoveryAdapter,
)\n\nadapter = FilesystemRecoveryAdapter(base_path=work)\npre = await adapter.capture_recovery_evidence(action)\nevidence = await adapter.capture_recovery_evidence(action, before_snapshot=before)\ncompensation = await adapter.generate_compensation(action, evidence)\nresult = await adapter.execute_compensation(compensation, evidence.idempotency_key)\nprint(result.success, result.execution_state.value)`,
      },
      { kind: 'h2', id: 'sdk', text: 'SDK' },
      { kind: 'code', language: 'python', code: `from sdk.intentlock import IntentLockGuard, SecurityError, guard_tool\n\nclient = IntentLockGuard(\n    base_url="http://localhost:8000/api/v1/intent/verify",\n    execute_url="http://localhost:8000/api/v1/intent/execute",\n    auth_token="<access_token>",\n)\n\n@guard_tool(client)\ndef query_database(query: str, user_prompt: str = "Database query", agent_id: str = "agent-001") -> str:\n    return "results"`,
      },
      { kind: 'p', text: 'A LangChain wrapper lives at `sdk/langchain_adapter.py`. SDK reference: `sdk/README.md` in the repository.' },
      { kind: 'h2', id: 'rest', text: 'REST endpoints' },
      { kind: 'code', language: 'bash', code: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000\ncurl http://localhost:8000/api/v1/health   # {"status":"ok"}\ncurl http://localhost:8000/api/v1/ready    # {"status":"ready","db":"ok","redis":"disabled"}` },
      { kind: 'p', text: 'While the app is running, the generated OpenAPI schema is served at `/docs`. An `openapi_snapshot.json` is kept in the repository for diffing the surface between releases.' },
      { kind: 'h2', id: 'scripts', text: 'Scripts' },
      { kind: 'table', head: ['Script', 'Purpose'], rows: [
        ['`scripts/pilot_demo_v1.py`', 'Safe, disposable demonstration with four verdicts.'],
        ['`scripts/run_benchmarks.py`', 'Benchmark harness (frozen; requires separate authorisation to run).'],
        ['`scripts/generate_sbom.py`', 'SBOM generation for the release gate.'],
        ['`scripts/seed_plans.py`', 'Seed sample recovery plans for local development.'],
      ] },
      { kind: 'h2', id: 'does-not-exist', text: 'Interfaces that are not published' },
      { kind: 'ul', items: [
        'No published package on PyPI or npm - the package installs from a checkout.',
        'No hosted API, webhooks, or dashboard.',
        'No published VS Code extension: the source is in the repository and builds locally, but there is no Marketplace listing, download or published checksum.',
        'No sign-in system on this website.',
      ] },
    ],
  },
  {
    slug: 'beta-guidance',
    title: 'Beta guidance',
    summary: 'Who the controlled beta is for, how to run it safely, and how results are reported.',
    group: 'Reference',
    blocks: [
      { kind: 'p', text: 'The controlled beta tests one thing: byte-exact filesystem recovery for AI-agent file modifications, on disposable projects, on Windows x64.' },
      { kind: 'h2', id: 'in-out', text: 'In scope / out of scope' },
      { kind: 'table', head: ['In scope', 'Out of scope'], rows: [
        ['Byte-exact filesystem recovery on files you create for the test', 'Database or migration operations (`alembic upgrade/downgrade`)'],
        ['Conflict protection, idempotent replay, traversal refusal', 'Production systems, real projects, valuable databases'],
        ['Reporting problems safely', 'Performance benchmarking; SSO/KMS; web dashboard; PostgreSQL paths'],
      ] },
      { kind: 'h2', id: 'safe-testing', text: 'Safe testing practices' },
      { kind: 'ul', items: [
        'Work only in a fresh clone and a disposable directory you create.',
        'Never point Interlock at anything you cannot afford to lose.',
        'Verify recoveries independently with your own hash tool.',
        'Watch for network attempts — none should occur in the tested workflow; if one does, stop and report.',
        'You may stop at any time; partial results still help.',
      ] },
      { kind: 'h2', id: 'privacy', text: 'Privacy' },
      { kind: 'ul', items: [
        'No telemetry exists; nothing is collected automatically.',
        'You are not asked for credentials, source code, database dumps or full logs.',
        'Interlock reads and writes only inside the directory you point it at, plus a local evidence file under `logs/`.',
        'This website collects nothing: no analytics, no cookies, no forms that transmit data.',
      ] },
      { kind: 'h2', id: 'report', text: 'Reporting template' },
      { kind: 'code', language: 'text', code: `Slot: T1/T2/T3\nOS / python --version: _\nCheckout commit: _\nStep that failed: _\nExact command: _\nExact error text: _\nReproducible (yes/no, N attempts): _\nFiles created outside your disposable dir (yes/no): _\nNetwork attempts observed (yes/no): _\nInstall / demo duration: _\nClarity notes (what confused you): _` },
      { kind: 'h2', id: 'apply', text: 'How to apply' },
      { kind: 'p', text: 'Open an issue on the repository with the template above, or contact the coordinator through the channel you received the invitation package from. See the [beta page](/beta) for the full description of what you are signing up for.' },
      { kind: 'callout', type: 'warn', title: 'Stop immediately if…', text: 'Anything changes outside your disposable directory, a network attempt occurs, secrets appear in output, the same crash happens twice, or data you did not deliberately sacrifice is damaged.' },
    ],
  },
];

export const DOC_INDEX = DOCS.map((doc) => ({
  slug: doc.slug,
  title: doc.title,
  summary: doc.summary,
  group: doc.group,
}));

export function getDoc(slug: string | undefined): DocArticle | undefined {
  return DOCS.find((doc) => doc.slug === slug);
}

/** Plain text of an article, used for client-side search. */
export function docPlainText(doc: DocArticle): string {
  const parts: string[] = [doc.title, doc.summary];
  doc.blocks.forEach((block) => {
    switch (block.kind) {
      case 'p':
      case 'h2':
      case 'h3':
        parts.push(block.text);
        break;
      case 'ul':
      case 'ol':
        parts.push(...block.items);
        break;
      case 'callout':
        parts.push(block.title ?? '', block.text);
        break;
      case 'code':
        parts.push(block.code);
        break;
      case 'table':
        parts.push(...block.head, ...block.rows.flat());
        break;
      default:
        break;
    }
  });
  return parts.join(' ').toLowerCase();
}
