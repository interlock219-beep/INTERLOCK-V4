/**
 * Recovery Inbox controller tests (trusted flow, headless).
 *
 * These drive the REAL controller - the real discovery, the real plan
 * parsing, the real review scope and the real per-file apply pipeline -
 * with the engine boundary stubbed. What they pin down is the behaviour a
 * user depends on:
 *
 *   * opening, scanning, selecting and previewing never write a file;
 *   * cancelling at the approval writes nothing;
 *   * confirming asks the trusted engine to write exactly the reviewed set;
 *   * a file that changed, lost its baseline or conflicts is never written;
 *   * a failed file is never reported as recovered;
 *   * the inbox invalidates itself after a run, so no stale result can be
 *     acted on twice.
 */

import * as assert from 'assert';
import * as crypto from 'crypto';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import { BridgeCallResult, BridgeInvocation } from '../../src/bridge';
import {
  InboxApproval,
  InboxDeps,
  InboxPanelHandle,
  InboxWatcherHandle,
  RecoveryInboxController,
} from '../../src/inboxController';
import { InboxViewState } from '../../src/recoveryInbox';
import { BaselineStore, BASELINE_FORMAT } from '../../src/state';

const sha = (text: string): string =>
  crypto.createHash('sha256').update(Buffer.from(text, 'utf8')).digest('hex');

interface Harness {
  controller: RecoveryInboxController;
  panel: {
    shown: InboxViewState[];
    updates: unknown[];
    views: InboxViewState[];
    revealed: number;
    disposed: boolean;
  };
  /** The most recent state the panel received (rendered or pushed). */
  lastView(): InboxViewState | null;
  applied: Array<{ resource: string; approvedBy: string }>;
  approvals: { count: number };
  approval: InboxApproval;
  identities: { count: number };
  previews: string[];
  workspace: string;
  storage: BaselineStore;
  cleanup(): void;
}

interface FileSpec {
  name: string;
  baseline: string | null;
  current: string;
  /** Break the stored evidence (hash mismatch) so the file is not eligible. */
  corrupt?: boolean;
}

async function harness(
  files: FileSpec[],
  options: { approval?: InboxApproval; applyFails?: boolean } = {},
): Promise<Harness> {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'il_inbox_ctrl_'));
  const workspace = path.join(root, 'ws');
  const storage = new BaselineStore(path.join(root, 'storage'));
  fs.mkdirSync(workspace, { recursive: true });

  for (const spec of files) {
    const absolute = path.join(workspace, spec.name);
    fs.mkdirSync(path.dirname(absolute), { recursive: true });
    if (spec.baseline !== null) {
      const content = Buffer.from(spec.baseline, 'utf8');
      fs.writeFileSync(absolute, content);
      await storage.save({
        format: BASELINE_FORMAT,
        workspace,
        resource: spec.name,
        captured_at: '2026-10-20T10:00:00.000Z',
        snapshot: {
          hash: spec.corrupt ? sha('something else entirely') : sha(spec.baseline),
          size: content.length,
          content_b64: content.toString('base64'),
        },
      });
    }
    fs.writeFileSync(absolute, spec.current, 'utf8');
  }

  const applied: Array<{ resource: string; approvedBy: string }> = [];
  const previews: string[] = [];
  const panel = {
    shown: [] as InboxViewState[],
    updates: [] as unknown[],
    views: [] as InboxViewState[],
    revealed: 0,
    disposed: false,
  };
  const approvals = { count: 0 };
  const identities = { count: 0 };
  const approval = options.approval ?? 'apply';

  const handle: InboxPanelHandle = {
    show: (view) => {
      panel.shown.push(view);
      panel.views.push(view);
    },
    reveal: () => {
      panel.revealed += 1;
    },
    update: (update) => {
      panel.updates.push(update);
      if (update.view) {
        panel.views.push(update.view);
      }
    },
    isOpen: () => true,
    dispose: () => {
      panel.disposed = true;
    },
  };
  const watcher: InboxWatcherHandle = {
    dispose: () => undefined,
    onDidCreate: () => undefined,
    onDidChange: () => undefined,
    onDidDelete: () => undefined,
  };

  const deps: InboxDeps = {
    workspace: async () => workspace,
    call: async (invocation: BridgeInvocation): Promise<BridgeCallResult> =>
      fakeEngineCall(invocation, workspace),
    storage,
    baselineExclusions: () => [],
    log: { info: () => undefined, warn: () => undefined, error: () => undefined },
    previewFile: async (_workspace, resource) => {
      previews.push(resource);
    },
    openDiff: async () => undefined,
    readOptionalFile: async (absolutePath) => {
      try {
        return await fs.promises.readFile(absolutePath);
      } catch {
        return null;
      }
    },
    resolveApproverIdentity: async () => {
      identities.count += 1;
      return 'Test Approver';
    },
    applyPlanned: async (planned, approvedBy) => {
      applied.push({ resource: planned.resource, approvedBy });
      if (options.applyFails === true) {
        return {
          resource: planned.resource,
          success: false,
          skipped: false,
          verified: false,
          message: 'Recovery ran but verification did NOT confirm a byte-exact restore.',
          details: null,
        };
      }
      return {
        resource: planned.resource,
        success: true,
        skipped: false,
        verified: true,
        message: 'Recovered and verified byte-exact.',
        details: null,
      };
    },
    openFile: async () => undefined,
    verifyRecovery: async () => undefined,
    tempDir: () => path.join(root, 'tmp'),
    note: () => undefined,
    createPanel: () => handle,
    createWatcher: () => watcher,
    confirmRecovery: async () => {
      approvals.count += 1;
      return approval;
    },
    askReference: async () => null,
  };

  const controller = new RecoveryInboxController(deps);
  return {
    controller,
    panel,
    lastView: () => (panel.views.length > 0 ? panel.views[panel.views.length - 1] : null),
    applied,
    approvals,
    approval,
    identities,
    previews,
    workspace,
    storage,
    cleanup: () => fs.rmSync(root, { recursive: true, force: true }),
  };
}

/**
 * The engine boundary: answers a `plan-many` call with the verdicts the
 * engine would give for these files (eligible unless the file has no usable
 * baseline evidence).
 */
async function fakeEngineCall(
  invocation: BridgeInvocation,
  workspace: string,
): Promise<BridgeCallResult> {
  if (invocation.command !== 'plan-many' || !invocation.resourcesFile) {
    return {
      ok: false,
      command: invocation.command,
      kind: 'invalid_invocation',
      exitCode: 2,
      envelope: null,
      result: null,
      message: 'unexpected call',
      hint: '',
      stderrExcerpt: '',
      truncated: false,
      durationMs: 0,
    };
  }
  const manifest = JSON.parse(fs.readFileSync(invocation.resourcesFile, 'utf8')) as {
    entries: Array<{ resource: string; baseline_file: string }>;
  };
  const entries = manifest.entries.map((entry) => {
    const document = JSON.parse(fs.readFileSync(entry.baseline_file, 'utf8')) as {
      snapshot: { hash: string; size: number };
    };
    const currentBytes = fs.readFileSync(path.join(workspace, ...entry.resource.split('/')));
    return {
      resource: entry.resource,
      ok: true,
      summary: {
        would_succeed: true,
        conflict_status: 'no_conflict',
        drift_status: 'no_drift',
        operation: 'restore_content',
        current_exists: true,
        matches_baseline: false,
        baseline: { hash: document.snapshot.hash, size: document.snapshot.size },
        current: { hash: sha(currentBytes.toString('utf8')), size: currentBytes.length },
        diff: { changed: true },
        warnings: [],
      },
    };
  });
  return {
    ok: true,
    command: invocation.command,
    kind: 'ok',
    exitCode: 0,
    envelope: { ok: true, result: { entries } },
    result: { total: entries.length, count: entries.length, entries },
    message: '',
    hint: '',
    stderrExcerpt: '',
    truncated: false,
    durationMs: 1,
  };
}

/** The most recent state the panel received (rendered or pushed). */
function lastViewOf(h: Harness): InboxViewState {
  const view = h.lastView();
  assert.ok(view, 'the panel received a state');
  return view;
}

const CHANGED = { name: 'changed.ts', baseline: 'original\n', current: 'agent edit\n' };
const SECOND = { name: 'nested/second.ts', baseline: 'original two\n', current: 'agent edit two\n' };
const SAME = { name: 'same.ts', baseline: 'untouched\n', current: 'untouched\n' };
const UNPROTECTED = { name: 'brand-new.ts', baseline: null, current: 'new file\n' };
const BROKEN = {
  name: 'broken.ts',
  baseline: 'original three\n',
  current: 'agent edit three\n',
  corrupt: true,
};

describe('Recovery Inbox controller - nothing is written before the approval', () => {
  it('opening and scanning writes nothing', async () => {
    const h = await harness([CHANGED, SAME]);
    try {
      await h.controller.open();
      assert.strictEqual(h.applied.length, 0, 'the scan must not write');
      const view = lastViewOf(h);
      assert.ok(view.counts.examined !== null, 'the scan reports what it examined');
    } finally {
      h.cleanup();
    }
  });

  it('selecting a file writes nothing', async () => {
    const h = await harness([CHANGED]);
    try {
      await h.controller.open();
      h.controller.handle({ type: 'select', add: ['changed.ts'] });
      assert.strictEqual(h.applied.length, 0);
    } finally {
      h.cleanup();
    }
  });

  it('previewing a file writes nothing', async () => {
    const h = await harness([CHANGED]);
    try {
      await h.controller.open();
      await h.controller.handle({ type: 'preview', resource: 'changed.ts' });
      assert.deepStrictEqual(h.previews, ['changed.ts'], 'the preview ran');
      assert.strictEqual(h.applied.length, 0, 'a preview never writes');
    } finally {
      h.cleanup();
    }
  });

  it('cancelling at the approval writes nothing', async () => {
    const h = await harness([CHANGED], { approval: 'cancel' });
    try {
      await h.controller.open();
      h.controller.handle({ type: 'select', add: ['changed.ts'] });
      await h.controller.handle({ type: 'recoverSelected' });
      assert.strictEqual(h.approvals.count, 1, 'the approval was asked for');
      assert.strictEqual(h.applied.length, 0, 'a cancelled approval writes nothing');
      assert.strictEqual(h.identities.count, 0, 'a cancelled approval never asks for an identity');
    } finally {
      h.cleanup();
    }
  });
});

describe('Recovery Inbox controller - the view is updated in place', () => {
  it('renders the document once and pushes the state while scanning', async () => {
    const h = await harness([CHANGED, SAME]);
    try {
      await h.controller.open();
      // The scan must NOT replace the document: a reload swallows the first
      // click, loses the focus and the scroll position.
      assert.strictEqual(
        h.panel.shown.length,
        1,
        'the document is rendered exactly once when the inbox opens',
      );
      assert.ok(
        h.panel.updates.length > 0,
        'the scan state is pushed into the open document instead',
      );
      const view = lastViewOf(h);
      assert.strictEqual(view.scan.status, 'done');
      assert.ok(view.counts.examined !== null, 'the pushed state carries the counts');
      assert.strictEqual(
        h.panel.shown.length,
        1,
        'no further document was rendered while the scan ran',
      );
    } finally {
      h.cleanup();
    }
  });

  it('renders a new document only when the mode changes', async () => {
    const h = await harness([CHANGED, SAME]);
    try {
      await h.controller.open();
      const afterOpen = h.panel.shown.length;
      h.controller.handle({ type: 'select', add: ['changed.ts'] });
      assert.strictEqual(
        h.panel.shown.length,
        afterOpen,
        'a selection never reloads the document',
      );
      await h.controller.handle({ type: 'recoverSelected' });
      assert.strictEqual(
        h.panel.shown.length,
        afterOpen + 1,
        'the review page is a new document (a different page)',
      );
    } finally {
      h.cleanup();
    }
  });

  it('reveals the inbox tab every time it is opened', async () => {
    const h = await harness([CHANGED]);
    try {
      await h.controller.open();
      const revealed = h.panel.revealed;
      assert.ok(revealed > 0, 'the tab is revealed when the inbox opens');
      await h.controller.open();
      assert.ok(
        h.panel.revealed > revealed,
        're-opening the inbox focuses the tab that is already open',
      );
    } finally {
      h.cleanup();
    }
  });
});

describe('Recovery Inbox controller - the confirmed recovery', () => {
  it('recovers exactly the reviewed file through the trusted engine', async () => {
    const h = await harness([CHANGED, SAME]);
    try {
      await h.controller.open();
      h.controller.handle({ type: 'select', add: ['changed.ts'] });
      await h.controller.handle({ type: 'recoverSelected' });
      assert.strictEqual(h.approvals.count, 1, 'the user had to approve');
      assert.strictEqual(h.identities.count, 1, 'the real approver identity was resolved');
      assert.deepStrictEqual(
        h.applied.map((entry) => entry.resource),
        ['changed.ts'],
        'only the reviewed file was written',
      );
      assert.strictEqual(h.applied[0].approvedBy, 'Test Approver');
    } finally {
      h.cleanup();
    }
  });

  it('never writes a file without usable evidence, and never a file that did not change', async () => {
    const h = await harness([CHANGED, SAME, UNPROTECTED, BROKEN]);
    try {
      await h.controller.open();
      h.controller.handle({ type: 'select', add: ['changed.ts', 'same.ts', 'brand-new.ts', 'broken.ts'] });
      await h.controller.handle({ type: 'recoverSelected' });
      // Several files: the review is shown first, with every exclusion and
      // its reason, and nothing is written before the user confirms.
      const view = lastViewOf(h);
      assert.strictEqual(view.mode, 'review');
      assert.deepStrictEqual(
        view.review?.included.map((entry) => entry.resource),
        ['changed.ts'],
      );
      assert.strictEqual(view.review?.excluded.length, 3);
      assert.ok(
        view.review?.excluded.some((entry) =>
          entry.reason.includes('do not match the recorded baseline hash'),
        ),
        'the file with broken evidence explains itself',
      );
      assert.strictEqual(h.applied.length, 0, 'the review alone writes nothing');

      await h.controller.handle({ type: 'confirm' });
      assert.deepStrictEqual(
        h.applied.map((entry) => entry.resource),
        ['changed.ts'],
        'only the changed file with verified evidence is recoverable',
      );
    } finally {
      h.cleanup();
    }
  });

  it('recover all touches only the changed files with verified evidence', async () => {
    const h = await harness([CHANGED, SECOND, SAME, UNPROTECTED, BROKEN]);
    try {
      await h.controller.open();
      await h.controller.handle({ type: 'recoverAll' });
      const review = lastViewOf(h);
      assert.strictEqual(review.mode, 'review');
      assert.strictEqual(review.review?.scope, 'all');
      assert.deepStrictEqual(
        review.review?.included.map((entry) => entry.resource).sort(),
        ['changed.ts', 'nested/second.ts'],
        'the bulk scope is exactly the eligible changed files',
      );
      assert.strictEqual(h.applied.length, 0, 'the scope is shown before anything is written');

      await h.controller.handle({ type: 'confirm' });
      assert.strictEqual(h.approvals.count, 1, 'the bulk run was confirmed explicitly');
      assert.deepStrictEqual(
        h.applied.map((entry) => entry.resource).sort(),
        ['changed.ts', 'nested/second.ts'],
        'the bulk run writes exactly the confirmed scope',
      );
    } finally {
      h.cleanup();
    }
  });

  it('reports a failed file as failed, never as recovered', async () => {
    const h = await harness([CHANGED], { applyFails: true });
    try {
      await h.controller.open();
      h.controller.handle({ type: 'select', add: ['changed.ts'] });
      h.controller.handle({ type: 'recoverSelected' });
      await new Promise((resolve) => setTimeout(resolve, 100));
      const view = lastViewOf(h);
      assert.strictEqual(view.mode, 'results');
      const results = view.results;
      assert.ok(results);
      assert.strictEqual(results.counts.recovered, 0, 'an unverified run is not a recovery');
      assert.strictEqual(results.counts.attention, 1);
      assert.strictEqual(results.entries[0].outcome, 'attention');
    } finally {
      h.cleanup();
    }
  });

  it('invalidates the scan after a run so no stale result can be applied twice', async () => {
    const h = await harness([CHANGED]);
    try {
      await h.controller.open();
      h.controller.handle({ type: 'select', add: ['changed.ts'] });
      h.controller.handle({ type: 'recoverSelected' });
      await new Promise((resolve) => setTimeout(resolve, 100));
      const view = lastViewOf(h);
      assert.strictEqual(view.recoverSelected.enabled, false, 'the stale scan cannot recover again');
      assert.ok(view.scan.stale, 'the scan is marked stale after a write');
    } finally {
      h.cleanup();
    }
  });
});
