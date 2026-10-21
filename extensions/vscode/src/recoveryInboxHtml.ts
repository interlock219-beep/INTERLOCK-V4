/**
 * Recovery Inbox renderer (pure).
 *
 * Renders an {@link InboxViewState} into the panel's HTML using the shared
 * design system (`STYLESHEET` from `webviewHtml.ts`). The main list is
 * rendered client-side from an embedded JSON payload so that search, filter,
 * sort, folder grouping and pagination stay responsive at thousands of rows
 * without re-rendering the document (and without losing the search focus).
 *
 * Security model (mirrors the sidebar and the Recovery Report):
 *   * One per-render CSP nonce covers <style> and <script>; no images, fonts,
 *     remote scripts or remote styles are permitted at all.
 *   * Every dynamic value passes through {@link escapeHtml}; the JSON payload
 *     is escaped for `</script` and only ever read with textContent-safe DOM
 *     building (createElement + textContent - never innerHTML, never eval).
 *   * The script only posts typed messages back to the extension. Selection
 *     intents carry resource names only; the host re-validates everything
 *     against its own authoritative model before acting.
 *   * Hashes, engine verdicts and read errors appear only inside collapsed
 *     per-row "Details" disclosures - never in the main view.
 */

import { RenderOptions, STYLESHEET, brandShield, escapeHtml, icon } from './webviewHtml';
import { isSafeResource } from './recoveryReportHtml';
import { INBOX_FILTERS, InboxViewState } from './recoveryInbox';

// ---------------------------------------------------------------- messages

const MESSAGE_TYPES = [
  'ready',
  'refresh',
  'cancelScan',
  'close',
  'preview',
  'select',
  'clearSelection',
  'recoverSelected',
  'recoverAll',
  'reviewPage',
  'viewDiff',
  'back',
  'confirm',
  'retry',
  'openFile',
  'verifyRecovery',
] as const;

/** Typed messages the inbox script may send to the extension. */
export interface InboxMessage {
  type: (typeof MESSAGE_TYPES)[number];
  /** Only for `preview` / `viewDiff` / `openFile`: a workspace-relative resource. */
  resource?: string;
  /** Only for `select`: resources to add/remove (bounded, host re-validates). */
  add?: string[];
  remove?: string[];
  /** Only for `reviewPage`: 1-based page number. */
  page?: number;
}

function isBoundedStringList(value: unknown, max: number): value is string[] {
  return (
    Array.isArray(value) &&
    value.length <= max &&
    value.every((item) => typeof item === 'string' && item.length > 0 && item.length <= 1024)
  );
}

/** Validate a message received from the webview (shape only - the panel
 *  additionally checks resources against its own allow-list). */
export function isInboxMessage(value: unknown): value is InboxMessage {
  if (value === null || typeof value !== 'object') {
    return false;
  }
  const record = value as Record<string, unknown>;
  const type = record['type'];
  if (typeof type !== 'string' || !MESSAGE_TYPES.includes(type as (typeof MESSAGE_TYPES)[number])) {
    return false;
  }
  const resource = record['resource'];
  if (resource !== undefined && typeof resource !== 'string') {
    return false;
  }
  if (type === 'preview' || type === 'viewDiff' || type === 'openFile') {
    if (typeof resource !== 'string') {
      return false;
    }
  }
  if (type === 'select') {
    const add = record['add'];
    const remove = record['remove'];
    if (add !== undefined && !isBoundedStringList(add, 5000)) {
      return false;
    }
    if (remove !== undefined && !isBoundedStringList(remove, 5000)) {
      return false;
    }
    if (add === undefined && remove === undefined) {
      return false;
    }
  }
  if (type === 'reviewPage') {
    const page = record['page'];
    if (typeof page !== 'number' || !Number.isInteger(page) || page < 1) {
      return false;
    }
  }
  return true;
}

/** Workspace-relative path sanity check (delegated to the report guard). */
export function isInboxSafeResource(value: string): boolean {
  return isSafeResource(value);
}

// ------------------------------------------------------- host -> webview push

/** Lightweight live update pushed to the open panel (no full re-render). */
export interface InboxUpdate {
  type: 'update';
  /**
   * The complete inbox state. The client applies it in place, so the document
   * is never replaced while the inbox is open (no lost focus, no lost click,
   * no lost scroll position).
   */
  view: InboxViewState;
}

// ------------------------------------------------------------------ helpers

function formatStamp(iso: string | null): string | null {
  if (iso === null) {
    return null;
  }
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) {
    return null;
  }
  const date = new Date(ms);
  const pad = (n: number): string => String(n).padStart(2, '0');
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

const UNKNOWN_TITLE =
  'This value could not be derived from the validated evidence, so it is reported as Unknown.';

/** The seven summary counts, each with a live hook the client can update. */
const COUNT_KEYS = [
  ['examined', 'Files examined'],
  ['changed', 'Changed vs baseline'],
  ['verifiedEvidence', 'Verified evidence'],
  ['recoverableModified', 'Recoverable modified'],
  ['recoverableDeleted', 'Recoverable deleted'],
  ['attention', 'Need attention'],
  ['noBaseline', 'Without usable baseline'],
] as const;

/**
 * One summary card. The live element IS the styled element, so the client can
 * replace the number (or "Unknown") without losing the card's typography.
 */
function countCell(
  key: string,
  label: string,
  count: number | null,
  warnWhenPositive: boolean,
): string {
  const tone = warnWhenPositive && count !== null && count > 0 ? ' data-tone-value="warn"' : '';
  if (count === null) {
    return (
      `<div class="il-ib-stat"><span class="il-ib-stat-l">${escapeHtml(label)}</span>` +
      `<span class="il-ib-unknown" data-live="count-${key}" title="${UNKNOWN_TITLE}">Unknown</span></div>`
    );
  }
  return (
    `<div class="il-ib-stat"><span class="il-ib-stat-l">${escapeHtml(label)}</span>` +
    `<span class="il-ib-stat-v" data-live="count-${key}"${tone}>` +
    `${count.toLocaleString('en-US')}</span></div>`
  );
}

function notice(text: string | null, className: string, liveKey: string): string {
  const hidden = text === null || text === '' ? ' hidden' : '';
  const body = text === null || text === '' ? '' : escapeHtml(text);
  return `<p class="${className}" role="status" data-live="${liveKey}"${hidden}>${body}</p>`;
}

// -------------------------------------------------------------------- shell

function headerHtml(view: InboxViewState): string {
  const scan = view.scan;
  const lastScan = formatStamp(scan.finishedAt);
  const cancelHidden = scan.status === 'scanning' || scan.status === 'assessing' ? '' : ' hidden';
  return `<header class="il-header">
    <div class="il-idline">
      <span class="il-mark" aria-hidden="true">${brandShield()}</span>
      <span class="il-wordmark">Recovery Inbox</span>
      <span class="il-flex"></span>
      <span class="il-pill" data-tone-value="${
        scan.status === 'done' && !scan.stale ? 'ok' : scan.stale || scan.status === 'error' ? 'warn' : 'idle'
      }" title="${escapeHtml(scan.statusNote)}">
        <span class="il-dot" aria-hidden="true"></span>
        <span data-live="scanStatus">${escapeHtml(scan.statusLabel)}</span>
      </span>
    </div>
    <div class="il-subline">
      <span class="il-subtitle il-truncate" title="${escapeHtml(view.workspaceName ?? 'NO WORKSPACE FOLDER')}">${escapeHtml(view.workspaceName ?? 'NO WORKSPACE FOLDER')}</span>
      <span class="il-sep" aria-hidden="true">·</span>
      <span class="il-subtitle il-truncate" title="Last scan finished at ${escapeHtml(lastScan ?? 'never')}"><span data-live="lastScan">LAST SCAN ${escapeHtml(lastScan ?? 'never')}</span></span>
      <span class="il-flex"></span>
      <button type="button" class="il-iconbtn" data-act="cancelScan" title="Cancel the running scan"${cancelHidden}>${icon('close', 'il-i-sm')}</button>
      <button type="button" class="il-iconbtn" data-act="refresh" title="Refresh the inbox (re-scan the workspace)">${icon('refresh', 'il-i-sm')}</button>
    </div>
  </header>`;
}

function summaryHtml(view: InboxViewState): string {
  const counts = view.counts;
  const coverage = view.coverageLines
    .map((line) => `<li>${escapeHtml(line)}</li>`)
    .join('');
  return `<section class="il-section" aria-label="Summary">
    <h2 class="il-help-h">Summary</h2>
    <div class="il-ib-summary">
      ${COUNT_KEYS.map(([key, label]) =>
        countCell(
          key,
          label,
          counts[key],
          key === 'attention' || key === 'noBaseline',
        ),
      ).join('\n      ')}
    </div>
    <ul class="il-list il-ib-coverage" data-live="coverage">${coverage}</ul>
  </section>`;
}

// ---------------------------------------------------------------- list mode

function filterButtonsHtml(): string {
  return INBOX_FILTERS.map(
    (filter, index) =>
      `<button type="button" class="il-ib-filter" data-act="filter" data-filter="${escapeHtml(filter.id)}" aria-pressed="${index === 0}">${escapeHtml(filter.label)}</button>`,
  ).join('\n        ');
}

function listToolbarHtml(): string {
  return `<div class="il-ib-toolbar">
      <div class="il-ib-filters" role="group" aria-label="Filter files">
        ${filterButtonsHtml()}
      </div>
      <div class="il-ib-search">
        <input type="search" id="il-ib-search" placeholder="Search paths…" aria-label="Search files by path" autocomplete="off">
        <button type="button" class="il-iconbtn" data-act="clearSearch" title="Clear the search">${icon('close', 'il-i-sm')}</button>
      </div>
    </div>
    <div class="il-ib-sortrow">
      <label class="il-ib-sortlabel" for="il-ib-sort">Sort by</label>
      <select id="il-ib-sort" class="il-ib-sort" data-act="sort">
        <option value="path">Path</option>
        <option value="status">Status</option>
        <option value="eligibility">Eligibility</option>
      </select>
      <span class="il-flex"></span>
      <button type="button" class="il-ib-mini" data-act="collapseAll" title="Collapse every folder">Collapse all</button>
      <button type="button" class="il-ib-mini" data-act="expandAll" title="Expand every folder">Expand all</button>
    </div>`;
}

function selectionBarHtml(view: InboxViewState): string {
  return `<div class="il-ib-selbar">
      <span class="il-ib-seltext" data-live="selection">${escapeHtml(view.selection.text)}</span>
      <span class="il-flex"></span>
      <button type="button" class="il-ib-mini" data-act="selectVisible" title="Select every file matching the current filter and search">Select all shown</button>
      <button type="button" class="il-ib-mini" data-act="selectEligible" title="Select every changed file the engine currently calls recoverable">Select all eligible</button>
      <button type="button" class="il-ib-mini" data-act="clearSelection" title="Clear the selection">Clear</button>
    </div>`;
}

function actionsHtml(view: InboxViewState): string {
  const selected = view.recoverSelected;
  const all = view.recoverAll;
  const note = !selected.enabled ? selected.note : all.note;
  return `<div class="il-ib-actions">
      <button type="button" class="il-rowbtn" id="il-ib-recover-selected" data-act="recoverSelected" title="Review the selected files, then confirm recovery"${selected.enabled ? '' : ' disabled'}>
        ${icon('rotate', 'il-btn-ico')}
        <span class="il-rowtext">
          <span class="il-rowlabel">${escapeHtml(selected.label)}</span>
          <span class="il-rowdesc">${escapeHtml(selected.note)}</span>
        </span>
      </button>
      <button type="button" class="il-rowbtn" data-act="recoverAll" title="Recover every changed file the engine currently calls recoverable"${all.enabled ? '' : ' disabled'}>
        ${icon('rotate', 'il-btn-ico')}
        <span class="il-rowtext">
          <span class="il-rowlabel">${escapeHtml(all.label)}</span>
          <span class="il-rowdesc">${escapeHtml(all.note)}</span>
        </span>
      </button>
      <p class="il-hint" data-live="actionNote">${escapeHtml(note)}</p>
    </div>`;
}

function listSectionHtml(view: InboxViewState): string {
  return `<section class="il-section" aria-label="Changed files">
    <h2 class="il-help-h">Changed files</h2>
    ${listToolbarHtml()}
    ${selectionBarHtml(view)}
    <div class="il-ib-progress" aria-hidden="true"><div id="il-ib-progress-bar"></div></div>
    <p class="il-hint" data-live="progress"></p>
    <div class="il-ib-list" id="il-ib-list" aria-live="polite"></div>
    <div class="il-ib-pager" id="il-ib-pager" hidden>
      <button type="button" class="il-ib-mini" id="il-ib-prev" data-act="pagePrev">← Prev</button>
      <span data-live="page"></span>
      <button type="button" class="il-ib-mini" id="il-ib-next" data-act="pageNext">Next →</button>
    </div>
    ${actionsHtml(view)}
  </section>`;
}

// --------------------------------------------------------------- review mode

function reviewSectionHtml(view: InboxViewState): string {
  const review = view.review;
  if (review === null) {
    return '';
  }
  const warnings =
    review.warnings.length === 0
      ? ''
      : `<ul class="il-list il-ib-warns">${review.warnings
          .map((warning) => `<li class="il-li-warn">${escapeHtml(warning)}</li>`)
          .join('')}</ul>`;
  const notice = review.notice === null ? '' : `<p class="il-ib-notice" role="status">${escapeHtml(review.notice)}</p>`;
  const scopeCounts =
    review.scopeCounts === null
      ? ''
      : `<div class="il-ib-scope">
        ${countCell('scopeChanged', 'Changed files', review.scopeCounts.changed, false)}
        ${countCell('scopeEligible', 'Eligible now', review.scopeCounts.eligible, false)}
        ${countCell('scopeAttention', 'Need attention', review.scopeCounts.attention, review.scopeCounts.attention > 0)}
        ${countCell('scopeNoBaseline', 'Without usable baseline', review.scopeCounts.noBaseline, false)}
      </div>
      <p class="il-hint">Scope of "Recover All Eligible Changed Files": every changed file with
        verified evidence that passes the engine checks. Everything else is listed below with
        its reason and is NOT recovered by this run.</p>`;
  return `<section class="il-section" aria-label="Recovery review">
    <h2 class="il-help-h">Review recovery</h2>
    <p class="il-hint">
      ${review.scope === 'all'
        ? 'Recover All Eligible Changed Files: every changed file with verified evidence that passed the engine checks.'
        : review.scope === 'retry'
          ? 'Retry: only the files that failed the last run, re-validated by the engine just now.'
          : 'Recover Selected: the files you selected in the inbox.'}
      Nothing is written until you confirm below.
    </p>
    ${scopeCounts}
    <div class="il-ib-scope">
      ${countCell('reviewScope', 'In scope', review.requested, false)}
      ${countCell('reviewIncluded', 'Will be recovered', review.included.length, false)}
      ${countCell('reviewExcluded', 'Excluded (with reasons)', review.excluded.length, review.excluded.length > 0)}
    </div>
    ${notice}
    ${warnings}
    <h3 class="il-help-h il-ib-sub">Files to recover (${review.included.length})</h3>
    <div class="il-ib-list" id="il-ib-review-included"></div>
    <h3 class="il-help-h il-ib-sub">Excluded from this run (${review.excluded.length})</h3>
    <div class="il-ib-list" id="il-ib-review-excluded"></div>
    <div class="il-ib-actions">
      <button type="button" class="il-rowbtn" data-act="back" title="Back to the file list - nothing is recovered">
        ${icon('back', 'il-btn-ico')}
        <span class="il-rowtext">
          <span class="il-rowlabel">Back to list</span>
          <span class="il-rowdesc">Return to the inbox without changing any file.</span>
        </span>
      </button>
      <button type="button" class="il-rowbtn il-guarded" data-act="confirm" title="Review the exact scope above, then confirm recovery"${review.included.length === 0 ? ' disabled' : ''}>
        ${icon('lock', 'il-btn-ico')}
        <span class="il-rowtext">
          <span class="il-rowlabel">Confirm Recovery (${review.included.length})</span>
          <span class="il-rowdesc">Asks for explicit approval, then revalidates every file immediately before writing.</span>
        </span>
      </button>
    </div>
  </section>`;
}

// -------------------------------------------------------------- results mode

function resultsSectionHtml(view: InboxViewState): string {
  const results = view.results;
  if (results === null) {
    return '';
  }
  const counts = results.counts;
  const retryable = results.entries.filter(
    (entry) => entry.outcome === 'failed' || entry.outcome === 'attention',
  ).length;
  return `<section class="il-section" aria-label="Recovery results">
    <h2 class="il-help-h">Recovery results</h2>
    <p class="il-hint">
      Approved by <strong>${escapeHtml(results.approvedBy)}</strong> · finished ${escapeHtml(
        formatStamp(results.finishedAt) ?? 'just now',
      )}${results.running ? ' · still running…' : ''}
    </p>
    <div class="il-ib-scope">
      ${countCell('runRecovered', 'Recovered & verified', counts.recovered, false)}
      ${countCell('runSkipped', 'Skipped (no longer eligible)', counts.skipped, false)}
      ${countCell('runFailed', 'Failed', counts.failed, counts.failed > 0)}
      ${countCell('runAttention', 'Need attention', counts.attention, counts.attention > 0)}
    </div>
    <div class="il-ib-list" id="il-ib-results"></div>
    <div class="il-ib-actions">
      <button type="button" class="il-rowbtn" data-act="refresh" title="Rescan the workspace and rebuild the inbox">
        ${icon('refresh', 'il-btn-ico')}
        <span class="il-rowtext">
          <span class="il-rowlabel">Refresh Inbox</span>
          <span class="il-rowdesc">Re-scan the workspace after this run.</span>
        </span>
      </button>
      <button type="button" class="il-rowbtn" data-act="retry" title="Re-validate the failed files with the engine, then review again"${retryable === 0 ? ' disabled' : ''}>
        ${icon('rotate', 'il-btn-ico')}
        <span class="il-rowtext">
          <span class="il-rowlabel">Retry failed (${retryable})</span>
          <span class="il-rowdesc">Fresh engine validation first - nothing is retried on stale proof.</span>
        </span>
      </button>
      <button type="button" class="il-rowbtn" data-act="verifyRecovery" title="Run the existing Verify Recovery command">
        ${icon('badgeCheck', 'il-btn-ico')}
        <span class="il-rowtext">
          <span class="il-rowlabel">Verify Recovery</span>
          <span class="il-rowdesc">Re-check the restored files against their baselines.</span>
        </span>
      </button>
      <button type="button" class="il-rowbtn" data-act="close" title="Close this panel">
        ${icon('close', 'il-btn-ico')}
        <span class="il-rowtext">
          <span class="il-rowlabel">Close</span>
          <span class="il-rowdesc">Close the inbox. Nothing else is changed.</span>
        </span>
      </button>
    </div>
  </section>`;
}

// -------------------------------------------------------------------- script

/**
 * The inbox script: a small pure core (filter/sort/search/paginate/group -
 * unit-tested headlessly by evaluating this source) plus a thin DOM adapter
 * that only ever builds nodes with createElement/textContent.
 */
export const INBOX_SCRIPT = `(function () {
  'use strict';

  function filterRows(rows, filterId, query) {
    var q = (query || '').trim().toLowerCase();
    return rows.filter(function (row) {
      var match;
      switch (filterId) {
        case 'all-changed':
          match = row.flags.changed || row.flags.unprotected || row.status === 'unknown';
          break;
        case 'recoverable':
          match = row.flags.recoverable;
          break;
        case 'modified':
          match = row.flags.modified;
          break;
        case 'deleted':
          match = row.flags.deleted;
          break;
        case 'attention':
          match = row.flags.attention;
          break;
        case 'not-recoverable':
          match = !row.flags.recoverable && !row.flags.unchanged;
          break;
        case 'unchanged':
          match = row.flags.unchanged;
          break;
        default:
          match = true;
      }
      if (!match) { return false; }
      if (q === '') { return true; }
      return row.resource.toLowerCase().indexOf(q) !== -1;
    });
  }

  function sortRows(rows, sortId) {
    var copy = rows.slice();
    copy.sort(function (a, b) {
      var d;
      if (sortId === 'status') {
        d = a.rankStatus - b.rankStatus || a.resource.localeCompare(b.resource);
      } else if (sortId === 'eligibility') {
        d = a.rankEligibility - b.rankEligibility || a.resource.localeCompare(b.resource);
      } else {
        d = a.resource.localeCompare(b.resource);
      }
      return d;
    });
    return copy;
  }

  function pageSlice(rows, page, pageSize) {
    var pages = Math.max(1, Math.ceil(rows.length / pageSize));
    var p = Math.min(Math.max(1, page), pages);
    return { rows: rows.slice((p - 1) * pageSize, p * pageSize), page: p, pages: pages };
  }

  function groupRows(rows) {
    var groups = [];
    var index = {};
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var key = row.dir;
      var group = index[key];
      if (!group) {
        group = { dir: key, rows: [] };
        index[key] = group;
        groups.push(group);
      }
      group.rows.push(row);
    }
    return groups;
  }

  function visibleRows(state) {
    var filtered = filterRows(state.rows, state.filter, state.query);
    var sorted = sortRows(filtered, state.sort);
    return pageSlice(sorted, state.page, state.pageSize);
  }

  function selectionText(rows, selection) {
    var count = 0, eligible = 0, attention = 0, pending = 0;
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      if (!selection[row.resource]) { continue; }
      count++;
      if (row.eligibility === 'eligible') { eligible++; }
      else if (row.eligibility === 'pending') { pending++; }
      if (row.flags.attention) { attention++; }
    }
    var parts = [count + ' file' + (count === 1 ? '' : 's') + ' selected', eligible + ' eligible'];
    if (pending > 0) { parts.push(pending + ' assessing'); }
    parts.push(attention + ' require attention');
    return parts.join(' · ');
  }

  var api = {
    filterRows: filterRows,
    sortRows: sortRows,
    pageSlice: pageSlice,
    groupRows: groupRows,
    visibleRows: visibleRows,
    selectionText: selectionText,
  };

  if (typeof document === 'undefined') {
    return api;
  }

  var vscodeApi = typeof acquireVsCodeApi === 'function'
    ? acquireVsCodeApi()
    : { postMessage: function () {} };

  var payloadNode = document.getElementById('il-ib-payload');
  var payload = {};
  try {
    payload = JSON.parse(payloadNode ? payloadNode.textContent || '' : '{}');
  } catch (error) {
    payload = {};
  }

  var rows = payload.rows || [];
  var state = {
    rows: rows,
    filter: 'all-changed',
    query: '',
    sort: 'path',
    page: 1,
    pageSize: 200,
    reviewPage: 1,
    resultsPage: 1,
    selection: {},
    collapsed: {},
  };
  var selectionResources = payload.selectionResources || [];
  for (var i = 0; i < selectionResources.length; i++) {
    state.selection[selectionResources[i]] = true;
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined && text !== null) { node.textContent = text; }
    return node;
  }

  function send(message) {
    vscodeApi.postMessage(message);
  }

  function chip(label, tone) {
    var node = el('span', 'il-chip');
    node.setAttribute('data-tone-value', tone);
    node.appendChild(el('span', null, label));
    return node;
  }

  function rowNode(row) {
    var wrap = el('div', 'il-ib-row');
    wrap.setAttribute('data-resource', row.resource);
    var label = el('label', 'il-ib-check');
    var box = document.createElement('input');
    box.type = 'checkbox';
    box.className = 'il-ib-box';
    box.setAttribute('data-act', 'rowcheck');
    box.setAttribute('data-resource', row.resource);
    box.checked = !!state.selection[row.resource];
    label.appendChild(box);
    label.appendChild(el('span', 'il-ib-name', row.name));
    wrap.appendChild(label);
    var pathNode = el('span', 'il-ib-path il-mono', row.resource);
    pathNode.setAttribute('title', row.resource);
    wrap.appendChild(pathNode);
    wrap.appendChild(chip(row.statusLabel, row.statusTone));
    wrap.appendChild(chip(row.evidenceLabel, row.evidenceTone));
    wrap.appendChild(chip(row.eligibilityLabel, row.eligibilityTone));
    wrap.appendChild(el('span', 'il-ib-reason', row.reason));
    if (row.previewable) {
      var btn = el('button', 'il-ib-preview', 'Preview');
      btn.type = 'button';
      btn.setAttribute('data-act', 'preview');
      btn.setAttribute('data-resource', row.resource);
      wrap.appendChild(btn);
    } else if (row.previewNote) {
      wrap.appendChild(el('span', 'il-ib-note', row.previewNote));
    }
    if (row.details) {
      var tech = el('details', 'il-ib-tech');
      tech.appendChild(el('summary', null, 'Details'));
      tech.appendChild(el('p', null, row.details));
      wrap.appendChild(tech);
    }
    return wrap;
  }

  function renderList() {
    var list = document.getElementById('il-ib-list');
    if (!list) { return; }
    list.textContent = '';
    var view = visibleRows(state);
    var groups = groupRows(view.rows);
    if (groups.length === 0) {
      list.appendChild(
        el('p', 'il-ib-empty', rows.length === 0
          ? 'No files discovered yet. Refresh to scan the workspace.'
          : 'No files match the current filter and search.'),
      );
    }
    for (var g = 0; g < groups.length; g++) {
      var group = groups[g];
      var details = el('details', 'il-ib-group');
      if (!state.collapsed[group.dir]) { details.setAttribute('open', 'open'); }
      var summary = el('summary', 'il-ib-group-summary');
      summary.appendChild(el('span', 'il-ib-group-dir', group.dir === '.' ? '(workspace root)' : group.dir));
      summary.appendChild(el('span', 'il-ib-group-count', String(group.rows.length)));
      details.appendChild(summary);
      for (var r = 0; r < group.rows.length; r++) {
        details.appendChild(rowNode(group.rows[r]));
      }
      list.appendChild(details);
    }
    var pager = document.getElementById('il-ib-pager');
    if (pager) {
      pager.hidden = view.pages <= 1;
      var label = document.querySelector('[data-live="page"]');
      if (label) {
        label.textContent = 'Page ' + view.page + ' of ' + view.pages +
          ' (' + view.rows.length + ' of ' + rows.length + ' files)';
      }
      var prev = document.getElementById('il-ib-prev');
      var next = document.getElementById('il-ib-next');
      if (prev) { prev.disabled = view.page <= 1; }
      if (next) { next.disabled = view.page >= view.pages; }
    }
    updateSelectionUI();
  }

  function updateSelectionUI() {
    var node = document.querySelector('[data-live="selection"]');
    if (node) { node.textContent = selectionText(rows, state.selection); }
    var boxes = document.querySelectorAll('#il-ib-list input[data-act="rowcheck"]');
    for (var i = 0; i < boxes.length; i++) {
      var box = boxes[i];
      box.checked = !!state.selection[box.getAttribute('data-resource')];
    }
  }

  function syncFilterButtons() {
    var buttons = document.querySelectorAll('[data-act="filter"]');
    for (var i = 0; i < buttons.length; i++) {
      var button = buttons[i];
      if (button.setAttribute) {
        button.setAttribute('aria-pressed', button.getAttribute('data-filter') === state.filter ? 'true' : 'false');
      }
    }
  }

  function applyActions(actions) {
    var selected = document.getElementById('il-ib-recover-selected');
    if (selected) {
      selected.disabled = !actions.recoverSelected.enabled;
      selected.textContent = actions.recoverSelected.label;
    }
    var all = document.getElementById('il-ib-recover-all');
    if (all) {
      all.disabled = !actions.recoverAll.enabled;
      all.textContent = actions.recoverAll.label;
    }
    var note = document.querySelector('[data-live="actionNote"]');
    if (note) {
      note.textContent = !actions.recoverSelected.enabled
        ? actions.recoverSelected.note
        : actions.recoverAll.note;
    }
  }

  var UNKNOWN_TITLE =
    'This value could not be derived from the validated evidence, so it is reported as Unknown.';
  var WARN_COUNTS = { attention: true, noBaseline: true };

  function setText(selector, text) {
    var node = document.querySelector(selector);
    if (node) { node.textContent = text; }
  }

  function formatNumber(value) {
    return String(value).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  function formatStamp(iso) {
    if (!iso) { return 'never'; }
    var ms = Date.parse(iso);
    if (!isFinite(ms)) { return 'never'; }
    var date = new Date(ms);
    function pad(n) { return (n < 10 ? '0' : '') + n; }
    return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate()) +
      ' ' + pad(date.getHours()) + ':' + pad(date.getMinutes());
  }

  function setCount(key, value) {
    var node = document.querySelector('[data-live="count-' + key + '"]');
    if (!node) { return; }
    if (value === null || value === undefined) {
      node.textContent = 'Unknown';
      node.className = 'il-ib-unknown';
      node.setAttribute('title', UNKNOWN_TITLE);
      node.removeAttribute('data-tone-value');
      return;
    }
    node.textContent = formatNumber(value);
    node.className = 'il-ib-stat-v';
    node.removeAttribute('title');
    if (WARN_COUNTS[key] && value > 0) {
      node.setAttribute('data-tone-value', 'warn');
    } else {
      node.removeAttribute('data-tone-value');
    }
  }

  function setList(selector, items) {
    var list = document.querySelector(selector);
    if (!list) { return; }
    list.textContent = '';
    for (var i = 0; i < items.length; i++) {
      list.appendChild(el('li', null, items[i]));
    }
  }

  function setBanner(selector, text) {
    var node = document.querySelector(selector);
    if (!node) { return; }
    node.textContent = text || '';
    node.hidden = !text;
  }

  /*
   * Apply a new inbox state IN PLACE. The document is never replaced while
   * the inbox is open, so the focus, the scroll position, the search text and
   * the selection survive every update - and a click is never swallowed by a
   * reload that happens while the user is reaching for a control.
   */
  function applyState(view) {
    if (!view) { return; }
    if (view.rows) {
      rows = view.rows;
      state.rows = rows;
    }
    if (view.selectionResources) {
      selectionResources = view.selectionResources;
      state.selection = {};
      for (var s = 0; s < selectionResources.length; s++) {
        state.selection[selectionResources[s]] = true;
      }
    }
    var scan = view.scan || {};
    setText('[data-live="scanStatus"]', scan.statusLabel || '');
    setText('[data-live="scanNote"]', scan.statusNote || '');
    setText('[data-live="lastScan"]', 'LAST SCAN ' + formatStamp(scan.finishedAt));
    var pill = document.querySelector('.il-pill');
    if (pill) {
      pill.setAttribute(
        'data-tone-value',
        scan.status === 'done' && !scan.stale
          ? 'ok'
          : scan.stale || scan.status === 'error'
            ? 'warn'
            : 'idle',
      );
      pill.setAttribute('title', scan.statusNote || '');
    }
    var cancel = document.querySelector('[data-act="cancelScan"]');
    if (cancel) {
      cancel.hidden = !(scan.status === 'scanning' || scan.status === 'assessing');
    }
    var counts = view.counts || {};
    setCount('examined', counts.examined);
    setCount('changed', counts.changed);
    setCount('verifiedEvidence', counts.verifiedEvidence);
    setCount('recoverableModified', counts.recoverableModified);
    setCount('recoverableDeleted', counts.recoverableDeleted);
    setCount('attention', counts.attention);
    setCount('noBaseline', counts.noBaseline);
    setList('[data-live="coverage"]', view.coverageLines || []);
    setBanner('[data-live="notice"]', view.notice || '');
    setBanner('[data-live="stale"]', scan.stale ? (scan.staleReason || '') : '');
    document.body.classList.toggle('is-busy', !!view.busy);
    var progress = scan.progress;
    setText(
      '[data-live="progress"]',
      progress ? progress.phase + ' ' + progress.done + '/' + progress.total : '',
    );
    var bar = document.getElementById('il-ib-progress-bar');
    if (bar) {
      var pct = progress && progress.total > 0
        ? Math.round((progress.done / progress.total) * 100)
        : 0;
      bar.style.width = pct + '%';
    }
    if (view.selection) { setText('[data-live="selection"]', view.selection.text); }
    if (view.recoverSelected && view.recoverAll) {
      applyActions({ recoverSelected: view.recoverSelected, recoverAll: view.recoverAll });
    }
    if (document.getElementById('il-ib-list')) { renderList(); }
    if (view.review && document.getElementById('il-ib-review-included')) {
      renderReview(view.review);
    }
    if (view.results && document.getElementById('il-ib-results')) {
      renderResults(view.results);
    }
  }

  function reviewEntryNode(entry) {
    var wrap = el('div', 'il-ib-row');
    wrap.setAttribute('data-resource', entry.resource);
    wrap.appendChild(el('span', 'il-ib-name', entry.name));
    var pathNode = el('span', 'il-ib-path il-mono', entry.resource);
    pathNode.setAttribute('title', entry.resource);
    wrap.appendChild(pathNode);
    wrap.appendChild(el('span', 'il-ib-reason', entry.operation ? 'Operation: ' + entry.operation : 'restore'));
    if (entry.diffable) {
      var btn = el('button', 'il-ib-preview', 'View diff');
      btn.type = 'button';
      btn.setAttribute('data-act', 'viewDiff');
      btn.setAttribute('data-resource', entry.resource);
      wrap.appendChild(btn);
    } else if (entry.previewNote) {
      wrap.appendChild(el('span', 'il-ib-note', entry.previewNote));
    }
    return wrap;
  }

  function excludedNode(entry) {
    var wrap = el('div', 'il-ib-row');
    wrap.setAttribute('data-resource', entry.resource);
    wrap.appendChild(el('span', 'il-ib-name', entry.name));
    var pathNode = el('span', 'il-ib-path il-mono', entry.resource);
    pathNode.setAttribute('title', entry.resource);
    wrap.appendChild(pathNode);
    wrap.appendChild(el('span', 'il-ib-reason', entry.reason));
    return wrap;
  }

  function renderReview(review) {
    var included = document.getElementById('il-ib-review-included');
    if (included) {
      included.textContent = '';
      if (review.included.length === 0) {
        included.appendChild(el('p', 'il-ib-empty', 'No file is currently eligible for recovery.'));
      }
      var view = pageSlice(review.included, state.reviewPage, 200);
      var groups = groupRows(view.rows);
      for (var g = 0; g < groups.length; g++) {
        var group = groups[g];
        var details = el('details', 'il-ib-group');
        details.setAttribute('open', 'open');
        var summary = el('summary', 'il-ib-group-summary');
        summary.appendChild(el('span', 'il-ib-group-dir', group.dir === '.' ? '(workspace root)' : group.dir));
        summary.appendChild(el('span', 'il-ib-group-count', String(group.rows.length)));
        details.appendChild(summary);
        for (var r = 0; r < group.rows.length; r++) {
          details.appendChild(reviewEntryNode(group.rows[r]));
        }
        included.appendChild(details);
      }
      if (view.pages > 1) {
        included.appendChild(el('p', 'il-ib-empty',
          'Page ' + view.page + ' of ' + view.pages + ' - use the pager below.'));
      }
    }
    var excluded = document.getElementById('il-ib-review-excluded');
    if (excluded) {
      excluded.textContent = '';
      if (review.excluded.length === 0) {
        excluded.appendChild(el('p', 'il-ib-empty', 'Nothing was excluded from this scope.'));
      }
      var shown = review.excluded.slice(0, 100);
      for (var e = 0; e < shown.length; e++) {
        excluded.appendChild(excludedNode(shown[e]));
      }
      if (review.excluded.length > shown.length) {
        excluded.appendChild(el('p', 'il-ib-empty',
          '… and ' + (review.excluded.length - shown.length) + ' more excluded file(s).'));
      }
    }
  }

  function resultNode(entry) {
    var wrap = el('div', 'il-ib-row');
    wrap.setAttribute('data-resource', entry.resource);
    wrap.appendChild(chip(entry.label, entry.tone));
    wrap.appendChild(el('span', 'il-ib-name', entry.name));
    var pathNode = el('span', 'il-ib-path il-mono', entry.resource);
    pathNode.setAttribute('title', entry.resource);
    wrap.appendChild(pathNode);
    wrap.appendChild(el('span', 'il-ib-reason', entry.message));
    if (entry.outcome === 'recovered') {
      var open = el('button', 'il-ib-preview', 'Open file');
      open.type = 'button';
      open.setAttribute('data-act', 'openFile');
      open.setAttribute('data-resource', entry.resource);
      wrap.appendChild(open);
    }
    if (entry.diffable) {
      var diff = el('button', 'il-ib-preview', 'View diff');
      diff.type = 'button';
      diff.setAttribute('data-act', 'viewDiff');
      diff.setAttribute('data-resource', entry.resource);
      wrap.appendChild(diff);
    }
    if (entry.details) {
      var tech = el('details', 'il-ib-tech');
      tech.appendChild(el('summary', null, 'Details'));
      tech.appendChild(el('p', null, entry.details));
      wrap.appendChild(tech);
    }
    return wrap;
  }

  function renderResults(results) {
    var container = document.getElementById('il-ib-results');
    if (!container) { return; }
    container.textContent = '';
    if (results.entries.length === 0) {
      container.appendChild(el('p', 'il-ib-empty', 'No files were processed in this run.'));
    }
    var view = pageSlice(results.entries, state.resultsPage, 200);
    for (var i = 0; i < view.rows.length; i++) {
      container.appendChild(resultNode(view.rows[i]));
    }
    if (view.pages > 1) {
      container.appendChild(el('p', 'il-ib-empty',
        'Page ' + view.page + ' of ' + view.pages + ' - use the pager below.'));
    }
  }

  var searchTimer = null;
  function scheduleSearch(value) {
    if (searchTimer) { clearTimeout(searchTimer); }
    searchTimer = setTimeout(function () {
      state.query = value;
      state.page = 1;
      renderList();
    }, 150);
  }

  document.addEventListener('click', function (event) {
    var target = event.target;
    var node = target && typeof target.closest === 'function'
      ? target.closest('[data-act]')
      : null;
    if (!node || node.disabled) { return; }
    var act = node.getAttribute('data-act');
    var resource = node.getAttribute('data-resource') || '';
    if (act === 'filter') {
      state.filter = node.getAttribute('data-filter') || 'all-changed';
      state.page = 1;
      syncFilterButtons();
      renderList();
      return;
    }
    if (act === 'clearSearch') {
      var input = document.getElementById('il-ib-search');
      if (input) { input.value = ''; }
      state.query = '';
      state.page = 1;
      renderList();
      return;
    }
    if (act === 'selectVisible') {
      // EVERY file matching the current filter and search - not just the
      // page the user happens to be looking at.
      var matching = sortRows(filterRows(rows, state.filter, state.query), state.sort);
      var resources = [];
      for (var i = 0; i < matching.length; i++) { resources.push(matching[i].resource); }
      send({ type: 'select', add: resources });
      return;
    }
    if (act === 'selectEligible') {
      var eligible = [];
      for (var e = 0; e < rows.length; e++) {
        if (rows[e].flags.recoverable) { eligible.push(rows[e].resource); }
      }
      send({ type: 'select', add: eligible });
      return;
    }
    if (act === 'clearSelection') { send({ type: 'clearSelection' }); return; }
    if (act === 'pagePrev') { state.page = Math.max(1, state.page - 1); renderList(); return; }
    if (act === 'pageNext') {
      var current = visibleRows(state);
      state.page = Math.min(current.pages, state.page + 1);
      renderList();
      return;
    }
    if (act === 'collapseAll') {
      var collapsed = groupRows(visibleRows(state).rows);
      for (var c = 0; c < collapsed.length; c++) { state.collapsed[collapsed[c].dir] = true; }
      renderList();
      return;
    }
    if (act === 'expandAll') { state.collapsed = {}; renderList(); return; }
    if (act === 'preview') { send({ type: 'preview', resource: resource }); return; }
    if (act === 'refresh') { send({ type: 'refresh' }); return; }
    if (act === 'cancelScan') { send({ type: 'cancelScan' }); return; }
    if (act === 'recoverSelected') { send({ type: 'recoverSelected' }); return; }
    if (act === 'recoverAll') { send({ type: 'recoverAll' }); return; }
    if (act === 'back') { send({ type: 'back' }); return; }
    if (act === 'confirm') { send({ type: 'confirm' }); return; }
    if (act === 'viewDiff') { send({ type: 'viewDiff', resource: resource }); return; }
    if (act === 'openFile') { send({ type: 'openFile', resource: resource }); return; }
    if (act === 'retry') { send({ type: 'retry' }); return; }
    if (act === 'verifyRecovery') { send({ type: 'verifyRecovery' }); return; }
    if (act === 'close') { send({ type: 'close' }); return; }
  });

  document.addEventListener('change', function (event) {
    var target = event.target;
    if (!target || !target.getAttribute) { return; }
    var act = target.getAttribute('data-act');
    if (act === 'rowcheck') {
      var resource = target.getAttribute('data-resource') || '';
      if (target.checked) {
        state.selection[resource] = true;
        send({ type: 'select', add: [resource] });
      } else {
        delete state.selection[resource];
        send({ type: 'select', remove: [resource] });
      }
      updateSelectionUI();
      return;
    }
    if (act === 'sort') {
      state.sort = target.value;
      state.page = 1;
      renderList();
    }
  });

  document.addEventListener('input', function (event) {
    var target = event.target;
    if (target && target.id === 'il-ib-search') { scheduleSearch(target.value); }
  });

  window.addEventListener('message', function (event) {
    var message = event.data;
    if (!message || message.type !== 'update' || !message.view) { return; }
    applyState(message.view);
  });

  renderList();
  if (payload.review) { renderReview(payload.review); }
  if (payload.results) { renderResults(payload.results); }
  send({ type: 'ready' });

  return api;
})();`;

// -------------------------------------------------------------------- styles

/**
 * Inbox-specific layout only. Every color, size, radius and font comes from
 * the shared tokens in STYLESHEET - no new palette values are introduced.
 */
const INBOX_STYLES = `
.il-ib { max-width: 1120px; margin: 0 auto; width: 100%; }
/* the header must be able to shrink: a truncated label may never widen the page */
.il-ib .il-idline, .il-ib .il-subline { min-width: 0; }
.il-ib .il-subtitle, .il-ib .il-wordmark { min-width: 0; }
.il-ib .il-wordmark { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/*
 * The sidebar deliberately pulls its header out of the body padding so it
 * reaches the panel edge. In the Inbox that made the header wider than the
 * content column, so the brand line no longer lined up with the summary
 * cards. The Inbox keeps the header inside the content column instead.
 */
.il-ib .il-header { margin: 0; padding: var(--il-s2) 0; }
.il-ib-summary {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  /* every card is as tall as the tallest one, so no row drifts out of line */
  grid-auto-rows: 1fr;
  align-items: stretch;
  gap: var(--il-s2); min-width: 0;
}
.il-ib-stat {
  /* the label may wrap to one or two lines; the value is pinned to the
     bottom so every number in a row sits on the same line */
  display: grid; grid-template-rows: 1fr auto; align-content: start;
  gap: var(--il-s1); min-width: 0;
  background: var(--il-surface); border: 1px solid var(--il-border-soft);
  border-radius: var(--il-r-md); padding: var(--il-s3);
}.il-ib-stat-l {
  font-size: var(--il-fs-sm); font-weight: var(--il-fw-bold);
  letter-spacing: var(--il-ls-wide); text-transform: uppercase; color: var(--il-text2);
  overflow-wrap: anywhere;
}
.il-ib-stat-v {
  font-family: var(--il-font-display); font-size: var(--il-fs-h2);
  font-weight: var(--il-fw-black); font-variant-numeric: tabular-nums;
  line-height: var(--il-lh-tight); overflow-wrap: anywhere;
}
.il-ib-unknown { color: var(--il-text2); font-size: var(--il-fs-h2); font-weight: var(--il-fw-semi); }
.il-ib-coverage { margin: var(--il-s2) 0 0; }
.il-ib-coverage li { font-size: var(--il-fs-sm); }

.il-ib-toolbar { display: flex; gap: var(--il-s2); flex-wrap: wrap; align-items: center; justify-content: space-between; }
.il-ib-filters { display: flex; gap: var(--il-s1); flex-wrap: wrap; }
.il-ib-filter {
  padding: 3px var(--il-s3); min-height: 26px;
  border: 1px solid var(--il-border); border-radius: var(--il-r-sm);
  background: var(--il-inset); color: var(--il-text2);
  font-size: var(--il-fs-meta); font-weight: var(--il-fw-semi); letter-spacing: var(--il-ls);
}
.il-ib-filter:hover { border-color: var(--il-accent); color: var(--il-accent); }
.il-ib-filter[aria-pressed="true"] { border-color: var(--il-accent); color: var(--il-accent); background: var(--il-surface); }
.il-ib-search { display: inline-flex; align-items: center; gap: var(--il-s1); }
.il-ib-search input {
  min-width: 220px; padding: 3px var(--il-s3); min-height: 26px;
  border: 1px solid var(--il-border); border-radius: var(--il-r-sm);
  background: var(--il-inset); color: var(--il-text);
  font-size: var(--il-fs-meta);
}
.il-ib-search input:focus { outline: 1px solid var(--il-accent); outline-offset: 1px; }
.il-ib-sortrow { display: flex; gap: var(--il-s2); align-items: center; margin-top: var(--il-s2); }
.il-ib-sortlabel { font-size: var(--il-fs-sm); color: var(--il-text2); }
.il-ib-sort {
  padding: 3px var(--il-s2); min-height: 26px;
  border: 1px solid var(--il-border); border-radius: var(--il-r-sm);
  background: var(--il-inset); color: var(--il-text);
  font-size: var(--il-fs-meta);
}
.il-ib-mini {
  padding: 3px var(--il-s3); min-height: 26px;
  border: 1px solid var(--il-border); border-radius: var(--il-r-sm);
  background: var(--il-inset); color: var(--il-text2);
  font-size: var(--il-fs-meta); font-weight: var(--il-fw-semi); letter-spacing: var(--il-ls);
}
.il-ib-mini:hover:not(:disabled) { border-color: var(--il-accent); color: var(--il-accent); }
.il-ib-mini:disabled { border-style: dashed; color: var(--il-text2); opacity: 0.7; }

.il-ib-selbar { display: flex; gap: var(--il-s2); align-items: center; flex-wrap: wrap; margin-top: var(--il-s2); }
.il-ib-seltext { font-size: var(--il-fs-body); font-weight: var(--il-fw-semi); }

.il-ib-progress { height: 4px; background: var(--il-inset); border-radius: 2px; overflow: hidden; margin-top: var(--il-s2); }
.il-ib-progress > div { height: 100%; background: var(--il-accent); width: 0; transition: width 0.2s ease; }

.il-ib-list { display: flex; flex-direction: column; gap: var(--il-s2); min-width: 0; margin-top: var(--il-s2); }
.il-ib-group { background: var(--il-surface); border: 1px solid var(--il-border-soft); border-radius: var(--il-r-md); }
.il-ib-group-summary {
  display: flex; gap: var(--il-s2); align-items: center;
  padding: var(--il-s2) var(--il-s3); cursor: pointer;
  font-size: var(--il-fs-body); font-weight: var(--il-fw-semi);
}
.il-ib-group-summary:hover { color: var(--il-accent); }
.il-ib-group-dir { overflow-wrap: anywhere; min-width: 0; }
.il-ib-group-count { color: var(--il-text2); font-size: var(--il-fs-sm); font-weight: var(--il-fw-semi); }
.il-ib-row {
  display: flex; align-items: center; gap: var(--il-s2); flex-wrap: wrap;
  padding: var(--il-s2) var(--il-s3); border-top: 1px solid var(--il-border-soft);
}
.il-ib-row:first-child { border-top: none; }
.il-ib-check { display: inline-flex; align-items: center; gap: var(--il-s1); min-width: 0; }
.il-ib-box { accent-color: var(--il-accent); }
.il-ib-name { font-weight: var(--il-fw-semi); overflow-wrap: anywhere; min-width: 0; }
.il-ib-path { color: var(--il-text2); font-size: var(--il-fs-sm); min-width: 0; overflow-wrap: anywhere; }
.il-ib-reason {
  flex: 1 1 100%; min-width: 0; font-size: var(--il-fs-sm); line-height: var(--il-lh);
  color: var(--il-text2); overflow-wrap: anywhere;
}
.il-ib-note { font-size: var(--il-fs-sm); color: var(--il-text2); }
.il-ib-preview {
  display: inline-flex; align-items: center; gap: var(--il-s1); flex: 0 0 auto;
  padding: 3px var(--il-s3); min-height: 26px;
  border: 1px solid var(--il-border); border-radius: var(--il-r-sm);
  background: var(--il-inset); color: var(--il-text);
  font-size: var(--il-fs-meta); font-weight: var(--il-fw-semi); letter-spacing: var(--il-ls);
}
.il-ib-preview:hover:not(:disabled) { border-color: var(--il-accent); color: var(--il-accent); }
.il-ib-preview:disabled { border-style: dashed; color: var(--il-text2); }
.il-ib-tech { flex: 1 1 100%; }
.il-ib-tech summary { cursor: pointer; font-size: var(--il-fs-sm); color: var(--il-text2); }
.il-ib-tech p { font-size: var(--il-fs-sm); color: var(--il-text2); overflow-wrap: anywhere; }
.il-ib-empty { color: var(--il-text2); font-size: var(--il-fs-body); }
.il-ib-pager { display: flex; gap: var(--il-s2); align-items: center; justify-content: center; margin-top: var(--il-s2); }
.il-ib-actions { display: flex; flex-direction: column; gap: var(--il-s2); margin-top: var(--il-s3); }
.il-ib-actions .il-rowbtn:disabled { border-style: dashed; }
.il-ib-sub { margin-top: var(--il-s3); font-size: var(--il-fs-h2); }
.il-ib-scope {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  grid-auto-rows: 1fr; align-items: stretch;
  gap: var(--il-s2); min-width: 0; margin-top: var(--il-s2);
}
.il-ib-warns { margin: var(--il-s2) 0 0; }
.il-ib-warns li { font-size: var(--il-fs-sm); }
.il-ib-notice {
  margin: var(--il-s2) 0 0; padding: var(--il-s2) var(--il-s3);
  border: 1px solid #4a3b12; background: #15120A; color: var(--il-warn);
  border-radius: var(--il-r-md); font-size: var(--il-fs-body); line-height: var(--il-lh);
  overflow-wrap: anywhere;
}
.il-ib-stale {
  margin: 0; padding: var(--il-s2) var(--il-s3);
  border: 1px solid #4a3b12; background: #15120A; color: var(--il-warn);
  border-radius: var(--il-r-md); font-size: var(--il-fs-body); line-height: var(--il-lh);
  overflow-wrap: anywhere;
}
.il-root.is-busy [data-act] { opacity: 0.55; pointer-events: none; }
@media (max-width: 520px) {
  .il-ib-toolbar { align-items: flex-start; }
  .il-ib-search input { min-width: 0; width: 100%; }
}
`;

// -------------------------------------------------------------------- render

function payloadJson(view: InboxViewState): string {
  const payload = {
    rows: view.rows,
    review: view.review,
    results: view.results,
    selectionResources: view.selectionResources,
  };
  return JSON.stringify(payload).replace(/</g, '\\u003c');
}

/**
 * Render the complete inbox document. All dynamic values are escaped; the
 * CSP allows only the nonce'd inline style and script for this render.
 */
export function renderInboxHtml(view: InboxViewState, options: RenderOptions): string {
  const { nonce } = options;
  const scan = view.scan;
  const staleBanner = notice(
    scan.stale ? scan.staleReason : null,
    'il-ib-stale',
    'stale',
  );
  const body =
    view.mode === 'list'
      ? listSectionHtml(view)
      : view.mode === 'review'
        ? reviewSectionHtml(view)
        : resultsSectionHtml(view);
  const summary = view.mode === 'results' ? '' : summaryHtml(view);
  const footer =
    view.mode === 'results'
      ? 'The run above applied the approval shown with it. Every file lists what really ' +
        'happened - a file is only called recovered when the engine restored the captured ' +
        'bytes and the extension re-checked the hash independently.'
      : 'Nothing has been recovered. Recovery requires explicit approval and final safety ' +
        'revalidation.';
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'none'; font-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Interlock Recovery Inbox</title>
<style nonce="${nonce}">
${STYLESHEET}
${INBOX_STYLES}
</style>
</head>
<body>
<div class="il-root il-ib" id="il-inbox">

  ${headerHtml(view)}

  <p class="il-note" role="status" data-live="scanNote">${escapeHtml(scan.statusNote)}</p>
  ${notice(view.notice, 'il-ib-notice', 'notice')}
  ${staleBanner}
  ${summary}
  ${body}

  <div class="il-footer">${escapeHtml(footer)}</div>
</div>
<script type="application/json" id="il-ib-payload">
${payloadJson(view)}
</script>
<script nonce="${nonce}">
${INBOX_SCRIPT}
</script>
</body>
</html>`;
}
