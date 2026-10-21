/**
 * Recovery Inbox performance measurement on a large synthetic workspace.
 *
 *   node test/perf/inbox-perf.js [fileCount]
 *
 * Builds a throwaway workspace (never the real one), captures baselines for
 * every file, changes a realistic share of them, and then measures:
 *
 *   1. the local discovery phase (baseline enumeration, evidence validation,
 *      current-file hashing, workspace walk) - the part the extension runs
 *      on every open/refresh;
 *   2. the engine eligibility assessment through the real bridge
 *      (`plan-many`), so the per-file engine cost is a measured number and
 *      not an estimate.
 *
 * Everything is written under the OS temp directory and removed afterwards.
 */

'use strict';

const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const { BaselineStore } = require('../../out/src/state.js');
const { runDiscovery, probeFile, walkWorkspace } = require('../../out/src/inboxDiscovery.js');

const FILE_COUNT = Number.parseInt(process.argv[2] ?? '2000', 10);
const FOLDERS = 20;
const BYTES = 2048;

const repoRoot = path.resolve(__dirname, '..', '..', '..', '..');
const bridge = path.join(repoRoot, 'extensions', 'vscode', 'python', 'interlock_bridge.py');
const python =
  process.env.INTERLOCK_PYTHON ?? path.join(repoRoot, '.venv', 'Scripts', 'python.exe');

function sha(text) {
  return crypto.createHash('sha256').update(Buffer.from(text, 'utf8')).digest('hex');
}

function body(index) {
  const line = `export const value${index} = ${'x'.repeat(60)};\n`;
  return line.repeat(Math.ceil(BYTES / line.length)).slice(0, BYTES);
}

async function main() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'il_inbox_perf_'));
  const workspace = path.join(root, 'ws');
  const storage = path.join(root, 'storage');
  fs.mkdirSync(workspace, { recursive: true });
  const store = new BaselineStore(storage);

  const resources = [];
  for (let index = 0; index < FILE_COUNT; index += 1) {
    const folder = path.join(workspace, `pkg-${String(index % FOLDERS).padStart(2, '0')}`);
    fs.mkdirSync(folder, { recursive: true });
    const resource = `pkg-${String(index % FOLDERS).padStart(2, '0')}/file-${index}.ts`;
    fs.writeFileSync(path.join(workspace, ...resource.split('/')), body(index), 'utf8');
    resources.push(resource);
  }

  // Capture a baseline for every file (this is what "Protect Workspace" does).
  const captureStarted = Date.now();
  for (const resource of resources) {
    const content = fs.readFileSync(path.join(workspace, ...resource.split('/')));
    await store.save({
      format: 'interlock-baseline-v2',
      workspace,
      resource,
      captured_at: new Date().toISOString(),
      snapshot: {
        hash: sha(content.toString('utf8')),
        size: content.length,
        content_b64: content.toString('base64'),
      },
    });
  }
  const captureMs = Date.now() - captureStarted;

  // A realistic change set: 60% modified, 10% deleted, 30% untouched.
  let modified = 0;
  let deleted = 0;
  resources.forEach((resource, index) => {
    const absolute = path.join(workspace, ...resource.split('/'));
    if (index % 10 === 3) {
      fs.unlinkSync(absolute);
      deleted += 1;
    } else if (index % 10 < 6) {
      fs.writeFileSync(absolute, `${body(index)}\n// agent edit\n`, 'utf8');
      modified += 1;
    }
  });

  // ---- 1) the local discovery phase (no engine call) -------------------
  const localStarted = Date.now();
  const outcome = await runDiscovery({
      workspace,
      nowMs: Date.now(),
      baselines: async () =>
        (await store.list(workspace)).map((entry) => ({
          resource: entry.resource,
          file: entry.file,
          hash: entry.hash,
          size: entry.size,
          capturedAt: entry.capturedAt,
          snapshot: entry.snapshot,
        })),
      loadDoc: (resource) => store.load(workspace, resource),
      probe: (absolutePath) => probeFile(absolutePath),
      walk: () => walkWorkspace(workspace, { limit: 50_000 }),
      excludeFile: () => null,
      assess: async (candidates) =>
        candidates.map((candidate) => ({
          resource: candidate.resource,
          ok: true,
          summary: {
            would_succeed: true,
            conflict_status: 'no_conflict',
            drift_status: 'no_drift',
          },
        })),
      onProgress: () => undefined,
  });
  const localMs = Date.now() - localStarted;
  const changed = outcome.records.filter((record) => record.status === 'modified').length;
  const removed = outcome.records.filter((record) => record.status === 'deleted').length;
  const untouched = outcome.records.filter((record) => record.status === 'unchanged').length;
  const unprotected = outcome.records.filter((record) => record.kind === 'unprotected').length;

  console.log('== Recovery Inbox performance (synthetic workspace) ==');
  console.log(`workspace files            : ${FILE_COUNT} (${FOLDERS} folders, ${BYTES} bytes each)`);
  console.log(`baseline capture (${FILE_COUNT} files): ${captureMs} ms`);
  console.log(`changed on disk            : ${modified} modified, ${deleted} deleted, ${untouched} unchanged`);
  console.log(`local discovery phase      : ${localMs} ms (${(localMs / FILE_COUNT).toFixed(2)} ms/file)`);
  console.log(`files examined             : ${outcome.coverage.baselinesChecked + outcome.coverage.nonBaselineChecked}`);
  console.log(`changed vs baseline        : ${changed + removed}`);
  console.log(`files without a baseline   : ${unprotected}`);
  console.log(`walk files / skipped dirs  : ${outcome.coverage.nonBaselineChecked} / ${outcome.coverage.skippedDirectories}`);

  // ---- 2) the engine assessment through the real bridge ---------------
  if (fs.existsSync(python) && fs.existsSync(bridge)) {
    const candidates = outcome.records
      .filter((record) => record.status === 'modified')
      .slice(0, 40)
      .map((record) => ({ resource: record.resource, baseline_file: store.fileFor(workspace, record.resource) }));
    const manifest = path.join(root, 'manifest.json');
    fs.writeFileSync(
      manifest,
      JSON.stringify({ workspace, entries: candidates }),
      'utf8',
    );
    const engineStarted = Date.now();
    const stdout = execFileSync(
      python,
      [
        bridge,
        'plan-many',
        '--workspace',
        workspace,
        '--resources-file',
        manifest,
        '--engine-root',
        repoRoot,
      ],
      { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 },
    );
    const engineMs = Date.now() - engineStarted;
    const payload = JSON.parse(stdout);
    const planned = (payload.result?.entries ?? []).filter((entry) => entry.ok).length;
    console.log('');
    console.log(`engine assessment (plan-many): ${engineMs} ms for ${planned} file(s) in one process`);
    console.log(`  -> per file (incl. process start): ${(engineMs / Math.max(1, planned)).toFixed(1)} ms`);
    console.log(
      `  -> projected for ${changed + removed} changed files at 40-file chunks: ` +
        `${Math.round(((engineMs / Math.max(1, planned)) * (changed + removed)) / 1000)} s`,
    );
  } else {
    console.log('');
    console.log('engine assessment skipped: no interpreter or bridge script found');
  }

  fs.rmSync(root, { recursive: true, force: true });
  console.log('');
  console.log('temporary workspace removed');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
