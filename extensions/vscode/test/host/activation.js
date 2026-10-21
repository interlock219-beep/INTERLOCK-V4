/**
 * Extension-host smoke test.
 *
 * This module runs INSIDE the VS Code extension host against the extension
 * as installed from the local VSIX (see ../host/launch.js). It verifies, with
 * the real engine:
 *
 *   1. the extension activates;
 *   2. all contributed commands are registered;
 *   3. the sidebar view container is registered and can be opened;
 *   4. "Check Installation" reaches the REAL engine (not a stub) and reports
 *      the recorded primary platform verdict;
 *   5. "Check Status" authorizes the workspace and reports incident history
 *      honestly;
 *   6. "Analyze Workspace" runs and leaves no error behind.
 *
 * Environment supplied by the launcher:
 *   INTERLOCK_ENGINE_ROOT  - engine checkout root
 *   INTERLOCK_PYTHON_PATH  - interpreter used by the bridge
 */

'use strict';

const vscode = require('vscode');

const EXT_ID = 'interlock219-beep.interlock-vscode';

const REQUIRED_COMMANDS = [
  'interlock.checkInstallation',
  'interlock.checkStatus',
  'interlock.analyzeWorkspace',
  'interlock.protectWorkspace',
  'interlock.captureBaseline',
  'interlock.previewRecoveryPlan',
  'interlock.viewRecoveryPlan',
  'interlock.openRecoveryInbox',
  'interlock.executeRecovery',
  'interlock.verifyRecovery',
  'interlock.refresh',
  'interlock.openOutput',
  'interlock.openDocumentation',
];

const failures = [];
let passes = 0;

function check(label, condition, detail) {
  if (condition) {
    passes += 1;
    console.log(`  PASS  ${label}`);
  } else {
    failures.push(`${label} :: ${detail || ''}`);
    console.log(`  FAIL  ${label} :: ${detail || ''}`);
  }
}

async function run() {
  const engineRoot = process.env.INTERLOCK_ENGINE_ROOT;
  const pythonPath = process.env.INTERLOCK_PYTHON_PATH;
  check('launcher supplied engine root', Boolean(engineRoot), String(engineRoot));
  check('launcher supplied interpreter', Boolean(pythonPath), String(pythonPath));

  console.log('== activation ==');
  const ext = vscode.extensions.getExtension(EXT_ID);
  check('extension discovered by id', Boolean(ext), EXT_ID);
  if (!ext) {
    throw new Error(`extension ${EXT_ID} not found in the extension host`);
  }
  check(
    'extension resolves its Python bridge',
    require('fs').existsSync(
      require('path').join(ext.extensionPath, 'python', 'interlock_bridge.py'),
    ),
    ext.extensionPath,
  );

  await ext.activate();
  check('extension activated', ext.isActive === true);
  const api = ext.exports;
  check('activation returned a read-only API', Boolean(api) && typeof api.getModel === 'function');
  if (!api || typeof api.getModel !== 'function') {
    throw new Error('extension API missing; cannot assert on real state');
  }

  console.log('== contributed commands ==');
  const commands = await vscode.commands.getCommands(true);
  for (const id of REQUIRED_COMMANDS) {
    check(`command registered: ${id}`, commands.includes(id), 'not in getCommands()');
  }

  console.log('== sidebar view container ==');
  check(
    'view container command registered',
    commands.includes('workbench.view.extension.interlock'),
    'workbench.view.extension.interlock missing',
  );
  try {
    await vscode.commands.executeCommand('workbench.view.extension.interlock');
    check('sidebar view opens', true);
  } catch (error) {
    check('sidebar view opens', false, String(error));
  }

  console.log('== recovery diff plumbing (virtual documents) ==');
  // The native diff's right-hand side is a read-only virtual document. The
  // provider is registered at activation, so both schemes must resolve in a
  // real VS Code - and must never invent content before a preview proposed it.
  for (const scheme of ['interlock-proposed', 'interlock-missing']) {
    try {
      const doc = await vscode.workspace.openTextDocument(
        vscode.Uri.from({ scheme, path: '/interlock-host-probe.txt', query: 'h=probe' }),
      );
      check(`${scheme}: scheme is registered and opens`, doc.uri.scheme === scheme, doc.uri.toString());
      check(`${scheme}: no content is invented before a preview`, doc.getText() === '',
        JSON.stringify(doc.getText().slice(0, 80)));
    } catch (error) {
      check(`${scheme}: scheme is registered and opens`, false, String(error));
    }
  }

  console.log('== real engine: Check Installation ==');
  await vscode.commands.executeCommand('interlock.checkInstallation');
  let model = api.getModel();
  check('status recorded', Boolean(model.status), JSON.stringify(model.lastError || ''));
  check(
    'engine reported available',
    model.status && model.status.engineAvailable === true,
    `headline=${model.status ? model.status.headline : '(none)'} lastError=${model.lastError}`,
  );
  check(
    'engine root reported',
    Boolean(model.status && model.status.engineRoot),
    model.status ? String(model.status.engineRoot) : '(no status)',
  );
  check(
    'platform verdict recorded (extension vs engine kept apart)',
    Boolean(model.status && model.status.platformStatus),
    model.status ? model.status.platformStatus : '(none)',
  );

  console.log('== real engine: Check Status ==');
  await vscode.commands.executeCommand('interlock.checkStatus');
  model = api.getModel();
  check(
    'workspace authorized by the engine',
    model.workspaceAuthorized === true,
    `workspaceAuthorized=${model.workspaceAuthorized} lastError=${model.lastError}`,
  );
  check('workspace path recorded', Boolean(model.workspacePath), String(model.workspacePath));
  check(
    'incident history stated honestly (not invented)',
    typeof model.incidentNote === 'string' && model.incidentNote.length > 0
      ? true
      : model.incidentNote === null || model.incidentNote === undefined,
    `incidentNote=${model.incidentNote}`,
  );
  check('no error left behind after status', model.lastError === null, String(model.lastError));

  console.log('== real engine: Analyze Workspace ==');
  await vscode.commands.executeCommand('interlock.analyzeWorkspace');
  model = api.getModel();
  check(
    'analyze completed without error',
    model.lastError === null,
    `lastError=${model.lastError} lastAction=${model.lastAction}`,
  );
  check(
    'analyze recorded an action',
    typeof model.lastAction === 'string' && model.lastAction.includes('ok'),
    String(model.lastAction),
  );

  console.log('== real engine: Recovery Inbox ==');
  // The inbox runs the real discovery + engine assessment against this
  // workspace. It must open as an editor tab, receive focus, and never write
  // a workspace file while doing so.
  const folder = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
  check('workspace folder available for the inbox', Boolean(folder), String(folder && folder.uri.fsPath));
  if (folder) {
    const fs = require('fs');
    const path = require('path');
    const sample = path.join(folder.uri.fsPath, 'sample.txt');
    const before = fs.existsSync(sample) ? fs.readFileSync(sample) : Buffer.alloc(0);
    fs.writeFileSync(sample, 'changed by the agent before the inbox scan\n', 'utf8');

    const INBOX_TAB_LABEL = 'Interlock Recovery Inbox';
    const inboxTabs = () =>
      vscode.window.tabGroups.all
        .flatMap((group) => group.tabs)
        .filter((tab) => {
          if (!tab.input) {
            return false;
          }
          const viewType = typeof tab.input.viewType === 'string' ? tab.input.viewType : '';
          return viewType === 'interlock.recoveryInbox' || tab.label === INBOX_TAB_LABEL;
        });

    try {
      await vscode.commands.executeCommand('interlock.openRecoveryInbox');
    } catch (error) {
      check('inbox command runs without throwing', false, String(error));
    }
    // The scan talks to the engine; give it time to finish.
    let model2 = api.getModel();
    for (let attempt = 0; attempt < 30; attempt += 1) {
      if (typeof model2.lastAction === 'string' && model2.lastAction.includes('Recovery Inbox')) {
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
      model2 = api.getModel();
    }
    check(
      'inbox scan finished against the real engine',
      typeof model2.lastAction === 'string' && model2.lastAction.includes('Recovery Inbox'),
      `lastAction=${model2.lastAction} lastError=${model2.lastError}`,
    );
    check('inbox scan left no error behind', model2.lastError === null, String(model2.lastError));
    // The scan must not have touched the workspace file it observed.
    check(
      'inbox scan did not write to the workspace',
      fs.readFileSync(sample, 'utf8') === 'changed by the agent before the inbox scan\n',
      fs.readFileSync(sample, 'utf8').slice(0, 80),
    );

    check('the inbox opened as an editor tab', inboxTabs().length === 1, `tabs=${inboxTabs().length}`);
    const active = vscode.window.tabGroups.activeTabGroup.activeTab;
    check(
      'the inbox tab received focus',
      Boolean(active) && inboxTabs().some((tab) => tab === active),
      active ? active.label : 'no active tab',
    );

    // A second click must reuse the open tab, not stack duplicates.
    await vscode.commands.executeCommand('interlock.openRecoveryInbox');
    check(
      'a second Recover click does not open a duplicate inbox tab',
      inboxTabs().length === 1,
      `tabs=${inboxTabs().length}`,
    );

    fs.writeFileSync(sample, before);
  }

  console.log('== refresh (no engine call) ==');
  await vscode.commands.executeCommand('interlock.refresh');
  check('refresh leaves no error', api.getModel().lastError === null, String(api.getModel().lastError));

  console.log('');
  console.log(`host-test passed=${passes} failed=${failures.length}`);
  if (failures.length > 0) {
    for (const failure of failures) {
      console.log('  FAILED:', failure);
    }
    throw new Error(`${failures.length} host check(s) failed`);
  }
}

module.exports = { run };
