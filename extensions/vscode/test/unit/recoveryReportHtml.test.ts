/**
 * Recovery Report renderer tests (pure).
 *
 * The report panel is a webview, so these tests pin down the rendering
 * contract: the CSP permits nothing but this render's nonce, every dynamic
 * value is escaped, hashes/technical details stay inside a collapsed
 * section, failed checks and "Not checked" checks render distinctly, every
 * disabled action carries an explanation, the message bridge is typed and
 * inert (no innerHTML/eval), and there is no control anywhere in the report
 * that could execute a recovery or ask for an approver.
 */

import * as assert from 'assert';
import * as fs from 'fs';
import * as path from 'path';
import * as crypto from 'crypto';

import {
  buildRecoveryReport,
  previewableResources,
} from '../../src/recoveryReport';
import {
  isReportMessage,
  isSafeResource,
  renderRecoveryReportHtml,
} from '../../src/recoveryReportHtml';
import { PlannedRecovery, ProposedCode } from '../../src/recoveryPlan';
import { PREVIEW_TTL_MS } from '../../src/protection';

const sha = (input: string): string =>
  crypto.createHash('sha256').update(input).digest('hex');

const NOW = '2026-10-20T12:00:00.000Z';
const NOW_MS = Date.parse(NOW);
const BASELINE = 'BASELINE-CONTENT-EXACT-BYTES\n';
const BASELINE_HASH = sha(BASELINE);

function makePlan(spec: {
  resource?: string;
  currentHash?: string | null;
  conflict?: string;
  drift?: string;
  wouldSucceed?: boolean;
  kind?: 'text' | 'binary' | 'unavailable';
  code?: ProposedCode;
  limitation?: string;
  aclAvailable?: boolean | null;
  aclError?: string | null;
  at?: string;
  report?: Record<string, unknown>;
} = {}): PlannedRecovery {
  const kind = spec.kind ?? 'text';
  return {
    workspace: 'C:/ws',
    resource: spec.resource ?? 'src/app.ts',
    absolutePath: 'C:/ws/src/app.ts',
    operation: 'restore_content',
    wouldSucceed: spec.wouldSucceed !== false,
    conflict: spec.conflict ?? 'no_conflict',
    drift: spec.drift ?? 'no_drift',
    baselineHash: BASELINE_HASH,
    currentHash: spec.currentHash === undefined ? sha('changed\n') : spec.currentHash,
    currentExists: true,
    baselineCapturedAt: '2026-10-20T09:00:00Z',
    at: spec.at ?? NOW,
    proposed: {
      kind,
      text: kind === 'text' ? BASELINE : null,
      bytes: kind === 'unavailable' ? null : Buffer.from(BASELINE, 'utf8'),
      hash: kind === 'unavailable' ? null : BASELINE_HASH,
      limitation:
        spec.limitation ??
        (kind === 'binary'
          ? 'this is a binary file, so a text diff would be misleading.'
          : null),
      code: kind === 'unavailable' ? (spec.code ?? 'no_contents') : null,
    },
    diffable: kind === 'text',
    evidence: {
      aclAvailable: spec.aclAvailable === undefined ? true : spec.aclAvailable,
      aclError: spec.aclError ?? null,
      snapshotSize: BASELINE.length,
      snapshotHash: BASELINE_HASH,
      capturedAt: '2026-10-20T09:00:00Z',
    },
    evidenceFile: 'C:/storage/src/app.ts.evidence.json',
    report:
      spec.report ?? {
        would_succeed: true,
        conflict_status: spec.conflict ?? 'no_conflict',
        drift_status: 'no_drift',
        reversibility: 'reversible',
        matches_baseline: false,
        warnings: ['engine warning sample'],
        diff: { permissions: {}, ownership: {}, metadata: {} },
      },
  };
}

const render = (plans: PlannedRecovery[], workspacePath = 'C:/ws'): string =>
  renderRecoveryReportHtml(buildRecoveryReport(plans, { nowMs: NOW_MS, workspacePath }), {
    nonce: 'TESTNONCE',
  });

describe('recovery report rendering (CSP, escaping, structure)', () => {
  it('allows nothing but this render nonce - no images, fonts or remote code', () => {
    const html = render([makePlan()]);
    assert.ok(html.includes("default-src 'none'"));
    assert.ok(html.includes("img-src 'none'"));
    assert.ok(html.includes("font-src 'none'"));
    assert.ok(html.includes("style-src 'nonce-TESTNONCE'"));
    assert.ok(html.includes("script-src 'nonce-TESTNONCE'"));
    assert.ok(!html.includes('https://'), 'no remote URLs');
    assert.ok(!html.includes('http://'), 'no remote URLs');
    assert.ok(!/<script[^>]+src=/.test(html), 'no external scripts');
    assert.ok(!/<link[^>]+href=/.test(html), 'no external stylesheets');
  });

  it('escapes every dynamic value (workspace, resource, reason, notices)', () => {
    const hostile = makePlan({
      resource: 'src/<script>alert(1)</script>.ts',
    });
    const html = render([hostile], 'C:/my "quoted" ws');
    assert.ok(!html.includes('<script>alert(1)</script>'), 'payload must be escaped');
    assert.ok(html.includes('&lt;script&gt;alert(1)&lt;/script&gt;'));
    assert.ok(
      html.includes('my &quot;quoted&quot; ws'),
      'workspace name escaped in text and title positions',
    );
    assert.ok(!html.includes('quoted" ws'));
    // The only <script> element in the document is the extension's own bridge.
    const scriptTags = html.match(/<script[^>]*>/g) ?? [];
    assert.strictEqual(scriptTags.length, 1);
    assert.ok(scriptTags[0].includes('nonce="TESTNONCE"'));
  });

  it('renders header, summary, files, safety checks and actions', () => {
    const html = render([makePlan()]);
    // Header: brand shield, title, workspace, generation time, status pill.
    assert.ok(html.includes('il-wordmark">Recovery Report</span>'));
    assert.ok(html.includes('fill-rule="evenodd"'), 'brand shield artwork');
    assert.ok(html.includes('src/app.ts') || html.includes('C:/ws'), 'workspace shown');
    assert.ok(/GENERATED 2026-10-2\d/.test(html), 'generation time');
    assert.ok(html.includes('Ready to review'), 'overall status');
    // Sections.
    assert.ok(html.includes('>Summary</h2>'));
    assert.ok(html.includes('>Files <span class="il-r-count">1</span></h2>'));
    assert.ok(html.includes('>Safety checks</h2>'));
    // Actions: preview, refresh, close.
    assert.ok(html.includes('Preview Recovery'));
    assert.ok(html.includes('Refresh Report'));
    assert.ok(html.includes('>Close</span>'));
    assert.ok(html.includes('Nothing has been recovered'));
  });

  it('hashes and technical details live only in a collapsed section', () => {
    const html = render([makePlan()]);
    const technical = '<details class="il-collapsible il-r-tech">';
    assert.ok(html.includes(technical), 'per-file technical details exist');
    const detailsIndex = html.indexOf(technical);
    const openIndex = html.indexOf(' open>', detailsIndex);
    const summaryIndex = html.indexOf('<summary>Technical details</summary>', detailsIndex);
    assert.ok(summaryIndex > detailsIndex, 'technical section has a summary');
    assert.ok(
      openIndex === -1 || openIndex > html.indexOf('</details>', summaryIndex),
      'technical details start collapsed',
    );
    // The hash appears only AFTER the technical summary, never before it.
    const hashIndex = html.indexOf(BASELINE_HASH);
    assert.ok(hashIndex > summaryIndex, 'hash hidden inside collapsed details');
    // And the default payload carries no raw engine fields or encoded contents.
    assert.ok(!html.includes('content_b64'));
    assert.ok(!html.includes('would_succeed'));
    assert.ok(!html.includes('conflict_status'));
    assert.ok(!html.includes('"permissions"'));
    assert.ok(!html.includes('BASELINE-CONTENT-EXACT-BYTES'), 'no file contents anywhere');
  });

  it('renders "Unknown" for underivable counts instead of zero', () => {
    const html = render([makePlan({ currentHash: null })]);
    assert.ok(html.includes('>Unknown<'), 'unknown count is shown as Unknown');
    const unknownCount = (html.match(/il-r-unknown/g) ?? []).length;
    assert.ok(unknownCount >= 1, 'at least the "differing" count is Unknown');
  });

  it('renders Not checked distinctly from Failed', () => {
    const error = "ModuleNotFoundError: No module named 'win32security'";
    const html = render([
      makePlan({ aclAvailable: false, aclError: error, report: { diff: {} } }),
    ]);
    // ACL could not run: Not checked + plain-language explanation.
    const notChecked = (html.match(/>Not checked</g) ?? []).length;
    assert.ok(notChecked >= 1, 'a check that could not run shows Not checked');
    assert.ok(html.includes('pywin32'));
    assert.ok(html.includes('win32security'), 'the underlying error stays visible');
    assert.ok(html.includes('did NOT run'));
    // The check row in the Safety checks section reports Not checked.
    const checksAt = html.indexOf('>Safety checks</h2>');
    assert.ok(checksAt > 0, 'safety checks section exists');
    const aclAt = html.indexOf('File ACL comparison', checksAt);
    assert.ok(aclAt > checksAt, 'ACL check listed under safety checks');
    const aclRow = html.slice(aclAt, aclAt + 500);
    assert.ok(aclRow.includes('Not checked'), 'ACL result is Not checked');
    assert.ok(!/File ACL comparison<\/span>\s*<span class="il-pill" data-tone-value="ok"/.test(html));
    // A genuinely failed check renders as Failed (drift).
    const failedHtml = render([makePlan({ drift: 'drift_hash' })]);
    assert.ok(failedHtml.includes('>Failed<'));
  });

  it('disables ineligible preview buttons and explains why, visibly', () => {
    const html = render([makePlan({ conflict: 'content_conflict' })]);
    assert.ok(/class="il-r-preview" data-action="preview"[\s\S]{0,400}disabled/.test(html));
    assert.ok(html.includes('The engine reported a conflict (content_conflict)'), 'visible reason');
    // The disabled action still carries a tooltip explanation.
    const button = html.slice(html.indexOf('data-action="preview"'));
    assert.ok(button.includes('Recovery is not available for this file'));
    // An eligible file keeps an enabled button.
    const okHtml = render([makePlan()]);
    const okButtons = [...okHtml.matchAll(/data-action="preview"[\s\S]{0,220}?title="[^"]*">/g)];
    assert.strictEqual(okButtons.length, 1, 'one preview button for one file');
    assert.ok(!okButtons[0][0].includes('disabled'), 'eligible preview stays enabled');
    assert.ok(okHtml.includes('Open the side-by-side diff for src/app.ts'));
  });

  it('exposes only typed, inert controls: preview, previewAll, refresh, close, copy', () => {
    const html = render([makePlan()]);
    const actions = new Set(html.match(/data-action="([a-zA-Z]+)"/g) ?? []);
    assert.deepStrictEqual(
      [...actions].sort(),
      [
        'data-action="close"',
        'data-action="copy"',
        'data-action="preview"',
        'data-action="previewAll"',
        'data-action="refresh"',
      ],
    );
    // No execution, no apply, no approval prompt, no inputs at all.
    assert.ok(!/data-action="(apply|execute|recover|approve)"/.test(html));
    assert.ok(!/<input\b/i.test(html));
    assert.ok(!/<textarea\b/i.test(html));
    assert.ok(!/approver/i.test(html));
    assert.ok(!/showInputBox/.test(html));
    // The script is message-only: no DOM injection or evaluation.
    const script = html.slice(html.indexOf('<script nonce='));
    assert.ok(!script.includes('innerHTML'));
    assert.ok(!script.includes('eval('));
    assert.ok(!script.includes('document.write'));
    assert.ok(script.includes("type: 'refresh'"));
    assert.ok(script.includes("type: 'close'"));
    assert.ok(script.includes("type: 'preview'"));
    assert.ok(script.includes('acquireVsCodeApi'));
  });

  it('shows the stale-evidence notice and a Refresh path', () => {
    const staleAt = new Date(NOW_MS - PREVIEW_TTL_MS - 60_000).toISOString();
    const html = render([makePlan({ at: staleAt })]);
    assert.ok(html.includes('il-r-notice'), 'stale notice rendered');
    assert.ok(html.includes('Refresh to re-observe'));
    assert.ok(html.includes('Refresh Report'));
  });

  it('renders an honest empty report when no plan could be produced', () => {
    const html = render([]);
    assert.ok(html.includes('Recovery unavailable'));
    assert.ok(html.includes('No files were reviewed'));
    assert.ok(html.includes('>Unknown<'), 'counts are Unknown, not zero');
    assert.ok(html.includes('Not checked'), 'no check claims to have run');
    assert.ok(!html.includes('Ready to review'));
  });
});

describe('recovery report message bridge', () => {
  it('accepts only the typed messages the script can send', () => {
    assert.ok(isReportMessage({ type: 'ready' }));
    assert.ok(isReportMessage({ type: 'refresh' }));
    assert.ok(isReportMessage({ type: 'close' }));
    assert.ok(isReportMessage({ type: 'previewAll' }));
    assert.ok(isReportMessage({ type: 'preview', resource: 'src/app.ts' }));
    assert.ok(!isReportMessage({ type: 'preview' }), 'preview requires a resource');
    assert.ok(!isReportMessage({ type: 'preview', resource: 7 }), 'resource must be a string');
    assert.ok(!isReportMessage({ type: 'execute' }), 'unknown type rejected');
    assert.ok(!isReportMessage({ type: 'apply' }));
    assert.ok(!isReportMessage(null));
    assert.ok(!isReportMessage('ready'));
    assert.ok(!isReportMessage({ type: 'refresh', resource: { evil: true } }));
  });

  it('rejects traversal, absolute and drive paths', () => {
    assert.ok(isSafeResource('src/app.ts'));
    assert.ok(isSafeResource('README.md'));
    assert.ok(!isSafeResource('../secrets.txt'));
    assert.ok(!isSafeResource('src/../../etc/passwd'));
    assert.ok(!isSafeResource('/etc/passwd'));
    assert.ok(!isSafeResource('C:/windows/system32'));
    assert.ok(!isSafeResource('C:\\windows'));
    assert.ok(!isSafeResource('src\\app.ts'));
    assert.ok(!isSafeResource(''));
    assert.ok(!isSafeResource('a\u0000b'));
  });

  it('the rendered allow-list matches the previewable rows exactly', () => {
    const plans = [
      makePlan({ resource: 'ok.ts' }),
      makePlan({ resource: 'blocked.ts', conflict: 'content_conflict' }),
    ];
    const model = buildRecoveryReport(plans, { nowMs: NOW_MS, workspacePath: 'C:/ws' });
    const html = renderRecoveryReportHtml(model, { nonce: 'TESTNONCE' });
    assert.deepStrictEqual(previewableResources(model), ['ok.ts']);
    const buttons = [...html.matchAll(/data-action="preview"\s+data-resource="([^"]+)"([^>]*)>/g)];
    const resources = buttons.map((match) => match[1]);
    const enabled = buttons
      .filter((match) => !(match[2] ?? '').includes('disabled'))
      .map((match) => match[1]);
    assert.deepStrictEqual(resources.sort(), ['blocked.ts', 'ok.ts'], 'both rows render');
    assert.deepStrictEqual(enabled, ['ok.ts'], 'only previewable rows carry an enabled button');
    // The blocked resource exists in the document but is not previewable.
    assert.ok(html.includes('blocked.ts'));
    assert.ok(!enabled.includes('blocked.ts'));
  });

  it('the panel re-validates every message on receipt before acting', () => {
    const panelSource = fs.readFileSync(
      path.resolve(__dirname, '..', '..', '..', 'src', 'recoveryReportPanel.ts'),
      'utf8',
    );
    assert.ok(panelSource.includes('isReportMessage(raw)'), 'shape guard on receipt');
    assert.ok(panelSource.includes('isSafeResource(resource)'), 'path sanity check');
    assert.ok(
      panelSource.includes('previewableResources(model).includes(resource)'),
      'the resource must be on THIS report own allow-list',
    );
    assert.ok(panelSource.includes('ignored.'), 'rejects are logged and ignored, never resolved');
    assert.ok(
      panelSource.includes('this.panel.webview.html = this.html()'),
      'refresh re-renders the whole document (no innerHTML injection)',
    );
    assert.ok(panelSource.includes('onDidReceiveMessage'), 'messages are wired');
    assert.ok(panelSource.includes("VIEW_TYPE = 'interlock.recoveryReport'"), 'typed webview panel');
    assert.ok(panelSource.includes("PANEL_TITLE = 'Recovery Report'"), 'meaningful panel title');
    assert.ok(!panelSource.includes('innerHTML'), 'no dynamic HTML injection');
    assert.ok(!panelSource.includes('openTextDocument'), 'never falls back to a document');
    assert.ok(!panelSource.includes('resolveApproverIdentity'), 'never asks for an approver');
    assert.ok(!panelSource.includes("command: 'execute'"), 'never executes a recovery');
  });
});
