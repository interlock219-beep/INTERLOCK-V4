import * as assert from 'assert';
import { buildEnv, runProcess, validateInvocation } from '../../src/runner';

const NODE = process.execPath;
const SLEEP = ['-e', 'setTimeout(() => {}, 10000)'];

describe('runner invocation validation', () => {
  it('accepts a normal command plus argument array', () => {
    assert.strictEqual(validateInvocation(NODE, ['-e', 'console.log(1)']), null);
  });

  it('rejects empty commands, newlines, NULs, and non-array arguments', () => {
    assert.notStrictEqual(validateInvocation('', []), null);
    assert.notStrictEqual(validateInvocation('  ', []), null);
    assert.notStrictEqual(validateInvocation('bad\nname', []), null);
    assert.notStrictEqual(validateInvocation('bad\u0000name', []), null);
    assert.notStrictEqual(validateInvocation(NODE, 'not-an-array' as unknown as string[]), null);
    assert.notStrictEqual(validateInvocation(NODE, [42 as unknown as string]), null);
    assert.notStrictEqual(validateInvocation(NODE, ['a\nb']), null);
    assert.notStrictEqual(validateInvocation(NODE, ['a\u0000b']), null);
  });

  it('rejects an invalid invocation before spawning (promise rejects)', async () => {
    await assert.rejects(
      runProcess({ command: '', args: [] }),
      /non-empty string/,
    );
  });
});

describe('runner environment allow-list', () => {
  it('never copies the whole host environment', () => {
    const env = buildEnv();
    // A secret-looking host variable must not be inherited.
    process.env['INTERLOCK_TEST_SECRET'] = 'super-secret-value';
    try {
      const env2 = buildEnv();
      assert.strictEqual(env2['INTERLOCK_TEST_SECRET'], undefined);
      assert.ok(Object.keys(env2).length < Object.keys(process.env).length);
    } finally {
      delete process.env['INTERLOCK_TEST_SECRET'];
    }
    assert.ok(typeof env['PATH'] === 'string' || typeof env['Path'] === 'string');
  });

  it('always forces deterministic UTF-8 python IO', () => {
    const env = buildEnv();
    assert.strictEqual(env['PYTHONUTF8'], '1');
    assert.strictEqual(env['PYTHONIOENCODING'], 'utf-8');
    assert.strictEqual(env['PYTHONUNBUFFERED'], '1');
  });

  it('drops extra env entries containing newlines or NULs', () => {
    const env = buildEnv({
      GOOD: 'yes',
      BAD: 'line\nbreak',
      'BAD\rKEY': 'x',
      'BAD\u0000KEY': 'y',
    });
    assert.strictEqual(env['GOOD'], 'yes');
    assert.strictEqual(env['BAD'], undefined);
    assert.strictEqual(env['BAD\rKEY'], undefined);
    assert.strictEqual(env['BAD\u0000KEY'], undefined);
  });
});

describe('runner process execution', () => {
  it('captures stdout and exit code without a shell', async () => {
    const result = await runProcess({
      command: NODE,
      args: ['-e', 'process.stdout.write("hello")'],
      timeoutMs: 20000,
    });
    assert.strictEqual(result.exitCode, 0);
    assert.strictEqual(result.stdout, 'hello');
    assert.strictEqual(result.spawnError, null);
    assert.strictEqual(result.timedOut, false);
  });

  it('reports a non-zero exit code distinctly from a spawn error', async () => {
    const result = await runProcess({
      command: NODE,
      args: ['-e', 'process.exit(3)'],
      timeoutMs: 20000,
    });
    assert.strictEqual(result.exitCode, 3);
    assert.strictEqual(result.spawnError, null);
  });

  it('passes arguments literally (no shell interpolation)', async () => {
    const marker = '$(echo pwned); & | >';
    const result = await runProcess({
      command: NODE,
      args: ['-e', 'process.stdout.write(process.argv[1] ?? "")', marker],
      timeoutMs: 20000,
    });
    assert.strictEqual(result.exitCode, 0);
    assert.strictEqual(result.stdout, marker);
  });

  it('terminates the child on timeout and flags it', async () => {
    const started = Date.now();
    const result = await runProcess({
      command: NODE,
      args: SLEEP,
      timeoutMs: 700,
      maxOutputBytes: 1024 * 1024,
    });
    assert.strictEqual(result.timedOut, true);
    assert.ok(Date.now() - started < 15000, 'timeout should end well before the child would');
    assert.notStrictEqual(result.exitCode, 0);
  });

  it('terminates the child on external cancellation', async () => {
    const controller = new AbortController();
    setTimeout(() => controller.abort(), 300);
    const result = await runProcess({
      command: NODE,
      args: SLEEP,
      signal: controller.signal,
      timeoutMs: 20000,
    });
    assert.strictEqual(result.cancelled, true);
    assert.strictEqual(result.timedOut, false);
  });

  it('honours an already-aborted signal immediately', async () => {
    const controller = new AbortController();
    controller.abort();
    const result = await runProcess({
      command: NODE,
      args: SLEEP,
      signal: controller.signal,
      timeoutMs: 20000,
    });
    assert.strictEqual(result.cancelled, true);
  });

  it('reports ENOENT-style spawn failures instead of throwing', async () => {
    const result = await runProcess({
      command: 'definitely-not-a-real-binary-interlock-xyz',
      args: [],
      timeoutMs: 5000,
    });
    assert.strictEqual(result.exitCode, null);
    assert.ok(result.spawnError !== null && result.spawnError.length > 0);
  });

  it('truncates output beyond maxOutputBytes and flags it', async () => {
    const result = await runProcess({
      command: NODE,
      args: ['-e', 'process.stdout.write("x".repeat(100000))'],
      timeoutMs: 20000,
      maxOutputBytes: 1000,
    });
    assert.strictEqual(result.truncated, true);
    assert.ok(result.stdout.length <= 1000);
  });
});
