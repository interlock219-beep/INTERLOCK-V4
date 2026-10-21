/**
 * Renders the Recovery Inbox webview documents for visual inspection.
 *
 *   npm run compile && node test/visual/generate-inbox.js
 *
 * Writes three standalone HTML files next to preview.html, each exactly what
 * the panel shows (same CSP nonce rules, same design system):
 *
 *   recovery-inbox.html          - the file list after a scan (mixed states)
 *   recovery-inbox-review.html   - the review/confirmation step
 *   recovery-inbox-results.html  - the per-file result of a recovery run
 *
 * Open them in a browser (or the Review pane) at typical editor widths.
 */

const path = require('path');
const fs = require('fs');

const { InboxState, buildViewState } = require('../../out/src/recoveryInbox.js');
const { renderInboxHtml } = require('../../out/src/recoveryInboxHtml.js');

const NOW = '2026-10-20T14:32:00.000Z';
const NOW_MS = Date.parse(NOW);
const CAPTURED_AT = '2026-10-20T13:05:00.000Z';

function coverage(overrides) {
  return Object.assign(
    {
      baselinesChecked: 248,
      nonBaselineChecked: 132,
      skippedDirectories: 14,
      skippedDirSample: ['.git', 'node_modules', '.venv', 'site', 'out', 'dist'],
      excludedByPolicy: 6,
      walkRan: true,
      walkFailed: false,
      walkTruncated: false,
      walkLimit: 50000,
      failed: 1,
      failureNotes: ['assets/huge.log: EACCES'],
      partial: false,
    },
    overrides || {},
  );
}

function record(resource, overrides) {
  return Object.assign(
    {
      resource,
      kind: 'protected',
      status: 'modified',
      evidence: 'verified',
      evidenceNote: null,
      technical: null,
      baselineHash: 'a1b2c3d4e5f6'.padEnd(64, '0'),
      baselineSize: 2048,
      currentSize: 2310,
      capturedAt: CAPTURED_AT,
      observedAtMs: null,
      createdAfterCapture: false,
    },
    overrides || {},
  );
}

function assessment(resource, eligibility, reason) {
  return {
    resource,
    eligibility,
    reason,
    technical: 'would_succeed=true, conflict=no_conflict, drift=no_drift',
  };
}

function buildListState() {
  const state = new InboxState('F:/Desktop_Data_2026/Desktop/INTERLOCK V4', NOW_MS);
  state.beginScan(NOW_MS);
  state.applyDiscovery(
    [
      record('src/recovery/controller.ts', { status: 'modified' }),
      record('src/recovery/engine.ts', { status: 'modified' }),
      record('src/recovery/adapter.py', {
        status: 'modified',
        evidence: 'invalid',
        evidenceNote:
          'the stored contents do not match the recorded baseline hash (expected 3f9a1c77b21e…, got 91d0ce44aa05…). Nothing is shown: recapture the baseline before previewing.',
        technical:
          'Evidence check: hash_mismatch; baseline sha256 3f9a1c77b21e….',
      }),
      record('docs/operations/SAFETY_AND_LIMITATIONS.md', {
        status: 'deleted',
        currentSize: null,
      }),
      record('config/settings.json', {
        status: 'modified',
        eligibility: 'blocked',
        evidenceNote: null,
      }),
      record('README.md', { status: 'unchanged' }),
      record('assets/interlock-icon.png', { status: 'modified', currentSize: 40960 }),
      record('src/ui/new-panel.tsx', {
        kind: 'unprotected',
        status: 'created',
        evidence: 'none',
        baselineHash: null,
        baselineSize: null,
        capturedAt: null,
        createdAfterCapture: true,
        observedAtMs: NOW_MS - 600000,
      }),
      record('src/ui/legacy-panel.tsx', {
        kind: 'unprotected',
        status: 'unprotected',
        evidence: 'none',
        baselineHash: null,
        baselineSize: null,
        capturedAt: null,
        createdAfterCapture: false,
        observedAtMs: NOW_MS - 300000,
      }),
    ],
    coverage(),
    NOW_MS,
  );
  state.applyAssessment([
    assessment(
      'src/recovery/controller.ts',
      'eligible',
      'The engine simulated this recovery: it would succeed with no conflicts and no drift.',
    ),
    assessment(
      'src/recovery/engine.ts',
      'eligible',
      'The engine simulated this recovery: it would succeed with no conflicts and no drift.',
    ),
    assessment(
      'docs/operations/SAFETY_AND_LIMITATIONS.md',
      'eligible',
      'The engine simulated this recovery: it would succeed with no conflicts and no drift.',
    ),
    assessment(
      'assets/interlock-icon.png',
      'eligible',
      'The engine simulated this recovery: it would succeed with no conflicts and no drift.',
    ),
    assessment(
      'config/settings.json',
      'blocked',
      'The engine reported a conflict (concurrent_modification) between the stored baseline and the current file state.',
    ),
  ]);
  state.finishScan('done', null, NOW_MS);
  state.select(['src/recovery/controller.ts', 'src/recovery/engine.ts'], 'add');
  state.setNotice('Scan complete. 37 files changed since the last baseline capture.');
  return state;
}

function write(name, state) {
  const view = buildViewState(state, { workspaceName: 'INTERLOCK V4' });
  const html = renderInboxHtml(view, { nonce: 'ILVISUALNONCE' });
  const out = path.join(__dirname, name);
  fs.writeFileSync(out, html, 'utf8');
  console.log(`wrote ${out} (${Buffer.byteLength(html, 'utf8')} bytes)`);
  return out;
}

// 1) The list after a scan.
write('recovery-inbox.html', buildListState());

// 2) The review/confirmation step for a Recover All run.
const reviewState = buildListState();
reviewState.beginReview({
  scope: 'all',
  at: NOW,
  requested: 37,
  included: [
    {
      resource: 'src/recovery/controller.ts',
      name: 'controller.ts',
      dir: 'src/recovery',
      operation: 'restore_content',
      diffable: true,
      previewNote: null,
    },
    {
      resource: 'src/recovery/engine.ts',
      name: 'engine.ts',
      dir: 'src/recovery',
      operation: 'restore_content',
      diffable: true,
      previewNote: null,
    },
    {
      resource: 'assets/interlock-icon.png',
      name: 'interlock-icon.png',
      dir: 'assets',
      operation: 'restore_content',
      diffable: false,
      previewNote:
        'this is a binary file, so a text diff would be misleading. Compare the hashes and sizes instead - recovery writes these exact bytes.',
    },
  ],
  excluded: [
    {
      resource: 'config/settings.json',
      name: 'settings.json',
      dir: 'config',
      reason:
        "The engine's fresh plan is not applicable for this file (would_succeed=true, conflict=concurrent_modification, drift=no_drift).",
    },
    {
      resource: 'src/recovery/adapter.py',
      name: 'adapter.py',
      dir: 'src/recovery',
      reason: 'The stored baseline evidence failed validation. Recapture the baseline before recovering.',
    },
  ],
  warnings: [
    '1 file(s) cannot be shown as a text diff (binary or truncated baseline). Their bytes and hashes are still verified exactly.',
  ],
  notice: null,
  scopeCounts: { changed: 37, eligible: 29, attention: 5, noBaseline: 3 },
});
write('recovery-inbox-review.html', reviewState);

// 3) The results of a run.
const resultsState = buildListState();
resultsState.setResults({
  scope: 'all',
  startedAt: NOW,
  finishedAt: NOW,
  approvedBy: 'Dana Ops (ref: CHG-4711)',
  entries: [
    {
      resource: 'src/recovery/controller.ts',
      name: 'controller.ts',
      dir: 'src/recovery',
      outcome: 'recovered',
      label: 'Recovered',
      tone: 'ok',
      message:
        'Recovered and verified byte-exact: the engine restored the captured bytes and the extension re-checked the hash independently.',
      verified: true,
      details: null,
      diffable: true,
    },
    {
      resource: 'src/recovery/engine.ts',
      name: 'engine.ts',
      dir: 'src/recovery',
      outcome: 'skipped',
      label: 'Skipped',
      tone: 'warn',
      message:
        'Skipped: the file changed after the preview (3f9a1c77b21e… → 91d0ce44aa05…) - nothing was written for it.',
      verified: false,
      details: null,
      diffable: true,
    },
    {
      resource: 'docs/operations/SAFETY_AND_LIMITATIONS.md',
      name: 'SAFETY_AND_LIMITATIONS.md',
      dir: 'docs/operations',
      outcome: 'failed',
      label: 'Failed',
      tone: 'bad',
      message: 'The engine refused recovery: conflict or safety check.',
      verified: false,
      details: 'engine_refusal: the file was changed by someone else after the review.',
      diffable: true,
    },
  ],
  counts: { recovered: 1, skipped: 1, failed: 1, attention: 0, total: 3 },
  running: false,
});
write('recovery-inbox-results.html', resultsState);

console.log('wrote 3 inbox documents');
