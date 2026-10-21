/**
 * Zero-configuration extension-host test.
 *
 * Unlike ./activation.js (which pre-seeds interlock.pythonPath/engineRoot to a
 * developer checkout), this test runs with NO Interlock configuration at all:
 *
 *   - no interlock.pythonPath
 *   - no interlock.engineRoot
 *   - auto-detection left enabled (the default a real user has)
 *
 * It therefore proves the zero-configuration claim in a REAL VS Code host: on
 * activation the extension installs its bundled engine against its BUNDLED
 * runtime (no system Python is configured or required), the install passes its
 * health check, and a real engine call succeeds - all with a default profile.
 *
 * Usage: node test/host/launch-zerocfg.js
 */

'use strict';

const assert = require('assert');
const vscode = require('vscode');

const EXT_ID = 'interlock219-beep.interlock-vscode';

function log(message) {
  console.log(message);
}

async function run() {
  const ext = vscode.extensions.getExtension(EXT_ID);
  assert.ok(ext, `extension ${EXT_ID} is present`);
  const extensionPath = ext.extensionPath;

  const api = await ext.activate();
  assert.ok(api && typeof api.getModel === 'function', 'activation returned the read-only API');
  assert.ok(typeof api.getSetup === 'function', 'activation exposes the setup state');

  // First-run: with no configuration the extension must install its engine
  // against the bundled runtime and pass the health check.
  await vscode.commands.executeCommand('interlock.installEngine');

  const setup = api.getSetup();
  log(`  setup status=${setup.status} phase=${setup.phase} version=${setup.version ?? 'n/a'}`);
  assert.strictEqual(
    setup.status,
    'ready',
    `engine setup reached ready (got ${setup.status}${setup.error ? `: ${setup.error}` : ''})`,
  );

  // The managed engine must resolve WITHOUT any configured interpreter: a real
  // engine call must report the engine available.
  await vscode.commands.executeCommand('interlock.checkInstallation');
  const model = api.getModel();
  assert.ok(model.status, 'checkInstallation recorded a status');
  assert.strictEqual(
    model.status.engineAvailable,
    true,
    `engine available with zero configuration (${model.status.headline ?? ''})`,
  );

  // The engine root and interpreter must be the extension's OWN bundled files,
  // not this checkout and not any configured path.
  const engineRoot = String(model.status.engineRoot ?? '');
  assert.ok(
    engineRoot.startsWith(extensionPath),
    `engine root is the bundled engine inside the extension (got ${engineRoot})`,
  );
  assert.ok(
    !engineRoot.includes('INTERLOCK V4') && !/[\\\/]\.venv[\\\/]/.test(engineRoot),
    'engine root is not a developer checkout or a venv',
  );

  log('  PASS zero-config: bundled engine installed + health-checked + available, no Python configured');
}

module.exports = { run };
