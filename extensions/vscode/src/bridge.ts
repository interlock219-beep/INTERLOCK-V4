/**
 * Bridge invocation: builds argument arrays, runs the Python integration
 * layer, and translates its structured envelope into typed outcomes.
 *
 * The extension never builds a shell string; `buildArgs` output is passed to
 * `spawn` verbatim as an argument array.
 */

import { redact, truncate } from './redact';
import { runProcess, RunResult } from './runner';

export type BridgeCommand =
  | 'probe'
  | 'status'
  | 'analyze'
  | 'capture-baseline'
  | 'plan'
  | 'plan-many'
  | 'execute'
  | 'verify';

export const BRIDGE_EXIT = {
  OK: 0,
  USAGE: 2,
  ENGINE_UNAVAILABLE: 3,
  NOT_AUTHORIZED: 4,
  REFUSED: 5,
  VERIFICATION_FAILED: 6,
  PRECONDITION: 7,
  INTERNAL: 8,
} as const;

export type BridgeResultKind =
  | 'ok'
  | 'interpreter_not_found'
  | 'spawn_error'
  | 'engine_unavailable'
  | 'not_authorized'
  | 'refused'
  | 'verification_failed'
  | 'precondition'
  | 'invalid_invocation'
  | 'internal_error'
  | 'timeout'
  | 'cancelled'
  | 'protocol_error';

export interface BridgeInvocation {
  command: BridgeCommand;
  workspace?: string;
  resource?: string;
  baselineFile?: string;
  evidenceFile?: string;
  approvedBy?: string;
  engineRoot?: string;
  maxBytes?: number;
  /**
   * Manifest of a bulk plan (`plan-many`): a JSON file in the extension's
   * private storage listing {resource, baseline_file} entries. Never a path
   * inside the workspace.
   */
  resourcesFile?: string;
  /** `plan-many`: persist preview-time evidence for every planned file. */
  saveEvidence?: boolean;
  /** `plan-many`: index of the first manifest entry to process. */
  offset?: number;
  /** `plan-many`: how many manifest entries to process in this call. */
  limit?: number;
}

export interface BridgeEnvelope {
  bridge?: string;
  bridge_version?: string;
  command?: string;
  ok?: boolean;
  result?: Record<string, unknown> | null;
  error?: { kind?: string; message?: string; hint?: string } | null;
  python?: Record<string, unknown>;
}

export interface BridgeCallResult {
  ok: boolean;
  command: string;
  kind: BridgeResultKind;
  exitCode: number | null;
  envelope: BridgeEnvelope | null;
  result: Record<string, unknown> | null;
  message: string;
  hint: string;
  stderrExcerpt: string;
  truncated: boolean;
  durationMs: number;
}

export type RunFn = (options: {
  command: string;
  args: string[];
  cwd?: string;
  timeoutMs?: number;
  signal?: AbortSignal;
  maxOutputBytes?: number;
}) => Promise<RunResult>;

/** Build the argument array for a bridge call (script path excluded). */
export function buildArgs(invocation: BridgeInvocation): string[] {
  const args: string[] = [invocation.command];
  if (invocation.workspace) {
    args.push('--workspace', invocation.workspace);
  }
  if (invocation.resource) {
    args.push('--resource', invocation.resource);
  }
  if (invocation.baselineFile) {
    args.push('--baseline-file', invocation.baselineFile);
  }
  if (invocation.evidenceFile) {
    args.push('--evidence-file', invocation.evidenceFile);
  }
  if (invocation.approvedBy) {
    args.push('--approved-by', invocation.approvedBy);
  }
  if (invocation.engineRoot) {
    args.push('--engine-root', invocation.engineRoot);
  }
  if (typeof invocation.maxBytes === 'number') {
    args.push('--max-bytes', String(Math.floor(invocation.maxBytes)));
  }
  if (invocation.resourcesFile) {
    args.push('--resources-file', invocation.resourcesFile);
  }
  if (invocation.saveEvidence === true) {
    args.push('--save-evidence');
  }
  if (typeof invocation.offset === 'number') {
    args.push('--offset', String(Math.floor(invocation.offset)));
  }
  if (typeof invocation.limit === 'number') {
    args.push('--limit', String(Math.floor(invocation.limit)));
  }
  return args;
}

/** Parse the single-line JSON envelope the bridge writes to stdout. */
export function parseEnvelope(stdout: string): {
  envelope: BridgeEnvelope | null;
  error: string | null;
} {
  const trimmed = stdout.trim();
  if (trimmed === '') {
    return { envelope: null, error: 'The engine bridge produced no output.' };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    return {
      envelope: null,
      error: 'The engine bridge did not return valid JSON.',
    };
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { envelope: null, error: 'The engine bridge returned an unexpected payload.' };
  }
  const candidate = parsed as BridgeEnvelope;
  if (typeof candidate.ok !== 'boolean') {
    return { envelope: null, error: 'The engine bridge envelope is missing its status field.' };
  }
  return { envelope: candidate, error: null };
}

const ERROR_KIND_MAP: Record<string, BridgeResultKind> = {
  engine_unavailable: 'engine_unavailable',
  no_workspace: 'not_authorized',
  not_authorized: 'not_authorized',
  engine_refusal: 'refused',
  approval_required: 'refused',
  unsupported_environment: 'refused',
  verification_failed: 'verification_failed',
  no_baseline: 'precondition',
  corrupt_baseline: 'precondition',
  baseline_unsealed: 'precondition',
  baseline_truncated: 'precondition',
  unsupported_baseline_integrity: 'precondition',
  baseline_integrity_failed: 'refused',
  preview_required: 'precondition',
  corrupt_evidence: 'precondition',
  precondition_failed: 'precondition',
  invalid_invocation: 'invalid_invocation',
  internal_error: 'internal_error',
  cancelled: 'cancelled',
};

const EXIT_CODE_MAP: Record<number, BridgeResultKind> = {
  2: 'invalid_invocation',
  3: 'engine_unavailable',
  4: 'not_authorized',
  5: 'refused',
  6: 'verification_failed',
  7: 'precondition',
  8: 'internal_error',
};

export function kindFromExitCode(exitCode: number | null): BridgeResultKind {
  if (exitCode === BRIDGE_EXIT.OK) {
    return 'ok';
  }
  if (exitCode === null) {
    return 'spawn_error';
  }
  return EXIT_CODE_MAP[exitCode] ?? 'internal_error';
}

export function kindFromErrorKind(errorKind: string | undefined): BridgeResultKind | null {
  if (!errorKind) {
    return null;
  }
  return ERROR_KIND_MAP[errorKind] ?? null;
}

/** Human-readable headline for a failed call (already redacted). */
export function describeFailure(result: BridgeCallResult): string {
  switch (result.kind) {
    case 'interpreter_not_found':
      return 'The configured Python interpreter could not be started.';
    case 'spawn_error':
      return 'The engine bridge process could not be started.';
    case 'timeout':
      return 'The engine call timed out and the process was terminated.';
    case 'cancelled':
      return 'The engine call was cancelled.';
    case 'protocol_error':
      return result.message;
    case 'engine_unavailable':
      return result.message || 'The Interlock engine could not be imported.';
    default:
      return result.message || `The engine call failed (${result.kind}).`;
  }
}

export interface BridgeCallParams {
  bridgeScript: string;
  pythonPath: string;
  invocation: BridgeInvocation;
  cwd?: string;
  timeoutMs: number;
  signal?: AbortSignal;
  maxOutputBytes?: number;
  run?: RunFn;
}

/** Execute one bridge call and normalize every failure mode. */
export async function callBridge(params: BridgeCallParams): Promise<BridgeCallResult> {
  const run = params.run ?? runProcess;
  const args = [params.bridgeScript, ...buildArgs(params.invocation)];
  const command = params.invocation.command;

  let raw: RunResult;
  try {
    raw = await run({
      command: params.pythonPath,
      args,
      cwd: params.cwd,
      timeoutMs: params.timeoutMs,
      signal: params.signal,
      maxOutputBytes: params.maxOutputBytes,
    });
  } catch (error) {
    return {
      ok: false,
      command,
      kind: 'invalid_invocation',
      exitCode: null,
      envelope: null,
      result: null,
      message: redact(error instanceof Error ? error.message : String(error)),
      hint: 'Check the Interlock interpreter and path settings.',
      stderrExcerpt: '',
      truncated: false,
      durationMs: 0,
    };
  }

  const stderrExcerpt = redact(truncate(raw.stderr, 4000));
  const base: BridgeCallResult = {
    ok: false,
    command,
    kind: 'internal_error',
    exitCode: raw.exitCode,
    envelope: null,
    result: null,
    message: '',
    hint: '',
    stderrExcerpt,
    truncated: raw.truncated,
    durationMs: raw.durationMs,
  };

  if (raw.spawnError) {
    const notFound = /ENOENT|not found|no such file/i.test(raw.spawnError);
    return {
      ...base,
      kind: notFound ? 'interpreter_not_found' : 'spawn_error',
      message: redact(raw.spawnError),
      hint: notFound
        ? 'Set "interlock.pythonPath" to a valid Python interpreter (3.11-3.14).'
        : 'See the Interlock output log for details.',
    };
  }
  if (raw.cancelled) {
    return { ...base, kind: 'cancelled', message: 'Cancelled.' };
  }
  if (raw.timedOut) {
    return {
      ...base,
      kind: 'timeout',
      message: `The engine did not respond within ${Math.round(params.timeoutMs / 1000)}s and was terminated.`,
      hint: 'Raise "interlock.timeoutSeconds" or investigate the engine installation.',
    };
  }

  const { envelope, error } = parseEnvelope(raw.stdout);
  if (!envelope) {
    return {
      ...base,
      kind: 'protocol_error',
      message: redact(error ?? 'Unexpected bridge output.'),
      stderrExcerpt: stderrExcerpt || redact(truncate(raw.stdout, 2000)),
    };
  }

  const envelopeError = envelope.error ?? undefined;
  const mapped =
    kindFromErrorKind(envelopeError?.kind) ??
    (raw.exitCode === null ? 'spawn_error' : kindFromExitCode(raw.exitCode));
  const success = raw.exitCode === 0 && envelope.ok === true && mapped === 'ok';

  return {
    ...base,
    ok: success,
    envelope,
    result: envelope.result ?? null,
    kind: success ? 'ok' : mapped,
    message: redact(envelopeError?.message ?? ''),
    hint: redact(envelopeError?.hint ?? ''),
  };
}
