/**
 * Recovery report renderer (pure).
 *
 * Renders a {@link RecoveryReportModel} into the panel's HTML using the exact
 * design system the sidebar uses (`STYLESHEET` from `webviewHtml.ts`: tokens,
 * resets, buttons, pills, collapsibles, tones) so the report reads as the same
 * product. Report-specific layout rules are few, prefixed `.il-r-`.
 *
 * Security model (mirrors the sidebar):
 *   * One per-render CSP nonce covers <style> and <script>; no images, fonts,
 *     remote scripts or remote styles are permitted at all.
 *   * Every dynamic value passes through {@link escapeHtml}.
 *   * The script only posts typed messages back to the extension - it never
 *     writes innerHTML, never evaluates strings and never touches the FS.
 *   * Hashes, sizes and raw engine errors appear ONLY inside collapsed
 *     "Technical details"; the default view carries no contents, no secrets
 *     and no raw payloads.
 */

import {
  RenderOptions,
  STYLESHEET,
  brandShield,
  escapeHtml,
  icon,
} from './webviewHtml';
import {
  CheckResult,
  RecoveryReportModel,
  ReportCounts,
  ReportFileRow,
  SafetyCheck,
} from './recoveryReport';

// ---------------------------------------------------------------- messages

/** Typed messages the report script may send to the extension. */
export interface ReportMessage {
  type: 'ready' | 'refresh' | 'close' | 'preview' | 'previewAll';
  /** Only present for `preview`: a workspace-relative resource. */
  resource?: string;
}

/** Validate a message received from the webview (shape only - the panel
 *  additionally checks the resource against this report's own allow-list). */
export function isReportMessage(value: unknown): value is ReportMessage {
  if (value === null || typeof value !== 'object') {
    return false;
  }
  const record = value as Record<string, unknown>;
  const type = record['type'];
  if (
    type !== 'ready' &&
    type !== 'refresh' &&
    type !== 'close' &&
    type !== 'preview' &&
    type !== 'previewAll'
  ) {
    return false;
  }
  const resource = record['resource'];
  if (resource !== undefined && typeof resource !== 'string') {
    return false;
  }
  return type !== 'preview' || typeof resource === 'string';
}

/** Workspace-relative path sanity check: normalized, no traversal, no
 *  absolute or drive path, no control characters. The panel still requires
 *  the value to be one of this report's own resources. */
export function isSafeResource(value: string): boolean {
  if (value.length === 0 || value.length > 1024) {
    return false;
  }
  if (value.includes('\\') || value.startsWith('/') || /^[a-zA-Z]:/.test(value)) {
    return false;
  }
  if (/[\u0000-\u001f]/.test(value)) {
    return false;
  }
  const parts = value.split('/');
  return parts.every((part) => part.length > 0 && part !== '.' && part !== '..');
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

function formatBytes(value: number | null): string | null {
  return value === null ? null : `${value.toLocaleString('en-US')} bytes`;
}

const UNKNOWN_TITLE =
  'This value could not be derived from the validated evidence, so it is reported as Unknown.';

function valueOrUnknown(value: string | null): string {
  return value === null ? `<span class="il-r-unknown" title="${UNKNOWN_TITLE}">Unknown</span>` : escapeHtml(value);
}

function statusTone(status: RecoveryReportModel['status']): string {
  if (status === 'ready') {
    return 'accent';
  }
  return status === 'review' ? 'warn' : 'bad';
}

function checkTone(result: CheckResult): string {
  return result === 'passed'
    ? 'ok'
    : result === 'failed'
      ? 'bad'
      : result === 'attention'
        ? 'warn'
        : 'idle';
}

/** Default is neutral: color appears only for real warnings, errors, passes. */
function currentChipTone(row: ReportFileRow): string | null {
  if (row.current === 'missing') {
    return 'warn';
  }
  return row.current === 'unknown' ? 'idle' : null;
}

function baselineChipTone(row: ReportFileRow): string | null {
  if (row.baseline === 'invalid') {
    return 'bad';
  }
  return row.baseline === 'unavailable' ? 'idle' : null;
}

function eligibilityChipTone(row: ReportFileRow): string | null {
  return row.eligibility === 'available' ? null : 'warn';
}

function reasonTone(row: ReportFileRow): string | null {
  if (row.eligibility === 'available') {
    return null;
  }
  return row.baseline === 'invalid' ? 'bad' : 'warn';
}

function chip(label: string, tone: string | null, extraClass = ''): string {
  const toneAttr = tone === null ? '' : ` data-tone-value="${tone}"`;
  const cls = extraClass ? `class="il-chip ${extraClass}"` : 'class="il-chip"';
  return `<span ${cls}${toneAttr}><span>${escapeHtml(label)}</span></span>`;
}

// ------------------------------------------------------------------ summary

function countCell(label: string, count: number | null, warnWhenPositive: boolean): string {
  const shown =
    count === null
      ? `<span class="il-r-unknown" title="${UNKNOWN_TITLE}">Unknown</span>`
      : `<span class="il-r-stat-v"${warnWhenPositive && count > 0 ? ' data-tone-value="warn"' : ''}>${count}</span>`;
  return `<div class="il-r-stat"><span class="il-r-stat-l">${escapeHtml(label)}</span>${shown}</div>`;
}

function summaryHtml(counts: ReportCounts): string {
  return `<section class="il-section" aria-label="Summary">
    <h2 class="il-help-h">Summary</h2>
    <div class="il-r-summary">
      ${countCell('Files reviewed', counts.reviewed, false)}
      ${countCell('Baseline evidence available', counts.withBaseline, false)}
      ${countCell('Differ from baseline', counts.differing, false)}
      ${countCell('Recoverable now', counts.recoverable, false)}
      ${countCell('Need attention', counts.attention, true)}
    </div>
  </section>`;
}

// -------------------------------------------------------------------- files

function technicalHtml(row: ReportFileRow, index: number): string {
  const tech = row.technical;
  const kv: Array<[string, string | null]> = [
    ['Baseline SHA-256', tech.baselineHash],
    ['Current SHA-256', tech.currentHash],
    ['Baseline size', formatBytes(tech.baselineSize)],
    ['Baseline captured', formatStamp(tech.capturedAt)],
    ['Evidence observed', formatStamp(tech.observedAt)],
    ['Operation', tech.operation],
    ['Reversibility', tech.reversibility],
    [
      'Matches baseline',
      tech.matchesBaseline === null
        ? null
        : tech.matchesBaseline
          ? 'Yes - no changes to undo'
          : 'No - changes detected',
    ],
    ['File ACL comparison', tech.aclDetail],
    ['Evidence file', tech.evidenceRef],
    ...tech.comparisons.map((item): [string, string] => [item.label, item.detail]),
  ];
  const rows = kv
    .map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${valueOrUnknown(value)}</dd>`)
    .join('');
  const warnings =
    tech.warnings.length === 0
      ? ''
      : `<ul class="il-list">${tech.warnings
          .slice(0, 6)
          .map((warning) => `<li class="il-li-warn">${escapeHtml(warning)}</li>`)
          .join('')}${
          tech.warnings.length > 6
            ? `<li class="il-li-muted">… and ${tech.warnings.length - 6} more warning(s).</li>`
            : ''
        }</ul>`;
  return `<details class="il-collapsible il-r-tech">
      <summary>Technical details</summary>
      <div class="il-r-techtext" id="il-tech-${index}">
        <dl class="il-kv">${rows}</dl>
        ${warnings}
        <div>
          <button type="button" class="il-r-preview" data-action="copy"
            data-copy="il-tech-${index}" title="Copy this file's technical details">
            ${icon('copy', 'il-i-sm')}<span>Copy details</span>
          </button>
        </div>
      </div>
    </details>`;
}

function fileRowHtml(row: ReportFileRow, index: number): string {
  const previewDisabled = row.previewable ? '' : ' disabled';
  const previewTitle = row.previewable
    ? `Open the side-by-side diff for ${row.resource} (read-only)`
    : (row.previewNote ?? 'Preview is not available for this file.');
  const reason =
    row.reason === null
      ? ''
      : `<p class="il-r-reason"${reasonTone(row) === null ? '' : ` data-tone-value="${reasonTone(row)}"`}>${escapeHtml(row.reason)}</p>`;
  const note =
    row.eligibility === 'available' && row.previewNote !== null
      ? `<p class="il-r-note">${escapeHtml(row.previewNote)}</p>`
      : '';
  return `<article class="il-r-file" aria-label="${escapeHtml(row.resource)}">
    <div class="il-r-filehead">
      <div class="il-r-titles">
        <span class="il-r-name">${escapeHtml(row.name)}</span>
        <span class="il-r-path il-mono il-truncate" title="${escapeHtml(row.resource)}">${escapeHtml(row.resource)}</span>
      </div>
      <span class="il-flex"></span>
      ${chip(row.currentLabel, currentChipTone(row))}
      ${chip(`Baseline ${row.baselineLabel}`, baselineChipTone(row))}
      ${chip(row.eligibilityLabel, eligibilityChipTone(row))}
      <button type="button" class="il-r-preview" data-action="preview"
        data-resource="${escapeHtml(row.resource)}"${previewDisabled}
        title="${escapeHtml(previewTitle)}">
        ${icon('diff', 'il-i-sm')}<span>Preview Recovery</span>
      </button>
    </div>
    ${reason}${note}
    ${technicalHtml(row, index)}
  </article>`;
}

function filesSection(model: RecoveryReportModel): string {
  const stamp = formatStamp(model.evidenceAt);
  const observed =
    stamp === null
      ? 'Evidence observation time: Unknown.'
      : `Evidence observed ${escapeHtml(stamp)}.`;
  const body =
    model.files.length === 0
      ? `<p class="il-note">No files were reviewed: no recovery plan could be produced from the current evidence. Nothing can be previewed or recovered from this report.</p>`
      : `<div class="il-r-files">${model.files.map(fileRowHtml).join('\n    ')}</div>`;
  return `<section class="il-section" aria-label="Files">
    <h2 class="il-help-h">Files <span class="il-r-count">${model.files.length}</span></h2>
    <p class="il-hint">${observed}</p>
    ${body}
  </section>`;
}

// ------------------------------------------------------------------- checks

function checkRowHtml(check: SafetyCheck): string {
  return `<div class="il-r-check" data-tone-value="${checkTone(check.result)}">
    <span class="il-r-check-name">${escapeHtml(check.name)}</span>
    <span class="il-pill" data-tone-value="${checkTone(check.result)}">
      <span class="il-dot" aria-hidden="true"></span><span>${escapeHtml(check.resultLabel)}</span>
    </span>
    <span class="il-r-check-detail">${escapeHtml(check.detail)}</span>
  </div>`;
}

function checksSection(model: RecoveryReportModel): string {
  return `<section class="il-section" aria-label="Safety checks">
    <h2 class="il-help-h">Safety checks</h2>
    <p class="il-hint">Only checks the engine actually ran are listed. A check that could not
      run - for example a missing optional dependency - is always shown as
      "Not checked", never as a pass.</p>
    <div class="il-r-checks">
      ${model.checks.map(checkRowHtml).join('\n    ')}
    </div>
  </section>`;
}

// ------------------------------------------------------------------ actions

function previewAllState(model: RecoveryReportModel): { enabled: boolean; desc: string } {
  const previewable = model.files.filter((file) => file.previewable);
  if (previewable.length > 0) {
    return {
      enabled: true,
      desc: `Opens the side-by-side diff for ${previewable.length} eligible file(s). Read-only - nothing is applied.`,
    };
  }
  if (model.files.length === 0) {
    return { enabled: false, desc: 'No file was reviewed, so there is nothing to preview.' };
  }
  const first = model.files[0];
  return {
    enabled: false,
    desc: first?.previewNote ?? 'No file can be previewed right now.',
  };
}

function actionsSection(model: RecoveryReportModel): string {
  const previewAll = previewAllState(model);
  return `<section class="il-section" aria-label="Report actions">
    <div class="il-r-actions">
      <button type="button" class="il-duobtn" data-action="previewAll"
        ${previewAll.enabled ? '' : 'disabled'}
        title="Preview the eligible recovery as a side-by-side diff">
        ${icon('diff', 'il-btn-ico')}
        <span class="il-duotext">
          <span class="il-duolabel">Preview Recovery</span>
          <span class="il-duodesc">${escapeHtml(previewAll.desc)}</span>
        </span>
      </button>
      <button type="button" class="il-duobtn" data-action="refresh"
        title="Recalculate this report from fresh evidence">
        ${icon('refresh', 'il-btn-ico')}
        <span class="il-duotext">
          <span class="il-duolabel">Refresh Report</span>
          <span class="il-duodesc">Re-observe the files and rebuild every count and check.</span>
        </span>
      </button>
      <button type="button" class="il-duobtn" data-action="close"
        title="Close this report">
        ${icon('close', 'il-btn-ico')}
        <span class="il-duotext">
          <span class="il-duolabel">Close</span>
          <span class="il-duodesc">Close the report. Nothing is applied or recovered.</span>
        </span>
      </button>
    </div>
  </section>`;
}

// ------------------------------------------------------------------- script

/** Tiny, typed message bridge: click delegation only. No innerHTML, no eval. */
const REPORT_SCRIPT = `(function () {
  var vscodeApi = typeof acquireVsCodeApi === 'function'
    ? acquireVsCodeApi()
    : { postMessage: function () {} };
  function send(message) { vscodeApi.postMessage(message); }
  document.addEventListener('click', function (event) {
    var target = event.target;
    var el = target && typeof target.closest === 'function'
      ? target.closest('[data-action]')
      : null;
    if (!el || el.disabled) { return; }
    var action = el.getAttribute('data-action');
    if (action === 'refresh') { send({ type: 'refresh' }); return; }
    if (action === 'close') { send({ type: 'close' }); return; }
    if (action === 'previewAll') { send({ type: 'previewAll' }); return; }
    if (action === 'preview') {
      send({ type: 'preview', resource: el.getAttribute('data-resource') || '' });
      return;
    }
    if (action === 'copy') {
      var node = document.getElementById(el.getAttribute('data-copy') || '');
      if (!node) { return; }
      try {
        var area = document.createElement('textarea');
        area.value = node.innerText;
        area.setAttribute('readonly', 'readonly');
        area.style.position = 'fixed';
        area.style.opacity = '0';
        document.body.appendChild(area);
        area.select();
        document.execCommand('copy');
        document.body.removeChild(area);
      } catch (error) { /* copying is best-effort and never blocks review */ }
    }
  });
  send({ type: 'ready' });
})();`;

// ------------------------------------------------------------------- styles

/**
 * Report-specific layout only. Every color, size, radius and font comes from
 * the shared tokens in STYLESHEET - no new palette values are introduced.
 */
const REPORT_STYLES = `
.il-r { max-width: 1080px; margin: 0 auto; width: 100%; }
.il-r-summary {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
  gap: var(--il-s2); min-width: 0;
}
.il-r-stat {
  display: flex; flex-direction: column; gap: var(--il-s1); min-width: 0;
  background: var(--il-surface); border: 1px solid var(--il-border-soft);
  border-radius: var(--il-r-md); padding: var(--il-s3);
}
.il-r-stat-l {
  font-size: var(--il-fs-sm); font-weight: var(--il-fw-bold);
  letter-spacing: var(--il-ls-wide); text-transform: uppercase; color: var(--il-text2);
}
.il-r-stat-v {
  font-family: var(--il-font-display); font-size: var(--il-fs-display);
  font-weight: var(--il-fw-black); font-variant-numeric: tabular-nums;
  line-height: var(--il-lh-tight); overflow-wrap: anywhere;
}
.il-r-unknown { color: var(--il-text2); font-size: var(--il-fs-h2); font-weight: var(--il-fw-semi); }
.il-r-count { color: var(--il-text2); font-weight: var(--il-fw-semi); margin-left: var(--il-s1); }

.il-r-files { display: flex; flex-direction: column; gap: var(--il-s2); min-width: 0; }
.il-r-file {
  display: flex; flex-direction: column; gap: var(--il-s2); min-width: 0;
  background: var(--il-surface); border: 1px solid var(--il-border-soft);
  border-radius: var(--il-r-md); padding: var(--il-s3);
}
.il-r-filehead { display: flex; align-items: center; gap: var(--il-s2); flex-wrap: wrap; min-width: 0; }
.il-r-titles { display: flex; flex-direction: column; gap: 1px; min-width: 0; flex: 1 1 auto; }
.il-r-name { font-size: var(--il-fs-h2); font-weight: var(--il-fw-bold); overflow-wrap: anywhere; }
.il-r-path { font-size: var(--il-fs-sm); color: var(--il-text2); }
.il-r-reason {
  margin: 0; padding-left: 7px; border-left: 2px solid var(--il-border);
  font-size: var(--il-fs-body); line-height: var(--il-lh); color: var(--il-text2);
  overflow-wrap: anywhere;
}
.il-r-reason[data-tone-value="bad"] { border-left-color: var(--il-error); }
.il-r-reason[data-tone-value="warn"] { border-left-color: var(--il-warn); }
.il-r-note { margin: 0; font-size: var(--il-fs-sm); color: var(--il-text2); overflow-wrap: anywhere; }

.il-r-preview {
  display: inline-flex; align-items: center; gap: var(--il-s2); flex: 0 0 auto;
  padding: 3px var(--il-s3); min-height: 26px;
  border: 1px solid var(--il-border); border-radius: var(--il-r-sm);
  background: var(--il-inset); color: var(--il-text);
  font-size: var(--il-fs-meta); font-weight: var(--il-fw-semi); letter-spacing: var(--il-ls);
}
.il-r-preview:hover:not(:disabled) { border-color: var(--il-accent); color: var(--il-accent); }
.il-r-preview:disabled { border-style: dashed; background: transparent; color: var(--il-text2); }
.il-r-preview > .il-i { color: currentColor; }

.il-r-file .il-collapsible { background: transparent; border: none; padding: 0; }
.il-r-techtext {
  background: var(--il-inset); border: 1px solid var(--il-border-soft);
  border-radius: var(--il-r-sm); padding: var(--il-s3); margin-top: var(--il-s2);
  display: flex; flex-direction: column; gap: var(--il-s3); min-width: 0;
}

.il-r-checks { display: flex; flex-direction: column; gap: var(--il-s2); min-width: 0; }
.il-r-check {
  display: flex; align-items: baseline; gap: var(--il-s3); flex-wrap: wrap; min-width: 0;
  padding: var(--il-s2) var(--il-s3); background: var(--il-surface);
  border: 1px solid var(--il-border-soft); border-left-width: 2px;
  border-radius: var(--il-r-md);
}
.il-r-check, .il-r-check[data-tone-value] { color: var(--il-text); }
.il-r-check[data-tone-value="ok"] { border-left-color: var(--il-ok); }
.il-r-check[data-tone-value="bad"] { border-left-color: var(--il-error); }
.il-r-check[data-tone-value="warn"] { border-left-color: var(--il-warn); }
.il-r-check[data-tone-value="idle"] { border-left-color: var(--il-border); }
.il-r-check-name { font-size: var(--il-fs-body); font-weight: var(--il-fw-bold); min-width: 150px; flex: 0 0 auto; }
.il-r-check-detail {
  font-size: var(--il-fs-body); color: var(--il-text2); line-height: var(--il-lh);
  flex: 1 1 240px; min-width: 0; overflow-wrap: anywhere;
}

.il-r-actions { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: var(--il-s2); }
.il-r-actions .il-duobtn:disabled { border-style: dashed; }
.il-r-notice {
  margin: 0; padding: var(--il-s2) var(--il-s3); border: 1px solid #4a3b12;
  background: #15120A; color: var(--il-warn); border-radius: var(--il-r-md);
  font-size: var(--il-fs-body); line-height: var(--il-lh); overflow-wrap: anywhere;
}
@media (max-width: 520px) {
  .il-r-check-name { min-width: 0; }
  .il-r-filehead { align-items: flex-start; }
}
`;

// ------------------------------------------------------------------- render

/**
 * Render the complete report document. All dynamic values are escaped; the
 * CSP allows only the nonce'd inline style and script for this render.
 */
export function renderRecoveryReportHtml(
  model: RecoveryReportModel,
  options: RenderOptions,
): string {
  const { nonce } = options;
  const workspaceLabel = model.workspaceName ?? 'NO WORKSPACE FOLDER';
  const generated = formatStamp(model.generatedAt) ?? 'Unknown';
  const notice =
    model.notice === null
      ? ''
      : `<p class="il-r-notice" role="status">${escapeHtml(model.notice)}</p>`;
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'none'; font-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Interlock Recovery Report</title>
<style nonce="${nonce}">
${STYLESHEET}
${REPORT_STYLES}
</style>
</head>
<body>
<div class="il-root il-r" id="il-report">

  <header class="il-header">
    <div class="il-idline">
      <span class="il-mark" aria-hidden="true">${brandShield()}</span>
      <span class="il-wordmark">Recovery Report</span>
      <span class="il-flex"></span>
      <span class="il-pill" data-tone-value="${statusTone(model.status)}"
        title="${escapeHtml(model.statusNote)}">
        <span class="il-dot" aria-hidden="true"></span>
        <span>${escapeHtml(model.statusLabel)}</span>
      </span>
    </div>
    <div class="il-subline">
      <span class="il-subtitle il-truncate" title="${escapeHtml(workspaceLabel)}">${escapeHtml(workspaceLabel)}</span>
      <span class="il-sep" aria-hidden="true">·</span>
      <span class="il-subtitle il-truncate" title="Report generated at ${escapeHtml(generated)}">GENERATED ${escapeHtml(generated)}</span>
      <span class="il-flex"></span>
    </div>
  </header>

  <p class="il-note" role="status">${escapeHtml(model.statusNote)}</p>
  ${notice}

  ${summaryHtml(model.counts)}
  ${filesSection(model)}
  ${checksSection(model)}
  ${actionsSection(model)}

  <div class="il-footer">Nothing has been recovered. Recovery still requires explicit approval
    and final safety revalidation.</div>
</div>
<script nonce="${nonce}">
${REPORT_SCRIPT}
</script>
</body>
</html>`;
}
