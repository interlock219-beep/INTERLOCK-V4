/**
 * Safe subprocess execution.
 *
 * Guarantees enforced here (and covered by unit tests):
 *  - never invokes a shell (`shell: false`, literal argument arrays);
 *  - the child receives a minimal allow-listed environment, so host secrets,
 *    tokens, and unrelated variables are not inherited;
 *  - per-call timeout and external cancellation both terminate the child;
 *  - stdout/stderr are size-capped (bounded memory, bounded log exposure);
 *  - exit code, signal, spawn errors, timeout and cancellation are all
 *    reported distinctly instead of being collapsed into "failed".
 */

import { spawn } from 'child_process';

export interface RunOptions {
  command: string;
  args: string[];
  cwd?: string;
  timeoutMs?: number;
  signal?: AbortSignal;
  maxOutputBytes?: number;
  extraEnv?: Record<string, string>;
}

export interface RunResult {
  exitCode: number | null;
  signal: NodeJS.Signals | null;
  stdout: string;
  stderr: string;
  timedOut: boolean;
  cancelled: boolean;
  truncated: boolean;
  spawnError: string | null;
  durationMs: number;
}

export const DEFAULT_MAX_OUTPUT_BYTES = 32 * 1024 * 1024;

/**
 * Minimal environment allow-list. Deliberately not a copy of `process.env`:
 * credentials and unrelated tool configuration must not reach the child.
 */
const ENV_ALLOW_LIST = [
  'PATH',
  'PATHEXT',
  'SystemRoot',
  'SYSTEMROOT',
  'WINDIR',
  'COMSPEC',
  'TEMP',
  'TMP',
  'USERPROFILE',
  'HOME',
  'LANG',
  'LC_ALL',
  'TZ',
  'NUMBER_OF_PROCESSORS',
];

export function buildEnv(extraEnv: Record<string, string> = {}): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {};
  for (const key of ENV_ALLOW_LIST) {
    const value = process.env[key];
    if (typeof value === 'string') {
      env[key] = value;
    }
  }
  // Deterministic, utf-8 subprocess IO regardless of host locale.
  env['PYTHONIOENCODING'] = 'utf-8';
  env['PYTHONUTF8'] = '1';
  env['PYTHONUNBUFFERED'] = '1';
  for (const [key, value] of Object.entries(extraEnv)) {
    if (key.length === 0 || key.includes('\u0000') || value.includes('\u0000')) {
      continue;
    }
    if (/[\r\n]/.test(key) || /[\r\n]/.test(value)) {
      continue;
    }
    env[key] = value;
  }
  return env;
}

/**
 * Validate an invocation before spawning.
 * Returns a human-readable problem, or `null` when the call is acceptable.
 */
export function validateInvocation(command: string, args: string[]): string | null {
  if (typeof command !== 'string' || command.trim() === '') {
    return 'Executable path/command must be a non-empty string.';
  }
  if (/[\u0000\r\n]/.test(command)) {
    return 'Executable path must not contain newlines or NUL characters.';
  }
  if (!Array.isArray(args)) {
    return 'Arguments must be an array.';
  }
  for (const arg of args) {
    if (typeof arg !== 'string') {
      return 'Every argument must be a string.';
    }
    if (arg.includes('\u0000') || /[\r\n]/.test(arg)) {
      return 'Arguments must not contain newlines or NUL characters.';
    }
  }
  return null;
}

/** Spawn a process without a shell and collect bounded output. */
export function runProcess(options: RunOptions): Promise<RunResult> {
  const problem = validateInvocation(options.command, options.args);
  if (problem) {
    return Promise.reject(new Error(problem));
  }

  const started = Date.now();
  const maxBytes = options.maxOutputBytes ?? DEFAULT_MAX_OUTPUT_BYTES;

  return new Promise<RunResult>((resolve, reject) => {
    let child: ReturnType<typeof spawn>;
    try {
      child = spawn(options.command, options.args, {
        shell: false,
        windowsHide: true,
        cwd: options.cwd,
        env: buildEnv(options.extraEnv),
        stdio: ['ignore', 'pipe', 'pipe'],
      });
    } catch (error) {
      reject(error instanceof Error ? error : new Error(String(error)));
      return;
    }

    let stdout = '';
    let stderr = '';
    let outBytes = 0;
    let errBytes = 0;
    let timedOut = false;
    let cancelled = false;
    let truncated = false;
    let settled = false;
    let timeoutHandle: NodeJS.Timeout | undefined;
    let killHandle: NodeJS.Timeout | undefined;

    const onAbort = (): void => {
      cancelled = true;
      terminate();
    };

    const cleanup = (): void => {
      if (timeoutHandle) {
        clearTimeout(timeoutHandle);
      }
      if (killHandle) {
        clearTimeout(killHandle);
      }
      if (options.signal) {
        options.signal.removeEventListener('abort', onAbort);
      }
    };

    const terminate = (): void => {
      try {
        child.kill('SIGTERM');
      } catch {
        // child already exited
      }
      killHandle = setTimeout(() => {
        try {
          child.kill('SIGKILL');
        } catch {
          // already gone
        }
      }, 3000);
      killHandle.unref?.();
    };

    if (typeof options.timeoutMs === 'number' && options.timeoutMs > 0) {
      timeoutHandle = setTimeout(() => {
        timedOut = true;
        terminate();
      }, options.timeoutMs);
      timeoutHandle.unref?.();
    }

    if (options.signal) {
      if (options.signal.aborted) {
        cancelled = true;
        terminate();
      } else {
        options.signal.addEventListener('abort', onAbort, { once: true });
      }
    }

    const append = (which: 'out' | 'err', chunk: Buffer): void => {
      if (which === 'out') {
        if (outBytes + chunk.length > maxBytes) {
          const remaining = Math.max(0, maxBytes - outBytes);
          stdout += chunk.subarray(0, remaining).toString('utf8');
          outBytes = maxBytes;
          truncated = true;
          terminate();
          return;
        }
        stdout += chunk.toString('utf8');
        outBytes += chunk.length;
        return;
      }
      if (errBytes + chunk.length > maxBytes) {
        const remaining = Math.max(0, maxBytes - errBytes);
        stderr += chunk.subarray(0, remaining).toString('utf8');
        errBytes = maxBytes;
        truncated = true;
        terminate();
        return;
      }
      stderr += chunk.toString('utf8');
      errBytes += chunk.length;
    };

    child.stdout?.on('data', (chunk: Buffer) => append('out', chunk));
    child.stderr?.on('data', (chunk: Buffer) => append('err', chunk));

    child.on('error', (error: Error) => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      resolve({
        exitCode: null,
        signal: null,
        stdout,
        stderr: stderr ? `${stderr}\n${error.message}` : error.message,
        timedOut,
        cancelled,
        truncated,
        spawnError: error.message,
        durationMs: Date.now() - started,
      });
    });

    child.on('close', (code: number | null, signal: NodeJS.Signals | null) => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      resolve({
        exitCode: code,
        signal,
        stdout,
        stderr,
        timedOut,
        cancelled,
        truncated,
        spawnError: null,
        durationMs: Date.now() - started,
      });
    });
  });
}
