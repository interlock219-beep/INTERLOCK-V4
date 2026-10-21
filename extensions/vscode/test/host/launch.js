/**
 * Launcher for the extension-host smoke test (./activation.js).
 *
 * Boots a REAL VS Code instance (the same installation as the `code` CLI)
 * against the extension **as installed from the local VSIX**, with:
 *   - an isolated user-data-dir (so the test never touches real settings),
 *   - workspace trust disabled for the test profile,
 *   - `interlock.engineRoot` / `interlock.pythonPath` pre-seeded to this
 *     checkout's engine and interpreter.
 *
 * Usage:  node test/host/launch.js
 * Exit 0 = every host check passed.
 */

'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { runTests } = require('@vscode/test-electron');

const REPO = path.resolve(__dirname, '..', '..', '..', '..');
const VSCODE_EXE =
  process.env.INTERLOCK_VSCODE_EXE ||
  path.join(
    process.env.LOCALAPPDATA || '',
    'Programs',
    'Microsoft VS Code',
    'Code.exe',
  );
const INSTALLED_EXT_DIR = path.join(
  process.env.USERPROFILE || os.homedir(),
  '.vscode',
  'extensions',
  'interlock219-beep.interlock-vscode-0.1.0',
);
const PYTHON = path.join(REPO, '.venv', 'Scripts', 'python.exe');

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
  if (!fs.existsSync(PYTHON)) {
    fail(`Engine interpreter not found: ${PYTHON}`);
    return;
  }

  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'interlock-host-'));
  const userDataDir = path.join(scratch, 'user-data');
  const workspaceDir = path.join(scratch, 'workspace');
  fs.mkdirSync(path.join(userDataDir, 'User'), { recursive: true });
  fs.mkdirSync(workspaceDir, { recursive: true });
  fs.writeFileSync(
    path.join(workspaceDir, 'sample.txt'),
    'temporary workspace for the Interlock host test\n',
    'utf8',
  );

  // Pre-seeded profile: no trust prompt, engine pointed at this checkout.
  fs.writeFileSync(
    path.join(userDataDir, 'User', 'settings.json'),
    JSON.stringify(
      {
        'security.workspace.trust.enabled': false,
        'update.mode': 'none',
        'telemetry.telemetryLevel': 'off',
        'interlock.engineRoot': REPO,
        'interlock.pythonPath': PYTHON,
        'interlock.autoDetectEngine': false,
      },
      null,
      2,
    ),
    'utf8',
  );

  console.log(`VS Code:        ${VSCODE_EXE}`);
  console.log(`Extension:      ${INSTALLED_EXT_DIR}`);
  console.log(`Engine root:    ${REPO}`);
  console.log(`Interpreter:    ${PYTHON}`);
  console.log(`Workspace:      ${workspaceDir}`);
  console.log(`User data dir:  ${userDataDir}`);
  console.log('');

  try {
    await runTests({
      vscodeExecutablePath: VSCODE_EXE,
      extensionDevelopmentPath: INSTALLED_EXT_DIR,
      extensionTestsPath: path.join(__dirname, 'activation.js'),
      launchArgs: [
        '--user-data-dir',
        userDataDir,
        '--new-window',
        '--disable-workspace-trust',
        workspaceDir,
      ],
      extensionTestsEnv: {
        ...process.env,
        INTERLOCK_ENGINE_ROOT: REPO,
        INTERLOCK_PYTHON_PATH: PYTHON,
      },
    });
    console.log('host test run finished');
  } catch (error) {
    fail(`host test run failed: ${error && error.stack ? error.stack : error}`);
  } finally {
    try {
      fs.rmSync(scratch, { recursive: true, force: true });
    } catch (cleanupError) {
      console.warn(`cleanup warning: ${cleanupError.message}`);
    }
  }
}

main();
