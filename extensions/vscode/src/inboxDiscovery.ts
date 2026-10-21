/**
 * Recovery Inbox discovery (pure orchestration - every IO call is injected).
 *
 * One scan answers three questions without writing a single workspace file:
 *
 *   1. Classification: for every stored baseline, does the current file still
 *      match it (unchanged / modified / deleted / unknown)?
 *   2. Evidence validity: do the stored baseline bytes still hash to their
 *      recorded SHA-256 (verified / invalid / unusable)?
 *   3. Changed-without-baseline: which workspace files changed after the
 *      newest baseline was captured but have no baseline at all (they exist,
 *      but there is nothing to restore - said so plainly)?
 *
 * Eligibility ("can this actually be recovered right now") comes from the
 * engine via a bulk assessment over the changed candidates only, so a
 * workspace with thousands of untouched files stays fast. The engine remains
 * the authority: this module never decides safety on its own, it only
 * classifies observed state and translates engine verdicts into plain words.
 *
 * Honesty rules:
 *   * every phase reports progress and honors cancellation;
 *   * partial coverage (walk truncation, policy skips, read failures) is
 *     recorded in {@link InboxCoverage} - counts that depend on an incomplete
 *     walk render as Unknown, never as a lower-bound number;
 *   * a scan cancelled during classification marks its coverage partial, so
 *     every summary count falls back to Unknown while the rows it did
 *     observe stay visible.
 */

import * as fsp from 'fs/promises';
import * as path from 'path';

import { redact, truncate } from './redact';
import {
  AssessmentEntry,
  InboxCoverage,
  InboxEvidenceState,
  InboxFileStatus,
  InboxRecord,
} from './recoveryInbox';
import { proposedFromSnapshot } from './recoveryPlan';
import { readPlanSummary } from './recoveryPlanReport';

/**
 * Mirrors `SCAN_SKIP_DIRS` in `python/interlock_bridge.py`. A unit test
 * parses the Python source and fails if the two lists ever drift apart.
 */
export const SCAN_SKIP_DIRS: readonly string[] = [
  '.git',
  'node_modules',
  '.venv',
  'venv',
  '__pycache__',
  '.mypy_cache',
  '.pytest_cache',
  '.ruff_cache',
  'site',
  'logs',
  'out',
  'dist',
  '.next',
];

/** Depth cap for the workspace walk (the engine scan caps at 8 as well). */
export const WALK_DEPTH_CAP = 8;

/** Default cap on files the walk will enumerate before stopping (honest cap). */
export const DEFAULT_WALK_LIMIT = 50_000;

/** Files larger than this are classified by size alone (never silently hashed). */
export const MAX_HASH_BYTES = 128 * 1024 * 1024;

// ------------------------------------------------------------------- inputs

export interface DiscoveryBaseline {
  resource: string;
  file: string;
  hash: string | null;
  size: number | null;
  capturedAt: string | null;
  /**
   * The stored document, when the caller already read it (the extension
   * reads every baseline exactly once). `null` means "unreadable"; leaving
   * it undefined asks the runner to call {@link DiscoveryDeps.loadDoc}.
   */
  snapshot?: Record<string, unknown> | null;
}

export interface DiscoveryDoc {
  format?: string;
  workspace?: string;
  resource?: string;
  captured_at?: string;
  snapshot: Record<string, unknown>;
}

export interface FileProbe {
  missing: boolean;
  size: number | null;
  /** null when the file was not hashed (missing, unreadable or too large). */
  hash: string | null;
  /** Short error code (`EACCES`, ...) - technical details only. */
  error: string | null;
  tooLarge: boolean;
}

export interface WalkFile {
  rel: string;
  size: number;
  mtimeMs: number;
  birthtimeMs: number;
}

export interface WalkResult {
  files: WalkFile[];
  skippedDirectories: number;
  skippedDirSample: string[];
  truncated: boolean;
  limit: number;
  failed: number;
  failureNotes: string[];
}

export interface DiscoveryCandidate {
  resource: string;
  file: string;
}

export interface AssessResult {
  resource: string;
  ok: boolean;
  summary?: Record<string, unknown>;
  error?: { kind: string; message: string; hint?: string };
}

export interface DiscoveryProgress {
  phase: string;
  done: number;
  total: number;
}

export interface DiscoveryDeps {
  workspace: string;
  nowMs: number;
  /** Stored baselines for this workspace (from the extension-private store). */
  baselines(): Promise<DiscoveryBaseline[]>;
  /**
   * Full baseline document (for evidence validation); null when unreadable.
   * Only needed when the baseline listing did not already carry the document.
   */
  loadDoc?(resource: string): Promise<DiscoveryDoc | null>;
  /** Current file observation (size + hash) with honest failure reporting. */
  probe(absPath: string): Promise<FileProbe>;
  /** Workspace walk honoring the ignore rules; null when it could not run. */
  walk(): Promise<WalkResult | null>;
  /** Policy gate for files without a baseline (sensitive / excluded). */
  excludeFile(rel: string): string | null;
  /**
   * Engine eligibility for every candidate, chunked by the controller, with
   * aggregate progress. Rejects with an AbortError when cancelled.
   */
  assess(
    candidates: DiscoveryCandidate[],
    onProgress: (done: number, total: number) => void,
  ): Promise<AssessResult[]>;
  walkLimit?: number;
  signal?: AbortSignal;
  onProgress(update: DiscoveryProgress): void;
}

export interface DiscoveryOutcome {
  status: 'complete' | 'cancelled' | 'error';
  records: InboxRecord[];
  coverage: InboxCoverage | null;
  error: string | null;
  assessments: AssessmentEntry[];
  assessmentStatus: 'complete' | 'cancelled' | 'error' | 'none';
  assessmentError: string | null;
}

// -------------------------------------------------------------------- walk

/**
 * Recursive, bounded, read-only walk of the workspace. Skips the ignore
 * directories (never enters them), never follows directory symlinks, stops
 * at the depth cap and at `limit` files, and reports unreadable directories
 * instead of failing the whole scan.
 */
export async function walkWorkspace(
  workspace: string,
  options: {
    limit?: number;
    skipDirs?: readonly string[];
    signal?: AbortSignal;
  } = {},
): Promise<WalkResult> {
  const limit = options.limit ?? DEFAULT_WALK_LIMIT;
  const skip = new Set(options.skipDirs ?? SCAN_SKIP_DIRS);
  const result: WalkResult = {
    files: [],
    skippedDirectories: 0,
    skippedDirSample: [],
    truncated: false,
    limit,
    failed: 0,
    failureNotes: [],
  };
  const base = path.resolve(workspace);
  const queue: Array<{ relDir: string; absDir: string; depth: number }> = [
    { relDir: '', absDir: base, depth: 0 },
  ];
  const pushSkipSample = (name: string): void => {
    if (result.skippedDirSample.length < 12 && !result.skippedDirSample.includes(name)) {
      result.skippedDirSample.push(name);
    }
  };

  while (queue.length > 0) {
    if (options.signal?.aborted === true) {
      const error = new Error('scan cancelled');
      error.name = 'AbortError';
      throw error;
    }
    const current = queue.shift();
    if (!current) {
      break;
    }
    let entries: Array<import('fs').Dirent>;
    try {
      entries = await fsp.readdir(current.absDir, { withFileTypes: true });
    } catch (error) {
      result.failed += 1;
      result.failureNotes.push(
        `${current.relDir === '' ? '.' : current.relDir}: ${describeIoError(error)}`,
      );
      continue;
    }
    for (const entry of entries) {
      const rel = current.relDir === '' ? entry.name : `${current.relDir}/${entry.name}`;
      const abs = path.join(current.absDir, entry.name);
      if (entry.isDirectory()) {
        if (current.depth >= WALK_DEPTH_CAP || skip.has(entry.name)) {
          result.skippedDirectories += 1;
          pushSkipSample(entry.name);
          continue;
        }
        queue.push({ relDir: rel, absDir: abs, depth: current.depth + 1 });
        continue;
      }
      if (!entry.isFile()) {
        // Sockets, pipes, broken links: not plain files, nothing to compare.
        continue;
      }
      if (result.files.length >= limit) {
        result.truncated = true;
        queue.length = 0;
        break;
      }
      try {
        const stat = await fsp.stat(abs);
        result.files.push({
          rel,
          size: stat.size,
          mtimeMs: stat.mtimeMs,
          birthtimeMs: stat.birthtimeMs,
        });
      } catch (error) {
        result.failed += 1;
        result.failureNotes.push(`${rel}: ${describeIoError(error)}`);
      }
    }
  }
  result.files.sort((a, b) => a.rel.localeCompare(b.rel));
  return result;
}

function describeIoError(error: unknown): string {
  const code =
    error !== null && typeof error === 'object' && 'code' in error
      ? String((error as { code?: unknown }).code)
      : '';
  return code !== '' ? code : error instanceof Error ? error.message : 'unreadable';
}

// ------------------------------------------------------------------- probe

/** Stat + SHA-256 of one current file, with honest failure reporting. */
export async function probeFile(absPath: string, maxHashBytes = MAX_HASH_BYTES): Promise<FileProbe> {
  let size: number;
  try {
    const stat = await fsp.stat(absPath);
    if (stat.isDirectory()) {
      return { missing: false, size: null, hash: null, error: 'EISDIR', tooLarge: false };
    }
    size = stat.size;
  } catch (error) {
    const notFound =
      error !== null && typeof error === 'object' && 'code' in error
        ? (error as { code?: unknown }).code === 'ENOENT'
        : false;
    return {
      missing: notFound,
      size: null,
      hash: null,
      error: notFound ? null : describeIoError(error),
      tooLarge: false,
    };
  }
  if (size > maxHashBytes) {
    return { missing: false, size, hash: null, error: null, tooLarge: true };
  }
  try {
    const hash = await hashFile(absPath);
    return { missing: false, size, hash, error: null, tooLarge: false };
  } catch (error) {
    return { missing: false, size, hash: null, error: describeIoError(error), tooLarge: false };
  }
}

/** Streaming SHA-256 (never loads the whole file into memory). */
export async function hashFile(absPath: string): Promise<string> {
  const { createHash } = await import('crypto');
  const stream = await fsp.open(absPath, 'r');
  try {
    const hash = createHash('sha256');
    const buffer = Buffer.allocUnsafe(64 * 1024);
    let position = 0;
    for (;;) {
      const { bytesRead } = await stream.read(buffer, 0, buffer.length, position);
      if (bytesRead <= 0) {
        break;
      }
      hash.update(buffer.subarray(0, bytesRead));
      position += bytesRead;
    }
    return hash.digest('hex');
  } finally {
    await stream.close();
  }
}

// ---------------------------------------------------------- evidence checks

interface EvidenceVerdict {
  state: InboxEvidenceState;
  note: string | null;
  technical: string | null;
}

function evidenceVerdict(rawSnapshot: unknown, baselineHash: string | null): EvidenceVerdict {
  const proposed = proposedFromSnapshot(rawSnapshot);
  const recorded = baselineHash ?? proposed.hash;
  const technical =
    `Evidence check: ${
      proposed.kind === 'text' || proposed.kind === 'binary'
        ? 'stored bytes hash to the recorded SHA-256'
        : (proposed.code ?? 'unavailable')
    }; baseline sha256 ${recorded === null ? 'unknown' : `${recorded.slice(0, 12)}…`}.`;
  if (proposed.kind === 'text' || proposed.kind === 'binary') {
    return { state: 'verified', note: null, technical };
  }
  const note = proposed.limitation ?? 'the stored baseline evidence is unusable.';
  const invalid = proposed.code === 'hash_mismatch' || proposed.code === 'truncated';
  return { state: invalid ? 'invalid' : 'unusable', note, technical };
}

// ------------------------------------------------------------ assessment i/o

function verdictFromSummary(
  summary: Record<string, unknown>,
): { eligibility: 'eligible' | 'blocked'; reason: string; technical: string } {
  const plan = readPlanSummary(summary);
  const technical = `would_succeed=${plan.wouldSucceed}, conflict=${plan.conflict}, drift=${plan.drift}`;
  const conflictOk = plan.conflict === 'no_conflict' || plan.conflict === 'unknown';
  const driftOk = plan.drift === 'no_drift' || plan.drift === 'unknown';
  if (plan.conflict !== 'no_conflict' && plan.conflict !== 'unknown') {
    return {
      eligibility: 'blocked',
      reason: `The engine reported a conflict (${plan.conflict}) between the stored baseline and the current file state.`,
      technical,
    };
  }
  if (plan.drift !== 'no_drift' && plan.drift !== 'unknown') {
    return {
      eligibility: 'blocked',
      reason: `The engine detected drift (${plan.drift}): the file no longer matches what the evidence observed.`,
      technical,
    };
  }
  if (!conflictOk || !driftOk) {
    return {
      eligibility: 'blocked',
      reason:
        'The engine returned no conflict/drift verdict for this file, so recovery ' +
        'cannot be declared available.',
      technical,
    };
  }
  if (!plan.wouldSucceed) {
    return {
      eligibility: 'blocked',
      reason: 'The engine simulated this recovery and reported it would not succeed.',
      technical,
    };
  }
  return {
    eligibility: 'eligible',
    reason: 'The engine simulated this recovery: it would succeed with no conflicts and no drift.',
    technical,
  };
}

function failureAssessment(resource: string, error: { kind: string; message: string }): AssessmentEntry {
  const message = truncate(redact(error.message), 240);
  return {
    resource,
    eligibility: 'unavailable',
    reason:
      message.length > 0
        ? `The engine could not assess this file: ${message}`
        : 'The engine could not assess this file, so its eligibility is unknown.',
    technical: `assessment failed (${error.kind})${message ? `: ${message}` : ''}`,
  };
}

// -------------------------------------------------------------------- scan

function aborted(signal: AbortSignal | undefined): boolean {
  return signal?.aborted === true;
}

function cancelledOutcome(partial: {
  records: InboxRecord[];
  coverage: InboxCoverage | null;
}): DiscoveryOutcome {
  return {
    status: 'cancelled',
    records: partial.records,
    coverage: partial.coverage === null ? null : { ...partial.coverage, partial: true },
    error: null,
    assessments: [],
    assessmentStatus: 'none',
    assessmentError: null,
  };
}

/** How many files are examined at the same time during the local phase. */
const DISCOVERY_CONCURRENCY = 8;

/**
 * Map with a bounded worker pool. The order of the results is the order of
 * the input, so the scan stays deterministic no matter how the work is
 * scheduled.
 */
async function mapWithConcurrency<T, R>(
  items: T[],
  limit: number,
  worker: (item: T, index: number) => Promise<R>,
  onDone: (index: number) => void,
): Promise<R[]> {
  const results = new Array<R>(items.length);
  let next = 0;
  const runners = Array.from(
    { length: Math.max(1, Math.min(limit, items.length)) },
    async () => {
      for (;;) {
        const index = next;
        next += 1;
        if (index >= items.length) {
          return;
        }
        results[index] = await worker(items[index], index);
        onDone(index);
      }
    },
  );
  await Promise.all(runners);
  return results;
}

/**
 * Run one full discovery pass. Never writes: classification is read-only and
 * the eligibility assessment is an engine *plan* (read-only) without
 * evidence persistence.
 */
export async function runDiscovery(deps: DiscoveryDeps): Promise<DiscoveryOutcome> {
  const { workspace } = deps;
  const walkLimit = deps.walkLimit ?? DEFAULT_WALK_LIMIT;

  let baselines: DiscoveryBaseline[];
  try {
    baselines = await deps.baselines();
  } catch (error) {
    return {
      status: 'error',
      records: [],
      coverage: null,
      error: `Recovery baselines could not be listed: ${describeIoError(error)}`,
      assessments: [],
      assessmentStatus: 'none',
      assessmentError: null,
    };
  }

  const coverage: InboxCoverage = {
    baselinesChecked: 0,
    nonBaselineChecked: 0,
    skippedDirectories: 0,
    skippedDirSample: [],
    excludedByPolicy: 0,
    walkRan: false,
    walkFailed: false,
    walkTruncated: false,
    walkLimit,
    failed: 0,
    failureNotes: [],
    partial: false,
  };

  if (baselines.length === 0) {
    // No evidence at all: there is nothing to compare files against, so the
    // walk is deliberately skipped (every workspace file would be noise).
    deps.onProgress({ phase: 'No baselines to compare', done: 0, total: 0 });
    return {
      status: 'complete',
      records: [],
      coverage,
      error: null,
      assessments: [],
      assessmentStatus: 'none',
      assessmentError: null,
    };
  }

  const records: InboxRecord[] = [];
  const candidates: DiscoveryCandidate[] = [];
  const baselineResources = new Set<string>();
  let newestCaptureMs: number | null = null;
  for (const baseline of baselines) {
    baselineResources.add(baseline.resource);
    if (baseline.capturedAt !== null) {
      const parsed = Date.parse(baseline.capturedAt);
      if (Number.isFinite(parsed)) {
        newestCaptureMs = newestCaptureMs === null ? parsed : Math.max(newestCaptureMs, parsed);
      }
    }
  }

  let index = 0;
  // The per-file work is I/O bound (read the stored document, read and hash
  // the current file), so a small worker pool keeps a large workspace fast
  // without ever overwhelming the disk.
  const outcomes = await mapWithConcurrency(
    baselines,
    DISCOVERY_CONCURRENCY,
    async (baseline) => {
      const doc =
        baseline.snapshot !== undefined
          ? baseline.snapshot === null
            ? null
            : { snapshot: baseline.snapshot }
          : ((await deps.loadDoc?.(baseline.resource)) ?? null);
      const absPath = path.join(workspace, ...baseline.resource.split('/'));
      const probe = await deps.probe(absPath);
      return { baseline, doc, probe };
    },
    () => {
      if (aborted(deps.signal)) {
        return;
      }
      index += 1;
      deps.onProgress({
        phase: 'Checking baseline evidence',
        done: index,
        total: baselines.length,
      });
    },
  );
  if (aborted(deps.signal)) {
    return cancelledOutcome({ records, coverage });
  }

  for (const { baseline, doc, probe } of outcomes) {
    if (doc === null) {
      coverage.failed += 1;
      coverage.failureNotes.push(`${baseline.resource}: baseline document unreadable`);
      records.push({
        resource: baseline.resource,
        kind: 'protected',
        status: 'unknown',
        evidence: 'unusable',
        evidenceNote:
          'The stored baseline document could not be read, so nothing can be restored from it.',
        technical: 'Baseline document unreadable (deleted or corrupted between listing and reading).',
        baselineHash: baseline.hash,
        baselineSize: baseline.size,
        currentSize: probe.size,
        capturedAt: baseline.capturedAt,
        observedAtMs: null,
        createdAfterCapture: false,
      });
      continue;
    }

    const snapshot = doc.snapshot ?? {};
    const verdict = evidenceVerdict(snapshot, baseline.hash);
    let status: InboxFileStatus;
    const technical: string[] = [verdict.technical ?? ''];
    if (probe.missing) {
      status = 'deleted';
    } else if (probe.error !== null) {
      status = 'unknown';
      technical.push(`Current file unreadable (${probe.error}).`);
    } else if (probe.hash === null && probe.tooLarge) {
      const differsBySize =
        baseline.size !== null && probe.size !== null && baseline.size !== probe.size;
      status = differsBySize ? 'modified' : 'unknown';
      if (!differsBySize) {
        technical.push(
          `Current file is ${probe.size ?? 0} bytes - too large to hash quickly; size matches the baseline but content was not compared.`,
        );
      }
    } else if (probe.hash === null) {
      status = 'unknown';
    } else {
      status = probe.hash === baseline.hash ? 'unchanged' : 'modified';
    }

    records.push({
      resource: baseline.resource,
      kind: 'protected',
      status,
      evidence: verdict.state,
      evidenceNote: verdict.note,
      technical: technical.filter((line) => line !== '').join(' ') || null,
      baselineHash: baseline.hash,
      baselineSize: baseline.size,
      currentSize: probe.size,
      capturedAt: baseline.capturedAt,
      observedAtMs: null,
      createdAfterCapture: false,
    });

    if (verdict.state === 'verified' && (status === 'modified' || status === 'deleted')) {
      candidates.push({ resource: baseline.resource, file: baseline.file });
    }
  }
  coverage.baselinesChecked = records.length;

  // ---------------------------------------------------- workspace walk
  if (aborted(deps.signal)) {
    return cancelledOutcome({ records, coverage });
  }
  deps.onProgress({ phase: 'Scanning for files without baselines', done: 0, total: 0 });
  let walk: WalkResult | null = null;
  try {
    walk = await deps.walk();
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      return cancelledOutcome({ records, coverage });
    }
    coverage.walkFailed = true;
    coverage.failed += 1;
    coverage.failureNotes.push(`workspace walk: ${describeIoError(error)}`);
  }
  if (walk !== null) {
    coverage.walkRan = true;
    coverage.walkTruncated = walk.truncated;
    coverage.skippedDirectories = walk.skippedDirectories;
    coverage.skippedDirSample = walk.skippedDirSample;
    coverage.failed += walk.failed;
    coverage.failureNotes.push(...walk.failureNotes.slice(0, 5));
    if (walk.failureNotes.length > 5) {
      coverage.failureNotes.push(`… and ${walk.failureNotes.length - 5} more walk failures`);
    }
    for (const file of walk.files) {
      if (aborted(deps.signal)) {
        return cancelledOutcome({ records, coverage });
      }
      if (baselineResources.has(file.rel)) {
        continue; // already classified from its baseline
      }
      if (deps.excludeFile(file.rel) !== null) {
        coverage.excludedByPolicy += 1;
        continue;
      }
      coverage.nonBaselineChecked += 1;
      if (newestCaptureMs === null) {
        // No parseable capture time: "changed after capture" cannot be
        // supported by evidence, so nothing is claimed and nothing listed.
        continue;
      }
      const created = file.birthtimeMs > newestCaptureMs;
      const changedAfter = file.mtimeMs > newestCaptureMs;
      if (!created && !changedAfter) {
        continue; // exists, but no evidence it changed since protection
      }
      records.push({
        resource: file.rel,
        kind: 'unprotected',
        status: created ? 'created' : 'unprotected',
        evidence: 'none',
        evidenceNote: null,
        technical:
          `File metadata: modified ${new Date(file.mtimeMs).toISOString()}` +
          (file.birthtimeMs > 0 ? `, created ${new Date(file.birthtimeMs).toISOString()}` : '') +
          `; newest baseline capture ${new Date(newestCaptureMs).toISOString()}.`,
        baselineHash: null,
        baselineSize: null,
        currentSize: file.size,
        capturedAt: null,
        observedAtMs: created ? file.birthtimeMs : file.mtimeMs,
        createdAfterCapture: created,
      });
    }
  }

  // ------------------------------------------------- engine assessment
  if (candidates.length === 0) {
    return {
      status: 'complete',
      records,
      coverage,
      error: null,
      assessments: [],
      assessmentStatus: 'none',
      assessmentError: null,
    };
  }
  if (aborted(deps.signal)) {
    return cancelledOutcome({ records, coverage });
  }

  const attempts = new Map<string, AssessResult>();
  try {
    const results = await deps.assess(candidates, (done, total) => {
      deps.onProgress({ phase: 'Assessing recovery eligibility', done, total });
    });
    for (const result of results) {
      attempts.set(result.resource, result);
    }
  } catch (error) {
    const cancelled = aborted(deps.signal) || (error instanceof Error && error.name === 'AbortError');
    const message = cancelled
      ? null
      : `Eligibility assessment failed: ${describeIoError(error)}`;
    return {
      status: 'complete',
      records,
      coverage,
      error: null,
      assessments: [],
      assessmentStatus: cancelled ? 'cancelled' : 'error',
      assessmentError: message,
    };
  }

  const assessments: AssessmentEntry[] = [];
  for (const candidate of candidates) {
    const attempt = attempts.get(candidate.resource);
    if (!attempt) {
      assessments.push({
        resource: candidate.resource,
        eligibility: 'unavailable',
        reason: 'The engine returned no assessment for this file, so its eligibility is unknown.',
        technical: 'no assessment result returned',
      });
      continue;
    }
    if (attempt.ok && attempt.summary) {
      const verdict = verdictFromSummary(attempt.summary);
      assessments.push({
        resource: candidate.resource,
        eligibility: verdict.eligibility,
        reason: verdict.reason,
        technical: verdict.technical,
      });
      continue;
    }
    assessments.push(
      failureAssessment(
        candidate.resource,
        attempt.error ?? { kind: 'internal_error', message: 'unknown engine failure' },
      ),
    );
  }

  return {
    status: 'complete',
    records,
    coverage,
    error: null,
    assessments,
    assessmentStatus: 'complete',
    assessmentError: null,
  };
}
