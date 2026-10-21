import * as assert from 'assert';

import {
  describeProtectionPlan,
  duoStates,
  DUO_KEYS,
  evaluateProtection,
  exclusionSummary,
  globToRegExp,
  isPreviewPending,
  isSensitiveResource,
  matchesExclusionPattern,
  planProtection,
  PREVIEW_TTL_MS,
  protectionOf,
  PRIMARY_COPY,
  PROTECTION_CAPTURE_CAP,
  PROTECTION_ICON,
  PROTECTION_TONE,
  ProtectionInput,
  recoveryRowStates,
  ROW_COPY,
  SENSITIVE_MARKERS,
  SENSITIVE_POLICY_NOTE,
} from '../../src/protection';
import { emptyModel, SidebarModel } from '../../src/sidebar';
import { StoredStatus, StoredVerification } from '../../src/state';

const WS = 'F:\\projects\\demo';

const engineAvailable: StoredStatus = {
  at: '2026-10-19T10:00:00.000Z',
  engineAvailable: true,
  engineVersion: 'source checkout',
  engineRoot: 'F:\\repo',
  pythonVersion: '3.11.9',
  platformStatus: 'TESTED - PRIMARY',
  headline: 'ok',
};

function input(overrides: Partial<ProtectionInput> = {}): ProtectionInput {
  return {
    workspacePath: WS,
    workspaceAuthorized: null,
    baselineCount: 0,
    engineStatus: null,
    verification: null,
    ...overrides,
  };
}

function model(overrides: Partial<SidebarModel> = {}): SidebarModel {
  return { ...emptyModel(), ...overrides };
}

describe('protection status - evidence ladder (never engine availability)', () => {
  it('no folder open is unknown, never a protection claim', () => {
    const state = evaluateProtection(input({ workspacePath: null }));
    assert.strictEqual(state.status, 'unknown');
    assert.strictEqual(state.headline, 'No folder open');
    assert.strictEqual(state.countsText, '');
  });

  it('a live run wins over everything and says what it is doing', () => {
    const state = evaluateProtection(
      input({ analyzing: true, analyzingDetail: 'Capturing recovery evidence…' }),
    );
    assert.strictEqual(state.status, 'analyzing');
    assert.strictEqual(state.headline, 'Analyzing');
    assert.strictEqual(state.detail, 'Capturing recovery evidence…');
  });

  it('refused confinement is action-required with a plain blocker', () => {
    const state = evaluateProtection(input({ workspaceAuthorized: false, baselineCount: 3 }));
    assert.strictEqual(state.status, 'action-required');
    assert.strictEqual(state.headline, 'Protection unavailable');
    assert.ok(state.blocker && state.blocker.includes('confinement'));
    assert.ok(state.blocker.includes('Analyze Workspace'));
  });

  it('an engine that did not respond is action-required, not protected', () => {
    const state = evaluateProtection(
      input({ engineStatus: { ...engineAvailable, engineAvailable: false }, baselineCount: 3 }),
    );
    assert.strictEqual(state.status, 'action-required');
    assert.strictEqual(state.headline, 'Protection unavailable');
    assert.ok(state.blocker && state.blocker.includes('Check Installation'));
  });

  it('a failed verification is action-required and names the file', () => {
    const verification: StoredVerification = {
      workspace: WS,
      resource: 'file:config.yaml',
      at: '2026-10-19T10:05:00.000Z',
      success: false,
      reason: 'hash mismatch',
      checksPassed: [],
      checksFailed: ['hash'],
    };
    const state = evaluateProtection(input({ verification, baselineCount: 3 }));
    assert.strictEqual(state.status, 'action-required');
    assert.ok(state.detail.includes('file:config.yaml'));
    assert.strictEqual(state.blocker, 'Verification reported: hash mismatch');
  });

  it('an available engine with zero evidence is needs-protection', () => {
    const state = evaluateProtection(input({ engineStatus: engineAvailable }));
    assert.strictEqual(state.status, 'needs-protection');
    assert.strictEqual(state.headline, 'Needs protection');
    assert.ok(state.detail.includes("isn't protected yet"));
    assert.strictEqual(state.countsText, 'no recovery evidence yet');
    assert.strictEqual(state.blocker, null);
  });

  it('baselines + engine availability alone is still not "Protected"', () => {
    // Evidence exists but the engine has never authorized this folder.
    const state = evaluateProtection(input({ baselineCount: 3, engineStatus: engineAvailable }));
    assert.strictEqual(state.status, 'unknown');
    assert.strictEqual(state.headline, 'Not verified yet');
    assert.ok(state.detail.includes('has not been authorized'));
  });

  it('baselines + an authorized workspace is Protected', () => {
    const state = evaluateProtection(
      input({
        baselineCount: 3,
        workspaceAuthorized: true,
        engineStatus: engineAvailable,
        checkedAt: '2026-10-19T10:00:00.000Z',
      }),
    );
    assert.strictEqual(state.status, 'protected');
    assert.strictEqual(state.headline, 'Protected');
    assert.strictEqual(state.countsText, '3 files protected');
    assert.strictEqual(state.coveredFiles, 3);
    assert.strictEqual(state.checkedAt, '2026-10-19T10:00:00.000Z');
  });

  it('partial coverage is its own honest state, with the real counts shown', () => {
    const state = evaluateProtection(
      input({
        baselineCount: 2,
        eligibleFiles: 5,
        workspaceAuthorized: true,
        engineStatus: engineAvailable,
      }),
    );
    assert.strictEqual(state.status, 'partial');
    assert.strictEqual(state.headline, 'Partial protection');
    assert.strictEqual(state.countsText, '2 of 5 files protected');
    assert.strictEqual(state.detail, 'Some files in this workspace still have no recovery evidence.');
  });

  it('skipped files are disclosed alongside the coverage', () => {
    const state = evaluateProtection(
      input({ baselineCount: 4, skippedFiles: 2, workspaceAuthorized: true }),
    );
    assert.strictEqual(state.countsText, '4 files protected · 2 files skipped by policy');
  });

  it('a singular count reads correctly', () => {
    const state = evaluateProtection(input({ baselineCount: 1, workspaceAuthorized: true }));
    assert.strictEqual(state.countsText, '1 file protected');
  });

  it('every status has a tone and an icon', () => {
    const statuses = Object.keys(PROTECTION_TONE) as Array<keyof typeof PROTECTION_TONE>;
    for (const status of statuses) {
      assert.ok(PROTECTION_ICON[status], `no icon for ${status}`);
    }
    assert.strictEqual(Object.keys(PROTECTION_TONE).length, 7);
    // The distinct icon keys cover the closed icon set the renderer ships.
    assert.deepStrictEqual(
      [...new Set(Object.values(PROTECTION_ICON))].sort(),
      ['pulse', 'rotate', 'shield', 'shieldAlert', 'shieldCheck'].sort(),
    );
    // Recovery-ready is the electric-yellow "you can act" tone, never a
    // success green - nothing has been restored at that point.
    assert.strictEqual(PROTECTION_TONE['recovery-ready'], 'accent');
    assert.strictEqual(PROTECTION_TONE['partial'], 'warn');
  });
});

describe('recovery-ready - render-time upgrade over real evidence', () => {
  const now = Date.parse('2026-10-19T12:00:00.000Z');

  function protectedModel(overrides: Partial<SidebarModel> = {}): SidebarModel {
    return model({
      workspacePath: WS,
      workspaceAuthorized: true,
      baselineCount: 1,
      ...overrides,
    });
  }

  const freshPreview = (wouldSucceed = true, at = new Date(now - 60_000).toISOString()) => ({
    workspace: WS,
    resource: 'file:config.yaml',
    at,
    wouldSucceed,
  });

  it('a fresh same-workspace preview that would succeed shows Recovery ready', () => {
    const state = protectionOf(protectedModel({ pendingPreview: freshPreview() }), now);
    assert.strictEqual(state.status, 'recovery-ready');
    assert.strictEqual(state.headline, 'Recovery ready');
    assert.ok(state.detail.includes('file:config.yaml'));
    assert.ok(state.detail.includes('side-by-side diff'), 'the diff is the review step');
    assert.strictEqual(state.countsText, '1 file protected', 'coverage stays disclosed');
    assert.strictEqual(state.blocker, null);
  });

  it('a multi-file preview says how many diffs are waiting', () => {
    const preview = { ...freshPreview(), resources: ['index.html', 'assets/app.js'] };
    const state = protectionOf(protectedModel({ pendingPreview: preview }), now);
    assert.strictEqual(state.status, 'recovery-ready');
    assert.ok(state.detail.includes('2 files'), state.detail);
    assert.ok(state.detail.includes('each side-by-side diff'), state.detail);
  });

  it('a preview that would not succeed never becomes recovery-ready', () => {
    const state = protectionOf(protectedModel({ pendingPreview: freshPreview(false) }), now);
    assert.strictEqual(state.status, 'protected');
    assert.strictEqual(state.headline, 'Protected');
  });

  it('an expired preview falls back to the honest evidence state', () => {
    const m = protectedModel({
      pendingPreview: freshPreview(true, new Date(now - PREVIEW_TTL_MS - 1).toISOString()),
    });
    assert.ok(!isPreviewPending(m, now));
    assert.strictEqual(protectionOf(m, now).status, 'protected');
  });

  it('a preview for another workspace is ignored', () => {
    const preview = { ...freshPreview(), workspace: 'F:\\projects\\elsewhere' };
    const m = protectedModel({ pendingPreview: preview });
    assert.ok(!isPreviewPending(m, now));
    assert.strictEqual(protectionOf(m, now).status, 'protected');
  });

  it('an unparsable preview timestamp is treated as absent', () => {
    const m = protectedModel({ pendingPreview: { ...freshPreview(), at: 'not-a-date' } });
    assert.ok(!isPreviewPending(m, now));
    assert.strictEqual(protectionOf(m, now).status, 'protected');
  });

  it('partial protection upgrades too, without hiding the partial scope', () => {
    const m = model({
      workspacePath: WS,
      workspaceAuthorized: true,
      baselineCount: 2,
      protection: evaluateProtection(
        input({
          baselineCount: 2,
          eligibleFiles: 5,
          workspaceAuthorized: true,
          engineStatus: engineAvailable,
        }),
      ),
      pendingPreview: freshPreview(),
    });
    const state = protectionOf(m, now);
    assert.strictEqual(state.status, 'recovery-ready');
    assert.strictEqual(state.countsText, '2 of 5 files protected', 'partial scope stays visible');
  });

  it('an unusable baseline never becomes recovery-ready', () => {
    // Needs protection (no evidence at all) with a stray preview stays honest.
    const m = model({ workspacePath: WS, pendingPreview: freshPreview() });
    assert.strictEqual(protectionOf(m, now).status, 'needs-protection');
  });

  it('a refused workspace never becomes recovery-ready', () => {
    const m = model({
      workspacePath: WS,
      workspaceAuthorized: false,
      baselineCount: 1,
      pendingPreview: freshPreview(),
    });
    assert.strictEqual(protectionOf(m, now).status, 'action-required');
  });
});

describe('action availability - prominent duo and secondary rows', () => {
  it('with no folder everything states the folder reason', () => {
    for (const key of ['preview', 'verify'] as const) {
      const row = recoveryRowStates(model())[key];
      assert.ok(row.disabled, `${key} must be disabled without a folder`);
      assert.strictEqual(row.description, ROW_COPY._whyFolder);
    }
    for (const key of ['analyze', 'recover'] as const) {
      const entry = duoStates(model())[key];
      assert.ok(entry.disabled, `${key} must be disabled without a folder`);
      assert.strictEqual(entry.description, ROW_COPY._whyFolder);
    }
  });

  it('analyze only needs a folder; the recovery rows need evidence', () => {
    const duo = duoStates(model({ workspacePath: WS }));
    assert.ok(!duo.analyze.disabled, 'analyze stays available (read-only)');
    assert.strictEqual(duo.analyze.description, ROW_COPY.analyze.enabled);
    // Recover opens the Inbox, which reports honestly when there is nothing
    // to recover from - so it only needs an open folder.
    assert.ok(!duo.recover.disabled, 'recover (the Inbox) only needs a folder');
    assert.strictEqual(duo.recover.description, ROW_COPY.recover.enabled);
    for (const key of ['preview', 'verify'] as const) {
      const row = recoveryRowStates(model({ workspacePath: WS }))[key];
      assert.ok(row.disabled, `${key} needs evidence`);
      assert.strictEqual(row.description, ROW_COPY._whyEvidence);
    }
  });

  it('with folder + evidence every control is enabled with its own description', () => {
    const m = model({ workspacePath: WS, baselineCount: 1 });
    for (const key of ['analyze', 'recover'] as const) {
      assert.ok(!duoStates(m)[key].disabled, `${key} must be enabled`);
      assert.ok(duoStates(m)[key].description.length > 0);
      assert.ok(!duoStates(m)[key].description.includes('first.'), 'no stale reason');
    }
    for (const key of ['preview', 'verify'] as const) {
      assert.ok(!recoveryRowStates(m)[key].disabled, `${key} must be enabled`);
      assert.ok(recoveryRowStates(m)[key].description.length > 0);
    }
  });

  it('Recover is a real, distinct recovery command; preview and verify stay separate', () => {
    const m = model({ workspacePath: WS, baselineCount: 1 });
    assert.deepStrictEqual([...DUO_KEYS], ['analyze', 'recover']);
    assert.deepStrictEqual(
      [...DUO_KEYS].map((k) => duoStates(m)[k].actionId),
      ['interlock.analyzeWorkspace', 'interlock.openRecoveryInbox'],
    );
    assert.deepStrictEqual(
      (['preview', 'verify'] as const).map((k) => recoveryRowStates(m)[k].actionId),
      ['interlock.previewRecoveryPlan', 'interlock.verifyRecovery'],
    );
  });

  it('the primary button copy is static protection copy', () => {
    assert.strictEqual(PRIMARY_COPY.label, 'Protect My Workspace');
    assert.strictEqual(PRIMARY_COPY.explain, 'Create and verify a baseline.');
  });
});

describe('exclusion disclosure - policy note and user patterns', () => {
  it('the policy note names the built-in markers', () => {
    assert.ok(SENSITIVE_POLICY_NOTE.includes('never captured automatically'));
    for (const marker of ['.env', 'id_rsa', 'private.pem', 'secret']) {
      assert.ok(SENSITIVE_POLICY_NOTE.includes(marker), `note must name ${marker}`);
    }
  });

  it('no user patterns says so plainly', () => {
    assert.strictEqual(exclusionSummary([]), 'No user exclusion patterns configured.');
  });

  it('user patterns are listed, singular reads correctly, extras are counted', () => {
    assert.strictEqual(
      exclusionSummary(['docs/generated/**']),
      '1 user exclusion pattern: docs/generated/**.',
    );
    const many = Array.from({ length: 7 }, (_, i) => `gen${i}/**`);
    assert.strictEqual(
      exclusionSummary(many),
      '7 user exclusion patterns: gen0/**, gen1/**, gen2/**, gen3/**, gen4/** +2 more.',
    );
  });
});

describe('exclusion policy - secrets always, user patterns additive', () => {
  it('the sensitive markers mirror the engine list', () => {
    for (const marker of ['.env', 'secret', 'id_rsa', 'private.pem', '.p12', '.pfx', '.ppk']) {
      assert.ok(SENSITIVE_MARKERS.includes(marker), `missing marker ${marker}`);
    }
  });

  it('secret and credential files are excluded wherever they sit', () => {
    for (const path of [
      '.env',
      'app/.env',
      'secrets/production.env',
      'config/secret.yaml',
      'keys/id_rsa',
      '.ssh/id_ed25519',
      'certs/private.pem',
      'store.ppk',
      'vault.kdbx',
    ]) {
      const decision = isSensitiveResource(path);
      assert.ok(decision.excluded, `${path} must be excluded`);
      assert.strictEqual(decision.reason, 'secret or credential file');
    }
  });

  it('ordinary source files are not swept up by marker substrings', () => {
    for (const path of ['src/main.ts', 'docs/keyword-notes.md', 'config/settings.json']) {
      assert.ok(!isSensitiveResource(path).excluded, `${path} must stay capturable`);
    }
  });

  it('user exclusions can only add, never remove the built-ins', () => {
    assert.ok(isSensitiveResource('.env', ['**/*.md']).excluded, 'built-ins still apply');
    const decision = isSensitiveResource('docs/generated/spec.md', ['docs/generated/**']);
    assert.ok(decision.excluded);
    assert.strictEqual(decision.reason, 'excluded by configuration');
  });

  it('glob translation handles *, ? and path separators', () => {
    assert.ok(globToRegExp('*.pem').test('server.pem'));
    assert.ok(!globToRegExp('*.pem').test('server.pem.bak'));
    assert.ok(globToRegExp('logs/?.txt').test('logs/a.txt'));
    assert.ok(!globToRegExp('logs/?.txt').test('logs/ab.txt'));
    assert.ok(matchesExclusionPattern('docs\\generated\\a.md', 'docs/generated/**'));
    assert.ok(matchesExclusionPattern('nested/dir/build.log', '*.log'), 'segment match');
    assert.ok(!matchesExclusionPattern('a.txt', '   '), 'blank pattern never matches');
  });
});

describe('capture plan - reuse, policy skips, honest caps', () => {
  const opts = { maxBaselineBytes: 1000, exclusions: [] as string[] };

  it('existing evidence is reused, never recaptured', () => {
    const plan = planProtection(
      [
        { path: 'a.txt', size: 10 },
        { path: 'b.txt', size: 20 },
      ],
      [{ resource: 'a.txt', hash: 'h1' }],
      opts,
    );
    assert.deepStrictEqual(plan.reused, ['a.txt']);
    assert.deepStrictEqual(plan.toCapture, [{ path: 'b.txt', size: 20 }]);
  });

  it('evidence paths with either separator are recognised', () => {
    const plan = planProtection([{ path: 'src\\main.ts', size: 5 }], [{ resource: 'src/main.ts', hash: 'h' }], opts);
    assert.deepStrictEqual(plan.reused, ['src/main.ts']);
    assert.deepStrictEqual(plan.toCapture, []);
  });

  it('secret files are skipped with a disclosure reason', () => {
    const plan = planProtection(
      [
        { path: '.env', size: 10 },
        { path: 'ok.txt', size: 10 },
      ],
      [],
      opts,
    );
    assert.deepStrictEqual(plan.toCapture, [{ path: 'ok.txt', size: 10 }]);
    assert.deepStrictEqual(plan.skipped, [{ path: '.env', reason: 'secret or credential file' }]);
  });

  it('oversized files are skipped, not silently dropped', () => {
    const plan = planProtection([{ path: 'huge.bin', size: 5000 }], [], opts);
    assert.strictEqual(plan.toCapture.length, 0);
    assert.strictEqual(plan.skipped[0].reason, 'larger than the 1000-byte baseline limit');
  });

  it('a non-finite size counts as oversized (never captured blindly)', () => {
    const plan = planProtection([{ path: 'x.bin', size: Number.NaN }], [], opts);
    assert.strictEqual(plan.toCapture.length, 0);
    assert.ok(plan.skipped[0].reason.startsWith('larger than'));
  });

  it('the per-run cap is disclosed, not applied silently', () => {
    const files = Array.from({ length: PROTECTION_CAPTURE_CAP + 5 }, (_, i) => ({
      path: `f${String(i).padStart(3, '0')}.txt`,
      size: 1,
    }));
    const plan = planProtection(files, [], opts);
    assert.strictEqual(plan.toCapture.length, PROTECTION_CAPTURE_CAP);
    assert.strictEqual(plan.skipped.length, 5);
    assert.strictEqual(plan.skipped[0].reason, 'capture limit for this run reached');
  });

  it('captures come back sorted so progress reads predictably', () => {
    const plan = planProtection(
      [
        { path: 'z.txt', size: 1 },
        { path: 'a.txt', size: 1 },
        { path: 'm.txt', size: 1 },
      ],
      [],
      opts,
    );
    assert.deepStrictEqual(plan.toCapture.map((f) => f.path), ['a.txt', 'm.txt', 'z.txt']);
  });

  it('the disclosure groups skip reasons for a pre-capture summary', () => {
    const plan = planProtection(
      [
        { path: '.env', size: 1 },
        { path: 'id_rsa', size: 1 },
        { path: 'huge.bin', size: 99999 },
      ],
      [],
      opts,
    );
    const text = describeProtectionPlan(plan);
    assert.ok(text.startsWith('0 file(s) will be captured'));
    assert.ok(text.includes('3 will be skipped'));
    assert.ok(text.includes('2 secret or credential file'));
    assert.ok(text.includes('1 over the size limit'));
  });

  it('a fully-covered workspace is disclosed as reused, not recaptured', () => {
    const plan = planProtection([{ path: 'a.txt', size: 1 }], [{ resource: 'a.txt', hash: 'h' }], opts);
    const text = describeProtectionPlan(plan);
    assert.ok(text.startsWith('0 file(s) will be captured'));
    assert.ok(text.includes('1 already have evidence and will be kept untouched'));
  });
});
