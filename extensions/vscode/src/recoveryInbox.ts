/**
 * Recovery Inbox model (pure, headless - no `vscode`, no DOM, no engine).
 *
 * The Inbox answers one question after many automated changes: *what changed
 * in this workspace, and what can actually be recovered?* This module owns
 * every rule behind that answer so the panel, the controller and the tests
 * all agree:
 *
 *   * Discovery produces {@link InboxRecord}s (classification + evidence
 *     validity + engine eligibility). Records become display rows here.
 *   * Every count comes from the validated records. When a value cannot be
 *     derived honestly (no scan, walk truncated, eligibility still pending)
 *     it stays `null` and the renderer shows "Unknown" - never 0.
 *   * Selection lives in the trusted layer: the webview only sends intents,
 *     the model intersects them with its own rows, and the executable set is
 *     recomputed from engine verdicts at recovery time.
 *   * A scan that is stale (workspace changed underneath it) can never enable
 *     a recovery action.
 *   * Ineligible files may sit in a selection (they are explained and
 *     excluded), but they are never silently part of a recovery run.
 */

import { ProposedContent } from './recoveryPlan';

// ----------------------------------------------------------------- scan state

export type InboxScanStatus =
  | 'idle'
  | 'scanning'
  | 'assessing'
  | 'done'
  | 'cancelled'
  | 'error';

export interface InboxScanProgress {
  /** Short live phase label, e.g. "Reading baselines". */
  phase: string;
  done: number;
  total: number;
}

export interface InboxCoverage {
  /** Baselines for this workspace whose stored evidence was examined. */
  baselinesChecked: number;
  /** Files found by the workspace walk that have no baseline at all. */
  nonBaselineChecked: number;
  /** Directories skipped by the ignore rules (never walked). */
  skippedDirectories: number;
  skippedDirSample: string[];
  /** Files refused by the sensitive-file / exclusion policy (never listed). */
  excludedByPolicy: number;
  /** False when the walk deliberately did not run (no baselines to compare). */
  walkRan: boolean;
  /** True when the walk ran but could not complete (unreadable directory). */
  walkFailed: boolean;
  walkTruncated: boolean;
  walkLimit: number;
  /** Per-file failures encountered during the scan (partial coverage). */
  failed: number;
  /** A few short, relative-path failure notes (bounded - never raw dumps). */
  failureNotes: string[];
  /** True when the scan was cancelled during classification: counts are Unknown. */
  partial: boolean;
}

export interface InboxScanState {
  status: InboxScanStatus;
  startedAt: string | null;
  finishedAt: string | null;
  progress: InboxScanProgress | null;
  error: string | null;
  /** Workspace changed after the scan: recovery stays disabled until Refresh. */
  stale: boolean;
  staleReason: string | null;
  coverage: InboxCoverage | null;
  /** Workspace events arrived while the scan/execution owned the workspace. */
  dirtyDuringScan: boolean;
}

// -------------------------------------------------------------------- records

/** What the current file looks like relative to the stored baseline. */
export type InboxFileStatus =
  | 'modified'
  | 'deleted'
  | 'unchanged'
  | 'unknown'
  | 'created'
  | 'unprotected';

/** Validity of the stored recovery evidence for one protected file. */
export type InboxEvidenceState = 'verified' | 'invalid' | 'unusable' | 'none';

/** Engine-backed recovery eligibility for one row. */
export type InboxEligibility =
  | 'pending'
  | 'eligible'
  | 'blocked'
  | 'unavailable'
  | 'none';

/**
 * One discovered file. Produced by the discovery layer (classification,
 * evidence validation, engine assessment) and turned into a display row by
 * this module. Contains only workspace-relative metadata - never contents.
 */
export interface InboxRecord {
  resource: string;
  kind: 'protected' | 'unprotected';
  status: InboxFileStatus;
  evidence: InboxEvidenceState;
  /** Plain-English explanation of the evidence state (protected files). */
  evidenceNote: string | null;
  /** Engine verdict details / read errors - surfaced only in <details>. */
  technical: string | null;
  baselineHash: string | null;
  baselineSize: number | null;
  currentSize: number | null;
  capturedAt: string | null;
  /** Unprotected files: file mtime/birth time evidence (epoch ms). */
  observedAtMs: number | null;
  /** Unprotected files: birth time alone proves it was created after capture. */
  createdAfterCapture: boolean;
}

/** One engine assessment result applied to a candidate row. */
export interface AssessmentEntry {
  resource: string;
  eligibility: 'eligible' | 'blocked' | 'unavailable';
  reason: string;
  technical: string | null;
}

// ----------------------------------------------------------------------- rows

export type InboxTone = 'ok' | 'bad' | 'warn' | 'idle' | 'accent';

export interface InboxRowFlags {
  /** Baseline-relative change (matches the summary count "changed"). */
  changed: boolean;
  unprotected: boolean;
  modified: boolean;
  deleted: boolean;
  unchanged: boolean;
  attention: boolean;
  recoverable: boolean;
}

export interface InboxRow {
  resource: string;
  name: string;
  /** Parent directory inside the workspace (`.` for the workspace root). */
  dir: string;
  kind: 'protected' | 'unprotected';
  status: InboxFileStatus;
  statusLabel: string;
  statusTone: InboxTone;
  evidence: InboxEvidenceState;
  evidenceLabel: string;
  evidenceTone: InboxTone;
  eligibility: InboxEligibility;
  eligibilityLabel: string;
  eligibilityTone: InboxTone;
  /** Plain-English reason shown on the row (always present). */
  reason: string;
  /** Technical detail for the per-row disclosure (verdicts/errors only). */
  details: string | null;
  previewable: boolean;
  previewNote: string | null;
  baselineHash: string | null;
  capturedAt: string | null;
  flags: InboxRowFlags;
  /** Sort keys (display only): smaller sorts first. */
  rankStatus: number;
  rankEligibility: number;
}

export interface InboxCounts {
  /** null renders as "Unknown" - never as 0. */
  examined: number | null;
  changed: number | null;
  verifiedEvidence: number | null;
  recoverableModified: number | null;
  recoverableDeleted: number | null;
  attention: number | null;
  noBaseline: number | null;
}

// ------------------------------------------------------------ review/results

export interface InboxReviewEntry {
  resource: string;
  name: string;
  dir: string;
  operation: string | null;
  /** True when the native diff can honestly show the exact proposed bytes. */
  diffable: boolean;
  previewNote: string | null;
}

export interface InboxReviewExcluded {
  resource: string;
  name: string;
  dir: string;
  reason: string;
}

export interface InboxReview {
  scope: 'selected' | 'all' | 'retry';
  at: string;
  /** Every row that entered this review (the requested scope). */
  requested: number;
  included: InboxReviewEntry[];
  excluded: InboxReviewExcluded[];
  /** Batch warnings (binary rows, non-diffable rows) - exact counts. */
  warnings: string[];
  /** Set when a confirmation found changed files and renewed the review. */
  notice: string | null;
  /** Exact scope of a "Recover All" run (changed / eligible / attention / no baseline). */
  scopeCounts: {
    changed: number;
    eligible: number;
    attention: number;
    noBaseline: number;
  } | null;
}

export type InboxRunOutcome =
  | 'recovered'
  | 'skipped'
  | 'failed'
  | 'attention';

/**
 * The honest outcome of one file write. `success` is true only when the
 * engine AND the extension verified the restored bytes; a skipped file was
 * never written (its precondition no longer held).
 */
export interface ApplyOutcome {
  resource: string;
  success: boolean;
  skipped: boolean;
  verified: boolean;
  message: string;
  details: string | null;
}

export interface InboxRunEntry {
  resource: string;
  name: string;
  dir: string;
  outcome: InboxRunOutcome;
  label: string;
  tone: InboxTone;
  /** Plain-English result, always explicit about verification. */
  message: string;
  /** True only when the engine AND the extension verified byte-exact bytes. */
  verified: boolean;
  details: string | null;
  diffable: boolean;
}

export interface InboxRunResults {
  scope: 'selected' | 'all' | 'retry';
  startedAt: string;
  finishedAt: string | null;
  /** Truthful approver identity recorded for this run (never invented). */
  approvedBy: string;
  entries: InboxRunEntry[];
  counts: {
    recovered: number;
    skipped: number;
    failed: number;
    attention: number;
    total: number;
  };
  /** True while files are still being processed. */
  running: boolean;
}

// -------------------------------------------------------------------- action

export interface InboxAction {
  enabled: boolean;
  /** Button label (the count is part of the label when actionable). */
  label: string;
  /** Why the button is disabled - shown next to it, never hidden. */
  note: string;
}

// -------------------------------------------------------------------- labels

const STATUS_LABELS: Record<InboxFileStatus, string> = {
  modified: 'Modified',
  deleted: 'Deleted',
  unchanged: 'Unchanged',
  unknown: 'Unknown',
  created: 'New file',
  unprotected: 'Changed, no baseline',
};

const STATUS_TONES: Record<InboxFileStatus, InboxTone> = {
  modified: 'warn',
  deleted: 'warn',
  unchanged: 'ok',
  unknown: 'bad',
  created: 'idle',
  unprotected: 'warn',
};

const EVIDENCE_LABELS: Record<InboxEvidenceState, string> = {
  verified: 'Verified',
  invalid: 'Invalid',
  unusable: 'Unusable',
  none: 'No baseline',
};

const EVIDENCE_TONES: Record<InboxEvidenceState, InboxTone> = {
  verified: 'ok',
  invalid: 'bad',
  unusable: 'warn',
  none: 'idle',
};

const ELIGIBILITY_LABELS: Record<InboxEligibility, string> = {
  pending: 'Assessing…',
  eligible: 'Recoverable',
  blocked: 'Blocked',
  unavailable: 'Not recoverable',
  none: 'Not needed',
};

const ELIGIBILITY_TONES: Record<InboxEligibility, InboxTone> = {
  pending: 'idle',
  eligible: 'ok',
  blocked: 'bad',
  unavailable: 'warn',
  none: 'idle',
};

export const INBOX_FILTERS = [
  { id: 'all-changed', label: 'All Changed' },
  { id: 'recoverable', label: 'Recoverable' },
  { id: 'modified', label: 'Modified' },
  { id: 'deleted', label: 'Deleted' },
  { id: 'attention', label: 'Needs Attention' },
  { id: 'not-recoverable', label: 'Not Recoverable' },
  { id: 'unchanged', label: 'Unchanged' },
] as const;

export type InboxFilterId = (typeof INBOX_FILTERS)[number]['id'];

const STATUS_RANK: Record<InboxFileStatus, number> = {
  modified: 0,
  deleted: 1,
  created: 2,
  unprotected: 3,
  unknown: 4,
  unchanged: 5,
};

const ELIGIBILITY_RANK: Record<InboxEligibility, number> = {
  eligible: 0,
  pending: 1,
  blocked: 2,
  unavailable: 3,
  none: 4,
};

// ------------------------------------------------------------------ helpers

function basenameOf(path: string): string {
  const parts = path.split('/');
  const last = parts[parts.length - 1];
  return last !== undefined && last !== '' ? last : path;
}

function dirnameOf(path: string): string {
  const parts = path.split('/');
  parts.pop();
  return parts.length > 0 ? parts.join('/') : '.';
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'}`;
}

function display(sentence: string): string {
  const trimmed = sentence.trim();
  if (trimmed === '') {
    return '';
  }
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
}

// ------------------------------------------------------------ row derivation

interface Derived {
  eligibility: InboxEligibility;
  reason: string;
  technical: string | null;
  evidenceNote: string | null;
}

/**
 * Eligibility for a record the engine has not assessed yet. Everything that
 * cannot be recovered says so here, in plain words, with the evidence state
 * as the reason - the engine verdicts only ever replace `pending`.
 */
function deriveUnassessed(record: InboxRecord): Derived {
  const technical = record.technical;
  if (record.kind === 'unprotected') {
    const reason = record.createdAfterCapture
      ? 'Created after your recovery baselines were captured (file creation time ' +
        'evidence), so there is no saved prior version to recover.'
      : 'Changed after your recovery baselines were captured but has no stored ' +
        'baseline, so there is nothing exact to restore.';
    return { eligibility: 'unavailable', reason, technical, evidenceNote: record.evidenceNote };
  }
  if (record.status === 'unchanged') {
    return {
      eligibility: 'none',
      reason: 'The current file matches the captured baseline - nothing to recover.',
      technical,
      evidenceNote: record.evidenceNote,
    };
  }
  if (record.evidence !== 'verified') {
    const reason =
      record.evidenceNote ??
      (record.evidence === 'invalid'
        ? 'The stored baseline evidence failed validation. Recapture the baseline before recovering.'
        : 'No usable baseline contents were captured for this file, so there is nothing exact to restore.');
    return { eligibility: 'unavailable', reason, technical, evidenceNote: record.evidenceNote };
  }
  if (record.status === 'unknown') {
    return {
      eligibility: 'unavailable',
      reason:
        'The current file could not be compared against the baseline, so recovery ' +
        'eligibility cannot be confirmed.',
      technical,
      evidenceNote: record.evidenceNote,
    };
  }
  return {
    eligibility: 'pending',
    reason: 'The engine has not assessed this file yet. Eligibility appears when the scan completes.',
    technical,
    evidenceNote: record.evidenceNote,
  };
}

function buildRow(record: InboxRecord): InboxRow {
  const derived = deriveUnassessed(record);
  const evidence = record.evidence;
  const eligibility = derived.eligibility;
  const flags: InboxRowFlags = {
    changed: record.kind === 'protected' && (record.status === 'modified' || record.status === 'deleted'),
    unprotected: record.kind === 'unprotected',
    modified: record.status === 'modified',
    deleted: record.status === 'deleted',
    unchanged: record.status === 'unchanged',
    attention: false,
    recoverable: eligibility === 'eligible',
  };
  flags.attention =
    flags.unprotected === false &&
    (evidence === 'invalid' ||
      evidence === 'unusable' ||
      record.status === 'unknown' ||
      eligibility === 'blocked');

  const diffCapable = record.kind === 'protected' && record.status !== 'unchanged';
  const previewable = diffCapable && evidence === 'verified';
  const previewNote = previewable
    ? null
    : record.kind === 'unprotected'
      ? 'No baseline exists for this file, so there is no prior version to preview.'
      : record.status === 'unchanged'
        ? 'The file already matches its baseline - there is nothing to preview.'
        : 'Recovery evidence for this file is unavailable, so no honest preview can exist.';

  return {
    resource: record.resource,
    name: basenameOf(record.resource),
    dir: dirnameOf(record.resource),
    kind: record.kind,
    status: record.status,
    statusLabel: STATUS_LABELS[record.status],
    statusTone: STATUS_TONES[record.status],
    evidence,
    evidenceLabel: EVIDENCE_LABELS[evidence],
    evidenceTone: EVIDENCE_TONES[evidence],
    eligibility,
    eligibilityLabel: ELIGIBILITY_LABELS[eligibility],
    eligibilityTone: ELIGIBILITY_TONES[eligibility],
    reason: derived.reason,
    details: derived.technical,
    previewable,
    previewNote,
    baselineHash: record.baselineHash,
    capturedAt: record.capturedAt,
    flags,
    rankStatus: STATUS_RANK[record.status],
    rankEligibility: ELIGIBILITY_RANK[eligibility],
  };
}

// -------------------------------------------------------------------- counts

export interface CountContext {
  status: InboxScanStatus;
  coverage: InboxCoverage | null;
}

function emptyCounts(): InboxCounts {
  return {
    examined: null,
    changed: null,
    verifiedEvidence: null,
    recoverableModified: null,
    recoverableDeleted: null,
    attention: null,
    noBaseline: null,
  };
}

/**
 * Summary counts. Values that cannot be derived honestly stay `null` so the
 * renderer shows "Unknown":
 *   * before a scan finished (or after a failed scan) everything is Unknown;
 *   * recoverable counts stay Unknown while any candidate is still pending
 *     engine assessment;
 *   * the no-baseline count is Unknown when the walk did not run or stopped
 *     early (a partial walk cannot claim a total).
 */
export function buildCounts(rows: InboxRow[], context: CountContext): InboxCounts {
  const { status, coverage } = context;
  if (status === 'idle' || status === 'error' || coverage === null || coverage.partial) {
    return emptyCounts();
  }

  const zeroBaselineCase = coverage.baselinesChecked === 0 && !coverage.walkRan;
  const pendingCandidates = rows.filter((row) => row.eligibility === 'pending').length;

  const counts: InboxCounts = {
    examined: coverage.baselinesChecked + coverage.nonBaselineChecked,
    changed: rows.filter((row) => row.flags.changed).length,
    verifiedEvidence: rows.filter((row) => row.evidence === 'verified').length,
    recoverableModified: null,
    recoverableDeleted: null,
    attention: rows.filter((row) => row.flags.attention).length,
    noBaseline:
      coverage.walkRan && !coverage.walkTruncated
        ? rows.filter((row) => row.kind === 'unprotected').length
        : null,
  };

  if (pendingCandidates > 0) {
    counts.recoverableModified = null;
    counts.recoverableDeleted = null;
  } else {
    counts.recoverableModified = rows.filter(
      (row) => row.flags.modified && row.eligibility === 'eligible',
    ).length;
    counts.recoverableDeleted = rows.filter(
      (row) => row.flags.deleted && row.eligibility === 'eligible',
    ).length;
  }

  if (zeroBaselineCase) {
    // Nothing to compare against and the walk deliberately did not run:
    // the baseline-relative counts are real zeros, the walk-derived one is not.
    counts.examined = 0;
    counts.changed = 0;
    counts.verifiedEvidence = 0;
    counts.recoverableModified = 0;
    counts.recoverableDeleted = 0;
    counts.attention = 0;
    counts.noBaseline = null;
  }

  return counts;
}

// ---------------------------------------------------------------- coverage UI

export function coverageLines(coverage: InboxCoverage | null): string[] {
  if (coverage === null) {
    return [];
  }
  const lines: string[] = [];
  lines.push(
    `${plural(coverage.baselinesChecked, 'baseline file')} checked against its stored evidence.`,
  );
  if (coverage.walkRan) {
    lines.push(
      `${plural(coverage.nonBaselineChecked, 'file')} without a baseline examined ` +
        `(${coverage.skippedDirectories} director${coverage.skippedDirectories === 1 ? 'y' : 'ies'} ` +
        `skipped by the ignore rules${
          coverage.skippedDirSample.length > 0
            ? `: ${coverage.skippedDirSample.slice(0, 6).join(', ')}`
            : ''
        }).`,
    );
  } else if (coverage.walkFailed) {
    lines.push(
      'The workspace walk could not be completed, so files without baselines ' +
        'were not fully examined. Counts that depend on the walk show Unknown.',
    );
  } else {
    lines.push(
      'Workspace walk skipped: there are no recovery baselines to compare files against yet.',
    );
  }
  if (coverage.excludedByPolicy > 0) {
    lines.push(
      `${plural(coverage.excludedByPolicy, 'file')} excluded by the sensitive-file / exclusion policy (never recoverable).`,
    );
  }
  if (coverage.walkTruncated) {
    lines.push(
      `The workspace walk stopped at its safety limit of ${coverage.walkLimit.toLocaleString('en-US')} ` +
        'files, so coverage is PARTIAL - counts that depend on the walk show Unknown.',
    );
  }
  if (coverage.failed > 0) {
    lines.push(
      `${plural(coverage.failed, 'file')} could not be read during this scan; ` +
        'their rows say so instead of guessing.',
    );
  }
  return lines;
}

// ----------------------------------------------------------------- selection

export interface SelectionSummary {
  count: number;
  eligible: number;
  attention: number;
  pending: number;
  /** "12 files selected · 10 eligible · 2 require attention" */
  text: string;
}

export function selectionSummaryText(summary: Omit<SelectionSummary, 'text'>): string {
  const parts = [`${summary.count} file${summary.count === 1 ? '' : 's'} selected`];
  parts.push(`${summary.eligible} eligible`);
  if (summary.pending > 0) {
    parts.push(`${summary.pending} assessing`);
  }
  parts.push(`${summary.attention} require attention`);
  return parts.join(' · ');
}

// --------------------------------------------------------------------- state

export interface InboxActionContext {
  workspaceName: string | null;
}

/**
 * The authoritative Inbox state. The controller mutates it only through the
 * methods below; the panel renders a {@link InboxViewState} snapshot and the
 * webview only ever sends intents back.
 */
export class InboxState {
  readonly workspace: string;
  scan: InboxScanState;
  rows: InboxRow[] = [];
  counts: InboxCounts = emptyCounts();
  mode: 'list' | 'review' | 'results' = 'list';
  review: InboxReview | null = null;
  results: InboxRunResults | null = null;
  notice: string | null = null;
  /** Non-null while a scan / plan / execution owns the workspace. */
  busy: string | null = null;
  private readonly selection = new Set<string>();

  constructor(workspace: string, nowMs: number = Date.now()) {
    this.workspace = workspace;
    this.scan = {
      status: 'idle',
      startedAt: new Date(nowMs).toISOString(),
      finishedAt: null,
      progress: null,
      error: null,
      stale: false,
      staleReason: null,
      coverage: null,
      dirtyDuringScan: false,
    };
  }

  // ------------------------------------------------------------- scan events

  beginScan(nowMs: number = Date.now()): void {
    this.scan = {
      status: 'scanning',
      startedAt: new Date(nowMs).toISOString(),
      finishedAt: null,
      progress: { phase: 'Reading recovery baselines', done: 0, total: 0 },
      error: null,
      stale: false,
      staleReason: null,
      coverage: null,
      dirtyDuringScan: this.scan.dirtyDuringScan,
    };
    this.selection.clear();
    this.mode = 'list';
    this.review = null;
    this.results = null;
    this.notice = null;
  }

  setProgress(phase: string, done: number, total: number): void {
    this.scan.progress = { phase, done, total };
  }

  /**
   * Local discovery finished: rows + coverage are in. Eligibility may still
   * be pending while the engine assessment runs.
   */
  applyDiscovery(records: InboxRecord[], coverage: InboxCoverage, nowMs: number = Date.now()): void {
    const sorted = [...records].sort((a, b) => a.resource.localeCompare(b.resource));
    this.rows = sorted.map(buildRow);
    this.scan.coverage = coverage;
    this.scan.status = 'assessing';
    this.scan.finishedAt = new Date(nowMs).toISOString();
    this.selection.clear();
    this.mode = 'list';
    this.review = null;
    this.results = null;
    this.recount();
  }

  /** Apply one chunk of engine assessment verdicts. */
  applyAssessment(entries: AssessmentEntry[]): void {
    const byResource = new Map(entries.map((entry) => [entry.resource, entry]));
    let touched = false;
    this.rows = this.rows.map((row) => {
      const entry = byResource.get(row.resource);
      if (!entry) {
        return row;
      }
      touched = true;
      const eligibility = entry.eligibility;
      const flags: InboxRowFlags = { ...row.flags, recoverable: eligibility === 'eligible' };
      flags.attention =
        row.flags.unprotected === false &&
        (row.evidence === 'invalid' ||
          row.evidence === 'unusable' ||
          row.status === 'unknown' ||
          eligibility === 'blocked');
      return {
        ...row,
        eligibility,
        eligibilityLabel: ELIGIBILITY_LABELS[eligibility],
        eligibilityTone: ELIGIBILITY_TONES[eligibility],
        reason: entry.reason,
        details: entry.technical ?? row.details,
        flags,
        rankEligibility: ELIGIBILITY_RANK[eligibility],
      };
    });
    if (touched) {
      this.recount();
    }
  }

  finishScan(status: 'done' | 'cancelled' | 'error', error: string | null = null, nowMs: number = Date.now()): void {
    this.scan.status = status;
    this.scan.finishedAt = new Date(nowMs).toISOString();
    this.scan.progress = null;
    this.scan.error = error;
    if (status === 'error' && this.scan.coverage === null) {
      // Nothing trustworthy was discovered: drop any partial rows instead of
      // presenting them as a scan result.
      this.rows = [];
      this.selection.clear();
    }
    if (this.scan.dirtyDuringScan && status === 'done') {
      this.markStale('Workspace files changed while the scan was running.');
    }
    this.recount();
  }

  markStale(reason: string): void {
    this.scan.stale = true;
    this.scan.staleReason = reason;
  }

  clearStale(): void {
    this.scan.stale = false;
    this.scan.staleReason = null;
    this.scan.dirtyDuringScan = false;
  }

  noteWorkspaceEvent(): void {
    if (this.busy !== null || this.scan.status === 'scanning' || this.scan.status === 'assessing') {
      this.scan.dirtyDuringScan = true;
      return;
    }
    if (!this.scan.stale) {
      this.markStale('Workspace files changed since this scan.');
    }
  }

  private recount(): void {
    this.counts = buildCounts(this.rows, {
      status: this.scan.status,
      coverage: this.scan.coverage,
    });
  }

  // -------------------------------------------------------------- selection

  select(resources: Iterable<string>, mode: 'add' | 'remove'): string[] {
    const known = new Set(this.rows.map((row) => row.resource));
    const accepted: string[] = [];
    for (const resource of resources) {
      if (!known.has(resource)) {
        continue; // never select something this scan did not discover
      }
      accepted.push(resource);
      if (mode === 'add') {
        this.selection.add(resource);
      } else {
        this.selection.delete(resource);
      }
    }
    return accepted;
  }

  clearSelection(): void {
    this.selection.clear();
  }

  hasSelection(resource: string): boolean {
    return this.selection.has(resource);
  }

  selectedResources(): string[] {
    const selected = this.selection;
    return this.rows.filter((row) => selected.has(row.resource)).map((row) => row.resource);
  }

  selectionSummary(): SelectionSummary {
    let eligible = 0;
    let attention = 0;
    let pending = 0;
    for (const row of this.rows) {
      if (!this.selection.has(row.resource)) {
        continue;
      }
      if (row.eligibility === 'eligible') {
        eligible += 1;
      } else if (row.eligibility === 'pending') {
        pending += 1;
      }
      if (row.flags.attention) {
        attention += 1;
      }
    }
    const summary: Omit<SelectionSummary, 'text'> = {
      count: this.selection.size,
      eligible,
      attention,
      pending,
    };
    return { ...summary, text: selectionSummaryText(summary) };
  }

  /** Selected rows that are eligible right now, in stable row order. */
  recoverableSelected(): string[] {
    const selected = this.selection;
    return this.rows
      .filter((row) => selected.has(row.resource) && row.eligibility === 'eligible')
      .map((row) => row.resource);
  }

  selectedPendingCount(): number {
    const selected = this.selection;
    return this.rows.filter((row) => selected.has(row.resource) && row.eligibility === 'pending')
      .length;
  }

  // ----------------------------------------------------------- recover scope

  recoverAllScope(): {
    changed: number;
    eligible: number;
    attention: number;
    noBaseline: number;
    candidates: string[];
  } {
    const candidates = this.rows
      .filter((row) => row.flags.recoverable && row.flags.changed && row.evidence === 'verified')
      .map((row) => row.resource);
    return {
      changed: this.rows.filter((row) => row.flags.changed).length,
      eligible: candidates.length,
      attention: this.rows.filter((row) => row.flags.attention).length,
      noBaseline: this.rows.filter((row) => row.kind === 'unprotected').length,
      candidates,
    };
  }

  rowFor(resource: string): InboxRow | undefined {
    return this.rows.find((row) => row.resource === resource);
  }

  // ---------------------------------------------------------------- actions

  recoverSelectedAction(): InboxAction {
    const label = 'Recover Selected';
    if (this.busy !== null) {
      return { enabled: false, label, note: this.busy };
    }
    if (this.scan.status === 'scanning' || this.scan.status === 'assessing') {
      return { enabled: false, label, note: 'The scan is still running - wait for it to finish.' };
    }
    if (this.scan.status === 'idle' || this.scan.status === 'error') {
      return {
        enabled: false,
        label,
        note:
          this.scan.status === 'error'
            ? 'The last scan failed - refresh before recovering anything.'
            : 'No scan has run yet - refresh the inbox first.',
      };
    }
    if (this.scan.stale) {
      return {
        enabled: false,
        label,
        note: this.scan.staleReason ?? 'Workspace changed since the scan - refresh first.',
      };
    }
    const count = this.selection.size;
    if (count === 0) {
      return { enabled: false, label, note: 'Select one or more changed files first.' };
    }
    const pending = this.selectedPendingCount();
    if (pending > 0) {
      return {
        enabled: false,
        label,
        note: `${plural(pending, 'selected file')} ${pending === 1 ? 'has' : 'have'} not been assessed yet - refresh to finish the scan.`,
      };
    }
    const eligible = this.recoverableSelected().length;
    if (eligible === 0) {
      return {
        enabled: false,
        label,
        note: 'None of the selected files is eligible for recovery - see the reasons in the list.',
      };
    }
    return {
      enabled: true,
      label: `${label} (${eligible})`,
      note: `Review ${plural(eligible, 'file')} before anything is written. Nothing is applied without confirmation.`,
    };
  }

  recoverAllAction(): InboxAction {
    const label = 'Recover All Eligible Changed Files';
    if (this.busy !== null) {
      return { enabled: false, label, note: this.busy };
    }
    if (this.scan.status === 'scanning' || this.scan.status === 'assessing') {
      return { enabled: false, label, note: 'The scan is still running - wait for it to finish.' };
    }
    if (this.scan.status !== 'done') {
      return {
        enabled: false,
        label,
        note: 'A complete scan is required before the eligible set can be calculated.',
      };
    }
    if (this.scan.stale) {
      return {
        enabled: false,
        label,
        note: this.scan.staleReason ?? 'Workspace changed since the scan - refresh first.',
      };
    }
    const scope = this.recoverAllScope();
    if (scope.candidates.length === 0) {
      return {
        enabled: false,
        label,
        note: 'No changed file is currently eligible for recovery (see the summary above).',
      };
    }
    return {
      enabled: true,
      label: `Recover All Eligible Changed Files (${scope.candidates.length})`,
      note:
        `${scope.candidates.length} of ${scope.changed} changed file(s) are eligible after ` +
        'engine validation. Every exclusion is listed before you confirm.',
    };
  }

  // ------------------------------------------------------- review / results

  beginReview(review: InboxReview): void {
    this.review = review;
    this.mode = 'review';
  }

  updateReview(mutate: (review: InboxReview) => void): void {
    if (this.review !== null) {
      mutate(this.review);
    }
  }

  setResults(results: InboxRunResults): void {
    this.results = results;
    this.mode = 'results';
  }

  updateResults(mutate: (results: InboxRunResults) => void): void {
    if (this.results !== null) {
      mutate(this.results);
      const counts = { recovered: 0, skipped: 0, failed: 0, attention: 0, total: 0 };
      for (const entry of this.results.entries) {
        counts.total += 1;
        if (entry.outcome === 'recovered') counts.recovered += 1;
        else if (entry.outcome === 'skipped') counts.skipped += 1;
        else if (entry.outcome === 'failed') counts.failed += 1;
        else counts.attention += 1;
      }
      this.results.counts = counts;
    }
  }

  /**
   * After a run, recovered rows become "unchanged" (the engine verified the
   * restored bytes) and the scan is marked stale so nothing else can be
   * recovered from outdated rows without a refresh.
   */
  applyRunOutcomes(entries: Iterable<{ resource: string; outcome: InboxRunOutcome }>): void {
    const byResource = new Map(
      Array.from(entries).map((entry) => [entry.resource, entry] as const),
    );
    this.rows = this.rows.map((row) => {
      const entry = byResource.get(row.resource);
      if (!entry || entry.outcome !== 'recovered') {
        return row;
      }
      const flags: InboxRowFlags = {
        ...row.flags,
        changed: false,
        modified: false,
        deleted: false,
        unchanged: true,
        recoverable: false,
        attention: false,
      };
      this.selection.delete(row.resource);
      return {
        ...row,
        status: 'unchanged',
        statusLabel: STATUS_LABELS.unchanged,
        statusTone: STATUS_TONES.unchanged,
        eligibility: 'none',
        eligibilityLabel: ELIGIBILITY_LABELS.none,
        eligibilityTone: ELIGIBILITY_TONES.none,
        reason: 'Recovered and verified byte-exact in this run.',
        previewable: false,
        previewNote: 'The file matches its baseline again - there is nothing to preview.',
        flags,
        rankStatus: STATUS_RANK.unchanged,
        rankEligibility: ELIGIBILITY_RANK.none,
      };
    });
    this.recount();
    this.markStale('Files were written by the last recovery run - refresh to rescan.');
  }

  setNotice(notice: string | null): void {
    this.notice = notice;
  }

  setBusy(busy: string | null): void {
    this.busy = busy;
  }
}

// ---------------------------------------------------------------- view state

/** Slim, JSON-safe row for the webview (no contents, no absolute paths). */
export interface InboxClientRow {
  resource: string;
  name: string;
  dir: string;
  kind: 'protected' | 'unprotected';
  status: InboxFileStatus;
  statusLabel: string;
  statusTone: InboxTone;
  evidenceLabel: string;
  evidenceTone: InboxTone;
  eligibility: InboxEligibility;
  eligibilityLabel: string;
  eligibilityTone: InboxTone;
  reason: string;
  details: string | null;
  previewable: boolean;
  previewNote: string | null;
  capturedAt: string | null;
  flags: InboxRowFlags;
  rankStatus: number;
  rankEligibility: number;
}

export function clientRows(rows: InboxRow[]): InboxClientRow[] {
  return rows.map((row) => ({
    resource: row.resource,
    name: row.name,
    dir: row.dir,
    kind: row.kind,
    status: row.status,
    statusLabel: row.statusLabel,
    statusTone: row.statusTone,
    evidenceLabel: row.evidenceLabel,
    evidenceTone: row.evidenceTone,
    eligibility: row.eligibility,
    eligibilityLabel: row.eligibilityLabel,
    eligibilityTone: row.eligibilityTone,
    reason: row.reason,
    details: row.details,
    previewable: row.previewable,
    previewNote: row.previewNote,
    capturedAt: row.capturedAt,
    flags: row.flags,
    rankStatus: row.rankStatus,
    rankEligibility: row.rankEligibility,
  }));
}

export interface InboxScanView {
  status: InboxScanStatus;
  statusLabel: string;
  statusNote: string;
  startedAt: string | null;
  finishedAt: string | null;
  progress: InboxScanProgress | null;
  error: string | null;
  stale: boolean;
  staleReason: string | null;
}

function scanView(scan: InboxScanState): InboxScanView {
  const labels: Record<InboxScanStatus, string> = {
    idle: 'Not scanned yet',
    scanning: 'Scanning…',
    assessing: 'Assessing eligibility…',
    done: 'Scan complete',
    cancelled: 'Scan cancelled (partial)',
    error: 'Scan failed',
  };
  let note: string;
  switch (scan.status) {
    case 'idle':
      note = 'Refresh to discover changed files. Nothing is modified by a scan.';
      break;
    case 'scanning':
      note = 'Reading stored evidence and comparing files - no workspace file is written.';
      break;
    case 'assessing':
      note =
        'Classification is done; the engine is validating recovery eligibility. ' +
        'Recoverable counts show Unknown until it finishes.';
      break;
    case 'done':
      note = 'Discovery and eligibility assessment finished.';
      break;
    case 'cancelled':
      note =
        'The scan was cancelled, so some files were never assessed. Rows that did ' +
        'complete are shown; refresh to finish the scan.';
      break;
    case 'error':
      note = scan.error ?? 'The scan failed before results could be trusted.';
      break;
  }
  return {
    status: scan.status,
    statusLabel: labels[scan.status],
    statusNote: note,
    startedAt: scan.startedAt,
    finishedAt: scan.finishedAt,
    progress: scan.progress,
    error: scan.error,
    stale: scan.stale,
    staleReason: scan.staleReason,
  };
}

export interface InboxViewState {
  mode: 'list' | 'review' | 'results';
  workspaceName: string | null;
  scan: InboxScanView;
  counts: InboxCounts;
  coverageLines: string[];
  notice: string | null;
  busy: string | null;
  rows: InboxClientRow[];
  selection: SelectionSummary;
  selectionResources: string[];
  recoverSelected: InboxAction;
  recoverAll: InboxAction;
  review: InboxReview | null;
  results: InboxRunResults | null;
}

export function buildViewState(
  state: InboxState,
  context: InboxActionContext,
): InboxViewState {
  return {
    mode: state.mode,
    workspaceName: context.workspaceName,
    scan: scanView(state.scan),
    counts: state.counts,
    coverageLines: coverageLines(state.scan.coverage),
    notice: state.notice,
    busy: state.busy,
    rows: state.mode === 'list' ? clientRows(state.rows) : [],
    selection: state.selectionSummary(),
    selectionResources: state.mode === 'list' ? state.selectedResources() : [],
    recoverSelected: state.recoverSelectedAction(),
    recoverAll: state.recoverAllAction(),
    review: state.review,
    results: state.results,
  };
}

// ------------------------------------------------------------------ preview

/**
 * Whether a row may open the native diff right now. Preview runs a fresh
 * engine plan for exactly one file, so the gate is evidence + change state.
 */
export function canPreview(row: InboxRow): boolean {
  return row.previewable;
}

/** Short plain-English description of one review entry (never a hash dump). */
export function describeReviewEntry(entry: InboxReviewEntry): string {
  const operation = entry.operation ?? 'restore';
  return `${entry.resource} - ${operation}`;
}

/** Approval-dialog detail for a bulk run: honest, bounded, never omits count. */
export function reviewApprovalDetail(
  review: InboxReview,
  maxLines: number = 40,
): string {
  const lines = review.included.map((entry) => `• ${describeReviewEntry(entry)}`);
  const shown = lines.slice(0, maxLines);
  const rest = lines.length - shown.length;
  const excludedNote =
    review.excluded.length > 0
      ? `\n\n${plural(review.excluded.length, 'file')} from this scope will NOT be recovered ` +
        '(each with its reason is listed in the Recovery Inbox review).'
      : '';
  return (
    `Recovery will overwrite ${plural(review.included.length, 'file')} with the captured ` +
    'baseline (exact bytes, re-checked immediately before writing):\n\n' +
    shown.join('\n') +
    (rest > 0 ? `\n… and ${rest} more file(s) listed in the Recovery Inbox review.` : '') +
    excludedNote +
    '\n\nThe engine re-checks conflicts and containment before writing, verifies ' +
    'byte-exactly afterwards, and the extension re-checks the hash independently.'
  );
}

/** Merge a preview-limited ProposedContent verdict into a row reason. */
export function evidenceReasonFor(proposed: ProposedContent): string | null {
  if (proposed.kind === 'text' || proposed.kind === 'binary') {
    return null;
  }
  return display(proposed.limitation ?? 'the stored baseline evidence is unusable.');
}

// ------------------------------------------------------------ review scope

/** A plan the engine produced for one file of a review scope. */
export interface ReviewPlanLike {
  resource: string;
  operation: string | null;
  diffable: boolean;
  previewNote: string | null;
  applicable: boolean;
  /** Why the engine's fresh plan is not applicable (else null). */
  blockedReason: string | null;
}

export interface ReviewScopeResult {
  included: InboxReviewEntry[];
  excluded: InboxReviewExcluded[];
  warnings: string[];
}

/**
 * Build the review of an exact scope: every requested file appears either in
 * the included list (with what would be written) or in the excluded list
 * (with the reason it will NOT be recovered).
 */
export function buildReviewScope(
  scope: 'selected' | 'all' | 'retry',
  requested: string[],
  plans: Map<string, ReviewPlanLike>,
  errors: Map<string, string>,
  scopeCounts: InboxReview['scopeCounts'] = null,
  /** The scan's own reason per file (used when a file was never planned). */
  reasons: Map<string, string> = new Map(),
): ReviewScopeResult {
  const included: InboxReviewEntry[] = [];
  const excluded: InboxReviewExcluded[] = [];
  for (const resource of requested) {
    const plan = plans.get(resource);
    if (!plan) {
      excluded.push({
        resource,
        name: basenameOf(resource),
        dir: dirnameOf(resource),
        reason:
          errors.get(resource) ??
          reasons.get(resource) ??
          'This file is not eligible for recovery (see its reason in the file list).',
      });
      continue;
    }
    if (!plan.applicable) {
      excluded.push({
        resource,
        name: basenameOf(resource),
        dir: dirnameOf(resource),
        reason:
          plan.blockedReason ??
          "The engine's fresh plan is not applicable for this file.",
      });
      continue;
    }
    included.push({
      resource,
      name: basenameOf(resource),
      dir: dirnameOf(resource),
      operation: plan.operation,
      diffable: plan.diffable,
      previewNote: plan.previewNote,
    });
  }
  const nonDiffable = included.filter((entry) => !entry.diffable).length;
  const warnings: string[] = [];
  if (nonDiffable > 0) {
    warnings.push(
      `${nonDiffable} file(s) cannot be shown as a text diff (binary or truncated baseline). ` +
        'Their bytes and hashes are still verified exactly.',
    );
  }
  void scope;
  void scopeCounts;
  return { included, excluded, warnings };
}

/**
 * Apply the revalidation that happens right before the approval: every file
 * that changed since the review leaves the scope and the confirmation has to
 * happen again for what is left.
 */
export function applyStaleToReview(
  review: InboxReview,
  stale: Array<{ resource: string; reason: string }>,
): InboxReview {
  if (stale.length === 0) {
    return review;
  }
  const staleResources = new Set(stale.map((entry) => entry.resource));
  return {
    ...review,
    included: review.included.filter((entry) => !staleResources.has(entry.resource)),
    excluded: [
      ...review.excluded,
      ...stale.map((entry) => ({
        resource: entry.resource,
        name: basenameOf(entry.resource),
        dir: dirnameOf(entry.resource),
        reason: `Changed since the review (${entry.reason}) - removed from this run.`,
      })),
    ],
    notice:
      `${stale.length} file(s) changed since you reviewed them and were removed from ` +
      'this run. Review the updated scope and confirm again.',
  };
}

// -------------------------------------------------------------- run results

/** A planned recovery, reduced to what a result row needs. */
export interface RunPlanLike {
  resource: string;
  diffable: boolean;
}

function runEntry(
  plan: RunPlanLike,
  outcome: InboxRunOutcome,
  label: string,
  tone: InboxTone,
  message: string,
  verified: boolean,
  details: string | null,
): InboxRunEntry {
  return {
    resource: plan.resource,
    name: basenameOf(plan.resource),
    dir: dirnameOf(plan.resource),
    outcome,
    label,
    tone,
    message,
    verified,
    details,
    diffable: plan.diffable,
  };
}

/** A file that was not written because its precondition no longer held. */
export function skippedRunEntry(plan: RunPlanLike, message: string): InboxRunEntry {
  return runEntry(plan, 'skipped', 'Skipped', 'warn', message, false, null);
}

/**
 * The honest outcome of one file write. A file is only "Recovered" when the
 * engine AND the extension verified the restored bytes; an unverified run is
 * reported as needing attention, never as a success.
 */
export function runEntryFromOutcome(
  plan: RunPlanLike,
  outcome: ApplyOutcome,
): InboxRunEntry {
  if (outcome.success && outcome.verified) {
    return runEntry(
      plan,
      'recovered',
      'Recovered',
      'ok',
      outcome.message,
      true,
      outcome.details,
    );
  }
  if (outcome.skipped) {
    return runEntry(plan, 'skipped', 'Skipped', 'warn', outcome.message, false, outcome.details);
  }
  const unverified = /verif/i.test(outcome.message) && !/verified/i.test(outcome.message);
  return runEntry(
    plan,
    unverified ? 'attention' : 'failed',
    unverified ? 'Needs attention' : 'Failed',
    'bad',
    outcome.message,
    false,
    outcome.details,
  );
}
