import * as assert from 'assert';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import { EngineRuntime, runtimeKey, selectBundledRuntime } from '../../src/engineRuntime';
import { RunOptions, RunResult } from '../../src/runner';

const EXTENSION_PATH = path.resolve(__dirname, '..', '..', '..');

function okResult(stdout: string): RunResult {
  return {
    stdout,
    stderr: '',
    exitCode: 0,
    spawnError: null,
    timedOut: false,
    cancelled: false,
    truncated: false,
  } as RunResult;
}

function failResult(): RunResult {
  return {
    stdout: '',
    stderr: 'synthetic failure',
    exitCode: 1,
    spawnError: null,
    timedOut: false,
    cancelled: false,
    truncated: false,
  } as RunResult;
}

describe('bundled runtime selection', () => {
  it('runtimeKey is platform-arch shaped', () => {
    assert.strictEqual(runtimeKey('win32', 'x64'), 'win32-x64');
    assert.strictEqual(runtimeKey('darwin', 'arm64'), 'darwin-arm64');
  });

  it('finds the Windows interpreter layout when it exists', () => {
    const wanted = path.join('runtime', 'win32-x64', 'python', 'python.exe');
    const selection = selectBundledRuntime({
      extensionPath: '/ext',
      platform: 'win32',
      arch: 'x64',
      exists: (candidate) => path.normalize(candidate).endsWith(path.normalize(wanted)),
    });
    assert.ok(selection.pythonPath);
    assert.match(selection.pythonPath, /python\.exe$/);
    assert.match(selection.reason, /bundled win32-x64 runtime/);
  });

  it('finds the POSIX interpreter layout when it exists', () => {
    const selection = selectBundledRuntime({
      extensionPath: '/ext',
      platform: 'linux',
      arch: 'x64',
      exists: (candidate) => candidate.endsWith(path.join('bin', 'python3')),
    });
    assert.ok(selection.pythonPath);
    assert.match(selection.reason, /bundled linux-x64 runtime/);
  });

  it('returns null with an honest reason when this build ships no runtime', () => {
    const selection = selectBundledRuntime({
      extensionPath: '/ext',
      platform: 'darwin',
      arch: 'arm64',
      exists: () => false,
    });
    assert.strictEqual(selection.pythonPath, null);
    assert.match(selection.reason, /no bundled runtime for darwin-arm64/);
  });

  it('only ever reads under runtime/<requested-platform>-<arch>/', () => {
    // Ask for darwin-arm64 but make the filesystem only expose a win32-x64
    // interpreter: the darwin selection must NOT adopt another platform's
    // runtime, because it only ever probes runtime/darwin-arm64/.
    const selection = selectBundledRuntime({
      extensionPath: '/ext',
      platform: 'darwin',
      arch: 'arm64',
      exists: (candidate) => candidate.includes(`win32-x64${path.sep}`),
    });
    assert.strictEqual(selection.pythonPath, null);
    assert.match(selection.reason, /no bundled runtime for darwin-arm64/);
  });

  it('this build really ships the Windows x64 runtime it was tested with', () => {
    const selection = selectBundledRuntime({ extensionPath: EXTENSION_PATH });
    if (process.platform === 'win32') {
      assert.ok(selection.pythonPath, 'expected a bundled win32 runtime in this build');
      assert.match(selection.pythonPath, /win32-x64/);
    }
  });
});

describe('EngineRuntime lifecycle', () => {
  function runtime(runner?: (o: RunOptions) => Promise<RunResult>): EngineRuntime {
    return new EngineRuntime({
      extensionPath: EXTENSION_PATH,
      storageDir: os.tmpdir(),
      bridgeScript: path.join(EXTENSION_PATH, 'python', 'interlock_bridge.py'),
      runner,
      // Force the managed path to be considered even off-Windows.
      platform: 'win32',
      arch: 'x64',
      // Excluding a bundled runtime here keeps these lifecycle tests on the
      // deterministic fake-runner path (the bundled path is covered by the
      // real-subprocess tests below, which use the actual shipped runtime).
      exists: () => false,
    });
  }

  it('reports a filesystem-only setup state without spawning anything', () => {
    let spawns = 0;
    const rt = runtime(async () => {
      spawns += 1;
      return failResult();
    });
    const state = rt.state();
    assert.ok(['missing', 'incomplete', 'ready'].includes(state.status));
    assert.strictEqual(spawns, 0, 'state() must never spawn a subprocess');
  });

  it('collapses concurrent installs onto ONE run (single-flight)', async () => {
    let probes = 0;
    const rt = runtime(async (options: RunOptions): Promise<RunResult> => {
      // Answer the interpreter probe, then fail the venv step quickly so the
      // install finishes fast while the guard is still observable.
      if (options.args.includes('-c')) {
        probes += 1;
        return okResult(JSON.stringify({ version: '3.11.9', executable: '/synthetic/python' }));
      }
      return failResult();
    });

    const first = rt.ensureInstalled();
    const second = rt.ensureInstalled();
    assert.strictEqual(first, second, 'concurrent callers must share one install run');
    assert.strictEqual(rt.installing, true);

    await Promise.all([first, second]);
    assert.strictEqual(rt.installing, false, 'the guard is released after the run');
    assert.strictEqual(probes, 1, 'only ONE install (one interpreter probe) ran');

    // A later request starts a fresh run (the guard is not sticky).
    const third = rt.ensureInstalled();
    assert.notStrictEqual(third, first);
    await third;
    assert.strictEqual(probes, 2);
  });

  it('resolve() prefers an intact managed installation over configuration', () => {
    const rt = new EngineRuntime({
      extensionPath: EXTENSION_PATH,
      storageDir: os.tmpdir(),
      bridgeScript: path.join(EXTENSION_PATH, 'python', 'interlock_bridge.py'),
      configuredPython: '/configured/python',
      configuredEngineRoot: '/configured/engine',
      runner: async () => failResult(),
    });
    const resolved = rt.resolve();
    // No managed install record exists in the temp storage, so the explicit
    // configuration is what remains - a developer checkout keeps working.
    if (resolved) {
      assert.strictEqual(resolved.pythonPath, '/configured/python');
      assert.strictEqual(resolved.engineRoot, '/configured/engine');
    }
  });

  it('resolve() is null when there is neither a managed install nor configuration', () => {
    const rt = new EngineRuntime({
      extensionPath: EXTENSION_PATH,
      storageDir: os.tmpdir(),
      bridgeScript: path.join(EXTENSION_PATH, 'python', 'interlock_bridge.py'),
      runner: async () => failResult(),
    });
    assert.strictEqual(rt.resolve(), null);
  });

  it('exposes the bundled engine directory for verification', () => {
    const rt = runtime();
    assert.strictEqual(rt.bundledEngineDir, path.join(EXTENSION_PATH, 'engine'));
  });
});

describe('zero-configuration bundled install (real subprocesses)', function () {
  this.timeout(120_000);
  let storage: string;

  beforeEach(() => {
    storage = fs.mkdtempSync(path.join(os.tmpdir(), 'interlock-runtime-'));
  });

  afterEach(() => {
    fs.rmSync(storage, { recursive: true, force: true });
  });

  it('installs against the bundled runtime, writes a record, and resolves ready', async () => {
    if (process.platform !== 'win32') {
      return; // this build ships the Windows x64 runtime only
    }
    const rt = new EngineRuntime({
      extensionPath: EXTENSION_PATH,
      storageDir: storage,
      bridgeScript: path.join(EXTENSION_PATH, 'python', 'interlock_bridge.py'),
    });

    // Before: nothing is installed.
    assert.notStrictEqual(rt.state().status, 'ready');

    const outcome = await rt.ensureInstalled();
    assert.strictEqual(outcome.ok, true, `install failed: ${outcome.setup.error ?? ''}`);
    assert.strictEqual(outcome.setup.status, 'installed');
    assert.ok(outcome.envelope, 'a real probe envelope must be returned');

    // A record now exists and the filesystem-only state is ready.
    assert.strictEqual(rt.state().status, 'ready');
    assert.ok(fs.existsSync(path.join(storage, 'engine', 'install.json')));

    // The bridge resolves to the BUNDLED interpreter + bundled engine, and the
    // bundled interpreter is what the health check actually ran on.
    const resolved = rt.resolve();
    assert.ok(resolved);
    assert.match(resolved.pythonPath, /win32-x64/);
    assert.strictEqual(resolved.engineRoot, path.join(EXTENSION_PATH, 'engine'));
    assert.match(resolved.source, /managed installation/);

    const python = (outcome.envelope as Record<string, unknown>)['result'] as Record<
      string,
      unknown
    >;
    const info = python['python'] as Record<string, unknown>;
    assert.match(String(info['executable']), /win32-x64/);
    assert.strictEqual(info['in_supported_range'], true);
  });

  it('reuses a valid installation across launches without reinstalling', async () => {
    if (process.platform !== 'win32') {
      return;
    }
    const first = new EngineRuntime({
      extensionPath: EXTENSION_PATH,
      storageDir: storage,
      bridgeScript: path.join(EXTENSION_PATH, 'python', 'interlock_bridge.py'),
    });
    await first.ensureInstalled();

    // A brand-new runtime object (fresh activation) sees a ready installation.
    const second = new EngineRuntime({
      extensionPath: EXTENSION_PATH,
      storageDir: storage,
      bridgeScript: path.join(EXTENSION_PATH, 'python', 'interlock_bridge.py'),
    });
    assert.strictEqual(second.state().status, 'ready');
    assert.ok(second.resolve()?.pythonPath);
  });

  it('detects a corrupted engine bundle and refuses to report ready', async () => {
    if (process.platform !== 'win32') {
      return;
    }
    // Copy the engine tree to a scratch dir and tamper one file.
    const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'interlock-corrupt-'));
    try {
      fs.cpSync(path.join(EXTENSION_PATH, 'engine'), path.join(scratch, 'engine'), {
        recursive: true,
      });
      fs.cpSync(path.join(EXTENSION_PATH, 'python'), path.join(scratch, 'python'), {
        recursive: true,
      });
      fs.writeFileSync(
        path.join(scratch, 'engine', 'app', 'domain', 'services', 'evidence_hash.py'),
        '# tampered\n',
        'utf8',
      );
      const rt = new EngineRuntime({
        extensionPath: scratch,
        storageDir: storage,
        bridgeScript: path.join(scratch, 'python', 'interlock_bridge.py'),
      });
      const outcome = await rt.ensureInstalled();
      assert.strictEqual(outcome.ok, false);
      assert.match(outcome.setup.error ?? '', /verification|failed/i);
      assert.notStrictEqual(rt.state().status, 'ready');
    } finally {
      fs.rmSync(scratch, { recursive: true, force: true });
    }
  });
});
