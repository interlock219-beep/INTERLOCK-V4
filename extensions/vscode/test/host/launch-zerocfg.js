/**
 * Launcher for the ZERO-CONFIGURATION extension-host test (./activation-zerocfg.js).
 *
 * Boots a REAL VS Code instance against the extension **as installed from the
 * local VSIX**, with an isolated user-data-dir whose profile contains NO
 * Interlock configuration at all - no pythonPath, no engineRoot, auto-detection
 * left at its default. This is the environment a brand-new user has, so it is
 * the honest test of the zero-configuration claim.
 *
 * Unlike ./launch.js it does not require a developer virtualenv: the bundled
 * runtime inside the VSIX is what must be used.
 *
 * Usage: node test/host/launch-zerocfg.js
 * Exit 0 = every zero-config host check passed.
 */

'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { runTests } = require('@vscode/test-electron');

const VSCODE_EXE =
  process.env.INTERLOCK_VSCODE_EXE ||
  path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Microsoft VS Code', 'Code.exe');
const INSTALLED_EXT_DIR = path.join(
  process.env.USERPROFILE || os.homedir(),
  '.vscode',
  'extensions',
  'interlock219-beep.interlock-vscode-0.1.0',
);

function fail(message) {
  console.error(message);
  process.exitCode = 1;
}

async function main() {
  if (!fs.existsSync(VSCODE_EXE)) {
    fail(`VS Code executable not found: ${VSCODE_EXE} (set INTERLOCK_VSCODE_EXE)`);
    return;
  }
  if (!fs.existsSync(path.join(INSTALLED_EXT_DIR, 'package.json'))) {
    fail(`Installed extension not found at ${INSTALLED_EXT_DIR}. Run code --install-extension first.`);
    return;
  }
  // NOTE: no check for a developer virtualenv - zero config must not need one.

  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'interlock-zerocfg-'));
  const userDataDir = path.join(scratch, 'user-data');
  const workspaceDir = path.join(scratch, 'workspace');
  fs.mkdirSync(path.join(userDataDir, 'User'), { recursive: true });
  fs.mkdirSync(workspaceDir, { recursive: true });
  fs.writeFileSync(
    path.join(workspaceDir, 'sample.txt'),
    'temporary workspace for the Interlock zero-config host test\n',
    'utf8',
  );

  // A DEFAULT profile: trust disabled for automation, telemetry off - and
  // deliberately NO interlock.* settings, exactly like a fresh install.
  fs.writeFileSync(
    path.join(userDataDir, 'User', 'settings.json'),
    JSON.stringify(
      {
        'security.workspace.trust.enabled': false,
        'update.mode': 'none',
        'telemetry.telemetryLevel': 'off',
      },
      null,
      2,
    ),
    'utf8',
  );

  console.log(`VS Code:        ${VSCODE_EXE}`);
  console.log(`Extension:      ${INSTALLED_EXT_DIR}`);
  console.log(`Workspace:      ${workspaceDir}`);
  console.log(`User data dir:  ${userDataDir}`);
  console.log(`Interlock config: (none - zero configuration)`);
  console.log('');

  try {
    await runTests({
      vscodeExecutablePath: VSCODE_EXE,
      extensionDevelopmentPath: INSTALLED_EXT_DIR,
      extensionTestsPath: path.join(__dirname, 'activation-zerocfg.js'),
      launchArgs: [
        '--user-data-dir',
        userDataDir,
        '--new-window',
        '--disable-workspace-trust',
        workspaceDir,
      ],
      // No INTERLOCK_ENGINE_ROOT / INTERLOCK_PYTHON_PATH here: the test must
      // succeed using only what the VSIX ships.
      extensionTestsEnv: (() => {
        const env = { ...process.env };
        delete env.INTERLOCK_ENGINE_ROOT;
        delete env.INTERLOCK_PYTHON_PATH;
        delete env.INTERLOCK_PYTHON;
        return env;
      })(),
    });
    console.log('zero-config host test run finished');
  } catch (error) {
    fail(`zero-config host test run failed: ${error && error.stack ? error.stack : error}`);
  } finally {
    try {
      fs.rmSync(scratch, { recursive: true, force: true });
    } catch (cleanupError) {
      console.warn(`cleanup warning: ${cleanupError.message}`);
    }
  }
}

main();
