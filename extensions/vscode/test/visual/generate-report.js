/**
 * Renders the Recovery Report webview documents for visual inspection.
 *
 *   npm run compile && node test/visual/generate-report.js
 *
 * Writes three standalone HTML files next to preview.html, each exactly what
 * the panel shows (same CSP nonce rules, same design system):
 *
 *   recovery-report.html            - healthy evidence, "Ready to review"
 *   recovery-report-attention.html  - blocked / invalid baseline / missing
 *                                     pywin32 -> "Review required"
 *   recovery-report-empty.html      - no plan producible -> "Recovery
 *                                     unavailable" with Unknown counts
 *
 * Open them in a browser (or the Review pane) at typical editor widths.
 */

const path = require('path');
const fs = require('fs');
const crypto = require('crypto');

const { buildRecoveryReport } = require('../../out/src/recoveryReport.js');
const { renderRecoveryReportHtml } = require('../../out/src/recoveryReportHtml.js');

const sha = (input) => crypto.createHash('sha256').update(input).digest('hex');

const NOW = '2026-10-20T14:32:00.000Z';
const NOW_MS = Date.parse(NOW);
const WORKSPACE = 'F:/Desktop_Data_2026/Desktop/INTERLOCK V4';

const BASE = {
  workspace: WORKSPACE,
  operation: 'restore_content',
  wouldSucceed: true,
  conflict: 'no_conflict',
  drift: 'no_drift',
  currentExists: true,
  baselineCapturedAt: '2026-10-20T14:05:00Z',
  at: NOW,
  evidenceFile: 'F:/storage/interlock/baselines/report.evidence.json',
  report: {
    would_succeed: true,
    conflict_status: 'no_conflict',
    drift_status: 'no_drift',
    reversibility: 'reversible',
    matches_baseline: false,
    warnings: [],
    diff: { permissions: {}, ownership: {}, metadata: {} },
  },
};

function plan(overrides) {
  const spec = Object.assign({}, overrides);
  const resource = spec.resource || 'src/app.ts';
  const baselineText = spec.baselineText || `baseline bytes for ${resource}\n`;
  const currentText = spec.currentText || `edited ${resource} after protection\n`;
  const kind = spec.kind || 'text';
  const baselineHash = spec.baselineHash === undefined ? sha(baselineText) : spec.baselineHash;
  const currentHash = spec.currentHash === undefined ? sha(currentText) : spec.currentHash;
  const planned = Object.assign({}, BASE, spec, {
    resource,
    absolutePath: `${WORKSPACE}/${resource}`,
    baselineHash,
    currentHash,
    proposed: {
      kind,
      text: kind === 'text' ? baselineText : null,
      bytes: kind === 'unavailable' ? null : Buffer.from(baselineText, 'utf8'),
      hash: kind === 'unavailable' ? null : sha(baselineText),
      limitation:
        spec.limitation !== undefined
          ? spec.limitation
          : kind === 'binary'
            ? 'this is a binary file, so a text diff would be misleading. Compare the hashes and sizes instead - recovery writes these exact bytes.'
            : kind === 'unavailable'
              ? 'the stored baseline carries no file contents, so there is nothing exact to show.'
              : null,
      code: kind === 'unavailable' ? spec.code || 'no_contents' : null,
    },
    diffable: kind === 'text',
    evidence: {
      aclAvailable: spec.aclAvailable === undefined ? true : spec.aclAvailable,
      aclError: spec.aclError || null,
      snapshotSize: Buffer.byteLength(baselineText, 'utf8'),
      snapshotHash: sha(baselineText),
      capturedAt: '2026-10-20T14:05:00Z',
    },
    evidenceFile: `F:/storage/interlock/baselines/${resource}.evidence.json`,
  });
  delete planned.baselineText;
  delete planned.currentText;
  delete planned.limitation;
  delete planned.code;
  delete planned.kind;
  delete planned.aclAvailable;
  delete planned.aclError;
  return planned;
}

function write(name, model) {
  const html = renderRecoveryReportHtml(model, { nonce: 'ILVISUALNONCE' });
  const out = path.join(__dirname, name);
  fs.writeFileSync(out, html, 'utf8');
  console.log(`wrote ${out} (${Buffer.byteLength(html, 'utf8')} bytes)`);
  return out;
}

// 1) Healthy evidence: modified, unchanged, deleted and a binary file.
const healthy = buildRecoveryReport(
  [
    plan({
      resource: 'src/app.ts',
      baselineText: 'export const version = 6;\n',
      currentText: 'export const version = 6;\n// experimental rewrite\n',
      limitation: null,
      report: Object.assign({}, BASE.report, {
        human_change_analysis: { kind: 'code_change' },
      }),
    }),
    plan({
      resource: 'README.md',
      baselineText: '# Interlock V6\n',
      currentText: '# Interlock V6\n', // unchanged
    }),
    plan({
      resource: 'docs/operations/SAFETY_AND_LIMITATIONS.md',
      currentExists: false, // deleted after protection
      currentHash: null,
      baselineText: 'Recovery requires explicit approval.\n',
    }),
    plan({
      resource: 'assets/interlock-icon.png',
      kind: 'binary',
      baselineText: 'PNG-BYTES-PLACEHOLDER',
      currentText: 'PNG-BYTES-CHANGED',
      limitation:
        'this is a binary file, so a text diff would be misleading. Compare the hashes and sizes instead - recovery writes these exact bytes.',
    }),
  ],
  { nowMs: NOW_MS, workspacePath: WORKSPACE },
);
write('recovery-report.html', healthy);

// 2) Attention: conflict-blocked, invalid baseline, missing pywin32.
const attention = buildRecoveryReport(
  [
    plan({
      resource: 'config/settings.json',
      conflict: 'content_conflict',
      wouldSucceed: false,
      report: Object.assign({}, BASE.report, {
        would_succeed: false,
        conflict_status: 'content_conflict',
        warnings: [
          'the observed file differs from the state the plan was computed against',
        ],
      }),
      limitation: null,
    }),
    plan({
      resource: 'src/parser.ts',
      kind: 'unavailable',
      code: 'hash_mismatch',
      limitation:
        'the stored contents do not match the recorded baseline hash (expected 3f9a1c77b21e…, got 91d0ce44aa05…). Nothing is shown: recapture the baseline before previewing.',
    }),
    plan({
      resource: 'notes/team-standup.md',
      aclAvailable: false,
      aclError: "ModuleNotFoundError: No module named 'win32security'",
      report: Object.assign({}, BASE.report, {
        warnings: ['ACL capture unavailable in this Python runtime'],
      }),
      limitation: null,
    }),
  ],
  { nowMs: NOW_MS, workspacePath: WORKSPACE },
);
write('recovery-report-attention.html', attention);

// 3) Nothing to review.
const empty = buildRecoveryReport([], { nowMs: NOW_MS, workspacePath: WORKSPACE });
write('recovery-report-empty.html', empty);

console.log('status:', healthy.status, '/', attention.status, '/', empty.status);
