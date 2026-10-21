/**
 * Managed engine + runtime lifecycle (zero-configuration installation).
 *
 * `engineSetup.ts` already implements the hard parts - manifest-verified
 * engine bundles, an isolated managed virtual environment, a real `probe`
 * health check, and an atomically written install record. This module composes
 * those primitives into the lifecycle the extension actually needs, and adds
 * the two things a first-run experience requires:
 *
 *   1. **A bundled runtime preference.** When this build of the extension
 *      ships a self-contained CPython under `runtime/<platform>-<arch>/`, that
 *      interpreter is used as the base for the managed environment, so the
 *      user does not have to install Python themselves. Nothing is ever
 *      downloaded at runtime: the interpreter is part of the VSIX and its
 *      presence is a build-time decision. When no bundled runtime exists for
 *      this platform the behaviour is unchanged - a supported system Python is
 *      detected and used, or the user is told, precisely, what is missing.
 *
 *   2. **A single-flight concurrency guard.** Installation is expensive
 *      (interpreter probe + venv creation + health check) and several
 *      commands can ask for it at once. `ensureInstalled()` collapses every
 *      concurrent caller onto ONE install run instead of racing several
 *      venv creations over the same directory.
 *
 * Like `engineSetup.ts`, this module deliberately does NOT import `vscode`,
 * so every path here is unit-testable headlessly. It never receives a
 * workspace path: installation cannot read or write project files.
 */

import * as fs from 'fs';
import * as path from 'path';

import {
  INSTALL_FORMAT,
  InstallOptions,
  InstallOutcome,
  SetupContext,
  SetupState,
  computeSetupState,
  healthCheck,
  installEngine,
  installRecordPath,
  managedInstallation,
  pythonCandidates,
  readInstallRecord,
  venvPythonRelative,
  verifyBundle,
  writeInstallRecord,
} from './engineSetup';
import { redact } from './redact';
import { RunOptions, RunResult } from './runner';

/** Directory prefix holding bundled runtimes: `runtime/<platform>-<arch>/`. */
export const RUNTIME_ROOT = 'runtime';

/** Interpreter locations inside a bundled runtime, per platform. */
const RUNTIME_INTERPRETER: Record<string, string[]> = {
  win32: [path.join('python', 'python.exe'), path.join('python.exe')],
  linux: [path.join('python', 'bin', 'python3'), path.join('bin', 'python3')],
  darwin: [path.join('python', 'bin', 'python3'), path.join('bin', 'python3')],
};

export interface RuntimeSelection {
  /** `win32-x64`, `darwin-arm64`, ... */
  key: string;
  /** Absolute path of the bundled interpreter, or null when not bundled. */
  pythonPath: string | null;
  /** Why this selection was made (shown in technical details). */
  reason: string;
}

/** Platform-arch key used to select a bundled runtime directory. */
export function runtimeKey(
  platform: string = process.platform,
  arch: string = process.arch,
): string {
  return `${platform}-${arch}`;
}

/**
 * Look for a bundled interpreter for this platform/arch. Purely
 * filesystem-based so activation can decide instantly and offline.
 */
export function selectBundledRuntime(opts: {
  extensionPath: string;
  platform?: string;
  arch?: string;
  exists?: (candidate: string) => boolean;
}): RuntimeSelection {
  const platform = opts.platform ?? process.platform;
  const arch = opts.arch ?? process.arch;
  const exists = opts.exists ?? ((candidate: string) => fs.existsSync(candidate));
  const key = runtimeKey(platform, arch);
  const dir = path.join(opts.extensionPath, RUNTIME_ROOT, key);
  const candidates = RUNTIME_INTERPRETER[platform] ?? RUNTIME_INTERPRETER.linux;
  for (const relative of candidates) {
    const candidate = path.join(dir, ...relative.split('/'));
    if (exists(candidate)) {
      return {
        key,
        pythonPath: candidate,
        reason: `bundled ${key} runtime (no system Python needed)`,
      };
    }
  }
  return {
    key,
    pythonPath: null,
    reason: `no bundled runtime for ${key} in this build`,
  };
}

export interface EngineRuntimeOptions {
  /** Absolute path to the unpacked extension directory. */
  extensionPath: string;
  /** Extension global storage root (install record + managed environments). */
  storageDir: string;
  /** Absolute path to the bundled bridge script. */
  bridgeScript: string;
  /** Explicit user configuration (always wins over detection). */
  configuredPython?: string;
  configuredEngineRoot?: string;
  autoDetectEngine?: boolean;
  workspaceRoots?: string[];
  runner?: (options: RunOptions) => Promise<RunResult>;
  /** Test hooks. */
  platform?: string;
  arch?: string;
  exists?: (candidate: string) => boolean;
  now?: () => Date;
}

/**
 * One managed engine installation surface for the whole extension.
 *
 * Responsibilities:
 *   - answer "is a usable engine present?" without spawning anything
 *     ({@link state}) so the very first render is already correct;
 *   - install/repair/upgrade the managed environment exactly once at a time
 *     ({@link ensureInstalled}), reusing a valid installation across launches;
 *   - hand the bridge the interpreter and engine root to use
 *     ({@link resolve}), preferring the managed installation, then a bundled
 *     runtime, then an explicit configuration.
 */
export class EngineRuntime {
  private readonly options: EngineRuntimeOptions;
  private readonly engineDir: string;
  private readonly storageDir: string;
  /** Single-flight install guard: concurrent callers await the same promise. */
  private inFlight: Promise<InstallOutcome> | null = null;

  constructor(options: EngineRuntimeOptions) {
    this.options = options;
    this.engineDir = path.join(options.extensionPath, 'engine');
    this.storageDir = path.join(options.storageDir, 'engine');
  }

  /** Bundled engine directory (the SHA-256 manifest lives next to it). */
  get bundledEngineDir(): string {
    return this.engineDir;
  }

  /** Filesystem-only first paint: no subprocess, no workspace scan. */
  state(): SetupState {
    return computeSetupState(this.setupContext());
  }

  /** Bundled runtime selection for this platform/arch (may be absent). */
  runtime(): RuntimeSelection {
    return selectBundledRuntime({
      extensionPath: this.options.extensionPath,
      platform: this.options.platform,
      arch: this.options.arch,
      exists: this.options.exists,
    });
  }

  /**
   * The verified managed installation (bundled engine + its interpreter),
   * when one exists. This is the zero-configuration engine: it needs no
   * user setup, no system Python, and no workspace. Returns null when no
   * installation record is present (before first install).
   */
  managed(): { engineRoot: string; pythonPath: string; version: string | null } | null {
    const managed = managedInstallation({
      engineDir: this.engineDir,
      storageDir: this.storageDir,
    });
    if (!managed) {
      return null;
    }
    return {
      engineRoot: managed.engineRoot,
      pythonPath: managed.pythonPath,
      version: managed.version,
    };
  }

  /**
   * The interpreter and engine root the bridge should use right now.
   *
   * Order: an intact managed installation always wins (it is the verified,
   * isolated one); otherwise the configured interpreter/engine root, so a
   * developer checkout keeps working exactly as before.
   */
  resolve(): {
    engineRoot: string;
    pythonPath: string;
    source: string;
    version: string | null;
  } | null {
    const managed = this.managed();
    if (managed) {
      return {
        engineRoot: managed.engineRoot,
        pythonPath: managed.pythonPath,
        source: 'managed installation (verified)',
        version: managed.version,
      };
    }
    if (this.options.configuredPython?.trim() && this.options.configuredEngineRoot?.trim()) {
      return {
        engineRoot: this.options.configuredEngineRoot.trim(),
        pythonPath: this.options.configuredPython.trim(),
        source: 'configured interpreter and engine root',
        version: null,
      };
    }
    return null;
  }

  /**
   * Install (or repair, or upgrade) the managed engine, collapsing every
   * concurrent caller onto ONE run. Returns the same outcome to all callers.
   */
  ensureInstalled(signal?: AbortSignal): Promise<InstallOutcome> {
    if (this.inFlight) {
      return this.inFlight;
    }
    const run = this.install(signal).finally(() => {
      this.inFlight = null;
    });
    this.inFlight = run;
    return run;
  }

  /** True while an installation is running (the sidebar shows progress). */
  get installing(): boolean {
    return this.inFlight !== null;
  }

  private async install(signal?: AbortSignal): Promise<InstallOutcome> {
    // A bundled runtime, when present, is the base interpreter: it removes the
    // "install Python first" step entirely and needs no virtual environment,
    // because the engine's import closure is standard-library-only. Otherwise
    // engineSetup detects a supported system interpreter (or reports precisely
    // what is missing) and provisions an isolated environment as before.
    const bundled = this.runtime();
    const options: InstallOptions = {
      engineDir: this.engineDir,
      storageDir: this.storageDir,
      bridgeScript: this.options.bridgeScript,
      configuredPython: bundled.pythonPath ?? this.options.configuredPython ?? '',
      signal,
      runner: this.options.runner,
      now: this.options.now,
    };
    if (bundled.pythonPath) {
      return this.installBundled(options, bundled.pythonPath, signal);
    }
    return installEngine(options);
  }

  /**
   * Zero-configuration install against a bundled, self-contained interpreter.
   *
   * No virtual environment is created: the shipped runtime is already isolated
   * and the engine needs nothing beyond the standard library, so the "managed
   * environment" IS the bundled interpreter. The safety contract is unchanged
   * from the venv path - verify the engine bytes against the manifest, run the
   * real `probe` health check, cross-check the reported version, and only then
   * write the installation record. A record is never written unless the health
   * check passed.
   */
  private async installBundled(
    options: InstallOptions,
    bundledPython: string,
    signal?: AbortSignal,
  ): Promise<InstallOutcome> {
    const runner = this.options.runner;
    const technical: string[] = [
      `engine bundle: ${this.engineDir}`,
      `bundled interpreter: ${bundledPython}`,
      'no virtual environment is required (standard-library-only engine)',
    ];
    const failed = (
      phase: 'requirements' | 'engine-files' | 'verifying',
      version: string | null,
      message: string,
      error: string,
    ): InstallOutcome => ({
      ok: false,
      setup: {
        status: 'failed',
        phase,
        message,
        error,
        version,
        python: null,
        engineRoot: this.engineDir,
        venvPython: null,
        treeSha: null,
        technical: [...technical, error],
      },
      record: null,
      envelope: null,
    });

    // Phase: requirements + engine-files (verify the manifest-checked bytes).
    fs.mkdirSync(this.storageDir, { recursive: true });
    options.onPhase?.('engine-files', 'Verifying the bundled engine files...');
    const verification = verifyBundle(this.engineDir);
    if (verification.bundle === null || verification.problems.length > 0) {
      const problems =
        verification.bundle === null
          ? ['engine/manifest.json is missing or unreadable']
          : verification.problems;
      return failed(
        'engine-files',
        verification.bundle?.engineVersion ?? null,
        'Installation stopped: the bundled engine files failed verification.',
        problems.slice(0, 3).join('; '),
      );
    }
    const engineVersion = verification.bundle.engineVersion;
    const treeSha = verification.treeSha256!;
    technical.push(`engine ${engineVersion}, ${verification.bundle.fileCount} files verified`);

    if (signal?.aborted) {
      return failed('requirements', engineVersion, 'Installation was cancelled.', 'cancelled');
    }

    // Phase: verifying (real health check through the bundled bridge).
    options.onPhase?.('verifying', 'Running the engine health check...');
    const health = await healthCheck({
      pythonCommand: bundledPython,
      bridgeScript: options.bridgeScript,
      engineDir: this.engineDir,
      cwd: this.storageDir,
      signal,
      runner,
    });
    if (!health.ok) {
      return failed(
        'verifying',
        engineVersion,
        'Verification failed: the bundled engine did not pass its health check.',
        health.problems.map(redact).join(' ') || 'health check failed',
      );
    }
    const engineInfo = ((health.envelope!['result'] as Record<string, unknown>)['engine'] ??
      {}) as Record<string, unknown>;
    const reported = typeof engineInfo['version'] === 'string' ? engineInfo['version'] : null;
    if (reported && reported !== engineVersion) {
      return failed(
        'verifying',
        engineVersion,
        'Verification failed: the engine reported an unexpected version.',
        `manifest says ${engineVersion} but the engine reported ${reported}`,
      );
    }

    // Success: only now is a record written (atomic), reusing an existing one.
    const now = options.now ?? ((): Date => new Date());
    const timestamp = now().toISOString();
    const envKey = `${engineVersion}-bundled`;
    const { record: existing } = readInstallRecord(this.storageDir);
    writeInstallRecord(this.storageDir, {
      format: INSTALL_FORMAT,
      engineVersion,
      envKey,
      venvPython: bundledPython,
      pythonBase: bundledPython,
      installedAt: existing && existing.envKey === envKey ? existing.installedAt : timestamp,
      verifiedAt: timestamp,
      bundleTreeSha256: treeSha,
      status: 'ready',
    });
    options.onPhase?.('ready', 'Ready to use.');
    return {
      ok: true,
      setup: {
        status: 'installed',
        phase: 'ready',
        message: 'Ready to use. The bundled recovery engine passed its health check.',
        error: null,
        version: engineVersion,
        python: engineInfo['version'] ? String(engineInfo['version']) : null,
        engineRoot: this.engineDir,
        venvPython: bundledPython,
        treeSha,
        technical: [...technical, `record: ${installRecordPath(this.storageDir)}`],
      },
      record: readInstallRecord(this.storageDir).record,
      envelope: health.envelope,
    };
  }

  private setupContext(): SetupContext {
    return {
      engineDir: this.engineDir,
      storageDir: this.storageDir,
      bridgeScript: this.options.bridgeScript,
      configuredPython: this.options.configuredPython ?? '',
      configuredEngineRoot: this.options.configuredEngineRoot ?? '',
      autoDetectEngine: this.options.autoDetectEngine ?? true,
      workspaceRoots: this.options.workspaceRoots ?? [],
    };
  }
}

/** Re-exported so callers can build candidate lists without importing setup. */
export { pythonCandidates, venvPythonRelative };
