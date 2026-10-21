import * as assert from 'assert';
import * as path from 'path';
import { DEFAULTS, InterlockSettings } from '../../src/config';
import { detectEngine, ExistsFn, isEngineRoot } from '../../src/discovery';

function settings(overrides: Partial<InterlockSettings> = {}): InterlockSettings {
  return { ...DEFAULTS, ...overrides };
}

/** An ExistsFn backed by an explicit set of normalized paths. */
function fakeFs(paths: string[]): ExistsFn {
  const set = new Set(paths.map((p) => p.toLowerCase()));
  return (candidate: string) => set.has(candidate.toLowerCase());
}

const VENV_REL = path.join('.venv', process.platform === 'win32' ? 'Scripts' : 'bin',
  process.platform === 'win32' ? 'python.exe' : 'python3');

describe('engine root detection', () => {
  it('recognizes a directory containing the app package', () => {
    assert.ok(isEngineRoot('C:/engine', fakeFs([path.join('C:/engine', 'app', 'main.py')])));
    assert.ok(
      isEngineRoot('C:/engine', fakeFs([path.join('C:/engine', 'app', 'domain', '__init__.py')])),
    );
    assert.ok(!isEngineRoot('C:/engine', () => false));
    assert.ok(!isEngineRoot('', () => true));
  });

  it('auto-detects the engine root from workspace folders', () => {
    const ws = path.join('C:', 'ws');
    const engineWs = path.join('C:', 'engine-checkout');
    const exists = fakeFs([path.join(engineWs, 'app', 'main.py')]);
    const loc = detectEngine(settings(), [ws, engineWs], exists);
    assert.strictEqual(loc.engineRoot, engineWs);
    assert.strictEqual(loc.engineSource, 'detected from workspace');
    assert.deepStrictEqual(loc.issues, []);
  });

  it('does not run auto-detection when it is disabled', () => {
    const engineWs = path.join('C:', 'engine-checkout');
    const exists = fakeFs([path.join(engineWs, 'app', 'main.py')]);
    const loc = detectEngine(settings({ autoDetectEngine: false }), [engineWs], exists);
    assert.strictEqual(loc.engineRoot, undefined);
    assert.ok(loc.issues.some((i) => i.includes('auto-detection is disabled')));
    assert.ok(loc.issues.some((i) => i.includes('interlock.pythonPath')));
  });
});

describe('interpreter detection precedence', () => {
  it('a valid configured interpreter wins over everything', () => {
    const configured = path.join('C:', 'custom', 'python.exe');
    const engineWs = path.join('C:', 'engine-checkout');
    const exists = fakeFs([
      configured,
      path.join(engineWs, 'app', 'main.py'),
      path.join(engineWs, VENV_REL),
    ]);
    const loc = detectEngine(settings({ pythonPath: configured }), [engineWs], exists);
    assert.strictEqual(loc.pythonPath, configured);
    assert.ok(loc.pythonSource.includes('configured'));
  });

  it('a configured path that does not exist is reported, not silently replaced', () => {
    const missing = path.join('C:', 'nope', 'python.exe');
    const engineWs = path.join('C:', 'engine-checkout');
    const exists = fakeFs([
      path.join(engineWs, 'app', 'main.py'),
      path.join(engineWs, VENV_REL),
    ]);
    const loc = detectEngine(settings({ pythonPath: missing }), [engineWs], exists);
    assert.ok(loc.issues.some((i) => i.includes('does not exist')));
    // Auto-detection still runs, but the problem stays visible.
    assert.strictEqual(loc.pythonPath, path.join(engineWs, VENV_REL));
  });

  it('a bare command name is accepted without an existence check', () => {
    const loc = detectEngine(settings({ pythonPath: 'python3.12' }), [], () => false);
    assert.strictEqual(loc.pythonPath, 'python3.12');
    assert.ok(loc.pythonSource.includes('PATH'));
    assert.ok(!loc.issues.some((i) => i.includes('does not exist')));
  });

  it('falls back to a project venv, then to a PATH command name', () => {
    const engineWs = path.join('C:', 'engine-checkout');
    const venvPython = path.join(engineWs, VENV_REL);
    const withVenv = detectEngine(
      settings(),
      [engineWs],
      fakeFs([path.join(engineWs, 'app', 'main.py'), venvPython]),
    );
    assert.strictEqual(withVenv.pythonPath, venvPython);
    assert.ok(withVenv.pythonSource.includes('virtualenv'));

    const withoutVenv = detectEngine(
      settings(),
      [engineWs],
      fakeFs([path.join(engineWs, 'app', 'main.py')]),
    );
    assert.strictEqual(withoutVenv.pythonPath, process.platform === 'win32' ? 'python' : 'python3');
    assert.ok(withoutVenv.pythonSource.includes('PATH lookup'));
  });

  it('flags a configured engine root that lacks the app package', () => {
    const badRoot = path.join('C:', 'not-an-engine');
    const loc = detectEngine(settings({ engineRoot: badRoot, autoDetectEngine: false }), [], () => false);
    assert.strictEqual(loc.engineRoot, undefined);
    assert.ok(loc.issues.some((i) => i.includes('does not contain the Interlock "app" package')));
  });

  it('reports when no engine checkout exists in the workspace', () => {
    const loc = detectEngine(settings(), [path.join('C:', 'plain-project')], () => false);
    assert.strictEqual(loc.engineRoot, undefined);
    assert.ok(loc.issues.some((i) => i.includes('No Interlock engine checkout detected')));
  });

  it('uses a configured engine root even when the workspace has none', () => {
    const root = path.join('C:', 'engine-checkout');
    const exists = fakeFs([path.join(root, 'app', 'main.py'), path.join(root, VENV_REL)]);
    const loc = detectEngine(settings({ engineRoot: root }), [path.join('C:', 'other')], exists);
    assert.strictEqual(loc.engineRoot, root);
    assert.strictEqual(loc.engineSource, 'interlock.engineRoot (configured)');
    assert.strictEqual(loc.pythonPath, path.join(root, VENV_REL));
    assert.deepStrictEqual(loc.issues, []);
  });
});
