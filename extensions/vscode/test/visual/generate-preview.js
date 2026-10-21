/**
 * Generates a static preview page from the REAL sidebar renderer
 * (out/src/webviewHtml.js), so the visual result can be inspected in a
 * browser without launching VS Code.
 *
 * Usage:  node test/visual/generate-preview.js   -> writes preview.html
 *
 * The scenarios use clearly-labelled sample state (this is a layout preview,
 * not an engine result): production rendering only ever receives real model
 * data from the extension host.
 */

'use strict';

const fs = require('fs');
const path = require('path');

const { renderSidebarHtml } = require('../../out/src/webviewHtml.js');
const { emptyModel } = require('../../out/src/sidebar.js');
const { evaluateProtection } = require('../../out/src/protection.js');

function escapeAttr(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

const now = new Date().toISOString();

const primaryStatus = {
  at: now,
  engineAvailable: true,
  engineVersion: 'source checkout (V6)',
  engineRoot: 'F:\\Desktop_Data_2026\\Desktop\\INTERLOCK V4',
  pythonVersion: '3.11.9',
  platformStatus: 'TESTED - PRIMARY',
  headline: 'Windows x64 + NTFS + Python 3.11.9 is the recorded primary test environment.',
};

const scenarios = [
  {
    id: 'first-run',
    label: 'First run - nothing checked yet (honest empty states, Protect disabled)',
    width: 300,
    model: { ...emptyModel() },
  },
  {
    id: 'needs-protection',
    label: 'Folder open, no evidence - Protect enabled, Recover disabled with the reason',
    width: 300,
    model: {
      ...emptyModel(),
      status: primaryStatus,
      workspacePath: 'F:\\projects\\globex\\checkout-service',
      workspaceAuthorized: true,
      baselineCount: 0,
      gitChangedFiles: ['src/app.ts'],
    },
  },
  {
    id: 'protected',
    label: 'Protected - evidence captured, confinement authorized',
    width: 300,
    model: {
      ...emptyModel(),
      status: primaryStatus,
      workspacePath:
        'F:\\projects\\customers\\globex\\very-deeply-nested-application-workspace',
      workspaceAuthorized: true,
      workspaceSupportStatus: 'TESTED - PRIMARY',
      baselineCount: 4,
      recentBaselines: [
        { workspace: 'w', resource: 'file:config.yaml', file: 'f', hash: 'h', size: 128, capturedAt: now },
        { workspace: 'w', resource: 'file:app/settings.py', file: 'f', hash: 'h', size: 256, capturedAt: now },
      ],
      gitChangedFiles: ['src/a.ts', 'src/b.ts', 'docs/c.md'],
      baselineExclusions: ['docs/generated/**', 'vendor/**'],
      verification: {
        workspace: 'w',
        resource: 'file:config.yaml',
        at: now,
        success: true,
        reason: 'byte-exact match against captured baseline',
        checksPassed: ['hash', 'size', 'seal'],
        checksFailed: [],
      },
      lastAction: 'verify: ok',
    },
  },
  {
    id: 'recovery-ready',
    label: 'Recovery ready - a fresh would-succeed preview is pending (transient)',
    width: 300,
    model: {
      ...emptyModel(),
      status: primaryStatus,
      workspacePath: 'F:\\projects\\globex\\checkout-service',
      workspaceAuthorized: true,
      baselineCount: 4,
      recentBaselines: [
        { workspace: 'w', resource: 'file:src/app.ts', file: 'f', hash: 'h', size: 512, capturedAt: now },
      ],
      pendingPreview: {
        workspace: 'F:\\projects\\globex\\checkout-service',
        resource: 'file:src/app.ts',
        at: now,
        wouldSucceed: true,
      },
    },
  },
  {
    id: 'partial',
    label: 'Partial protection - 2 of 5 files protected, skips disclosed',
    width: 300,
    model: {
      ...emptyModel(),
      status: primaryStatus,
      workspacePath: 'F:\\projects\\acme\\migrations',
      workspaceAuthorized: true,
      baselineCount: 2,
      lastAction: 'protect: partial',
      autoProtectionNote:
        'Automatic protection: captured 2 of 5 · 0 already had evidence (kept) · 3 skipped by policy.',
      protection: evaluateProtection({
        workspacePath: 'F:\\projects\\acme\\migrations',
        workspaceAuthorized: true,
        baselineCount: 2,
        engineStatus: primaryStatus,
        verification: null,
        eligibleFiles: 5,
        skippedFiles: 3,
        checkedAt: now,
      }),
    },
  },
  {
    id: 'analyzing',
    label: 'Analyzing - live run shows progress, never a verdict',
    width: 300,
    model: {
      ...emptyModel(),
      status: primaryStatus,
      workspacePath: 'F:\\projects\\acme\\migrations',
      workspaceAuthorized: true,
      baselineCount: 0,
      lastAction: 'analyze: running',
      protection: evaluateProtection({
        workspacePath: 'F:\\projects\\acme\\migrations',
        workspaceAuthorized: true,
        baselineCount: 0,
        engineStatus: primaryStatus,
        verification: null,
        analyzing: true,
        analyzingDetail: 'Checking this workspace and its recovery evidence…',
      }),
    },
  },
  {
    id: 'action-required',
    label: 'Protection unavailable - refused confinement + failed verification (bad states)',
    width: 300,
    model: {
      ...emptyModel(),
      status: {
        ...primaryStatus,
        platformStatus: 'DECLARED - COMMUNITY REPORTED',
        headline: 'Declared by the community; no recorded engine evidence for this environment.',
      },
      workspacePath: 'F:\\workspace',
      workspaceAuthorized: false,
      baselineCount: 1,
      warnings: ['Workspace is outside the authorized root; recovery is refused.'],
      verification: {
        workspace: 'w',
        resource: 'file:app/main.py',
        at: now,
        success: false,
        reason: 'hash mismatch - file changed after the preview',
        checksPassed: ['size'],
        checksFailed: ['hash'],
      },
      lastError: 'verify: byte-exact mismatch on file:app/main.py',
    },
  },
  {
    id: 'manual-only',
    label: 'Automatic protection off - the card says so, evidence stays manual',
    width: 300,
    model: {
      ...emptyModel(),
      status: primaryStatus,
      workspacePath: 'F:\\projects\\acme\\hand-managed',
      workspaceAuthorized: true,
      baselineCount: 1,
      autoProtectionEnabled: false,
    },
  },
  {
    id: 'narrow',
    label: 'Narrow sidebar (260px) - details stack, no horizontal scroll',
    width: 260,
    model: null, // uses the protected model below
  },
];

const PREVIEW_NONCE = 'preview-nonce';

/**
 * Lets the production updater run outside VS Code.
 *
 * The shipped script is host-driven: it posts `ready` and then receives a
 * `model` message. A browser preview has no host, so this injects a nonce'd
 * bootstrap that (a) stubs the VS Code bridge and (b) replays the scenario
 * model as a `model` message - exactly the message the real view receives.
 * Production code paths are untouched.
 */
function withPreviewHost(html, model) {
  const payload = JSON.stringify(model).replace(/</g, '\\u003c');
  const bootstrap =
    `<script nonce="${PREVIEW_NONCE}">` +
    'window.acquireVsCodeApi=function(){return{postMessage:function(){}};};' +
    "window.addEventListener('load',function(){window.dispatchEvent(new MessageEvent('message'," +
    `{data:{type:'model',model:${payload}}}))});` +
    '</script>';
  return html.replace('<body>', `<body>${bootstrap}`);
}

const healthy = scenarios.find((s) => s.id === 'protected').model;
const frames = scenarios
  .map((scenario) => {
    const model = scenario.model ?? healthy;
    const html = withPreviewHost(
      renderSidebarHtml(model, { nonce: PREVIEW_NONCE }),
      model,
    );
    return `
  <figure class="frame-wrap">
    <figcaption><b>${scenario.id}</b> — ${scenario.label}</figcaption>
    <div class="frame" style="width:${scenario.width}px">
      <iframe title="${escapeAttr(scenario.id)}" srcdoc="${escapeAttr(html)}"></iframe>
    </div>
  </figure>`;
  })
  .join('\n');

const page = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Interlock V6 — sidebar preview</title>
<style>
  :root { color-scheme: dark; }
  body {
    margin: 0; padding: 28px; background: #060707; color: #A0A5A5;
    font-family: system-ui, "Segoe UI", sans-serif;
  }
  h1 { color: #F5F5F5; font-size: 16px; letter-spacing: .14em; text-transform: uppercase; margin: 0 0 4px; }
  h1 span { color: #FFE500; }
  p.hint { margin: 0 0 22px; font-size: 12px; }
  .frames { display: flex; flex-wrap: wrap; gap: 26px; align-items: flex-start; }
  .frame-wrap { margin: 0; }
  .frame-wrap figcaption { font-size: 11.5px; margin-bottom: 8px; max-width: 320px; }
  .frame-wrap figcaption b { color: #FFE500; letter-spacing: .08em; text-transform: uppercase; }
  .frame {
    border: 1px solid #292D2C; border-radius: 8px; overflow: hidden;
    background: #0A0B0B; box-shadow: 0 12px 34px rgba(0,0,0,.55);
  }
  .frame iframe { width: 100%; height: 1180px; border: 0; display: block; background: #0A0B0B; }
</style>
</head>
<body>
<h1>Interlock <span>V6</span> — compact sidebar preview</h1>
<p class="hint">Rendered and live-bound by the production code path
  (<code>renderSidebarHtml</code> + the shipped updater script). Sample state, layout only.</p>
<div class="frames">${frames}
</div>
</body>
</html>
`;

const out = path.join(__dirname, 'preview.html');
fs.writeFileSync(out, page, 'utf8');
console.log(`wrote ${out} (${page.length} bytes, ${scenarios.length} scenarios)`);
