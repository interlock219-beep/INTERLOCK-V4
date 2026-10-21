/**
 * Recovery report model (pure).
 *
 * Turns validated {@link PlannedRecovery} records into the structured data a
 * report panel renders: overall status, counted summary, one row per file and
 * a "Safety checks" list. Rendering lives in `recoveryReportHtml.ts`; nothing
 * here touches VS Code, the DOM or the engine.
 *
 * Rules this model enforces, so the UI never has to:
 *
 *   * Every count comes from the validated plans. When a value cannot be
 *     derived it stays `null` and the renderer shows "Unknown" - a missing
 *     measurement is never presented as zero.
 *   * A file is only "Available" when the engine's own verdicts allow the
 *     recovery AND the stored baseline evidence validated (exact bytes,
 *     SHA-256 verified). Anything else is "Blocked" or "Needs review".
 *   * "Ready to review" therefore cannot appear while any validation failed.
 *   * A check that could not run (missing optional dependency, no verdict
 *     returned) reports "Not checked" - never "Passed".
 *   * Only workspace-relative paths and metadata reach the model. File
 *     contents, secrets and absolute paths are never copied in.
 */

import { PlannedRecovery, isApplicable } from './recoveryPlan';
import { PREVIEW_TTL_MS } from './protection';

// ------------------------------------------------------------------- types

/** Overall report status - the most conservative state wins. */
export type ReportStatus = 'ready' | 'review' | 'unavailable';

/** What the workspace file looks like right now (observed at preview time). */
export type FileCurrentState = 'modified' | 'deleted' | 'unchanged' | 'missing' | 'unknown';

/** Whether usable baseline evidence exists for this file. */
export type FileBaselineState = 'available' | 'unavailable' | 'invalid';

/** Whether this file may currently be recovered. */
export type FileEligibility = 'available' | 'blocked' | 'needs_review';

/** Result of one safety check - "failed" and "not_checked" are distinct. */
export type CheckResult = 'passed' | 'attention' | 'failed' | 'not_checked';

export interface ReportFileTechnical {
  baselineHash: string | null;
  currentHash: string | null;
  baselineSize: number | null;
  capturedAt: string | null;
  observedAt: string | null;
  operation: string | null;
  reversibility: string | null;
  matchesBaseline: boolean | null;
  /** Honest per-file ACL status (never presented as a pass when it did not run). */
  aclDetail: string;
  /** Comparison status lines as the engine reported them (never re-derived). */
  comparisons: Array<{ label: string; detail: string }>;
  warnings: string[];
  /** Baseline evidence filename only - never its absolute path. */
  evidenceRef: string | null;
}

export interface ReportFileRow {
  /** Workspace-relative path with forward slashes (never absolute). */
  resource: string;
  /** File name for the row headline. */
  name: string;
  /** Parent directory inside the workspace (`.` for workspace root). */
  dir: string;
  current: FileCurrentState;
  currentLabel: string;
  baseline: FileBaselineState;
  baselineLabel: string;
  eligibility: FileEligibility;
  eligibilityLabel: string;
  /** Plain-language reason when the file is not available (else null). */
  reason: string | null;
  /** True when the native diff can honestly be opened for this row. */
  previewable: boolean;
  /** Why Preview is unavailable/disabled for this row (else null). */
  previewNote: string | null;
  /** True when the observed evidence is inside the freshness window. */
  fresh: boolean;
  technical: ReportFileTechnical;
}

export interface SafetyCheck {
  id: string;
  name: string;
  result: CheckResult;
  resultLabel: string;
  /** One short explanation; exact counts, no raw payloads. */
  detail: string;
}

export interface ReportCounts {
  /** null renders as "Unknown" - never as 0. */
  reviewed: number | null;
  withBaseline: number | null;
  differing: number | null;
  recoverable: number | null;
  attention: number | null;
}

export interface RecoveryReportModel {
  status: ReportStatus;
  statusLabel: string;
  statusNote: string;
  /** Folder display name only (no absolute path). */
  workspaceName: string | null;
  /** ISO-8601 moment the report was built. */
  generatedAt: string;
  /** ISO-8601 moment the evidence was observed (null if unknown). */
  evidenceAt: string | null;
  /** Report-level caveat (e.g. stale evidence), else null. */
  notice: string | null;
  counts: ReportCounts;
  files: ReportFileRow[];
  checks: SafetyCheck[];
}

export interface ReportOptions {
  /** Epoch ms used for the report timestamp and freshness evaluation. */
  nowMs: number;
  /** Absolute workspace path (used only to derive the display name). */
  workspacePath?: string | null;
}

// -------------------------------------------------------------- primitives

const LABELS: Record<FileCurrentState, string> = {
  modified: 'Modified',
  deleted: 'Deleted',
  unchanged: 'Unchanged',
  missing: 'Missing',
  unknown: 'Unknown',
};

const BASELINE_LABELS: Record<FileBaselineState, string> = {
  available: 'Available',
  unavailable: 'Unavailable',
  invalid: 'Invalid',
};

const ELIGIBILITY_LABELS: Record<FileEligibility, string> = {
  available: 'Available',
  blocked: 'Blocked',
  needs_review: 'Needs review',
};

const CHECK_LABELS: Record<CheckResult, string> = {
  passed: 'Passed',
  attention: 'Needs attention',
  failed: 'Failed',
  not_checked: 'Not checked',
};

export const STATUS_LABELS: Record<ReportStatus, string> = {
  ready: 'Ready to review',
  review: 'Review required',
  unavailable: 'Recovery unavailable',
};

/** Turn a lowercase reason sentence into display copy (never rewrites it). */
function display(sentence: string): string {
  const trimmed = sentence.trim();
  if (trimmed.length === 0) {
    return '';
  }
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
}

function basename(path: string): string {
  const parts = path.split(/[\\/]/);
  return parts.length > 0 && parts[parts.length - 1] !== ''
    ? parts[parts.length - 1]
    : path;
}

function dirnameOf(path: string): string {
  const parts = path.split('/');
  parts.pop();
  return parts.length > 0 ? parts.join('/') : '.';
}

function isValidIso(value: string): boolean {
  return Number.isFinite(Date.parse(value));
}

// --------------------------------------------------------- ACL explanation

/**
 * Honest, plain-language explanation of an ACL capture failure. The raw error
 * stays visible (technical details) - the check is reported as NOT run.
 */
export function explainAclError(error: string | null): string {
  const raw = (error ?? '').trim();
  const missingModule =
    /(ModuleNotFoundError|ImportError)/.test(raw) && /(win32security|pywin32)/i.test(raw);
  if (missingModule) {
    return (
      'Windows ACL inspection needs the optional pywin32 module, which is not ' +
      `installed in the Python runtime running the engine (${raw}). Install it in ` +
      'that runtime (pip install pywin32) to enable ACL capture. The engine ' +
      'treats ACL preservation as "where supported", so recovery is not blocked - ' +
      'but this check did NOT run.'
    );
  }
  if (raw.length > 0) {
    return (
      `The engine could not read the file ACL: ${raw}. ACL preservation is ` +
      '"where supported", so recovery is not blocked - but this check did NOT run.'
    );
  }
  return (
    'The engine recorded no ACL for this file, so no ACL comparison ran. ' +
    'ACL preservation is "where supported" and does not block recovery.'
  );
}

// --------------------------------------------------------------- per file

function currentState(planned: PlannedRecovery): FileCurrentState {
  if (!planned.currentExists) {
    return planned.baselineHash !== null ? 'deleted' : 'missing';
  }
  if (planned.currentHash === null || planned.baselineHash === null) {
    return 'unknown';
  }
  return planned.currentHash === planned.baselineHash ? 'unchanged' : 'modified';
}

function baselineState(planned: PlannedRecovery): FileBaselineState {
  const { kind, code } = planned.proposed;
  if (kind === 'text' || kind === 'binary') {
    return 'available';
  }
  if (planned.baselineHash === null) {
    return 'unavailable';
  }
  if (code === 'hash_mismatch' || code === 'plan_mismatch' || code === 'truncated') {
    return 'invalid';
  }
  // no_contents / no_hash / unreadable / null code: nothing was captured.
  return 'unavailable';
}

function eligibilityOf(
  planned: PlannedRecovery,
  baseline: FileBaselineState,
): FileEligibility {
  if (baseline === 'invalid') {
    // Evidence exists but failed validation: a human decision is required
    // (recapture), the engine verdicts cannot make it valid.
    return 'needs_review';
  }
  if (baseline === 'unavailable') {
    return 'needs_review';
  }
  if (!isApplicable(planned)) {
    return 'blocked';
  }
  return 'available';
}

function blockedReason(planned: PlannedRecovery): string {
  if (planned.conflict !== 'no_conflict' && planned.conflict !== 'unknown') {
    return `The engine reported a conflict (${planned.conflict}) between the stored baseline and the observed state.`;
  }
  if (planned.drift !== 'no_drift' && planned.drift !== 'unknown') {
    return `The engine detected drift (${planned.drift}): the file no longer matches what the evidence observed.`;
  }
  if (planned.conflict === 'unknown' || planned.drift === 'unknown') {
    return 'The engine returned no conflict/drift verdict for this file, so recovery cannot be declared available.';
  }
  return 'The engine simulated this recovery and reported it would not succeed.';
}

function reviewReason(planned: PlannedRecovery, baseline: FileBaselineState): string {
  if (baseline === 'invalid' && planned.proposed.limitation) {
    return display(planned.proposed.limitation);
  }
  if (baseline === 'invalid') {
    return 'The stored baseline evidence failed validation. Recapture the baseline before recovering.';
  }
  return 'No usable baseline evidence was captured for this file, so there is nothing exact to restore.';
}

function comparisonsOf(planned: PlannedRecovery): Array<{ label: string; detail: string }> {
  const diff = planned.report['diff'];
  const record = (diff !== null && typeof diff === 'object' ? diff : {}) as Record<
    string,
    unknown
  >;
  const out: Array<{ label: string; detail: string }> = [];
  const countChanges = (value: unknown): number | null => {
    if (value === null || typeof value !== 'object') {
      return null;
    }
    return Object.keys(value as Record<string, unknown>).length;
  };
  const permissions = countChanges(record['permissions']);
  const ownership = countChanges(record['ownership']);
  const metadata = countChanges(record['metadata']);
  out.push({
    label: 'Permissions',
    detail:
      permissions === null
        ? 'Not checked - the plan carried no permission comparison.'
        : permissions === 0
          ? 'Compared - no differences reported.'
          : `Compared - ${permissions} difference(s) reported.`,
  });
  out.push({
    label: 'Ownership',
    detail:
      ownership === null
        ? 'Not checked - the plan carried no ownership comparison.'
        : ownership === 0
          ? 'Compared - no differences reported.'
          : `Compared - ${ownership} difference(s) reported.`,
  });
  out.push({
    label: 'Schema / type',
    detail:
      metadata === null
        ? 'Not checked - the plan carried no metadata comparison.'
        : metadata === 0
          ? 'Compared - no differences reported.'
          : `Compared - ${metadata} difference(s) reported.`,
  });
  return out;
}

function technicalOf(planned: PlannedRecovery): ReportFileTechnical {
  const report = planned.report;
  const warnings: string[] = [];
  const rawWarnings = report['warnings'];
  if (Array.isArray(rawWarnings)) {
    for (const item of rawWarnings) {
      if (typeof item === 'string' && item.trim().length > 0) {
        warnings.push(item.trim());
      }
    }
  }
  const reversibility =
    typeof report['reversibility'] === 'string' ? report['reversibility'] : null;
  const matches =
    typeof report['matches_baseline'] === 'boolean' ? report['matches_baseline'] : null;
  const acl = planned.evidence;
  const aclDetail =
    acl.aclAvailable === true
      ? 'Captured and compared by the engine.'
      : acl.aclAvailable === false
        ? explainAclError(acl.aclError)
        : 'Not checked - the snapshot carries no ACL record for this file.';
  return {
    baselineHash: planned.baselineHash,
    currentHash: planned.currentHash,
    baselineSize: planned.evidence.snapshotSize,
    capturedAt: planned.evidence.capturedAt,
    observedAt: planned.at,
    operation: planned.operation,
    reversibility,
    matchesBaseline: matches,
    aclDetail,
    comparisons: comparisonsOf(planned),
    warnings,
    evidenceRef: basename(planned.evidenceFile),
  };
}

function buildRow(planned: PlannedRecovery, nowMs: number): ReportFileRow {
  const current = currentState(planned);
  const baseline = baselineState(planned);
  const eligibility = eligibilityOf(planned, baseline);
  const observedAt = Date.parse(planned.at);
  const fresh = isValidIso(planned.at) && nowMs - observedAt <= PREVIEW_TTL_MS;

  let reason: string | null = null;
  if (eligibility === 'blocked') {
    reason = blockedReason(planned);
  } else if (eligibility === 'needs_review') {
    reason = reviewReason(planned, baseline);
  }

  let previewNote: string | null = null;
  if (eligibility !== 'available') {
    previewNote = 'Recovery is not available for this file, so there is nothing to preview.';
  } else if (!planned.diffable) {
    previewNote = display(planned.proposed.limitation ?? 'the exact proposed contents are unavailable.');
  } else if (!fresh) {
    previewNote =
      'This evidence is outside the freshness window. Refresh the report to re-observe the file.';
  }

  return {
    resource: planned.resource,
    name: basename(planned.resource),
    dir: dirnameOf(planned.resource),
    current,
    currentLabel: LABELS[current],
    baseline,
    baselineLabel: BASELINE_LABELS[baseline],
    eligibility,
    eligibilityLabel: ELIGIBILITY_LABELS[eligibility],
    reason,
    previewable: previewNote === null,
    previewNote,
    fresh,
    technical: technicalOf(planned),
  };
}

// ----------------------------------------------------------- safety checks

function statusOf(result: CheckResult, name: string, detail: string): SafetyCheck {
  return { id: name.toLowerCase().replace(/[^a-z]+/g, '_'), name, result, resultLabel: CHECK_LABELS[result], detail };
}

function confinementCheck(plans: PlannedRecovery[]): SafetyCheck {
  if (plans.length === 0) {
    return statusOf(
      'not_checked',
      'Workspace confinement',
      'No recovery plan was produced, so no path was validated.',
    );
  }
  return statusOf(
    'passed',
    'Workspace confinement',
    `All ${plans.length} target path(s) were validated inside the authorized workspace before planning (the engine refuses anything else).`,
  );
}

function baselineCheck(rows: ReportFileRow[]): SafetyCheck {
  if (rows.length === 0) {
    return statusOf(
      'not_checked',
      'Baseline evidence',
      'No files were reviewed, so no baseline evidence was validated.',
    );
  }
  const invalid = rows.filter((row) => row.baseline === 'invalid').length;
  const unusable = rows.filter((row) => row.baseline === 'unavailable').length;
  const valid = rows.filter((row) => row.baseline === 'available').length;
  const total = rows.length;
  if (invalid > 0) {
    return statusOf(
      'failed',
      'Baseline evidence',
      `${invalid} of ${total} file(s) failed validation (stored bytes did not match their recorded SHA-256 or the capture was truncated); ${valid} passed.`,
    );
  }
  if (unusable > 0) {
    return statusOf(
      'attention',
      'Baseline evidence',
      `${unusable} of ${total} file(s) have no usable baseline contents; ${valid} matched their recorded SHA-256.`,
    );
  }
  return statusOf(
    'passed',
    'Baseline evidence',
    `Stored baseline contents matched their recorded SHA-256 for all ${valid} file(s).`,
  );
}

function verdictCheck(
  plans: PlannedRecovery[],
  okValue: string,
  missingValue: string,
  field: 'conflict' | 'drift',
  name: string,
): SafetyCheck {
  if (plans.length === 0) {
    return statusOf('not_checked', name, 'No plan was produced, so this check did not run.');
  }
  const failedList = plans.filter((plan) => plan[field] !== okValue && plan[field] !== missingValue);
  const unknownList = plans.filter((plan) => plan[field] === missingValue);
  const okCount = plans.length - failedList.length - unknownList.length;
  if (failedList.length > 0) {
    const samples = failedList
      .slice(0, 3)
      .map((plan) => `${plan.resource} (${plan[field]})`)
      .join(', ');
    return statusOf(
      'failed',
      name,
      `${failedList.length} of ${plans.length} file(s) reported ${field}: ${samples}${failedList.length > 3 ? ', …' : ''}.`,
    );
  }
  if (unknownList.length > 0) {
    return statusOf(
      'not_checked',
      name,
      `The engine returned no ${field} verdict for ${unknownList.length} of ${plans.length} file(s) (${okCount} checked clear). A missing verdict is not a pass.`,
    );
  }
  return statusOf(
    'passed',
    name,
    `The engine checked ${field} for all ${plans.length} file(s): ${okValue}.`,
  );
}

function simulationCheck(plans: PlannedRecovery[]): SafetyCheck {
  if (plans.length === 0) {
    return statusOf(
      'not_checked',
      'Recovery simulation',
      'No plan was produced, so the engine did not simulate a recovery.',
    );
  }
  const withVerdict = plans.filter(
    (plan) => typeof plan.report['would_succeed'] === 'boolean',
  );
  if (withVerdict.length === 0) {
    return statusOf(
      'not_checked',
      'Recovery simulation',
      'The engine returned no simulation verdict, so this check did not run.',
    );
  }
  const failed = withVerdict.filter((plan) => plan.report['would_succeed'] !== true);
  if (failed.length > 0) {
    const samples = failed
      .slice(0, 3)
      .map((plan) => plan.resource)
      .join(', ');
    return statusOf(
      'failed',
      'Recovery simulation',
      `The engine reported ${failed.length} of ${withVerdict.length} simulated recover${failed.length === 1 ? 'y' : 'ies'} would not succeed: ${samples}${failed.length > 3 ? ', …' : ''}.`,
    );
  }
  return statusOf(
    'passed',
    'Recovery simulation',
    `The engine simulated ${withVerdict.length} planned recover${withVerdict.length === 1 ? 'y' : 'ies'} successfully.`,
  );
}

function aclCheck(plans: PlannedRecovery[]): SafetyCheck {
  if (plans.length === 0) {
    return statusOf(
      'not_checked',
      'File ACL comparison',
      'No plan was produced, so no ACL comparison ran.',
    );
  }
  const errored = plans.filter(
    (plan) => plan.evidence.aclAvailable === false && plan.evidence.aclError !== null,
  );
  if (errored.length > 0) {
    const captured = plans.filter((plan) => plan.evidence.aclAvailable === true).length;
    return statusOf(
      'not_checked',
      'File ACL comparison',
      `${explainAclError(errored[0]?.evidence.aclError ?? null)} (ACLs captured for ${captured} of ${plans.length} file(s).)`,
    );
  }
  const captured = plans.filter((plan) => plan.evidence.aclAvailable === true).length;
  if (captured === 0) {
    return statusOf(
      'not_checked',
      'File ACL comparison',
      `This platform or filesystem recorded no ACL for any of the ${plans.length} reviewed file(s), so no ACL comparison ran.`,
    );
  }
  const note =
    captured < plans.length
      ? ` (Captured for ${captured} of ${plans.length}; the rest expose no ACL record.)`
      : '';
  return statusOf(
    'passed',
    'File ACL comparison',
    `The engine captured and compared Windows ACLs for every file that exposes one.${note}`,
  );
}

function buildChecks(plans: PlannedRecovery[], rows: ReportFileRow[]): SafetyCheck[] {
  return [
    confinementCheck(plans),
    baselineCheck(rows),
    verdictCheck(plans, 'no_conflict', 'unknown', 'conflict', 'Conflict check'),
    verdictCheck(plans, 'no_drift', 'unknown', 'drift', 'Drift check'),
    simulationCheck(plans),
    aclCheck(plans),
  ];
}

// ------------------------------------------------------------------ counts

function buildCounts(rows: ReportFileRow[]): ReportCounts {
  if (rows.length === 0) {
    // Nothing was reviewed: every count is Unknown, never zero.
    return {
      reviewed: null,
      withBaseline: null,
      differing: null,
      recoverable: null,
      attention: null,
    };
  }
  const unknownState = rows.some((row) => row.current === 'unknown');
  return {
    reviewed: rows.length,
    withBaseline: rows.filter((row) => row.baseline === 'available').length,
    differing: unknownState
      ? null
      : rows.filter((row) => row.current === 'modified' || row.current === 'deleted').length,
    recoverable: rows.filter((row) => row.eligibility === 'available').length,
    attention: rows.filter((row) => row.eligibility !== 'available').length,
  };
}

// ------------------------------------------------------------------ status

function buildStatus(
  rows: ReportFileRow[],
  counts: ReportCounts,
): { status: ReportStatus; note: string } {
  if (rows.length === 0) {
    return {
      status: 'unavailable',
      note: 'No recovery plan could be produced from the current evidence, so nothing can be reviewed or recovered. Check that a workspace is open and baselines were captured.',
    };
  }
  const attention = counts.attention ?? 0;
  const total = rows.length;
  if (attention === 0) {
    return {
      status: 'ready',
      note: `All ${total} reviewed file(s) have valid, SHA-256-verified baseline evidence and the engine reports every recovery would succeed. Nothing has been recovered yet - review the diff and approve explicitly.`,
    };
  }
  if (attention === total) {
    return {
      status: 'unavailable',
      note: `None of the ${total} reviewed file(s) can be recovered right now - a required check failed or usable baseline evidence is missing, so recovery is unavailable until that is addressed. No recovery has been executed.`,
    };
  }
  return {
    status: 'review',
    note: `${attention} of ${total} reviewed file(s) need attention before recovery. No recovery has been executed.`,
  };
}

// ------------------------------------------------------------------ builder

/**
 * Build the report model from validated plans. Pure: same inputs, same model.
 */
export function buildRecoveryReport(
  plans: PlannedRecovery[],
  options: ReportOptions,
): RecoveryReportModel {
  const { nowMs } = options;
  const rows = plans.map((plan) => buildRow(plan, nowMs));
  const counts = buildCounts(rows);
  const { status, note } = buildStatus(rows, counts);
  const checks = buildChecks(plans, rows);

  const observed = plans.map((plan) => Date.parse(plan.at)).filter((ms) => Number.isFinite(ms));
  const evidenceAt =
    observed.length === plans.length && plans.length > 0
      ? new Date(Math.max(...observed)).toISOString()
      : null;

  const allStale = plans.length > 0 && rows.every((row) => !row.fresh);
  const notice = allStale
    ? `This report uses evidence observed more than ${Math.round(PREVIEW_TTL_MS / 60000)} minutes ago. Refresh to re-observe the current files before previewing.`
    : null;

  const workspacePath = options.workspacePath ?? null;
  const workspaceName = workspacePath ? basename(workspacePath.replace(/[\\/]+$/, '')) : null;

  return {
    status,
    statusLabel: STATUS_LABELS[status],
    statusNote: note,
    workspaceName,
    generatedAt: new Date(nowMs).toISOString(),
    evidenceAt,
    notice,
    counts,
    files: rows,
    checks,
  };
}

/** Resources this model can legitimately preview (allow-list for messages). */
export function previewableResources(model: RecoveryReportModel): string[] {
  return model.files.filter((file) => file.previewable).map((file) => file.resource);
}

/** Total rows (convenience for tests and panel copy). */
export function reportIsEmpty(model: RecoveryReportModel): boolean {
  return model.files.length === 0;
}
