/**
 * The inbox's live-update channel (pure, headless).
 *
 * A webview only exists after its document was loaded, and it is only able to
 * receive a message once its script asked for the VS Code API. Anything the
 * host pushes in that window would be lost - which is exactly how a freshly
 * opened inbox could show a stale view (or no reaction at all) until the user
 * clicked something.
 *
 * The channel therefore queues updates until the webview reports `ready` and
 * flushes them afterwards. It is deliberately free of `vscode` so the
 * behaviour can be unit-tested.
 */

import { InboxUpdate } from './recoveryInboxHtml';

export interface InboxChannelHost {
  /** Deliver one update to the webview. */
  deliver(update: InboxUpdate): void;
}

export class InboxChannel {
  private live = false;
  private queued: InboxUpdate[] = [];

  constructor(private readonly host: InboxChannelHost) {}

  /**
   * The webview reported that it is ready: everything that was queued is
   * delivered now (in order) and later updates go straight through.
   */
  markReady(): InboxUpdate[] {
    this.live = true;
    const pending = this.queued;
    this.queued = [];
    for (const update of pending) {
      this.host.deliver(update);
    }
    return pending;
  }

  /**
   * Send one update. Before the webview is ready the update is queued; after
   * that it is delivered immediately.
   */
  send(update: InboxUpdate): 'queued' | 'delivered' {
    if (!this.live) {
      this.queued.push(update);
      return 'queued';
    }
    this.host.deliver(update);
    return 'delivered';
  }

  /** A new document means a new webview: the handshake starts over. */
  reset(): void {
    this.live = false;
    this.queued = [];
  }

  /** True once the webview reported that it is live. */
  isLive(): boolean {
    return this.live;
  }

  /** How many updates are waiting for the webview. */
  pending(): number {
    return this.queued.length;
  }
}
