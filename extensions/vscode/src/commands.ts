/**
 * Command implementations.
 *
 * Every command here either (a) performs a read-only call into the real
 * Interlock engine through `python/interlock_bridge.py`, or (b) runs the
 * approval-gated recovery flow. Success is only ever reported when the engine
 * itself reported success *and* verification confirmed a byte-exact restore.
 */

import * as fs from 'fs';
import * as fsp from 'fs/promises';
import * as path from 'path';
import * as vscode from 'vscode';

import {
  BridgeCallResult,
  BridgeInvocation,
  callBridge,
  describeFailure,
} from './bridge';
import { InterlockSettings, isAllowedDocumentationUrl, normalizeSettings } from './config';
import { detectEngine, EngineLocation } from './discovery';
import type { EngineRuntime } from './engineRuntime';
import { RecoveryInboxController, InboxDeps } from './inboxController';
import { asArray, asBool, asDict, asStr, asStringArray } from './jsonValues';
import { InterlockLog } from './log';
import { resolveWithin, isAcceptableRelativeResource } from './paths';
import { statusLabel } from './platform';
import {
  describeProtectionPlan,
  evaluateProtection,
  planProtection,
  previewIsFresh,
  ProtectionPlan,
  ScanFile,
} from './protection';
import { redact, truncate } from './redact';
import { MISSING_SCHEME, PROPOSED_SCHEME, RecoveryDocuments } from './recoveryDocuments';
import { ApplyOutcome } from './recoveryInbox';
import { readPlanSummary } from './recoveryPlanReport';
import { buildRecoveryReport } from './recoveryReport';
import { RecoveryReportPanel } from './recoveryReportPanel';
import { RecoveryInboxPanel } from './recoveryInboxPanel';
import {
  diffTitle,
  isApplicable,
  planFromEngineResult,
  PlannedRecovery,
  staleAgainstCurrent,
  summarizePlans,
} from './recoveryPlan';
import { runProcess } from './runner';
import { SidebarState } from './sidebar';
import {
  BaselineStore,
  evidencePathFor,
  sameWorkspace,
  StoredStatus,
  StoredVerification,
  toBaselineDocument,
} from './state';

const PYTHON_PROBE_CODE = [
  'import json,platform,sys',
  'print(json.dumps({"version":platform.python_version(),"executable":sys.executable}))',
].join(';');

const DOC_RELATIVE_PATHS = [
  'docs/INDEX.md',
  'docs/operations/BETA_FIRST_RUN.md',
  'docs/operations/SAFETY_AND_LIMITATIONS.md',
  'docs/operations/SUPPORTED_PLATFORMS.md',
  'docs/operations/TROUBLESHOOTING.md',
  'README.md',
];

const REPOSITORY_URL = 'https://github.com/interlock219-beep/INTERLOCK-V4';

export class CommandHost implements vscode.Disposable {
  private readonly disposables: vscode.Disposable[] = [];
  private lastScanFiles: string[] = [];
  private readonly globalState: vscode.Memento;
  /**
   * Protection bookkeeping that only a real scan or capture run can know:
   * how many files were eligible, how many policy skips occurred, and when
   * the state was last established. Kept out of the model so a reload never
   * shows stale coverage claims (after a reload they reset to "unknown").
   */
  private protectionEligible: number | null = null;
  private protectionSkipped = 0;
  private protectionCheckedAt: string | null = null;
  private protectionWorkspace: string | null = null;
  private analyzing = false;
  private analyzingDetail: string | null = null;
  /**
   * The recovery plans behind the currently open diffs, in review order.
   * Apply only ever acts on plans from this list (re-validated engine plan +
   * re-verified baseline bytes) - the webview can never name a target.
   */
  private previewed: PlannedRecovery[] = [];
  /** The single Recovery Report panel (created on first use). */
  private recoveryReport: RecoveryReportPanel | null = null;
  /** Read-only virtual documents for the "proposed recovery" diff side. */
  private readonly recoveryDocs = new RecoveryDocuments();
  /** Approver identity confirmed once per session (never re-asked). */
  private sessionApprover: string | null = null;
  /** The Recovery Inbox controller (created on first use, disposed with the host). */
  private inbox: RecoveryInboxController | null = null;

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly log: InterlockLog,
    private readonly sidebar: SidebarState,
    private readonly storage: BaselineStore,
    private readonly engineRuntime?: EngineRuntime,
  ) {
    this.globalState = context.globalState;
    this.disposables.push(
      vscode.workspace.registerTextDocumentContentProvider(PROPOSED_SCHEME, this.recoveryDocs),
      vscode.workspace.registerTextDocumentContentProvider(MISSING_SCHEME, this.recoveryDocs),
      this.recoveryDocs,
    );
  }

  dispose(): void {
    for (const disposable of this.disposables) {
      disposable.dispose();
    }
  }

  // ------------------------------------------------------------------ config

  private getSettings(): InterlockSettings {
    const cfg = vscode.workspace.getConfiguration('interlock');
    const { settings, issues } = normalizeSettings({
      pythonPath: cfg.get('pythonPath'),
      engineRoot: cfg.get('engineRoot'),
      autoDetectEngine: cfg.get('autoDetectEngine'),
      timeoutSeconds: cfg.get('timeoutSeconds'),
      maxBaselineBytes: cfg.get('maxBaselineBytes'),
      showGitChanges: cfg.get('showGitChanges'),
      allowedDocumentationUrls: cfg.get('allowedDocumentationUrls'),
      automaticBaselineProtection: cfg.get('automaticBaselineProtection'),
      baselineExclusions: cfg.get('baselineExclusions'),
    });
    for (const issue of issues) {
      this.log.warn(`Configuration: ${issue.key} - ${issue.message}`);
    }
    if (issues.length > 0) {
      this.sidebar.patchModel({
        warnings: issues.map((issue) => `${issue.key}: ${issue.message}`),
      });
    }
    // Mirror the settings for the sidebar (config stays the single source);
    // patched only on change so a hot loop of reads cannot churn the model.
    const model = this.sidebar.getModel();
    if (model.autoProtectionEnabled !== settings.automaticBaselineProtection) {
      this.sidebar.patchModel({ autoProtectionEnabled: settings.automaticBaselineProtection });
    }
    if (JSON.stringify(model.baselineExclusions) !== JSON.stringify(settings.baselineExclusions)) {
      this.sidebar.patchModel({ baselineExclusions: settings.baselineExclusions });
    }
    return settings;
  }

  private locate(settings: InterlockSettings): EngineLocation {
    const roots = (vscode.workspace.workspaceFolders ?? []).map((folder) => folder.uri.fsPath);
    // The extension's own verified installation (bundled engine + bundled
    // runtime) is offered as the discovery override, so a fresh install works
    // with zero configuration. Explicit interlock.pythonPath/engineRoot still
    // win inside detectEngine, so a developer checkout is unaffected.
    const managed = this.engineRuntime?.managed();
    const override = managed
      ? {
          pythonPath: managed.pythonPath,
          pythonSource: 'managed installation (verified)',
          engineRoot: managed.engineRoot,
          engineSource: 'managed installation (bundled engine)',
        }
      : undefined;
    const location = detectEngine(settings, roots, (candidate) => fs.existsSync(candidate), override);
    for (const issue of location.issues) {
      this.log.warn(`Discovery: ${issue}`);
    }
    this.log.info(
      `Interpreter: ${location.pythonPath || '(none)'} [${location.pythonSource}]; ` +
        `engine root: ${location.engineRoot || '(none)'} [${location.engineSource}]`,
    );
    return location;
  }

  private bridgeScriptPath(): string | null {
    const candidate = path.join(this.context.extensionPath, 'python', 'interlock_bridge.py');
    if (!fs.existsSync(candidate)) {
      this.log.error(`Bridge script missing at ${candidate}`);
      return null;
    }
    return candidate;
  }

  // --------------------------------------------------------------- workspace

  private async pickWorkspace(): Promise<string | null> {
    const folders = vscode.workspace.workspaceFolders ?? [];
    if (folders.length === 0) {
      void vscode.window.showErrorMessage(
        'Interlock: no folder is open. Open the project folder you want to protect.',
      );
      return null;
    }
    let chosen: string;
    if (folders.length === 1) {
      chosen = folders[0].uri.fsPath;
    } else {
      // Multiple folders: require an explicit choice; never guess which one to act on.
      const choice = await vscode.window.showQuickPick(
        folders.map((folder) => ({
          label: folder.name,
          description: folder.uri.fsPath,
          folder,
        })),
        { title: 'Interlock: select the workspace folder to operate on' },
      );
      if (!choice) {
        return null;
      }
      chosen = choice.folder.uri.fsPath;
    }
    this.adoptWorkspace(chosen);
    return chosen;
  }

  /**
   * Everything derived from a specific workspace is dropped when the target
   * folder changes: coverage numbers, skip counts, and previews that belong
   * to the previous folder (they must never drive this folder's actions).
   */
  private adoptWorkspace(workspaceRoot: string): void {
    if (this.protectionWorkspace !== workspaceRoot) {
      this.protectionWorkspace = workspaceRoot;
      this.protectionEligible = null;
      this.protectionSkipped = 0;
      this.protectionCheckedAt = null;
    }
    const model = this.sidebar.getModel();
    if (model.pendingPreview && model.pendingPreview.workspace !== workspaceRoot) {
      this.sidebar.patchModel({ pendingPreview: null });
    }
  }

  private async resolveTarget(
    workspaceRoot: string,
    title = 'Select the file to work with',
  ): Promise<string | null> {
    const active = vscode.window.activeTextEditor?.document.uri;
    const items: Array<vscode.QuickPickItem & { action: 'active' | 'browse' | 'type' | 'file'; rel?: string }> = [];

    if (active && active.scheme === 'file') {
      const rel = resolveWithin(workspaceRoot, active.fsPath);
      if (rel) {
        items.push({ label: rel, description: 'active editor', action: 'active', rel });
      }
    }
    for (const file of this.lastScanFiles.slice(0, 60)) {
      items.push({ label: file, description: 'workspace file', action: 'file', rel: file });
    }
    items.push({ label: 'Browseâ€¦', description: 'pick a file with the file dialog', action: 'browse' });
    items.push({ label: 'Enter pathâ€¦', description: 'type a workspace-relative path', action: 'type' });

    const pick = await vscode.window.showQuickPick(items, {
      title,
      placeHolder: 'Recovery only ever targets files inside this workspace',
    });
    if (!pick) {
      return null;
    }
    if (pick.action === 'browse') {
      const chosen = await vscode.window.showOpenDialog({
        canSelectMany: false,
        defaultUri: vscode.Uri.file(workspaceRoot),
        openLabel: 'Select target file',
      });
      if (!chosen || chosen.length === 0) {
        return null;
      }
      const rel = resolveWithin(workspaceRoot, chosen[0].fsPath);
      if (!rel) {
        void vscode.window.showErrorMessage(
          'Interlock: that file is outside the authorized workspace and was refused.',
        );
        return null;
      }
      return rel;
    }
    if (pick.action === 'type') {
      const typed = await vscode.window.showInputBox({
        prompt: 'Workspace-relative path of the target file',
        placeHolder: 'src/config.yaml',
        validateInput: (value) =>
          isAcceptableRelativeResource(value.trim()) ? undefined : 'Enter a relative path inside the workspace',
      });
      if (!typed) {
        return null;
      }
      return typed.trim().replace(/\\/g, '/');
    }
    return pick.rel ?? null;
  }

  // ------------------------------------------------------------------- calls

  private async call(
    invocation: BridgeInvocation,
    options: {
      title: string;
      workspaceRoot?: string;
      maxOutputBytes?: number;
      /**
       * Run without its own progress notification - used when this call is
       * nested inside an outer progress (e.g. per-file capture during a
       * protection run) so the user sees ONE progress, not N.
       */
      silent?: boolean;
      /** External cancellation (e.g. the outer protection run's token). */
      signal?: AbortSignal;
    },
  ): Promise<BridgeCallResult> {
    const settings = this.getSettings();
    const location = this.locate(settings);
    const bridgeScript = this.bridgeScriptPath();

    const emptyResult = (message: string, hint: string): BridgeCallResult => ({
      ok: false,
      command: invocation.command,
      kind: 'interpreter_not_found',
      exitCode: null,
      envelope: null,
      result: null,
      message,
      hint,
      stderrExcerpt: '',
      truncated: false,
      durationMs: 0,
    });

    if (!bridgeScript) {
      const result = emptyResult(
        'The Interlock bridge script is missing from the extension installation.',
        'Reinstall the extension VSIX.',
      );
      this.finalize(result);
      return result;
    }
    if (!location.pythonPath) {
      const result = emptyResult(
        'No Python interpreter is configured for Interlock.',
        'Set "interlock.pythonPath" to a Python 3.11-3.14 interpreter.',
      );
      this.finalize(result);
      return result;
    }

    const engineRoot = invocation.engineRoot ?? location.engineRoot;
    const fullInvocation: BridgeInvocation = { ...invocation, engineRoot };

    const invoke = (signal: AbortSignal): Promise<BridgeCallResult> =>
      callBridge({
        bridgeScript,
        pythonPath: location.pythonPath,
        invocation: fullInvocation,
        cwd: options.workspaceRoot ?? engineRoot ?? undefined,
        timeoutMs: settings.timeoutSeconds * 1000,
        signal,
        maxOutputBytes:
          options.maxOutputBytes ??
          (invocation.command === 'capture-baseline'
            ? Math.min(96 * 1024 * 1024, settings.maxBaselineBytes * 2 + 1024 * 1024)
            : undefined),
      });

    const started = Date.now();
    let result: BridgeCallResult;
    if (options.silent) {
      const controller = new AbortController();
      const forwardAbort = (): void => controller.abort();
      options.signal?.addEventListener('abort', forwardAbort);
      try {
        result = await invoke(controller.signal);
      } finally {
        options.signal?.removeEventListener('abort', forwardAbort);
      }
    } else {
      result = await vscode.window.withProgress<BridgeCallResult>(
        {
          location: vscode.ProgressLocation.Notification,
          title: options.title,
          cancellable: true,
        },
        async (progress, token) => {
          const controller = new AbortController();
          const subscription = token.onCancellationRequested(() => controller.abort());
          const forwardAbort = (): void => controller.abort();
          options.signal?.addEventListener('abort', forwardAbort);
          const ticker = setInterval(() => {
            progress.report({ message: `${Math.round((Date.now() - started) / 1000)}s` });
          }, 1000);
          try {
            return await invoke(controller.signal);
          } finally {
            clearInterval(ticker);
            subscription.dispose();
            options.signal?.removeEventListener('abort', forwardAbort);
          }
        },
      );
    }

    this.finalize(result, options.workspaceRoot);
    return result;
  }

  /** Log + reflect a call outcome in the sidebar. Never logs payload bodies. */
  private finalize(result: BridgeCallResult, workspaceRoot?: string): void {
    const headline = describeFailure(result);
    if (result.ok) {
      this.log.info(`bridge ${result.command}: ok (${result.durationMs}ms, exit ${result.exitCode})`);
      this.sidebar.patchModel({ lastError: null, lastAction: `${result.command}: ok` });
      if (workspaceRoot) {
        this.sidebar.patchModel({ workspacePath: workspaceRoot });
      }
      // A successful bridge call IS a real engine observation: if we had a
      // recorded "engine unavailable" status, the engine just responded.
      const status = this.sidebar.getModel().status;
      if (status && !status.engineAvailable) {
        const updated: StoredStatus = {
          ...status,
          at: new Date().toISOString(),
          engineAvailable: true,
          headline: `Engine responded to the latest command (${result.command}).`,
        };
        void this.globalState.update('interlock.status', updated);
        this.sidebar.patchModel({ status: updated });
      }
      return;
    }
    this.log.error(
      `bridge ${result.command}: ${result.kind} (exit ${result.exitCode}, ${result.durationMs}ms) - ${headline}` +
        (result.hint ? ` | hint: ${result.hint}` : ''),
    );
    if (result.stderrExcerpt) {
      this.log.detail('bridge stderr (redacted):', result.stderrExcerpt);
    }
    this.sidebar.patchModel({
      lastError: headline,
      lastAction: `${result.command}: ${result.kind}`,
    });
  }

  private showFailure(result: BridgeCallResult): void {
    const detail = result.hint ? `${describeFailure(result)}\n\n${result.hint}` : describeFailure(result);
    void vscode.window
      .showErrorMessage(truncate(redact(detail), 600), 'Show Output')
      .then((choice) => {
        if (choice === 'Show Output') {
          this.log.show();
        }
      });
  }

  // -------------------------------------------------------------- git signal

  private async gitChangedFiles(workspaceRoot: string): Promise<string[] | null> {
    const run = await runProcess({
      command: 'git',
      args: ['status', '--porcelain'],
      cwd: workspaceRoot,
      timeoutMs: 10000,
      maxOutputBytes: 1024 * 1024,
    });
    if (run.spawnError || run.exitCode !== 0 || run.timedOut) {
      return null;
    }
    return run.stdout
      .split(/\r?\n/)
      .filter((line) => line.trim().length > 0)
      .slice(0, 200)
      .map((line) => {
        const raw = line.length > 3 ? line.slice(3) : line;
        const cleaned = raw.replace(/^"|"$/g, '');
        const arrow = cleaned.indexOf(' -> ');
        return (arrow >= 0 ? cleaned.slice(arrow + 4) : cleaned).trim();
      });
  }

  // ---------------------------------------------------------------- commands

  async checkInstallation(): Promise<void> {
    const settings = this.getSettings();
    const location = this.locate(settings);
    const workspaceRoot = (await this.pickWorkspace()) ?? undefined;

    if (!location.pythonPath) {
      this.sidebar.patchModel({
        lastError: 'No Python interpreter configured for Interlock.',
        warnings: location.issues,
      });
      void vscode.window.showErrorMessage(
        'Interlock: no interpreter. Set "interlock.pythonPath" to Python 3.11-3.14.',
      );
      return;
    }

    // Step 1: is the interpreter itself runnable and in range?
    const probe = await runProcess({
      command: location.pythonPath,
      args: ['-c', PYTHON_PROBE_CODE],
      timeoutMs: Math.min(15000, settings.timeoutSeconds * 1000),
      maxOutputBytes: 64 * 1024,
    });
    if (probe.spawnError) {
      const notFound = /ENOENT|not found|no such file/i.test(probe.spawnError);
      const message = notFound
        ? `Interpreter "${location.pythonPath}" was not found (${location.pythonSource}).`
        : `Interpreter "${location.pythonPath}" could not be started: ${redact(probe.spawnError)}`;
      this.sidebar.patchModel({
        status: {
          at: new Date().toISOString(),
          engineAvailable: false,
          engineVersion: null,
          engineRoot: null,
          pythonVersion: null,
          platformStatus: 'UNKNOWN',
          headline: message,
        },
        lastError: message,
      });
      this.refreshProtection();
      void vscode.window.showErrorMessage(
        message,
        'Edit Settings',
      ).then((choice) => {
        if (choice === 'Edit Settings') {
          void vscode.commands.executeCommand(
            'workbench.action.openSettings',
            'interlock.pythonPath',
          );
        }
      });
      this.log.error(message);
      return;
    }

    let pythonVersion: string | null = null;
    try {
      const parsed = JSON.parse(probe.stdout.trim()) as { version?: string };
      pythonVersion = typeof parsed.version === 'string' ? parsed.version : null;
    } catch {
      this.log.warn(`Interpreter probe returned unparseable output: ${probe.stdout.slice(0, 200)}`);
    }
    const inRange = isPythonInRange(pythonVersion);
    if (pythonVersion && !inRange) {
      this.log.warn(
        `Interpreter ${pythonVersion} is outside the engine's declared range (>=3.11,<3.15).`,
      );
    }

    // Step 2: engine availability through the bridge.
    const result = await this.call(
      { command: 'probe', workspace: workspaceRoot },
      { title: 'Interlock: checking installationâ€¦', workspaceRoot },
    );

    if (!result.ok || !result.result) {
      const status: StoredStatus = {
        at: new Date().toISOString(),
        engineAvailable: false,
        engineVersion: null,
        engineRoot: location.engineRoot ?? null,
        pythonVersion,
        platformStatus: 'UNKNOWN',
        headline: describeFailure(result),
      };
      await this.globalState.update('interlock.status', status);
      this.sidebar.patchModel({ status, warnings: location.issues });
      this.refreshProtection();
      this.showFailure(result);
      return;
    }

    const engine = asDict(result.result['engine']);
    const platform = asDict(result.result['platform']);
    const support = asDict(result.result['support']);
    const status: StoredStatus = {
      at: new Date().toISOString(),
      engineAvailable: true,
      engineVersion: asStr(engine['version']) ?? 'not installed as a package (source checkout)',
      engineRoot: asStr(engine['root']) ?? null,
      pythonVersion,
      platformStatus: statusLabelFrom(support['status']),
      headline: asStr(support['detail']) ?? '',
    };
    await this.globalState.update('interlock.status', status);

    const warnings = [
      ...location.issues,
      ...asStringArray(support['warnings']),
      ...(inRange ? [] : [`Python ${pythonVersion ?? 'unknown'} is outside the declared range.`]),
    ];
    this.sidebar.patchModel({
      status,
      workspacePath: workspaceRoot ?? null,
      workspaceSupportStatus: status.platformStatus,
      warnings,
    });

    await this.refreshBaselines();
    this.protectionCheckedAt = new Date().toISOString();
    this.refreshProtection();
    void vscode.window.showInformationMessage(
      `Interlock: engine ${status.engineVersion} on ${platform['platform'] ?? 'this machine'} ` +
        `(${statusLabelFrom(support['status'])}). Interpreter ${pythonVersion ?? 'unknown'}.`,
    );
  }

  async checkStatus(): Promise<void> {
    const workspaceRoot = await this.pickWorkspace();
    if (!workspaceRoot) {
      return;
    }
    const result = await this.call(
      { command: 'status', workspace: workspaceRoot },
      { title: 'Interlock: checking statusâ€¦', workspaceRoot },
    );
    if (!result.ok || !result.result) {
      this.showFailure(result);
      return;
    }

    const probe = asDict(result.result['probe']);
    const engine = asDict(probe['engine']);
    const support = asDict(probe['support']);
    const adapter = asDict(result.result['adapter']);
    const workspace = asDict(result.result['workspace']);
    const incidents = asDict(result.result['incident_history']);
    const docs = asStringArray(result.result['documentation']);

    
    const capabilitySummary = summarizeCapabilities(adapter);
    const authorized = asBool(workspace['authorized']);
    const status: StoredStatus = {
      at: new Date().toISOString(),
      engineAvailable: true,
      engineVersion: asStr(engine['version']) ?? 'source checkout',
      engineRoot: asStr(engine['root']) ?? null,
      pythonVersion: asStr(asDict(probe['python'])['version']),
      platformStatus: statusLabelFrom(support['status']),
      headline: capabilitySummary,
    };
    await this.globalState.update('interlock.status', status);

    this.sidebar.patchModel({
      status,
      workspacePath: workspaceRoot,
      workspaceAuthorized: authorized,
      workspaceSupportStatus: status.platformStatus,
      warnings: asStringArray(support['warnings']),
      incidentNote: asStr(incidents['reason']) ?? this.sidebar.getModel().incidentNote,
    });
    await this.refreshBaselines();
    this.protectionCheckedAt = new Date().toISOString();
    this.refreshProtection();

    const lines = [
      `Engine: ${status.engineVersion} at ${status.engineRoot ?? 'unknown'}`,
      `Adapter capabilities: ${capabilitySummary}`,
      `Workspace confinement: ${authorized ? 'authorized' : 'REFUSED'}`,
      `Platform: ${status.platformStatus}`,
      `Incident history: ${asBool(incidents['available']) ? 'available' : 'not available (engine limitation)'}`,
      docs.length > 0 ? `Local docs: ${docs.length} file(s) found` : 'Local docs: not found',
    ];
    void vscode.window.showInformationMessage(`Interlock status: ${lines.join(' Â· ')}`);
  }

  async analyzeWorkspace(): Promise<void> {
    const workspaceRoot = await this.pickWorkspace();
    if (!workspaceRoot) {
      return;
    }
    this.setAnalyzing('Checking this workspace and its recovery evidence…');
    try {
      const result = await this.call(
        { command: 'analyze', workspace: workspaceRoot },
        { title: 'Interlock: analyzing workspace…', workspaceRoot },
      );
      if (!result.ok || !result.result) {
        this.showFailure(result);
        return;
      }

      const probes = asArray(result.result['confinement_probes']).map(asDict);
      const passed = probes.filter((probe) => asBool(probe['pass'])).length;
      const confinementPass = asBool(result.result['confinement_pass']);
      const support = asDict(result.result['support']);
      const scan = asDict(result.result['scan']);
      const findings = asArray(result.result['findings']).map(asDict);
      const scanFiles = readScanFiles(scan);
      const files = scanFiles.map((entry) => entry.path);
      this.lastScanFiles = files;

      let gitFiles: string[] = [];
      let gitNote: string | null = null;
      const settings = this.getSettings();
      if (settings.showGitChanges) {
        gitFiles = (await this.gitChangedFiles(workspaceRoot)) ?? [];
        gitNote =
          gitFiles.length > 0 ? null : 'Git changes unavailable (not a git repository, or git is not installed).';
      } else {
        gitNote = 'Git change listing disabled in settings.';
      }

      this.sidebar.patchModel({
        workspacePath: workspaceRoot,
        workspaceAuthorized: confinementPass,
        workspaceSupportStatus: statusLabelFrom(support['status']),
        gitChangedFiles: gitFiles,
        gitNote,
        warnings: findings
          .map((finding) => `${asStr(finding['severity']) ?? 'info'}: ${asStr(finding['message']) ?? ''}`)
          .slice(0, 12),
        lastError: confinementPass ? null : 'Engine confinement probes FAILED - do not run recovery here.',
        lastAction: 'analyze: ok',
      });
      await this.refreshBaselines();

      // Protection evaluation from THIS real scan (engine file list + storage).
      const plan = await this.planForRun(workspaceRoot, scanFiles, settings);
      this.protectionEligible = plan.toCapture.length + plan.reused.length;
      this.protectionSkipped = plan.skipped.length;
      this.protectionCheckedAt = new Date().toISOString();
      this.refreshProtection();

      const detailLines = [
        `Confinement probes: ${passed}/${probes.length} as expected`,
        `${files.length} file(s) scanned`,
        `${findings.length} finding(s)`,
        `Platform: ${statusLabelFrom(support['status'])}`,
        gitNote ? 'git: n/a' : `git: ${gitFiles.length} changed`,
        `${plan.reused.length} file(s) with recovery evidence`,
        plan.skipped.length > 0 ? `${plan.skipped.length} excluded by policy` : null,
      ].filter((line): line is string => Boolean(line));
      if (confinementPass) {
        void vscode.window.showInformationMessage(`Interlock analyze: ${detailLines.join(' · ')}`);
      } else {
        const failed = probes
          .filter((probe) => !asBool(probe['pass']))
          .map((probe) => asStr(probe['probe']) ?? 'unknown')
          .join(', ');
        void vscode.window.showErrorMessage(
          `Interlock analyze: confinement probes failed (${failed}). Recovery is not safe here.`,
        );
        return;
      }

      // Documented automatic-protection checkpoint: a read-only analysis of
      // an authorized workspace establishes evidence for files that have
      // none. Files that already have evidence are never touched here.
      if (settings.automaticBaselineProtection && plan.toCapture.length > 0) {
        await this.establishProtection(workspaceRoot, plan, { automatic: true });
      }
    } finally {
      this.setAnalyzing(null);
    }
  }

  /**
   * "Protect Workspace": establish recovery evidence for every eligible file
   * the engine's read-only scan finds, disclosing up front what will and
   * will not be captured. Existing evidence is never overwritten here.
   */
  async protectWorkspace(): Promise<void> {
    const workspaceRoot = await this.pickWorkspace();
    if (!workspaceRoot) {
      return;
    }
    const settings = this.getSettings();
    this.setAnalyzing('Checking this workspace and its files…');
    try {
      const analysis = await this.call(
        { command: 'analyze', workspace: workspaceRoot },
        { title: 'Interlock: checking the workspace before protecting it…', workspaceRoot },
      );
      if (!analysis.ok || !analysis.result) {
        this.showFailure(analysis);
        return;
      }
      if (!asBool(analysis.result['confinement_pass'])) {
        this.sidebar.patchModel({
          workspaceAuthorized: false,
          lastError: 'Engine confinement probes FAILED - do not run recovery here.',
          lastAction: 'protect: refused',
        });
        void vscode.window.showErrorMessage(
          'Interlock: the engine refused this workspace (confinement check failed), so no ' +
            'baselines were captured. Nothing was changed.',
        );
        return;
      }
      this.sidebar.patchModel({ workspaceAuthorized: true, lastError: null });

      const scanFiles = readScanFiles(asDict(asDict(analysis.result)['scan']));
      this.lastScanFiles = scanFiles.map((entry) => entry.path);

      const plan = await this.planForRun(workspaceRoot, scanFiles, settings);
      this.protectionEligible = plan.toCapture.length + plan.reused.length;
      this.protectionSkipped = plan.skipped.length;
      this.protectionCheckedAt = new Date().toISOString();
      await this.refreshBaselines();
      this.refreshProtection();

      const disclosure = describeProtectionPlan(plan);
      if (plan.toCapture.length === 0) {
        void vscode.window.showInformationMessage(`Interlock: nothing to capture. ${disclosure}`);
        return;
      }
      const choice = await vscode.window.showWarningMessage(
        `Protect ${plan.toCapture.length} file(s) in this workspace?`,
        {
          modal: true,
          detail:
            `${disclosure}\n\n` +
            "Baselines are stored in Interlock's private extension storage; workspace files " +
            'are never modified, and this action never replaces existing evidence.',
        },
        'Capture baselines',
      );
      if (choice !== 'Capture baselines') {
        this.log.info('protect: cancelled at the disclosure dialog (nothing was captured).');
        return;
      }
      await this.establishProtection(workspaceRoot, plan, { automatic: false });
      this.inbox?.invalidate(
        'New recovery baselines were captured - refresh the Recovery Inbox to see them.',
      );
    } finally {
      this.setAnalyzing(null);
    }
  }

  /**
   * Execute a capture plan and report the outcome honestly: full success,
   * partial coverage (kept partial - never reported as full protection),
   * early cancellation, or failure.
   */
  private async establishProtection(
    workspaceRoot: string,
    plan: ProtectionPlan,
    options: { automatic: boolean },
  ): Promise<void> {
    if (plan.toCapture.length === 0) {
      if (options.automatic && (plan.reused.length > 0 || plan.skipped.length > 0)) {
        const note = `Automatic protection: ${describeProtectionPlan(plan)}`;
        this.sidebar.patchModel({ autoProtectionNote: note });
      }
      return;
    }

    this.setAnalyzing('Capturing recovery evidence for eligible files…');
    const outcome = await this.capturePlan(workspaceRoot, plan, {
      title: options.automatic
        ? `Interlock: automatically protecting ${plan.toCapture.length} file(s)…`
        : `Interlock: protecting ${plan.toCapture.length} file(s)…`,
    });

    const parts = [
      `captured ${outcome.captured} of ${plan.toCapture.length}`,
      `${plan.reused.length} already had evidence (kept)`,
      `${plan.skipped.length} skipped by policy`,
    ];
    if (outcome.failed.length > 0) {
      parts.push(`${outcome.failed.length} failed`);
    }
    if (outcome.cancelled) {
      parts.push('run cancelled before it finished');
    }
    const prefix = options.automatic ? 'Automatic protection:' : 'Protection run:';
    const complete = outcome.failed.length === 0 && !outcome.cancelled;
    const note = `${prefix} ${parts.join(' · ')}.`;
    this.sidebar.patchModel({
      autoProtectionNote: note,
      lastAction: complete ? 'protect: ok' : 'protect: partial',
    });

    if (outcome.failed.length > 0) {
      const detail = outcome.failed
        .slice(0, 4)
        .map((entry) => `${entry.path} (${entry.reason})`)
        .join(', ');
      this.log.warn(`protect: ${outcome.failed.length} capture(s) failed: ${redact(detail)}`);
      void vscode.window.showWarningMessage(
        `Interlock: ${note} Not covered: ${redact(truncate(detail, 400))}`,
      );
      return;
    }
    if (outcome.cancelled) {
      void vscode.window.showWarningMessage(
        `Interlock: ${note} The remaining files have no recovery evidence yet - run ` +
          '"Interlock: Protect Workspace" again to finish.',
      );
      return;
    }
    void vscode.window.showInformationMessage(`Interlock: ${note}`);
  }

  /**
   * Capture the planned baselines under one progress notification. Every
   * stored document is re-loaded and its hash compared with what the engine
   * reported before it counts as evidence; read-back mismatches are failures.
   */
  private async capturePlan(
    workspaceRoot: string,
    plan: ProtectionPlan,
    options: { title: string },
  ): Promise<{
    captured: number;
    failed: Array<{ path: string; reason: string }>;
    cancelled: boolean;
  }> {
    const settings = this.getSettings();
    const captured: string[] = [];
    const failed: Array<{ path: string; reason: string }> = [];
    let cancelled = false;

    await vscode.window.withProgress<void>(
      {
        location: vscode.ProgressLocation.Notification,
        title: options.title,
        cancellable: true,
      },
      async (progress, token) => {
        for (let index = 0; index < plan.toCapture.length; index += 1) {
          if (token.isCancellationRequested) {
            cancelled = true;
            break;
          }
          const file = plan.toCapture[index];
          const controller = new AbortController();
          const subscription = token.onCancellationRequested(() => controller.abort());
          let result: BridgeCallResult;
          try {
            result = await this.call(
              {
                command: 'capture-baseline',
                workspace: workspaceRoot,
                resource: file.path,
                maxBytes: settings.maxBaselineBytes,
              },
              {
                title: `Interlock: capturing ${file.path}…`,
                workspaceRoot,
                silent: true,
                signal: controller.signal,
              },
            );
          } finally {
            subscription.dispose();
          }
          if (!result.ok || !result.result) {
            failed.push({
              path: file.path,
              reason: redact(truncate(describeFailure(result), 160)),
            });
            continue;
          }
          const snapshot = asDict(result.result['snapshot']);
          const engineHash = asStr(snapshot['hash']);
          // The ENGINE builds and seals the baseline document; the extension
          // stores exactly that document and never creates one itself.
          const document = toBaselineDocument(result.result['baseline_document']);
          if (!document) {
            failed.push({
              path: file.path,
              reason: 'engine did not return a sealed baseline document',
            });
            continue;
          }
          try {
            await this.storage.save(document);
            const stored = await this.storage.load(workspaceRoot, file.path);
            const storedHash = stored ? asStr(stored.snapshot['hash']) : null;
            if (!engineHash || storedHash !== engineHash) {
              failed.push({
                path: file.path,
                reason: 'stored baseline failed read-back verification',
              });
              continue;
            }
          } catch (error) {
            failed.push({ path: file.path, reason: redact(String(error)) });
            continue;
          }
          captured.push(file.path);
          progress.report({
            message: `${captured.length}/${plan.toCapture.length} files captured`,
          });
        }
      },
    );

    await this.refreshBaselines();
    this.protectionCheckedAt = new Date().toISOString();
    this.refreshProtection();
    return { captured: captured.length, failed, cancelled };
  }

  /** Storage-backed capture plan for this workspace (reuse vs capture vs skip). */
  private async planForRun(
    workspaceRoot: string,
    scanFiles: ScanFile[],
    settings: InterlockSettings,
  ): Promise<ProtectionPlan> {
    const summaries = await this.storage.summaries();
    const existing = summaries
      .filter((entry) => sameWorkspace(entry.workspace, workspaceRoot))
      .map((entry) => ({ resource: entry.resource, hash: entry.hash }));
    return planProtection(scanFiles, existing, {
      maxBaselineBytes: settings.maxBaselineBytes,
      exclusions: settings.baselineExclusions,
    });
  }

  async captureBaseline(): Promise<void> {
    const workspaceRoot = await this.pickWorkspace();
    if (!workspaceRoot) {
      return;
    }
    const resource = await this.resolveTarget(workspaceRoot, 'Select a file to baseline');
    if (!resource) {
      return;
    }
    const settings = this.getSettings();

    // Deliberate replacement only: this manual command is the ONE path that
    // may replace existing evidence, and it always asks first. The automatic
    // flows never overwrite a usable baseline.
    const existing = await this.storage.load(workspaceRoot, resource);
    if (existing) {
      const replace = await vscode.window.showWarningMessage(
        `Replace the existing baseline for ${resource}?`,
        {
          modal: true,
          detail:
            `An earlier baseline (captured ${
              existing.captured_at ?? 'at an unknown time'
            }) exists for this file.\n\n` +
            'Replacing it discards that before-state permanently. Automatic protection ' +
            'never replaces existing evidence.',
        },
        'Replace baseline',
      );
      if (replace !== 'Replace baseline') {
        this.log.info('capture: cancelled at the replace dialog (existing evidence kept).');
        return;
      }
    }
    try {
      const stat = await fsp.stat(path.join(workspaceRoot, resource));
      if (stat.size > settings.maxBaselineBytes) {
        void vscode.window.showErrorMessage(
          `Interlock: ${resource} is ${stat.size} bytes; the baseline limit is ` +
            `${settings.maxBaselineBytes} bytes. Raise "interlock.maxBaselineBytes" to store larger files ` +
            '(baselines include file contents in extension-private storage).',
        );
        return;
      }
    } catch (error) {
      void vscode.window.showErrorMessage(
        `Interlock: cannot read ${resource}: ${redact(String(error))}`,
      );
      return;
    }

    const result = await this.call(
      {
        command: 'capture-baseline',
        workspace: workspaceRoot,
        resource,
        maxBytes: settings.maxBaselineBytes,
      },
      { title: `Interlock: capturing baseline for ${resource}â€¦`, workspaceRoot },
    );
    if (!result.ok || !result.result) {
      this.showFailure(result);
      return;
    }

    const snapshot = asDict(result.result['snapshot']);
    // The ENGINE builds and seals the baseline document; the extension stores
    // exactly that document and never creates one itself.
    const document = toBaselineDocument(result.result['baseline_document']);
    if (!document) {
      this.log.error('capture-baseline returned no sealed baseline document; nothing was stored.');
      void vscode.window.showErrorMessage(
        'Interlock: the engine did not return a sealed baseline document; nothing was stored.',
      );
      return;
    }
    const file = await this.storage.save(document);
    this.log.info(`Baseline stored for ${resource} at ${file} (contents not logged).`);
    await this.refreshBaselines();
    this.protectionCheckedAt = new Date().toISOString();
    this.refreshProtection();
    await this.globalState.update('interlock.lastBaseline', {
      workspace: workspaceRoot,
      resource,
      at: asStr(document['captured_at']) ?? new Date().toISOString(),
    });
    this.inbox?.invalidate(
      'A new baseline was captured - refresh the Recovery Inbox to see it.',
    );

    const hash = asStr(snapshot['hash']) ?? '';
    void vscode.window.showInformationMessage(
      `Interlock: baseline captured for ${resource} (sha256 ${hash.slice(0, 12)}â€¦). ` +
        'Run Preview Recovery Plan after a change to see what recovery would restore.',
    );
  }

  /**
   * Preview Recovery: build a validated engine plan for every selected file
   * and open each one as a native VS Code side-by-side diff - the real file
   * on the left, the exact proposed recovery (hash-verified against the
   * stored baseline) on the right.
   *
   * Read-only by construction: nothing is written, no approver is asked, and
   * closing a diff never applies anything.
   */
  async previewRecoveryPlan(): Promise<void> {
    const plans = await this.runPreview({ openDiffs: true });
    if (!plans.length) {
      // No reviewable state exists - the sidebar must not offer "Recovery ready".
      this.sidebar.patchModel({ pendingPreview: null });
      return;
    }
    const decision = await vscode.window.showInformationMessage(
      `Interlock: preview ready for ${
        plans.length === 1 ? plans[0].resource : `${plans.length} files`
      } (read-only - nothing was applied). Review the side-by-side diff, then decide.`,
      'Apply Recovery',
      'View Recovery Plan',
    );
    if (decision === 'Apply Recovery') {
      await this.executeRecovery();
      return;
    }
    if (decision === 'View Recovery Plan') {
      await this.viewRecoveryPlan();
    }
  }

  /**
   * View Recovery Plan: the Recovery Report panel - a read-only report over
   * the same validated engine plans (counts, per-file states, safety checks,
   * collapsed technical details). It never executes a recovery and never
   * asks for approver identity; the side-by-side diff stays the review
   * experience and approval happens only in Apply Recovery.
   */
  async viewRecoveryPlan(): Promise<void> {
    let plans = this.previewed;
    if (!plans.length) {
      plans = await this.runPreview({ openDiffs: false });
    }
    if (!plans.length) {
      // With no folder open (already reported) or a cancelled folder choice
      // there is nothing to report. With exactly one open folder an empty
      // plan is real evidence ("no baseline captured yet") - show that
      // honestly as "Recovery unavailable" instead of silently doing nothing.
      const folders = vscode.workspace.workspaceFolders ?? [];
      if (folders.length !== 1) {
        return;
      }
      this.showRecoveryReport([]);
      return;
    }
    this.showRecoveryReport(plans);
  }

  /** Render (or re-render) the report panel for these plans. */
  private showRecoveryReport(plans: PlannedRecovery[]): void {
    const workspacePath =
      plans[0]?.workspace ?? vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? null;
    const model = buildRecoveryReport(plans, { nowMs: Date.now(), workspacePath });
    this.reportPanel().show(model);
  }

  private reportPanel(): RecoveryReportPanel {
    if (this.recoveryReport === null) {
      this.recoveryReport = new RecoveryReportPanel(
        {
          refresh: () => this.refreshRecoveryReport(),
          preview: (resource) => this.previewReportFile(resource),
        },
        this.log,
      );
      this.disposables.push(this.recoveryReport);
    }
    return this.recoveryReport;
  }

  /**
   * Refresh Report: re-observe every file of the current report with the
   * engine (the same validated per-file pipeline the preview uses) and
   * rebuild all counts and checks from that fresh evidence. If any file
   * cannot be re-observed the existing report stays on screen - a partial
   * refresh must not silently drop rows or pretend the failure was a result.
   */
  private async refreshRecoveryReport(): Promise<void> {
    const current = this.previewed;
    if (!current.length) {
      await this.viewRecoveryPlan();
      return;
    }
    const workspaceRoot = current[0].workspace;
    const refreshed: PlannedRecovery[] = [];
    for (const planned of current) {
      const fresh = await this.buildPlannedRecovery(workspaceRoot, planned.resource);
      if (!fresh) {
        void vscode.window.showWarningMessage(
          `Interlock: ${planned.resource} could not be re-observed; the report still shows the previously observed evidence. Refresh again after fixing the cause.`,
        );
        return;
      }
      refreshed.push(fresh);
    }
    this.rememberPreviews(workspaceRoot, refreshed);
    this.showRecoveryReport(refreshed);
  }

  /**
   * Open the native diff for one resource named by the report panel. The
   * panel already allow-listed it against the rendered model; this re-checks
   * that it is still one of the remembered, validated plans.
   */
  private async previewReportFile(resource: string): Promise<void> {
    const planned = this.previewed.find((entry) => entry.resource === resource);
    if (!planned) {
      void vscode.window.showWarningMessage(
        'Interlock: that file is not part of the current report. Refresh the report and try again.',
      );
      return;
    }
    await this.openRecoveryDiff(planned);
  }

  /**
   * Apply Recovery: review -> explicit approval -> engine -> independent verify.
   *
   * It only ever applies plans produced by {@link runPreview} (validated by
   * the engine, proposed contents hash-verified against the reviewed
   * baseline); the webview can never name a target. Immediately before
   * writing everything is re-checked: a fresh engine plan, the baseline
   * still being the reviewed one, and the workspace file still holding
   * exactly the bytes that were reviewed. Anything else invalidates the
   * preview instead of writing on top of it.
   */
  async executeRecovery(): Promise<void> {
    const workspaceRoot = await this.pickWorkspace();
    if (!workspaceRoot) {
      return;
    }
    let plans = this.freshPreviews(workspaceRoot);
    if (!plans.length) {
      // No reviewed preview: build one (and show its diffs) first. Apply
      // never picks a target of its own and never skips the reviewable step.
      plans = await this.runPreview({ openDiffs: true });
      if (!plans.length) {
        return;
      }
    }

    // 1) Re-observe with the engine NOW (fresh evidence + conflict guard) and
    //    confirm this is still the operation that was reviewed.
    const refreshed: PlannedRecovery[] = [];
    for (const planned of plans) {
      const fresh = await this.buildPlannedRecovery(workspaceRoot, planned.resource);
      if (!fresh) {
        // The failure was reported; nothing may proceed on stale proof.
        this.clearPreviews();
        this.sidebar.patchModel({ pendingPreview: null });
        return;
      }
      if (
        fresh.baselineHash !== planned.baselineHash ||
        fresh.proposed.hash !== planned.proposed.hash
      ) {
        this.clearPreviews();
        this.sidebar.patchModel({ pendingPreview: null });
        void vscode.window.showErrorMessage(
          `Interlock: the recovery evidence for ${planned.resource} changed since you ` +
            'reviewed it. Nothing was changed. Preview the recovery again to re-review.',
        );
        return;
      }
      refreshed.push(fresh);
    }

    // 2) The workspace must still hold exactly the reviewed bytes.
    for (const planned of refreshed) {
      const current = await this.readOptionalFile(planned.absolutePath);
      const staleness = staleAgainstCurrent(planned, current);
      if (staleness.stale) {
        this.clearPreviews();
        this.sidebar.patchModel({ pendingPreview: null });
        void vscode.window.showErrorMessage(
          `Interlock: the preview for ${planned.resource} is out of date ` +
            `(${staleness.reason ?? 'the file changed'}). Nothing was changed. ` +
            'Preview the recovery again.',
        );
        return;
      }
    }

    // 3) Only plans the engine itself declared applicable may be applied.
    const applicable = refreshed.filter(isApplicable);
    if (applicable.length !== refreshed.length) {
      const reasons = refreshed
        .filter((planned) => !isApplicable(planned))
        .map(
          (planned) =>
            `${planned.resource}: would_succeed=${planned.wouldSucceed}, ` +
            `conflict=${planned.conflict}, drift=${planned.drift}`,
        )
        .join('; ');
      void vscode.window.showWarningMessage(
        `Interlock will not run recovery (${reasons}). Nothing was changed.`,
      );
      return;
    }

    // 4) Explicit approval: one confirmation listing every affected file,
    //    its operation and the hashes involved. No typing required here.
    const applyLabel = 'Apply recovery';
    const withReferenceLabel = 'Apply with change/ticket reference…';
    const confirmation = await vscode.window.showWarningMessage(
      `Apply recovery to ${
        applicable.length === 1 ? applicable[0].resource : `${applicable.length} files`
      }?`,
      { modal: true, detail: summarizePlans(applicable) },
      applyLabel,
      withReferenceLabel,
    );
    if (confirmation !== applyLabel && confirmation !== withReferenceLabel) {
      this.log.info('execute: cancelled at the approval dialog (nothing was changed).');
      return;
    }

    // A change/ticket reference is optional and asked for only when the user
    // explicitly asks to attach one - never on every recovery.
    let reference: string | null = null;
    if (confirmation === withReferenceLabel) {
      const typed = await vscode.window.showInputBox({
        prompt:
          'Optional change/ticket reference recorded with the approver identity (empty = none)',
        placeHolder: 'CHG-12345',
        validateInput: (value) =>
          value.trim().length <= 120 ? undefined : 'Keep the reference under 120 characters',
      });
      if (typed === undefined) {
        this.log.info('execute: cancelled at the reference prompt (nothing was changed).');
        return;
      }
      reference = typed.trim();
    }

    // 5) Approver identity (mandatory engine audit field, never invented):
    //    preconfigured setting -> this session's confirmed value -> the
    //    user's git identity -> a single explained prompt as last resort.
    const identity = await this.resolveApproverIdentity();
    if (!identity) {
      this.log.info('execute: cancelled without an approver identity (nothing was changed).');
      return;
    }
    const approvedBy = reference ? `${identity} (ref: ${reference})` : identity;

    // Execution begins: the "Recovery ready" card must not outlive it.
    this.sidebar.patchModel({ pendingPreview: null });
    for (const planned of applicable) {
      await this.applyPlannedRecovery(planned, approvedBy);
    }
    this.clearPreviews();
  }

  /**
   * Execute one reviewed plan with the real engine, then report the result
   * (engine verdict + independent verification) honestly.
   */
  private async applyPlannedRecovery(
    planned: PlannedRecovery,
    approvedBy: string,
    options: { quiet?: boolean } = {},
  ): Promise<ApplyOutcome> {
    const { workspace: workspaceRoot, resource } = planned;
    const baselineFile = this.storage.fileFor(workspaceRoot, resource);

    // The stored evidence must still be the exact one that was reviewed.
    const recheck = await this.storage.load(workspaceRoot, resource);
    const recheckHash = recheck ? asStr(recheck.snapshot['hash']) : null;
    if (!recheck || recheckHash !== planned.baselineHash) {
      this.log.warn('execute: baseline recheck failed (evidence changed since preview).');
      if (options.quiet !== true) {
        void vscode.window.showErrorMessage(
          `Interlock: the recovery evidence for ${resource} changed since the preview ` +
            `(baseline ${planned.baselineHash ?? 'unknown'} -> ${recheckHash ?? 'missing'}). ` +
            'Nothing was changed for this file. Preview the recovery again to re-observe.',
        );
      }
      return {
        resource,
        success: false,
        skipped: true,
        verified: false,
        message:
          'Skipped: the stored recovery evidence changed since it was reviewed - ' +
          'nothing was written for this file.',
        details: `baseline ${planned.baselineHash ?? 'unknown'} -> ${recheckHash ?? 'missing'}`,
      };
    }

    const result = await this.call(
      {
        command: 'execute',
        workspace: workspaceRoot,
        resource,
        baselineFile,
        evidenceFile: evidencePathFor(baselineFile),
        approvedBy,
      },
      {
        title: `Interlock: applying recovery to ${resource}…`,
        workspaceRoot,
        silent: options.quiet === true,
      },
    );

    const engineResult = result.result ? asDict(result.result) : null;
    const success =
      result.ok &&
      engineResult !== null &&
      asBool(engineResult['success']) === true &&
      asBool(engineResult['verified']) === true &&
      asBool(asDict(engineResult['independent_check'])['byte_exact']) === true;

    const verification = buildVerification(workspaceRoot, resource, engineResult, success);
    await this.globalState.update('interlock.verification', verification);
    this.sidebar.patchModel({ verification });
    this.refreshProtection();

    if (success) {
      this.log.info(`execute: recovery applied and independently verified for ${resource}.`);
      if (options.quiet !== true) {
        void vscode.window.showInformationMessage(
          `Interlock: recovery applied to ${resource} and verified byte-exact ` +
            `(approved by ${approvedBy}).`,
        );
      }
      return {
        resource,
        success: true,
        skipped: false,
        verified: true,
        message:
          'Recovered and verified byte-exact: the engine restored the captured bytes and ' +
          'the extension re-checked the hash independently.',
        details: null,
      };
    }

    // Anything less than a fully verified restore is reported as a failure.
    const reason =
      result.kind === 'refused'
        ? `The engine refused recovery: ${result.message || 'conflict or safety check'}`
        : result.kind === 'verification_failed'
          ? 'Recovery ran but verification did NOT confirm a byte-exact restore - do not trust the file state.'
          : describeFailure(result);
    this.log.error(`execute: ${result.kind} - ${reason}`);
    if (options.quiet !== true) {
      void vscode.window.showErrorMessage(
        `Interlock: ${reason}${result.hint ? `\n\n${result.hint}` : ''}`,
      );
    }
    return {
      resource,
      success: false,
      skipped: false,
      verified: false,
      message: reason,
      details: result.hint ? `${reason} ${result.hint}` : reason,
    };
  }

  /**
   * The shared pipeline behind "Preview Recovery" and the review step of
   * "Apply Recovery": engine plan per selected file -> exact proposed
   * contents decoded from the stored baseline (hash re-verified) -> native
   * diff editors. Every file is planned and validated individually by the
   * engine; the UI never chooses a different target.
   */
  private async runPreview(options: { openDiffs: boolean }): Promise<PlannedRecovery[]> {
    const workspaceRoot = await this.pickWorkspace();
    if (!workspaceRoot) {
      return [];
    }
    const resources = await this.resolvePreviewTargets(workspaceRoot);
    if (!resources.length) {
      return [];
    }
    const plans: PlannedRecovery[] = [];
    for (const resource of resources) {
      const planned = await this.buildPlannedRecovery(workspaceRoot, resource);
      if (planned) {
        plans.push(planned);
      }
    }
    if (!plans.length) {
      this.clearPreviews();
      this.sidebar.patchModel({ pendingPreview: null });
      return [];
    }
    this.rememberPreviews(workspaceRoot, plans);
    if (options.openDiffs) {
      for (const planned of plans) {
        await this.openRecoveryDiff(planned);
      }
    }
    return plans;
  }

  /**
   * One validated engine plan plus the exact contents its baseline would
   * restore. Returns null (with the failure already reported) when no honest
   * preview can exist for this file.
   */
  private async buildPlannedRecovery(
    workspaceRoot: string,
    resource: string,
  ): Promise<PlannedRecovery | null> {
    const baseline = await this.storage.load(workspaceRoot, resource);
    if (!baseline) {
      // Recovery restores a BEFORE-state. If none was captured there is
      // nothing to restore - say so instead of faking a preview.
      const message = this.getSettings().automaticBaselineProtection
        ? `Interlock: no baseline for ${resource}, so there is nothing to restore. Run ` +
          '"Interlock: Protect Workspace" before the next change - automatic protection ' +
          'captures evidence BEFORE changes happen, it cannot recreate a lost before-state.'
        : `Interlock: no baseline for ${resource}. Capture a baseline before the agent ` +
          'modifies the file. (Automatic baseline protection is off.)';
      void vscode.window.showErrorMessage(message);
      return null;
    }
    const baselineFile = this.storage.fileFor(workspaceRoot, resource);
    const result = await this.call(
      { command: 'plan', workspace: workspaceRoot, resource, baselineFile },
      { title: `Interlock: building recovery preview for ${resource}…`, workspaceRoot },
    );
    if (!result.ok || !result.result) {
      this.showFailure(result);
      return null;
    }
    return planFromEngineResult({
      workspace: workspaceRoot,
      resource,
      absolutePath: path.join(workspaceRoot, ...resource.split('/')),
      evidenceFile: evidencePathFor(baselineFile),
      summary: readPlanSummary(result.result),
      baselineSnapshot: baseline.snapshot,
      report: result.result,
    });
  }

  /**
   * Open the native VS Code diff for one planned recovery: the real file on
   * the left, the exact proposed contents (in-memory, read-only) on the
   * right. Files whose exact contents cannot honestly be shown (binary,
   * truncated capture, hash mismatch) are reported instead of faked.
   */
  private async openRecoveryDiff(planned: PlannedRecovery): Promise<void> {
    if (!planned.diffable || planned.proposed.text === null) {
      void vscode.window.showWarningMessage(
        `Interlock: ${planned.resource} cannot be shown as a text diff - ` +
          `${planned.proposed.limitation ?? 'the exact proposed contents are unavailable'}. ` +
          'Use "View Recovery Plan" for the hashes and evidence.',
      );
      return;
    }
    const proposed = this.recoveryDocs.propose(
      planned.resource,
      planned.proposed.hash ?? 'unverified',
      planned.proposed.text,
    );
    const left = planned.currentExists
      ? vscode.Uri.file(planned.absolutePath)
      : this.recoveryDocs.missingDocument(planned.resource);
    // The built-in diff editor: left = the real file (or an explicit empty
    // stand-in when it was deleted), right = the read-only proposed contents.
    await vscode.commands.executeCommand(
      'vscode.diff',
      left,
      proposed,
      diffTitle(planned.resource),
    );
  }

  /**
   * Pick the files to preview. Everything with stored recovery evidence is
   * offered (multi-select), so a multi-file preview is a deliberate choice;
   * the engine still plans and validates each file on its own.
   */
  private async resolvePreviewTargets(workspaceRoot: string): Promise<string[]> {
    const summaries = await this.storage.summaries();
    const inWorkspace = summaries.filter((entry) => sameWorkspace(entry.workspace, workspaceRoot));
    if (inWorkspace.length === 0) {
      // No evidence yet: fall back to the normal picker so the user gets the
      // honest "capture a baseline first" message for whatever they pick.
      const single = await this.resolveTarget(workspaceRoot, 'Select the file to preview');
      return single ? [single] : [];
    }
    if (inWorkspace.length === 1) {
      return [inWorkspace[0].resource];
    }
    const picks: Array<vscode.QuickPickItem & { resource?: string; other?: boolean }> = [
      ...inWorkspace.map((entry) => ({
        label: entry.resource,
        description: entry.capturedAt
          ? `baseline ${entry.capturedAt}${entry.size === null ? '' : ` · ${entry.size} bytes`}`
          : 'baseline captured',
        detail: entry.hash ? `sha256 ${entry.hash.slice(0, 12)}…` : undefined,
        resource: entry.resource,
      })),
      {
        label: 'Other file…',
        description: 'preview a file without stored evidence',
        other: true,
      },
    ];
    const selected = await vscode.window.showQuickPick(picks, {
      title: 'Select the file(s) to preview',
      placeHolder: 'Recovery only ever targets files inside this workspace',
      canPickMany: true,
    });
    if (!selected) {
      return [];
    }
    const chosen = Array.isArray(selected) ? selected : [selected];
    const resources = chosen
      .map((entry) => entry.resource)
      .filter((entry): entry is string => typeof entry === 'string');
    if (chosen.some((entry) => entry.other)) {
      const single = await this.resolveTarget(workspaceRoot, 'Select the file to preview');
      if (single && !resources.includes(single)) {
        resources.push(single);
      }
    }
    return resources;
  }

  /** Remember the reviewed plans and surface the "Recovery ready" card. */
  private rememberPreviews(workspaceRoot: string, plans: PlannedRecovery[]): void {
    this.recoveryDocs.clear(); // supersede the previous session's documents
    this.previewed = plans;
    this.sidebar.patchModel({
      pendingPreview: plans.every(isApplicable)
        ? {
            workspace: workspaceRoot,
            resource: plans[0].resource,
            resources: plans.map((planned) => planned.resource),
            at: new Date().toISOString(),
            wouldSucceed: true,
          }
        : null,
    });
  }

  /** Drop the reviewed plans and their virtual documents. */
  private clearPreviews(): void {
    this.recoveryDocs.clear();
    this.previewed = [];
  }

  /** Reviewed plans that still apply to this workspace and are still in date. */
  private freshPreviews(workspaceRoot: string): PlannedRecovery[] {
    const preview = this.sidebar.getModel().pendingPreview;
    if (!previewIsFresh(workspaceRoot, preview, Date.now())) {
      return [];
    }
    return this.previewed.filter((planned) => planned.workspace === workspaceRoot);
  }

  /** File bytes, or null when the file is missing/unreadable right now. */
  private async readOptionalFile(absolutePath: string): Promise<Buffer | null> {
    try {
      return await fsp.readFile(absolutePath);
    } catch {
      return null;
    }
  }

  /**
   * The approver identity the engine records in its audit result. The engine
   * refuses a recovery without a non-empty identity, so this resolves the
   * most trusted value available and only ever asks the user as a last
   * resort:
   *   1. `interlock.approverIdentity` (preconfigured - used silently);
   *   2. the identity confirmed earlier in this session (asked once);
   *   3. the user's git `user.name` (a real identity provider, confirmed
   *      with one click instead of typed);
   *   4. a single modal prompt, explained as an engine requirement.
   * Nothing is ever invented and no identity is silently assumed.
   */
  private async resolveApproverIdentity(): Promise<string | null> {
    const settings = this.getSettings();
    if (settings.approverIdentity) {
      this.log.info('execute: approver identity taken from interlock.approverIdentity.');
      return settings.approverIdentity;
    }
    if (this.sessionApprover) {
      return this.sessionApprover;
    }
    const gitIdentity = await this.gitUserIdentity();
    if (gitIdentity) {
      const use = await vscode.window.showWarningMessage(
        `Interlock records an approver identity in the engine's audit result. Use your ` +
          `configured git identity "${gitIdentity}"?`,
        {
          modal: true,
          detail:
            'Taken from git config user.name. Set "interlock.approverIdentity" to use a ' +
            'different identity without this question.',
        },
        'Use this identity',
        'Enter another…',
      );
      if (use === 'Use this identity') {
        this.sessionApprover = gitIdentity;
        return gitIdentity;
      }
      if (use !== 'Enter another…') {
        return null; // cancelled - an identity is never invented
      }
    }
    const typed = await vscode.window.showInputBox({
      title: 'Confirm Recovery Approver',
      prompt:
        'This identity is recorded in the recovery audit record - nothing has ' +
        'been changed yet.',
      placeHolder: 'Enter your name or approved identity',
      validateInput: (value) =>
        value.trim().length > 0 ? undefined : 'An approver identity is required',
    });
    if (!typed || !typed.trim()) {
      return null;
    }
    this.sessionApprover = typed.trim();
    return this.sessionApprover;
  }

  /** The user's configured git identity, when the git extension has one. */
  private async gitUserIdentity(): Promise<string | null> {
    try {
      const extension = vscode.extensions.getExtension<{
        getConfiguration?: (section: string) => {
          get?: <T>(key: string) => T | undefined;
        } | undefined;
      }>('vscode.git');
      if (!extension) {
        return null;
      }
      const api = await extension.activate();
      const configuration = api?.getConfiguration?.('user');
      const name = configuration?.get?.<string>('name');
      const trimmed = typeof name === 'string' ? name.trim() : '';
      return trimmed.length > 0 ? trimmed : null;
    } catch {
      return null; // git missing/unconfigured is not an error - just unavailable
    }
  }

  /**
   * Recovery Inbox: a tab that lists what changed in this workspace, lets the
   * user select files (individually, by folder, by filter or all eligible
   * ones) and recover them in a reviewed, explicitly confirmed batch.
   *
   * The inbox never decides what is safe: it asks the engine for the
   * eligibility of every changed file and re-validates each file again
   * immediately before it is written.
   */
  async openRecoveryInbox(): Promise<void> {
    if (this.inbox === null) {
      this.inbox = new RecoveryInboxController(this.inboxDeps());
      this.disposables.push(this.inbox);
    }
    await this.inbox.open();
  }

  /** Everything the inbox controller needs - no engine logic lives here. */
  private inboxDeps(): InboxDeps {
    return {
      workspace: () => this.pickWorkspace(),
      call: (invocation, options) => this.call(invocation, options),
      storage: this.storage,
      baselineExclusions: () => this.getSettings().baselineExclusions,
      log: this.log,
      previewFile: (workspaceRoot, resource) => this.inboxPreview(workspaceRoot, resource),
      openDiff: (planned) => this.openRecoveryDiff(planned),
      readOptionalFile: (absolutePath) => this.readOptionalFile(absolutePath),
      resolveApproverIdentity: () => this.resolveApproverIdentity(),
      applyPlanned: (planned, approvedBy, options) =>
        this.applyPlannedRecovery(planned, approvedBy, { quiet: options.quiet }),
      openFile: (absolutePath) => this.openWorkspaceFile(absolutePath),
      verifyRecovery: () => this.verifyRecovery(),
      tempDir: () => this.context.globalStorageUri.fsPath,
      note: (action) => this.sidebar.patchModel({ lastAction: action }),
      createPanel: (host) => new RecoveryInboxPanel(host, this.log),
      createWatcher: (workspaceRoot) => {
        const watcher = vscode.workspace.createFileSystemWatcher(
          new vscode.RelativePattern(workspaceRoot, '**/*'),
        );
        return {
          dispose: () => watcher.dispose(),
          onDidCreate: (handler) => watcher.onDidCreate(handler),
          onDidChange: (handler) => watcher.onDidChange(handler),
          onDidDelete: (handler) => watcher.onDidDelete(handler),
        };
      },
      confirmRecovery: async (request) => {
        const applyLabel = 'Apply recovery';
        const withReferenceLabel = 'Apply with change/ticket reference…';
        const choice = await vscode.window.showWarningMessage(
          `Apply recovery to ${
            request.count === 1 ? 'the selected file' : `${request.count} files`
          }?`,
          { modal: true, detail: request.detail },
          applyLabel,
          withReferenceLabel,
        );
        if (choice === applyLabel) {
          return 'apply';
        }
        if (choice === withReferenceLabel) {
          return 'apply-with-reference';
        }
        return 'cancel';
      },
      askReference: async () => {
        const typed = await vscode.window.showInputBox({
          prompt:
            'Optional change/ticket reference recorded with the approver identity (empty = none)',
          placeHolder: 'CHG-12345',
          validateInput: (value) =>
            value.trim().length <= 120 ? undefined : 'Keep the reference under 120 characters',
        });
        return typed === undefined ? null : typed;
      },
    };
  }

  /** Preview one inbox row through the existing, honest diff pipeline. */
  private async inboxPreview(workspaceRoot: string, resource: string): Promise<void> {
    const planned = await this.buildPlannedRecovery(workspaceRoot, resource);
    if (!planned) {
      return; // the failure was already reported by buildPlannedRecovery
    }
    await this.openRecoveryDiff(planned);
  }

  /** Open a restored file in the editor. */
  private async openWorkspaceFile(absolutePath: string): Promise<void> {
    await vscode.window.showTextDocument(vscode.Uri.file(absolutePath));
  }

  async verifyRecovery(): Promise<void> {
    const workspaceRoot = await this.pickWorkspace();
    if (!workspaceRoot) {
      return;
    }
    const resource = await this.resolveTarget(workspaceRoot, 'Select the file to verify');
    if (!resource) {
      return;
    }
    const baselineFile = this.storage.fileFor(workspaceRoot, resource);
    if (!(await this.storage.load(workspaceRoot, resource))) {
      void vscode.window.showErrorMessage(
        `Interlock: no baseline for ${resource} - verification needs a captured before-state.`,
      );
      return;
    }

    const result = await this.call(
      { command: 'verify', workspace: workspaceRoot, resource, baselineFile },
      { title: `Interlock: verifying ${resource}â€¦`, workspaceRoot },
    );
    const engineResult = result.result ? asDict(result.result) : null;
    const success = result.ok && engineResult !== null && asBool(engineResult['success']) === true;
    const verification = buildVerification(workspaceRoot, resource, engineResult, success);
    await this.globalState.update('interlock.verification', verification);
    this.sidebar.patchModel({ verification });
    this.refreshProtection();

    if (success) {
      void vscode.window.showInformationMessage(
        `Interlock: ${resource} matches the captured baseline (byte-exact).`,
      );
      return;
    }
    const details = verification.checksFailed.length
      ? `failed checks: ${verification.checksFailed.join(', ')}`
      : verification.reason;
    void vscode.window.showErrorMessage(`Interlock: verification FAILED for ${resource} - ${details}`);
  }

  async openDocumentation(): Promise<void> {
    const settings = this.getSettings();
    const location = this.locate(settings);
    const roots = [
      ...(location.engineRoot ? [location.engineRoot] : []),
      ...(vscode.workspace.workspaceFolders ?? []).map((folder) => folder.uri.fsPath),
    ];

    const localDocs: Array<{ label: string; fsPath: string }> = [];
    for (const relative of DOC_RELATIVE_PATHS) {
      for (const root of roots) {
        const contained = resolveWithin(root, path.join(root, relative));
        if (!contained) {
          continue; // stays inside the authorized root or it is refused
        }
        const absolute = path.join(root, contained);
        if (fs.existsSync(absolute)) {
          localDocs.push({ label: path.basename(absolute), fsPath: absolute });
          break;
        }
      }
    }

    const options: Array<vscode.QuickPickItem & { fsPath?: string; url?: string }> = localDocs.map(
      (doc) => ({ label: `$(file-code) ${doc.label}`, description: doc.fsPath, fsPath: doc.fsPath }),
    );
    const urlAllowed = isAllowedDocumentationUrl(
      REPOSITORY_URL,
      settings.allowedDocumentationUrls,
    );
    if (urlAllowed) {
      options.push({
        label: '$(globe) Repository documentation',
        description: REPOSITORY_URL,
        url: REPOSITORY_URL,
      });
    }
    if (options.length === 0) {
      void vscode.window.showErrorMessage(
        'Interlock: no documentation found. Set interlock.engineRoot to the engine checkout ' +
          '(docs/ lives there), or add an https URL to interlock.allowedDocumentationUrls.',
      );
      return;
    }

    const picked = await vscode.window.showQuickPick(options, {
      title: 'Interlock documentation',
      placeHolder: 'Safety, first-run instructions, limitations, and troubleshooting',
    });
    if (!picked) {
      return;
    }
    if (picked.fsPath) {
      const document = await vscode.workspace.openTextDocument(picked.fsPath);
      await vscode.window.showTextDocument(document, { preview: true });
      return;
    }
    if (picked.url) {
      if (!isAllowedDocumentationUrl(picked.url, settings.allowedDocumentationUrls)) {
        void vscode.window.showErrorMessage('Interlock: documentation URL is not on the allow-list.');
        return;
      }
      await vscode.env.openExternal(vscode.Uri.parse(picked.url));
    }
  }

  // --------------------------------------------------------------- internals

  private async refreshBaselines(): Promise<void> {
    const summaries = await this.storage.summaries();
    const currentRoot = this.sidebar.getModel().workspacePath;
    const scoped = currentRoot
      ? summaries.filter((entry) => entry.workspace === currentRoot)
      : summaries;
    this.sidebar.patchModel({
      baselineCount: scoped.length,
      recentBaselines: scoped,
    });
  }

  /** Flip the protection card into its "Analyzing" state (or recompute it). */
  private setAnalyzing(detail: string | null): void {
    this.analyzing = detail !== null;
    this.analyzingDetail = detail;
    this.refreshProtection();
  }

  /**
   * Recompute the protection card from real evidence. This is the only place
   * the model's protection state is written, and it never claims "Protected"
   * without stored baselines plus an authorized workspace - engine
   * availability alone is never enough.
   */
  private refreshProtection(): void {
    const model = this.sidebar.getModel();
    const protection = evaluateProtection({
      workspacePath: model.workspacePath,
      workspaceAuthorized: model.workspaceAuthorized,
      baselineCount: model.baselineCount,
      engineStatus: model.status,
      verification: model.verification,
      analyzing: this.analyzing,
      analyzingDetail: this.analyzingDetail,
      eligibleFiles: this.protectionEligible,
      skippedFiles: this.protectionSkipped,
      checkedAt: this.protectionCheckedAt,
    });
    if (JSON.stringify(model.protection) === JSON.stringify(protection)) {
      return; // unchanged - avoid pointless model churn on every bridge call
    }
    this.sidebar.patchModel({ protection });
  }

  /**
   * Hydration without engine calls: scope stored baselines to the current
   * folder and derive the protection card from persisted evidence only.
   * Reads extension-private storage; no subprocess, no workspace scan.
   */
  async initializeFromStorage(): Promise<void> {
    this.getSettings();
    this.protectionWorkspace = this.sidebar.getModel().workspacePath;
    await this.refreshBaselines();
    this.protectionCheckedAt = new Date().toISOString();
    this.refreshProtection();
  }

  /** The open-folder set changed: drop every per-workspace derived value. */
  async workspaceChanged(): Promise<void> {
    const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? null;
    const previous = this.sidebar.getModel();
    const changed = folder !== previous.workspacePath;
    this.protectionWorkspace = folder;
    this.protectionEligible = null;
    this.protectionSkipped = 0;
    this.protectionCheckedAt = null;
    this.inbox?.invalidate('The workspace folders changed - refresh the Recovery Inbox.');
    this.sidebar.patchModel({
      workspacePath: folder,
      workspaceAuthorized: changed ? null : previous.workspaceAuthorized,
      pendingPreview:
        previous.pendingPreview && previous.pendingPreview.workspace !== folder
          ? null
          : previous.pendingPreview,
      verification:
        previous.verification && previous.verification.workspace !== folder
          ? null
          : previous.verification,
    });
    await this.refreshBaselines();
    this.refreshProtection();
  }

}

// -------------------------------------------------------------- pure helpers

function buildVerification(
  workspace: string,
  resource: string,
  engineResult: Record<string, unknown> | null,
  success: boolean,
): StoredVerification {
  const engineVerification = engineResult ? asDict(engineResult['engine_verification']) : {};
  const details = asDict(engineVerification['details']);
  const independent = engineResult ? asDict(engineResult['independent_check']) : {};
  const checksPassed = asStringArray(details['checks_passed']);
  const checksFailed = asStringArray(details['checks_failed']);
  const reason =
    asStr(details['reason']) ??
    (success ? 'verified' : engineResult === null ? 'no engine result' : 'not verified');
  return {
    workspace,
    resource,
    at: new Date().toISOString(),
    success,
    reason,
    checksPassed,
    checksFailed: checksFailed.length
      ? checksFailed
      : success
        ? []
        : [
            ...(asBool(independent['byte_exact']) ? [] : ['byte_exact_hash_match']),
            ...(engineResult === null ? ['no_engine_result'] : []),
          ],
  };
}

function summarizeCapabilities(adapter: Record<string, unknown>): string {
  const flags = [
    ['can_capture_before_state', 'capture'],
    ['can_compute_delta', 'diff'],
    ['can_detect_drift', 'drift'],
    ['can_simulate', 'simulate'],
    ['can_compensate', 'recover'],
    ['can_verify', 'verify'],
    ['supports_idempotency', 'idempotent'],
    ['supports_safe_merge', 'safe-merge'],
  ] as const;
  const present = flags.filter(([key]) => asBool(adapter[key])).map(([, label]) => label);
  return present.length > 0 ? present.join(', ') : 'no capabilities reported';
}

function statusLabelFrom(value: unknown): string {
  const status = asStr(value);
  switch (status) {
    case 'tested_primary':
      return statusLabel('tested_primary');
    case 'declared_ci_pending':
      return statusLabel('declared_ci_pending');
    case 'unsupported':
      return statusLabel('unsupported');
    case 'untested':
      return statusLabel('untested');
    default:
      return 'UNKNOWN';
  }
}

function isPythonInRange(version: string | null): boolean {
  if (!version) {
    return false;
  }
  const match = /^(\d+)\.(\d+)/.exec(version);
  if (!match) {
    return false;
  }
  const major = Number(match[1]);
  const minor = Number(match[2]);
  if (major !== 3) {
    return false;
  }
  return minor >= 11 && minor <= 14;
}

// Value coercion helpers live in ./jsonValues; re-exported here for
// compatibility with existing importers of this module.
export { asArray, asBool, asDict, asStr, asStringArray } from './jsonValues';

/**
 * Normalize the engine's scan file list (`{path, size}` entries) for capture
 * planning. Entries without a path are dropped; a missing size counts as 0.
 */
export function readScanFiles(scan: Record<string, unknown>): ScanFile[] {
  return asArray(scan['files'])
    .map((entry) => {
      const dict = asDict(entry);
      const rel = asStr(dict['path']);
      if (!rel) {
        return null;
      }
      const raw = dict['size'];
      const size = typeof raw === 'number' && Number.isFinite(raw) && raw >= 0 ? raw : 0;
      return { path: rel, size };
    })
    .filter((entry): entry is ScanFile => entry !== null);
}

