#!/usr/bin/env node
/**
 * Provision the bundled Python runtime for the Interlock VS Code extension.
 *
 * This is a BUILD-TIME tool. It is never executed by the packaged extension:
 * the extension only ever looks for an already-extracted interpreter under
 * `runtime/<platform>-<arch>/` (see `src/engineRuntime.ts`). Nothing is
 * downloaded when a user installs the VSIX.
 *
 * Distribution policy enforced here:
 *   - the interpreter comes from python-build-standalone (astral-sh), a
 *     well-known builder of relocatable CPython builds;
 *   - the release tag, asset name and SHA-256 are PINNED below - a floating
 *     "latest" download is never used;
 *   - the archive's SHA-256 is verified against the value recorded here
 *     BEFORE extraction, and extraction is aborted on any mismatch;
 *   - after extraction the interpreter is executed once to prove it runs.
 *
 * Usage:
 *   node tools/provision-runtime.js                 # provision this machine
 *   node tools/provision-runtime.js --key win32-x64 # provision one target
 *   node tools/provision-runtime.js --archive <file> # verify + extract a
 *                                                    # pre-downloaded archive
 *   node tools/provision-runtime.js --verify        # check existing install
 *
 * Targets without a pinned runtime are refused with an explicit message: the
 * extension then falls back to a detected system interpreter, or reports that
 * Python is required. No platform is ever advertised as bundled unless its
 * runtime was really provisioned and verified.
 */

'use strict';

const crypto = require('crypto');
const fs = require('fs');
const https = require('https');
const path = require('path');
const { spawnSync } = require('child_process');

const RELEASE_TAG = '20261013';

/**
 * Pinned runtimes. Only platforms that are really bundled may appear here.
 * `sha256` must match the asset's entry in the upstream release's SHA256SUMS
 * manifest; verify it there before changing anything in this table.
 */
const RUNTIMES = {
  'win32-x64': {
    asset: 'cpython-3.11.17+20261013-x86_64-pc-windows-msvc-install_only.tar.gz',
    sha256: '7616ab1f74aab975bd91eb0a657a74a092a63a46cac38c5f3f9415c79fd781f5',
    interpreter: ['python', 'python.exe'],
  },
  // darwin-arm64 / linux-x64 runtimes are NOT bundled in this build. When one
  // is added here (with its own verified asset + sha256), the extension will
  // automatically prefer it for that platform - see src/engineRuntime.ts.
};

/** Directories removed after extraction: unused by a stdlib-only engine. */
const STRIP = [
  path.join('Lib', 'site-packages'),
  path.join('Lib', 'venv'),
  path.join('Lib', 'ensurepip'),
  path.join('Lib', 'idlelib'),
  'tcl',
  'include',
  'libs',
];

const EXTENSION_ROOT = path.resolve(__dirname, '..');

function parseArgs(argv) {
  const args = { key: `${process.platform}-${process.arch}`, archive: null, verify: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--key') {
      args.key = argv[++i];
    } else if (arg === '--archive') {
      args.archive = path.resolve(argv[++i]);
    } else if (arg === '--verify') {
      args.verify = true;
    } else {
      throw new Error(`unknown argument: ${arg}`);
    }
  }
  return args;
}

function sha256File(file) {
  const hash = crypto.createHash('sha256');
  hash.update(fs.readFileSync(file));
  return hash.digest('hex');
}

function download(url, destination) {
  return new Promise((resolve, reject) => {
    const follow = (current) => {
      https
        .get(current, (response) => {
          const status = response.statusCode ?? 0;
          if (status >= 300 && status < 400 && response.headers.location) {
            response.resume();
            follow(response.headers.location);
            return;
          }
          if (status !== 200) {
            response.resume();
            reject(new Error(`download failed: HTTP ${status} for ${current}`));
            return;
          }
          const out = fs.createWriteStream(destination);
          response.pipe(out);
          out.on('finish', () => out.close(() => resolve(destination)));
          out.on('error', reject);
        })
        .on('error', reject);
    };
    follow(url);
  });
}

function stripCruft(runtimeDir) {
  for (const relative of STRIP) {
    fs.rmSync(path.join(runtimeDir, relative), { recursive: true, force: true });
  }
  const removeCache = (directory) => {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const full = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === '__pycache__') {
          fs.rmSync(full, { recursive: true, force: true });
        } else {
          removeCache(full);
        }
      }
    }
  };
  removeCache(runtimeDir);
}

function verifyRuns(interpreter) {
  const result = spawnSync(interpreter, ['--version'], { encoding: 'utf8' });
  if (result.status !== 0) {
    throw new Error(`extracted interpreter failed to run: ${result.error?.message ?? result.status}`);
  }
  return `${result.stdout || result.stderr}`.trim();
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const spec = RUNTIMES[args.key];
  if (!spec) {
    console.error(
      `No pinned runtime is bundled for "${args.key}".\n` +
        `Bundled targets: ${Object.keys(RUNTIMES).join(', ') || '(none)'}.\n` +
        `On this platform the extension falls back to a detected system Python, ` +
        `or reports that Python 3.11-3.14 is required.`,
    );
    process.exit(2);
  }

  const runtimeDir = path.join(EXTENSION_ROOT, 'runtime', args.key);
  const interpreter = path.join(runtimeDir, ...spec.interpreter);

  if (args.verify) {
    if (!fs.existsSync(interpreter)) {
      console.error(`No provisioned runtime at ${interpreter}`);
      process.exit(1);
    }
    console.log(`OK ${args.key}: ${verifyRuns(interpreter)} at ${interpreter}`);
    return;
  }

  const archive =
    args.archive ??
    path.join(require('os').tmpdir(), `interlock-${spec.asset}`);
  if (!fs.existsSync(archive)) {
    const url = `https://github.com/astral-sh/python-build-standalone/releases/download/${RELEASE_TAG}/${spec.asset}`;
    console.log(`Downloading pinned runtime:\n  ${url}`);
    await download(url, archive);
  }

  const actual = sha256File(archive);
  if (actual !== spec.sha256) {
    fs.rmSync(archive, { force: true });
    console.error(
      `INTEGRITY FAILURE - refusing to extract.\n  expected sha256 ${spec.sha256}\n  actual   sha256 ${actual}`,
    );
    process.exit(1);
  }
  console.log(`Integrity OK (${actual.slice(0, 16)}...)`);

  fs.rmSync(runtimeDir, { recursive: true, force: true });
  fs.mkdirSync(runtimeDir, { recursive: true });
  const extracted = spawnSync('tar', ['-xzf', archive, '-C', runtimeDir], { encoding: 'utf8' });
  if (extracted.status !== 0) {
    throw new Error(`extraction failed: ${extracted.error?.message ?? extracted.stderr}`);
  }

  stripCruft(runtimeDir);
  const version = verifyRuns(interpreter);
  const sizeMb = (
    fs.readdirSync(runtimeDir, { recursive: true }).length && measure(runtimeDir)
  ).toFixed(1);
  console.log(`Provisioned ${args.key}: ${version}`);
  console.log(`  interpreter: ${interpreter}`);
  console.log(`  size: ${sizeMb} MB (cruft stripped)`);
}

function measure(directory) {
  let total = 0;
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full);
      } else {
        total += fs.statSync(full).size;
      }
    }
  };
  walk(directory);
  return total / (1024 * 1024);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
