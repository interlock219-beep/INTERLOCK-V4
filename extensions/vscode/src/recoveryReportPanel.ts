/**
 * Recovery Report panel: a VS Code webview panel (editor tab), not a Markdown
 * document. One instance at a time; re-rendered server-side on refresh by
 * replacing the whole document (no dynamic HTML injection into a live view).
 *
 * Message handling is deliberately strict:
 *   * every message must pass {@link isReportMessage} (shape),
 *   * `preview` must name a SAFE workspace-relative resource that is on THIS
 *     report's own allow-list (`previewableResources`) - a webview can never
 *     point the extension at an arbitrary path,
 *   * the panel itself never executes a recovery: it only asks the host to
 *     open the existing native diff or to rebuild the report.
 */

import { randomBytes } from 'crypto';
import * as vscode from 'vscode';
import { RecoveryReportModel, previewableResources } from './recoveryReport';
import {
  isReportMessage,
  isSafeResource,
  renderRecoveryReportHtml,
} from './recoveryReportHtml';

/** What the panel needs from its host (CommandHost) - no engine access here. */
export interface RecoveryReportHost {
  /** Re-observe the files and rebuild the model; the host re-calls show(). */
  refresh(): Promise<void>;
  /** Open the native side-by-side diff for one of the report's resources. */
  preview(resource: string): Promise<void>;
}

/** Minimal log shape the panel uses (structural - matches InterlockLog). */
export interface ReportLogger {
  warn(message: string): void;
}

const VIEW_TYPE = 'interlock.recoveryReport';
const PANEL_TITLE = 'Recovery Report';

export class RecoveryReportPanel implements vscode.Disposable {
  private panel: vscode.WebviewPanel | null = null;
  private model: RecoveryReportModel | null = null;
  private readonly listeners: vscode.Disposable[] = [];

  constructor(
    private readonly host: RecoveryReportHost,
    private readonly log: ReportLogger,
  ) {}

  /** Create or reveal the panel and render the given model. */
  show(model: RecoveryReportModel): void {
    this.model = model;
    if (this.panel === null) {
      this.panel = vscode.window.createWebviewPanel(
        VIEW_TYPE,
        PANEL_TITLE,
        vscode.ViewColumn.Active,
        {
          enableScripts: true,
          enableFindWidget: true,
          retainContextWhenHidden: false,
          // The report loads no local resources at all (CSP: img-src 'none').
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
    } else {
      this.panel.reveal(vscode.ViewColumn.Active);
    }
    this.panel.webview.html = this.html();
  }

  private html(): string {
    const nonce = randomBytes(16).toString('base64');
    const model = this.model;
    if (model === null) {
      return '<!DOCTYPE html><html><body></body></html>';
    }
    return renderRecoveryReportHtml(model, { nonce });
  }

  private onMessage(raw: unknown): void {
    if (!isReportMessage(raw)) {
      this.log.warn('Recovery report webview sent an unrecognized message; ignored.');
      return;
    }
    if (raw.type === 'ready') {
      return;
    }
    if (raw.type === 'close') {
      this.panel?.dispose();
      return;
    }
    if (raw.type === 'refresh') {
      this.host.refresh().catch(() => {
        // Fixed wording: no error payload is logged or shown, so no absolute
        // path or secret can leak from a failed refresh.
        this.log.warn('Recovery report refresh failed.');
        void vscode.window.showErrorMessage(
          'Interlock: could not refresh the recovery report. See the Interlock output log for details.',
        );
      });
      return;
    }
    if (raw.type === 'previewAll') {
      const model = this.model;
      if (model === null) {
        return;
      }
      void this.previewEach(previewableResources(model));
      return;
    }
    // raw.type === 'preview'
    const resource = raw.resource ?? '';
    const model = this.model;
    if (model === null) {
      return;
    }
    if (!isSafeResource(resource) || !previewableResources(model).includes(resource)) {
      // The webview may only name a resource THIS report rendered as
      // previewable. Anything else is ignored, never resolved to a path.
      this.log.warn(
        'Recovery report webview asked to preview a resource outside this report; ignored.',
      );
      return;
    }
    void this.previewEach([resource]);
  }

  /** Preview resources one at a time through the host's existing diff flow. */
  private async previewEach(resources: string[]): Promise<void> {
    for (const resource of resources) {
      try {
        await this.host.preview(resource);
      } catch {
        this.log.warn('Recovery report preview failed.');
        void vscode.window.showWarningMessage(
          'Interlock: could not open the side-by-side diff for one of the files.',
        );
        return;
      }
    }
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
    this.model = null;
  }
}
