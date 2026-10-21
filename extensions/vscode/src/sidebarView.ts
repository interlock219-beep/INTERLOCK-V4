/**
 * The Interlock sidebar webview view (compact security dashboard).
 *
 * Contract with the webview:
 *   host -> webview : {type:'model', model}  full state projection
 *                     {type:'busy', busy}    a command is running
 *   webview -> host : {type:'ready'}         view is ready for state
 *                     {type:'run', command}  allow-listed command id only
 *                     {type:'openSettings'}  no payload (host picks the query)
 *
 * Every inbound message is validated with `isWebviewMessage` before it can
 * reach `vscode.commands.executeCommand`, and the model is pushed, never
 * pulled, so the webview can never ask for arbitrary host data.
 */

import { randomBytes } from 'crypto';
import * as vscode from 'vscode';

import { InterlockLog } from './log';
import { SidebarState } from './sidebar';
import { isWebviewMessage, renderSidebarHtml } from './webviewHtml';

export class InterlockSidebarViewProvider implements vscode.WebviewViewProvider, vscode.Disposable {
  public static readonly viewType = 'interlock.sidebar';

  private readonly subscriptions: vscode.Disposable[] = [];
  private view: vscode.WebviewView | undefined;
  private running = 0;

  constructor(
    private readonly state: SidebarState,
    private readonly log: InterlockLog,
  ) {
    this.subscriptions.push(state.onDidChange((model) => this.postModel(model)));
  }

  dispose(): void {
    for (const disposable of this.subscriptions) {
      disposable.dispose();
    }
    this.view = undefined;
  }

  resolveWebviewView(webviewView: vscode.WebviewView): void {
    this.view = webviewView;
    webviewView.webview.options = {
      enableScripts: true,
      // No local assets are loaded: every icon is inline SVG, so the webview
      // may not reach the filesystem at all.
      localResourceRoots: [],
    };
    webviewView.webview.html = this.html();

    this.subscriptions.push(
      webviewView.onDidDispose(() => {
        this.view = undefined;
      }),
      webviewView.webview.onDidReceiveMessage((message: unknown) => this.onMessage(message)),
    );
  }

  private html(): string {
    const nonce = randomBytes(16).toString('base64');
    return renderSidebarHtml(this.state.getModel(), { nonce });
  }

  private onMessage(message: unknown): void {
    if (!isWebviewMessage(message)) {
      this.log.warn(`Sidebar webview sent an unrecognized message; ignored.`);
      return;
    }
    if (message.type === 'ready') {
      this.postModel(this.state.getModel());
      return;
    }
    if (message.type === 'openSettings') {
      void vscode.commands.executeCommand('workbench.action.openSettings', 'interlock');
      return;
    }
    const command = message.command;
    if (command === undefined) {
      return;
    }
    void this.runCommand(command);
  }

  /** Run an allow-listed command, mirroring its busy state into the view. */
  private async runCommand(command: string): Promise<void> {
    this.running += 1;
    this.post({ type: 'busy', busy: true });
    try {
      await vscode.commands.executeCommand(command);
    } catch (error) {
      // Command implementations report their own failures; this is a backstop.
      this.log.error(
        `Sidebar command ${command} failed: ${
          error instanceof Error ? error.message : String(error)
        }`,
      );
    } finally {
      this.running = Math.max(0, this.running - 1);
      this.post({ type: 'busy', busy: this.running > 0 });
    }
  }

  private postModel(model: SidebarState['model']): void {
    this.post({ type: 'model', model });
  }

  private post(message: unknown): void {
    void this.view?.webview.postMessage(message);
  }
}
