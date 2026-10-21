/**
 * Recovery Report model tests (pure).
 *
 * The report is the only place a user sees "what can be recovered" in
 * numbers. These tests pin down that every count comes from validated plan
 * data (and shows "Unknown" - never 0 - when a value cannot be derived),
 * that status never says "ready" while validation failed, that a check which
 * could not run (e.g. missing pywin32/win32security) is reported as "Not
 * checked" rather than a pass, that preview eligibility follows the engine
 * verdicts plus hash-verified evidence and freshness, and that no file
 * contents or absolute paths leak into the model.
 */

import * as assert from 'assert';
import * as crypto from 'crypto';

import {
  BaselineEvidence,
  PlannedRecovery,
  ProposedCode,
  ProposedKind,
} from '../../src/recoveryPlan';
import { PREVIEW_TTL_MS } from '../../src/protection';
import {
  buildRecoveryReport,
  explainAclError,
  previewableResources,
} from '../../src/recoveryReport';

const sha = (input: string | Buffer): string =>
  crypto.createHash('sha256').update(input).digest('hex');

const NOW = '2026-10-20T12:00:00.000Z';
const NOW_MS = Date.parse(NOW);
const BASELINE_BYTES = 'baseline content\n';
const CURRENT_BYTES = 'changed content\n';
const BASELINE_HASH = sha(BASELINE_BYTES);
const CURRENT_HASH = sha(CURRENT_BYTES);

interface PlanSpec {
  resource?: string;
  currentExists?: boolean;
  currentHash?: string | null;
  baselineHash?: string | null;
  wouldSucceed?: boolean;
  conflict?: string;
  drift?: string;
  at?: string;
  kind?: ProposedKind;
  code?: ProposedCode;
  limitation?: string;
  proposedHash?: string | null;
  aclAvailable?: boolean | null;
  aclError?: string | null;
  report?: Record<string, unknown>;
}

/** A complete PlannedRecovery the way planFromEngineResult produces one. */
function makePlan(spec: PlanSpec = {}): PlannedRecovery {
  const baselineHash = spec.baselineHash === undefined ? BASELINE_HASH : spec.baselineHash;
  const kind: ProposedKind = spec.kind ?? 'text';
  return {
    workspace: 'C:/ws',
    resource: spec.resource ?? 'src/app.ts',
    absolutePath: 'C:/ws/src/app.ts',
    operation: 'restore_content',
    wouldSucceed: spec.wouldSucceed ?? true,
    conflict: spec.conflict ?? 'no_conflict',
    drift: spec.drift ?? 'no_drift',
    baselineHash,
    currentHash: spec.currentHash === undefined ? CURRENT_HASH : spec.currentHash,
    currentExists: spec.currentExists ?? true,
    baselineCapturedAt: '2026-10-20T09:00:00Z',
    at: spec.at ?? NOW,
    proposed: {
      kind,
      text: kind === 'text' ? BASELINE_BYTES : null,
      bytes: kind === 'unavailable' ? null : Buffer.from(BASELINE_BYTES, 'utf8'),
      hash: spec.proposedHash === undefined ? baselineHash : spec.proposedHash,
      limitation:
        spec.limitation ??
        (kind === 'unavailable' ? 'the stored baseline carries no file contents.' : null),
      code: kind === 'unavailable' ? (spec.code ?? 'no_contents') : null,
    },
    // diffable mirrors planFromEngineResult: content availability only;
    // engine verdicts gate previewability via eligibility, not the diff.
    diffable: kind === 'text',
    evidence: {
      aclAvailable: spec.aclAvailable === undefined ? true : spec.aclAvailable,
      aclError: spec.aclError === undefined ? null : spec.aclError,
      snapshotSize: BASELINE_BYTES.length,
      snapshotHash: baselineHash,
      capturedAt: '2026-10-20T09:00:00Z',
    } satisfies BaselineEvidence,
    evidenceFile: `C:/storage/${spec.resource ?? 'src/app.ts'}.evidence.json`,
    report:
      spec.report ??
      {
        would_succeed: spec.wouldSucceed ?? true,
        conflict_status: spec.conflict ?? 'no_conflict',
        drift_status: spec.drift ?? 'no_drift',
        reversibility: 'reversible',
        matches_baseline: false,
        warnings: [],
        diff: { permissions: {}, ownership: {}, metadata: {} },
      },
  };
}

const check = (model: ReturnType<typeof buildRecoveryReport>, id: string) => {
  const found = model.checks.find((entry) => entry.id === id);
  assert.ok(found, `missing check ${id}`);
  return found;
};

describe('recovery report model (counts, states, status)', () => {
  it('builds a ready report from valid evidence with exact counts', () => {
    const model = buildRecoveryReport(
      [
        makePlan({ resource: 'src/app.ts' }), // modified
        makePlan({ resource: 'README.md', currentHash: BASELINE_HASH }), // unchanged
        makePlan({ resource: 'gone.txt', currentExists: false }), // deleted
      ],
      { nowMs: NOW_MS, workspacePath: 'C:/ws' },
    );
    assert.strictEqual(model.status, 'ready');
    assert.strictEqual(model.statusLabel, 'Ready to review');
    assert.deepStrictEqual(model.counts, {
      reviewed: 3,
      withBaseline: 3,
      differing: 2, // modified + deleted
      recoverable: 3,
      attention: 0,
    });
    assert.strictEqual(model.workspaceName, 'ws');
    assert.strictEqual(model.generatedAt, NOW);
    assert.strictEqual(model.evidenceAt, NOW);
    assert.strictEqual(model.notice, null);
    assert.ok(model.statusNote.includes('Nothing has been recovered yet'));
    const states = model.files.map((file) => file.current);
    assert.deepStrictEqual(states, ['modified', 'unchanged', 'deleted']);
    const labels = model.files.map((file) => file.currentLabel);
    assert.deepStrictEqual(labels, ['Modified', 'Unchanged', 'Deleted']);
  });

  it('classifies missing, unknown and no-baseline files honestly', () => {
    const model = buildRecoveryReport(
      [
        makePlan({ resource: 'missing.txt', currentExists: false, baselineHash: null }),
        makePlan({ resource: 'unknown.txt', currentHash: null }),
        makePlan({ resource: 'nobase.txt', currentExists: false, baselineHash: null }),
      ],
      { nowMs: NOW_MS, workspacePath: 'C:/ws' },
    );
    assert.strictEqual(model.files[0].current, 'missing');
    assert.strictEqual(model.files[0].currentLabel, 'Missing');
    assert.strictEqual(model.files[1].current, 'unknown');
    assert.strictEqual(model.files[2].current, 'missing');
    // One state cannot be determined -> the "differing" count is Unknown, not a number.
    assert.strictEqual(model.counts.differing, null);
  });

  it('reports Unknown (null) instead of zero when nothing was reviewed', () => {
    const model = buildRecoveryReport([], { nowMs: NOW_MS, workspacePath: 'C:/ws' });
    assert.deepStrictEqual(model.counts, {
      reviewed: null,
      withBaseline: null,
      differing: null,
      recoverable: null,
      attention: null,
    });
    assert.strictEqual(model.status, 'unavailable');
    assert.strictEqual(model.statusLabel, 'Recovery unavailable');
    assert.strictEqual(model.files.length, 0);
    // Every check says Not checked - nothing ran.
    for (const entry of model.checks) {
      assert.strictEqual(entry.result, 'not_checked', `${entry.name} must not claim a pass`);
    }
  });

  it('never says "Ready to review" when baseline validation failed', () => {
    const model = buildRecoveryReport(
      [
        makePlan({
          kind: 'unavailable',
          code: 'hash_mismatch',
          limitation: 'the stored contents do not match the recorded baseline hash.',
        }),
      ],
      { nowMs: NOW_MS, workspacePath: 'C:/ws' },
    );
    assert.notStrictEqual(model.status, 'ready');
    assert.strictEqual(model.statusLabel, 'Recovery unavailable');
    const row = model.files[0];
    assert.strictEqual(row?.baseline, 'invalid');
    assert.strictEqual(row?.baselineLabel, 'Invalid');
    assert.strictEqual(row?.eligibility, 'needs_review');
    assert.strictEqual(row?.eligibilityLabel, 'Needs review');
    assert.ok(row?.reason?.includes('do not match the recorded baseline hash'));
    assert.strictEqual(model.counts.attention, 1);
    assert.strictEqual(model.counts.recoverable, 0);
  });

  it('marks engine-blocked files Blocked with the engine reason', () => {
    const model = buildRecoveryReport([makePlan({ conflict: 'content_conflict' })], {
      nowMs: NOW_MS,
      workspacePath: 'C:/ws',
    });
    const row = model.files[0];
    assert.strictEqual(row?.eligibility, 'blocked');
    assert.strictEqual(row?.eligibilityLabel, 'Blocked');
    assert.ok(row?.reason?.includes('content_conflict'));
    assert.ok(row?.reason?.includes('engine reported a conflict'));
    assert.strictEqual(model.status, 'unavailable');
    assert.strictEqual(model.statusLabel, 'Recovery unavailable');
  });

  it('keeps a mixed report at "Review required"', () => {
    const model = buildRecoveryReport(
      [makePlan(), makePlan({ resource: 'other.txt', drift: 'drift_hash' })],
      { nowMs: NOW_MS, workspacePath: 'C:/ws' },
    );
    assert.strictEqual(model.status, 'review');
    assert.strictEqual(model.statusLabel, 'Review required');
    assert.strictEqual(model.counts.recoverable, 1);
    assert.strictEqual(model.counts.attention, 1);
    assert.ok(model.statusNote.includes('1 of 2'));
  });

  it('reports unavailable baselines as Unavailable (not Invalid)', () => {
    const model = buildRecoveryReport(
      [
        makePlan({ kind: 'unavailable', code: 'no_hash', limitation: 'no content hash.' }),
        makePlan({
          resource: 'b.txt',
          currentExists: false,
          baselineHash: null,
          kind: 'unavailable',
          limitation: 'the stored baseline snapshot is missing or unreadable.',
        }),
      ],
      { nowMs: NOW_MS, workspacePath: 'C:/ws' },
    );
    assert.strictEqual(model.files[0]?.baseline, 'unavailable');
    assert.strictEqual(model.files[0]?.eligibility, 'needs_review');
    assert.strictEqual(model.files[1]?.baseline, 'unavailable');
    assert.strictEqual(model.files[1]?.current, 'missing');
  });

  it('binary files stay recoverable but are never previewable as a diff', () => {
    const model = buildRecoveryReport([makePlan({ kind: 'binary', limitation: 'binary file' })], {
      nowMs: NOW_MS,
      workspacePath: 'C:/ws',
    });
    const row = model.files[0];
    assert.strictEqual(row?.baseline, 'available');
    assert.strictEqual(row?.eligibility, 'available');
    assert.strictEqual(row?.previewable, false);
    assert.ok(row?.previewNote?.toLowerCase().includes('binary file'));
    assert.strictEqual(model.counts.recoverable, 1);
    assert.deepStrictEqual(previewableResources(model), []);
  });

  it('stale evidence disables preview and raises a notice; refresh clears it', () => {
    const staleAt = new Date(NOW_MS - PREVIEW_TTL_MS - 60_000).toISOString();
    const stale = buildRecoveryReport([makePlan({ at: staleAt })], {
      nowMs: NOW_MS,
      workspacePath: 'C:/ws',
    });
    assert.strictEqual(stale.files[0]?.fresh, false);
    assert.strictEqual(stale.files[0]?.previewable, false);
    assert.ok(stale.files[0]?.previewNote?.includes('freshness window'));
    assert.ok(stale.notice?.includes('Refresh'));
    assert.strictEqual(stale.evidenceAt, staleAt);

    const fresh = buildRecoveryReport([makePlan({ at: NOW })], {
      nowMs: NOW_MS,
      workspacePath: 'C:/ws',
    });
    assert.strictEqual(fresh.files[0]?.previewable, true);
    assert.strictEqual(fresh.notice, null);
    assert.deepStrictEqual(previewableResources(fresh), ['src/app.ts']);
  });

  it('previewableResources names exactly the rows whose buttons may act', () => {
    const model = buildRecoveryReport(
      [
        makePlan({ resource: 'ok.ts' }),
        makePlan({ resource: 'blocked.ts', conflict: 'content_conflict' }),
        makePlan({ resource: 'bin.ts', kind: 'binary' }),
      ],
      { nowMs: NOW_MS, workspacePath: 'C:/ws' },
    );
    assert.deepStrictEqual(previewableResources(model), ['ok.ts']);
  });
});

describe('recovery report safety checks', () => {
  it('passes the checks that genuinely ran on healthy evidence', () => {
    const model = buildRecoveryReport([makePlan()], {
      nowMs: NOW_MS,
      workspacePath: 'C:/ws',
    });
    assert.strictEqual(check(model, 'workspace_confinement').result, 'passed');
    assert.strictEqual(check(model, 'baseline_evidence').result, 'passed');
    assert.strictEqual(check(model, 'conflict_check').result, 'passed');
    assert.strictEqual(check(model, 'drift_check').result, 'passed');
    assert.strictEqual(check(model, 'recovery_simulation').result, 'passed');
    assert.strictEqual(check(model, 'file_acl_comparison').result, 'passed');
    for (const entry of model.checks) {
      assert.strictEqual(entry.resultLabel, 'Passed');
      assert.ok(entry.detail.length > 0, `${entry.name} needs an explanation`);
    }
  });

  it('reports a missing win32security module as Not checked - never as a pass', () => {
    const error = "ModuleNotFoundError: No module named 'win32security'";
    const model = buildRecoveryReport([makePlan({ aclAvailable: false, aclError: error })], {
      nowMs: NOW_MS,
      workspacePath: 'C:/ws',
    });
    const acl = check(model, 'file_acl_comparison');
    assert.strictEqual(acl.result, 'not_checked');
    assert.strictEqual(acl.resultLabel, 'Not checked');
    assert.ok(acl.detail.includes('pywin32'), 'names the missing dependency');
    assert.ok(acl.detail.includes('win32security'), 'preserves the underlying error');
    assert.ok(acl.detail.includes('did NOT run'), 'never implies the check succeeded');
    assert.ok(acl.detail.includes('where supported'), 'keeps the engine policy visible');
    // The per-file technical entry tells the same story.
    assert.ok(model.files[0]?.technical.aclDetail.includes('pywin32'));
    // A dependency problem must never be reported as a passing check, and the
    // engine's own policy (ACL is where-supported) is what keeps recovery open:
    assert.notStrictEqual(acl.resultLabel, 'Passed');
    assert.ok(!/passed/i.test(acl.detail), 'the ACL check never claims a pass');
    assert.ok(!/passed/i.test(model.files[0]?.technical.aclDetail ?? ''));
    // Baseline/engine validation still governs the overall status.
    assert.ok(model.status === 'ready' || model.status === 'review');
  });

  it('distinguishes a failed check from a check that could not run', () => {
    const model = buildRecoveryReport(
      [
        makePlan({
          conflict: 'unknown', // engine gave no verdict -> not checked
          wouldSucceed: false, // simulation says it would fail -> failed
          report: { would_succeed: false, diff: {} },
          drift: 'drift_hash', // drift detected -> failed
        }),
      ],
      { nowMs: NOW_MS, workspacePath: 'C:/ws' },
    );
    assert.strictEqual(check(model, 'conflict_check').result, 'not_checked');
    assert.ok(check(model, 'conflict_check').detail.includes('no conflict verdict'));
    assert.ok(check(model, 'conflict_check').detail.includes('not a pass'));
    assert.strictEqual(check(model, 'drift_check').result, 'failed');
    assert.strictEqual(check(model, 'drift_check').resultLabel, 'Failed');
    assert.strictEqual(check(model, 'recovery_simulation').result, 'failed');
    assert.ok(check(model, 'recovery_simulation').detail.includes('would not succeed'));
    assert.strictEqual(check(model, 'baseline_evidence').result, 'passed');
  });

  it('reports a missing simulation verdict as Not checked', () => {
    const model = buildRecoveryReport([makePlan({ report: { diff: {} } })], {
      nowMs: NOW_MS,
      workspacePath: 'C:/ws',
    });
    const simulation = check(model, 'recovery_simulation');
    assert.strictEqual(simulation.result, 'not_checked');
    assert.strictEqual(simulation.resultLabel, 'Not checked');
  });

  it('reports failed baseline validation as a failed check with counts', () => {
    const model = buildRecoveryReport(
      [
        makePlan(),
        makePlan({
          resource: 'bad.txt',
          kind: 'unavailable',
          code: 'hash_mismatch',
          limitation: 'hash mismatch',
        }),
      ],
      { nowMs: NOW_MS, workspacePath: 'C:/ws' },
    );
    const baseline = check(model, 'baseline_evidence');
    assert.strictEqual(baseline.result, 'failed');
    assert.ok(baseline.detail.includes('1 of 2'));
    assert.ok(baseline.detail.includes('SHA-256'));
  });

  it('explains a non-dependency ACL failure without calling it a pass', () => {
    const detail = explainAclError('PermissionError: [Errno 13] denied');
    assert.ok(detail.includes('PermissionError'));
    assert.ok(detail.includes('did NOT run'));
    assert.ok(!detail.toLowerCase().includes('passed'));
  });
});

describe('recovery report confidentiality', () => {
  it('carries no file contents, no encoded bytes and no absolute paths', () => {
    const secret = 'TOP-SECRET-BASELINE-CONTENT';
    const plan = makePlan();
    const withSecret: PlannedRecovery = {
      ...plan,
      absolutePath: 'C:/ws/src/app.ts',
      proposed: { ...plan.proposed, text: secret, bytes: Buffer.from(secret, 'utf8') },
      evidenceFile: 'C:/storage/src/app.ts.evidence.json',
    };
    const model = buildRecoveryReport([withSecret], {
      nowMs: NOW_MS,
      workspacePath: 'C:/ws',
    });
    const serialized = JSON.stringify(model);
    assert.ok(!serialized.includes(secret), 'baseline contents must not reach the model');
    assert.ok(!serialized.includes('content_b64'));
    assert.ok(!serialized.includes('C:/ws/src/app.ts'), 'no absolute workspace path');
    assert.ok(!serialized.includes('C:/storage'), 'no absolute evidence path');
    assert.ok(!serialized.includes('TOP-SECRET'));
    // The evidence reference is a filename only.
    assert.strictEqual(model.files[0]?.technical.evidenceRef, 'app.ts.evidence.json');
  });

  it('keeps raw hashes only inside the collapsed technical details payload', () => {
    const model = buildRecoveryReport([makePlan()], { nowMs: NOW_MS, workspacePath: 'C:/ws' });
    const tech = model.files[0]?.technical;
    assert.strictEqual(tech?.baselineHash, BASELINE_HASH);
    assert.strictEqual(tech?.currentHash, CURRENT_HASH);
    // The default fields a renderer shows first (labels/reasons) hold no hashes.
    const row = model.files[0];
    assert.ok(row && !JSON.stringify({
      resource: row.resource,
      name: row.name,
      currentLabel: row.currentLabel,
      baselineLabel: row.baselineLabel,
      eligibilityLabel: row.eligibilityLabel,
      reason: row.reason,
    }).includes(BASELINE_HASH));
  });
});
