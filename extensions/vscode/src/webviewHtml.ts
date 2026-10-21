/**
 * Pure renderer for the Interlock sidebar webview (recovery dashboard).
 *
 * This module deliberately does NOT import `vscode`, so every layout rule,
 * empty state, escaping decision and message-validation rule can be unit
 * tested directly from mocha.
 *
 * Information architecture (V6 redesign):
 *   1. header           - brand, WORKSPACE PROTECTION subtitle, a live
 *                          protection-status pill, one unobtrusive refresh
 *   2. protection card  - ONE prominent plain-language status
 *   3. primary action   - "Protect My Workspace" (always the one large CTA)
 *   4. prominent duo    - Analyze | Recover side by side (Recover runs the
 *                          real approval-gated recovery flow), approval
 *                          requirement stated directly underneath
 *   5. secondary rows   - Preview Recovery, Verify Recovery
 *   6. advanced         - baselines & capture, exclusions & sensitive files,
 *                          engine diagnostics, settings & troubleshooting
 *                          (all collapsed; urgent errors NEVER live only
 *                          inside them)
 *
 * Safety rules enforced here:
 *  - all model-derived text passes through {@link escapeHtml};
 *  - Content Security Policy allows only a nonce'd <style> and <script>
 *    (no `unsafe-inline`, no `unsafe-eval`, no remote origins, no images);
 *  - the webview may only ask the host to run an explicit allow-list of
 *    command ids (see {@link WEBVIEW_COMMANDS}) - never arbitrary strings;
 *  - the DOM updater in the shipped script only writes textContent, hidden,
 *    disabled, title and data attributes from closed lookup tables (never
 *    HTML built from model data);
 *  - "Protected" is rendered from evidence-derived protection state only -
 *    never from engine availability.
 */

import { SidebarModel } from './sidebar';
import {
  DUO_KEYS,
  DuoKey,
  exclusionSummary,
  PRIMARY_COPY,
  ProtectionState,
  PROTECTION_ICON,
  PROTECTION_TONE,
  protectionOf,
  recoveryRowStates,
  duoStates,
  SENSITIVE_POLICY_NOTE,
} from './protection';
import { ROW_COPY, RowKey, ROW_KEYS } from './protection';

export { PRIMARY_COPY, ROW_COPY, ROW_KEYS, DUO_KEYS, SENSITIVE_POLICY_NOTE };
export type { RowKey, DuoKey };

export interface RenderOptions {
  /**
   * Per-render CSP nonce shared by <style> and <script>. The view loads no
   * images, fonts or local files at all, so no other CSP source is permitted.
   */
  nonce: string;
}

/** Escape text for safe interpolation into HTML text or attribute positions. */
export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// --------------------------------------------------------------------- icons

/**
 * Inline stroke icons (16px grid, `currentColor`). No fonts, no external
 * assets and no image requests: the whole UI stays inside the CSP.
 */
const ICONS: Record<string, string> = {
  shield: 'M12 3 19 5.6v5.7c0 4.3-2.9 7.7-7 9.7-4.1-2-7-5.4-7-9.7V5.6L12 3Z',
  shieldCheck:
    'M12 3 19 5.6v5.7c0 4.3-2.9 7.7-7 9.7-4.1-2-7-5.4-7-9.7V5.6L12 3Z|m9 11.9 2.2 2.2 4-4.4',
  refresh:
    'M19.6 12a7.6 7.6 0 0 1-13 5.3M4.4 12a7.6 7.6 0 0 1 13-5.3|M17.8 3.4v3.6h-3.6|M6.2 20.6V17h3.6',
  search: 'M10.8 17.3a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13Z|m15.6 15.6 4.2 4.2',
  pulse: 'M3 12.2h3.6L8.7 6l3.5 12 2.1-5.8H21',
  save: 'M5 4.8h11.5L19.5 8v11.2H5Z|M8.4 4.8v4.6h6.8V4.8|M8.4 19.6v-5.4h7.2v5.4',
  diff:
    'M4.5 5.5h6v13h-6Z|M13.5 5.5h6v13h-6Z|m7 9.6-1.6 1.6 1.6 1.6|m10 12.8h4',
  shieldAlert:
    'M12 3 19 5.6v5.7c0 4.3-2.9 7.7-7 9.7-4.1-2-7-5.4-7-9.7V5.6L12 3Z|M12 8.4v4|M12 15.4h.01',
  badgeCheck: 'M12 3.2 14.4 5l2.9-.2.8 2.8 2.4 1.8-1.3 2.6 1.3 2.6-2.4 1.8-.8 2.8-2.9-.2L12 20.8 9.6 19l-2.9.2-.8-2.8L3.5 14.6l1.3-2.6-1.3-2.6 2.4-1.8.8-2.8L9.6 5Z|m9.2 12.1 2 2 3.7-4',
  folder: 'M4 6.2h5.4l1.8 2.2H20v9.4H4Z',
  book: 'M4.5 5.4c2.6-.9 5-.9 7.5.4v13c-2.5-1.3-4.9-1.3-7.5-.4Z|m19.5 5.4c-2.6-.9-5-.9-7.5.4v13c2.5-1.3 4.9-1.3 7.5-.4Z',
  warning: 'M12 4.4 21 19.6H3Z|m12 10.2v3.6|M12 16.6h.01',
  info: 'M12 20.8a8.8 8.8 0 1 0 0-17.6 8.8 8.8 0 0 0 0 17.6Z|M12 11.2v5|M12 8h.01',
  clock: 'M12 20.8a8.8 8.8 0 1 0 0-17.6 8.8 8.8 0 0 0 0 17.6Z|M12 7.4V12l3.2 2',
  checkCircle:
    'M12 20.8a8.8 8.8 0 1 0 0-17.6 8.8 8.8 0 0 0 0 17.6Z|m8.5 12.1 2.3 2.3 4.7-5',
  lock: 'M6.4 10.6h11.2v9.2H6.4Z|M8.8 10.6V8.2a3.2 3.2 0 0 1 6.4 0v2.4',
  // rotate-ccw: the recovery action (restore backwards in time)
  rotate: 'M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8|M3 3v5h5',
  dot: 'M12 15.4a3.4 3.4 0 1 0 0-6.8 3.4 3.4 0 0 0 0 6.8Z',
  close: 'M6.4 6.4l11.2 11.2M17.6 6.4 6.4 17.6',
  copy: 'M9 9h8.5v8.5H9Z|M15.5 9V6.5A1.5 1.5 0 0 0 14 5H6.5A1.5 1.5 0 0 0 5 6.5V14a1.5 1.5 0 0 0 1.5 1.5H9',
  // inbox: the Recovery Inbox tray
  inbox: 'M3 13h4.2l1.5 2.6h6.6L16.8 13H21v5.2a1.8 1.8 0 0 1-1.8 1.8H4.8A1.8 1.8 0 0 1 3 18.2Z|M5.6 5h12.8l2.6 8H3Z',
  spark: 'M12 4.4 13.8 10 19.6 12 13.8 14 12 19.6 10.2 14 4.4 12 10.2 10Z',
};

export function icon(name: string, sizeClass = ''): string {
  const body = ICONS[name] ?? ICONS['dot'];
  const paths = body
    .split('|')
    .map((d) => `<path d="${d}"/>`)
    .join('');
  return (
    `<svg class="il-i ${sizeClass}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">` +
    `${paths}</svg>`
  );
}

/**
 * The Interlock shield logo - the exact artwork used by the Activity Bar
 * icon and the packaged extension icon: a shield with two interlocking bars
 * cut out of it (single path, `fill-rule="evenodd"`, so the bars stay
 * transparent). It carries no text, so it still reads at 16px.
 */
export const SHIELD_LOGO_PATH =
  'M12 2.2 20 5.1v6.4c0 4.6-3.2 8.6-8 10.4-4.8-1.8-8-5.8-8-10.4V5.1L12 2.2Z' +
  'M7.4 9.6h9.2v2.8H7.4ZM9.4 14h5.2v2.6H9.4Z';

export function brandShield(sizeClass = ''): string {
  return (
    `<svg class="il-shield ${sizeClass}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">` +
    `<path fill-rule="evenodd" d="${SHIELD_LOGO_PATH}"/></svg>`
  );
}

// -------------------------------------------------------------------- tones

export type Tone = 'ok' | 'bad' | 'warn' | 'idle' | 'accent';

/** Tone keys rendered on the shell; the updater script recomputes them. */
export const TONE_KEYS = [
  'protectionTone',
  'engineTone',
  'platformTone',
  'verifyTone',
  'stripTone',
] as const;
export type ToneKey = (typeof TONE_KEYS)[number];

/**
 * Text bindings the updater script may refresh (kept in sync by tests).
 *
 * The sidebar answers four questions - Am I protected? / What should I do
 * next? / What can I run? / What is going on technically? - and keeps the
 * technical answers inside collapsed "Advanced" sections.
 */
export const BIND_KEYS = [
  'stripText',
  'protectionHeadline',
  'protectionDetail',
  'protectionCounts',
  'protectionBlocker',
  'protectionAuto',
  'protectionRun',
  'workspaceName',
  'primaryDesc',
  'analyzeDesc',
  'recoverDesc',
  'previewDesc',
  'verifyDesc',
  'engineText',
  'engineNote',
  'pythonText',
  'platformText',
  'lastCheck',
  'engineVersion',
  'engineHeadline',
  'autoProtectionText',
  'exclusionsText',
  'verifyText',
  'verifyDetail',
  'gitText',
  'incidentText',
  'warningCount',
] as const;
export type BindKey = (typeof BIND_KEYS)[number];

/**
 * Tooltip bindings: full workspace path, protected-file list, changed-file
 * list. These stay out of the visible layout (narrow sidebar!) and are
 * refreshed through `title` instead of `textContent`.
 */
export const TITLE_BIND_KEYS = [
  'workspaceTitle',
  'baselineTitle',
  'gitTitle',
  'verifyTitle',
] as const;
export type TitleBindKey = (typeof TITLE_BIND_KEYS)[number];

export function engineTone(model: SidebarModel): Tone {
  if (!model.status) {
    return 'idle';
  }
  return model.status.engineAvailable ? 'ok' : 'bad';
}

export function engineLabel(model: SidebarModel): string {
  if (!model.status) {
    return 'Not checked';
  }
  return model.status.engineAvailable ? 'Available' : 'Unavailable';
}

/** Engine platform verdict - an independent claim from "engine starts". */
export function platformTone(label: string | null): Tone {
  if (!label) {
    return 'idle';
  }
  if (label.startsWith('TESTED')) {
    return 'ok';
  }
  if (label.startsWith('UNSUPPORTED')) {
    return 'bad';
  }
  if (label.startsWith('DECLARED')) {
    return 'warn';
  }
  return 'idle';
}

export function verifyTone(model: SidebarModel): Tone {
  if (!model.verification) {
    return 'idle';
  }
  return model.verification.success ? 'ok' : 'bad';
}

export function verifyLabel(model: SidebarModel): string {
  if (!model.verification) {
    return 'Not run';
  }
  return model.verification.success ? 'Passed' : 'Failed';
}

/**
 * Technical-detail explanation for an engine that runs on a platform whose
 * support is not fully validated. Empty when there is nothing to say.
 */
export function engineNote(model: SidebarModel): string {
  const notes: string[] = [];
  // The engine starting is NOT a platform-support claim - keep the distinction.
  const platform = model.status?.platformStatus ?? '';
  if (platform.startsWith('UNSUPPORTED')) {
    notes.push('Platform unsupported: recovery results are not guaranteed here.');
  } else if (platform.startsWith('UNTESTED')) {
    notes.push('Platform untested: recovery results are not guaranteed here.');
  } else if (platform.startsWith('DECLARED')) {
    notes.push('Platform support is community-declared, not officially tested.');
  }
  return notes.join(' ');
}

function tones(model: SidebarModel): Record<ToneKey, Tone> {
  const protection = protectionOf(model);
  return {
    protectionTone: (PROTECTION_TONE[protection.status] ?? 'idle') as Tone,
    engineTone: engineTone(model),
    platformTone: platformTone(model.status?.platformStatus ?? null),
    verifyTone: verifyTone(model),
    stripTone: model.lastError ? 'bad' : 'idle',
  };
}

function bindValues(model: SidebarModel): Record<BindKey, string> {
  const status = model.status;
  const protection = protectionOf(model);
  const workspacePath = model.workspacePath;
  const workspaceName = workspacePath
    ? workspacePath.split(/[\\/]/).filter(Boolean).pop() ?? workspacePath
    : 'No folder open';
  const warningsTotal = model.warnings.length + (model.lastError ? 1 : 0);
  const changedCount = model.gitChangedFiles.length;
  const rows = recoveryRowStates(model);
  const duo = duoStates(model);

  return {
    stripText: model.lastError
      ? model.lastError
      : model.lastAction
        ? `Last action: ${model.lastAction}`
        : '',
    protectionHeadline: protection.headline,
    protectionDetail: protection.detail,
    protectionCounts: protection.countsText,
    protectionBlocker: protection.blocker ?? '',
    protectionAuto: model.autoProtectionEnabled
      ? ''
      : 'Automatic baseline protection is off - evidence is only captured manually.',
    protectionRun: model.autoProtectionNote ?? '',
    workspaceName,
    primaryDesc: model.workspacePath ? PRIMARY_COPY.explain : ROW_COPY._whyFolder,
    analyzeDesc: duo.analyze.description,
    recoverDesc: duo.recover.description,
    previewDesc: rows.preview.description,
    verifyDesc: rows.verify.description,
    engineText: engineLabel(model),
    engineNote: engineNote(model),
    pythonText: status?.pythonVersion ? `Python ${status.pythonVersion}` : 'Python not verified',
    platformText: status?.platformStatus ?? 'Platform not checked',
    lastCheck: status ? new Date(status.at).toLocaleString() : 'never',
    engineVersion: status?.engineVersion ?? 'unknown',
    engineHeadline: status?.headline ?? 'Run Check Installation to probe the engine.',
    autoProtectionText: model.autoProtectionEnabled
      ? 'Automatic protection: on - evidence is captured at safe checkpoints only.'
      : 'Automatic protection: off - capture baselines manually.',
    exclusionsText: exclusionSummary(model.baselineExclusions),
    verifyText: verifyLabel(model),
    verifyDetail: !model.verification
      ? ''
      : [
          model.verification.resource,
          model.verification.reason,
          new Date(model.verification.at).toLocaleString(),
        ]
          .filter(Boolean)
          .join(' · '),
    gitText: model.gitNote
      ? 'No git data'
      : `${changedCount} changed file${changedCount === 1 ? '' : 's'}`,
    incidentText: model.incidentNote,
    warningCount: warningsTotal > 0 ? String(warningsTotal) : '',
  };
}

/** Tooltip values (kept out of the visible layout; see {@link TITLE_BIND_KEYS}). */
function titleValues(model: SidebarModel): Record<TitleBindKey, string> {
  return {
    workspaceTitle: model.workspacePath ?? 'No folder open',
    baselineTitle: model.recentBaselines.length
      ? model.recentBaselines
          .map((b) => `${b.resource} (${b.capturedAt ?? 'unknown time'})`)
          .join('\n')
      : 'No recovery evidence captured yet',
    gitTitle: model.gitNote
      ? model.gitNote
      : model.gitChangedFiles.length
        ? model.gitChangedFiles.slice(0, 40).join('\n') +
          (model.gitChangedFiles.length > 40 ? '\n…' : '') +
          '\n\nGit signal only - not an Interlock incident record.'
        : 'Git signal only - not an Interlock incident record.',
    // The tooltip always carries the full explanation, even when the visible
    // line is the concise version.
    verifyTitle: !model.verification
      ? 'Run Verify Recovery after a recovery to record an independent byte-exact result.'
      : bindValues(model).verifyDetail,
  };
}

// ------------------------------------------------------------------- actions

export interface ActionSpec {
  id: string;
  label: string;
  icon: string;
  tooltip: string;
  /** Recovery execution: never styled like an ordinary action. */
  guarded?: boolean;
}

/**
 * Every action the sidebar can run, in workflow order: the primary button,
 * the two prominent side-by-side actions and the two secondary rows all
 * render straight from these specs (label, icon and tooltip included), so a
 * command's wording exists in exactly one place.
 */
export const ACTIONS: ActionSpec[] = [
  {
    id: 'interlock.protectWorkspace',
    label: 'Protect My Workspace',
    icon: 'shield',
    tooltip:
      'Capture recovery baselines for the eligible files in this workspace (extension-private storage; existing evidence is never overwritten).',
  },
  {
    id: 'interlock.analyzeWorkspace',
    label: 'Analyze',
    icon: 'search',
    tooltip: 'Run the engine confinement probes and scan this workspace (read-only).',
  },
  {
    id: 'interlock.openRecoveryInbox',
    label: 'Recover',
    icon: 'inbox',
    tooltip:
      'Opens the Recovery Inbox in an editor tab: every changed file in this workspace, with ' +
      'its status and eligibility. You pick the files, review the exact scope and approve ' +
      'before anything is written - it is never a one-click restore.',
    guarded: true,
  },
  {
    id: 'interlock.previewRecoveryPlan',
    label: 'Preview Recovery',
    icon: 'diff',
    tooltip:
      'Opens the native side-by-side diff: the current file on the left, the exact proposed recovery on the right. Read-only - nothing is applied.',
  },
  {
    id: 'interlock.verifyRecovery',
    label: 'Verify Recovery',
    icon: 'badgeCheck',
    tooltip: 'Independent byte-exact verification against the captured baseline.',
  },
];

/** Action per recovery-row key (`protect` | `analyze` | ... ). */

/** Links inside the collapsed Advanced sections. */
export const ADVANCED_LINKS: Array<ActionSpec & { section: 'baselines' | 'engine' | 'help' }> = [
  {
    id: 'interlock.checkInstallation',
    label: 'Check installation',
    icon: 'spark',
    tooltip: 'Verify the Python interpreter and import the real engine.',
    section: 'engine',
  },
  {
    id: 'interlock.checkStatus',
    label: 'Check status',
    icon: 'pulse',
    tooltip: 'Engine capabilities, platform verdict, workspace authorization.',
    section: 'engine',
  },
  {
    id: 'interlock.captureBaseline',
    label: 'Capture one file manually',
    icon: 'save',
    tooltip:
      'Deliberately capture (or refresh) the baseline of one file. This is the only way existing evidence is replaced.',
    section: 'baselines',
  },
  {
    id: 'interlock.viewRecoveryPlan',
    label: 'View recovery plan',
    icon: 'book',
    tooltip:
      'Open the Recovery Report: status, summary counts, per-file states, safety checks ' +
      'and technical details for the last preview (read-only - nothing is applied).',
    section: 'baselines',
  },
  {
    id: 'interlock.executeRecovery',
    label: 'Recover one file, step by step',
    icon: 'rotate',
    tooltip:
      'The single-file recovery flow: pick one file, review its diff, approve it, then restore ' +
      'it with byte-exact verification. Use the Inbox for several files at once.',
    section: 'baselines',
  },
  {
    id: 'interlock.openDocumentation',
    label: 'Documentation',
    icon: 'book',
    tooltip: 'Open safety, first-run and limitation documentation.',
    section: 'help',
  },
  {
    id: 'interlock.openOutput',
    label: 'Show output log',
    icon: 'info',
    tooltip: 'Open the structured, secret-redacted output log.',
    section: 'engine',
  },
];

/**
 * Commands the webview is allowed to ask the host to run. Anything else is
 * dropped by {@link isWebviewMessage}.
 */
export const WEBVIEW_COMMANDS: readonly string[] = [
  ...ACTIONS.map((a) => a.id),
  ...ADVANCED_LINKS.map((a) => a.id),
  'interlock.refresh',
];

export interface WebviewMessage {
  type: 'run' | 'ready' | 'openSettings';
  command?: string;
}

/** Validate a message coming back from the webview. Never trusts the shape. */
export function isWebviewMessage(value: unknown): value is WebviewMessage {
  if (value === null || typeof value !== 'object') {
    return false;
  }
  const candidate = value as { type?: unknown; command?: unknown };
  if (typeof candidate.type !== 'string') {
    return false;
  }
  if (candidate.type === 'ready' || candidate.type === 'openSettings') {
    // `openSettings` carries no payload: the host opens the fixed `interlock`
    // settings query, so the webview cannot steer it anywhere else.
    return true;
  }
  if (candidate.type === 'run') {
    return (
      typeof candidate.command === 'string' && WEBVIEW_COMMANDS.includes(candidate.command)
    );
  }
  return false;
}

// -------------------------------------------------------------------- render

function actionRow(action: ActionSpec, rowKey: RowKey, model: SidebarModel): string {
  const rows = recoveryRowStates(model);
  const state = rows[rowKey];
  const guarded = action.guarded === true;
  const cls = guarded ? 'il-rowbtn il-guarded' : 'il-rowbtn';
  // Worded as a requirement, never as a granted approval or a success state.
  const guardNote = guarded
    ? `<span class="il-chip il-chip-guard">${icon('lock', 'il-i-sm')}requires approval</span>`
    : '';
  const disabled = state.disabled ? ' disabled' : '';
  return (
    `<button type="button" class="${cls}" data-action="${escapeHtml(action.id)}" ` +
    `data-row="${rowKey}"${disabled} title="${escapeHtml(action.tooltip)}">` +
    `${icon(action.icon, 'il-btn-ico')}` +
    `<span class="il-rowtext">` +
    `<span class="il-rowlabel">${escapeHtml(action.label)}</span>` +
    `<span class="il-rowdesc" ${bindAttr(
      (`${rowKey}Desc`) as BindKey,
      state.description,
    )}></span>` +
    `</span>${guardNote}</button>`
  );
}

function linkRow(link: ActionSpec): string {
  return (
    `<button type="button" class="il-linkrow" data-action="${escapeHtml(link.id)}" ` +
    `title="${escapeHtml(link.tooltip)}">` +
    `${icon(link.icon, 'il-btn-ico')}<span>${escapeHtml(link.label)}</span></button>`
  );
}

function toneAttr(key: ToneKey, tone: Tone): string {
  return `data-tone="${key}" data-tone-value="${tone}"`;
}

function bindAttr(key: BindKey, value: string): string {
  return `data-bind="${key}" data-bind-value="${escapeHtml(value)}"`;
}

function titleAttr(key: TitleBindKey, value: string): string {
  return `data-title-bind="${key}" data-title-value="${escapeHtml(value)}" title="${escapeHtml(value)}"`;
}

/** Initial warning/error list markup (the updater rebuilds it on each model). */
function warningItemsHtml(model: SidebarModel): string {
  const items: string[] = [];
  if (model.lastError) {
    items.push(`<li class="il-li-error">${escapeHtml(model.lastError)}</li>`);
  }
  for (const warning of model.warnings.slice(0, 8)) {
    items.push(`<li class="il-li-warn">${escapeHtml(warning)}</li>`);
  }
  if (items.length === 0) {
    return '<li class="il-li-muted">No warnings</li>';
  }
  return items.join('');
}

/** The four protection-status icons, toggled by the updater (closed set). */
function protectionIcons(activeStatus: ProtectionState['status']): string {
  const active = PROTECTION_ICON[activeStatus] ?? 'shield';
  const distinct = [...new Set(Object.values(PROTECTION_ICON))];
  return distinct
    .map(
      (name) =>
        `<span class="il-prot-ico" data-prot-icon="${name}"${
          name === active ? '' : ' hidden'
        }>${icon(name)}</span>`,
    )
    .join('');
}

function duoButton(action: ActionSpec, duoKey: DuoKey, model: SidebarModel): string {
  const state = duoStates(model)[duoKey];
  const guarded = action.guarded === true;
  const cls = guarded ? 'il-duobtn il-duobtn-guard' : 'il-duobtn';
  return (
    `<button type="button" class="${cls}" data-action="${escapeHtml(action.id)}" ` +
    `data-duo="${duoKey}"${state.disabled ? ' disabled' : ''} ` +
    `title="${escapeHtml(action.tooltip)}">` +
    `${icon(action.icon, 'il-btn-ico')}` +
    `<span class="il-duotext">` +
    `<span class="il-duolabel">${escapeHtml(action.label)}</span>` +
    `<span class="il-duodesc" ${bindAttr(
      (`${duoKey}Desc`) as BindKey,
      state.description,
    )}></span>` +
    `</span></button>`
  );
}

/** Initial recent-baseline list markup (the updater rebuilds it on each model). */
function baselineItemsHtml(model: SidebarModel): string {
  const items = model.recentBaselines.slice(0, 8);
  if (items.length === 0) {
    return '<li class="il-li-muted">No recovery evidence captured yet</li>';
  }
  return items
    .map((entry) => `<li>${escapeHtml(entry.resource)}</li>`)
    .join('');
}

/**
 * Render the complete sidebar document for the current model.
 *
 * The initial HTML carries every value already escaped; the shipped updater
 * script only refreshes the elements declared with `data-bind` / `data-tone`
 * using textContent and closed lookup tables.
 */
export function renderSidebarHtml(model: SidebarModel, options: RenderOptions): string {
  const t = tones(model);
  const b = bindValues(model);
  const tv = titleValues(model);
  const protection = protectionOf(model);
  const rows = recoveryRowStates(model);
  const nonce = escapeHtml(options.nonce);

  // Empty explanations collapse instead of leaving a blank line behind.
  const hideWhenEmpty = (value: string): string => (value ? '' : ' hidden');
  const findAction = (actionId: string): ActionSpec => {
    const found = ACTIONS.find((a) => a.id === actionId);
    if (!found) {
      throw new Error(`missing action spec for ${actionId}`);
    }
    return found;
  };
  const rowSpec = (key: RowKey): ActionSpec => findAction(rows[key].actionId);
  const duoSpec = (key: DuoKey): ActionSpec => findAction(duoStates(model)[key].actionId);
  const primarySpec = findAction('interlock.protectWorkspace');

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'none'; font-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Interlock</title>
<style nonce="${nonce}">
${STYLESHEET}
</style>
</head>
<body>
<div class="il-root" id="il-root" data-busy="false">

  <header class="il-header">
    <div class="il-idline">
      <span class="il-mark" aria-hidden="true">${brandShield()}</span>
      <span class="il-wordmark">INTERLOCK</span>
      <span class="il-badge" title="Interlock V6 - AI agent recovery">V6</span>
      <span class="il-flex"></span>
      <span class="il-pill" ${toneAttr('protectionTone', t.protectionTone)}
        title="Protection status - the full explanation is in the Protection card below">
        <span class="il-dot" aria-hidden="true"></span>
        <span ${bindAttr('protectionHeadline', b.protectionHeadline)}></span>
      </span>
    </div>
    <div class="il-subline">
      <span class="il-subtitle">WORKSPACE PROTECTION</span>
      <span class="il-flex"></span>
      <button type="button" class="il-iconbtn" data-action="interlock.refresh"
        title="Refresh sidebar" aria-label="Refresh sidebar">${icon('refresh')}</button>
    </div>
  </header>

  <div class="il-strip" id="il-strip" ${stripVisible(b.stripText) ? '' : 'hidden'}
    ${toneAttr('stripTone', t.stripTone)} role="status" aria-live="polite">
    <span class="il-spin" aria-hidden="true"></span>
    <span class="il-strip-text" ${bindAttr('stripText', b.stripText)}></span>
  </div>

  <section class="il-card il-protect" aria-labelledby="il-h-protection">
    <h2 class="il-card-title" id="il-h-protection">
      <span class="il-prot-ico-host" ${toneAttr('protectionTone', t.protectionTone)}
        aria-hidden="true">${protectionIcons(protection.status)}</span>
      Protection
    </h2>
    <div class="il-state" role="status" aria-live="polite" aria-atomic="true">
      <span class="il-state-head" ${toneAttr('protectionTone', t.protectionTone)}
        ${bindAttr('protectionHeadline', b.protectionHeadline)}></span>
    </div>
    <p class="il-state-detail" ${bindAttr('protectionDetail', b.protectionDetail)}></p>
    <p class="il-facts">
      <span class="il-name il-truncate" ${titleAttr('workspaceTitle', tv.workspaceTitle)}>
        <span ${bindAttr('workspaceName', b.workspaceName)}></span>
      </span>
      <span class="il-sep" aria-hidden="true">·</span>
      <span class="il-truncate" ${toneAttr('protectionTone', t.protectionTone)}
        ${titleAttr('baselineTitle', tv.baselineTitle)}>
        <span ${bindAttr('protectionCounts', b.protectionCounts)}></span>
      </span>
    </p>
    <p class="il-hint il-hint-bad" data-hide-empty
      ${bindAttr('protectionBlocker', b.protectionBlocker)}${hideWhenEmpty(b.protectionBlocker)}></p>
    <p class="il-hint" data-hide-empty
      ${bindAttr('protectionAuto', b.protectionAuto)}${hideWhenEmpty(b.protectionAuto)}></p>
    <p class="il-hint" data-hide-empty
      ${bindAttr('protectionRun', b.protectionRun)}${hideWhenEmpty(b.protectionRun)}></p>
  </section>

  <div class="il-group">
    <button type="button" class="il-primary" id="il-primary"
      data-action="${escapeHtml(primarySpec.id)}"${model.workspacePath ? '' : ' disabled'}
      title="${escapeHtml(primarySpec.tooltip)}">
      ${icon(primarySpec.icon, 'il-btn-ico')}
      <span class="il-btn-label">${escapeHtml(PRIMARY_COPY.label)}</span>
    </button>
    <p class="il-explain" ${bindAttr('primaryDesc', b.primaryDesc)}></p>
  </div>

  <div class="il-duo" role="group" aria-label="Analyze and recover">
    ${duoButton(duoSpec('analyze'), 'analyze', model)}
    ${duoButton(duoSpec('recover'), 'recover', model)}
  </div>

  <p class="il-guardnote">
    <span class="il-chip il-chip-guard">${icon('lock', 'il-i-sm')}requires approval</span>
    May modify files. Review the preview and approve before anything changes.
  </p>

  <section class="il-section" aria-label="Review and verify recovery">
    <div class="il-rows">
      ${actionRow(rowSpec('preview'), 'preview', model)}
      ${actionRow(rowSpec('verify'), 'verify', model)}
    </div>
  </section>

  <details class="il-collapsible">
    <summary>Baselines &amp; capture</summary>
    <div class="il-help">
      <ul class="il-list" data-list="baselines">
        ${baselineItemsHtml(model)}
      </ul>
      <p class="il-hint" data-hide-empty
        ${bindAttr('protectionRun', b.protectionRun)}${hideWhenEmpty(b.protectionRun)}></p>
      <p class="il-hint" ${bindAttr('autoProtectionText', b.autoProtectionText)}></p>
      <div class="il-links">
        ${ADVANCED_LINKS.filter((l) => l.section === 'baselines').map(linkRow).join('\n        ')}
      </div>
    </div>
  </details>

  <details class="il-collapsible">
    <summary>Exclusions &amp; sensitive files</summary>
    <div class="il-help">
      <p class="il-note">${escapeHtml(SENSITIVE_POLICY_NOTE)}</p>
      <p class="il-note">User exclusion patterns can only add to this policy - they can never
        remove the built-in secret rules.</p>
      <p class="il-note" ${bindAttr('exclusionsText', b.exclusionsText)}></p>
      <div class="il-links">
        <button type="button" class="il-linkrow" data-action="interlock.settings"
          title="Open Interlock settings (baseline exclusions)">
          ${icon('lock', 'il-btn-ico')}<span>Exclusion settings</span>
        </button>
      </div>
    </div>
  </details>

  <details class="il-collapsible">
    <summary>Diagnostics &amp; engine</summary>
    <div class="il-help">
      <dl class="il-kv">
        <dt>Engine</dt>
        <dd class="il-row">
          <span class="il-dot" ${toneAttr('engineTone', t.engineTone)} aria-hidden="true"></span>
          <span ${bindAttr('engineText', b.engineText)}></span>
        </dd>
        <dt>Interpreter</dt><dd class="il-mono" ${bindAttr('pythonText', b.pythonText)}></dd>
        <dt>Platform</dt>
        <dd>
          <span class="il-chip" ${toneAttr('platformTone', t.platformTone)}
            title="Engine platform verdict - independent from 'the engine starts'.">
            ${icon('shield', 'il-i-sm')}<span ${bindAttr('platformText', b.platformText)}></span>
          </span>
        </dd>
        <dt>Version</dt><dd class="il-mono" ${bindAttr('engineVersion', b.engineVersion)}></dd>
        <dt>Last check</dt><dd class="il-mono" ${bindAttr('lastCheck', b.lastCheck)}></dd>
        <dt>Headline</dt><dd ${bindAttr('engineHeadline', b.engineHeadline)}></dd>
      </dl>
      <p class="il-hint" data-hide-empty ${bindAttr('engineNote', b.engineNote)}
        ${hideWhenEmpty(b.engineNote)}></p>
      <p class="il-note" ${titleAttr('gitTitle', tv.gitTitle)}>
        Git signal: <span ${bindAttr('gitText', b.gitText)}></span>
      </p>
      <p class="il-note">Git changes are informational only - they never mean corruption by themselves.</p>
      <div class="il-links">
        ${ADVANCED_LINKS.filter((l) => l.section === 'engine').map(linkRow).join('\n        ')}
      </div>
    </div>
  </details>

  <details class="il-collapsible">
    <summary>Settings &amp; troubleshooting
      <span class="il-count il-count-warn" data-hide-empty
        ${bindAttr('warningCount', b.warningCount)}${hideWhenEmpty(b.warningCount)}></span>
    </summary>
    <div class="il-help">
      <ul class="il-list" data-list="warnings">
        ${warningItemsHtml(model)}
      </ul>
      <h3 class="il-help-h">Verification</h3>
      <dl class="il-kv">
        <dt>Result</dt>
        <dd class="il-row">
          <span class="il-dot" ${toneAttr('verifyTone', t.verifyTone)} aria-hidden="true"></span>
          <span ${bindAttr('verifyText', b.verifyText)}></span>
        </dd>
      </dl>
      <p class="il-note il-truncate" data-hide-empty ${titleAttr('verifyTitle', tv.verifyTitle)}
        ${bindAttr('verifyDetail', b.verifyDetail)}${hideWhenEmpty(b.verifyDetail)}></p>
      <h3 class="il-help-h">Incidents</h3>
      <p class="il-note" ${bindAttr('incidentText', b.incidentText)}></p>
      <div class="il-links">
        ${ADVANCED_LINKS.filter((l) => l.section === 'help').map(linkRow).join('\n        ')}
        <button type="button" class="il-linkrow" data-action="interlock.settings"
          title="Open Interlock settings">
          ${icon('lock', 'il-btn-ico')}<span>Settings</span>
        </button>
      </div>
    </div>
  </details>

  <footer class="il-footer">
    <span>Interlock V6 · local engine · no telemetry</span>
  </footer>
</div>
<script nonce="${nonce}">
${SCRIPT}
</script>
</body>
</html>`;
}

function stripVisible(text: string): boolean {
  return text.trim().length > 0;
}

// -------------------------------------------------------------------- styles

/** The shared webview design system: tokens, resets, components, tones.
 *  Reused verbatim by every Interlock webview (sidebar + recovery report) so
 *  both surfaces stay visually identical. */
export const STYLESHEET = `
:root {
  /* palette */
  --il-bg: #0A0B0B;
  --il-surface: #111414;
  --il-surface-2: #0F1211;
  --il-hover: #1B1E1D;
  --il-accent: #FFE500;
  --il-accent-hover: #FFF04A;
  --il-text: #F5F5F5;
  --il-text2: #B7BCBC;
  --il-border: #292D2C;
  --il-border-soft: #1D2120;
  --il-ok: #53D769;
  --il-warn: #FFC857;
  --il-error: #FF6464;

  /* one corner-radius scale for the whole dashboard */
  --il-r-xs: 3px;
  --il-r-sm: 4px;
  --il-r-md: 6px;
  --il-r-lg: 8px;
  --il-r-full: 999px;

  /* one spacing scale */
  --il-s1: 3px;
  --il-s2: 5px;
  --il-s3: 8px;
  --il-s4: 11px;

  /* deliberate type system: the editor's mono face is the ONE voice of the
     sidebar - brand, headings, labels and prose all come from it, so the
     panel reads as a single, confident product instead of mixed faces */
  --il-font-display: var(--vscode-editor-font-family, "Cascadia Code", "SFMono-Regular",
    Consolas, "Liberation Mono", monospace);
  --il-font-body: var(--vscode-font-family, -apple-system, BlinkMacSystemFont,
    "Segoe UI", sans-serif);
  /* primary face: the display/mono stack first, the theme face as fallback */
  --il-font: var(--il-font-display), var(--il-font-body);

  /* one size scale - every rule below reads its size from here (floor 12px) */
  --il-fs-brand: 17px;    /* the product title */
  --il-fs-display: 16px;  /* the protection headline */
  --il-fs-h1: 15px;       /* section headings, the primary action label */
  --il-fs-h2: 14px;       /* action card titles, advanced section headings */
  --il-fs-body: 13.5px;   /* descriptions, helper text, list items, values */
  --il-fs-meta: 12.5px;   /* status pills, chips, approval notices */
  --il-fs-sm: 12px;       /* small metadata - the hard floor, never smaller */

  /* one weight scale: 500 ordinary, 600 important, 700/800 emphasis */
  --il-fw-med: 500;
  --il-fw-semi: 600;
  --il-fw-bold: 700;
  --il-fw-black: 800;

  /* one line-height + tracking scale */
  --il-lh-tight: 1.3;   /* headings and button labels */
  --il-lh-snug: 1.4;    /* secondary lines inside a control */
  --il-lh: 1.5;         /* prose */
  --il-ls: .01em;       /* default label tracking */
  --il-ls-wide: .08em;  /* uppercase section headings */
  --il-ls-brand: .14em; /* brand wordmark + subtitle */

  /* the single muted elevation reused by every inset surface */
  --il-inset: var(--il-surface-2);
  color-scheme: dark;
}
* { box-sizing: border-box; }
[hidden] { display: none !important; }
html, body {
  margin: 0; padding: 0;
  background: var(--il-bg);
  color: var(--il-text);
  font-family: var(--il-font);
  font-size: var(--il-fs-body);
  font-weight: var(--il-fw-med);
  line-height: var(--il-lh);
}
body { padding: 0 var(--il-s3) var(--il-s3); }
.il-root { display: flex; flex-direction: column; gap: var(--il-s3); min-width: 0; }
.il-flex { flex: 1 1 auto; min-width: 0; }
.il-mono {
  font-family: var(--il-font-display);
  font-variant-numeric: tabular-nums;
}
.il-i { width: 16px; height: 16px; flex: 0 0 auto; fill: none;
  stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
.il-i-sm { width: 13px; height: 13px; }
/* every icon that labels a control shares one optical column */
.il-btn-ico { width: 15px; height: 15px; }
button { font: inherit; color: inherit; background: none; border: none;
  margin: 0; padding: 0; cursor: pointer; text-align: left; }
button:disabled { cursor: not-allowed; }
:focus-visible { outline: 1px solid var(--vscode-focusBorder, var(--il-accent));
  outline-offset: 1px; border-radius: var(--il-r-sm); }
.il-truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }

/* ---- header: brand, status pill, subtitle - compact but complete ---- */
.il-header {
  position: sticky; top: 0; z-index: 5;
  display: flex; flex-direction: column; gap: var(--il-s1);
  margin: 0 calc(var(--il-s2) * -1);
  padding: var(--il-s2);
  background: var(--il-bg);
  border-bottom: 1px solid var(--il-border-soft);
}
.il-idline {
  display: flex; align-items: center; gap: var(--il-s2);
  min-width: 0; flex-wrap: wrap;
}
.il-subline {
  display: flex; align-items: center; gap: var(--il-s2);
  min-width: 0;
}
.il-subtitle {
  font-family: var(--il-font);
  font-size: var(--il-fs-sm); font-weight: var(--il-fw-bold);
  letter-spacing: var(--il-ls-brand);
  text-transform: uppercase; color: var(--il-text2);
  min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
/* the live protection indicator: one glance, same tone as the card */
.il-pill {
  display: inline-flex; align-items: center; gap: var(--il-s2);
  padding: 2px var(--il-s2); border-radius: var(--il-r-full);
  border: 1px solid var(--il-border); background: var(--il-surface);
  font-size: var(--il-fs-meta); font-weight: var(--il-fw-bold);
  letter-spacing: var(--il-ls);
  min-width: 0; max-width: 100%;
}
.il-pill > span:last-child {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0;
}
/* the brand shield: same artwork as the Activity Bar icon */
.il-mark { display: inline-flex; flex: 0 0 auto; }
.il-mark > svg { width: 20px; height: 20px; display: block; fill: var(--il-accent); }
.il-wordmark {
  font-family: var(--il-font);
  font-weight: var(--il-fw-black); letter-spacing: var(--il-ls-brand);
  font-size: var(--il-fs-brand);
  text-transform: uppercase; color: var(--il-text);
}
.il-badge {
  font-family: var(--il-font);
  font-size: var(--il-fs-sm); font-weight: var(--il-fw-black);
  letter-spacing: var(--il-ls-wide);
  color: #0A0B0B; background: var(--il-accent);
  border-radius: var(--il-r-xs); padding: 0 var(--il-s1); line-height: var(--il-lh-tight);
}
.il-iconbtn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; border-radius: var(--il-r-sm); color: var(--il-text2);
  flex: 0 0 auto;
}
.il-iconbtn:hover { background: var(--hover, var(--il-hover)); color: var(--il-text); }

/* ---- status strip (loading / last action / error) ---- */
.il-strip {
  display: flex; align-items: center; gap: var(--il-s2);
  padding: var(--il-s2) var(--il-s3); border-radius: var(--il-r-md);
  background: var(--il-surface); border: 1px solid var(--il-border-soft);
  color: var(--il-text2); font-size: var(--il-fs-body);
  font-weight: var(--il-fw-med);
}
.il-strip-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.il-spin {
  width: 9px; height: 9px; border-radius: 50%; flex: 0 0 auto;
  border: 1.5px solid currentColor; border-top-color: transparent;
  animation: il-rot .8s linear infinite; display: none;
}
@keyframes il-rot { to { transform: rotate(360deg); } }
.il-root.is-busy .il-spin { display: inline-block; }
.il-root.is-busy [data-action] { opacity: .55; pointer-events: none; }
.il-root.is-busy #il-strip { color: var(--il-accent); border-color: #3a3a1e; }
.il-strip[data-tone-value="bad"] { color: var(--il-error); border-color: #43262a; }
.il-strip[data-tone-value="ok"] { color: var(--il-ok); }

/* ---- the protection card: the one thing a beginner must understand ---- */
.il-card {
  background: var(--il-surface);
  border: 1px solid var(--il-border-soft);
  border-radius: var(--il-r-lg);
  padding: var(--il-s3);
  display: flex; flex-direction: column; gap: var(--il-s2);
  min-width: 0;
}
.il-card-title {
  margin: 0; display: flex; align-items: center; gap: var(--il-s2);
  font-family: var(--il-font);
  font-size: var(--il-fs-h2); font-weight: var(--il-fw-bold);
  letter-spacing: var(--il-ls-wide); line-height: var(--il-lh-tight);
  color: var(--il-text2); text-transform: uppercase;
}
.il-prot-ico-host { display: inline-flex; }
.il-state { display: flex; align-items: baseline; gap: var(--il-s2); min-width: 0; }
.il-state-head {
  font-family: var(--il-font);
  font-size: var(--il-fs-display); font-weight: var(--il-fw-black);
  letter-spacing: var(--il-ls); line-height: var(--il-lh-tight);
  min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.il-state-detail {
  margin: 0; font-size: var(--il-fs-body); line-height: var(--il-lh);
  color: var(--il-text2);
  overflow-wrap: anywhere;
}

/* ---- workspace facts: one calm line ---- */
.il-facts {
  margin: 0; display: flex; align-items: center; gap: var(--il-s2);
  font-size: var(--il-fs-body); color: var(--il-text2); min-width: 0;
}
.il-name { font-size: var(--il-fs-h2); font-weight: var(--il-fw-bold);
  letter-spacing: var(--il-ls); color: var(--il-text);
  min-width: 0; }
.il-sep { color: var(--il-border); }
.il-hint {
  margin: 0; font-size: var(--il-fs-body); line-height: var(--il-lh);
  color: var(--il-text2);
  overflow-wrap: anywhere;
}
.il-hint-bad { color: #FFC9C9; }
.il-note { margin: 0; font-size: var(--il-fs-body); line-height: var(--il-lh);
  color: var(--il-text2);
  overflow-wrap: anywhere; }
.il-chip {
  display: inline-flex; align-items: center; gap: var(--il-s1);
  padding: 1px var(--il-s2); border-radius: var(--il-r-full);
  border: 1px solid var(--il-border-soft);
  background: var(--il-inset); font-size: var(--il-fs-meta);
  font-weight: var(--il-fw-semi);
  letter-spacing: var(--il-ls); color: var(--il-text2);
  max-width: 100%; overflow: hidden;
}
.il-chip span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* the approval requirement is amber (a caution), never green (a success) */
.il-chip-guard { border-color: #4a3b12; color: var(--il-warn); background: #15120A; }
.il-dot {
  width: 8px; height: 8px; border-radius: var(--il-r-full); flex: 0 0 auto;
  background: currentColor;
}
.il-dot[data-tone-value="ok"] { box-shadow: 0 0 0 2px rgba(83, 215, 105, .14); }
.il-row { display: flex; align-items: center; gap: var(--il-s2); min-width: 0; }

/* ---- primary action: the one large CTA, always Protect My Workspace ---- */
.il-group { display: flex; flex-direction: column; gap: var(--il-s2); min-width: 0; }
.il-explain { margin: 0; padding: 0 var(--il-s1); font-size: var(--il-fs-body);
  line-height: var(--il-lh); color: var(--il-text2); }
.il-primary {
  display: flex; align-items: center; justify-content: center; gap: var(--il-s2);
  width: 100%; padding: var(--il-s3) var(--il-s4); border-radius: var(--il-r-md);
  background: var(--il-accent); color: #0A0B0B;
  font-family: var(--il-font);
  font-weight: var(--il-fw-bold); font-size: var(--il-fs-h1);
  letter-spacing: var(--il-ls); line-height: var(--il-lh-tight);
  border: 1px solid var(--il-accent);
  min-height: 34px;
  transition: background .12s ease, transform .05s ease;
}
.il-primary:hover:not(:disabled) { background: var(--il-accent-hover); border-color: var(--il-accent-hover); }
.il-primary:active:not(:disabled) { transform: translateY(1px); }
.il-primary:disabled {
  background: var(--il-surface); color: var(--il-text2); border-color: var(--il-border);
}
.il-primary .il-i { stroke-width: 2; }

/* ---- prominent duo: Analyze | Recover, side by side, stacking when narrow ---- */
.il-duo {
  display: grid; grid-template-columns: 1fr 1fr; gap: var(--il-s2); min-width: 0;
}
.il-duobtn {
  display: flex; flex-direction: column; align-items: flex-start; gap: var(--il-s1);
  min-width: 0; padding: var(--il-s3); border-radius: var(--il-r-md);
  background: var(--il-surface); border: 1px solid var(--il-border-soft);
  color: var(--il-text); min-height: 46px;
  transition: background .12s ease, border-color .12s ease;
}
.il-duobtn:hover:not(:disabled) { background: var(--il-hover); border-color: var(--il-border); }
.il-duobtn:disabled { opacity: .7; }
.il-duobtn > .il-i { color: var(--il-accent); }
.il-duotext { display: flex; flex-direction: column; gap: var(--il-s1); min-width: 0; }
.il-duolabel { font-weight: var(--il-fw-bold); font-size: var(--il-fs-h2);
  letter-spacing: var(--il-ls); line-height: var(--il-lh-tight);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.il-duodesc { font-size: var(--il-fs-body); line-height: var(--il-lh-snug);
  color: var(--il-text2);
  overflow-wrap: anywhere; }
.il-duobtn:disabled .il-duodesc { color: var(--il-warn); }
/* Recover changes files: amber caution palette, never the success colour */
.il-duobtn-guard { background: #15120A; border-color: #4A3B12; }
.il-duobtn-guard:hover:not(:disabled) { background: #1D1809; border-color: #5C4915; }
.il-duobtn-guard:disabled > .il-i { color: var(--il-warn); }

/* ---- secondary rows: preview and verify, visibly quieter ---- */
.il-section { display: flex; flex-direction: column; gap: var(--il-s2); min-width: 0; }
.il-rows { display: flex; flex-direction: column; gap: var(--il-s2); min-width: 0; }
.il-rowbtn {
  display: flex; align-items: center; gap: var(--il-s3); min-width: 0; width: 100%;
  padding: var(--il-s2) var(--il-s3); border-radius: var(--il-r-md);
  background: var(--il-surface); border: 1px solid var(--il-border-soft);
  color: var(--il-text); font-size: var(--il-fs-body);
  font-weight: var(--il-fw-med); line-height: var(--il-lh-tight);
  min-height: 28px;
  transition: background .12s ease, border-color .12s ease;
}
.il-rowbtn:hover:not(:disabled) { background: var(--il-hover); border-color: var(--il-border); }
.il-rowbtn:disabled { opacity: .7; }
.il-rowbtn > .il-i { color: var(--il-text2); }
.il-rowbtn:hover:not(:disabled) > .il-i { color: var(--il-accent); }
.il-rowtext { display: flex; flex-direction: column; gap: var(--il-s1); min-width: 0; flex: 1 1 auto; }
.il-rowlabel { font-weight: var(--il-fw-semi); font-size: var(--il-fs-h2);
  letter-spacing: var(--il-ls); line-height: var(--il-lh-tight);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* the helper line wraps (never shrinks below the 12px floor) */
.il-rowdesc { font-size: var(--il-fs-body); color: var(--il-text2);
  line-height: var(--il-lh-snug); overflow-wrap: anywhere; }
.il-rowbtn:disabled .il-rowdesc { color: var(--il-warn); }
/* guarded recovery: amber caution palette only - never the success colour */
.il-guarded {
  background: #15120A; border-color: #4A3B12; color: #F7E9B0;
}
.il-guarded:hover:not(:disabled) { background: #1D1809; border-color: #5C4915; }
.il-guarded > .il-i { color: var(--il-warn); }
.il-guarded .il-chip { flex: 0 0 auto; }
.il-guardnote {
  margin: 0; padding: 0 var(--il-s1); font-size: var(--il-fs-body);
  line-height: var(--il-lh); font-weight: var(--il-fw-med);
  color: var(--il-warn); overflow-wrap: anywhere;
}
.il-guardnote .il-chip { margin-right: var(--il-s1); }

/* ---- collapsibles: every technical answer lives here, collapsed ---- */
.il-collapsible {
  background: var(--il-surface); border: 1px solid var(--il-border-soft);
  border-radius: var(--il-r-md); padding: var(--il-s2) var(--il-s3);
}
.il-collapsible > summary {
  list-style: none; cursor: pointer; color: var(--il-text2);
  font-size: var(--il-fs-h2); font-weight: var(--il-fw-semi);
  letter-spacing: var(--il-ls); line-height: var(--il-lh-tight);
  display: flex; align-items: center; gap: var(--il-s2);
  border-radius: var(--il-r-sm); padding: 2px 2px;
}
.il-collapsible > summary::-webkit-details-marker { display: none; }
.il-collapsible > summary::before {
  content: ""; width: 0; height: 0; flex: 0 0 auto;
  border-left: 4.5px solid currentColor;
  border-top: 3.5px solid transparent; border-bottom: 3.5px solid transparent;
  transition: transform .12s ease; margin-right: 1px;
}
details[open] > summary::before { transform: rotate(90deg); }
.il-collapsible > summary:hover { color: var(--il-text); }
.il-count {
  margin-left: auto; min-width: 17px; text-align: center;
  border-radius: var(--il-r-full); padding: 0 var(--il-s2);
  font-size: var(--il-fs-sm); font-weight: var(--il-fw-bold);
  background: var(--il-error); color: #0A0B0B;
}
.il-count-warn { background: var(--il-warn); }
.il-help { display: flex; flex-direction: column; gap: var(--il-s2);
  padding-top: var(--il-s2); min-width: 0; }
.il-help-h {
  margin: var(--il-s1) 0 0; font-family: var(--il-font);
  font-size: var(--il-fs-h2); font-weight: var(--il-fw-bold);
  letter-spacing: var(--il-ls-wide); line-height: var(--il-lh-tight);
  text-transform: uppercase; color: var(--il-text2);
}
.il-list { margin: 0; padding: 0 0 0 var(--il-s1); list-style: none;
  display: flex; flex-direction: column; gap: var(--il-s1); }
.il-list li {
  font-size: var(--il-fs-body); line-height: var(--il-lh); color: var(--il-text);
  padding-left: 7px;
  border-left: 2px solid var(--il-border);
  overflow-wrap: anywhere;
}
.il-list li.il-li-error { border-left-color: var(--il-error); color: #FFC9C9; }
.il-list li.il-li-warn { border-left-color: var(--il-warn); }
.il-list li.il-li-muted { border-left-color: transparent; color: var(--il-text2); }
.il-kv { display: grid; grid-template-columns: auto 1fr; gap: var(--il-s1) var(--il-s3); margin: 0; }
.il-kv dt { color: var(--il-text2); font-size: var(--il-fs-sm);
  font-weight: var(--il-fw-semi); letter-spacing: var(--il-ls); }
.il-kv dd { margin: 0; font-size: var(--il-fs-body); color: var(--il-text);
  overflow-wrap: anywhere; min-width: 0; }
.il-links { display: flex; flex-direction: column; gap: var(--il-s1); }
.il-linkrow {
  display: flex; align-items: center; gap: var(--il-s2);
  padding: var(--il-s2); border-radius: var(--il-r-sm);
  color: var(--il-text); font-size: var(--il-fs-body);
  font-weight: var(--il-fw-med); line-height: var(--il-lh-tight);
  min-height: 26px;
  transition: background .12s ease;
}
.il-linkrow:hover { background: var(--il-hover); }
.il-linkrow > .il-i { color: var(--il-text2); }
.il-linkrow:hover > .il-i { color: var(--il-accent); }

.il-footer {
  text-align: center; font-size: var(--il-fs-sm);
  font-weight: var(--il-fw-med); color: var(--il-text2);
  padding-top: var(--il-s1);
}

/* ---- tones: applied last so they win over the base text colour ---- */
[data-tone-value="ok"] { color: var(--il-ok); }
[data-tone-value="warn"] { color: var(--il-warn); }
[data-tone-value="bad"] { color: var(--il-error); }
[data-tone-value="idle"] { color: var(--il-text2); }
[data-tone-value="accent"] { color: var(--il-accent); }

@media (max-width: 270px) {
  /* status rows stack label over value instead of squeezing side by side */
  .il-kv { grid-template-columns: 1fr; gap: var(--il-s1); }
  .il-wordmark { letter-spacing: .1em; }
  /* the two prominent actions stack instead of squeezing */
  .il-duo { grid-template-columns: 1fr; }
  /* the guarded action keeps its full label, letting the approval chip wrap */
  .il-rowbtn { padding: var(--il-s2) var(--il-s2); gap: var(--il-s2); }
  .il-guarded { flex-wrap: wrap; }
  .il-state-head { font-size: var(--il-fs-h1); }
}
@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
  .il-root.is-busy .il-spin { display: none; }
  .il-root.is-busy #il-strip::after { content: " · working"; }
}
`;

// -------------------------------------------------------------------- script

/**
 * Shipped updater. Rules:
 *  - only writes `textContent`, `hidden`, `disabled`, `title`, `dataset`
 *    values and `className` from closed tables - never `innerHTML` with
 *    model data;
 *  - every outbound message is `{type:'run', command}` with an id the host
 *    re-validates against its own allow-list.
 */
const SCRIPT = `
(function () {
  var vscode = acquireVsCodeApi();
  var root = document.getElementById('il-root');
  var strip = document.getElementById('il-strip');

  var BINDS = ${JSON.stringify(BIND_KEYS)};
  var TITLE_BINDS = ${JSON.stringify(TITLE_BIND_KEYS)};
  var TONES = ${JSON.stringify(TONE_KEYS)};
  var PROT_TONE = ${JSON.stringify(PROTECTION_TONE)};
  var PROT_ICON = ${JSON.stringify(PROTECTION_ICON)};
  var ROW_ORDER = ${JSON.stringify(ROW_KEYS)};
  var DUO_ORDER = ${JSON.stringify(DUO_KEYS)};
  var COPY = ${JSON.stringify(ROW_COPY)};
  var PRIMARY_COPY = ${JSON.stringify(PRIMARY_COPY)};

  function setBusy(busy) {
    root.classList.toggle('is-busy', !!busy);
    root.setAttribute('aria-busy', busy ? 'true' : 'false');
    if (busy) {
      var el = document.querySelector('[data-bind="stripText"]');
      if (el) { el.textContent = 'Working\\u2026'; }
      strip.hidden = false;
      strip.setAttribute('data-tone-value', 'idle');
    } else {
      renderStrip();
    }
  }

  function renderStrip() {
    var el = document.querySelector('[data-bind="stripText"]');
    if (!el) { return; }
    var text = el.textContent || '';
    strip.hidden = text.trim().length === 0;
  }

  // Honest fallback mirroring src/protection.ts evaluateProtection(), used
  // only before the host has pushed a computed protection state.
  function fallbackProtection(model) {
    if (!model.workspacePath) {
      return { status: 'unknown', headline: 'No folder open',
        detail: 'Open a project folder to see and manage its recovery protection.',
        countsText: '', blocker: null };
    }
    var count = Number(model.baselineCount || 0);
    if (model.workspaceAuthorized === false) {
      return { status: 'action-required', headline: 'Protection unavailable',
        detail: 'This folder is not authorized for recovery.',
        countsText: count ? count + ' file' + (count === 1 ? '' : 's') + ' protected' : 'no recovery evidence yet',
        blocker: 'The engine refused this workspace (confinement check failed). Interlock cannot protect or recover files here. Run Analyze Workspace for details.' };
    }
    if (count === 0) {
      return { status: 'needs-protection', headline: 'Needs protection',
        detail: "This workspace isn't protected yet. Capture a baseline of the current files so Interlock can restore them after an agent change.",
        countsText: 'no recovery evidence yet', blocker: null };
    }
    if (model.workspaceAuthorized === true) {
      return { status: 'protected', headline: 'Protected',
        detail: 'Valid recovery evidence is available for the files in this workspace.',
        countsText: count + ' file' + (count === 1 ? '' : 's') + ' protected', blocker: null };
    }
    return { status: 'unknown', headline: 'Not verified yet',
      detail: 'Recovery evidence exists for ' + count + ' file' + (count === 1 ? '' : 's') + ', but this workspace has not been authorized by the engine yet. Run Analyze Workspace.',
      countsText: count + ' file' + (count === 1 ? '' : 's') + ' protected', blocker: null };
  }

  function previewPending(model, now) {
    var pv = model.pendingPreview;
    if (!pv || !model.workspacePath) { return null; }
    if (pv.workspace !== model.workspacePath || !pv.wouldSucceed) { return null; }
    var at = Date.parse(pv.at);
    if (!isFinite(at) || now - at >= 1800000) { return null; }
    return pv;
  }

  // Mirrors src/protection.ts protectionOf(): the host's evidence state,
  // upgraded to the time-bounded "Recovery ready" while a preview is fresh.
  // Never fabricated: only protected/partial states can be upgraded, and an
  // expired preview falls straight back to the honest evidence state.
  function protectionOf(model, now) {
    var base = (model.protection && typeof model.protection === 'object')
      ? model.protection : fallbackProtection(model);
    if (base.status !== 'protected' && base.status !== 'partial') { return base; }
    var pv = previewPending(model, now);
    if (!pv) { return base; }
    var resources = (pv.resources && pv.resources.length) ? pv.resources : [pv.resource];
    return { status: 'recovery-ready', headline: 'Recovery ready',
      detail: resources.length > 1
        ? COPY.readyMany.replace('{count}', String(resources.length))
        : COPY.readySingle.replace('{resource}', pv.resource),
      countsText: base.countsText, blocker: null,
      coveredFiles: base.coveredFiles, eligibleFiles: base.eligibleFiles,
      skippedFiles: base.skippedFiles, checkedAt: base.checkedAt };
  }

  // Mirrors src/protection.ts recoveryRowStates() + duoStates(): recovery
  // operations need an open folder AND stored evidence; Analyze only needs
  // the folder. The gate replaces the description while it applies.
  function rowTable(model) {
    var noFolder = !model.workspacePath;
    var noEvidence = !Number(model.baselineCount || 0);
    var folderWhy = COPY._whyFolder;
    var evidenceWhy = COPY._whyEvidence;
    var gate = noFolder ? folderWhy : (noEvidence ? evidenceWhy : '');
    return {
      analyze: { disabled: noFolder, desc: noFolder ? folderWhy : COPY.analyze.enabled },
      recover: { disabled: noFolder, desc: noFolder ? folderWhy : COPY.recover.enabled },
      preview: { disabled: !!gate, desc: gate || COPY.preview.enabled },
      verify:  { disabled: !!gate, desc: gate || COPY.verify.enabled }
    };
  }

  // Mirrors src/protection.ts exclusionSummary().
  function exclusionSummary(patterns) {
    if (!patterns || !patterns.length) {
      return 'No user exclusion patterns configured.';
    }
    var shown = patterns.slice(0, 5);
    var extra = patterns.length - shown.length;
    return patterns.length + ' user exclusion pattern' +
      (patterns.length === 1 ? '' : 's') + ': ' + shown.join(', ') +
      (extra > 0 ? ' +' + extra + ' more' : '') + '.';
  }

  function toneTable(model, now) {
    var prot = protectionOf(model, now);
    var status = model.status || null;
    return {
      protectionTone: PROT_TONE[prot.status] || 'idle',
      engineTone: !status ? 'idle' : (status.engineAvailable ? 'ok' : 'bad'),
      platformTone: !status || !status.platformStatus ? 'idle'
        : (String(status.platformStatus).indexOf('TESTED') === 0 ? 'ok'
          : String(status.platformStatus).indexOf('UNSUPPORTED') === 0 ? 'bad'
          : String(status.platformStatus).indexOf('DECLARED') === 0 ? 'warn' : 'idle'),
      verifyTone: !model.verification ? 'idle' : (model.verification.success ? 'ok' : 'bad'),
      stripTone: model.lastError ? 'bad' : 'idle'
    };
  }

  function bindTable(model, now) {
    var status = model.status || null;
    var prot = protectionOf(model, now);
    var path = model.workspacePath;
    var name = 'No folder open';
    if (path) {
      var parts = String(path).split(/[\\\\/]/).filter(Boolean);
      name = parts.length ? parts[parts.length - 1] : String(path);
    }
    var changed = (model.gitChangedFiles || []).length;
    var total = (model.warnings || []).length + (model.lastError ? 1 : 0);
    var verify = model.verification;
    var rows = rowTable(model);
    var platform = (status && status.platformStatus) ? String(status.platformStatus) : '';
    var engineNotes = [];
    if (platform.indexOf('UNSUPPORTED') === 0) {
      engineNotes.push('Platform unsupported: recovery results are not guaranteed here.');
    } else if (platform.indexOf('UNTESTED') === 0) {
      engineNotes.push('Platform untested: recovery results are not guaranteed here.');
    } else if (platform.indexOf('DECLARED') === 0) {
      engineNotes.push('Platform support is community-declared, not officially tested.');
    }
    return {
      stripText: model.lastError ? String(model.lastError)
        : (model.lastAction ? 'Last action: ' + String(model.lastAction) : ''),
      protectionHeadline: String(prot.headline || ''),
      protectionDetail: String(prot.detail || ''),
      protectionCounts: String(prot.countsText || ''),
      protectionBlocker: prot.blocker ? String(prot.blocker) : '',
      protectionAuto: model.autoProtectionEnabled ? ''
        : 'Automatic baseline protection is off - evidence is only captured manually.',
      protectionRun: model.autoProtectionNote ? String(model.autoProtectionNote) : '',
      workspaceName: name,
      primaryDesc: model.workspacePath ? PRIMARY_COPY.explain : COPY._whyFolder,
      analyzeDesc: rows.analyze.desc,
      recoverDesc: rows.recover.desc,
      previewDesc: rows.preview.desc,
      verifyDesc: rows.verify.desc,
      engineText: !status ? 'Not checked'
        : (status.engineAvailable ? 'Available' : 'Unavailable'),
      engineNote: engineNotes.join(' '),
      pythonText: status && status.pythonVersion ? 'Python ' + status.pythonVersion
        : 'Python not verified',
      platformText: status && status.platformStatus ? String(status.platformStatus)
        : 'Platform not checked',
      lastCheck: status && status.at ? new Date(status.at).toLocaleString() : 'never',
      engineVersion: status && status.engineVersion ? String(status.engineVersion) : 'unknown',
      engineHeadline: status && status.headline ? String(status.headline)
        : 'Run Check Installation to probe the engine.',
      autoProtectionText: model.autoProtectionEnabled
        ? 'Automatic protection: on - evidence is captured at safe checkpoints only.'
        : 'Automatic protection: off - capture baselines manually.',
      exclusionsText: exclusionSummary(model.baselineExclusions || []),
      verifyText: !verify ? 'Not run' : (verify.success ? 'Passed' : 'Failed'),
      verifyDetail: !verify ? ''
        : [verify.resource, verify.reason,
           verify.at ? new Date(verify.at).toLocaleString() : '']
          .filter(Boolean).join(' \\u00b7 '),
      gitText: model.gitNote ? 'No git data'
        : changed + ' changed file' + (changed === 1 ? '' : 's'),
      incidentText: String(model.incidentNote || ''),
      warningCount: total > 0 ? String(total) : ''
    };
  }

  function titleTable(model) {
    var baselines = (model.recentBaselines || []);
    var changed = (model.gitChangedFiles || []);
    var verify = model.verification;
    return {
      workspaceTitle: model.workspacePath || 'No folder open',
      baselineTitle: baselines.length
        ? baselines.map(function (b) {
            return b.resource + (b.capturedAt ? ' (' + b.capturedAt + ')' : ' (unknown time)');
          }).join('\\n')
        : 'No recovery evidence captured yet',
      gitTitle: model.gitNote
        ? String(model.gitNote)
        : (changed.length
            ? changed.slice(0, 40).join('\\n') + (changed.length > 40 ? '\\n\\u2026' : '') +
              '\\n\\nGit signal only - not an Interlock incident record.'
            : 'Git signal only - not an Interlock incident record.'),
      verifyTitle: !verify
        ? 'Run Verify Recovery after a recovery to record an independent byte-exact result.'
        : [verify.resource, verify.reason,
           verify.at ? new Date(verify.at).toLocaleString() : '']
          .filter(Boolean).join(' \\u00b7 ')
    };
  }

  function updateWarnings(model) {
    var ul = document.querySelector('[data-list="warnings"]');
    if (!ul) { return; }
    ul.textContent = '';
    var items = [];
    if (model.lastError) { items.push({ text: String(model.lastError), cls: 'il-li-error' }); }
    (model.warnings || []).slice(0, 8).forEach(function (w) {
      items.push({ text: String(w), cls: 'il-li-warn' });
    });
    if (!items.length) {
      var li = document.createElement('li');
      li.className = 'il-li-muted';
      li.textContent = 'No warnings';
      ul.appendChild(li);
      return;
    }
    items.forEach(function (item) {
      var li = document.createElement('li');
      li.className = item.cls;
      li.textContent = item.text;
      ul.appendChild(li);
    });
  }

  function updateProtectionIcons(status) {
    var name = PROT_ICON[status] || 'shield';
    document.querySelectorAll('[data-prot-icon]').forEach(function (el) {
      el.hidden = el.getAttribute('data-prot-icon') !== name;
    });
  }

  // The primary button is always "Protect My Workspace"; only its availability
  // changes (nothing to protect without a folder).
  function updatePrimary(model) {
    var btn = document.getElementById('il-primary');
    if (!btn) { return; }
    btn.disabled = !model.workspacePath;
  }

  // Availability for the secondary rows AND the prominent duo (Analyze/Recover).
  function updateAvailability(model) {
    var rows = rowTable(model);
    ROW_ORDER.forEach(function (key) {
      var btn = document.querySelector('[data-row="' + key + '"]');
      if (!btn) { return; }
      btn.disabled = !!rows[key].disabled;
    });
    DUO_ORDER.forEach(function (key) {
      var btn = document.querySelector('[data-duo="' + key + '"]');
      if (!btn) { return; }
      btn.disabled = !!rows[key].disabled;
    });
  }

  // The recent-evidence list in "Baselines & capture" (closed data only:
  // resource paths, written as textContent - never markup).
  function updateBaselines(model) {
    var ul = document.querySelector('[data-list="baselines"]');
    if (!ul) { return; }
    ul.textContent = '';
    var items = (model.recentBaselines || []).slice(0, 8);
    if (!items.length) {
      var empty = document.createElement('li');
      empty.className = 'il-li-muted';
      empty.textContent = 'No recovery evidence captured yet';
      ul.appendChild(empty);
      return;
    }
    items.forEach(function (baseline) {
      var li = document.createElement('li');
      li.textContent = String(baseline.resource);
      ul.appendChild(li);
    });
  }

  function updateModel(model) {
    if (!model || typeof model !== 'object') { return; }
    var now = Date.now();
    var binds = bindTable(model, now);
    BINDS.forEach(function (key) {
      document.querySelectorAll('[data-bind="' + key + '"]').forEach(function (el) {
        var text = binds[key] === undefined ? '' : binds[key];
        el.textContent = text;
        // Optional hints disappear when empty instead of leaving blank space.
        if (el.hasAttribute('data-hide-empty')) { el.hidden = !text; }
      });
    });
    var titles = titleTable(model);
    TITLE_BINDS.forEach(function (key) {
      document.querySelectorAll('[data-title-bind="' + key + '"]').forEach(function (el) {
        el.title = titles[key] === undefined ? '' : titles[key];
      });
    });
    var tones = toneTable(model, now);
    document.querySelectorAll('[data-tone]').forEach(function (el) {
      var key = el.getAttribute('data-tone');
      el.setAttribute('data-tone-value', tones[key] || 'idle');
    });
    updateProtectionIcons(protectionOf(model, now).status);
    updatePrimary(model);
    updateAvailability(model);
    updateBaselines(model);
    updateWarnings(model);
    renderStrip();
  }

  window.addEventListener('message', function (event) {
    var msg = event.data;
    if (!msg || typeof msg !== 'object') { return; }
    if (msg.type === 'model' && msg.model) { updateModel(msg.model); }
    else if (msg.type === 'busy') { setBusy(!!msg.busy); }
  });

  document.addEventListener('click', function (event) {
    // Duplicate-click prevention: while the host is running a command, the
    // webview accepts no further actions (the host gates runs as well).
    if (root.classList.contains('is-busy')) { return; }
    var target = event.target instanceof Element
      ? event.target.closest('[data-action]') : null;
    if (!target) { return; }
    if (target.disabled) { return; }
    var action = target.getAttribute('data-action');
    if (!action) { return; }
    if (action === 'interlock.settings') {
      vscode.postMessage({ type: 'openSettings' });
      return;
    }
    vscode.postMessage({ type: 'run', command: action });
  });

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Enter' && event.key !== ' ') { return; }
    var summary = event.target instanceof Element ? event.target.closest('summary') : null;
    if (summary && summary.parentElement && summary.parentElement.tagName === 'DETAILS') {
      event.preventDefault();
      summary.parentElement.open = !summary.parentElement.open;
    }
  });

  vscode.postMessage({ type: 'ready' });
})();
`;

