/**
 * Recovery Inbox model tests (pure).
 *
 * The Inbox is where a user decides what to recover after many automated
 * changes, so the model has to be honest to the point of being boring:
 * counts come from validated records or they read "Unknown", eligibility
 * comes from the engine's verdicts, ineligible files may be selected but are
 * never part of a recovery run, and a stale scan never enables recovery.
 */

import * as assert from 'assert';

import {
  AssessmentEntry,
  InboxCoverage,
  InboxRecord,
  InboxState,
  applyStaleToReview,
  buildCounts,
  buildReviewScope,
  coverageLines,
  reviewApprovalDetail,
  runEntryFromOutcome,
  selectionSummaryText,
  skippedRunEntry,
} from '../../src/recoveryInbox';

const NOW = '2026-10-20T12:00:00.000Z';

function coverage(overrides: Partial<InboxCoverage> = {}): InboxCoverage {
  return {
    baselinesChecked: 0,
    nonBaselineChecked: 0,
    skippedDirectories: 0,
    skippedDirSample: [],
    excludedByPolicy: 0,
    walkRan: false,
    walkFailed: false,
    walkTruncated: false,
    walkLimit: 50_000,
    failed: 0,
    failureNotes: [],
    partial: false,
    ...overrides,
  };
}

function record(overrides: Partial<InboxRecord> = {}): InboxRecord {
  return {
    resource: 'src/app.ts',
    kind: 'protected',
    status: 'modified',
    evidence: 'verified',
    evidenceNote: null,
    technical: null,
    baselineHash: 'a'.repeat(64),
    baselineSize: 10,
    currentSize: 12,
    capturedAt: NOW,
    observedAtMs: null,
    createdAfterCapture: false,
    ...overrides,
  };
}

function assessment(
  resource: string,
  eligibility: AssessmentEntry['eligibility'],
  reason = 'The engine simulated this recovery: it would succeed with no conflicts and no drift.',
): AssessmentEntry {
  return { resource, eligibility, reason, technical: 'would_succeed=true, conflict=no_conflict' };
}

function stateWith(records: InboxRecord[], cov: InboxCoverage = coverage()): InboxState {
  const state = new InboxState('C:/workspace', Date.parse(NOW));
  state.beginScan(Date.parse(NOW));
  state.applyDiscovery(records, cov, Date.parse(NOW));
  state.finishScan('done', null, Date.parse(NOW));
  return state;
}

describe('Recovery Inbox model - classification', () => {
  it('classifies modified, deleted, unchanged and unreadable files', () => {
    const state = stateWith([
      record({ resource: 'a.ts', status: 'modified' }),
      record({ resource: 'b.ts', status: 'deleted' }),
      record({ resource: 'c.ts', status: 'unchanged' }),
      record({ resource: 'd.ts', status: 'unknown', technical: 'Current file unreadable (EACCES).' }),
    ]);

    const a = state.rowFor('a.ts');
    const b = state.rowFor('b.ts');
    const c = state.rowFor('c.ts');
    const d = state.rowFor('d.ts');
    assert.ok(a && b && c && d);
    assert.strictEqual(a.status, 'modified');
    assert.strictEqual(b.status, 'deleted');
    assert.strictEqual(c.status, 'unchanged');
    assert.strictEqual(d.status, 'unknown');
    assert.strictEqual(a.eligibility, 'pending', 'the engine still has to assess a changed file');
    assert.strictEqual(c.eligibility, 'none', 'an unchanged file needs no recovery');
    assert.ok(c.reason.includes('matches the captured baseline'));
  });

  it('never calls invalid or unusable evidence recoverable', () => {
    const state = stateWith([
      record({
        resource: 'hash.ts',
        evidence: 'invalid',
        evidenceNote: 'the stored contents do not match the recorded baseline hash.',
      }),
      record({ resource: 'empty.ts', evidence: 'unusable', evidenceNote: 'no contents stored' }),
    ]);

    const invalid = state.rowFor('hash.ts');
    const unusable = state.rowFor('empty.ts');
    assert.ok(invalid && unusable);
    assert.strictEqual(invalid.eligibility, 'unavailable');
    assert.strictEqual(unusable.eligibility, 'unavailable');
    assert.strictEqual(invalid.flags.attention, true, 'broken evidence needs attention');
    assert.strictEqual(invalid.flags.recoverable, false);
    assert.ok(invalid.reason.includes('do not match the recorded baseline hash'));
  });

  it('explains files without a baseline instead of pretending they can be recovered', () => {
    const state = stateWith([
      record({
        resource: 'new.ts',
        kind: 'unprotected',
        status: 'created',
        evidence: 'none',
        baselineHash: null,
        capturedAt: null,
        createdAfterCapture: true,
        observedAtMs: Date.parse(NOW),
      }),
      record({
        resource: 'touched.ts',
        kind: 'unprotected',
        status: 'unprotected',
        evidence: 'none',
        baselineHash: null,
        capturedAt: null,
        createdAfterCapture: false,
        observedAtMs: Date.parse(NOW),
      }),
    ]);

    const created = state.rowFor('new.ts');
    const touched = state.rowFor('touched.ts');
    assert.ok(created && touched);
    assert.strictEqual(created.flags.unprotected, true);
    assert.strictEqual(created.flags.recoverable, false);
    assert.ok(created.reason.includes('no saved prior version'));
    assert.ok(touched.reason.includes('no stored baseline'));
    assert.strictEqual(created.flags.attention, false, 'no baseline is not a failure');
  });
});

describe('Recovery Inbox model - summary counts', () => {
  it('counts examined, changed, verified, recoverable, attention and no-baseline files', () => {
    const state = stateWith(
      [
        record({ resource: 'a.ts', status: 'modified' }),
        record({ resource: 'b.ts', status: 'deleted' }),
        record({ resource: 'c.ts', status: 'unchanged' }),
        record({
          resource: 'd.ts',
          status: 'modified',
          evidence: 'invalid',
          evidenceNote: 'broken',
        }),
        record({
          resource: 'e.ts',
          kind: 'unprotected',
          status: 'created',
          evidence: 'none',
          baselineHash: null,
          capturedAt: null,
          createdAfterCapture: true,
        }),
      ],
      coverage({ baselinesChecked: 4, nonBaselineChecked: 1, walkRan: true }),
    );
    state.applyAssessment([
      assessment('a.ts', 'eligible'),
      assessment('b.ts', 'eligible'),
    ]);

    assert.strictEqual(state.counts.examined, 5);
    assert.strictEqual(state.counts.changed, 3, 'modified, deleted and the file with broken evidence');
    assert.strictEqual(state.counts.verifiedEvidence, 3);
    assert.strictEqual(state.counts.recoverableModified, 1);
    assert.strictEqual(state.counts.recoverableDeleted, 1);
    assert.strictEqual(state.counts.attention, 1);
    assert.strictEqual(state.counts.noBaseline, 1);
  });

  it('reports Unknown - never zero - before a scan or after a failed scan', () => {
    const fresh = new InboxState('C:/workspace', Date.parse(NOW));
    for (const value of Object.values(fresh.counts)) {
      assert.strictEqual(value, null);
    }
    fresh.beginScan(Date.parse(NOW));
    fresh.finishScan('error', 'the scan failed', Date.parse(NOW));
    for (const value of Object.values(fresh.counts)) {
      assert.strictEqual(value, null);
    }
  });

  it('reports Unknown for recoverable counts while a candidate is still unassessed', () => {
    const state = stateWith(
      [record({ resource: 'a.ts', status: 'modified' })],
      coverage({ baselinesChecked: 1 }),
    );
    assert.strictEqual(state.counts.recoverableModified, null);
    assert.strictEqual(state.counts.recoverableDeleted, null);
    assert.strictEqual(state.counts.changed, 1, 'other counts stay known');
  });

  it('reports Unknown for the no-baseline count when the walk was partial', () => {
    const state = stateWith(
      [record({ resource: 'a.ts' })],
      coverage({ baselinesChecked: 1, walkRan: true, walkTruncated: true }),
    );
    assert.strictEqual(state.counts.noBaseline, null);
    assert.ok(
      coverageLines(state.scan.coverage).some((line) => line.includes('PARTIAL')),
      'a truncated walk must be disclosed',
    );
  });

  it('keeps the baseline-relative counts honest when there is no baseline at all', () => {
    const state = stateWith([], coverage({ baselinesChecked: 0, walkRan: false }));
    assert.strictEqual(state.counts.examined, 0);
    assert.strictEqual(state.counts.changed, 0);
    assert.strictEqual(state.counts.noBaseline, null, 'the walk never ran');
  });

  it('builds counts for an empty, fully known scan without pretending', () => {
    const counts = buildCounts([], { status: 'done', coverage: coverage() });
    assert.strictEqual(counts.examined, 0);
    assert.strictEqual(counts.attention, 0);
  });
});

describe('Recovery Inbox model - selection', () => {
  it('ignores resources the scan did not discover', () => {
    const state = stateWith([record({ resource: 'a.ts' })]);
    state.select(['a.ts', '../../etc/passwd'], 'add');
    assert.deepStrictEqual(state.selectedResources(), ['a.ts']);
  });

  it('reports how many selected files are eligible and which need attention', () => {
    const state = stateWith([
      record({ resource: 'a.ts' }),
      record({ resource: 'b.ts' }),
      record({ resource: 'c.ts', evidence: 'invalid', evidenceNote: 'broken' }),
    ]);
    state.applyAssessment([assessment('a.ts', 'eligible'), assessment('b.ts', 'blocked')]);
    state.select(['a.ts', 'b.ts', 'c.ts'], 'add');

    const summary = state.selectionSummary();
    assert.strictEqual(summary.count, 3);
    assert.strictEqual(summary.eligible, 1);
    assert.strictEqual(summary.attention, 2);
    assert.strictEqual(summary.text, '3 files selected · 1 eligible · 2 require attention');
  });

  it('never includes an ineligible file in the recoverable set', () => {
    const state = stateWith([
      record({ resource: 'a.ts' }),
      record({ resource: 'b.ts' }),
    ]);
    state.applyAssessment([assessment('a.ts', 'eligible'), assessment('b.ts', 'blocked')]);
    state.select(['a.ts', 'b.ts'], 'add');
    assert.deepStrictEqual(state.recoverableSelected(), ['a.ts']);
  });

  it('formats the selection summary for one file', () => {
    assert.strictEqual(
      selectionSummaryText({ count: 1, eligible: 1, attention: 0, pending: 0 }),
      '1 file selected · 1 eligible · 0 require attention',
    );
  });

  it('clears the selection when a new scan starts', () => {
    const state = stateWith([record({ resource: 'a.ts' })]);
    state.select(['a.ts'], 'add');
    assert.strictEqual(state.selectionSummary().count, 1);
    state.beginScan(Date.parse(NOW));
    assert.strictEqual(state.selectionSummary().count, 0);
  });
});

describe('Recovery Inbox model - recovery scope', () => {
  it('computes the Recover All scope from changed files with verified evidence', () => {
    const state = stateWith(
      [
        record({ resource: 'a.ts' }),
        record({ resource: 'b.ts' }),
        record({ resource: 'c.ts', status: 'unchanged' }),
        record({ resource: 'd.ts', evidence: 'invalid', evidenceNote: 'broken' }),
        record({
          resource: 'e.ts',
          kind: 'unprotected',
          status: 'created',
          evidence: 'none',
          baselineHash: null,
          capturedAt: null,
          createdAfterCapture: true,
        }),
      ],
      coverage({ baselinesChecked: 4, nonBaselineChecked: 1, walkRan: true }),
    );
    state.applyAssessment([assessment('a.ts', 'eligible'), assessment('b.ts', 'blocked')]);

    const scope = state.recoverAllScope();
    assert.strictEqual(scope.changed, 3, 'every baseline-relative change counts as changed');
    assert.strictEqual(scope.eligible, 1);
    assert.strictEqual(scope.attention, 2, 'the blocked file and the broken evidence');
    assert.strictEqual(scope.noBaseline, 1);
    assert.deepStrictEqual(scope.candidates, ['a.ts']);
  });

  it('disables Recover Selected while a selected file is unassessed', () => {
    const state = stateWith([record({ resource: 'a.ts' })]);
    state.select(['a.ts'], 'add');
    const action = state.recoverSelectedAction();
    assert.strictEqual(action.enabled, false);
    assert.ok(action.note.includes('not been assessed'));
  });

  it('enables Recover Selected only for eligible selected files', () => {
    const state = stateWith([record({ resource: 'a.ts' })]);
    state.applyAssessment([assessment('a.ts', 'eligible')]);
    state.select(['a.ts'], 'add');
    const action = state.recoverSelectedAction();
    assert.strictEqual(action.enabled, true);
    assert.ok(action.label.includes('(1)'));
  });

  it('disables every recovery action while the scan is stale', () => {
    const state = stateWith([record({ resource: 'a.ts' })]);
    state.applyAssessment([assessment('a.ts', 'eligible')]);
    state.select(['a.ts'], 'add');
    state.markStale('Workspace files changed since this scan.');
    assert.strictEqual(state.recoverSelectedAction().enabled, false);
    assert.strictEqual(state.recoverAllAction().enabled, false);
    assert.ok(state.recoverSelectedAction().note.includes('changed'));
  });

  it('disables Recover All until the scan completed', () => {
    const state = new InboxState('C:/workspace', Date.parse(NOW));
    state.beginScan(Date.parse(NOW));
    state.applyDiscovery([record({ resource: 'a.ts' })], coverage({ baselinesChecked: 1 }));
    state.applyAssessment([assessment('a.ts', 'eligible')]);
    const action = state.recoverAllAction();
    assert.strictEqual(action.enabled, false, 'an unfinished scan has no eligible set');
  });
});

describe('Recovery Inbox model - run outcomes', () => {
  it('marks recovered files as unchanged and makes the scan stale', () => {
    const state = stateWith([record({ resource: 'a.ts' })]);
    state.applyAssessment([assessment('a.ts', 'eligible')]);
    state.select(['a.ts'], 'add');

    state.applyRunOutcomes([{ resource: 'a.ts', outcome: 'recovered' }]);

    const row = state.rowFor('a.ts');
    assert.ok(row);
    assert.strictEqual(row.status, 'unchanged');
    assert.strictEqual(row.flags.recoverable, false);
    assert.strictEqual(state.selectionSummary().count, 0);
    assert.strictEqual(state.scan.stale, true, 'the rows are outdated after a write');
    assert.strictEqual(state.recoverAllAction().enabled, false);
  });

  it('leaves failed files untouched', () => {
    const state = stateWith([record({ resource: 'a.ts' })]);
    state.applyRunOutcomes([{ resource: 'a.ts', outcome: 'failed' }]);
    const row = state.rowFor('a.ts');
    assert.ok(row);
    assert.strictEqual(row.status, 'modified');
  });
});

describe('Recovery Inbox model - review scope', () => {
  function planLike(resource: string, overrides: Partial<Parameters<typeof buildReviewScope>[2] extends Map<string, infer V> ? V : never> = {}) {
    return {
      resource,
      operation: 'restore_content',
      diffable: true,
      previewNote: null,
      applicable: true,
      blockedReason: null,
      ...overrides,
    };
  }

  it('shows every requested file either as included or as excluded with a reason', () => {
    const result = buildReviewScope(
      'selected',
      ['a.ts', 'b.ts', 'c.ts'],
      new Map([
        ['a.ts', planLike('a.ts')],
        ['b.ts', planLike('b.ts', { applicable: false, blockedReason: 'The engine reported a conflict.' })],
      ]),
      new Map([['c.ts', 'The engine could not plan this file.']]),
    );
    assert.deepStrictEqual(result.included.map((entry) => entry.resource), ['a.ts']);
    assert.strictEqual(result.excluded.length, 2);
    assert.ok(result.excluded[0].reason.includes('conflict'));
    assert.ok(result.excluded[1].reason.includes('could not plan'));
  });

  it('warns when a recovered file cannot be shown as a text diff', () => {
    const result = buildReviewScope(
      'all',
      ['a.png'],
      new Map([['a.png', planLike('a.png', { diffable: false, previewNote: 'binary file' })]]),
      new Map(),
    );
    assert.strictEqual(result.included.length, 1);
    assert.ok(result.warnings[0].includes('binary or truncated baseline'));
  });

  it('removes files that changed since the review and asks for a new confirmation', () => {
    const review = {
      scope: 'all' as const,
      at: NOW,
      requested: 2,
      included: [
        { resource: 'a.ts', name: 'a.ts', dir: '.', operation: 'restore', diffable: true, previewNote: null },
        { resource: 'b.ts', name: 'b.ts', dir: '.', operation: 'restore', diffable: true, previewNote: null },
      ],
      excluded: [],
      warnings: [],
      notice: null,
      scopeCounts: { changed: 2, eligible: 2, attention: 0, noBaseline: 0 },
    };
    const updated = applyStaleToReview(review, [{ resource: 'b.ts', reason: 'the file changed after the preview' }]);
    assert.deepStrictEqual(updated.included.map((entry) => entry.resource), ['a.ts']);
    assert.strictEqual(updated.excluded.length, 1);
    assert.ok(updated.excluded[0].reason.includes('Changed since the review'));
    assert.ok(updated.notice?.includes('confirm again'));
  });

  it('keeps the review untouched when nothing changed', () => {
    const review = {
      scope: 'selected' as const,
      at: NOW,
      requested: 1,
      included: [
        { resource: 'a.ts', name: 'a.ts', dir: '.', operation: 'restore', diffable: true, previewNote: null },
      ],
      excluded: [],
      warnings: [],
      notice: null,
      scopeCounts: null,
    };
    assert.strictEqual(applyStaleToReview(review, []), review);
  });
});

describe('Recovery Inbox model - per-file results', () => {
  const plan = { resource: 'src/app.ts', diffable: true };

  it('reports a verified restore as recovered', () => {
    const entry = runEntryFromOutcome(plan, {
      resource: 'src/app.ts',
      success: true,
      skipped: false,
      verified: true,
      message: 'Recovered and verified byte-exact.',
      details: null,
    });
    assert.strictEqual(entry.outcome, 'recovered');
    assert.strictEqual(entry.verified, true);
    assert.strictEqual(entry.tone, 'ok');
  });

  it('never calls an unverified restore a success', () => {
    const entry = runEntryFromOutcome(plan, {
      resource: 'src/app.ts',
      success: false,
      skipped: false,
      verified: false,
      message: 'Recovery ran but verification did NOT confirm a byte-exact restore.',
      details: null,
    });
    assert.strictEqual(entry.outcome, 'attention');
    assert.strictEqual(entry.verified, false);
    assert.strictEqual(entry.label, 'Needs attention');
  });

  it('reports a refusal as a failure', () => {
    const entry = runEntryFromOutcome(plan, {
      resource: 'src/app.ts',
      success: false,
      skipped: false,
      verified: false,
      message: 'The engine refused recovery: conflict or safety check.',
      details: null,
    });
    assert.strictEqual(entry.outcome, 'failed');
    assert.strictEqual(entry.verified, false);
  });

  it('reports a file that was never written as skipped', () => {
    const entry = skippedRunEntry(plan, 'Skipped: the file changed - nothing was written for it.');
    assert.strictEqual(entry.outcome, 'skipped');
    assert.strictEqual(entry.verified, false);
    assert.ok(entry.message.includes('nothing was written'));
  });
});

describe('Recovery Inbox model - review text', () => {
  it('states the exact scope and every exclusion in the approval detail', () => {
    const detail = reviewApprovalDetail({
      scope: 'all',
      at: NOW,
      requested: 3,
      included: [
        { resource: 'a.ts', name: 'a.ts', dir: '.', operation: 'restore', diffable: true, previewNote: null },
        { resource: 'b.ts', name: 'b.ts', dir: '.', operation: 'restore', diffable: true, previewNote: null },
      ],
      excluded: [
        { resource: 'c.ts', name: 'c.ts', dir: '.', reason: 'The engine reported a conflict.' },
      ],
      warnings: [],
      notice: null,
      scopeCounts: { changed: 3, eligible: 2, attention: 1, noBaseline: 0 },
    });
    assert.ok(detail.includes('overwrite 2 files'));
    assert.ok(detail.includes('a.ts'));
    assert.ok(detail.includes('b.ts'));
    assert.ok(detail.includes('1 file from this scope will NOT be recovered'));
  });

  it('never omits the number of files when the list is truncated', () => {
    const included = Array.from({ length: 60 }, (_, index) => ({
      resource: `file-${index}.ts`,
      name: `file-${index}.ts`,
      dir: '.',
      operation: 'restore',
      diffable: true,
      previewNote: null,
    }));
    const detail = reviewApprovalDetail({
      scope: 'selected',
      at: NOW,
      requested: 60,
      included,
      excluded: [],
      warnings: [],
      notice: null,
      scopeCounts: null,
    });
    assert.ok(detail.includes('and 20 more file(s) listed in the Recovery Inbox review'));
  });
});
