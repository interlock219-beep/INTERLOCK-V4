/**
 * Recovery Inbox update channel tests (pure).
 *
 * The channel is what keeps a freshly opened inbox alive: a webview can only
 * receive messages after it finished booting, so everything the host pushes
 * in that window has to wait instead of being lost. Losing those updates is
 * what made a newly opened inbox look unresponsive until the user clicked
 * something.
 */

import * as assert from 'assert';

import { InboxChannel } from '../../src/inboxChannel';
import { InboxViewState } from '../../src/recoveryInbox';
import { InboxUpdate } from '../../src/recoveryInboxHtml';

function view(mode: 'list' | 'review' | 'results' = 'list'): InboxViewState {
  return {
    mode,
    workspaceName: 'workspace',
    scan: {
      status: 'done',
      statusLabel: 'Scan complete',
      statusNote: 'Discovery and eligibility assessment finished.',
      startedAt: '2026-10-20T12:00:00.000Z',
      finishedAt: '2026-10-20T12:00:05.000Z',
      progress: null,
      error: null,
      stale: false,
      staleReason: null,
    },
    counts: {
      examined: 2,
      changed: 1,
      verifiedEvidence: 2,
      recoverableModified: 1,
      recoverableDeleted: 0,
      attention: 0,
      noBaseline: 0,
    },
    coverageLines: ['2 baseline files checked against its stored evidence.'],
    notice: null,
    busy: null,
    rows: [],
    selection: { count: 0, eligible: 0, attention: 0, pending: 0, text: '0 files selected' },
    selectionResources: [],
    recoverSelected: { enabled: false, label: 'Recover Selected', note: 'nothing to do' },
    recoverAll: { enabled: false, label: 'Recover All', note: 'nothing to do' },
    review: null,
    results: null,
  };
}

function update(mode: 'list' | 'review' | 'results' = 'list'): InboxUpdate {
  return { type: 'update', view: view(mode) };
}

describe('Recovery Inbox update channel', () => {
  it('queues updates until the webview reports that it is live', () => {
    const delivered: InboxUpdate[] = [];
    const channel = new InboxChannel({ deliver: (item) => delivered.push(item) });

    assert.strictEqual(channel.send(update()), 'queued');
    assert.strictEqual(channel.send(update()), 'queued');
    assert.strictEqual(delivered.length, 0, 'nothing may be delivered before the webview is live');
    assert.strictEqual(channel.pending(), 2);
    assert.strictEqual(channel.isLive(), false);
  });

  it('flushes the queued updates in order when the webview becomes live', () => {
    const delivered: InboxUpdate[] = [];
    const channel = new InboxChannel({ deliver: (item) => delivered.push(item) });

    channel.send(update('list'));
    channel.send(update('review'));
    const flushed = channel.markReady();

    assert.strictEqual(flushed.length, 2);
    assert.strictEqual(delivered.length, 2);
    assert.strictEqual(delivered[0].view?.mode, 'list');
    assert.strictEqual(delivered[1].view?.mode, 'review');
    assert.strictEqual(channel.pending(), 0);
    assert.strictEqual(channel.isLive(), true);
  });

  it('delivers later updates straight through', () => {
    const delivered: InboxUpdate[] = [];
    const channel = new InboxChannel({ deliver: (item) => delivered.push(item) });

    channel.markReady();
    assert.strictEqual(channel.send(update()), 'delivered');
    assert.strictEqual(delivered.length, 1);
  });

  it('starts over when a new document is loaded', () => {
    const delivered: InboxUpdate[] = [];
    const channel = new InboxChannel({ deliver: (item) => delivered.push(item) });

    channel.markReady();
    channel.send(update());
    assert.strictEqual(delivered.length, 1);

    // A new document means a new webview: it has to handshake again.
    channel.reset();
    assert.strictEqual(channel.isLive(), false);
    assert.strictEqual(channel.send(update()), 'queued');
    assert.strictEqual(delivered.length, 1, 'the update waits for the new webview');

    channel.markReady();
    assert.strictEqual(delivered.length, 2, 'and is delivered once the new webview is live');
  });

  it('never delivers an update twice', () => {
    const delivered: InboxUpdate[] = [];
    const channel = new InboxChannel({ deliver: (item) => delivered.push(item) });

    channel.send(update());
    channel.markReady();
    channel.markReady();
    assert.strictEqual(delivered.length, 1);
  });
});
