/**
 * Recovery-preview correctness tests.
 *
 * The native side-by-side diff is only honest if its right-hand side is the
 * EXACT content the approved recovery would write. These tests pin down how
 * those contents are obtained (stored baseline snapshot, hash-verified), when
 * they must be refused (truncation, binary, tampered, missing), how a stale
 * preview is detected, and - because the command handlers need a real VS Code
 * host - a source-level check that the preview path can never prompt for an
 * approver or write a file.
 */

import * as assert from 'assert';
import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';

import { readPlanSummary, buildPlanMarkdown } from '../../src/recoveryPlanReport';
import {
  describePlan,
  diffTitle,
  isApplicable,
  planFromEngineResult,
  PlannedRecovery,
  proposedFromSnapshot,
  sha256Hex,
  staleAgainstCurrent,
  summarizePlans,
} from '../../src/recoveryPlan';

const sha = (input: string | Buffer): string =>
  crypto.createHash('sha256').update(input).digest('hex');

/** A stored baseline snapshot holding exactly these bytes. */
function snapshotFor(
  bytes: Buffer,
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    hash: sha(bytes),
    exists: true,
    type: 'file',
    size: bytes.length,
    binary: false,
    truncated: false,
    content: bytes.toString('utf8'),
    content_b64: bytes.toString('base64'),
    ...overrides,
  };
}

function plannedFor(overrides: Partial<PlannedRecovery> = {}): PlannedRecovery {
  const bytes = Buffer.from('baseline bytes\n', 'utf8');
  return {
    workspace: 'C:/ws',
    resource: 'index.html',
    absolutePath: 'C:/ws/index.html',
    operation: 'restore_content',
    wouldSucceed: true,
    conflict: 'no_conflict',
    drift: 'no_drift',
    baselineHash: sha(bytes),
    currentHash: sha(Buffer.from('changed bytes\n', 'utf8')),
    currentExists: true,
    baselineCapturedAt: '2026-10-20T09:00:00Z',
    at: '2026-10-20T09:05:00Z',
    proposed: {
      kind: 'text',
      text: 'baseline bytes\n',
      bytes,
      hash: sha(bytes),
      limitation: null,
      code: null,
    },
    diffable: true,
    evidence: {
      aclAvailable: true,
      aclError: null,
      snapshotSize: bytes.length,
      snapshotHash: sha(bytes),
      capturedAt: '2026-10-20T09:00:00Z',
    },
    evidenceFile: 'C:/storage/index.html.evidence.json',
    report: {},
    ...overrides,
  };
}

describe('proposed recovery contents (exact bytes for the diff)', () => {
  it('decodes the stored baseline bytes and verifies them against the recorded hash', () => {
    const bytes = Buffer.from('line one\r\nline two without trailing newline', 'utf8');
    const proposed = proposedFromSnapshot(snapshotFor(bytes));
    assert.strictEqual(proposed.kind, 'text');
    assert.strictEqual(proposed.hash, sha(bytes));
    assert.deepStrictEqual(proposed.bytes, bytes);
    // Exact text, CRLF preserved, only the UTF-8 BOM (if any) removed.
    assert.strictEqual(proposed.text, bytes.toString('utf8'));
    assert.strictEqual(proposed.limitation, null);
  });

  it('keeps every byte except a leading BOM, which VS Code strips anyway', () => {
    const bytes = Buffer.from('\uFEFFconst x = 1;\r\n', 'utf8');
    const proposed = proposedFromSnapshot(snapshotFor(bytes));
    assert.strictEqual(proposed.kind, 'text');
    assert.strictEqual(proposed.text, 'const x = 1;\r\n');
    assert.deepStrictEqual(proposed.bytes, bytes); // bytes kept for hashing
  });

  it('falls back to the decoded text content when no base64 is stored', () => {
    const text = 'only decoded text\n';
    const bytes = Buffer.from(text, 'utf8');
    const proposed = proposedFromSnapshot({ hash: sha(bytes), content: text });
    assert.strictEqual(proposed.kind, 'text');
    assert.strictEqual(proposed.text, text);
  });

  it('refuses contents whose hash disagrees with the recorded baseline hash', () => {
    const bytes = Buffer.from('what the snapshot claims\n', 'utf8');
    const proposed = proposedFromSnapshot(
      snapshotFor(bytes, { hash: sha(Buffer.from('something else\n', 'utf8')) }),
    );
    assert.strictEqual(proposed.kind, 'unavailable');
    assert.strictEqual(proposed.text, null);
    assert.strictEqual(proposed.bytes, null);
    assert.match(proposed.limitation ?? '', /do not match the recorded baseline hash/);
  });

  it('refuses a truncated snapshot instead of showing a content-incomplete diff', () => {
    const bytes = Buffer.from('partial content', 'utf8');
    const proposed = proposedFromSnapshot(snapshotFor(bytes, { truncated: true }));
    assert.strictEqual(proposed.kind, 'unavailable');
    assert.strictEqual(proposed.text, null);
    assert.match(proposed.limitation ?? '', /truncated/);
  });

  it('reports a binary file as binary, with its exact bytes and verified hash', () => {
    const bytes = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x00, 0x01, 0x02, 0xff]);
    const proposed = proposedFromSnapshot(snapshotFor(bytes, { binary: true, content: null }));
    assert.strictEqual(proposed.kind, 'binary');
    assert.strictEqual(proposed.text, null); // never rendered as fake text
    assert.deepStrictEqual(proposed.bytes, bytes);
    assert.strictEqual(proposed.hash, sha(bytes));
    assert.match(proposed.limitation ?? '', /binary/);
  });

  it('refuses snapshots without contents, without a hash, or unreadable', () => {
    assert.strictEqual(proposedFromSnapshot(null).kind, 'unavailable');
    assert.strictEqual(proposedFromSnapshot('nonsense').kind, 'unavailable');
    assert.strictEqual(proposedFromSnapshot({}).kind, 'unavailable');
    assert.match(
      proposedFromSnapshot({ hash: sha(Buffer.from('x')) }).limitation ?? '',
      /no file contents/,
    );
    assert.match(
      proposedFromSnapshot({ content: 'x' }).limitation ?? '',
      /no content hash/,
    );
  });
});

describe('plan and diff agreement', () => {
  const summary = {
    wouldSucceed: true,
    conflict: 'no_conflict',
    drift: 'no_drift',
    operation: 'restore_content',
    baselineHash: '',
    currentHash: sha(Buffer.from('current')),
    currentExists: true,
    baselineCapturedAt: '2026-10-20T09:00:00Z',
  };

  it('marks a text plan diffable and carries the engine verdicts through', () => {
    const bytes = Buffer.from('restored exactly\n', 'utf8');
    const planned = planFromEngineResult({
      workspace: 'C:/ws',
      resource: 'index.html',
      absolutePath: 'C:/ws/index.html',
      evidenceFile: 'evidence.json',
      summary: { ...summary, baselineHash: sha(bytes) },
      baselineSnapshot: snapshotFor(bytes),
      report: { would_succeed: true },
      at: '2026-10-20T09:05:00Z',
    });
    assert.strictEqual(planned.diffable, true);
    assert.strictEqual(planned.proposed.text, 'restored exactly\n');
    assert.strictEqual(planned.baselineHash, sha(bytes));
    assert.strictEqual(planned.proposed.hash, sha(bytes));
    assert.strictEqual(planned.conflict, 'no_conflict');
    assert.strictEqual(planned.currentExists, true);
  });

  it('refuses a diff when the stored contents belong to a different baseline', () => {
    const stored = Buffer.from('contents of baseline A\n', 'utf8');
    const planned = planFromEngineResult({
      workspace: 'C:/ws',
      resource: 'index.html',
      absolutePath: 'C:/ws/index.html',
      evidenceFile: 'evidence.json',
      summary: { ...summary, baselineHash: sha(Buffer.from('baseline B\n', 'utf8')) },
      baselineSnapshot: snapshotFor(stored),
      report: {},
    });
    assert.strictEqual(planned.diffable, false);
    assert.strictEqual(planned.proposed.text, null);
    assert.match(planned.proposed.limitation ?? '', /do not belong to the baseline/);
  });

  it('never marks binary or truncated plans diffable', () => {
    const bytes = Buffer.from([1, 2, 3, 4]);
    const binary = planFromEngineResult({
      workspace: 'C:/ws',
      resource: 'logo.png',
      absolutePath: 'C:/ws/logo.png',
      evidenceFile: 'evidence.json',
      summary: { ...summary, baselineHash: sha(bytes) },
      baselineSnapshot: snapshotFor(bytes, { binary: true, content: null }),
      report: {},
    });
    assert.strictEqual(binary.diffable, false);
    assert.strictEqual(binary.proposed.kind, 'binary');

    const text = Buffer.from('big file content', 'utf8');
    const truncated = planFromEngineResult({
      workspace: 'C:/ws',
      resource: 'big.txt',
      absolutePath: 'C:/ws/big.txt',
      evidenceFile: 'evidence.json',
      summary: { ...summary, baselineHash: sha(text) },
      baselineSnapshot: snapshotFor(text, { truncated: true }),
      report: {},
    });
    assert.strictEqual(truncated.diffable, false);
  });
});

describe('stale preview detection', () => {
  it('accepts a file that still matches what the preview observed', () => {
    const planned = plannedFor();
    const current = Buffer.from('changed bytes\n', 'utf8'); // matches currentHash
    assert.deepStrictEqual(staleAgainstCurrent(planned, current), { stale: false, reason: null });
  });

  it('rejects the preview once the file content changed', () => {
    const staleness = staleAgainstCurrent(plannedFor(), Buffer.from('edited again\n', 'utf8'));
    assert.strictEqual(staleness.stale, true);
    assert.match(staleness.reason ?? '', /changed after the preview/);
  });

  it('rejects the preview when the file was deleted after previewing', () => {
    const staleness = staleAgainstCurrent(plannedFor(), null);
    assert.strictEqual(staleness.stale, true);
    assert.match(staleness.reason ?? '', /no longer exists/);
  });

  it('rejects the preview when a missing file appeared after previewing', () => {
    const planned = plannedFor({ currentExists: false, currentHash: null });
    const staleness = staleAgainstCurrent(planned, Buffer.from('appeared\n', 'utf8'));
    assert.strictEqual(staleness.stale, true);
    assert.match(staleness.reason ?? '', /appeared on disk/);
  });

  it('treats a still-missing file as unchanged', () => {
    const planned = plannedFor({ currentExists: false, currentHash: null });
    assert.deepStrictEqual(staleAgainstCurrent(planned, null), { stale: false, reason: null });
  });
});

describe('applicability and summaries', () => {
  it('only accepts plans the engine declared successful, conflict- and drift-free', () => {
    assert.strictEqual(isApplicable(plannedFor()), true);
    assert.strictEqual(isApplicable(plannedFor({ wouldSucceed: false })), false);
    assert.strictEqual(isApplicable(plannedFor({ conflict: 'conflict_detected' })), false);
    assert.strictEqual(isApplicable(plannedFor({ drift: 'drift_detected' })), false);
  });

  it('names both diff sides in the editor title', () => {
    assert.strictEqual(
      diffTitle('index.html'),
      'Current: index.html  ⇄  Proposed Recovery: index.html',
    );
  });

  it('lists every planned file with its operation and hashes', () => {
    const plans = [
      plannedFor({ resource: 'index.html' }),
      plannedFor({ resource: 'assets/app.js', operation: 'restore_deleted_file' }),
    ];
    const summary = summarizePlans(plans);
    assert.ok(summary.includes('2 files'));
    assert.ok(summary.includes('index.html'));
    assert.ok(summary.includes('assets/app.js'));
    assert.ok(summary.includes('restore_deleted_file'));
    assert.strictEqual(summary.split('•').length - 1, 2); // one line per file
    assert.strictEqual(describePlan(plans[1]).startsWith('assets/app.js'), true);
    assert.strictEqual(sha256Hex(Buffer.from('x')), sha(Buffer.from('x')));
  });
});

describe('plan report (read-only audit trail)', () => {
  const plan: Record<string, unknown> = {
    would_succeed: true,
    conflict_status: 'no_conflict',
    drift_status: 'no_drift',
    reversibility: 'reversible',
    matches_baseline: false,
    operation: 'restore_content',
    current_exists: true,
    baseline: { hash: sha(Buffer.from('baseline')) },
    current: { hash: sha(Buffer.from('current')) },
    baseline_captured_at: '2026-10-20T09:00:00Z',
    evidence_captured_at: '2026-10-20T09:05:00Z',
    diff: { changed: true, structural: { index: { change: 'modified' } } },
    warnings: ['current state differs from the captured baseline'],
  };

  it('reads every verdict field the summary depends on', () => {
    const summary = readPlanSummary(plan);
    assert.strictEqual(summary.wouldSucceed, true);
    assert.strictEqual(summary.conflict, 'no_conflict');
    assert.strictEqual(summary.drift, 'no_drift');
    assert.strictEqual(summary.changed, true);
    assert.strictEqual(summary.operation, 'restore_content');
    assert.strictEqual(summary.currentExists, true);
    assert.strictEqual(summary.baselineHash, sha(Buffer.from('baseline')));
    assert.strictEqual(summary.baselineCapturedAt, '2026-10-20T09:00:00Z');
  });

  it('renders the verdicts, hashes and next steps - and never file contents', () => {
    const markdown = buildPlanMarkdown('index.html', 'C:/ws', {
      ...plan,
      content: 'SECRET FILE CONTENT',
      content_b64: 'U0VDUkVU',
    });
    assert.ok(markdown.includes('# Interlock recovery plan preview'));
    assert.ok(markdown.includes('## Engine verdict'));
    assert.ok(markdown.includes('## State comparison'));
    assert.ok(markdown.includes('## What happens next'));
    assert.ok(markdown.includes('No file was changed'));
    assert.ok(markdown.includes('`no_conflict`'));
    assert.ok(markdown.includes('side-by-side diff'));
    assert.ok(markdown.includes('interlock.approverIdentity'));
    assert.ok(!markdown.includes('SECRET FILE CONTENT'));
    assert.ok(!markdown.includes('U0VDUkVU'));
  });

  it('reports a missing current file honestly', () => {
    const markdown = buildPlanMarkdown('gone.txt', 'C:/ws', {
      ...plan,
      current_exists: false,
      current: {},
    });
    assert.ok(markdown.includes('Current file exists: no'));
  });
});

/**
 * The command handlers need a real VS Code host, so the promises the review
 * flow makes are pinned here at the source level: preview never prompts and
 * never writes, apply always confirms, always resolves an identity, and always
 * re-checks staleness first.
 */
describe('recovery command flow (source-level guarantees)', () => {
  const source = fs.readFileSync(
    path.resolve(__dirname, '..', '..', '..', 'src', 'commands.ts'),
    'utf8',
  );

  const methodBody = (signature: string): string => {
    const start = source.indexOf(signature);
    assert.ok(start >= 0, `missing ${signature}`);
    // Skip past the parameter list (which may contain its own braces) before
    // brace-matching the body.
    const signatureEnd = source.indexOf('): ', start);
    assert.ok(signatureEnd > start, `unparsable signature ${signature}`);
    const open = source.indexOf('{', signatureEnd);
    let depth = 0;
    for (let i = open; i < source.length; i += 1) {
      const ch = source[i];
      if (ch === '{') {
        depth += 1;
      } else if (ch === '}') {
        depth -= 1;
        if (depth === 0) {
          return source.slice(start, i + 1);
        }
      }
    }
    throw new Error(`unbalanced braces for ${signature}`);
  };

  it('Preview Recovery opens diffs and never prompts or executes anything', () => {
    const preview = methodBody('async previewRecoveryPlan(): Promise<void> {');
    assert.ok(preview.includes('this.runPreview({ openDiffs: true })'));
    assert.ok(!preview.includes('showInputBox'), 'preview must not ask for an approver');
    assert.ok(!preview.includes("command: 'execute'"), 'preview must never execute recovery');
    assert.ok(!preview.includes('resolveApproverIdentity'));
  });

  it('the shared preview pipeline only reads: plan, decode, diff', () => {
    const runPreview = methodBody('private async runPreview(options: { openDiffs: boolean })');
    assert.ok(!runPreview.includes('showInputBox'));
    assert.ok(!runPreview.includes("command: 'execute'"));
    assert.ok(runPreview.includes('buildPlannedRecovery'));
    assert.ok(runPreview.includes('openRecoveryDiff'));
  });

  it('the diff side comes from the verified baseline via a virtual document', () => {
    const openDiff = methodBody('private async openRecoveryDiff(planned: PlannedRecovery)');
    assert.ok(openDiff.includes("'vscode.diff'"), 'the built-in diff editor is used');
    assert.ok(openDiff.includes('this.recoveryDocs.propose('));
    assert.ok(openDiff.includes('diffTitle('));
    assert.ok(!openDiff.includes('writeFile'), 'preview must never write a workspace file');
    assert.ok(!openDiff.includes('WorkspaceEdit'));
  });

  it('Apply Recovery confirms, keeps identity mandatory, and re-checks staleness', () => {
    const execute = methodBody('async executeRecovery(): Promise<void> {');
    assert.ok(execute.includes('modal: true'), 'approval must be an explicit modal confirmation');
    assert.ok(execute.includes('summarizePlans(applicable)'), 'confirmation lists the files');
    assert.ok(execute.includes('resolveApproverIdentity()'), 'identity is mandatory');
    assert.ok(execute.includes('staleAgainstCurrent('), 'stale previews are rejected');
    assert.ok(execute.includes('isApplicable'), 'engine verdicts gate the apply');
    assert.ok(execute.includes('buildPlannedRecovery(workspaceRoot, planned.resource)'));
  });

  it('the approver identity is resolved from trusted sources before prompting', () => {
    const identity = methodBody('private async resolveApproverIdentity()');
    assert.ok(identity.includes("settings.approverIdentity"), 'setting first');
    assert.ok(identity.includes('this.sessionApprover'), 'asked once per session');
    assert.ok(identity.includes('gitUserIdentity()'), 'git identity as a real provider');
    assert.ok(identity.includes('showInputBox'), 'prompt only as a last resort');
    const git = methodBody('private async gitUserIdentity()');
    assert.ok(git.includes("'vscode.git'"));
  });

  // ---- Recovery Report panel wiring (View Recovery Plan -> webview panel) ----

  it('View Recovery Plan opens the report panel, never a markdown document', () => {
    const view = methodBody('async viewRecoveryPlan(): Promise<void> {');
    assert.ok(view.includes('this.showRecoveryReport('), 'renders the report panel');
    assert.ok(!view.includes('openTextDocument'), 'no untitled document fallback');
    assert.ok(!view.includes('buildPlanMarkdown'), 'no raw markdown dump');
    assert.ok(!view.includes('showTextDocument'), 'no text-document fallback');
    const show = methodBody('private showRecoveryReport(plans: PlannedRecovery[]): void {');
    assert.ok(show.includes('buildRecoveryReport('), 'the pure report model is used');
    assert.ok(show.includes('this.reportPanel().show(model)'), 'the webview panel renders it');
    assert.ok(!show.includes('openTextDocument'));
    const panel = methodBody('private reportPanel(): RecoveryReportPanel {');
    assert.ok(panel.includes('new RecoveryReportPanel('), 'one reusable panel instance');
    assert.ok(panel.includes('refresh: () => this.refreshRecoveryReport()'), 'Refresh wired');
    assert.ok(panel.includes('preview: (resource) => this.previewReportFile(resource)'), 'Preview wired');
    assert.ok(panel.includes('this.disposables.push'), 'the panel is disposed with the host');
  });

  it('Refresh Report re-observes evidence through the validated per-file pipeline', () => {
    const refresh = methodBody('private async refreshRecoveryReport(): Promise<void> {');
    assert.ok(refresh.includes('buildPlannedRecovery(workspaceRoot, planned.resource)'),
      're-plans every current file through the same engine path');
    assert.ok(refresh.includes('this.rememberPreviews(workspaceRoot, refreshed)'),
      'fresh evidence replaces the remembered plans');
    assert.ok(refresh.includes('this.showRecoveryReport(refreshed)'),
      'the panel is rebuilt from the fresh evidence');
    assert.ok(refresh.includes('could not be re-observed'),
      'a partial refresh keeps the old report and says why');
    assert.ok(refresh.includes('return;'), 'failed re-observation never silently drops rows');
    assert.ok(!refresh.includes('runPreview'), 'refresh does not re-prompt target selection');
    assert.ok(!refresh.includes("command: 'execute'"));
  });

  it('report preview re-checks the remembered plans and only opens the diff', () => {
    const preview = methodBody('private async previewReportFile(resource: string): Promise<void> {');
    assert.ok(preview.includes('this.previewed.find('), 'allow-listed against remembered plans');
    assert.ok(preview.includes('this.openRecoveryDiff(planned)'), 'the existing native diff only');
    assert.ok(preview.includes('showWarningMessage'), 'an unknown resource is refused and explained');
    assert.ok(!preview.includes('writeFile'), 'the report never writes a workspace file');
    assert.ok(!preview.includes("command: 'execute'"), 'the report never executes recovery');
    assert.ok(!preview.includes('resolveApproverIdentity'), 'preview never asks for an approver');
  });

  it('the whole report path stays read-only: no approver, no execution', () => {
    const combined = [
      methodBody('async viewRecoveryPlan(): Promise<void> {'),
      methodBody('private showRecoveryReport(plans: PlannedRecovery[]): void {'),
      methodBody('private async refreshRecoveryReport(): Promise<void> {'),
      methodBody('private async previewReportFile(resource: string): Promise<void> {'),
    ].join('\n');
    assert.ok(!combined.includes('showInputBox'), 'no identity prompt anywhere in the report flow');
    assert.ok(!combined.includes('resolveApproverIdentity'));
    assert.ok(!combined.includes("command: 'execute'"), 'no execution channel');
    assert.ok(!combined.includes('applyPlannedRecovery'), 'no apply path');
    assert.ok(!combined.includes('executeRecovery'), 'no recovery execution');
  });

  // ---- Approver identity: timing, wording and separation (product scope) ----

  it('only Apply Recovery ever resolves an approver identity', () => {
    const previewSide = [
      methodBody('async previewRecoveryPlan(): Promise<void> {'),
      methodBody('async viewRecoveryPlan(): Promise<void> {'),
      methodBody('private async refreshRecoveryReport(): Promise<void> {'),
      methodBody('private async runPreview(options: { openDiffs: boolean })'),
      methodBody('private async openRecoveryDiff(planned: PlannedRecovery)'),
    ].join('\n');
    assert.ok(
      !previewSide.includes('resolveApproverIdentity'),
      'preview/view/refresh/diff never resolve an identity',
    );
    assert.ok(!previewSide.includes('showInputBox'), 'no input box anywhere on the preview side');
    assert.ok(
      !previewSide.includes('command: "execute"') && !previewSide.includes("command: 'execute'"),
      'the preview side never executes recovery',
    );
    const execute = methodBody('async executeRecovery(): Promise<void> {');
    assert.ok(execute.includes('resolveApproverIdentity()'), 'Apply resolves identity');
  });

  it('identity resolution order: setting -> session -> git -> dedicated prompt, prompt last', () => {
    const identity = methodBody('private async resolveApproverIdentity()');
    const settingIdx = identity.indexOf('settings.approverIdentity');
    const sessionIdx = identity.indexOf('if (this.sessionApprover)');
    const gitIdx = identity.indexOf('gitUserIdentity()');
    const promptIdx = identity.indexOf('showInputBox');
    assert.ok(settingIdx >= 0, 'configured identity is considered');
    assert.ok(identity.includes('return settings.approverIdentity'), 'configured identity short-circuits');
    assert.ok(sessionIdx > settingIdx, 'session identity is reused before any prompt');
    assert.ok(gitIdx > sessionIdx, 'git identity comes after the session value');
    assert.ok(promptIdx > gitIdx, 'the prompt is the last resort only');
    assert.ok(identity.includes('return this.sessionApprover'), 'session value is returned without re-asking');
  });

  it('the approver prompt is dedicated, clearly labelled, and free of any ticket field', () => {
    const identity = methodBody('private async resolveApproverIdentity()');
    assert.ok(identity.includes("title: 'Confirm Recovery Approver'"), 'clear approver title');
    assert.ok(
      identity.includes("placeHolder: 'Enter your name or approved identity'"),
      'placeholder asks only for an identity',
    );
    assert.ok(
      /identity is recorded in the recovery audit record/i.test(identity),
      'briefly explains the audit requirement',
    );
    // The approver field must never merge or invite a change/ticket reference.
    assert.ok(!identity.includes('change/ticket'), 'no ticket wording in the approver prompt');
    assert.ok(!identity.includes('CHG-'), 'no ticket format in the approver prompt');
  });

  it('the change/ticket reference is optional, separate, and only asked on explicit request', () => {
    const execute = methodBody('async executeRecovery(): Promise<void> {');
    assert.ok(
      execute.includes('Apply with change/ticket reference'),
      'an explicit opt-in button offers the ticket reference',
    );
    assert.ok(
      execute.includes('if (confirmation === withReferenceLabel)'),
      'the ticket box opens only when that button was chosen',
    );
    assert.ok(execute.includes('Optional change/ticket reference'), 'the ticket prompt is clearly optional');
    assert.ok(execute.includes("placeHolder: 'CHG-12345'"), 'a ticket-style placeholder, not an identity');
    assert.ok(execute.includes('cancelled at the reference prompt'), 'cancelling the ticket box aborts');
    // Two distinct showInputBox calls in two distinct methods: Apply owns the
    // reference box, resolveApproverIdentity owns the approver box.
    const executeBoxes = execute.split('showInputBox').length - 1;
    assert.ok(executeBoxes === 1, 'Apply\'s only input box is the optional ticket reference');
    const identity = methodBody('private async resolveApproverIdentity()');
    assert.ok(identity.split('showInputBox').length - 1 === 1, 'the approver prompt is its own input');
    assert.ok(!identity.includes('CHG-'), 'the identity is never a ticket reference');
  });

  it('cancelling approval or identity aborts recovery; empty identities are impossible', () => {
    const execute = methodBody('async executeRecovery(): Promise<void> {');
    assert.ok(execute.includes('cancelled at the approval dialog'), 'approval cancel aborts');
    assert.ok(
      execute.includes('cancelled without an approver identity'),
      'identity cancel aborts - recovery never continues',
    );
    assert.ok(!execute.includes('fallback') && !execute.includes('fabricat'), 'no invented identity');
    const identity = methodBody('private async resolveApproverIdentity()');
    assert.ok(identity.includes('value.trim().length > 0'), 'empty input is rejected in the prompt');
    assert.ok(identity.includes('if (!typed || !typed.trim())'), 'an empty result resolves to null');
    assert.ok(identity.includes('return null'), 'nothing is ever invented on cancel');
  });
});
