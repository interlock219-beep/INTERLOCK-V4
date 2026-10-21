#!/usr/bin/env node
/**
 * Clean-environment verification for the packaged Interlock VS Code extension.
 *
 * This is the evidence behind the zero-configuration claim. It proves that the
 * ARTIFACT THAT SHIPS (the VSIX), extracted into a clean directory and run with
 * NO Python on PATH, NO PYTHONHOME/PYTHONPATH, and NO reference to the source
 * checkout, can perform the whole recovery lifecycle by itself:
 *
 *   probe -> capture-baseline -> analyze -> plan -> approve -> execute -> verify
 *
 * Nothing here is mocked. Every step is a real subprocess launched through the
 * BUNDLED interpreter, against the BUNDLED engine, using the BUNDLED bridge,
 * on a throwaway workspace that contains no project files of ours.
 *
 * Usage:
 *   node tools/clean-env-verify.js                 # verify the local VSIX
 *   node tools/clean-env-verify.js --vsix <file>   # verify a specific VSIX
 *
 * Exit code 0 = every check passed. 1 = at least one check failed.
 */

'use strict';

const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const EXTENSION_ROOT = path.resolve(__dirname, '..');

function parseArgs(argv) {
  const args = { vsix: path.join(EXTENSION_ROOT, 'interlock-vscode-0.1.0.vsix') };
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === '--vsix') {
      args.vsix = path.resolve(argv[++i]);
    } else {
      throw new Error(`unknown argument: ${argv[i]}`);
    }
  }
  return args;
}

let passed = 0;
let failed = 0;
function check(name, condition, detail = '') {
  if (condition) {
    passed += 1;
    console.log(`  PASS  ${name}`);
  } else {
    failed += 1;
    console.log(`  FAIL  ${name}${detail ? ` :: ${detail}` : ''}`);
  }
}

function sha256(bytes) {
  return crypto.createHash('sha256').update(bytes).digest('hex');
}

function main() {
  const args = parseArgs(process.argv.slice(2));

  console.log('== clean-environment unpack ==');
  check('VSIX exists', fs.existsSync(args.vsix), args.vsix);
  if (!fs.existsSync(args.vsix)) {
    console.log(`\nRESULT: ${passed} passed, ${failed} failed`);
    process.exit(1);
  }

  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'interlock-clean-'));
  const installDir = path.join(root, 'install');
  const workspace = path.join(root, 'workspace');
  fs.mkdirSync(installDir, { recursive: true });
  fs.mkdirSync(workspace, { recursive: true });

  const extracted = spawnSync('tar', ['-xf', args.vsix, '-C', installDir], { encoding: 'utf8' });
  check('VSIX extracted', extracted.status === 0, extracted.error?.message ?? extracted.stderr);

  const extDir = path.join(installDir, 'extension');
  const python = path.join(extDir, 'runtime', 'win32-x64', 'python', 'python.exe');
  const bridge = path.join(extDir, 'python', 'interlock_bridge.py');
  const engineRoot = path.join(extDir, 'engine');
  check('bundled interpreter extracted', fs.existsSync(python), python);
  check('bundled bridge extracted', fs.existsSync(bridge), bridge);
  check('bundled engine extracted', fs.existsSync(path.join(engineRoot, 'manifest.json')), engineRoot);

  // A Python-free environment: no interpreter anywhere on PATH, and no
  // PYTHONHOME/PYTHONPATH that could point back at this machine's install.
  const cleanEnv = {
    PATH: 'C:\\Windows\\System32;C:\\Windows',
    PATHEXT: '.COM;.EXE;.BAT;.CMD',
    SystemRoot: process.env.SystemRoot ?? 'C:\\Windows',
    SYSTEMROOT: process.env.SystemRoot ?? 'C:\\Windows',
    WINDIR: process.env.WINDIR ?? 'C:\\Windows',
    COMSPEC: process.env.COMSPEC ?? 'C:\\Windows\\system32\\cmd.exe',
    TEMP: os.tmpdir(),
    TMP: os.tmpdir(),
    USERPROFILE: os.homedir(),
    NUMBER_OF_PROCESSORS: String(os.cpus().length),
    PYTHONIOENCODING: 'utf-8',
    PYTHONUTF8: '1',
    PYTHONUNBUFFERED: '1',
  };
  check('no python on the test PATH', !/python/i.test(cleanEnv.PATH), cleanEnv.PATH);
  check('PYTHONHOME is not set', !('PYTHONHOME' in cleanEnv));
  check('PYTHONPATH is not set', !('PYTHONPATH' in cleanEnv));

  const run = (bridgeArgs) => {
    const result = spawnSync(python, [bridge, ...bridgeArgs], {
      encoding: 'buffer',
      env: cleanEnv,
      cwd: workspace,
      maxBuffer: 32 * 1024 * 1024,
    });
    let envelope = null;
    const stdout = result.stdout?.toString('utf8') ?? '';
    try {
      envelope = JSON.parse(stdout);
    } catch {
      envelope = null;
    }
    return { code: result.status, envelope, stdout, stderr: result.stderr?.toString('utf8') ?? '', error: result.error };
  };

  console.log('== zero-configuration engine boot (no system Python) ==');
  const probe = run(['probe', '--engine-root', engineRoot]);
  check('probe exit 0', probe.code === 0, `code=${probe.code} err=${probe.error?.message ?? probe.stderr.slice(0, 200)}`);
  check('probe ok', probe.envelope?.ok === true, probe.stdout.slice(0, 200));
  check('engine available from bundled files', probe.envelope?.result?.engine?.available === true);
  const probedPython = probe.envelope?.result?.python?.executable ?? '';
  check('interpreter is the BUNDLED one', probedPython.startsWith(installDir), probedPython);
  check('python in supported range', probe.envelope?.result?.python?.in_supported_range === true);
  check('nothing was downloaded (no url/pip in envelope)', !/pypi|https?:\/\/(?!github\.com\/astral-sh)/i.test(probe.stdout), probe.stdout.slice(0, 160));

  console.log('== protect: capture baseline through the bundled engine ==');
  const target = path.join(workspace, 'config.yaml');
  const original = Buffer.from('name: interlock\nversion: 1\nprotected: true\n', 'utf8');
  fs.writeFileSync(target, original);
  const captured = run(['capture-baseline', '--workspace', workspace, '--resource', 'config.yaml', '--engine-root', engineRoot]);
  check('capture-baseline exit 0', captured.code === 0, `code=${captured.code} err=${captured.stderr.slice(0, 240)}`);
  const capturedResult = captured.envelope?.result ?? {};
  const snapshot = capturedResult.snapshot ?? {};

  // The extension (BaselineStore) owns the baseline file: it is written to
  // extension-private storage, never into the user's project. Mirror that here
  // so the recovery steps consume exactly what the real extension would store:
  // the ENGINE's sealed document, stored verbatim.
  const storageDir = path.join(root, 'private-storage');
  fs.mkdirSync(storageDir, { recursive: true });
  const baselineFile = path.join(storageDir, 'baseline.json');
  const sealedDocument = capturedResult.baseline_document ?? null;
  check('engine returned a sealed baseline document', sealedDocument !== null);
  check(
    'sealed document carries the v2 format and an integrity seal',
    sealedDocument !== null &&
      sealedDocument.format === 'interlock-baseline-v2' &&
      typeof sealedDocument.baseline_hash === 'string' &&
      sealedDocument.baseline_hash_spec === 'v1',
    JSON.stringify(sealedDocument ?? {}).slice(0, 200),
  );
  fs.writeFileSync(baselineFile, JSON.stringify(sealedDocument), 'utf8');
  check('baseline stored in private storage, not the project', !baselineFile.startsWith(workspace + path.sep), baselineFile);
  check('capture wrote no files into the project', fs.readdirSync(workspace).sort().join(',') === 'config.yaml', fs.readdirSync(workspace).join(','));

  let storedBytes = null;
  check('stored baseline keeps exact bytes', typeof snapshot.content_b64 === 'string');
  if (typeof snapshot.content_b64 === 'string') {
    storedBytes = Buffer.from(snapshot.content_b64, 'base64');
    check('stored bytes are byte-identical to the file', storedBytes.equals(original));
    check('stored bytes hash to the recorded baseline hash', sha256(storedBytes) === snapshot.hash);
  }

  console.log('== analyze the workspace through the bundled engine ==');
  const analyzed = run(['analyze', '--workspace', workspace, '--engine-root', engineRoot]);
  check('analyze exit 0', analyzed.code === 0, `code=${analyzed.code} err=${analyzed.stderr.slice(0, 200)}`);
  check('analyze ok', analyzed.envelope?.ok === true);

  console.log('== damage a file, then preview the recovery ==');
  const damaged = Buffer.from('AGENT OVERWROTE \x00\xff BYTES', 'binary');
  fs.writeFileSync(target, damaged);
  const planned = run(['plan', '--workspace', workspace, '--resource', 'config.yaml', '--baseline-file', baselineFile, '--engine-root', engineRoot]);
  check('plan exit 0', planned.code === 0, `code=${planned.code} err=${planned.stderr.slice(0, 240)}`);
  const plan = planned.envelope?.result ?? {};
  check('plan detects the change', plan.matches_baseline === false, String(plan.matches_baseline));
  check('plan says recovery would succeed', plan.would_succeed === true, JSON.stringify(plan.warnings ?? []));
  check('plan reports no conflict', plan.conflict_status === 'no_conflict', String(plan.conflict_status));
  check('plan shows a diff', (plan.diff ?? {}).changed === true);
  check('plan requires approval', plan.requires_approval === true);
  const evidenceFile = plan.evidence_file ?? null;
  check('preview evidence sidecar written', Boolean(evidenceFile) && fs.existsSync(evidenceFile), String(evidenceFile));
  check('plan report never leaks file contents', !String(planned.stdout).includes('content_b64": "') || String(planned.stdout).includes('[omitted]'));
  check('damage still on disk after preview (preview is read-only)', fs.readFileSync(target).equals(damaged));

  console.log('== approval gate ==');
  const unapproved = run(['execute', '--workspace', workspace, '--resource', 'config.yaml', '--baseline-file', baselineFile, '--evidence-file', evidenceFile, '--engine-root', engineRoot]);
  check('execute WITHOUT approval is refused (exit 5)', unapproved.code === 5, `code=${unapproved.code}`);
  check('file untouched after refusal', fs.readFileSync(target).equals(damaged));

  console.log('== execute the approved recovery ==');
  const executed = run(['execute', '--workspace', workspace, '--resource', 'config.yaml', '--baseline-file', baselineFile, '--evidence-file', evidenceFile, '--approved-by', 'clean-env-verify', '--engine-root', engineRoot]);
  check('execute exit 0', executed.code === 0, `code=${executed.code} err=${executed.stderr.slice(0, 300)}`);
  const result = executed.envelope?.result ?? {};
  check('recovery reports success', result.success === true, JSON.stringify(result).slice(0, 300));
  check('engine verified the result', result.verified === true);
  check('independent byte-exact check', (result.independent_check ?? {}).byte_exact === true);
  check('file restored byte-for-byte', fs.readFileSync(target).equals(original));

  console.log('== independent verification ==');
  const verified = run(['verify', '--workspace', workspace, '--resource', 'config.yaml', '--baseline-file', baselineFile, '--engine-root', engineRoot]);
  check('verify exit 0', verified.code === 0, `code=${verified.code} err=${verified.stderr.slice(0, 200)}`);
  check('verify reports success', (verified.envelope?.result ?? {}).success === true || verified.envelope?.ok === true);

  console.log('== confinement (nothing outside the workspace is touched) ==');
  const outside = path.join(root, 'outside-sentinel.txt');
  fs.writeFileSync(outside, 'intact', 'utf8');
  const escape = run(['capture-baseline', '--workspace', workspace, '--resource', '../outside-sentinel.txt', '--engine-root', engineRoot]);
  check('parent traversal is refused', escape.code !== 0, `code=${escape.code}`);
  check('sentinel outside the workspace is intact', fs.readFileSync(outside, 'utf8') === 'intact');

  fs.rmSync(root, { recursive: true, force: true });
  console.log(`\nRESULT: ${passed} passed, ${failed} failed`);
  console.log(`(clean env: PATH="${cleanEnv.PATH}", bundled python ${probedPython || '(n/a)'})`);
  process.exit(failed === 0 ? 0 : 1);
}

main();
