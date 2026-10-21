/**
 * Pure recovery-preview logic (no `vscode` import - unit-testable headlessly).
 *
 * The native side-by-side diff has to show the EXACT bytes the approved
 * recovery would write. Those bytes come from exactly one trusted place: the
 * stored baseline snapshot - the same `before_snapshot` the engine restores
 * from (`FilesystemRecoveryAdapter._execute_restore_content` writes
 * `content_b64` verbatim). The engine deliberately strips contents from the
 * plan report (`slim_snapshot`), so the diff never reconstructs a proposal
 * from a summarized diff: it decodes the stored bytes and re-verifies them
 * against the recorded sha256 before showing anything.
 *
 * Honesty rules encoded here:
 *   - bytes that do not hash to the recorded baseline hash are NEVER shown;
 *   - a truncated snapshot is NEVER shown (it would be a content-incomplete
 *     diff, i.e. a lie about what recovery restores);
 *   - binary files are reported as binary (hash/size comparison), never
 *     rendered as fake text;
 *   - a plan whose baseline hash disagrees with the previewed content is
 *     marked non-diffable so the UI cannot show a diff for a different
 *     operation than the validated plan.
 */

import * as crypto from 'crypto';

export type ProposedKind = 'text' | 'binary' | 'unavailable';

/**
 * Machine-readable reason a proposal is unavailable. The report model maps
 * these onto "Invalid" vs "Unavailable" baseline states, so the UI never has
 * to pattern-match prose (and never misreports one as the other).
 */
export type ProposedCode =
  | 'hash_mismatch' // stored bytes do not match their recorded hash
  | 'plan_mismatch' // stored bytes belong to a different baseline
  | 'truncated' // capture was cut off at the engine limit
  | 'no_contents' // snapshot carries no contents at all
  | 'no_hash' // snapshot carries no content hash
  | 'unreadable'; // snapshot missing or not an object

export interface ProposedContent {
  kind: ProposedKind;
  /** Exact proposed text - only for `kind === 'text'`. */
  text: string | null;
  /** Exact proposed bytes when the snapshot carried them. */
  bytes: Buffer | null;
  /** sha256 of {@link ProposedContent.bytes} (verified), when known. */
  hash: string | null;
  /** Honest reason the native diff cannot be shown, when it cannot. */
  limitation: string | null;
  /** Why it is unavailable (never set for text/binary proposals). */
  code: ProposedCode | null;
}

/**
 * Baseline evidence as the *stored* snapshot records it - used by the report
 * to state which comparisons actually ran (e.g. Windows ACL capture) without
 * re-reading or re-deriving anything from the engine.
 */
export interface BaselineEvidence {
  /** True when ACLs were captured; false when the capture reported an
   *  error/absence; null when the snapshot carries no ACL record at all. */
  aclAvailable: boolean | null;
  /** Raw engine ACL error (technical details only - never a headline). */
  aclError: string | null;
  snapshotSize: number | null;
  snapshotHash: string | null;
  capturedAt: string | null;
}

export const NO_EVIDENCE: BaselineEvidence = {
  aclAvailable: null,
  aclError: null,
  snapshotSize: null,
  snapshotHash: null,
  capturedAt: null,
};

const UNAVAILABLE = (code: ProposedCode, limitation: string): ProposedContent => ({
  kind: 'unavailable',
  text: null,
  bytes: null,
  hash: null,
  limitation,
  code,
});

export function sha256Hex(bytes: Buffer | Uint8Array): string {
  return crypto.createHash('sha256').update(bytes).digest('hex');
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' ? (value as Record<string, unknown>) : null;
}

/**
 * Decode the exact proposed contents from a stored baseline snapshot.
 *
 * Preference order matches what the engine writes on restore:
 * `content_b64` (raw bytes: BOM, CRLF and final newline preserved) first,
 * then the decoded `content` text as a fallback.
 */
export function proposedFromSnapshot(raw: unknown): ProposedContent {
  const snapshot = asRecord(raw);
  if (!snapshot) {
    return UNAVAILABLE('unreadable', 'the stored baseline snapshot is missing or unreadable.');
  }
  const recordedHash = typeof snapshot['hash'] === 'string' ? snapshot['hash'] : null;
  if (!recordedHash) {
    return UNAVAILABLE('no_hash', 'the stored baseline snapshot has no content hash.');
  }
  if (snapshot['truncated'] === true) {
    return UNAVAILABLE(
      'truncated',
      'the stored before-state was truncated at the engine capture limit, so the ' +
        'exact proposed contents are not available. Recapture the baseline with a ' +
        'higher interlock.maxBaselineBytes to preview it.',
    );
  }

  let bytes: Buffer | null = null;
  const encoded = snapshot['content_b64'];
  if (typeof encoded === 'string' && encoded.length > 0) {
    try {
      const decoded = Buffer.from(encoded, 'base64');
      // Reject obviously corrupt encodings instead of showing wrong bytes.
      if (decoded.length > 0 || encoded === '') {
        bytes = decoded;
      }
    } catch {
      bytes = null;
    }
  }
  if (bytes === null) {
    const text = snapshot['content'];
    if (typeof text === 'string') {
      bytes = Buffer.from(text, 'utf8');
    }
  }
  if (bytes === null) {
    return UNAVAILABLE(
      'no_contents',
      'the stored baseline carries no file contents, so there is nothing exact to show.',
    );
  }

  const actualHash = sha256Hex(bytes);
  if (actualHash !== recordedHash) {
    return UNAVAILABLE(
      'hash_mismatch',
      'the stored contents do not match the recorded baseline hash ' +
        `(expected ${recordedHash.slice(0, 12)}…, got ${actualHash.slice(0, 12)}…). ` +
        'Nothing is shown: recapture the baseline before previewing.',
    );
  }

  if (snapshot['binary'] === true) {
    return {
      kind: 'binary',
      text: null,
      bytes,
      hash: actualHash,
      limitation:
        'this is a binary file, so a text diff would be misleading. Compare the ' +
        'hashes and sizes instead - recovery writes these exact bytes.',
      code: null,
    };
  }

  const decoded = bytes.toString('utf8');
  // A UTF-8 BOM is real content; VS Code strips it when it opens a file with
  // one, so strip it here too rather than showing a stray U+FEFF glyph.
  const text = decoded.charCodeAt(0) === 0xfeff ? decoded.slice(1) : decoded;
  return { kind: 'text', text, bytes, hash: actualHash, limitation: null, code: null };
}

/**
 * Baseline evidence recorded by the engine at capture time (ACL availability,
 * size, hashes). Read straight from the stored snapshot - the report states
 * what *actually* ran rather than assuming a comparison succeeded.
 */
export function evidenceFromSnapshot(raw: unknown): BaselineEvidence {
  const snapshot = asRecord(raw);
  if (!snapshot) {
    return { ...NO_EVIDENCE };
  }
  const acl = asRecord(snapshot['acl']);
  const numberOrNull = (value: unknown): number | null =>
    typeof value === 'number' && Number.isFinite(value) ? value : null;
  return {
    aclAvailable:
      acl === null ? null : acl['available'] === true, // absent record -> null
    aclError: acl === null ? null : typeof acl['error'] === 'string' ? acl['error'] : null,
    snapshotSize: numberOrNull(snapshot['size']),
    snapshotHash: typeof snapshot['hash'] === 'string' ? snapshot['hash'] : null,
    capturedAt: typeof snapshot['captured_at'] === 'string' ? snapshot['captured_at'] : null,
  };
}

export interface PlanSummaryLike {
  wouldSucceed: boolean;
  conflict: string;
  drift: string;
  operation: string | null;
  baselineHash: string | null;
  currentHash: string | null;
  currentExists: boolean;
  baselineCapturedAt: string | null;
}

export interface PlannedRecovery {
  workspace: string;
  /** Workspace-relative path (forward slashes), exactly as validated. */
  resource: string;
  /** Path on disk for this resource, built only from workspace + resource. */
  absolutePath: string;
  operation: string | null;
  wouldSucceed: boolean;
  conflict: string;
  drift: string;
  baselineHash: string | null;
  currentHash: string | null;
  currentExists: boolean;
  baselineCapturedAt: string | null;
  /** When the plan was observed (ISO-8601). */
  at: string;
  proposed: ProposedContent;
  /** True when the native diff editor can honestly show this proposal. */
  diffable: boolean;
  /** What the stored baseline recorded about itself (ACL availability, size). */
  evidence: BaselineEvidence;
  /** Path of the sidecar holding this plan's preview-time evidence. */
  evidenceFile: string;
  /** The raw engine plan - source of the read-only plan report. */
  report: Record<string, unknown>;
}

export interface PlanInput {
  workspace: string;
  resource: string;
  absolutePath: string;
  evidenceFile: string;
  summary: PlanSummaryLike;
  baselineSnapshot: unknown;
  report: Record<string, unknown>;
  at?: string;
}

/**
 * Build one planned recovery from a validated engine plan plus the stored
 * baseline it will restore from. The diff is refused whenever the plan and
 * the stored content disagree, so the two can never drift apart silently.
 */
export function planFromEngineResult(input: PlanInput): PlannedRecovery {
  const proposed = proposedFromSnapshot(input.baselineSnapshot);
  const evidence = evidenceFromSnapshot(input.baselineSnapshot);
  const planBaselineHash = input.summary.baselineHash;
  const storedHash = proposed.hash;
  const belongsElsewhere =
    storedHash !== null && planBaselineHash !== null && storedHash !== planBaselineHash;

  // The stored bytes are verified against their own snapshot, but when they
  // are not the baseline this plan restores from they are DISCARDED here, not
  // merely flagged: nothing may reach a diff editor for an operation the
  // engine did not validate.
  const finalProposed: ProposedContent = belongsElsewhere
    ? {
        kind: 'unavailable',
        text: null,
        bytes: null,
        hash: storedHash,
        code: 'plan_mismatch',
        limitation:
          'the reviewed contents do not belong to the baseline this plan restores from ' +
          `(plan ${planBaselineHash.slice(0, 12)}… vs contents ${storedHash.slice(0, 12)}…). ` +
          'Preview the recovery again.',
      }
    : proposed;

  return {
    workspace: input.workspace,
    resource: input.resource,
    absolutePath: input.absolutePath,
    operation: input.summary.operation,
    wouldSucceed: input.summary.wouldSucceed,
    conflict: input.summary.conflict,
    drift: input.summary.drift,
    baselineHash: planBaselineHash,
    currentHash: input.summary.currentHash,
    currentExists: input.summary.currentExists,
    baselineCapturedAt: input.summary.baselineCapturedAt,
    at: input.at ?? new Date().toISOString(),
    proposed: finalProposed,
    diffable: !belongsElsewhere && finalProposed.kind === 'text' && finalProposed.text !== null,
    evidence,
    evidenceFile: input.evidenceFile,
    report: input.report,
  };
}

export interface Staleness {
  stale: boolean;
  reason: string | null;
}

/**
 * Compare the workspace file NOW against what the preview observed. Any
 * difference (content changed, file created, file deleted) invalidates the
 * preview: recovery must never run against an unreviewed state.
 */
export function staleAgainstCurrent(
  planned: PlannedRecovery,
  currentBytes: Buffer | null,
): Staleness {
  if (currentBytes === null) {
    return planned.currentExists
      ? { stale: true, reason: 'the file no longer exists on disk' }
      : { stale: false, reason: null };
  }
  if (!planned.currentExists) {
    return { stale: true, reason: 'the file appeared on disk after the preview' };
  }
  const actual = sha256Hex(currentBytes);
  if (planned.currentHash === null) {
    return { stale: true, reason: 'the preview could not record the current file hash' };
  }
  if (actual !== planned.currentHash) {
    return {
      stale: true,
      reason: `the file changed after the preview (${planned.currentHash.slice(0, 12)}… → ${actual.slice(0, 12)}…)`,
    };
  }
  return { stale: false, reason: null };
}

/** True when the engine's own verdicts allow this plan to be applied. */
export function isApplicable(planned: PlannedRecovery): boolean {
  return planned.wouldSucceed && planned.conflict === 'no_conflict' && planned.drift === 'no_drift';
}

/** Diff-editor title: both sides are named, so the tab is self-explanatory. */
export function diffTitle(resource: string): string {
  return `Current: ${resource}  ⇄  Proposed Recovery: ${resource}`;
}

/** One honest line describing what one plan will do. */
export function describePlan(planned: PlannedRecovery): string {
  const operation = planned.operation ?? 'unknown operation';
  const state = planned.currentExists ? 'file present' : 'file missing';
  return `${planned.resource} — ${operation}, ${state}, ` +
    `baseline ${shortHash(planned.baselineHash)}, current ${shortHash(planned.currentHash)}`;
}

/** Multi-file summary for the approval dialog (never omits a planned file). */
export function summarizePlans(plans: PlannedRecovery[]): string {
  const lines = plans.map((planned) => `• ${describePlan(planned)}`);
  return (
    `Recovery will overwrite ${plans.length === 1 ? 'the file' : `${plans.length} files`} with ` +
    'the captured baseline (exact bytes, re-checked immediately before writing):\n\n' +
    lines.join('\n') +
    '\n\nThe engine re-checks conflicts and containment before writing, verifies ' +
    'byte-exactly afterwards, and the extension re-checks the hash independently.'
  );
}

function shortHash(hash: string | null): string {
  return hash ? `${hash.slice(0, 12)}…` : 'unknown';
}
