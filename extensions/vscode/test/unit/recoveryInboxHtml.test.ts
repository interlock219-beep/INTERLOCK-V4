/**
 * Recovery Inbox renderer tests (pure).
 *
 * The Inbox renders a workspace-controlled file list into a webview, so the
 * renderer has to hold the line on the security contract (nonce'd CSP, no
 * remote assets, escaped values, no innerHTML/eval in the script) and on the
 * honesty contract (Unknown instead of a made-up zero, no hashes in the main
 * view, no "recoverable" claim without verified evidence).
 *
 * The client-side core (filter / sort / search / paginate / group) is
 * evaluated headlessly here, so the behaviour the user sees is unit-tested
 * instead of only being asserted in the source text.
 */

import * as assert from 'assert';

import {
  InboxClientRow,
  InboxCounts,
  InboxState,
  InboxViewState,
  buildViewState,
} from '../../src/recoveryInbox';
import {
  INBOX_SCRIPT,
  isInboxMessage,
  renderInboxHtml,
} from '../../src/recoveryInboxHtml';

const NOW = '2026-10-20T12:00:00.000Z';

interface ScriptApi {
  filterRows(rows: InboxClientRow[], filterId: string, query: string): InboxClientRow[];
  sortRows(rows: InboxClientRow[], sortId: string): InboxClientRow[];
  pageSlice<T>(rows: T[], page: number, pageSize: number): { rows: T[]; page: number; pages: number };
  groupRows(rows: InboxClientRow[]): Array<{ dir: string; rows: InboxClientRow[] }>;
  visibleRows(state: {
    rows: InboxClientRow[];
    filter: string;
    query: string;
    sort: string;
    page: number;
    pageSize: number;
  }): { rows: InboxClientRow[]; page: number; pages: number };
  selectionText(rows: InboxClientRow[], selection: Record<string, boolean>): string;
}

/** Evaluate the shipped script headlessly: without a DOM it returns its core. */
const scriptApi: ScriptApi = new Function(`return ${INBOX_SCRIPT}`)() as ScriptApi;

function clientRow(overrides: Partial<InboxClientRow> = {}): InboxClientRow {
  return {
    resource: 'src/app.ts',
    name: 'app.ts',
    dir: 'src',
    kind: 'protected',
    status: 'modified',
    statusLabel: 'Modified',
    statusTone: 'warn',
    evidenceLabel: 'Verified',
    evidenceTone: 'ok',
    eligibility: 'eligible',
    eligibilityLabel: 'Recoverable',
    eligibilityTone: 'ok',
    reason: 'Changed after the baseline was captured.',
    details: null,
    previewable: true,
    previewNote: null,
    capturedAt: NOW,
    flags: {
      changed: true,
      unprotected: false,
      modified: true,
      deleted: false,
      unchanged: false,
      attention: false,
      recoverable: true,
    },
    rankStatus: 0,
    rankEligibility: 0,
    ...overrides,
  };
}

function viewWith(rows: InboxClientRow[], overrides: Partial<InboxViewState> = {}): InboxViewState {
  const state = new InboxState('C:/workspace', Date.parse(NOW));
  state.beginScan(Date.parse(NOW));
  state.finishScan('done', null, Date.parse(NOW));
  const view = buildViewState(state, { workspaceName: 'workspace' });
  return {
    ...view,
    rows,
    counts: {
      examined: rows.length,
      changed: rows.length,
      verifiedEvidence: rows.length,
      recoverableModified: rows.length,
      recoverableDeleted: 0,
      attention: 0,
      noBaseline: 0,
    } satisfies InboxCounts,
    ...overrides,
  };
}

describe('Recovery Inbox renderer - security contract', () => {
  const html = renderInboxHtml(viewWith([clientRow()]), { nonce: 'n0nce' });

  it('ships a restrictive CSP with a nonce and no unsafe directives', () => {
    assert.ok(html.includes("default-src 'none'"));
    assert.ok(html.includes(`style-src 'nonce-n0nce'`));
    assert.ok(html.includes(`script-src 'nonce-n0nce'`));
    assert.ok(!html.includes("'unsafe-inline'"));
    assert.ok(!html.includes("'unsafe-eval'"));
  });

  it('uses the same nonce on <style> and <script>', () => {
    assert.ok(html.includes('<style nonce="n0nce">'));
    assert.ok(html.includes('<script nonce="n0nce">'));
  });

  it('loads no external images, fonts, stylesheets or scripts', () => {
    assert.ok(!/<img\b/i.test(html));
    assert.ok(!/<link\b/i.test(html));
    assert.ok(!/https?:\/\//i.test(html));
  });

  it('never writes innerHTML, evaluates strings or talks to the network', () => {
    assert.ok(!INBOX_SCRIPT.includes('innerHTML'));
    assert.ok(!INBOX_SCRIPT.includes('outerHTML'));
    assert.ok(!INBOX_SCRIPT.includes('eval('));
    assert.ok(!INBOX_SCRIPT.includes('new Function'));
    assert.ok(!INBOX_SCRIPT.includes('fetch('));
    assert.ok(!INBOX_SCRIPT.includes('XMLHttpRequest'));
    assert.ok(!INBOX_SCRIPT.includes('document.write'));
  });

  it('escapes hostile file names in the payload and never inlines them as markup', () => {
    const hostile = clientRow({
      resource: '</script><img src=x onerror=alert(1)>.ts',
      name: '<img src=x onerror=alert(1)>.ts',
    });
    const rendered = renderInboxHtml(viewWith([hostile]), { nonce: 'n' });
    assert.ok(!rendered.includes('<img src=x'), 'no markup may be injected through a file name');
    assert.ok(rendered.includes('\\u003c/script'), 'the payload escapes the closing script tag');
  });

  it('escapes dynamic text in the server-rendered parts', () => {
    const rendered = renderInboxHtml(
      viewWith([clientRow()], {
        notice: '<b>not bold</b>',
        workspaceName: '<script>x</script>',
      }),
      { nonce: 'n' },
    );
    assert.ok(!rendered.includes('<b>not bold</b>'));
    assert.ok(rendered.includes('&lt;b&gt;not bold&lt;/b&gt;'));
    assert.ok(!rendered.includes('<script>x</script>'));
  });
});

describe('Recovery Inbox renderer - honest view', () => {
  it('shows Unknown instead of a made-up zero for underivable counts', () => {
    const view = viewWith([clientRow()], {
      counts: {
        examined: null,
        changed: 3,
        verifiedEvidence: null,
        recoverableModified: null,
        recoverableDeleted: null,
        attention: null,
        noBaseline: null,
      },
    });
    const html = renderInboxHtml(view, { nonce: 'n' });
    assert.ok(html.includes('>Unknown<'));
    assert.ok(html.includes('>3<'));
  });

  it('never shows a raw hash in the main view', () => {
    const html = renderInboxHtml(viewWith([clientRow()]), { nonce: 'n' });
    assert.ok(!html.includes('a'.repeat(64)));
  });

  it('offers every documented filter and marks the first one as pressed', () => {
    const html = renderInboxHtml(viewWith([clientRow()]), { nonce: 'n' });
    for (const filter of ['all-changed', 'recoverable', 'modified', 'deleted', 'attention', 'not-recoverable', 'unchanged']) {
      assert.ok(html.includes(`data-filter="${filter}"`), `missing filter ${filter}`);
    }
    assert.ok(/data-filter="all-changed" aria-pressed="true"/.test(html));
  });

  it('exposes only inert controls - never a bare apply/execute action', () => {
    const html = renderInboxHtml(viewWith([clientRow()]), { nonce: 'n' });
    assert.ok(html.includes('data-act="recoverSelected"'));
    assert.ok(html.includes('data-act="recoverAll"'));
    assert.ok(html.includes('data-act="refresh"'));
    assert.ok(!/data-act="(apply|execute|approve)"/.test(html));
  });
});

describe('Recovery Inbox renderer - live updates instead of reloads', () => {
  it('exposes the live hooks the client updates in place', () => {
    const html = renderInboxHtml(viewWith([clientRow()]), { nonce: 'n' });
    for (const hook of [
      'data-live="scanStatus"',
      'data-live="scanNote"',
      'data-live="lastScan"',
      'data-live="count-examined"',
      'data-live="count-changed"',
      'data-live="count-attention"',
      'data-live="coverage"',
      'data-live="selection"',
      'data-live="actionNote"',
      'data-live="notice"',
      'data-live="stale"',
      'data-live="progress"',
    ]) {
      assert.ok(html.includes(hook), `missing live hook: ${hook}`);
    }
  });

  it('applies a pushed state in place instead of reloading the document', () => {
    assert.ok(INBOX_SCRIPT.includes('function applyState(view)'), 'the client applies a state');
    assert.ok(
      INBOX_SCRIPT.includes("message.type !== 'update' || !message.view"),
      'the client only accepts typed updates',
    );
    assert.ok(!INBOX_SCRIPT.includes('location.reload'), 'the client never reloads itself');
    assert.ok(
      !INBOX_SCRIPT.includes('document.write') && !INBOX_SCRIPT.includes('innerHTML'),
      'the client never rewrites the document',
    );
  });

  it('keeps the summary cards, the notice and the stale banner updatable', () => {
    assert.ok(INBOX_SCRIPT.includes("setCount('examined'"), 'the counts are updated');
    assert.ok(INBOX_SCRIPT.includes("setList('[data-live=\"coverage\"]'"), 'the coverage is updated');
    assert.ok(INBOX_SCRIPT.includes("setBanner('[data-live=\"notice\"]'"), 'the notice is updated');
    assert.ok(INBOX_SCRIPT.includes("setBanner('[data-live=\"stale\"]'"), 'the stale banner is updated');
  });
});

describe('Recovery Inbox message guard', () => {
  it('accepts only the typed messages the script can send', () => {
    assert.ok(isInboxMessage({ type: 'ready' }));
    assert.ok(isInboxMessage({ type: 'refresh' }));
    assert.ok(isInboxMessage({ type: 'cancelScan' }));
    assert.ok(isInboxMessage({ type: 'preview', resource: 'src/app.ts' }));
    assert.ok(isInboxMessage({ type: 'select', add: ['src/app.ts'] }));
    assert.ok(isInboxMessage({ type: 'select', remove: ['src/app.ts'] }));
    assert.ok(isInboxMessage({ type: 'recoverSelected' }));
    assert.ok(isInboxMessage({ type: 'recoverAll' }));
    assert.ok(isInboxMessage({ type: 'confirm' }));
    assert.ok(isInboxMessage({ type: 'reviewPage', page: 2 }));
  });

  it('rejects malformed or dangerous messages', () => {
    assert.ok(!isInboxMessage(null));
    assert.ok(!isInboxMessage('ready'));
    assert.ok(!isInboxMessage({ type: 'unknown' }));
    assert.ok(!isInboxMessage({ type: 'preview' }), 'preview requires a resource');
    assert.ok(!isInboxMessage({ type: 'preview', resource: 7 }));
    assert.ok(!isInboxMessage({ type: 'select' }), 'select needs add or remove');
    assert.ok(!isInboxMessage({ type: 'select', add: 'src/app.ts' }), 'add must be a list');
    assert.ok(!isInboxMessage({ type: 'select', add: [7] }));
    assert.ok(!isInboxMessage({ type: 'reviewPage', page: 0 }));
    assert.ok(!isInboxMessage({ type: 'reviewPage', page: 1.5 }));
  });
});

describe('Recovery Inbox client core (evaluated headlessly)', () => {
  const rows = [
    clientRow({
      resource: 'src/b.ts',
      name: 'b.ts',
      dir: 'src',
      flags: {
        changed: true,
        unprotected: false,
        modified: false,
        deleted: true,
        unchanged: false,
        attention: true,
        recoverable: false,
      },
      eligibility: 'blocked',
      rankStatus: 1,
      rankEligibility: 2,
    }),
    clientRow({
      resource: 'docs/a.md',
      name: 'a.md',
      dir: 'docs',
      eligibility: 'eligible',
      flags: {
        changed: true,
        unprotected: false,
        modified: true,
        deleted: false,
        unchanged: false,
        attention: false,
        recoverable: true,
      },
    }),
    clientRow({
      resource: 'new.txt',
      name: 'new.txt',
      dir: '.',
      kind: 'unprotected',
      status: 'created',
      eligibility: 'unavailable',
      flags: {
        changed: false,
        unprotected: true,
        modified: false,
        deleted: false,
        unchanged: false,
        attention: false,
        recoverable: false,
      },
      rankStatus: 2,
      rankEligibility: 3,
    }),
  ];

  it('filters by every documented filter', () => {
    assert.strictEqual(scriptApi.filterRows(rows, 'all-changed', '').length, 3);
    assert.strictEqual(scriptApi.filterRows(rows, 'recoverable', '').length, 1);
    assert.strictEqual(scriptApi.filterRows(rows, 'modified', '').length, 1);
    assert.strictEqual(scriptApi.filterRows(rows, 'deleted', '').length, 1);
    assert.strictEqual(scriptApi.filterRows(rows, 'attention', '').length, 1);
    assert.strictEqual(scriptApi.filterRows(rows, 'not-recoverable', '').length, 2);
    assert.strictEqual(scriptApi.filterRows(rows, 'unchanged', '').length, 0);
  });

  it('searches paths case-insensitively', () => {
    assert.deepStrictEqual(
      scriptApi.filterRows(rows, 'all-changed', 'docs/').map((row) => row.resource),
      ['docs/a.md'],
    );
    assert.deepStrictEqual(
      scriptApi.filterRows(rows, 'all-changed', 'B.TS').map((row) => row.resource),
      ['src/b.ts'],
    );
  });

  it('sorts by path, status and eligibility', () => {
    assert.deepStrictEqual(
      scriptApi.sortRows(rows, 'path').map((row) => row.resource),
      ['docs/a.md', 'new.txt', 'src/b.ts'],
    );
    assert.deepStrictEqual(
      scriptApi.sortRows(rows, 'status').map((row) => row.resource),
      ['docs/a.md', 'src/b.ts', 'new.txt'],
    );
    assert.deepStrictEqual(
      scriptApi.sortRows(rows, 'eligibility').map((row) => row.resource),
      ['docs/a.md', 'src/b.ts', 'new.txt'],
    );
  });

  it('paginates without losing or duplicating rows', () => {
    const many = Array.from({ length: 25 }, (_, index) =>
      clientRow({ resource: `file-${index}.ts` }),
    );
    const first = scriptApi.pageSlice(many, 1, 10);
    const second = scriptApi.pageSlice(many, 2, 10);
    const third = scriptApi.pageSlice(many, 3, 10);
    assert.strictEqual(first.pages, 3);
    assert.strictEqual(first.rows.length, 10);
    assert.strictEqual(second.rows.length, 10);
    assert.strictEqual(third.rows.length, 5);
    const seen = [...first.rows, ...second.rows, ...third.rows].map((row) => row.resource);
    assert.strictEqual(new Set(seen).size, 25);
  });

  it('clamps an out-of-range page instead of showing nothing', () => {
    const slice = scriptApi.pageSlice([clientRow()], 99, 10);
    assert.strictEqual(slice.page, 1);
    assert.strictEqual(slice.rows.length, 1);
  });

  it('groups rows into collapsible folders', () => {
    const groups = scriptApi.groupRows(rows);
    assert.deepStrictEqual(
      groups.map((group) => group.dir),
      ['src', 'docs', '.'],
    );
    assert.strictEqual(groups[0].rows.length, 1);
  });

  it('summarises the selection the way the host does', () => {
    const text = scriptApi.selectionText(rows, { 'docs/a.md': true, 'src/b.ts': true });
    assert.strictEqual(text, '2 files selected · 1 eligible · 1 require attention');
  });

  it('never shows more than one page of rows at a time', () => {
    const many = Array.from({ length: 500 }, (_, index) =>
      clientRow({ resource: `file-${index}.ts` }),
    );
    const view = scriptApi.visibleRows({
      rows: many,
      filter: 'all-changed',
      query: '',
      sort: 'path',
      page: 1,
      pageSize: 200,
    });
    assert.strictEqual(view.rows.length, 200, 'the DOM stays bounded');
    assert.strictEqual(view.pages, 3);
  });
});
