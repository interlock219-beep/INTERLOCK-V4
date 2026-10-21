import * as assert from 'assert';

import { emptyModel, SidebarModel } from '../../src/sidebar';
import { evaluateProtection, PRIMARY_COPY, ROW_COPY, SENSITIVE_POLICY_NOTE } from '../../src/protection';
import { StoredStatus, StoredVerification } from '../../src/state';
import {
  ACTIONS,
  ADVANCED_LINKS,
  BIND_KEYS,
  DUO_KEYS,
  escapeHtml,
  isWebviewMessage,
  renderSidebarHtml,
  ROW_KEYS,
  TITLE_BIND_KEYS,
  TONE_KEYS,
  WEBVIEW_COMMANDS,
} from '../../src/webviewHtml';

const NONCE = 'test-nonce-abc123';

function render(model: SidebarModel): string {
  return renderSidebarHtml(model, { nonce: NONCE });
}

/** Markup only - excludes the <style>/<script> source, which holds literals. */
function body(model: SidebarModel): string {
  const html = render(model);
  return html.slice(html.indexOf('<body>'), html.indexOf('<script'));
}

function richModel(): SidebarModel {
  const status: StoredStatus = {
    at: '2026-10-19T10:00:00.000Z',
    engineAvailable: true,
    engineVersion: 'source checkout',
    engineRoot: 'F:\\repo',
    pythonVersion: '3.11.9',
    platformStatus: 'TESTED - PRIMARY',
    headline: 'Windows x64 + NTFS + Python 3.11.9 is the recorded primary test environment.',
  };
  const verification: StoredVerification = {
    workspace: 'F:\\ws',
    resource: 'file:config.yaml',
    at: '2026-10-19T10:05:00.000Z',
    success: true,
    reason: 'byte-exact match against baseline',
    checksPassed: ['hash', 'size'],
    checksFailed: [],
  };
  return {
    ...emptyModel(),
    status,
    workspacePath: 'F:\\projects\\my-deeply-nested-project',
    workspaceAuthorized: true,
    workspaceSupportStatus: 'TESTED - PRIMARY',
    baselineCount: 2,
    recentBaselines: [
      { workspace: 'F:\\ws', resource: 'file:config.yaml', file: 'x', hash: 'h', size: 10, capturedAt: null },
    ],
    gitChangedFiles: ['a.ts', 'b.ts'],
    verification,
    warnings: ['long path warning'],
    lastAction: 'analyze: ok',
    baselineExclusions: ['docs/generated/**', 'vendor/**'],
  };
}

describe('sidebar webview renderer - security policy', () => {
  const html = render(emptyModel());

  it('ships a restrictive CSP with a nonce and no unsafe directives', () => {
    const csp = /<meta http-equiv="Content-Security-Policy" content="([^"]+)"/.exec(html);
    assert.ok(csp, 'CSP meta tag missing');
    const policy = csp[1];
    assert.ok(policy.includes("default-src 'none'"));
    assert.ok(policy.includes(`style-src 'nonce-${NONCE}'`));
    assert.ok(policy.includes(`script-src 'nonce-${NONCE}'`));
    assert.ok(!policy.includes('unsafe-inline'), 'unsafe-inline must never appear');
    assert.ok(!policy.includes('unsafe-eval'), 'unsafe-eval must never appear');
    assert.ok(!/https?:\/\//.test(policy), 'no remote origins allowed');
  });

  it('uses the same nonce on <style> and <script>', () => {
    assert.ok(html.includes(`<style nonce="${NONCE}">`));
    assert.ok(html.includes(`<script nonce="${NONCE}">`));
    assert.ok(!/<style(?! nonce)/.test(html));
    assert.ok(!/<script(?! nonce)/.test(html));
  });

  it('loads no external images, fonts or stylesheets', () => {
    assert.ok(!/<link\b/.test(html));
    assert.ok(!/<img\b/.test(html));
    assert.ok(!/@import/.test(html));
    assert.ok(!/url\(/.test(html));
    assert.ok(!/src="https?:/.test(html));
  });

  it('escapes hostile model content (attribute + markup injection)', () => {
    const evil: SidebarModel = {
      ...emptyModel(),
      workspacePath: 'F:\\ws\\</script><script>alert(1)</script>',
      lastError: '"><img src=x onerror=alert(2)>',
      warnings: ["' onmouseover='alert(3)"],
      incidentNote: 'inc & "idents" <b>bold</b>',
      protection: {
        status: 'action-required',
        headline: '"><svg onload=alert(4)>',
        detail: '<style>@import "x"</style>',
        countsText: '2 of 3 files protected',
        blocker: '<img src=x onerror=alert(5)>',
        coveredFiles: 2,
        eligibleFiles: 3,
        skippedFiles: 0,
        checkedAt: null,
      },
      status: {
        ...({
          at: new Date().toISOString(),
          engineAvailable: false,
          engineVersion: 'v</dd>',
          engineRoot: null,
          pythonVersion: null,
          platformStatus: 'UNTESTED',
          headline: 'A & B <C>',
        } as StoredStatus),
      },
    };
    const out = render(evil);
    assert.ok(!out.includes('<script>alert'), 'raw injected script tag leaked');
    assert.ok(!out.includes('<img src=x'), 'raw injected img tag leaked');
    assert.ok(!out.includes("onmouseover='alert"), 'raw handler attribute leaked');
    assert.ok(!out.includes('<svg onload'), 'raw injected svg leaked');
    assert.ok(!/<style>(?!<style nonce)/.test(out.replace('<style nonce', '<style nonce')), 'injected style tag leaked');
    assert.ok(out.includes('&lt;/script&gt;'));
    assert.ok(out.includes('&quot;&gt;&lt;img'));
    assert.ok(out.includes('&#39; onmouseover'));
    assert.ok(out.includes('A &amp; B &lt;C&gt;'));
    // The only <script> element is the nonce'd one.
    assert.strictEqual((out.match(/<script/g) ?? []).length, 1);
    assert.strictEqual((out.match(/<\/script>/g) ?? []).length, 1);
  });

  it('escapeHtml covers every dangerous character', () => {
    assert.strictEqual(escapeHtml(`<>&"'`), '&lt;&gt;&amp;&quot;&#39;');
  });
});

describe('sidebar webview renderer - bindings stay in sync', () => {
  const html = render(richModel());

  it('renders every documented data-bind key and no unexpected ones', () => {
    const found = [...html.matchAll(/data-bind="([A-Za-z]+)"/g)].map((m) => m[1]);
    assert.deepStrictEqual([...new Set(found)].sort(), [...BIND_KEYS].sort());
  });

  it('renders every documented title-bind key (tooltips, not visible text)', () => {
    const found = [...html.matchAll(/data-title-bind="([A-Za-z]+)"/g)].map((m) => m[1]);
    assert.deepStrictEqual([...new Set(found)].sort(), [...TITLE_BIND_KEYS].sort());
  });

  it('renders every documented tone key', () => {
    const found = new Set([...html.matchAll(/data-tone="([A-Za-z]+)"/g)].map((m) => m[1]));
    for (const key of TONE_KEYS) {
      assert.ok(found.has(key), `missing tone binding: ${key}`);
    }
  });

  it('every data-action is on the host allow-list', () => {
    const allowed = new Set([...WEBVIEW_COMMANDS, 'interlock.settings']);
    const found = [...html.matchAll(/data-action="([^"]+)"/g)].map((m) => m[1]);
    assert.ok(found.length >= WEBVIEW_COMMANDS.length);
    for (const action of found) {
      assert.ok(allowed.has(action), `unexpected action: ${action}`);
    }
  });

  it('declares an initial value for every binding', () => {
    for (const key of BIND_KEYS) {
      assert.ok(html.includes(`data-bind="${key}" data-bind-value="`), `no initial value: ${key}`);
    }
    for (const key of TITLE_BIND_KEYS) {
      assert.ok(
        html.includes(`data-title-bind="${key}" data-title-value="`),
        `no initial title: ${key}`,
      );
    }
  });
});

describe('sidebar protection card - honest, evidence-based states', () => {
  it('an untouched model never claims health or protection', () => {
    const out = body(emptyModel());
    assert.ok(out.includes('data-bind="engineText" data-bind-value="Not checked"'));
    assert.ok(out.includes('data-bind="verifyText" data-bind-value="Not run"'));
    assert.ok(out.includes('data-bind="protectionHeadline" data-bind-value="No folder open"'));
    assert.ok(!out.includes('data-bind-value="Protected"'), 'no protection claim');
    assert.ok(!out.includes('data-bind-value="Available"'), 'no availability claim');
    assert.ok(!out.includes('data-bind-value="Passed"'), 'no verification claim');
    assert.ok(out.includes('data-tone="engineTone" data-tone-value="idle"'));
    assert.ok(out.includes('data-tone="protectionTone" data-tone-value="idle"'));
    // The status strip only appears when there is something to say.
    assert.ok(/<div class="il-strip" id="il-strip" hidden/.test(out));
  });

  it('shows Protected only with real evidence and authorization', () => {
    const out = body(richModel());
    assert.ok(out.includes('data-bind="protectionHeadline" data-bind-value="Protected"'));
    assert.ok(out.includes('Valid recovery evidence is available'));
    assert.ok(out.includes('2 files protected'));
    assert.ok(out.includes('data-tone="protectionTone" data-tone-value="ok"'));
    // the shield-check icon is the visible one
    assert.ok(/data-prot-icon="shieldCheck"(?![^>]*hidden)/.test(out));
  });

  it('an available engine with no evidence says Needs protection, with the next step', () => {
    const model: SidebarModel = {
      ...emptyModel(),
      status: richModel().status,
      workspacePath: 'F:\\projects\\demo',
    };
    const out = body(model);
    assert.ok(out.includes('data-bind="engineText" data-bind-value="Available"'));
    assert.ok(out.includes('data-bind="protectionHeadline" data-bind-value="Needs protection"'));
    assert.ok(out.includes("This workspace isn&#39;t protected yet"));
    assert.ok(out.includes('data-tone="protectionTone" data-tone-value="warn"'));
    assert.ok(!out.includes('data-bind-value="Protected"'));
  });

  it('an in-flight analysis renders the Analyzing state, never a verdict', () => {
    const model: SidebarModel = {
      ...richModel(),
      protection: evaluateProtection({
        workspacePath: 'F:\\ws',
        workspaceAuthorized: true,
        baselineCount: 5,
        engineStatus: richModel().status,
        verification: null,
        analyzing: true,
        analyzingDetail: 'Capturing recovery evidence for eligible files…',
      }),
    };
    const out = body(model);
    assert.ok(out.includes('data-bind="protectionHeadline" data-bind-value="Analyzing"'));
    assert.ok(out.includes('Capturing recovery evidence for eligible files'));
    assert.ok(out.includes('data-tone="protectionTone" data-tone-value="idle"'));
  });

  it('a confinement refusal is Protection unavailable, visible, with a blocker', () => {
    const model: SidebarModel = {
      ...richModel(),
      workspaceAuthorized: false,
      lastError: 'Engine confinement probes FAILED - do not run recovery here.',
    };
    const out = body(model);
    assert.ok(
      out.includes('data-bind="protectionHeadline" data-bind-value="Protection unavailable"'),
    );
    assert.ok(out.includes('not authorized for recovery'));
    assert.ok(out.includes('confinement'));
    assert.ok(out.includes('data-tone="protectionTone" data-tone-value="bad"'));
    // The blocker line is visible, never collapsed.
    const blocker = /data-bind="protectionBlocker"[^>]*hidden/.exec(out);
    assert.ok(!blocker, 'a real blocker must not be collapsed');
    // ...and the last error is surfaced in the warnings list, not hidden.
    assert.ok(out.includes('Engine confinement probes FAILED'));
  });

  it('states when automatic protection has been switched off', () => {
    const out = body({ ...richModel(), autoProtectionEnabled: false });
    assert.ok(out.includes('Automatic baseline protection is off'));
    assert.ok(out.includes('data-bind="autoProtectionText" data-bind-value="Automatic protection: off'));
  });

  it('reports the last protection run when one happened', () => {
    const out = body({
      ...richModel(),
      autoProtectionNote: 'Automatic protection: captured 3 of 3 · 1 already had evidence (kept) · 2 skipped by policy.',
    });
    assert.ok(out.includes('captured 3 of 3'));
    assert.ok(out.includes('2 skipped by policy'));
  });

  it('never calls the workspace protected just because the engine is available', () => {
    const model: SidebarModel = {
      ...emptyModel(),
      status: richModel().status,
      workspacePath: 'F:\\projects\\my-project',
    };
    const out = body(model);
    assert.ok(out.includes('data-bind="protectionHeadline" data-bind-value="Needs protection"'));
    assert.ok(!out.includes('data-bind-value="Protected"'), 'no protection claim without evidence');
  });

  it('shows a workspace by folder name with the full path only in a tooltip', () => {
    const out = body(richModel());
    assert.ok(out.includes('my-deeply-nested-project'));
    assert.ok(out.includes('title="F:\\projects\\my-deeply-nested-project"'));
    const withoutTooltips = out.replace(/(data-title-value|title)="[^"]*"/g, '');
    assert.ok(
      !withoutTooltips.includes('F:\\projects\\my-deeply-nested-project'),
      'full path must never be visible text',
    );
  });
});

describe('sidebar primary button - always Protect My Workspace', () => {
  it('renders exactly one large primary button wired to protectWorkspace', () => {
    const html = render(emptyModel());
    const primary = /class="il-primary"[^>]*data-action="([^"]+)"/.exec(html);
    assert.ok(primary, 'primary button missing');
    assert.strictEqual(primary[1], 'interlock.protectWorkspace');
    assert.strictEqual(html.match(/class="il-primary"/g)?.length, 1);
    // The label is static markup - it appears exactly once in the visible body.
    const markup = body(emptyModel());
    assert.ok(markup.includes(PRIMARY_COPY.label), 'static Protect My Workspace label');
    assert.strictEqual(
      (markup.match(new RegExp(PRIMARY_COPY.label, 'g')) ?? []).length,
      1,
      'the label is not duplicated per state anywhere in the markup',
    );
  });

  it('with no folder the primary is disabled and says why beneath it', () => {
    const html = render(emptyModel());
    assert.ok(/class="il-primary"[^>]*disabled/.test(html));
    assert.ok(html.includes('data-bind="primaryDesc" data-bind-value="Open a project folder first."'));
    // The explanation sits directly beneath the button.
    assert.ok(/class="il-primary"[\s\S]*?<\/button>\s*<p class="il-explain"/.test(html));
  });

  it('with a folder it is enabled and states the baseline step', () => {
    const html = render({
      ...emptyModel(),
      status: richModel().status,
      workspacePath: 'F:\\ws',
    });
    assert.ok(/class="il-primary"(?![^>]*disabled)/.test(html));
    assert.ok(html.includes(`data-bind="primaryDesc" data-bind-value="${PRIMARY_COPY.explain}"`));
  });

  it('the header carries the brand, the subtitle and a live status pill', () => {
    const header = /<header class="il-header">([\s\S]*?)<\/header>/.exec(body(richModel()));
    assert.ok(header);
    assert.ok(header[1].includes('INTERLOCK'));
    assert.ok(header[1].includes('>V6<'));
    assert.ok(header[1].includes('WORKSPACE PROTECTION'));
    assert.ok(header[1].includes('data-tone="protectionTone"'), 'status pill shares the card tone');
    assert.ok(/data-bind="protectionHeadline"/.test(header[1]), 'pill shows the live headline');
    assert.ok(header[1].includes('aria-label="Refresh sidebar"'));
    assert.strictEqual((header[1].match(/<button/g) ?? []).length, 1);
  });
});

describe('sidebar action area - prominent duo, guarded recover, secondary rows', () => {
  const view = body(richModel());

  it('renders the two secondary rows in workflow order', () => {
    assert.deepStrictEqual(
      [...view.matchAll(/data-row="([a-z]+)"/g)].map((m) => m[1]),
      ['preview', 'verify'],
    );
    assert.strictEqual((view.match(/class="il-rowbtn/g) ?? []).length, 2);
  });

  it('renders the prominent duo side by side (Analyze | Recover)', () => {
    const duo = /<div class="il-duo"[^>]*>([\s\S]*?)\n {2}<\/div>/.exec(view);
    assert.ok(duo, 'duo container missing');
    assert.deepStrictEqual(
      [...duo[1].matchAll(/data-duo="([a-z]+)"/g)].map((m) => m[1]),
      [...DUO_KEYS],
    );
    assert.ok(/data-action="interlock\.analyzeWorkspace"[^>]*data-duo="analyze"/.test(view));
    // Recover is a genuinely separate action: it opens the Recovery Inbox.
    assert.ok(/data-action="interlock\.openRecoveryInbox"[^>]*data-duo="recover"/.test(view));
  });

  it('every action spec is rendered with its label, icon and tooltip', () => {
    for (const action of ACTIONS) {
      assert.ok(view.includes(`data-action="${action.id}"`), `missing ${action.id}`);
      assert.ok(view.includes(`title="${action.tooltip.replace(/"/g, '&quot;')}"`));
      assert.ok(view.includes(action.label));
    }
  });

  it('Recover is visually guarded and the approval requirement is stated', () => {
    assert.ok(
      /class="il-duobtn il-duobtn-guard"[^>]*data-action="interlock\.openRecoveryInbox"/.test(view),
    );
    assert.strictEqual(view.match(/class="il-duobtn il-duobtn-guard"/g)?.length, 1);
    assert.ok(view.includes('requires approval'));
    assert.ok(view.includes('il-chip-guard'));
  });

  it('says in plain words that recovery may modify files', () => {
    assert.ok(
      view.includes('May modify files. Review the preview and approve before anything changes.'),
    );
    const note = /<p class="il-guardnote">([\s\S]*?)<\/p>/.exec(view);
    assert.ok(note && note[1].includes('approve'));
    // The warning sits directly under the duo that contains Recover.
    assert.ok(/<div class="il-duo"[\s\S]*?<\/div>\s*<p class="il-guardnote">/.test(view));
  });

  it('the dedicated Recover button invokes a real, allow-listed recovery command', () => {
    assert.ok(WEBVIEW_COMMANDS.includes('interlock.openRecoveryInbox'));
    assert.strictEqual(
      [...view.matchAll(/data-action="([^"]+)"[^>]*data-duo="recover"/g)].length,
      1,
    );
    // ...and it is not a relabel of Analyze / Preview / Verify.
    const ids = new Set(ACTIONS.map((a) => a.id));
    assert.ok(ids.has('interlock.analyzeWorkspace'));
    assert.ok(ids.has('interlock.previewRecoveryPlan'));
    assert.ok(ids.has('interlock.verifyRecovery'));
    const recoverSpec = ACTIONS.find((a) => a.id === 'interlock.openRecoveryInbox');
    assert.ok(recoverSpec && recoverSpec.label === 'Recover');
    // The single-file flow stays reachable (it is not dead code).
    assert.ok(
      WEBVIEW_COMMANDS.includes('interlock.executeRecovery'),
      'the single-file recovery command must stay available',
    );
    assert.ok(
      ADVANCED_LINKS.some((link) => link.id === 'interlock.executeRecovery'),
      'the single-file recovery command must stay reachable from the sidebar',
    );
  });

  it('the Recover button opens the Inbox instead of writing anything itself', () => {
    const spec = ACTIONS.find((a) => a.id === 'interlock.openRecoveryInbox');
    assert.ok(spec && spec.tooltip.includes('Recovery Inbox'));
    assert.ok(spec && spec.guarded === true, 'the Inbox can modify files, so it stays guarded');
    // The click path is data-action -> allow-listed command -> host.
    assert.ok(
      /data-action="interlock\.openRecoveryInbox"/.test(view),
      'the button must carry the Inbox command id',
    );
  });

  it('keeps Recover available with a folder (the Inbox reports what it finds)', () => {
    const noEvidence = body({ ...richModel(), baselineCount: 0, protection: null });
    assert.ok(
      !/data-duo="recover"[^>]*disabled/.test(noEvidence),
      'the Inbox may be opened without evidence - it then says so honestly',
    );
    assert.ok(/data-row="preview"[^>]*disabled/.test(noEvidence), 'preview needs evidence');
    assert.ok(/data-row="verify"[^>]*disabled/.test(noEvidence), 'verify needs evidence');
  });

  it('disables everything without a folder, each explaining why', () => {
    const out = body(emptyModel());
    for (const key of ['analyze', 'recover']) {
      assert.ok(out.includes(`data-duo="${key}" disabled`), `${key} must be disabled`);
    }
    assert.ok(out.includes('data-row="preview" disabled'));
    assert.ok(out.includes('data-row="verify" disabled'));
    assert.ok(out.includes('data-bind="recoverDesc" data-bind-value="Open a project folder first."'));
    assert.ok(out.includes('data-bind="primaryDesc" data-bind-value="Open a project folder first."'));
  });

  it('the recovery caution is amber, never a success colour', () => {
    const css = stylesheet(richModel());
    const guardedRule = /\.il-duobtn-guard\s*\{[^}]*\}/.exec(css);
    assert.ok(guardedRule);
    assert.ok(
      !guardedRule[0].includes('--il-ok') && !guardedRule[0].includes('53D769'),
      'guarded styling must never use the success colour',
    );
    const guardNote = /\.il-guardnote\s*\{[^}]*\}/.exec(css);
    assert.ok(guardNote && guardNote[0].includes('--il-warn'));
  });
});

describe('sidebar advanced sections - technical answers, collapsed', () => {
  const view = body(richModel());

  it('ships exactly four collapsed sections with the expected titles', () => {
    const summaries = [...view.matchAll(/<summary>([^<]+?)(?:\s*<span[\s\S]*?)?<\/summary>/g)].map(
      (m) => m[1].trim(),
    );
    assert.deepStrictEqual(summaries, [
      'Baselines &amp; capture',
      'Exclusions &amp; sensitive files',
      'Diagnostics &amp; engine',
      'Settings &amp; troubleshooting',
    ]);
    assert.ok(!/<details class="il-collapsible" open/.test(view), 'all sections start closed');
  });

  it('baseline details and the capture control live under Baselines & capture', () => {
    const baselines = /<summary>Baselines &amp; capture([\s\S]*?)\n {2}<\/details>/.exec(view);
    assert.ok(baselines);
    assert.ok(baselines[1].includes('data-list="baselines"'));
    assert.ok(baselines[1].includes('file:config.yaml'), 'recent evidence listed');
    assert.ok(baselines[1].includes('data-bind="autoProtectionText"'));
    assert.ok(baselines[1].includes('data-bind="protectionRun"'));
    assert.ok(
      baselines[1].includes('data-action="interlock.captureBaseline"'),
      'manual per-file capture stays reachable',
    );
  });

  it('the sensitive-file policy and user exclusions are disclosed', () => {
    const exclusions = /<summary>Exclusions &amp; sensitive files([\s\S]*?)\n {2}<\/details>/.exec(
      view,
    );
    assert.ok(exclusions);
    // The note ships as static copy, escaped like every other string.
    assert.ok(exclusions[1].includes(escapeHtml(SENSITIVE_POLICY_NOTE)));
    assert.ok(exclusions[1].includes('can never'));
    assert.ok(exclusions[1].includes('data-bind="exclusionsText"'));
    assert.ok(exclusions[1].includes('2 user exclusion patterns: docs/generated/**, vendor/**.'));
    assert.ok(exclusions[1].includes('data-action="interlock.settings"'));
  });

  it('engine facts, git signal and engine actions live under Diagnostics & engine', () => {
    const engine = /<summary>Diagnostics &amp; engine([\s\S]*?)\n {2}<\/details>/.exec(view);
    assert.ok(engine);
    for (const key of ['engineText', 'pythonText', 'platformText', 'engineVersion', 'lastCheck', 'engineHeadline']) {
      assert.ok(engine[1].includes(`data-bind="${key}"`), `missing ${key}`);
    }
    assert.ok(engine[1].includes('Git signal'));
    assert.ok(engine[1].includes('never mean corruption'));
    assert.ok(engine[1].includes('data-bind="gitText" data-bind-value="2 changed files"'));
    for (const action of ['interlock.checkInstallation', 'interlock.checkStatus', 'interlock.openOutput']) {
      assert.ok(engine[1].includes(`data-action="${action}"`), `missing ${action}`);
    }
  });

  it('warnings, verification, incidents and settings live under their own section', () => {
    const trouble = /<summary>Settings &amp; troubleshooting([\s\S]*?)\n {2}<\/details>/.exec(view);
    assert.ok(trouble);
    assert.ok(trouble[1].includes('data-list="warnings"'));
    assert.ok(trouble[1].includes('long path warning'));
    assert.ok(trouble[1].includes('data-bind="verifyText"'));
    assert.ok(trouble[1].includes('data-bind="incidentText"'));
    assert.ok(trouble[1].includes('empty incident_id'));
    for (const action of ['interlock.openDocumentation', 'interlock.settings']) {
      assert.ok(trouble[1].includes(`data-action="${action}"`), `missing ${action}`);
    }
    // the warning badge rides on the summary, so urgency is visible closed
    assert.ok(/<summary>Settings &amp; troubleshooting[\s\S]{0,200}data-bind="warningCount"/.test(view));
  });

  it('urgent errors are never trapped inside a collapsed section', () => {
    const stripped = body({ ...richModel(), lastError: 'engine exploded' });
    // The always-visible strip carries the error outside every <details>.
    const strip = /<div class="il-strip"[^>]*>[\s\S]*?data-bind="stripText" data-bind-value="([^"]*)"/.exec(
      stripped,
    );
    assert.ok(strip && strip[1].includes('engine exploded'));
    const openingTag = /<div class="il-strip"[^>]*>/.exec(stripped);
    assert.ok(openingTag && !/\shidden[\s>]/.test(openingTag[0]), 'a real error must not be hidden');
  });
});

describe('webview message validation', () => {
  it('accepts the documented messages', () => {
    assert.ok(isWebviewMessage({ type: 'ready' }));
    assert.ok(isWebviewMessage({ type: 'openSettings' }));
    for (const command of WEBVIEW_COMMANDS) {
      assert.ok(isWebviewMessage({ type: 'run', command }), `rejected ${command}`);
    }
  });

  it('rejects anything not on the allow-list', () => {
    assert.ok(!isWebviewMessage({ type: 'run', command: 'workbench.action.closeWindow' }));
    assert.ok(!isWebviewMessage({ type: 'run', command: 'interlock.notACommand' }));
    assert.ok(!isWebviewMessage({ type: 'run', command: 'rm -rf /' }));
    assert.ok(!isWebviewMessage({ type: 'run', command: 42 }));
    assert.ok(!isWebviewMessage({ type: 'run' }));
    assert.ok(!isWebviewMessage({ type: 'evil' }));
    assert.ok(!isWebviewMessage({ type: 3 }));
    assert.ok(!isWebviewMessage(null));
    assert.ok(!isWebviewMessage('ready'));
    assert.ok(!isWebviewMessage([{ type: 'ready' }]));
    assert.ok(!isWebviewMessage(undefined));
    assert.ok(!isWebviewMessage({ type: 'run', command: { toString: () => 'interlock.refresh' } }));
  });
});

// ------------------------------------------------------- visual cohesion

/** Extract the shipped stylesheet from a rendered document. */
function stylesheet(model: SidebarModel): string {
  const html = render(model);
  return html.slice(html.indexOf('<style'), html.indexOf('</style>'));
}

/** The shared `--il-fs-*` type tokens declared in `:root`, in px. */
function typeTokens(css: string): Map<string, number> {
  const tokens = new Map<string, number>();
  for (const m of css.matchAll(/(--il-fs-[a-z0-9-]+):\s*([\d.]+)px/g)) {
    tokens.set(m[1], parseFloat(m[2]));
  }
  return tokens;
}

/**
 * Every `font-size` in the stylesheet resolved to px. Sizes must come from
 * the shared `--il-fs-*` scale; a bare `NNpx` (outside `:root`) is a
 * one-off override and fails the assertion.
 */
function fontSizes(css: string): number[] {
  const tokens = typeTokens(css);
  const sizes: number[] = [];
  for (const m of css.matchAll(/font-size:\s*([^;]+);/g)) {
    const value = m[1].trim();
    const token = /^var\((--il-fs-[a-z0-9-]+)\)$/.exec(value);
    if (token) {
      const px = tokens.get(token[1]);
      assert.ok(px !== undefined, `font-size uses an unknown type token: ${value}`);
      sizes.push(px);
      continue;
    }
    assert.match(value, /^[\d.]+px$/, `font-size must come from the --il-fs-* scale: ${value}`);
    sizes.push(parseFloat(value));
  }
  return sizes;
}

describe('sidebar visual cohesion', () => {
  const css = stylesheet(richModel());

  it('uses one corner-radius scale, with no stray literal radii', () => {
    for (const name of ['--il-r-xs', '--il-r-sm', '--il-r-md', '--il-r-lg', '--il-r-full']) {
      assert.ok(css.includes(`${name}:`), `missing radius token ${name}`);
    }
    const outsideRoot = css.slice(css.indexOf('}') + 1);
    const literals = [...outsideRoot.matchAll(/border-radius:\s*([^;]+);/g)]
      .map((m) => m[1].trim())
      .filter((value) => !value.startsWith('var(--il-r-') && value !== '50%');
    assert.deepStrictEqual(literals, [], `stray border-radius values: ${literals.join(', ')}`);
  });

  it('uses one spacing scale for gaps and padding', () => {
    for (const name of ['--il-s1', '--il-s2', '--il-s3', '--il-s4']) {
      assert.ok(css.includes(`${name}:`), `missing spacing token ${name}`);
    }
    // No literal gap below the 3px floor.
    const literalGaps = [...css.matchAll(/(?:^|[;{\s])gap:\s*([\d.]+)px/g)]
      .map((m) => parseFloat(m[1]))
      .filter((gap) => gap < 3);
    assert.deepStrictEqual(literalGaps, [], 'gaps must use the spacing scale (>= 3px)');
  });

  it('keeps the dark graphite + electric yellow palette', () => {
    assert.ok(css.includes('--il-accent: #FFE500'));
    assert.ok(css.includes('--il-bg: #0A0B0B'));
    assert.ok(/\.il-primary\s*\{[^}]*var\(--il-accent\)/.test(css));
  });

  it('gives the workspace folder name visual priority', () => {
    const tokens = typeTokens(css);
    const name = /\.il-name\s*\{[^}]*font-size:\s*var\((--il-fs-[a-z0-9-]+)\)/.exec(css);
    const desc = /\.il-rowdesc\s*\{[^}]*font-size:\s*var\((--il-fs-[a-z0-9-]+)\)/.exec(css);
    assert.ok(name && desc, 'both styles must read their size from the type scale');
    const namePx = tokens.get(name[1]);
    const descPx = tokens.get(desc[1]);
    assert.ok(namePx !== undefined && descPx !== undefined, 'both type tokens must be declared');
    assert.ok(
      namePx > descPx,
      `.il-name (${namePx}px) must be larger than .il-rowdesc (${descPx}px)`,
    );
  });

  it('uses one shared type scale with no one-off font sizes', () => {
    for (const token of [
      '--il-fs-brand',
      '--il-fs-display',
      '--il-fs-h1',
      '--il-fs-h2',
      '--il-fs-body',
      '--il-fs-meta',
      '--il-fs-sm',
      '--il-fw-med',
      '--il-fw-semi',
      '--il-fw-bold',
      '--il-lh',
      '--il-ls',
      '--il-font',
    ]) {
      assert.ok(css.includes(`${token}:`), `missing type token ${token}`);
    }
    // fontSizes() throws on any bare px size outside the scale.
    assert.ok(fontSizes(css).length >= 20, 'the sidebar must size its text through the scale');
  });

  it('no text drops below the 12px floor', () => {
    const sizes = fontSizes(css);
    assert.ok(sizes.length > 0);
    assert.ok(Math.min(...sizes) >= 12, `smallest was ${Math.min(...sizes)}px`);
    // Headline, headings and body copy keep their intended hierarchy.
    const tokens = typeTokens(css);
    assert.ok((tokens.get('--il-fs-brand') ?? 0) >= 16, 'product title must stay 16px+');
    assert.ok((tokens.get('--il-fs-h1') ?? 0) >= 14, 'section headings must stay 14px+');
    assert.ok((tokens.get('--il-fs-body') ?? 0) >= 13, 'descriptions must stay 13px+');
    assert.ok(
      (tokens.get('--il-fs-brand') ?? 0) > (tokens.get('--il-fs-body') ?? 0),
      'the product title must outrank body copy',
    );
  });

  it('offers large click targets and keyboard focus', () => {
    assert.ok(css.includes(':focus-visible'));
    assert.ok(/\.il-rowbtn\s*\{[^}]*min-height: 28px/.test(css));
    assert.ok(/\.il-primary\s*\{[^}]*padding:/.test(css));
    assert.ok(css.includes('prefers-reduced-motion: reduce'));
  });

  it('keeps the narrow fallback free of horizontal overflow', () => {
    const narrow = /@media \(max-width: 270px\)\s*\{([\s\S]*?)\n\}/.exec(css);
    assert.ok(narrow, 'narrow-width rules missing');
    assert.ok(
      narrow[1].includes('.il-kv') && narrow[1].includes('grid-template-columns: 1fr'),
      'the detail grid must stack at narrow widths',
    );
    assert.ok(narrow[1].includes('.il-wordmark'), 'the wordmark must relax its tracking');
    // Long prose wraps rather than scrolling sideways.
    assert.ok((css.match(/overflow-wrap:\s*anywhere/g) ?? []).length >= 4);
  });

  it('renders every control icon in the same optical column', () => {
    const view = body(emptyModel());
    // primary button + the duo (analyze, recover) + the two secondary rows
    // + 5 advanced links + the two settings entries (exclusions, help).
    assert.strictEqual(
      (view.match(/il-btn-ico/g) ?? []).length,
      ACTIONS.length + ADVANCED_LINKS.length + 2,
    );
  });
});

// ------------------------------------------------- updater parity

describe('sidebar polish - status and honesty details', () => {
  it('renders refused confinement and failed verification as failures', () => {
    const out = body({
      ...richModel(),
      workspaceAuthorized: false,
      verification: {
        ...(richModel().verification as StoredVerification),
        success: false,
        reason: 'hash mismatch',
      },
      lastError: 'verify failed',
      lastAction: null,
    });
    assert.ok(out.includes('data-bind="verifyText" data-bind-value="Failed"'));
    assert.ok(out.includes('data-tone="verifyTone" data-tone-value="bad"'));
    assert.ok(out.includes('data-tone="platformTone" data-tone-value="ok"'));
    assert.ok(out.includes('verify failed'), 'last error must be surfaced');
  });

  it('keeps an untested platform visually distinct from a healthy engine', () => {
    const out = render({
      ...richModel(),
      status: { ...richModel().status!, platformStatus: 'UNTESTED' },
    });
    assert.ok(out.includes('data-tone="platformTone" data-tone-value="idle"'));
    assert.ok(out.includes('Platform untested: recovery results are not guaranteed here.'));
  });

  it('marks an unsupported platform as bad even with a working engine', () => {
    const out = render({
      ...richModel(),
      status: { ...richModel().status!, platformStatus: 'UNSUPPORTED' },
    });
    assert.ok(out.includes('data-tone="platformTone" data-tone-value="bad"'));
  });

  it('shows each status exactly once in its own place', () => {
    const view = body(richModel());
    const count = (needle: string): number => view.split(needle).length - 1;
    assert.strictEqual(count('data-bind="engineText"'), 1);
    // the headline appears exactly twice: the header pill and the card.
    assert.strictEqual(count('data-bind="protectionHeadline"'), 2);
    assert.strictEqual(count('data-bind="verifyText"'), 1);
    assert.strictEqual(count('data-bind="workspaceName"'), 1);
    assert.strictEqual(count('data-bind="primaryDesc"'), 1);
  });

  it('keeps the incident section truthful (engine has no incident store)', () => {
    const out = body(emptyModel());
    assert.ok(out.includes('No incident history'));
    assert.ok(out.includes('empty incident_id'));
  });

  it('leaves an unverified state blank but explains fully on hover', () => {
    const html = render(emptyModel());
    assert.ok(/data-bind="verifyDetail" data-bind-value=""[^>]*hidden>/.test(html));
    assert.ok(
      html.includes(
        'Run Verify Recovery after a recovery to record an independent byte-exact result.',
      ),
    );
    const rich = render(richModel());
    const detail = /data-bind="verifyDetail" data-bind-value="([^"]*)"/.exec(rich);
    assert.ok(detail && detail[1].includes('byte-exact match'));
  });
});

describe('sidebar updater - the shipped script mirrors the renderer', () => {
  const html = render(richModel());
  const script = html.slice(html.indexOf('<script'));

  it('refreshes the same binding, tone, row and duo tables', () => {
    assert.ok(script.includes(JSON.stringify(BIND_KEYS)), 'updater BINDS out of sync');
    assert.ok(script.includes(JSON.stringify(TONE_KEYS)), 'updater TONES out of sync');
    assert.ok(script.includes(JSON.stringify(TITLE_BIND_KEYS)), 'updater TITLE_BINDS out of sync');
    assert.ok(script.includes(JSON.stringify(ROW_KEYS)), 'updater ROW_ORDER out of sync');
    assert.ok(script.includes(JSON.stringify(DUO_KEYS)), 'updater DUO_ORDER out of sync');
  });

  it('speaks the same copy as the renderer (injected, not retyped)', () => {
    assert.ok(script.includes(JSON.stringify(ROW_COPY)), 'updater ROW_COPY out of sync');
    assert.ok(script.includes(JSON.stringify(PRIMARY_COPY)), 'updater PRIMARY_COPY out of sync');
    assert.ok(script.includes('"Protect My Workspace"'), 'updater protect copy out of sync');
    assert.ok(script.includes(ROW_COPY._whyEvidence), 'updater disabled reason out of sync');
    assert.ok(script.includes(ROW_COPY.recover.enabled), 'updater recover copy out of sync');
    assert.ok(script.includes('No user exclusion patterns configured.'), 'updater exclusions copy');
  });

  it('mirrors the protection ladder and the recovery-ready upgrade', () => {
    // States the script's own fallback can produce are present as literals;
    // "Analyzing" is never fabricated client-side - it arrives host-pushed.
    for (const label of [
      'No folder open',
      'Protection unavailable',
      'Needs protection',
      'Protected',
      'Not verified yet',
      'Recovery ready',
    ]) {
      assert.ok(script.includes(label), `updater missing protection state: ${label}`);
    }
    assert.ok(script.includes('"analyzing"'), 'updater tone table lacks the analyzing key');
    assert.ok(script.includes('"recovery-ready"'), 'updater lacks the recovery-ready status key');
    assert.ok(script.includes('"partial"'), 'updater lacks the partial status key');
    assert.ok(script.includes('1800000'), 'updater preview TTL missing');
    assert.ok(script.includes('[data-duo="'), 'updater must drive the duo buttons');
    assert.ok(script.includes('[data-row="'), 'updater must drive the secondary rows');
  });

  it('only ever writes textContent, hidden, disabled, title and data attributes', () => {
    assert.ok(!/innerHTML/.test(script), 'innerHTML must never be used by the updater');
    assert.ok(script.includes("el.hasAttribute('data-hide-empty')"));
    assert.ok(script.includes("vscode.postMessage({ type: 'run', command:"));
  });
});
