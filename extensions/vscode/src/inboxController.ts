/**
 * Recovery Inbox controller: the trusted layer that owns the inbox state.
 *
 * The webview never decides what may be recovered. It only sends intents
 * ("select these resources", "recover the selection", "open this diff"); this
 * controller re-validates every intent against its own model, re-derives the
 * executable set from the engine's verdicts and performs the write only
 * after an explicit, scoped confirmation.
 *
 * Flow:
 *   scan  -> discovery (classification + evidence validation) -> engine
 *            eligibility assessment (chunked, cancellable, read-only)
 *   review-> a fresh engine plan per candidate (with preview-time evidence),
 *            so the review shows exactly what would be written
 *   apply -> revalidate every file immediately before its write, ask for
 *            approval, record the truthful approver identity, execute per
 *            file, and report each file's real outcome
 */

import * as fsp from 'fs/promises';
import * as path from 'path';

import { BridgeCallResult, BridgeInvocation } from './bridge';
import { asArray, asBool, asDict, asStr } from './jsonValues';
import {
  AssessResult,
  DiscoveryCandidate,
  probeFile,
  runDiscovery,
  walkWorkspace,
} from './inboxDiscovery';
import { isSensitiveResource } from './protection';
import type { RecoveryInboxPanelHost } from './recoveryInboxPanel';
import {
  ApplyOutcome,
  InboxReview,
  InboxRunResults,
  InboxState,
  InboxViewState,
  applyStaleToReview,
  buildReviewScope,
  buildViewState,
  reviewApprovalDetail,
  runEntryFromOutcome,
  skippedRunEntry,
} from './recoveryInbox';
import { InboxMessage, InboxUpdate } from './recoveryInboxHtml';
import {
  PlannedRecovery,
  isApplicable,
  planFromEngineResult,
  staleAgainstCurrent,
} from './recoveryPlan';
import { readPlanSummary } from './recoveryPlanReport';
import { BaselineStore, evidencePathFor } from './state';

/** Files planned per engine call (keeps every call well inside the timeout). */
const PLAN_CHUNK = 20;

/** The panel the controller drives (the real webview panel, or a test double). */
export interface InboxPanelHandle {
  show(view: InboxViewState): void;
  /** Focus the open tab without reloading its document. */
  reveal(): void;
  update(update: InboxUpdate): void;
  isOpen(): boolean;
  dispose(): void;
}

/** A workspace watcher the controller can dispose (real one, or a test double). */
export interface InboxWatcherHandle {
  dispose(): void;
  onDidCreate(handler: () => void): void;
  onDidChange(handler: () => void): void;
  onDidDelete(handler: () => void): void;
}

/** The explicit approval the user must give before anything is written. */
export type InboxApproval = 'apply' | 'apply-with-reference' | 'cancel';

/** Everything the controller needs from the extension host. */
export interface InboxDeps {
  /** The workspace the inbox operates on (null when the user cancels). */
  workspace(): Promise<string | null>;
  /** One engine call through the shared bridge. */
  call(
    invocation: BridgeInvocation,
    options: {
      title: string;
      workspaceRoot?: string;
      silent?: boolean;
      signal?: AbortSignal;
      maxOutputBytes?: number;
    },
  ): Promise<BridgeCallResult>;
  storage: BaselineStore;
  /** Extra capture exclusions from the settings (sensitive policy always applies). */
  baselineExclusions(): string[];
  log: { info(message: string): void; warn(message: string): void; error(message: string): void };
  /** One-file preview through the existing diff pipeline (writes evidence). */
  previewFile(workspace: string, resource: string): Promise<void>;
  /** Open the native diff for a planned recovery. */
  openDiff(planned: PlannedRecovery): Promise<void>;
  readOptionalFile(absolutePath: string): Promise<Buffer | null>;
  resolveApproverIdentity(): Promise<string | null>;
  /** Execute one reviewed plan; returns the honest per-file outcome. */
  applyPlanned(
    planned: PlannedRecovery,
    approvedBy: string,
    options: { quiet: boolean },
  ): Promise<ApplyOutcome>;
  /** Open a restored file in the editor. */
  openFile(absolutePath: string): Promise<void>;
  /** Run the existing Verify Recovery command. */
  verifyRecovery(): Promise<void>;
  /** A private directory for the controller's temporary manifests. */
  tempDir(): string;
  /** Show a short status line in the sidebar (optional). */
  note(action: string): void;
  /** The editor panel the inbox renders into. */
  createPanel(host: RecoveryInboxPanelHost): InboxPanelHandle;
  /** Watches the workspace so a changed file invalidates the scan. */
  createWatcher(workspace: string): InboxWatcherHandle;
  /**
   * The explicit approval gate. The host shows a modal that states the exact
   * scope; only 'apply'/'apply-with-reference' may write anything.
   */
  confirmRecovery(request: { scope: string; count: number; detail: string }): Promise<InboxApproval>;
  /** Optional change/ticket reference (only when the user asked for one). */
  askReference(): Promise<string | null>;
}

interface PlanManyEntry {
  resource: string;
  ok: boolean;
  summary?: Record<string, unknown>;
  error?: { kind: string; message: string };
}

export class RecoveryInboxController {
  private panel: InboxPanelHandle | null = null;
  private state: InboxState | null = null;
  private workspace: string | null = null;
  private busy: string | null = null;
  private abort: AbortController | null = null;
  private watcher: InboxWatcherHandle | null = null;
  private watchedWorkspace: string | null = null;
  /** The mode the open document was rendered for (a mode change = new document). */
  private renderedMode: 'list' | 'review' | 'results' | null = null;
  /** Planned recoveries of the current review (used for diffs and execution). */
  private reviewPlans = new Map<string, PlannedRecovery>();

  constructor(private readonly deps: InboxDeps) {}

  dispose(): void {
    this.watcher?.dispose();
    this.watcher = null;
    this.abort?.abort();
    this.panel?.dispose();
    this.panel = null;
  }

  // ------------------------------------------------------------------ open

  /** Open (or reveal) the inbox and run the first scan. */
  async open(): Promise<void> {
    const workspace = await this.deps.workspace();
    if (workspace === null) {
      return;
    }
    this.workspace = workspace;
    this.state = new InboxState(workspace);
    if (this.panel === null) {
      // One panel for the whole session: a second click re-uses (and focuses)
      // the tab that is already open instead of stacking duplicates.
      this.panel = this.deps.createPanel({
        handle: (message) => this.handle(message),
        ready: () => this.ready(),
      });
    }
    this.ensureWatcher(workspace);
    this.sync();
    // The user asked for the inbox: make sure its tab is the visible, focused
    // one - even when it was already open.
    this.panel?.reveal();
    await this.runScan();
  }

  /** Mark the current scan stale (e.g. new baselines were captured). */
  invalidate(reason: string): void {
    if (this.state === null) {
      return;
    }
    this.state.markStale(reason);
    this.sync();
  }

  /**
   * The webview finished booting (or reloaded): hand it the current state, so
   * a freshly opened inbox never shows a stale view and the first click is
   * never swallowed.
   */
  ready(): void {
    this.sync();
  }

  // --------------------------------------------------------------- intents

  /**
   * Handle one validated intent from the webview. Intent handlers that do
   * real work return their promise, so a caller (and the tests) can await
   * the outcome instead of guessing.
   */
  handle(message: InboxMessage): Promise<void> | void {
    const state = this.state;
    if (state === null) {
      return;
    }
    switch (message.type) {
      case 'ready':
        return;
      case 'refresh':
        return this.runScan();
      case 'cancelScan':
        this.abort?.abort();
        return;
      case 'close':
        this.panel?.dispose();
        this.panel = null;
        return;
      case 'select': {
        if (message.add !== undefined) {
          state.select(message.add, 'add');
        }
        if (message.remove !== undefined) {
          state.select(message.remove, 'remove');
        }
        this.pushSelection();
        return;
      }
      case 'clearSelection':
        state.clearSelection();
        this.pushSelection();
        return;
      case 'preview':
        return this.previewResource(message.resource ?? '');
      case 'recoverSelected':
        return this.startReview('selected');
      case 'recoverAll':
        return this.startReview('all');
      case 'retry':
        return this.startReview('retry');
      case 'back':
        state.mode = 'list';
        state.review = null;
        this.reviewPlans.clear();
        this.sync();
        return;
      case 'confirm':
        return this.confirmReview();
      case 'viewDiff':
        return this.showDiff(message.resource ?? '');
      case 'openFile':
        return this.openResource(message.resource ?? '');
      case 'verifyRecovery':
        return this.deps.verifyRecovery();
      default:
        return;
    }
  }

  // ------------------------------------------------------------------ scan

  private async runScan(): Promise<void> {
    if (this.busy !== null) {
      this.setNotice('A scan is already running.');
      return;
    }
    // A refresh keeps the workspace the inbox was opened for - the user is
    // never asked to pick a folder again for the same inbox.
    const workspace = this.workspace ?? (await this.deps.workspace());
    if (workspace === null) {
      return;
    }
    this.workspace = workspace;
    const state = new InboxState(workspace);
    this.state = state;
    this.reviewPlans.clear();
    state.beginScan();
    this.setBusy('Scanning the workspace…');
    this.sync();

    const controller = new AbortController();
    this.abort = controller;
    try {
      const outcome = await runDiscovery({
        workspace,
        nowMs: Date.now(),
        baselines: async () => {
          // One read per baseline: the metadata and the stored document come
          // from the same pass, which is what keeps a large scan quick.
          const entries = await this.deps.storage.list(workspace);
          return entries.map((entry) => ({
            resource: entry.resource,
            file: entry.file,
            hash: entry.hash,
            size: entry.size,
            capturedAt: entry.capturedAt,
            snapshot: entry.snapshot,
          }));
        },
        loadDoc: (resource) => this.deps.storage.load(workspace, resource),
        probe: (absolutePath) => probeFile(absolutePath),
        walk: () => walkWorkspace(workspace, { limit: 50_000 }),
        excludeFile: (rel) => {
          const decision = isSensitiveResource(rel, this.deps.baselineExclusions());
          return decision.excluded ? (decision.reason ?? 'excluded by policy') : null;
        },
        assess: async (candidates, onProgress) =>
          this.assess(candidates, onProgress, controller.signal),
        onProgress: (update) => this.pushProgress(update.phase, update.done, update.total),
        signal: controller.signal,
      });

      if (outcome.status === 'error') {
        state.finishScan('error', outcome.error);
        this.deps.log.error(`inbox: scan failed - ${outcome.error ?? 'unknown error'}`);
      } else {
        state.applyDiscovery(outcome.records, outcome.coverage ?? emptyCoverage());
        state.applyAssessment(outcome.assessments);
        this.sync();
        if (outcome.assessmentStatus === 'complete' || outcome.assessmentStatus === 'none') {
          state.finishScan('done');
        } else if (outcome.assessmentStatus === 'cancelled') {
          state.finishScan(
            'cancelled',
            'The scan was cancelled before every file was assessed. Refresh to finish it.',
          );
        } else {
          state.finishScan(
            'cancelled',
            outcome.assessmentError ??
              'The engine could not assess every file, so eligibility is incomplete.',
          );
        }
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      state.finishScan('error', `The scan failed: ${message}`);
      this.deps.log.error(`inbox: scan failed - ${message}`);
    } finally {
      this.abort = null;
      this.setBusy(null);
      this.sync();
      this.deps.note('Recovery Inbox: scan finished');
    }
  }

  /** Engine eligibility for the changed candidates (read-only, chunked). */
  private async assess(
    candidates: DiscoveryCandidate[],
    onProgress: (done: number, total: number) => void,
    signal: AbortSignal,
  ): Promise<AssessResult[]> {
    const entries = await this.runPlanMany(
      candidates.map((candidate) => candidate.resource),
      false,
      onProgress,
      signal,
    );
    return entries.map((entry) =>
      entry.ok
        ? { resource: entry.resource, ok: true, summary: entry.summary }
        : {
            resource: entry.resource,
            ok: false,
            error: entry.error ?? { kind: 'internal_error', message: 'unknown engine failure' },
          },
    );
  }

  /**
   * One bulk engine call per chunk. The manifest is written to the
   * extension's private storage (never into the workspace) and removed
   * afterwards.
   */
  private async runPlanMany(
    resources: string[],
    saveEvidence: boolean,
    onProgress: (done: number, total: number) => void,
    signal: AbortSignal,
  ): Promise<PlanManyEntry[]> {
    const workspace = this.workspace;
    if (workspace === null || resources.length === 0) {
      return [];
    }
    const entries = resources.map((resource) => ({
      resource,
      baseline_file: this.deps.storage.fileFor(workspace, resource),
    }));
    const directory = path.join(this.deps.tempDir(), 'inbox');
    await fsp.mkdir(directory, { recursive: true });
    const manifest = path.join(directory, `plan-${Date.now()}-${Math.random().toString(16).slice(2)}.json`);
    await fsp.writeFile(manifest, JSON.stringify({ workspace, entries }), 'utf8');
    const out: PlanManyEntry[] = [];
    try {
      for (let offset = 0; offset < entries.length; offset += PLAN_CHUNK) {
        const result = await this.deps.call(
          {
            command: 'plan-many',
            workspace,
            resourcesFile: manifest,
            saveEvidence,
            offset,
            limit: PLAN_CHUNK,
          },
          {
            title: 'Interlock: validating recovery plans…',
            workspaceRoot: workspace,
            silent: true,
            signal,
            maxOutputBytes: 64 * 1024 * 1024,
          },
        );
        if (!result.ok || result.result === null) {
          if (result.kind === 'cancelled') {
            throw abortError();
          }
          throw new Error(result.message || 'The engine call failed.');
        }
        const payload = asDict(result.result);
        for (const item of asArray(payload['entries'])) {
          const entry = asDict(item);
          const resource = asStr(entry['resource']) ?? '';
          if (asBool(entry['ok']) === true) {
            out.push({ resource, ok: true, summary: asDict(entry['summary']) });
          } else {
            const error = asDict(entry['error']);
            out.push({
              resource,
              ok: false,
              error: {
                kind: asStr(error['kind']) ?? 'internal_error',
                message: asStr(error['message']) ?? 'The engine could not plan this file.',
              },
            });
          }
        }
        onProgress(Math.min(offset + PLAN_CHUNK, entries.length), entries.length);
      }
    } finally {
      await fsp.rm(manifest, { force: true }).catch(() => undefined);
    }
    return out;
  }

  // ---------------------------------------------------------------- review

  private async startReview(scope: 'selected' | 'all' | 'retry'): Promise<void> {
    const state = this.state;
    const workspace = this.workspace;
    if (state === null || workspace === null) {
      return;
    }
    if (this.busy !== null) {
      this.setNotice('Another Interlock action is still running.');
      return;
    }
    if (state.scan.stale) {
      this.setNotice(state.scan.staleReason ?? 'Refresh the inbox before recovering anything.');
      return;
    }

    let requested: string[] = [];
    let candidates: string[] = [];
    if (scope === 'selected') {
      requested = state.selectedResources();
      candidates = state.recoverableSelected();
    } else if (scope === 'all') {
      requested = state.rows
        .filter((row) => row.flags.changed || row.flags.unprotected || row.status === 'unknown')
        .map((row) => row.resource);
      candidates = state.recoverAllScope().candidates;
    } else {
      const failed = (state.results?.entries ?? [])
        .filter((entry) => entry.outcome === 'failed' || entry.outcome === 'attention')
        .map((entry) => entry.resource);
      requested = failed;
      candidates = failed;
    }
    if (requested.length === 0) {
      this.setNotice('There is nothing to recover in this scope.');
      return;
    }
    if (candidates.length === 0) {
      this.setNotice('No file in this scope is currently eligible for recovery.');
      return;
    }

    this.setBusy('Validating the recovery plans…');
    this.pushProgress('Validating recovery plans', 0, candidates.length);

    let planned: Map<string, PlannedRecovery>;
    let errors: Map<string, string>;
    try {
      const entries = await this.runPlanMany(
        candidates,
        true,
        (done, total) => this.pushProgress('Validating recovery plans', done, total),
        new AbortController().signal,
      );
      planned = new Map<string, PlannedRecovery>();
      errors = new Map<string, string>();
      for (const entry of entries) {
        if (!entry.ok || !entry.summary) {
          errors.set(entry.resource, entry.error?.message ?? 'The engine could not plan this file.');
          continue;
        }
        const doc = await this.deps.storage.load(workspace, entry.resource);
        if (doc === null) {
          errors.set(entry.resource, 'The stored baseline could not be read.');
          continue;
        }
        const plan = planFromEngineResult({
          workspace,
          resource: entry.resource,
          absolutePath: path.join(workspace, ...entry.resource.split('/')),
          evidenceFile: evidencePathFor(this.deps.storage.fileFor(workspace, entry.resource)),
          summary: readPlanSummary(entry.summary),
          baselineSnapshot: doc.snapshot,
          report: entry.summary,
          at: new Date().toISOString(),
        });
        planned.set(entry.resource, plan);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.setBusy(null);
      this.setNotice(`The recovery plans could not be validated: ${message}`);
      this.sync();
      return;
    }

    const scopeCounts =
      scope === 'all'
        ? (() => {
            const info = state.recoverAllScope();
            return {
              changed: info.changed,
              eligible: info.eligible,
              attention: info.attention,
              noBaseline: info.noBaseline,
            };
          })()
        : null;

    const scopeResult = buildReviewScope(
      scope,
      requested,
      new Map(
        [...planned.entries()].map(([resource, plan]) => [
          resource,
          {
            resource,
            operation: plan.operation,
            diffable: plan.diffable,
            previewNote: plan.diffable
              ? null
              : (plan.proposed.limitation ?? 'the exact proposed contents are unavailable'),
            applicable: isApplicable(plan),
            blockedReason:
              `The engine's fresh plan is not applicable for this file ` +
              `(would_succeed=${plan.wouldSucceed}, conflict=${plan.conflict}, drift=${plan.drift}).`,
          },
        ]),
      ),
      errors,
      scopeCounts,
      new Map(
        state.rows
          .filter((row) => requested.includes(row.resource))
          .map((row) => [row.resource, row.reason] as const),
      ),
    );

    this.reviewPlans = planned;
    const review: InboxReview = {
      scope,
      at: new Date().toISOString(),
      requested: requested.length,
      included: scopeResult.included,
      excluded: scopeResult.excluded,
      warnings: scopeResult.warnings,
      notice: null,
      scopeCounts,
    };
    state.beginReview(review);

    // A single file goes straight to the approval gate: the same safe flow
    // (revalidate, approve, identity, write, verify) without an extra review
    // page and a second confirmation dialog. Several files get the review
    // page first, because the exact scope and the exclusions matter there.
    const singleFile = scope === 'selected' && review.included.length === 1 && review.excluded.length === 0;
    if (singleFile) {
      const plan = this.reviewPlans.get(review.included[0].resource);
      if (plan !== undefined) {
        const stale = await this.staleScope([plan]);
        if (stale.length > 0) {
          const updated = applyStaleToReview(review, stale);
          state.updateReview(() => {
            state.review = updated;
          });
          this.setBusy(null);
          this.sync();
          return;
        }
        await this.approveAndApply(review, [plan]);
        return;
      }
    }
    this.setBusy(null);
    this.sync();
  }

  /**
   * Revalidate the reviewed files against the workspace right now: a file
   * that changed since the review is not eligible any more.
   */
  private async staleScope(
    plans: PlannedRecovery[],
  ): Promise<Array<{ resource: string; reason: string }>> {
    const stale: Array<{ resource: string; reason: string }> = [];
    for (const plan of plans) {
      const current = await this.deps.readOptionalFile(plan.absolutePath);
      const staleness = staleAgainstCurrent(plan, current);
      if (staleness.stale) {
        stale.push({ resource: plan.resource, reason: staleness.reason ?? 'the file changed' });
      }
    }
    return stale;
  }

  // ---------------------------------------------------------------- apply

  private async confirmReview(): Promise<void> {
    const state = this.state;
    const review = state?.review ?? null;
    if (state === null || review === null) {
      return;
    }
    if (this.busy !== null) {
      this.setNotice('Another Interlock action is still running.');
      return;
    }
    const plans = review.included
      .map((entry) => this.reviewPlans.get(entry.resource))
      .filter((plan): plan is PlannedRecovery => plan !== undefined);
    if (plans.length === 0) {
      this.setNotice('There is nothing to recover in this scope.');
      return;
    }

    // Revalidate every reviewed file immediately before the approval: a file
    // that changed since the review leaves the scope and needs a new
    // confirmation.
    this.setBusy('Revalidating the reviewed files…');
    const stale = await this.staleScope(plans);
    if (stale.length > 0) {
      const updated = applyStaleToReview(review, stale);
      state.updateReview(() => {
        state.review = updated;
      });
      this.setBusy(null);
      this.sync();
      return;
    }

    await this.approveAndApply(review, plans);
  }

  /**
   * The explicit approval gate. The host shows ONE modal that states the
   * exact scope; the user may attach an optional reference; the real
   * approver identity is resolved through the existing approval policy; only
   * then is the trusted engine asked to write. Cancelling at any step leaves
   * every file untouched.
   */
  private async approveAndApply(review: InboxReview, plans: PlannedRecovery[]): Promise<void> {
    const state = this.state;
    if (state === null) {
      return;
    }
    const approval = await this.deps.confirmRecovery({
      scope: review.scope,
      count: plans.length,
      detail: reviewApprovalDetail(review),
    });
    if (approval === 'cancel') {
      this.setBusy(null);
      this.setNotice('Cancelled at the approval dialog - nothing was changed.');
      this.sync();
      return;
    }

    let reference: string | null = null;
    if (approval === 'apply-with-reference') {
      const typed = await this.deps.askReference();
      if (typed === null) {
        this.setBusy(null);
        this.setNotice('Cancelled at the reference prompt - nothing was changed.');
        this.sync();
        return;
      }
      reference = typed.trim();
    }

    const identity = await this.deps.resolveApproverIdentity();
    if (!identity) {
      this.setBusy(null);
      this.setNotice('No approver identity was provided - nothing was changed.');
      this.sync();
      return;
    }
    const approvedBy = reference ? `${identity} (ref: ${reference})` : identity;

    await this.executePlans(plans, approvedBy, review.scope);
  }

  private async executePlans(
    plans: PlannedRecovery[],
    approvedBy: string,
    scope: 'selected' | 'all' | 'retry',
  ): Promise<void> {
    const state = this.state;
    if (state === null) {
      return;
    }
    const results: InboxRunResults = {
      scope,
      startedAt: new Date().toISOString(),
      finishedAt: null,
      approvedBy,
      entries: [],
      counts: { recovered: 0, skipped: 0, failed: 0, attention: 0, total: 0 },
      running: true,
    };
    state.setResults(results);
    this.setBusy('Applying recovery…');
    this.sync();

    const controller = new AbortController();
    this.abort = controller;
    try {
      for (let index = 0; index < plans.length; index += 1) {
        const plan = plans[index];
        if (controller.signal.aborted) {
          for (const rest of plans.slice(index)) {
            results.entries.push(
              skippedRunEntry(
                rest,
                'Cancelled before this file was attempted - nothing was changed for it.',
              ),
            );
          }
          break;
        }
        // Revalidate immediately before this file is written.
        const current = await this.deps.readOptionalFile(plan.absolutePath);
        const staleness = staleAgainstCurrent(plan, current);
        if (staleness.stale) {
          results.entries.push(
            skippedRunEntry(
              plan,
              `Skipped: ${staleness.reason ?? 'the file changed'} - nothing was written for it.`,
            ),
          );
          this.pushProgress('Applying recovery', index + 1, plans.length);
          continue;
        }
        let outcome: ApplyOutcome;
        try {
          outcome = await this.deps.applyPlanned(plan, approvedBy, { quiet: true });
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          outcome = {
            resource: plan.resource,
            success: false,
            skipped: false,
            verified: false,
            message: `The recovery failed: ${message}`,
            details: message,
          };
        }
        results.entries.push(runEntryFromOutcome(plan, outcome));
        state.updateResults(() => undefined);
        this.pushProgress('Applying recovery', index + 1, plans.length);
      }
    } finally {
      results.running = false;
      results.finishedAt = new Date().toISOString();
      this.abort = null;
      state.updateResults(() => undefined);
      state.applyRunOutcomes(
        results.entries.map((entry) => ({ resource: entry.resource, outcome: entry.outcome })),
      );
      this.setBusy(null);
      this.sync();
    }
  }

  // --------------------------------------------------------------- actions

  private async previewResource(resource: string): Promise<void> {
    const state = this.state;
    const workspace = this.workspace;
    if (state === null || workspace === null) {
      return;
    }
    const row = state.rowFor(resource);
    if (!row || !row.previewable) {
      this.setNotice('This file cannot be previewed: no honest diff exists for it.');
      this.sync();
      return;
    }
    this.setBusy('Preparing the preview…');
    try {
      await this.deps.previewFile(workspace, resource);
    } catch (error) {
      this.deps.log.warn(
        `inbox: preview failed - ${error instanceof Error ? error.message : String(error)}`,
      );
      this.setNotice('The preview could not be opened. See the Interlock output log.');
    } finally {
      this.setBusy(null);
      this.sync();
    }
  }

  private async showDiff(resource: string): Promise<void> {
    const plan = this.reviewPlans.get(resource);
    if (!plan) {
      this.setNotice('No recovery plan is available for this file any more.');
      this.sync();
      return;
    }
    if (!plan.diffable) {
      this.setNotice(
        plan.proposed.limitation ?? 'This file cannot be shown as a text diff.',
      );
      this.sync();
      return;
    }
    await this.deps.openDiff(plan);
  }

  private async openResource(resource: string): Promise<void> {
    const workspace = this.workspace;
    if (workspace === null) {
      return;
    }
    const absolutePath = path.join(workspace, ...resource.split('/'));
    await this.deps.openFile(absolutePath);
  }

  // -------------------------------------------------------------- plumbing

  private ensureWatcher(workspace: string): void {
    if (this.watcher !== null && this.watchedWorkspace === workspace) {
      return;
    }
    this.watcher?.dispose();
    this.watchedWorkspace = workspace;
    this.watcher = this.deps.createWatcher(workspace);
    const onEvent = (): void => {
      const state = this.state;
      if (state === null) {
        return;
      }
      state.noteWorkspaceEvent();
      if (state.scan.stale) {
        this.sync();
      }
    };
    this.watcher.onDidCreate(onEvent);
    this.watcher.onDidChange(onEvent);
    this.watcher.onDidDelete(onEvent);
  }

  private setBusy(busy: string | null): void {
    this.busy = busy;
    this.state?.setBusy(busy);
  }

  private setNotice(notice: string | null): void {
    this.state?.setNotice(notice);
  }

  private view(): InboxViewState | null {
    if (this.state === null) {
      return null;
    }
    return buildViewState(this.state, {
      workspaceName: this.workspace === null ? null : path.basename(this.workspace),
    });
  }

  /**
   * Bring the panel in line with the current state.
   *
   * A new MODE (list / review / results) needs a new document, because the
   * pages differ. Everything else - the scan progress, the counts, the
   * selection, the eligibility verdicts - is pushed INTO the open document.
   * That keeps the focus, the scroll position, the search text and the
   * selection intact, and it means a click is never swallowed by a reload
   * that happens while the user reaches for a control.
   */
  private sync(): void {
    const view = this.view();
    if (view === null || this.panel === null) {
      return;
    }
    if (view.mode !== this.renderedMode) {
      this.renderedMode = view.mode;
      this.panel.show(view);
      return;
    }
    this.panel.update({ type: 'update', view });
  }

  private pushSelection(): void {
    this.sync();
  }

  private pushProgress(_phase: string, _done: number, _total: number): void {
    this.sync();
  }
}

function abortError(): Error {
  const error = new Error('cancelled');
  error.name = 'AbortError';
  return error;
}

function emptyCoverage(): {
  baselinesChecked: number;
  nonBaselineChecked: number;
  skippedDirectories: number;
  skippedDirSample: string[];
  excludedByPolicy: number;
  walkRan: boolean;
  walkFailed: boolean;
  walkTruncated: boolean;
  walkLimit: number;
  failed: number;
  failureNotes: string[];
  partial: boolean;
} {
  return {
    baselinesChecked: 0,
    nonBaselineChecked: 0,
    skippedDirectories: 0,
    skippedDirSample: [],
    excludedByPolicy: 0,
    walkRan: false,
    walkFailed: false,
    walkTruncated: false,
    walkLimit: 0,
    failed: 0,
    failureNotes: [],
    partial: false,
  };
}

