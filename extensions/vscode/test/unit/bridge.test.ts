import * as assert from 'assert';
import {
  buildArgs,
  callBridge,
  describeFailure,
  kindFromErrorKind,
  kindFromExitCode,
  parseEnvelope,
  RunFn,
} from '../../src/bridge';
import { RunResult } from '../../src/runner';

function fakeResult(overrides: Partial<RunResult> = {}): RunResult {
  return {
    exitCode: 0,
    signal: null,
    stdout: '',
    stderr: '',
    timedOut: false,
    cancelled: false,
    truncated: false,
    spawnError: null,
    durationMs: 12,
    ...overrides,
  };
}

const BASE_PARAMS = {
  bridgeScript: 'C:/ext/python/interlock_bridge.py',
  pythonPath: 'C:/venv/Scripts/python.exe',
  invocation: { command: 'plan' as const },
  timeoutMs: 1000,
};

describe('bridge argument building (no shell strings)', () => {
  it('builds an ordered argument array with flag/value pairs', () => {
    const args = buildArgs({
      command: 'execute',
      workspace: 'C:\\ws',
      resource: 'file:src/a.ts',
      baselineFile: 'C:/store/b.json',
      evidenceFile: 'C:/store/b.json.evidence.json',
      approvedBy: 'operator',
      engineRoot: 'C:/engine',
      maxBytes: 4096.7,
    });
    assert.deepStrictEqual(args, [
      'execute',
      '--workspace',
      'C:\\ws',
      '--resource',
      'file:src/a.ts',
      '--baseline-file',
      'C:/store/b.json',
      '--evidence-file',
      'C:/store/b.json.evidence.json',
      '--approved-by',
      'operator',
      '--engine-root',
      'C:/engine',
      '--max-bytes',
      '4096',
    ]);
  });

  it('omits optional flags entirely when unset', () => {
    assert.deepStrictEqual(buildArgs({ command: 'probe' }), ['probe']);
    assert.deepStrictEqual(buildArgs({ command: 'status', maxBytes: 10 }), [
      'status',
      '--max-bytes',
      '10',
    ]);
  });

  it('builds the bulk plan arguments (manifest, slice, evidence flag)', () => {
    const args = buildArgs({
      command: 'plan-many',
      workspace: 'C:\\ws',
      resourcesFile: 'C:/store/manifest.json',
      saveEvidence: true,
      offset: 40,
      limit: 40,
    });
    assert.deepStrictEqual(args, [
      'plan-many',
      '--workspace',
      'C:\\ws',
      '--resources-file',
      'C:/store/manifest.json',
      '--save-evidence',
      '--offset',
      '40',
      '--limit',
      '40',
    ]);
  });

  it('never sends the evidence flag when the caller did not ask for it', () => {
    const args = buildArgs({
      command: 'plan-many',
      workspace: 'C:\\ws',
      resourcesFile: 'C:/store/manifest.json',
      offset: 0,
      limit: 10,
    });
    assert.ok(!args.includes('--save-evidence'));
  });

  it('keeps shell metacharacters as literal single arguments', () => {
    const args = buildArgs({
      command: 'analyze',
      workspace: 'C:/a b',
      resource: 'file:x & y; $(evil).ts',
    });
    // Everything stays in the array - nothing is joined into a shell string.
    assert.strictEqual(args[0], 'analyze');
    assert.strictEqual(args[2], 'C:/a b');
    assert.strictEqual(args[4], 'file:x & y; $(evil).ts');
    assert.strictEqual(args.length, 5);
  });
});

describe('bridge envelope parsing', () => {
  it('accepts a well-formed envelope', () => {
    const { envelope, error } = parseEnvelope(
      JSON.stringify({ bridge: 'interlock', ok: true, result: { python: {} } }),
    );
    assert.strictEqual(error, null);
    assert.strictEqual(envelope?.ok, true);
  });

  it('rejects empty, non-JSON, non-object, and status-less payloads', () => {
    assert.notStrictEqual(parseEnvelope('   ').error, null);
    assert.notStrictEqual(parseEnvelope('not json').error, null);
    assert.notStrictEqual(parseEnvelope('[1,2,3]').error, null);
    assert.notStrictEqual(parseEnvelope('"hello"').error, null);
    assert.notStrictEqual(parseEnvelope('{"result": {}}').error, null);
  });

  it('tolerates surrounding noise-free whitespace and newlines', () => {
    const { envelope } = parseEnvelope('\n  {"ok": false, "error": {"kind": "refused"}}\n');
    assert.strictEqual(envelope?.ok, false);
    assert.strictEqual(envelope?.error?.kind, 'refused');
  });
});

describe('exit code and error kind mapping', () => {
  it('maps every documented bridge exit code', () => {
    assert.strictEqual(kindFromExitCode(0), 'ok');
    assert.strictEqual(kindFromExitCode(2), 'invalid_invocation');
    assert.strictEqual(kindFromExitCode(3), 'engine_unavailable');
    assert.strictEqual(kindFromExitCode(4), 'not_authorized');
    assert.strictEqual(kindFromExitCode(5), 'refused');
    assert.strictEqual(kindFromExitCode(6), 'verification_failed');
    assert.strictEqual(kindFromExitCode(7), 'precondition');
    assert.strictEqual(kindFromExitCode(8), 'internal_error');
    assert.strictEqual(kindFromExitCode(null), 'spawn_error');
    assert.strictEqual(kindFromExitCode(99), 'internal_error');
  });

  it('maps envelope error kinds and rejects unknown kinds', () => {
    assert.strictEqual(kindFromErrorKind('approval_required'), 'refused');
    assert.strictEqual(kindFromErrorKind('preview_required'), 'precondition');
    assert.strictEqual(kindFromErrorKind('no_workspace'), 'not_authorized');
    assert.strictEqual(kindFromErrorKind('engine_unavailable'), 'engine_unavailable');
    assert.strictEqual(kindFromErrorKind('something_new'), null);
    assert.strictEqual(kindFromErrorKind(undefined), null);
  });

  it('describes common failures with actionable headlines', () => {
    const headline = (kind: Parameters<typeof describeFailure>[0]['kind']): string =>
      describeFailure({
        ok: false,
        command: 'plan',
        kind,
        exitCode: null,
        envelope: null,
        result: null,
        message: kind === 'timeout' ? '' : 'detail',
        hint: '',
        stderrExcerpt: '',
        truncated: false,
        durationMs: 0,
      });
    assert.ok(headline('timeout').includes('timed out'));
    assert.ok(headline('cancelled').includes('cancelled'));
    assert.ok(headline('interpreter_not_found').includes('interpreter'));
  });
});

describe('callBridge result normalization (injected runner)', () => {
  const okEnvelope = JSON.stringify({
    bridge: 'interlock',
    command: 'plan',
    ok: true,
    result: { actions: [] },
  });

  it('reports success only for exit 0 plus ok:true envelope', async () => {
    const run: RunFn = async () => fakeResult({ stdout: okEnvelope });
    const result = await callBridge({ ...BASE_PARAMS, run });
    assert.strictEqual(result.ok, true);
    assert.strictEqual(result.kind, 'ok');
    assert.strictEqual(result.exitCode, 0);
    assert.deepStrictEqual(result.result, { actions: [] });
    // The script path must be the first argument, command second.
    assert.ok(result.command === 'plan');
  });

  it('maps a refusal envelope (exit 5, approval_required) to refused', async () => {
    const run: RunFn = async () =>
      fakeResult({
        exitCode: 5,
        stdout: JSON.stringify({
          ok: false,
          error: { kind: 'approval_required', message: 'approval required', hint: 'confirm' },
        }),
      });
    const result = await callBridge({ ...BASE_PARAMS, run });
    assert.strictEqual(result.ok, false);
    assert.strictEqual(result.kind, 'refused');
    assert.strictEqual(result.message, 'approval required');
    assert.strictEqual(result.hint, 'confirm');
  });

  it('prefers the envelope error kind over the exit code', async () => {
    const run: RunFn = async () =>
      fakeResult({
        exitCode: 1,
        stdout: JSON.stringify({ ok: false, error: { kind: 'preview_required' } }),
      });
    const result = await callBridge({ ...BASE_PARAMS, run });
    assert.strictEqual(result.kind, 'precondition');
  });

  it('reports interpreter_not_found on ENOENT spawn errors', async () => {
    const run: RunFn = async () =>
      fakeResult({ exitCode: null, spawnError: 'spawn python.exe ENOENT' });
    const result = await callBridge({ ...BASE_PARAMS, run });
    assert.strictEqual(result.kind, 'interpreter_not_found');
    assert.ok(result.hint.includes('interlock.pythonPath'));
  });

  it('reports spawn_error for non-ENOENT spawn failures', async () => {
    const run: RunFn = async () =>
      fakeResult({ exitCode: null, spawnError: 'EACCES: permission denied' });
    const result = await callBridge({ ...BASE_PARAMS, run });
    assert.strictEqual(result.kind, 'spawn_error');
  });

  it('reports timeout and cancellation distinctly', async () => {
    const timedOut: RunFn = async () => fakeResult({ exitCode: null, timedOut: true });
    const cancelled: RunFn = async () => fakeResult({ exitCode: null, cancelled: true });
    const t = await callBridge({ ...BASE_PARAMS, run: timedOut });
    assert.strictEqual(t.kind, 'timeout');
    assert.ok(t.message.includes('terminated'));
    const c = await callBridge({ ...BASE_PARAMS, run: cancelled });
    assert.strictEqual(c.kind, 'cancelled');
  });

  it('reports protocol_error for non-JSON output and keeps an excerpt', async () => {
    const run: RunFn = async () =>
      fakeResult({ exitCode: 0, stdout: 'Traceback (most recent call last): ...' });
    const result = await callBridge({ ...BASE_PARAMS, run });
    assert.strictEqual(result.kind, 'protocol_error');
    assert.ok(result.stderrExcerpt.length > 0 || result.message.length > 0);
  });

  it('does not treat ok:true with a non-zero exit as success', async () => {
    const run: RunFn = async () =>
      fakeResult({ exitCode: 8, stdout: JSON.stringify({ ok: true, result: {} }) });
    const result = await callBridge({ ...BASE_PARAMS, run });
    assert.strictEqual(result.ok, false);
    assert.strictEqual(result.kind, 'internal_error');
  });

  it('converts a thrown runner error into invalid_invocation', async () => {
    const run: RunFn = async () => {
      throw new Error('Arguments must not contain newlines or NUL characters.');
    };
    const result = await callBridge({ ...BASE_PARAMS, run });
    assert.strictEqual(result.ok, false);
    assert.strictEqual(result.kind, 'invalid_invocation');
    assert.ok(result.message.includes('newlines'));
  });

  it('passes the script path as argv[1] and the command as argv[2]', async () => {
    const seen: { command: string; args: string[] }[] = [];
    const run: RunFn = async (options) => {
      seen.push({ command: options.command, args: options.args });
      return fakeResult({ stdout: okEnvelope });
    };
    await callBridge({ ...BASE_PARAMS, run, invocation: { command: 'verify' } });
    assert.strictEqual(seen.length, 1);
    assert.strictEqual(seen[0].command, 'C:/venv/Scripts/python.exe');
    assert.strictEqual(seen[0].args[0], 'C:/ext/python/interlock_bridge.py');
    assert.strictEqual(seen[0].args[1], 'verify');
  });
});
