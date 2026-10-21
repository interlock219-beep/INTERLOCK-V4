/**
 * Recovery Inbox panel: a VS Code webview panel (editor tab), not a Markdown
 * document. One instance at a time; re-rendered server-side when the state
 * changes (list / review / results) and updated in place for live progress
 * and selection feedback.
 *
 * Message handling is deliberately strict:
 *   * every message must pass {@link isInboxMessage} (shape),
 *   * `preview` / `viewDiff` / `openFile` must name a SAFE workspace-relative
 *     resource that this inbox actually rendered - a webview can never point
 *     the extension at an arbitrary path,
 *   * the panel never performs a recovery itself: it forwards validated
 *     intents to the host, which re-validates them against its own model.
 */

import { randomBytes } from 'crypto';
import * as vscode from 'vscode';

import { InboxChannel } from './inboxChannel';
import { InboxViewState } from './recoveryInbox';
import { isSafeResource } from './recoveryReportHtml';
import {
  InboxMessage,
  InboxUpdate,
  isInboxMessage,
  renderInboxHtml,
} from './recoveryInboxHtml';

/** What the panel needs from its host (the inbox controller). */
export interface RecoveryInboxPanelHost {
  /** Handle a validated intent from the webview. */
  handle(message: InboxMessage): void | Promise<void>;
  /**
   * The webview finished booting. The host re-sends the current state, so a
   * webview that (re)loaded never shows a stale view.
   */
  ready?(): void;
}

/** Minimal log shape the panel uses (structural - matches InterlockLog). */
export interface InboxLogger {
  warn(message: string): void;
}

const VIEW_TYPE = 'interlock.recoveryInbox';
const PANEL_TITLE = 'Interlock Recovery Inbox';

/** Resources this inbox rendered and may therefore name in a message. */
export function knownResources(view: InboxViewState | null): string[] {
  if (view === null) {
    return [];
  }
  const out: string[] = [];
  for (const row of view.rows) {
    out.push(row.resource);
  }
  if (view.review !== null) {
    for (const entry of view.review.included) {
      out.push(entry.resource);
    }
    for (const entry of view.review.excluded) {
      out.push(entry.resource);
    }
  }
  if (view.results !== null) {
    for (const entry of view.results.entries) {
      out.push(entry.resource);
    }
  }
  return out;
}

export class RecoveryInboxPanel implements vscode.Disposable {  private panel: vscode.WebviewPanel | null = null;
  private view: InboxViewState | null = null;
  private readonly listeners: vscode.Disposable[] = [];
  /** Queues updates until the webview is live, then delivers them. */
  private readonly channel = new InboxChannel({
    deliver: (update) => {
      void this.panel?.webview.postMessage(update);
    },
  });

  constructor(
    private readonly host: RecoveryInboxPanelHost,
    private readonly log: InboxLogger,
  ) {}

  /** Create or reveal the panel and render the given state. */
  show(view: InboxViewState): void {
    this.view = view;
    // A new document means a new webview instance: it has to handshake again.
    this.channel.reset();
    if (this.panel === null) {
      this.panel = vscode.window.createWebviewPanel(
        VIEW_TYPE,
        PANEL_TITLE,
        vscode.ViewColumn.Active,
        {
          enableScripts: true,
          enableFindWidget: true,
          retainContextWhenHidden: false,
          // The inbox loads no local resources at all (CSP: img-src 'none').
          localResourceRoots: [],
        },
      );
      this.panel.onDidDispose(
        () => {
          this.panel = null;
          this.disposeListeners();
        },
        null,
        this.listeners,
      );
      this.panel.webview.onDidReceiveMessage(
        (message: unknown) => this.onMessage(message),
        null,
        this.listeners,
      );
    }
    // Reveal FIRST, then load the document: a webview that is not attached
    // yet can lose an early document, and the inbox would then never boot
    // (no script, no handlers, no visible tab).
    this.reveal();
    this.panel.webview.html = this.html();
  }

  /** Focus the inbox tab without reloading its document. */
  reveal(): void {
    this.panel?.reveal(vscode.ViewColumn.Active);
  }

  /**
   * Push a live update to the open panel.
   *
   * While the webview is still booting the update is queued and flushed as
   * soon as it reports `ready` - a state change that happens during the
   * initial load is never lost (that was the reason a freshly opened inbox
   * could look unresponsive until the user clicked something).
   */
  update(update: InboxUpdate): void {
    if (this.panel === null) {
      return;
    }
    this.channel.send(update);
  }

  /** True while the panel is open (the controller uses it to skip work). */
  isOpen(): boolean {
    return this.panel !== null;
  }

  private html(): string {
    const nonce = randomBytes(16).toString('base64');
    const view = this.view;
    if (view === null) {
      return '<!DOCTYPE html><html><body></body></html>';
    }
    return renderInboxHtml(view, { nonce });
  }

  private onMessage(raw: unknown): void {
    if (!isInboxMessage(raw)) {
      this.log.warn('Recovery inbox webview sent an unrecognized message; ignored.');
      return;
    }
    if (raw.type === 'ready') {
      // The webview is live: flush everything that arrived while it booted and
      // let the host re-send the current state.
      this.channel.markReady();
      this.host.ready?.();
      return;
    }
    if (raw.type === 'close') {
      this.panel?.dispose();
      return;
    }
    if (raw.type === 'preview' || raw.type === 'viewDiff' || raw.type === 'openFile') {
      const resource = raw.resource ?? '';
      if (!isSafeResource(resource) || !knownResources(this.view).includes(resource)) {
        // The webview may only name a resource THIS inbox rendered. Anything
        // else is ignored, never resolved to a path.
        this.log.warn(
          'Recovery inbox webview named a resource outside this inbox; ignored.',
        );
        return;
      }
    }
    if (raw.type === 'select') {
      const add = raw.add ?? [];
      const remove = raw.remove ?? [];
      if (
        !add.every((resource) => isSafeResource(resource)) ||
        !remove.every((resource) => isSafeResource(resource))
      ) {
        this.log.warn('Recovery inbox webview sent an unsafe selection; ignored.');
        return;
      }
    }
    // The controller reports its own failures; this is a backstop so a
    // rejected intent can never become an unhandled rejection in the host.
    void Promise.resolve(this.host.handle(raw)).catch(() => {
      this.log.warn('Recovery inbox could not handle a request; nothing was changed.');
    });
  }

  private disposeListeners(): void {
    while (this.listeners.length > 0) {
      const listener = this.listeners.pop();
      listener?.dispose();
    }
  }

  dispose(): void {
    this.disposeListeners();
    this.panel?.dispose();
    this.panel = null;
    this.view = null;
  }
}
