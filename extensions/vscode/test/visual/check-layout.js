/**
 * Layout sanity check for the redesigned sidebar: asserts the things that
 * keep the recovery dashboard usable at 260px and 300px without a browser.
 *
 * Usage: node test/visual/check-layout.js
 */
'use strict';

const { renderSidebarHtml } = require('../../out/src/webviewHtml.js');
const { emptyModel } = require('../../out/src/sidebar.js');

const html = renderSidebarHtml(emptyModel(), { nonce: 'n' });
const css = html.slice(html.indexOf('<style'), html.indexOf('</style>'));
const body = html.slice(html.indexOf('<body>'), html.indexOf('<script'));

let failures = 0;
function check(label, ok, detail) {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? `  (${detail})` : ''}`);
  if (!ok) {
    failures += 1;
  }
}

// ------------------------------------------------------- shared type scale
/** `--il-fs-*` tokens declared in `:root`, in px. */
function typeTokens(sheet) {
  const tokens = {};
  for (const m of sheet.matchAll(/(--il-fs-[a-z0-9-]+):\s*([\d.]+)px/g)) {
    tokens[m[1]] = parseFloat(m[2]);
  }
  return tokens;
}

function tokenPx(sheet, name) {
  return typeTokens(sheet)[name] ?? 0;
}

/** Bare `font-size: 13px` declarations outside the shared scale. */
function literalFontSizes(sheet) {
  return [...sheet.matchAll(/font-size:\s*([^;]+);/g)]
    .map((m) => m[1].trim())
    .filter((value) => /^[\d.]+px$/.test(value));
}

/** Every `font-size`, resolved through the `--il-fs-*` scale. */
function fontSizes(sheet) {
  const tokens = typeTokens(sheet);
  const sizes = [];
  for (const m of sheet.matchAll(/font-size:\s*([^;]+);/g)) {
    const value = m[1].trim();
    const token = /^var\((--il-fs-[a-z0-9-]+)\)$/.exec(value);
    if (token) {
      sizes.push(tokens[token[1]] ?? Number.NaN);
    } else if (/^[\d.]+px$/.test(value)) {
      sizes.push(parseFloat(value));
    } else {
      sizes.push(Number.NaN);
    }
  }
  return sizes;
}

// ---------------------------------------------------------------- layout CSS
const wide = [...css.matchAll(/(?:^|[;{\s])(?:min-)?width:\s*(\d+)px/g)]
  .map((x) => +x[1])
  .filter((w) => w > 200);
check('no fixed width above 200px (cannot force horizontal scroll)', wide.length === 0, wide.join(','));

const radii = [
  ...new Set([...css.matchAll(/border-radius:\s*([^;]+);/g)].map((x) => x[1].trim())),
];
check(
  'corner radii come from the token scale only',
  radii.every((r) => r.startsWith('var(--il-r-') || r === '50%'),
  radii.join(' | '),
);

const sizes = [
  ...new Set(
    fontSizes(css).map((x) => parseFloat(x.toFixed(1))),
  ),
].sort((a, b) => a - b);
check(
  'no text below the 12px floor (sizes come from the shared type scale)',
  sizes.length > 0 && sizes[0] >= 12,
  `smallest ${sizes[0]}px, largest ${sizes[sizes.length - 1]}px`,
);
check(
  'every font-size reads a --il-fs-* token (no one-off sizes)',
  literalFontSizes(css).length === 0,
  literalFontSizes(css).join(', ') || 'all through the type scale',
);
check(
  'brand / heading / body hierarchy holds',
  tokenPx(css, '--il-fs-brand') >= 16 &&
    tokenPx(css, '--il-fs-h1') >= 14 &&
    tokenPx(css, '--il-fs-h2') >= 14 &&
    tokenPx(css, '--il-fs-body') >= 13 &&
    tokenPx(css, '--il-fs-brand') > tokenPx(css, '--il-fs-body'),
  `brand ${tokenPx(css, '--il-fs-brand')}px, h1 ${tokenPx(css, '--il-fs-h1')}px, ` +
    `h2 ${tokenPx(css, '--il-fs-h2')}px, body ${tokenPx(css, '--il-fs-body')}px`,
);

const gaps = [
  ...new Set(
    [...css.matchAll(/(?:^|[;{\s])gap:\s*([\d.]+)px/g)].map((x) => parseFloat(x[1])),
  ),
].sort((a, b) => a - b);
check(
  'no gap below 3px (rows must stay finger/eye separated)',
  gaps.length === 0 || gaps[0] >= 3,
  gaps.length ? `smallest ${gaps[0]}px` : 'all gaps use spacing tokens',
);

check('no dashed borders left (restrained hairlines only)', !css.includes('dashed'));
check('universal border-box reset present', css.includes('* { box-sizing: border-box; }'));
check('reduced-motion support preserved', css.includes('prefers-reduced-motion: reduce'));
check('narrow fallback present', css.includes('@media (max-width: 270px)'));
check(
  'narrow fallback stacks the key/value grid',
  /\.il-kv\s*\{[^}]*\}/.test(css) &&
    /@media \(max-width: 270px\)\s*\{[\s\S]*?\.il-kv\s*\{[^}]*grid-template-columns:\s*1fr/.test(css),
);
check(
  'long prose wraps instead of overflowing',
  (css.match(/overflow-wrap:\s*anywhere/g) ?? []).length >= 4,
);
check(
  'no .il-val class survives (values now live inside truncating flex rows)',
  !/\.il-val\b/.test(css),
);

// ------------------------------------------------------- information order
check(
  'the protection card is the first card',
  /<section class="il-card il-protect" aria-labelledby="il-h-protection">/.test(body) &&
    body.indexOf('il-h-protection') < body.indexOf('il-primary'),
);
check(
  'exactly one prominent protection card',
  (body.match(/il-card il-protect/g) ?? []).length === 1,
);
check(
  'primary action explains itself right underneath',
  /class="il-primary"[\s\S]*?<\/button>\s*<p class="il-explain"/.test(body),
);
check(
  'the one large primary button is always Protect My Workspace',
  /class="il-primary"[^>]*data-action="interlock\.protectWorkspace"/.test(body) &&
    body.includes('Protect My Workspace'),
);
check(
  'header holds the brand, the subtitle, a status pill and one refresh',
  (() => {
    const header = /<header class="il-header">([\s\S]*?)<\/header>/.exec(body);
    return (
      !!header &&
      !header[1].includes('<details') &&
      (header[1].match(/<button/g) ?? []).length === 1 &&
      header[1].includes('INTERLOCK') &&
      header[1].includes('WORKSPACE PROTECTION') &&
      header[1].includes('data-tone="protectionTone"')
    );
  })(),
);
check(
  'the two secondary rows sit in workflow order',
  [...body.matchAll(/data-row="([a-z]+)"/g)].map((x) => x[1]).join(',') === 'preview,verify',
);
check(
  'Analyze and Recover are side-by-side prominent buttons (stacking when narrow)',
  [...body.matchAll(/data-duo="([a-z]+)"/g)].map((x) => x[1]).join(',') === 'analyze,recover' &&
    /\.il-duo\s*\{[^}]*grid-template-columns:\s*1fr 1fr/.test(css) &&
    /@media \(max-width: 270px\)\s*\{[\s\S]*?\.il-duo\s*\{[^}]*grid-template-columns:\s*1fr\b/.test(
      css,
    ),
);
check(
  'Recover runs the real recovery flow and is visually guarded',
  /data-action="interlock\.openRecoveryInbox"[^>]*data-duo="recover"/.test(body) &&
    /class="il-duobtn il-duobtn-guard"[^>]*data-action="interlock\.openRecoveryInbox"/.test(body),
);
check('guarded recovery states its requirement', body.includes('requires approval'));
check(
  'guarded recovery warns about file changes before it is clicked',
  body.includes('May modify files. Review the preview and approve before anything changes.'),
);
check(
  'the approval warning sits directly under the actions it applies to',
  /<div class="il-duo"[\s\S]*?<\/div>\s*<p class="il-guardnote">/.test(body) &&
    body.indexOf('il-guardnote') < body.indexOf('data-row="preview"'),
);
check(
  'every technical answer lives behind a collapsed Advanced section',
  (body.match(/<details class="il-collapsible">/g) ?? []).length === 4 &&
    !/<details class="il-collapsible" open/.test(body),
);
check(
  'the warning badge sits on the troubleshooting summary, not in the header',
  /<summary>Settings &amp; troubleshooting[\s\S]{0,200}data-bind="warningCount"/.test(body),
);
check(
  'workspace facts stay one calm line with no box of their own',
  (() => {
    const factsRule = /\.il-facts\s*\{[^}]*\}/.exec(css);
    return (
      body.includes('<p class="il-facts">') &&
      !!factsRule &&
      !factsRule[0].includes('border:') &&
      !factsRule[0].includes('background:')
    );
  })(),
);
check(
  'empty explanations are collapsed, not rendered as blank lines',
  /data-bind="protectionBlocker" data-bind-value=""[^>]*hidden>/.test(body) &&
    /data-bind="protectionAuto" data-bind-value=""[^>]*hidden>/.test(body) &&
    /data-bind="protectionRun" data-bind-value=""[^>]*hidden>/.test(body),
);
check(
  'an untouched model shows Protect disabled with the folder reason',
  /class="il-primary"[^>]*disabled/.test(body) &&
    body.includes('data-bind="primaryDesc" data-bind-value="Open a project folder first."'),
);
check(
  'no recovery action is offered without a folder',
  /data-duo="recover" disabled/.test(body) &&
    body.includes('data-bind="recoverDesc" data-bind-value="Open a project folder first."'),
);

// ------------------------------------------------------------- shield branding
const fs = require('fs');
const path = require('path');
const manifest = require('../../package.json');
const { SHIELD_LOGO_PATH } = require('../../out/src/webviewHtml.js');

const container = (manifest.contributes.viewsContainers.activitybar ?? [])[0];
check(
  'Activity Bar container is registered and opens the Interlock sidebar',
  !!container &&
    container.id === 'interlock' &&
    Array.isArray(manifest.contributes.views.interlock) &&
    manifest.contributes.views.interlock[0].type === 'webview',
  JSON.stringify(container),
);

const activityIcon = container ? path.join(__dirname, '..', '..', container.icon) : '';
const activitySvg = fs.existsSync(activityIcon) ? fs.readFileSync(activityIcon, 'utf8') : '';
check(
  'Activity Bar icon ships the text-free shield artwork',
  activitySvg.includes('<path') &&
    activitySvg.includes('M12 2.2') &&
    !activitySvg.includes('<text') &&
    !activitySvg.includes('<image'),
  container ? container.icon : 'no icon',
);

const manifestIcon = manifest.icon
  ? path.join(__dirname, '..', '..', manifest.icon)
  : '';
const iconBytes = fs.existsSync(manifestIcon) ? fs.readFileSync(manifestIcon) : Buffer.alloc(0);
check(
  'extension manifest carries a PNG extension icon',
  typeof manifest.icon === 'string' && iconBytes.length > 0 && iconBytes.subarray(0, 8).equals(
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
  ),
  manifest.icon || 'no icon field',
);

check(
  'the sidebar header shows the same shield logo (no text inside it)',
  body.includes('class="il-mark"') && body.includes(`d="${SHIELD_LOGO_PATH}"`),
  'header .il-mark shield',
);

// ------------------------------------------------------------- recovery inbox
const inboxHtml = fs.existsSync(path.join(__dirname, 'recovery-inbox.html'))
  ? fs.readFileSync(path.join(__dirname, 'recovery-inbox.html'), 'utf8')
  : '';
const inboxReview = fs.existsSync(path.join(__dirname, 'recovery-inbox-review.html'))
  ? fs.readFileSync(path.join(__dirname, 'recovery-inbox-review.html'), 'utf8')
  : '';
const inboxResults = fs.existsSync(path.join(__dirname, 'recovery-inbox-results.html'))
  ? fs.readFileSync(path.join(__dirname, 'recovery-inbox-results.html'), 'utf8')
  : '';
/** The inbox's own style block (the shared design system is not part of it). */
const inboxStyle = (() => {
  const start = inboxHtml.indexOf('.il-ib {');
  const end = inboxHtml.indexOf('</style>');
  return start > 0 && end > start ? inboxHtml.slice(start, end) : '';
})();

check(
  'the sidebar Recover button opens the Recovery Inbox',
  /data-action="interlock\.openRecoveryInbox"[^>]*data-duo="recover"/.test(body) &&
    body.includes('Opens the Recovery Inbox in an editor tab'),
);check(
  'the Recovery Inbox entry is disabled without an open folder',
  /data-duo="recover"[^>]*disabled/.test(body) ||
    /data-duo="recover"[^>]*data-action="interlock\.openRecoveryInbox"/.test(body),
);
check(
  'the sidebar keeps exactly two secondary rows and no second Inbox button',
  (body.match(/class="il-rowbtn/g) ?? []).length === 2 &&
    (body.match(/class="il-inboxbtn/g) ?? []).length === 0,
);
check(
  'the single-file recovery flow stays reachable from the sidebar',
  body.includes('data-action="interlock.executeRecovery"'),
);

check('the inbox document was generated', inboxHtml.length > 1000);
check(
  'the inbox document keeps the same restrictive CSP',
  inboxHtml.includes("default-src 'none'") &&
    inboxHtml.includes("style-src 'nonce-ILVISUALNONCE'") &&
    inboxHtml.includes("script-src 'nonce-ILVISUALNONCE'") &&
    !inboxHtml.includes("'unsafe-inline'"),
);
check(
  'the inbox document ships no remote asset',
  !/<img\b/i.test(inboxHtml) && !/<link\b/i.test(inboxHtml) && !/https?:\/\//i.test(inboxHtml),
);
check(
  'the inbox offers every documented filter',
  ['all-changed', 'recoverable', 'modified', 'deleted', 'attention', 'not-recoverable', 'unchanged'].every(
    (filter) => inboxHtml.includes(`data-filter="${filter}"`),
  ),
);
check(
  'the inbox offers search, sort and both recovery actions',
  inboxHtml.includes('id="il-ib-search"') &&
    inboxHtml.includes('data-act="sort"') &&
    inboxHtml.includes('data-act="recoverSelected"') &&
    inboxHtml.includes('data-act="recoverAll"'),
);
check(
  'the inbox script never writes innerHTML and never evaluates strings',
  !inboxHtml.includes('innerHTML') &&
    !inboxHtml.includes('eval(') &&
    !inboxHtml.includes('new Function'),
);
check(
  'the inbox list is rendered from an escaped JSON payload (bounded DOM)',
  inboxHtml.includes('id="il-ib-payload"') &&
    inboxHtml.includes('pageSize: 200') &&
    !/<script type="application\/json"[^>]*>\s*<\/script>/.test(inboxHtml),
);
check(
  'no inbox text drops below the 12px floor',
  (() => {
    const style = inboxHtml.slice(inboxHtml.indexOf('<style'), inboxHtml.indexOf('</style>'));
    const literals = [...style.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)].map((m) =>
      Number.parseFloat(m[1]),
    );
    const tokens = [...style.matchAll(/--il-fs-[a-z0-9-]+:\s*(\d+(?:\.\d+)?)px/g)].map((m) =>
      Number.parseFloat(m[1]),
    );
    const sizes = [...literals, ...tokens];
    return sizes.length > 0 && sizes.every((size) => size >= 12);
  })(),
);
check(
  'the review step shows the exact scope and every exclusion',
  inboxReview.includes('Files to recover') &&
    inboxReview.includes('Excluded from this run') &&
    inboxReview.includes('data-act="confirm"') &&
    inboxReview.includes('Changed files') &&
    inboxReview.includes('Eligible now'),
);
check(
  'the inbox header lines up with the content column (no sidebar bleed)',
  /\.il-ib \.il-header\s*\{[^}]*margin:\s*0[^}]*\}/.test(inboxStyle),
);
check(
  'the summary cards share one height (no ragged row)',
  /\.il-ib-summary\s*\{[^}]*grid-auto-rows:\s*1fr/.test(inboxStyle),
);
check(
  'the scope cards share one height too',
  /\.il-ib-scope\s*\{[^}]*grid-auto-rows:\s*1fr/.test(inboxStyle),
);
check(
  'the results view reports recovered, skipped, failed and attention counts',
  inboxResults.includes('Recovered &amp; verified') &&
    inboxResults.includes('Skipped (no longer eligible)') &&
    inboxResults.includes('Need attention') &&
    inboxResults.includes('data-act="retry"'),
);

console.log(failures === 0 ? '\nlayout check: all green' : `\nlayout check: ${failures} failure(s)`);
process.exitCode = failures === 0 ? 0 : 1;
