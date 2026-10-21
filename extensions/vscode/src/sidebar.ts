/**
 * Interlock sidebar state.
 *
 * This is the single source of truth the sidebar view renders: a read-only
 * projection of state produced by real engine calls (never fabricated -
 * unknown/failed states are rendered as exactly that).
 *
 * The module is deliberately free of any `vscode` import so the renderer and
 * the model can be unit-tested headlessly. The class is still structurally
 * compatible with `vscode.Disposable`, and `onDidChange` mirrors
 * `vscode.Event<T>` (`(listener) => { dispose(): void }`).
 */

import type { ProtectionState } from './protection';
import type { BaselineSummary, StoredStatus, StoredVerification } from './state';

/** A recovery preview the sidebar can offer to review (freshness-bounded). */
export interface PendingPreview {
  workspace: string;
  /** Primary (first) file of the preview - what the card names. */
  resource: string;
  /**
   * Every file this preview covers, in review order. Present when a preview
   * spans more than one file so the sidebar can say how many diffs to review.
   */
  resources?: string[];
  at: string;
  wouldSucceed: boolean;
}

export interface SidebarModel {
  status: StoredStatus | null;
  workspacePath: string | null;
  workspaceAuthorized: boolean | null;
  workspaceSupportStatus: string | null;
  baselineCount: number;
  recentBaselines: BaselineSummary[];
  gitChangedFiles: string[];
  gitNote: string | null;
  incidentNote: string;
  verification: StoredVerification | null;
  warnings: string[];
  lastError: string | null;
  lastAction: string | null;
  /** Derived protection status (never fabricated; null until first computed). */
  protection: ProtectionState | null;
  /** Fresh recovery preview for the current workspace, when one exists. */
  pendingPreview: PendingPreview | null;
  /** Mirrors `interlock.automaticBaselineProtection` for the UI. */
  autoProtectionEnabled: boolean;
  /** Last automatic-protection run summary line (plain language). */
  autoProtectionNote: string | null;
  /** Mirrors `interlock.baselineExclusions` so the sidebar can disclose it. */
  baselineExclusions: string[];
}

export function emptyModel(): SidebarModel {
  return {
    status: null,
    workspacePath: null,
    workspaceAuthorized: null,
    workspaceSupportStatus: null,
    baselineCount: 0,
    recentBaselines: [],
    gitChangedFiles: [],
    gitNote: null,
    incidentNote:
      'No incident history: the filesystem recovery adapter does not record incident history (empty incident_id) and no queryable store exists in the supported beta scope.',
    verification: null,
    warnings: [],
    lastError: null,
    lastAction: null,
    protection: null,
    pendingPreview: null,
    autoProtectionEnabled: true,
    autoProtectionNote: null,
    baselineExclusions: [],
  };
}

export interface ChangeSubscription {
  dispose(): void;
}

/** Minimal synchronous listener registry (same shape as `vscode.Event<T>`). */
type Listener<T> = (value: T) => void;

/** Holds the sidebar model and notifies listeners on every change. */
export class SidebarState {
  private model: SidebarModel = emptyModel();
  private readonly listeners: Array<Listener<SidebarModel>> = [];

  /** Fires with the complete model whenever any part of it changes. */
  onDidChange(listener: Listener<SidebarModel>): ChangeSubscription {
    this.listeners.push(listener);
    return {
      dispose: () => {
        const index = this.listeners.indexOf(listener);
        if (index >= 0) {
          this.listeners.splice(index, 1);
        }
      },
    };
  }

  setModel(model: SidebarModel): void {
    this.model = model;
    this.emit();
  }

  patchModel(patch: Partial<SidebarModel>): void {
    this.model = { ...this.model, ...patch };
    this.emit();
  }

  getModel(): SidebarModel {
    return this.model;
  }

  /** Re-emit the current model (drives `Interlock: Refresh Sidebar`). */
  refresh(): void {
    this.emit();
  }

  private emit(): void {
    for (const listener of [...this.listeners]) {
      listener(this.model);
    }
  }

  dispose(): void {
    this.listeners.length = 0;
  }
}
