/**
 * Interpreter and engine discovery (pure logic; filesystem access is injected
 * so it can be unit-tested without touching the real disk).
 *
 * Detection order is explicit and conservative: a configured value always wins
 * and is validated; auto-detection only runs when the user allows it.
 */

import * as path from 'path';
import { InterlockSettings } from './config';

export interface EngineLocation {
  /** Interpreter to spawn (absolute path, or a bare command name). */
  pythonPath: string;
  /** Where that interpreter value came from. */
  pythonSource: string;
  /** Engine checkout root, when one could be established. */
  engineRoot: string | undefined;
  engineSource: string;
  /** Human-readable configuration problems. */
  issues: string[];
}

export type ExistsFn = (candidate: string) => boolean;

/**
 * A verified engine the extension already manages (bundled engine files plus
 * an isolated, health-checked environment). It is used whenever the user has
 * NOT configured their own interpreter/engine root, so a fresh install needs
 * no configuration at all. Explicit configuration always wins: a developer
 * pointing at their own checkout keeps working exactly as before.
 */
export interface EngineOverride {
  pythonPath: string;
  pythonSource: string;
  engineRoot?: string;
  engineSource: string;
}

const VENV_WINDOWS = [
  path.join('.venv', 'Scripts', 'python.exe'),
  path.join('venv', 'Scripts', 'python.exe'),
  path.join('.venv314', 'Scripts', 'python.exe'),
];

const VENV_POSIX = [
  path.join('.venv', 'bin', 'python3'),
  path.join('.venv', 'bin', 'python'),
  path.join('venv', 'bin', 'python3'),
];

function looksLikePath(value: string): boolean {
  return path.isAbsolute(value) || value.includes('/') || value.includes('\\');
}

export function detectEngine(
  settings: InterlockSettings,
  workspaceRoots: string[],
  exists: ExistsFn,
  override?: EngineOverride,
): EngineLocation {
  const issues: string[] = [];
  let pythonPath = '';
  let pythonSource = '';
  let engineRoot: string | undefined;
  let engineSource = '';

  // 0) A verified managed installation (bundled engine + isolated, health
  //    checked environment) is used unless the user configured their own.
  //    This is what makes a fresh install work with no configuration.
  const managedPython = !settings.pythonPath && override?.pythonPath ? override : undefined;

  // 1) Explicit interpreter configuration (validated, never guessed over).
  if (settings.pythonPath) {
    if (looksLikePath(settings.pythonPath)) {
      if (exists(settings.pythonPath)) {
        pythonPath = settings.pythonPath;
        pythonSource = 'interlock.pythonPath (configured)';
      } else {
        issues.push(
          `interlock.pythonPath points to "${settings.pythonPath}" which does not exist.`,
        );
      }
    } else {
      // Bare command: resolved through PATH at spawn time, verified by
      // "Interlock: Check Installation".
      pythonPath = settings.pythonPath;
      pythonSource = 'interlock.pythonPath (command on PATH)';
    }
  }

  // 2) Explicit engine root configuration.
  if (settings.engineRoot) {
    if (!isEngineRoot(settings.engineRoot, exists)) {
      issues.push(
        `interlock.engineRoot "${settings.engineRoot}" does not contain the Interlock "app" package.`,
      );
    } else {
      engineRoot = settings.engineRoot;
      engineSource = 'interlock.engineRoot (configured)';
    }
  }

  if (!settings.autoDetectEngine) {
    if (!pythonPath) {
      issues.push(
        'No interpreter configured and auto-detection is disabled - set interlock.pythonPath.',
      );
      pythonPath = '';
      pythonSource = 'not configured';
    }
    if (!engineRoot) {
      issues.push(
        'No engine root configured and auto-detection is disabled - set interlock.engineRoot.',
      );
    }
    return { pythonPath, pythonSource, engineRoot, engineSource, issues };
  }

  // 3) The extension's own managed installation (bundled engine files plus a
  //    verified, isolated environment). Used before any workspace probing so a
  //    fresh install works with zero configuration and never depends on the
  //    project's own virtualenv.
  if (managedPython) {
    if (!pythonPath) {
      pythonPath = managedPython.pythonPath;
      pythonSource = managedPython.pythonSource;
    }
    if (!engineRoot && managedPython.engineRoot) {
      engineRoot = managedPython.engineRoot;
      engineSource = managedPython.engineSource;
    }
  }

  // 4) Auto-detect engine root from the open workspace folders.
  if (!engineRoot) {
    for (const root of workspaceRoots) {
      if (isEngineRoot(root, exists)) {
        engineRoot = root;
        engineSource = 'detected from workspace';
        break;
      }
    }
  }

  // 5) Auto-detect interpreter: a project venv first, then PATH commands.
  if (!pythonPath) {
    const searchRoots = engineRoot ? [engineRoot, ...workspaceRoots] : workspaceRoots;
    outer: for (const root of searchRoots) {
      const candidates = process.platform === 'win32' ? VENV_WINDOWS : VENV_POSIX;
      for (const relative of candidates) {
        const candidate = path.join(root, relative);
        if (exists(candidate)) {
          pythonPath = candidate;
          pythonSource = `detected virtualenv (${relative})`;
          break outer;
        }
      }
    }
  }
  if (!pythonPath) {
    pythonPath = process.platform === 'win32' ? 'python' : 'python3';
    pythonSource = 'PATH lookup (unverified until Check Installation runs)';
  }

  if (!engineRoot) {
    issues.push(
      'No Interlock engine checkout detected in the open workspace - set interlock.engineRoot.',
    );
  }

  return { pythonPath, pythonSource, engineRoot, engineSource, issues };
}

export function isEngineRoot(candidate: string, exists: ExistsFn): boolean {
  if (!candidate) {
    return false;
  }
  return (
    exists(path.join(candidate, 'app', 'main.py')) ||
    exists(path.join(candidate, 'app', 'domain', '__init__.py'))
  );
}
