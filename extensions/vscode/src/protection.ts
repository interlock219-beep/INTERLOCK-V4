/**
 * Protection status, primary-action selection, and automatic-baseline policy.
 *
 * This module is deliberately free of any `vscode` import so every decision
 * the sidebar makes is unit-testable headlessly. It answers three questions
 * from real model state (never from "the engine happens to start"):
 *
 *   1. Is this workspace protected?  ({@link evaluateProtection} for the
 *      evidence ladder, {@link protectionOf} for the render-time state the
 *      card shows, including the time-bounded "Recovery ready")
 *   2. Which actions are available right now, and why not when they are not?
 *      ({@link recoveryRowStates} + {@link duoStates})
 *   3. Which files may automatic baseline protection capture?
 *      ({@link planProtection} + {@link isSensitiveResource})
 *
 * Safety rules encoded here:
 *   - "Protected" is only ever claimed when the engine authorized the folder
 *     AND at least one stored baseline exists - engine availability alone is
 *     never enough;
 *   - an existing usable baseline is REUSED, never auto-overwritten: for a
 *     changed file the old baseline is precisely what enables undo, so
 *     recapturing would silently destroy usable recovery evidence. Deliberate
 *     refresh stays available through the explicit single-file
 *     "Interlock: Capture Baseline" command;
 *   - secret/credential files are excluded by default (mirroring the engine's
 *     own sensitive-marker policy in `app/domain/services/tool_security.py`)
 *     and users may only ADD exclusions, never remove the built-ins;
 *   - every skipped file is counted and disclosed, never dropped silently.
 */

import type { PendingPreview, SidebarModel } from './sidebar';
import type { StoredStatus, StoredVerification } from './state';

// ------------------------------------------------------------- protection

export type ProtectionStatus =
  | 'protected'
  | 'partial'
  | 'needs-protection'
  | 'analyzing'
  | 'recovery-ready'
  | 'action-required'
  | 'unknown';

export interface ProtectionState {
  status: ProtectionStatus;
  /** One short plain-language headline. */
  headline: string;
  /** One explanatory sentence. */
  detail: string;
  /** Compact scope line ("2 files protected", "2 of 5 files protected"). */
  countsText: string;
  /** Plain-language blocker, only for `action-required`; else null. */
  blocker: string | null;
  coveredFiles: number;
  /** Eligible files from the last scan/plan, null when unknown. */
  eligibleFiles: number | null;
  skippedFiles: number;
  checkedAt: string | null;
}

export interface ProtectionInput {
  workspacePath: string | null;
  workspaceAuthorized: boolean | null;
  baselineCount: number;
  engineStatus: StoredStatus | null;
  verification: StoredVerification | null;
  /** An analyze/protect run is in flight right now. */
  analyzing?: boolean;
  analyzingDetail?: string | null;
  eligibleFiles?: number | null;
  skippedFiles?: number;
  checkedAt?: string | null;
}

/** Tone per protection status (closed table; mirrored by the updater script). */
export const PROTECTION_TONE: Record<ProtectionStatus, string> = {
  protected: 'ok',
  partial: 'warn',
  'needs-protection': 'warn',
  analyzing: 'idle',
  // Recovery-ready is the electric-yellow "you can act now" state, never a
  // success green (nothing has been restored yet).
  'recovery-ready': 'accent',
  'action-required': 'bad',
  unknown: 'idle',
};

/** Icon per protection status (closed table; mirrored by the updater script). */
export const PROTECTION_ICON: Record<ProtectionStatus, string> = {
  protected: 'shieldCheck',
  partial: 'shieldAlert',
  'needs-protection': 'shieldAlert',
  analyzing: 'pulse',
  'recovery-ready': 'rotate',
  'action-required': 'shieldAlert',
  unknown: 'shield',
};

const DETAIL_CAP = 220;

function cap(text: string): string {
  return text.length > DETAIL_CAP ? `${text.slice(0, DETAIL_CAP - 1)}…` : text;
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'}`;
}

/**
 * Derive the protection status from what is actually known.
 *
 * Ladder (first match wins):
 *   no folder              -> unknown   "No folder open"
 *   analyzing              -> analyzing (in-flight run)
 *   confinement refused    -> action-required "Protection unavailable"
 *   engine did not respond -> action-required "Protection unavailable"
 *   verification failed    -> action-required "Action required"
 *   no baselines           -> needs-protection
 *   baselines + authorized -> protected, or "partial" when some eligible
 *                             files still have no evidence
 *   baselines, unchecked   -> unknown   (evidence exists, not authorized yet)
 *
 * The time-bounded "recovery-ready" state is NOT part of this ladder: it is
 * applied on top by {@link protectionOf} at render time, because preview
 * freshness must be re-evaluated against the clock on every model update
 * instead of being stored as a stale verdict.
 */
export function evaluateProtection(input: ProtectionInput): ProtectionState {
  const covered = Math.max(0, input.baselineCount);
  const eligible = input.eligibleFiles ?? null;
  const skipped = Math.max(0, input.skippedFiles ?? 0);
  const checkedAt = input.checkedAt ?? null;

  const counts = (): string => {
    const parts: string[] = [];
    if (covered === 0) {
      parts.push('no recovery evidence yet');
    } else if (eligible !== null && eligible > covered) {
      parts.push(`${covered} of ${eligible} files protected`);
    } else {
      parts.push(plural(covered, 'file') + ' protected');
    }
    if (skipped > 0) {
      parts.push(`${plural(skipped, 'file')} skipped by policy`);
    }
    return parts.join(' · ');
  };

  if (!input.workspacePath) {
    return {
      status: 'unknown',
      headline: 'No folder open',
      detail: 'Open a project folder to see and manage its recovery protection.',
      countsText: '',
      blocker: null,
      coveredFiles: covered,
      eligibleFiles: eligible,
      skippedFiles: skipped,
      checkedAt,
    };
  }

  if (input.analyzing) {
    return {
      status: 'analyzing',
      headline: 'Analyzing',
      detail: input.analyzingDetail ?? 'Checking this workspace and its recovery evidence…',
      countsText: counts(),
      blocker: null,
      coveredFiles: covered,
      eligibleFiles: eligible,
      skippedFiles: skipped,
      checkedAt,
    };
  }

  if (input.workspaceAuthorized === false) {
    return {
      status: 'action-required',
      headline: 'Protection unavailable',
      detail: 'This folder is not authorized for recovery.',
      countsText: counts(),
      blocker:
        'The engine refused this workspace (confinement check failed). Interlock cannot ' +
        'protect or recover files here. Run Analyze Workspace for details.',
      coveredFiles: covered,
      eligibleFiles: eligible,
      skippedFiles: skipped,
      checkedAt,
    };
  }

  const engineDown =
    input.engineStatus !== null && input.engineStatus.engineAvailable === false;
  if (engineDown) {
    return {
      status: 'action-required',
      headline: 'Protection unavailable',
      detail: 'The recovery engine did not respond, so nothing can be protected or recovered.',
      countsText: counts(),
      blocker:
        'Run "Check Installation" under Advanced → Engine & diagnostics, then analyze again.',
      coveredFiles: covered,
      eligibleFiles: eligible,
      skippedFiles: skipped,
      checkedAt,
    };
  }

  const verifyFailed = input.verification !== null && !input.verification.success;
  if (verifyFailed) {
    const verification = input.verification as StoredVerification;
    return {
      status: 'action-required',
      headline: 'Action required',
      detail: `The last verification for ${verification.resource} did not confirm a byte-exact restore.`,
      countsText: counts(),
      blocker: cap(`Verification reported: ${verification.reason}`),
      coveredFiles: covered,
      eligibleFiles: eligible,
      skippedFiles: skipped,
      checkedAt,
    };
  }

  if (covered === 0) {
    return {
      status: 'needs-protection',
      headline: 'Needs protection',
      detail:
        "This workspace isn't protected yet. Capture a baseline of the current files so " +
        'Interlock can restore them after an agent change.',
      countsText: counts(),
      blocker: null,
      coveredFiles: 0,
      eligibleFiles: eligible,
      skippedFiles: skipped,
      checkedAt,
    };
  }

  if (input.workspaceAuthorized === true) {
    const partial = eligible !== null && eligible > covered;
    return {
      status: partial ? 'partial' : 'protected',
      headline: partial ? 'Partial protection' : 'Protected',
      detail: partial
        ? 'Some files in this workspace still have no recovery evidence.'
        : 'Valid recovery evidence is available for the files in this workspace.',
      countsText: counts(),
      blocker: null,
      coveredFiles: covered,
      eligibleFiles: eligible,
      skippedFiles: skipped,
      checkedAt,
    };
  }

  return {
    status: 'unknown',
    headline: 'Not verified yet',
    detail: `Recovery evidence exists for ${plural(covered, 'file')}, but this workspace has not been authorized by the engine yet. Run Analyze Workspace.`,
    countsText: counts(),
    blocker: null,
    coveredFiles: covered,
    eligibleFiles: eligible,
    skippedFiles: skipped,
    checkedAt,
  };
}

// ---------------------------------------------------------- pending preview

/** How long a stored recovery preview drives the render-time "Recovery ready". */
export const PREVIEW_TTL_MS = 30 * 60 * 1000;

/**
 * The protection state this model should display. The host normally pushes a
 * computed state; when it has not yet (first paint, fixtures, previews), the
 * same pure evaluator derives an honest fallback from the rest of the model.
 */
export function effectiveProtection(model: SidebarModel): ProtectionState {
  if (model.protection) {
    return model.protection;
  }
  return evaluateProtection({
    workspacePath: model.workspacePath,
    workspaceAuthorized: model.workspaceAuthorized,
    baselineCount: model.baselineCount,
    engineStatus: model.status,
    verification: model.verification,
  });
}

/**
 * True when a preview for THIS workspace is fresh, still valid (`wouldSucceed`
 * - a conflicted preview is never presented as ready) and unparsable
 * timestamps count as absent.
 */
export function previewIsFresh(
  workspacePath: string | null,
  preview: PendingPreview | null | undefined,
  nowMs: number,
): boolean {
  if (!preview || !workspacePath) {
    return false;
  }
  if (preview.workspace !== workspacePath || !preview.wouldSucceed) {
    return false;
  }
  const at = Date.parse(preview.at);
  if (!Number.isFinite(at)) {
    return false;
  }
  return nowMs - at < PREVIEW_TTL_MS;
}

/** True when a preview exists for this workspace and is still fresh. */
export function isPreviewPending(model: SidebarModel, nowMs: number): boolean {
  return previewIsFresh(model.workspacePath, model.pendingPreview, nowMs);
}

/**
 * Upgrade a plain evidence state to "Recovery ready" while a preview the
 * engine said would succeed is fresh for this workspace.
 *
 * Deliberately render-time (never stored): preview freshness is judged
 * against the clock on every model update, so an expired or foreign preview
 * falls straight back to the honest evidence state. Only a workspace that is
 * already protected or partially protected can ever reach this state - a
 * missing or refused baseline is never upgraded, and the coverage counts of
 * the base state are preserved so partial scope is still disclosed.
 */
export function recoveryReadyState(
  base: ProtectionState,
  workspacePath: string | null,
  preview: PendingPreview | null | undefined,
  nowMs: number,
): ProtectionState {
  if (base.status !== 'protected' && base.status !== 'partial') {
    return base;
  }
  if (!preview || !previewIsFresh(workspacePath, preview, nowMs)) {
    return base;
  }
  const resources = preview.resources?.length ? preview.resources : [preview.resource];
  return {
    ...base,
    status: 'recovery-ready',
    headline: 'Recovery ready',
    detail:
      resources.length > 1
        ? ROW_COPY.readyMany.replace('{count}', String(resources.length))
        : ROW_COPY.readySingle.replace('{resource}', preview.resource),
    blocker: null,
  };
}

/**
 * The protection state this model should display. The host normally pushes a
 * computed evidence state; on top of it this applies the time-bounded
 * "Recovery ready" upgrade. When the host has not pushed anything yet (first
 * paint, fixtures, previews), the same pure evaluator derives an honest
 * fallback from the rest of the model. Both the renderer and the shipped
 * updater script call this, so the header pill, the card and the buttons can
 * never disagree about the same model.
 */
export function protectionOf(model: SidebarModel, nowMs: number = Date.now()): ProtectionState {
  const base = effectiveProtection(model);
  return recoveryReadyState(base, model.workspacePath, model.pendingPreview, nowMs);
}

// ---------------------------------------------- recovery actions (UI states)

/** Row keys for the two secondary full-width rows (Preview, Verify). */
export const ROW_KEYS = ['preview', 'verify'] as const;
export type RowKey = (typeof ROW_KEYS)[number];

/** Keys for the two prominent side-by-side actions (Analyze, Recover). */
export const DUO_KEYS = ['analyze', 'recover'] as const;
export type DuoKey = (typeof DUO_KEYS)[number];

export interface RowState {
  /** Command id this control runs (one of the host's allow-listed commands). */
  actionId: string;
  /** True when the action cannot work right now (no folder / no evidence). */
  disabled: boolean;
  /** Plain-language description - or the reason the control is disabled. */
  description: string;
}

/**
 * Copy shared by the renderer AND the shipped updater (injected as JSON), so
 * the two can never drift apart.
 */
export const ROW_COPY = {
  _whyFolder: 'Open a project folder first.',
  _whyEvidence: 'No recovery evidence yet - protect the workspace first.',
  analyze: { enabled: 'Find changes and recovery needs.' },
  recover: { enabled: 'Open the Inbox: choose changed files, review them, recover them.' },
  preview: { enabled: 'Review the side-by-side diff before applying.' },
  verify: { enabled: 'Independently check the result after recovery.' },
  /** "Recovery ready" detail: {resource} / {count} are substituted. */
  readySingle:
    'A recovery preview for {resource} is ready. Review the side-by-side diff, then approve to restore it.',
  readyMany:
    'A recovery preview for {count} files is ready. Review each side-by-side diff, then approve to restore them.',
} as const;

/**
 * Copy for the single primary button. The label is static by design: the
 * sidebar always offers "Protect My Workspace" as its one large action, and
 * only the sentence beneath it adapts to what is possible right now.
 */
export const PRIMARY_COPY = {
  label: 'Protect My Workspace',
  explain: 'Create and verify a baseline.',
} as const;

/**
 * Gate for every recovery operation: recovery restores a stored BEFORE-state,
 * so it needs BOTH an open folder and existing evidence. The returned string
 * is empty when recovery is possible, else the honest reason to show.
 */
function recoveryGate(model: SidebarModel): string {
  if (!model.workspacePath) {
    return ROW_COPY._whyFolder;
  }
  if (model.baselineCount <= 0) {
    return ROW_COPY._whyEvidence;
  }
  return '';
}

/**
 * Availability per secondary row. Both rows are inspection steps that need
 * the same evidence recovery needs; the disabled reason replaces the
 * description so it is never a mystery.
 */
export function recoveryRowStates(model: SidebarModel): Record<RowKey, RowState> {
  const gate = recoveryGate(model);
  return {
    preview: {
      actionId: 'interlock.previewRecoveryPlan',
      disabled: gate.length > 0,
      description: gate || ROW_COPY.preview.enabled,
    },
    verify: {
      actionId: 'interlock.verifyRecovery',
      disabled: gate.length > 0,
      description: gate || ROW_COPY.verify.enabled,
    },
  };
}

/**
 * Availability per prominent side-by-side action.
 *   Analyze - read-only, only needs an open folder;
 *   Recover - opens the Recovery Inbox, where the changed files are
 *             discovered, selected, reviewed, approved and applied. It only
 *             needs an open folder: the Inbox itself reports honestly when
 *             there is no evidence to recover from (and points back at the
 *             primary Protect action).
 */
export function duoStates(model: SidebarModel): Record<DuoKey, RowState> {
  const noFolder = !model.workspacePath;
  return {
    analyze: {
      actionId: 'interlock.analyzeWorkspace',
      disabled: noFolder,
      description: noFolder ? ROW_COPY._whyFolder : ROW_COPY.analyze.enabled,
    },
    recover: {
      actionId: 'interlock.openRecoveryInbox',
      disabled: noFolder,
      description: noFolder ? ROW_COPY._whyFolder : ROW_COPY.recover.enabled,
    },
  };
}

// ------------------------------------------------------- exclusion policies

/**
 * Sensitive-file markers. Mirrors the engine's own marker list
 * (`app/domain/services/tool_security.py`) plus additional private-key and
 * password-database formats. Matched with the same delimiter rule: the
 * marker must not sit inside an alphanumeric run, so `keyword.txt` is NOT
 * excluded by the `key`-adjacent markers while `id_rsa` in any directory is.
 */
export const SENSITIVE_MARKERS: readonly string[] = [
  'private.pem',
  '.env',
  'secret',
  'id_rsa',
  'id_dsa',
  'id_ed25519',
  '.p12',
  '.pfx',
  '.ppk',
  '.keystore',
  '.kdbx',
];

/**
 * Plain-language disclosure of the built-in policy (static copy in the
 * Advanced section; never built from model data).
 */
export const SENSITIVE_POLICY_NOTE =
  'Secret and credential files are never captured automatically: .env, private.pem, ' +
  'id_rsa, id_dsa, id_ed25519, .p12, .pfx, .ppk, .keystore, .kdbx and any path ' +
  'segment containing "secret".';

/**
 * One line disclosing the user's configured exclusions. Mirrored verbatim by
 * the shipped updater script (tests keep the two in sync).
 */
export function exclusionSummary(patterns: readonly string[]): string {
  if (patterns.length === 0) {
    return 'No user exclusion patterns configured.';
  }
  const shown = patterns.slice(0, 5);
  const extra = patterns.length - shown.length;
  return (
    `${patterns.length} user exclusion pattern${patterns.length === 1 ? '' : 's'}: ` +
    `${shown.join(', ')}${extra > 0 ? ` +${extra} more` : ''}.`
  );
}

export interface ExclusionDecision {
  excluded: boolean;
  /** Policy label for disclosure ("secret file", "user exclusion"). */
  reason: string | null;
}

/** Translate a `*` glob (case-insensitive) into a full-path regex. */
export function globToRegExp(pattern: string): RegExp {
  const escaped = pattern
    .toLowerCase()
    .replace(/[.+^${}()|[\]\\]/g, '\\$&')
    .replace(/\*/g, '.*')
    .replace(/\?/g, '.');
  return new RegExp(`^${escaped}$`);
}

export function matchesExclusionPattern(relPath: string, pattern: string): boolean {
  const normalized = relPath.replace(/\\/g, '/').toLowerCase();
  const cleaned = pattern.trim().replace(/\\/g, '/').toLowerCase();
  if (!cleaned) {
    return false;
  }
  if (globToRegExp(cleaned).test(normalized)) {
    return true;
  }
  // A bare pattern (no slash) also matches any single path segment,
  // so "secrets/**" style entries and "*.pem" both behave as users expect.
  if (!cleaned.includes('/')) {
    return normalized.split('/').some((segment) => globToRegExp(cleaned).test(segment));
  }
  // "dir/**" should also match files directly inside dir/.
  if (cleaned.endsWith('/**')) {
    const prefix = cleaned.slice(0, -3);
    return normalized === prefix || normalized.startsWith(`${prefix}/`);
  }
  return false;
}

/**
 * Decide whether a workspace-relative file must be excluded from automatic
 * baseline capture. Built-in secret markers always apply; user patterns may
 * only add exclusions.
 */
export function isSensitiveResource(
  relPath: string,
  extraPatterns: readonly string[] = [],
): ExclusionDecision {
  const normalized = relPath.replace(/\\/g, '/').toLowerCase();
  const segments = normalized.split('/');
  for (const marker of SENSITIVE_MARKERS) {
    const pattern = `*${marker}*`;
    if (segments.some((segment) => globToRegExp(pattern).test(segment))) {
      return { excluded: true, reason: 'secret or credential file' };
    }
  }
  for (const pattern of extraPatterns) {
    if (matchesExclusionPattern(normalized, pattern)) {
      return { excluded: true, reason: 'excluded by configuration' };
    }
  }
  return { excluded: false, reason: null };
}

// -------------------------------------------------------------- capture plan

export interface ScanFile {
  path: string;
  size: number;
}

export interface ExistingEvidence {
  resource: string;
  hash: string | null;
}

export interface PlannedCapture {
  path: string;
  size: number;
}

export interface SkippedFile {
  path: string;
  reason: string;
}

export interface ProtectionPlan {
  /** Files with no evidence yet that automatic protection may capture. */
  toCapture: PlannedCapture[];
  /** Files that already have usable evidence (kept, never overwritten). */
  reused: string[];
  skipped: SkippedFile[];
}

/** Upper bound for one protection run (mirrors the engine scan cap). */
export const PROTECTION_CAPTURE_CAP = 300;

/**
 * Human-readable disclosure of a capture plan, shown BEFORE anything is
 * captured: what will be captured, what is kept, and exactly why files are
 * skipped (grouped by policy reason).
 */
export function describeProtectionPlan(plan: ProtectionPlan): string {
  const parts: string[] = [`${plan.toCapture.length} file(s) will be captured`];
  if (plan.reused.length > 0) {
    parts.push(
      `${plan.reused.length} already have evidence and will be kept untouched`,
    );
  }
  if (plan.skipped.length > 0) {
    const groups = new Map<string, number>();
    for (const entry of plan.skipped) {
      const key = entry.reason.startsWith('larger than')
        ? 'over the size limit'
        : entry.reason.startsWith('capture limit')
          ? "beyond this run's cap"
          : entry.reason;
      groups.set(key, (groups.get(key) ?? 0) + 1);
    }
    const summary = [...groups]
      .map(([reason, count]) => `${count} ${reason}`)
      .join(', ');
    parts.push(`${plan.skipped.length} will be skipped (${summary})`);
  }
  return `${parts.join('; ')}.`;
}

export interface PlanOptions {
  maxBaselineBytes: number;
  /** Additional user-configured exclusion patterns (additive only). */
  exclusions: readonly string[];
  maxFiles?: number;
}

/**
 * Build the capture plan for a protection run.
 *
 * Reuse rule: a file that already has stored evidence is never recaptured
 * automatically - the existing baseline may be the only way back. Refresh is
 * a deliberate, per-file user action ("Interlock: Capture Baseline").
 */
export function planProtection(
  files: readonly ScanFile[],
  existing: readonly ExistingEvidence[],
  options: PlanOptions,
): ProtectionPlan {
  const known = new Set(existing.map((entry) => entry.resource.replace(/\\/g, '/')));
  const cap = options.maxFiles ?? PROTECTION_CAPTURE_CAP;
  const toCapture: PlannedCapture[] = [];
  const reused: string[] = [];
  const skipped: SkippedFile[] = [];

  for (const file of [...files].sort((a, b) => a.path.localeCompare(b.path))) {
    const rel = file.path.replace(/\\/g, '/');
    if (known.has(rel)) {
      reused.push(rel);
      continue;
    }
    const sensitive = isSensitiveResource(rel, options.exclusions);
    if (sensitive.excluded) {
      skipped.push({ path: rel, reason: sensitive.reason ?? 'excluded' });
      continue;
    }
    if (!Number.isFinite(file.size) || file.size > options.maxBaselineBytes) {
      skipped.push({
        path: rel,
        reason: `larger than the ${options.maxBaselineBytes}-byte baseline limit`,
      });
      continue;
    }
    if (toCapture.length >= cap) {
      skipped.push({ path: rel, reason: 'capture limit for this run reached' });
      continue;
    }
    toCapture.push({ path: rel, size: file.size });
  }

  return { toCapture, reused, skipped };
}
