/**
 * Interlock VS Code extension entry point.
 *
 * Activation is intentionally side-effect free: registering commands and the
 * sidebar performs **no** subprocess launch, no engine import, and no
 * workspace scan. Engine calls happen only when the user runs a command.
 * (Hydration reads only the extension's own private storage - previously
 * captured baselines - so the first paint shows real evidence, not guesses.)
 */

import * as path from 'path';
import * as vscode from 'vscode';

import { CommandHost } from './commands';
import { EngineRuntime } from './engineRuntime';
import { InterlockLog } from './log';
import { SetupState } from './engineSetup';
import { BaselineStore, StoredStatus, StoredVerification } from './state';
import { SidebarModel, SidebarState } from './sidebar';
import { InterlockSidebarViewProvider } from './sidebarView';

/**
 * Read-only API exposed on activation. It exists so tests and automation can
 * assert on what the extension actually observed (instead of scraping UI), and
 * it exposes nothing beyond state the sidebar already renders.
 */
export interface InterlockApi {
  /** Current sidebar model (engine status, workspace state, warnings). */
  getModel(): SidebarModel;
  /** Filesystem-only engine setup state (no subprocess is spawned). */
  getSetup(): SetupState;
}

export function activate(context: vscode.ExtensionContext): InterlockApi {
  const log = new InterlockLog();
  const sidebar = new SidebarState();
  const storage = new BaselineStore(context.globalStorageUri.fsPath);
  // The zero-configuration engine: a SHA-256-verified bundled engine plus a
  // bundled (or detected) interpreter, installed into extension-managed
  // storage. Installation never reads or writes the user's workspace.
  const engineRuntime = new EngineRuntime({
    extensionPath: context.extensionPath,
    storageDir: context.globalStorageUri.fsPath,
    bridgeScript: path.join(context.extensionPath, 'python', 'interlock_bridge.py'),
  });
  const host = new CommandHost(context, log, sidebar, storage, engineRuntime);
  const view = new InterlockSidebarViewProvider(sidebar, log);

  // Hydrate the sidebar from previously stored results (no engine call).
  const previousStatus = context.globalState.get<StoredStatus>('interlock.status');
  const previousVerification = context.globalState.get<StoredVerification>(
    'interlock.verification',
  );
  const model = sidebar.getModel();
  sidebar.setModel({
    ...model,
    status: previousStatus ?? null,
    verification: previousVerification ?? null,
    workspacePath: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? null,
  });
  // Hydrate the protection card from stored baselines (extension-private
  // storage only; no subprocess, no engine call, no workspace scan).
  void host.initializeFromStorage();

  const bridgeScript = path.join(context.extensionPath, 'python', 'interlock_bridge.py');
  log.info(`Interlock activated. Bridge script: ${bridgeScript}`);

  /**
   * Install (or repair, or verify) the managed engine. Concurrent triggers are
   * collapsed onto ONE run by the runtime's single-flight guard, so calling
   * this from both the auto-setup timer and a user command is safe.
   */
  const runInstall = (): Promise<void> =>
    Promise.resolve(
      vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: 'Interlock: setting up engine…' },
        () => engineRuntime.ensureInstalled(),
      ),
    ).then((outcome) => {
        if (outcome.ok) {
          log.info(`Engine ready: ${outcome.setup.message}`);
          sidebar.patchModel({
            lastAction: 'Engine installed and verified (bundled runtime).',
            lastError: null,
          });
          return;
        }
        log.error(`Engine setup failed: ${outcome.setup.error ?? outcome.setup.message}`);
        sidebar.patchModel({ lastError: outcome.setup.message });
        void vscode.window.showErrorMessage(
          `Interlock: ${outcome.setup.message}` +
            (outcome.setup.error ? ` (${outcome.setup.error})` : ''),
        );
      });

  // Deferred, non-blocking first-run setup: registration and the first paint
  // complete before any subprocess is launched, then the engine is installed
  // and health-checked in the background so Protect/Analyze work immediately.
  const initialSetup = engineRuntime.state();
  log.info(`Engine setup state: ${initialSetup.status} (${initialSetup.phase})`);
  let setupTimer: NodeJS.Timeout | undefined;
  if (initialSetup.status !== 'ready') {
    setupTimer = setTimeout(() => void runInstall(), 1500);
  }

  const register = (id: string, run: () => unknown): vscode.Disposable =>
    vscode.commands.registerCommand(id, () =>
      Promise.resolve(run()).catch((error: unknown) => {
        log.error(`Command ${id} failed: ${error instanceof Error ? error.stack ?? error.message : String(error)}`);
        void vscode.window.showErrorMessage(
          `Interlock: ${id} failed unexpectedly. See the Interlock output log.`,
        );
      }),
    );

  context.subscriptions.push(
    log,
    sidebar,
    view,
    host,
    vscode.window.registerWebviewViewProvider(InterlockSidebarViewProvider.viewType, view, {
      webviewOptions: { retainContextWhenHidden: true },
    }),
    register('interlock.installEngine', () => runInstall()),
    register('interlock.checkInstallation', () => host.checkInstallation()),
    register('interlock.checkStatus', () => host.checkStatus()),
    register('interlock.analyzeWorkspace', () => host.analyzeWorkspace()),
    register('interlock.protectWorkspace', () => host.protectWorkspace()),
    register('interlock.captureBaseline', () => host.captureBaseline()),
    register('interlock.previewRecoveryPlan', () => host.previewRecoveryPlan()),
    register('interlock.viewRecoveryPlan', () => host.viewRecoveryPlan()),
    register('interlock.openRecoveryInbox', () => host.openRecoveryInbox()),
    register('interlock.executeRecovery', () => host.executeRecovery()),
    register('interlock.verifyRecovery', () => host.verifyRecovery()),
    register('interlock.openDocumentation', () => host.openDocumentation()),
    register('interlock.refresh', () => sidebar.refresh()),
    register('interlock.openOutput', () => log.show()),
    // Folder set changed: drop previews/coverage that belonged elsewhere.
    vscode.workspace.onDidChangeWorkspaceFolders(() => {
      void host.workspaceChanged();
    }),
    // Cancel a pending deferred setup if the extension is deactivated first.
    new vscode.Disposable(() => {
      if (setupTimer) {
        clearTimeout(setupTimer);
      }
    }),
  );

  return {
    getModel: () => sidebar.getModel(),
    getSetup: () => engineRuntime.state(),
  };
}

export function deactivate(): void {
  // Nothing to clean up: no child processes outlive a command.
}
