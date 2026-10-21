/**
 * First-run recovery-engine installation.
 *
 * Distribution strategy (chosen after inspecting the repository):
 *   - The engine's runtime import closure (the six modules the bridge
 *     imports, plus everything they reach) is standard-library-only Python,
 *     proven by running the full command surface in a bare virtual
 *     environment. The VSIX therefore deliberately bundles exactly that
 *     closure under `engine/`, with a build-time SHA-256 manifest
 *     (`engine/manifest.json`) identifying every file.
 *   - Installation creates ONE isolated virtual environment under the
 *     extension's global storage and runs a real `probe` health check
 *     through the bundled bridge before anything is reported ready.
 *   - Nothing is downloaded. There is no URL, no pip install, no PyPI and no
 *     network module anywhere in this file; the only subprocesses are
 *     argument-array spawns through `runner.ts` (allow-listed environment,
 *     timeout, output caps, external cancellation).
 *   - This module never receives a workspace path: installation cannot read
 *     or write project files by construction.
 *
 * The module deliberately does NOT import `vscode` so every path is
 * unit-testable; the CommandHost wires it to the extension context.
 */

import { createHash } from 'crypto';
import * as fs from 'fs';
import * as path from 'path';

import { redact } from './redact';
import { RunOptions, RunResult, runProcess } from './runner';

export const BUNDLE_FORMAT = 'interlock-engine-bundle-v1';
export const INSTALL_FORMAT = 'interlock-engine-install-v1';

// --------------------------------------------------------------------- types

export type SetupStatus =
  | 'ready'
  | 'checking'
  | 'missing'
  | 'installing'
  | 'installed'
  | 'incomplete'
  | 'failed'
  | 'python-missing';

export type SetupPhase = '' | 'requirements' | 'engine-files' | 'environment' | 'verifying' | 'ready';

/** Ordered progress phases shown on the setup screen (identifiers). */
export const SETUP_PHASES: SetupPhase[] = [
  'requirements',
  'engine-files',
  'environment',
  'verifying',
  'ready',
];

export interface SetupState {
  /** `ready` hides the setup screen; every other value shows it. */
  status: SetupStatus;
  /** Current progress phase (only while `installing`/`checking`). */
  phase: SetupPhase;
  /** One plain-language sentence for the current state. */
  message: string;
  /** Plain-language failure cause, `null` when nothing failed. */
  error: string | null;
  version: string | null;
  python: string | null;
  engineRoot: string | null;
  venvPython: string | null;
  treeSha: string | null;
  /** Expandable diagnostic lines (already redacted). */
  technical: string[];
}

export interface EngineBundle {
  format: string;
  engineVersion: string;
  requiresPython: string;
  fileCount: number;
  treeSha256: string;
  files: Record<string, string>;
}

export interface InstallRecord {
  format: string;
  engineVersion: string;
  envKey: string;
  venvPython: string;
  pythonBase: string;
  installedAt: string;
  verifiedAt: string;
  bundleTreeSha256: string;
  status: 'ready';
  /** Previous managed environment kept for rollback, when one existed. */
  previous?: { engineVersion: string; envKey: string; venvPython: string };
}

export type Runner = (options: RunOptions) => Promise<RunResult>;

export interface PythonCandidate {
  command: string;
  /** Arguments inserted before `-c` (for the Windows `py` launcher). */
  prefix: string[];
  source: string;
}

export interface PythonProbe {
  command: string;
  prefix: string[];
  version: string;
  source: string;
}

export const PYTHON_PROBE_CODE = [
  'import json,platform,sys',
  'print(json.dumps({"version":platform.python_version(),"executable":sys.executable}))',
].join(';');

const VENV_TIMEOUT_MS = 240_000;
const PROBE_TIMEOUT_MS = 15_000;
const HEALTH_TIMEOUT_MS = 60_000;

// ------------------------------------------------------------------- helpers

export function isSupportedPython(version: string | null): boolean {
  if (!version) {
    return false;
  }
  const match = /^(\d+)\.(\d+)/.exec(version);
  if (!match) {
    return false;
  }
  const major = Number(match[1]);
  const minor = Number(match[2]);
  return major === 3 && minor >= 11 && minor <= 14;
}

/** Relative location of the interpreter inside a virtual environment. */
export function venvPythonRelative(platform = process.platform): string {
  return platform === 'win32'
    ? path.join('venv', 'Scripts', 'python.exe')
    : path.join('venv', 'bin', 'python3');
}

export function sha256Hex(bytes: Buffer): string {
  return createHash('sha256').update(bytes).digest('hex');
}

/**
 * Deterministic tree fingerprint over the manifest's per-file hashes
 * (same construction as the bundle builder, kept in sync by unit test).
 */
export function treeSha256Of(files: Record<string, string>): string {
  const lines = Object.keys(files)
    .sort()
    .map((rel) => `${rel}\n${files[rel]}\n`)
    .join('');
  return createHash('sha256').update(lines, 'utf8').digest('hex');
}

// ------------------------------------------------------------ bundle verify

export function parseBundle(raw: string): EngineBundle | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return null;
  }
  const candidate = parsed as Record<string, unknown>;
  if (
    candidate['format'] !== BUNDLE_FORMAT ||
    typeof candidate['engineVersion'] !== 'string' ||
    typeof candidate['requiresPython'] !== 'string' ||
    typeof candidate['treeSha256'] !== 'string' ||
    typeof candidate['fileCount'] !== 'number' ||
    candidate['files'] === null ||
    typeof candidate['files'] !== 'object' ||
    Array.isArray(candidate['files'])
  ) {
    return null;
  }
  const files: Record<string, string> = {};
  for (const [rel, hash] of Object.entries(candidate['files'] as Record<string, unknown>)) {
    if (typeof hash !== 'string' || !/^[0-9a-f]{64}$/.test(hash)) {
      return null;
    }
    if (rel.includes('..') || path.isAbsolute(rel) || rel.includes('\\')) {
      return null;
    }
    files[rel] = hash;
  }
  if (Object.keys(files).length !== candidate['fileCount']) {
    return null;
  }
  return {
    format: BUNDLE_FORMAT,
    engineVersion: candidate['engineVersion'],
    requiresPython: candidate['requiresPython'],
    fileCount: candidate['fileCount'],
    treeSha256: candidate['treeSha256'],
    files,
  };
}

export function readBundle(engineDir: string): EngineBundle | null {
  try {
    return parseBundle(fs.readFileSync(path.join(engineDir, 'manifest.json'), 'utf8'));
  } catch {
    return null;
  }
}

export interface BundleVerification {
  bundle: EngineBundle | null;
  problems: string[];
  /** Per-file hashes of the verified tree (only when `problems` is empty). */
  files: Record<string, string> | null;
  treeSha256: string | null;
}

/**
 * Verify every bundled engine file against the manifest before any of it is
 * used: missing files, changed bytes, and unexpected extra `.py` files are
 * all hard failures. `__pycache__`/`.pyc` are interpreter by-products and
 * are ignored.
 */
export function verifyBundle(engineDir: string): BundleVerification {
  const bundle = readBundle(engineDir);
  if (!bundle) {
    return {
      bundle: null,
      problems: ['engine/manifest.json is missing or unreadable'],
      files: null,
      treeSha256: null,
    };
  }
  const problems: string[] = [];
  for (const [rel, expected] of Object.entries(bundle.files)) {
    const file = path.join(engineDir, ...rel.split('/'));
    let bytes: Buffer;
    try {
      bytes = fs.readFileSync(file);
    } catch {
      problems.push(`${rel}: file is missing`);
      continue;
    }
    const actual = sha256Hex(bytes);
    if (actual !== expected) {
      problems.push(`${rel}: content hash mismatch`);
    }
  }
  // Unexpected engine sources are suspicious: the manifest is the contract.
  const expectedSet = new Set(Object.keys(bundle.files));
  const walk = (dir: string, prefix: string): void => {
    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
      if (entry.isDirectory()) {
        if (entry.name === '__pycache__') {
          continue;
        }
        walk(path.join(dir, entry.name), rel);
        continue;
      }
      if (!rel.endsWith('.py')) {
        continue;
      }
      if (!expectedSet.has(rel)) {
        problems.push(`${rel}: unexpected engine file (not in manifest)`);
      }
    }
  };
  walk(engineDir, '');
  const recomputed = treeSha256Of(bundle.files);
  if (recomputed !== bundle.treeSha256) {
    problems.push('manifest tree fingerprint does not match its own file list');
  }
  return {
    bundle,
    problems,
    files: problems.length === 0 ? bundle.files : null,
    treeSha256: problems.length === 0 ? recomputed : null,
  };
}

// -------------------------------------------------------- install record IO

export function installRecordPath(storageDir: string): string {
  return path.join(storageDir, 'install.json');
}

export function readInstallRecord(storageDir: string): {
  record: InstallRecord | null;
  problem: string | null;
} {
  let raw: string;
  try {
    raw = fs.readFileSync(installRecordPath(storageDir), 'utf8');
  } catch (error) {
    const missing = (error as NodeJS.ErrnoException).code === 'ENOENT';
    return { record: null, problem: missing ? null : 'The installation record could not be read.' };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { record: null, problem: 'The installation record is damaged (invalid JSON).' };
  }
  if (
    parsed === null ||
    typeof parsed !== 'object' ||
    (parsed as Record<string, unknown>)['format'] !== INSTALL_FORMAT ||
    typeof (parsed as Record<string, unknown>)['engineVersion'] !== 'string' ||
    typeof (parsed as Record<string, unknown>)['envKey'] !== 'string' ||
    typeof (parsed as Record<string, unknown>)['venvPython'] !== 'string' ||
    typeof (parsed as Record<string, unknown>)['bundleTreeSha256'] !== 'string'
  ) {
    return { record: null, problem: 'The installation record has an unexpected shape.' };
  }
  return { record: parsed as InstallRecord, problem: null };
}

export function writeInstallRecord(storageDir: string, record: InstallRecord): void {
  fs.mkdirSync(storageDir, { recursive: true });
  const target = installRecordPath(storageDir);
  const tmp = `${target}.tmp`;
  fs.writeFileSync(tmp, `${JSON.stringify(record, null, 2)}\n`, 'utf8');
  fs.renameSync(tmp, target);
}

/**
 * The managed installation the bridge should use, when one exists and is
 * intact enough to spawn. Spot checks only (this runs on every command);
 * full verification happens at activation and install time.
 */
export function managedInstallation(opts: {
  engineDir: string;
  storageDir: string;
}): { engineRoot: string; pythonPath: string; version: string } | null {
  const { record } = readInstallRecord(opts.storageDir);
  if (!record || record.status !== 'ready') {
    return null;
  }
  if (!fs.existsSync(record.venvPython)) {
    return null;
  }
  if (!fs.existsSync(path.join(opts.engineDir, 'app', 'domain', '__init__.py'))) {
    return null;
  }
  return { engineRoot: opts.engineDir, pythonPath: record.venvPython, version: record.engineVersion };
}

// ---------------------------------------------------------------- python

/** Deterministic interpreter candidates: configured first, then PATH. */
export function pythonCandidates(
  configured: string,
  platform: string = process.platform,
): PythonCandidate[] {
  const candidates: PythonCandidate[] = [];
  if (configured.trim()) {
    candidates.push({ command: configured.trim(), prefix: [], source: 'interlock.pythonPath' });
  }
  if (platform === 'win32') {
    candidates.push({ command: 'python', prefix: [], source: 'python on PATH' });
    candidates.push({ command: 'py', prefix: ['-3'], source: 'py launcher' });
    candidates.push({ command: 'python3', prefix: [], source: 'python3 on PATH' });
  } else {
    candidates.push({ command: 'python3', prefix: [], source: 'python3 on PATH' });
    candidates.push({ command: 'python', prefix: [], source: 'python on PATH' });
  }
  return candidates;
}

export interface DetectPythonOptions {
  configured?: string;
  /** Override the candidate list (tests; also `[]` to force failure). */
  candidates?: PythonCandidate[];
  platform?: string;
  runner?: Runner;
  timeoutMs?: number;
}

export interface DetectPythonResult {
  probe: PythonProbe | null;
  /** One line per candidate that could not be used (for technical details). */
  problems: string[];
}

/** Find and validate a supported runtime (3.11-3.14) by really running it. */
export async function detectPython(options: DetectPythonOptions): Promise<DetectPythonResult> {
  const runner = options.runner ?? runProcess;
  const candidates =
    options.candidates ??
    pythonCandidates(options.configured ?? '', options.platform ?? process.platform);
  const problems: string[] = [];
  for (const candidate of candidates) {
    const attempt = await runner({
      command: candidate.command,
      args: [...candidate.prefix, '-c', PYTHON_PROBE_CODE],
      timeoutMs: options.timeoutMs ?? PROBE_TIMEOUT_MS,
      maxOutputBytes: 64 * 1024,
    });
    if (attempt.spawnError) {
      problems.push(`${candidate.source}: could not start (${redact(attempt.spawnError)})`);
      continue;
    }
    if (attempt.timedOut || attempt.cancelled) {
      problems.push(`${candidate.source}: timed out or was cancelled`);
      continue;
    }
    if (attempt.exitCode !== 0) {
      problems.push(`${candidate.source}: exited with code ${attempt.exitCode}`);
      continue;
    }
    let version: string | null = null;
    try {
      const parsed = JSON.parse(attempt.stdout.trim()) as { version?: string };
      version = typeof parsed.version === 'string' ? parsed.version : null;
    } catch {
      problems.push(`${candidate.source}: returned unreadable output`);
      continue;
    }
    if (!isSupportedPython(version)) {
      problems.push(`${candidate.source}: Python ${version ?? 'unknown'} (need 3.11-3.14)`);
      continue;
    }
    return {
      probe: { command: candidate.command, prefix: candidate.prefix, version: version!, source: candidate.source },
      problems,
    };
  }
  if (candidates.length === 0) {
    problems.push('no interpreter candidates were considered');
  }
  return { probe: null, problems };
}

// -------------------------------------------------------------- health check

export interface HealthResult {
  ok: boolean;
  envelope: Record<string, unknown> | null;
  problems: string[];
}

/**
 * Real health check: run the bundled bridge's `probe` with the given
 * interpreter against the given engine root. `cwd` must be an
 * extension-owned directory - never a workspace.
 */
export async function healthCheck(opts: {
  pythonCommand: string;
  pythonPrefix?: string[];
  bridgeScript: string;
  engineDir: string;
  cwd: string;
  signal?: AbortSignal;
  runner?: Runner;
  timeoutMs?: number;
}): Promise<HealthResult> {
  const runner = opts.runner ?? runProcess;
  const attempt = await runner({
    command: opts.pythonCommand,
    args: [
      ...(opts.pythonPrefix ?? []),
      opts.bridgeScript,
      'probe',
      '--engine-root',
      opts.engineDir,
    ],
    cwd: opts.cwd,
    timeoutMs: opts.timeoutMs ?? HEALTH_TIMEOUT_MS,
    maxOutputBytes: 1024 * 1024,
    signal: opts.signal,
  });
  if (attempt.spawnError) {
    return { ok: false, envelope: null, problems: [`could not start python: ${redact(attempt.spawnError)}`] };
  }
  if (attempt.cancelled) {
    return { ok: false, envelope: null, problems: ['health check was cancelled'] };
  }
  if (attempt.timedOut) {
    return { ok: false, envelope: null, problems: ['health check timed out'] };
  }
  if (attempt.exitCode !== 0) {
    const detail = redact(attempt.stderr.trim() || attempt.stdout.trim()).slice(0, 400);
    return {
      ok: false,
      envelope: null,
      problems: [`probe exited with code ${attempt.exitCode}${detail ? `: ${detail}` : ''}`],
    };
  }
  let envelope: Record<string, unknown> | null = null;
  try {
    const parsed: unknown = JSON.parse(attempt.stdout.trim());
    if (parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)) {
      envelope = parsed as Record<string, unknown>;
    }
  } catch {
    envelope = null;
  }
  if (!envelope || envelope['ok'] !== true) {
    return { ok: false, envelope, problems: ['probe returned a non-ok envelope'] };
  }
  const result = envelope['result'];
  const engine =
    result !== null && typeof result === 'object'
      ? (result as Record<string, unknown>)['engine']
      : undefined;
  if (
    !engine ||
    typeof engine !== 'object' ||
    (engine as Record<string, unknown>)['available'] !== true
  ) {
    return { ok: false, envelope, problems: ['probe did not report an available engine'] };
  }
  return { ok: true, envelope, problems: [] };
}

// --------------------------------------------------------- setup state gate

export interface SetupContext {
  /** Bundled engine directory inside the extension installation. */
  engineDir: string;
  /** Extension global storage sub-directory for install metadata + venvs. */
  storageDir: string;
  /** Absolute path to the bundled bridge script. */
  bridgeScript: string;
  configuredPython: string;
  configuredEngineRoot: string;
  autoDetectEngine: boolean;
  workspaceRoots: string[];
}

function looksLikeEngineRoot(candidate: string): boolean {
  if (!candidate) {
    return false;
  }
  return (
    fs.existsSync(path.join(candidate, 'app', 'main.py')) ||
    fs.existsSync(path.join(candidate, 'app', 'domain', '__init__.py'))
  );
}

/**
 * Activation-time decision: does this VS Code installation have a usable
 * engine? Purely filesystem-based (no subprocess, no workspace scan beyond a
 * couple of `existsSync` checks), so the very first render is already
 * correct.
 *
 *  - record ready + environment present + bundle verified -> `ready`
 *  - anything along that chain missing/damaged           -> `incomplete`
 *  - no managed install, but a configured or workspace
 *    engine checkout exists                              -> `ready` (custom)
 *  - nothing                                             -> `missing`
 */
export function computeSetupState(ctx: SetupContext): SetupState {
  const { record, problem } = readInstallRecord(ctx.storageDir);

  if (problem) {
    return state({
      status: 'incomplete',
      message: 'The engine installation record could not be read.',
      error: problem,
      technical: [redact(problem), `record: ${installRecordPath(ctx.storageDir)}`],
    });
  }

  if (record && record.status === 'ready') {
    const technical: string[] = [
      `engine ${record.engineVersion}`,
      `environment ${record.envKey}`,
      `interpreter ${redact(record.venvPython)}`,
      `installed ${record.installedAt}`,
      `verified ${record.verifiedAt}`,
    ];
    if (!fs.existsSync(record.venvPython)) {
      return state({
        status: 'incomplete',
        version: record.engineVersion,
        venvPython: record.venvPython,
        engineRoot: ctx.engineDir,
        message: 'The Python environment is missing or incomplete.',
        error: 'The recorded interpreter for this installation no longer exists.',
        technical,
      });
    }
    const verification = verifyBundle(ctx.engineDir);
    if (verification.bundle === null || verification.problems.length > 0) {
      return state({
        status: 'incomplete',
        version: record.engineVersion,
        venvPython: record.venvPython,
        engineRoot: ctx.engineDir,
        message: 'The bundled engine files failed verification.',
        error:
          verification.bundle === null
            ? 'The engine manifest is missing from this extension installation.'
            : `The bundled engine files are damaged (${verification.problems.length} problem(s)).`,
        technical: [...technical, ...verification.problems.slice(0, 8).map(redact)],
      });
    }
    return state({
      status: 'ready',
      version: record.engineVersion,
      python: record.pythonBase,
      engineRoot: ctx.engineDir,
      venvPython: record.venvPython,
      treeSha: record.bundleTreeSha256,
      message: 'The recovery engine is installed and verified.',
      technical,
    });
  }

  // No managed installation: a configured or workspace checkout counts as a
  // usable engine (developer/explicit workflows keep working unchanged).
  const custom =
    looksLikeEngineRoot(ctx.configuredEngineRoot) ||
    (ctx.autoDetectEngine && ctx.workspaceRoots.some((root) => looksLikeEngineRoot(root)));
  if (custom) {
    return state({
      status: 'ready',
      engineRoot: ctx.configuredEngineRoot || null,
      message: 'Using an Interlock engine checkout.',
      technical: ctx.configuredEngineRoot
        ? [`engine root (configured): ${redact(ctx.configuredEngineRoot)}`]
        : ['engine root detected from the open workspace'],
    });
  }

  return state({
    status: 'missing',
    message: 'The recovery engine is not set up yet.',
    technical: [
      `engine bundle: ${ctx.engineDir}`,
      'installation metadata: extension global storage',
    ],
  });
}

// ---------------------------------------------------------------- installation

export function state(partial: Partial<SetupState> & { status: SetupStatus }): SetupState {
  return {
    status: partial.status,
    phase: partial.phase ?? '',
    message: partial.message ?? '',
    error: partial.error ?? null,
    version: partial.version ?? null,
    python: partial.python ?? null,
    engineRoot: partial.engineRoot ?? null,
    venvPython: partial.venvPython ?? null,
    treeSha: partial.treeSha ?? null,
    technical: partial.technical ?? [],
  };
}

export interface InstallOptions {
  engineDir: string;
  storageDir: string;
  bridgeScript: string;
  configuredPython: string;
  signal?: AbortSignal;
  onPhase?: (phase: SetupPhase, message: string) => void;
  runner?: Runner;
  now?: () => Date;
}

export interface InstallOutcome {
  ok: boolean;
  setup: SetupState;
  record: InstallRecord | null;
  /** Real `probe` envelope from the health check (only on success). */
  envelope: Record<string, unknown> | null;
}

const PHASE_MESSAGE: Record<Exclude<SetupPhase, ''>, string> = {
  requirements: 'Checking requirements...',
  'engine-files': 'Verifying the bundled engine files...',
  environment: 'Creating an isolated Python environment...',
  verifying: 'Running the engine health check...',
  ready: 'Ready to use.',
};

/**
 * Install (or repair, or upgrade) the managed engine.
 *
 * Ordering is strict: verify requirements -> verify bundle bytes against the
 * manifest -> prepare the environment -> real health check -> only then write
 * the installation record. A record is never written unless the health check
 * passed, so `ready` can never be reached by a partial run.
 */
export async function installEngine(options: InstallOptions): Promise<InstallOutcome> {
  const runner = options.runner ?? runProcess;
  const now = options.now ?? ((): Date => new Date());
  const phases: Array<{ phase: SetupPhase; message: string }> = [];
  const emit = (phase: SetupPhase, message?: string): void => {
    const text = message ?? (phase === '' ? '' : PHASE_MESSAGE[phase as Exclude<SetupPhase, ''>]);
    phases.push({ phase, message: text });
    options.onPhase?.(phase, text);
  };
  const cancelled = (): InstallOutcome => ({
    ok: false,
    setup: state({
      status: 'failed',
      message: 'Installation did not complete.',
      error: 'Installation was cancelled.',
      technical: ['cancelled by the user; no installation record was written'],
    }),
    record: null,
    envelope: null,
  });
  const aborted = (): boolean => options.signal?.aborted === true;
  const technical: string[] = [`engine bundle: ${options.engineDir}`];

  // --- phase 1: requirements ------------------------------------------------
  emit('requirements');
  if (aborted()) {
    return cancelled();
  }
  const bundleCheck = readBundle(options.engineDir);
  if (!bundleCheck) {
    return {
      ok: false,
      setup: state({
        status: 'failed',
        phase: 'requirements',
        message: 'Installation did not complete.',
        error: 'The engine files are missing from this extension installation.',
        technical: [...technical, `missing manifest at ${path.join(options.engineDir, 'manifest.json')}`],
      }),
      record: null,
      envelope: null,
    };
  }
  const detected = await detectPython({
    configured: options.configuredPython,
    runner,
  });
  technical.push(...detected.problems.map(redact));
  if (!detected.probe) {
    return {
      ok: false,
      setup: state({
        status: 'python-missing',
        phase: 'requirements',
        version: bundleCheck.engineVersion,
        message:
          'Python 3.11-3.14 is required, and no supported interpreter was found on this machine.',
        error: 'No supported Python runtime was found.',
        technical: [
          ...technical,
          'install Python 3.11-3.14 from python.org, then choose "Check Installation Again"',
        ],
      }),
      record: null,
      envelope: null,
    };
  }
  technical.push(`base interpreter: ${redact(detected.probe.command)} (Python ${detected.probe.version})`);

  // --- phase 2: verify the engine files before anything runs ----------------
  emit('engine-files');
  if (aborted()) {
    return cancelled();
  }
  const verification = verifyBundle(options.engineDir);
  if (verification.bundle === null || verification.problems.length > 0) {
    const problems =
      verification.bundle === null
        ? ['engine/manifest.json is missing or unreadable']
        : verification.problems;
    return {
      ok: false,
      setup: state({
        status: 'failed',
        phase: 'engine-files',
        version: bundleCheck.engineVersion,
        message: 'Installation stopped: the bundled engine files failed verification.',
        error: 'Engine file verification failed.',
        technical: [...technical, ...problems.slice(0, 8).map(redact)],
      }),
      record: null,
      envelope: null,
    };
  }
  const treeSha = verification.treeSha256!;
  technical.push(`engine ${bundleCheck.engineVersion}, ${bundleCheck.fileCount} files verified`);

  // --- phase 3: isolated environment ---------------------------------------
  const minor = detected.probe.version.split('.').slice(0, 2).join('.');
  const envKey = `${bundleCheck.engineVersion}-py${minor}`;
  const envDir = path.join(options.storageDir, envKey);
  const venvPython = path.join(envDir, ...venvPythonRelative().split('/'));
  const { record: existingRecord } = readInstallRecord(options.storageDir);
  const sameInstallation =
    existingRecord !== null &&
    existingRecord.engineVersion === bundleCheck.engineVersion &&
    existingRecord.envKey === envKey &&
    existingRecord.bundleTreeSha256 === treeSha;

  emit('environment');
  if (aborted()) {
    return cancelled();
  }

  let reusedEnvironment = false;
  if (sameInstallation && fs.existsSync(venvPython)) {
    const runnable = await runner({
      command: venvPython,
      args: ['-c', PYTHON_PROBE_CODE],
      timeoutMs: PROBE_TIMEOUT_MS,
      maxOutputBytes: 64 * 1024,
      signal: options.signal,
    });
    if (runnable.exitCode === 0 && !runnable.spawnError && !runnable.cancelled) {
      reusedEnvironment = true;
      technical.push('existing verified environment reused (no rebuild needed)');
    } else {
      technical.push('existing environment was not runnable and will be rebuilt');
    }
  }

  if (!reusedEnvironment) {
    // Only ever remove an environment that is not currently recorded as a
    // verified installation (never a working engine environment).
    if (fs.existsSync(path.join(envDir, 'venv'))) {
      if (!sameInstallation) {
        technical.push(`removing incomplete environment ${envKey}`);
      }
      fs.rmSync(path.join(envDir, 'venv'), { recursive: true, force: true });
    }
    fs.mkdirSync(envDir, { recursive: true });
    const venv = await runner({
      command: detected.probe.command,
      args: [...detected.probe.prefix, '-m', 'venv', venvPython.replace(/[\\/]venv[\\/](python(\.exe)?|python3)$/, '')],
      cwd: envDir,
      timeoutMs: VENV_TIMEOUT_MS,
      maxOutputBytes: 512 * 1024,
      signal: options.signal,
    });
    if (aborted()) {
      fs.rmSync(path.join(envDir, 'venv'), { recursive: true, force: true });
      return cancelled();
    }
    if (venv.spawnError || venv.timedOut || venv.exitCode !== 0) {
      const detail = redact((venv.stderr || venv.spawnError || '').trim()).slice(0, 400);
      return {
        ok: false,
        setup: state({
          status: 'failed',
          phase: 'environment',
          version: bundleCheck.engineVersion,
          message: 'Installation did not complete: the Python environment could not be created.',
          error: detail || `venv creation exited with code ${venv.exitCode}`,
          technical: [...technical, `python -m venv exit=${venv.exitCode}`],
        }),
        record: null,
        envelope: null,
      };
    }
    if (!fs.existsSync(venvPython)) {
      return {
        ok: false,
        setup: state({
          status: 'failed',
          phase: 'environment',
          version: bundleCheck.engineVersion,
          message: 'Installation did not complete: the Python environment is incomplete.',
          error: `The interpreter ${venvPython} was not created.`,
          technical,
        }),
        record: null,
        envelope: null,
      };
    }
    technical.push(`environment created: ${redact(venvPython)}`);
  }

  // --- phase 4: real health check ------------------------------------------
  emit('verifying');
  if (aborted()) {
    return cancelled();
  }
  const health = await healthCheck({
    pythonCommand: venvPython,
    bridgeScript: options.bridgeScript,
    engineDir: options.engineDir,
    cwd: envDir,
    signal: options.signal,
    runner,
  });
  if (!health.ok) {
    const stateName: SetupStatus = aborted() ? 'failed' : 'failed';
    return {
      ok: false,
      setup: state({
        status: stateName,
        phase: 'verifying',
        version: bundleCheck.engineVersion,
        venvPython,
        engineRoot: options.engineDir,
        message: aborted()
          ? 'Installation was cancelled.'
          : 'Verification failed: the engine did not pass its health check.',
        error: aborted()
          ? 'Installation was cancelled.'
          : health.problems.map(redact).join(' ') || 'health check failed',
        technical: [...technical, ...health.problems.map(redact)],
      }),
      record: null,
      envelope: health.envelope,
    };
  }

  // Cross-check the version the engine itself reports (never assumed).
  const engineInfo = ((health.envelope!['result'] as Record<string, unknown>)['engine'] ??
    {}) as Record<string, unknown>;
  const reportedVersion = typeof engineInfo['version'] === 'string' ? engineInfo['version'] : null;
  if (reportedVersion && reportedVersion !== bundleCheck.engineVersion) {
    return {
      ok: false,
      setup: state({
        status: 'failed',
        phase: 'verifying',
        version: bundleCheck.engineVersion,
        message: 'Verification failed: the engine reported an unexpected version.',
        error: `Manifest says ${bundleCheck.engineVersion} but the engine reported ${reportedVersion}.`,
        technical,
      }),
      record: null,
      envelope: health.envelope,
    };
  }

  // --- success: only now is a record written --------------------------------
  const timestamp = now().toISOString();
  const record: InstallRecord = {
    format: INSTALL_FORMAT,
    engineVersion: bundleCheck.engineVersion,
    envKey,
    venvPython,
    pythonBase: detected.probe.command,
    installedAt: sameInstallation && existingRecord ? existingRecord.installedAt : timestamp,
    verifiedAt: timestamp,
    bundleTreeSha256: treeSha,
    status: 'ready',
    ...(sameInstallation && existingRecord
      ? {}
      : existingRecord
        ? {
            previous: {
              engineVersion: existingRecord.engineVersion,
              envKey: existingRecord.envKey,
              venvPython: existingRecord.venvPython,
            },
          }
        : {}),
  };
  writeInstallRecord(options.storageDir, record);

  emit('ready');
  return {
    ok: true,
    setup: state({
      status: 'installed',
      phase: 'ready',
      version: bundleCheck.engineVersion,
      python: detected.probe.version,
      engineRoot: options.engineDir,
      venvPython,
      treeSha,
      message: 'Ready to use. The recovery engine passed its health check.',
      technical: [...technical, `record: ${installRecordPath(options.storageDir)}`],
    }),
    record,
    envelope: health.envelope,
  };
}

/** Phases emitted so far (test helper mirroring the progress contract). */
export type { InstallOutcome as _InstallOutcome };
export const _PHASE_MESSAGE = PHASE_MESSAGE;
