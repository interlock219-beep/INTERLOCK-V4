/**
 * Build the engine bundle that ships inside the VSIX.
 *
 * Strategy: the recovery engine's runtime import closure (the six modules the
 * bridge imports, plus everything they reach) is pure standard-library Python.
 * We copy exactly that closure from the canonical engine source into
 * `engine/` and write a deterministic SHA-256 manifest, so the installer can
 * verify every byte it is asked to trust before any of it is used.
 *
 * Deterministic by design: no timestamps, sorted inputs, stable JSON. Running
 * it twice on the same engine source produces identical bytes.
 *
 * Usage: node tools/build-engine-bundle.js
 * Exit 0 = bundle written (third-party import report printed for review).
 */

'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const REPO = path.resolve(__dirname, '..', '..', '..');
const EXT = path.resolve(__dirname, '..');
const ENGINE_OUT = path.join(EXT, 'engine');

/** The exact engine modules `python/interlock_bridge.py` imports. */
const ROOTS = [
  'app',
  'app.domain.entities.protected_action',
  'app.infrastructure.recovery.filesystem_recovery_adapter',
  'sdk.workspace_protection.path_security',
  'app.domain.entities.surgical_recovery_types',
  'app.domain.services.evidence_hash',
];

const BUNDLE_FORMAT = 'interlock-engine-bundle-v1';

// ------------------------------------------------------------------ scanning

function readSource(file) {
  try {
    return fs.readFileSync(file, 'utf8');
  } catch {
    return fs.readFileSync(file, 'latin1');
  }
}

/** Split a source file into (statement, modulePart) pairs for import lines. */
function importClauses(source) {
  const clauses = [];
  const lines = source.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];
    // Join explicit line continuations so `import a, \` + `b` is one clause.
    while (/\\\s*$/.test(line) && i + 1 < lines.length) {
      line = line.replace(/\\\s*$/, '') + lines[i + 1];
      i++;
    }
    const from = /^\s*from\s+([.\w]+)\s+import\s+([\s\S]*)$/.exec(line);
    if (from) {
      clauses.push({ kind: 'from', module: from[1], rest: from[2] });
      continue;
    }
    const imp = /^\s*import\s+([^\s#]+)/.exec(line);
    if (imp) {
      clauses.push({ kind: 'import', module: imp[1] });
    }
  }
  return clauses;
}

/**
 * Python standard-library top-level names (Python 3.11, plus names added by
 * 3.12-3.14). The bundle tool reports any import outside this set; a platform
 * module like `win32security` (pywin32) is expected and guarded at runtime,
 * which the bare-venv integration test proves by running every command.
 */
const PY_STDLIB = new Set(
  (
    '__future__ _abc _aix_support _ast _asyncio _bisect _blake2 _bootsubprocess _bz2 ' +
    '_codecs _codecs_cn _codecs_hk _codecs_iso2022 _codecs_jp _codecs_kr _codecs_tw ' +
    '_collections _collections_abc _compat_pickle _compression _contextvars _crypt _csv ' +
    '_ctypes _curses _curses_panel _datetime _dbm _decimal _elementtree _frozen_importlib ' +
    '_frozen_importlib_external _functools _gdbm _hashlib _heapq _imp _io _json _locale ' +
    '_lsprof _lzma _markupbase _md5 _msi _multibytecodec _multiprocessing _opcode _operator ' +
    '_osx_support _overlapped _pickle _posixshmem _posixsubprocess _py_abc _pydecimal _pyio ' +
    '_queue _random _scproxy _sha1 _sha256 _sha3 _sha512 _signal _sitebuiltins _socket ' +
    '_sqlite3 _sre _ssl _stat _statistics _string _strptime _struct _symtable _thread ' +
    '_threading_local _tkinter _tokenize _tracemalloc _typing _uuid _warnings _weakref ' +
    '_weakrefset _winapi _zoneinfo abc aifc antigravity argparse array ast asynchat asyncio ' +
    'asyncore atexit audioop base64 bdb binascii bisect builtins bz2 cProfile calendar cgi ' +
    'cgitb chunk cmath cmd code codecs codeop collections colorsys compileall concurrent ' +
    'configparser contextlib contextvars copy copyreg crypt csv ctypes curses dataclasses ' +
    'datetime dbm decimal difflib dis distutils doctest email encodings ensurepip enum errno ' +
    'faulthandler fcntl filecmp fileinput fnmatch fractions ftplib functools gc genericpath ' +
    'getopt getpass gettext glob graphlib grp gzip hashlib heapq hmac html http idlelib ' +
    'imaplib imghdr imp importlib inspect io ipaddress itertools json keyword lib2to3 ' +
    'linecache locale logging lzma mailbox mailcap marshal math mimetypes mmap modulefinder ' +
    'msilib msvcrt multiprocessing netrc nis nntplib nt ntpath nturl2path numbers opcode ' +
    'operator optparse os ossaudiodev pathlib pdb pickle pickletools pipes pkgutil platform ' +
    'plistlib poplib posix posixpath pprint profile pstats pty pwd py_compile pyclbr pydoc ' +
    'pydoc_data pyexpat queue quopri random re readline reprlib resource rlcompleter runpy ' +
    'sched secrets select selectors shelve shlex shutil signal site smtpd smtplib sndhdr ' +
    'socket socketserver spwd sqlite3 sre_compile sre_constants sre_parse ssl stat statistics ' +
    'string stringprep struct subprocess sunau symtable sys sysconfig syslog tabnanny tarfile ' +
    'telnetlib tempfile termios textwrap this threading time timeit tkinter token tokenize ' +
    'tomllib trace traceback tracemalloc tty turtle turtledemo types typing unicodedata ' +
    'unittest urllib uu uuid venv warnings wave weakref webbrowser winreg winsound wsgiref ' +
    'xdrlib xml xmlrpc zipapp zipfile zipimport zlib zoneinfo ' +
    // names added by Python 3.12 - 3.14
    'compression copytypes annotationlib interpreters'
  ).split(/\s+/),
);

function isStdlib(name) {
  return PY_STDLIB.has(name);
}

/**
 * Resolve a dotted module name (as written in a file) to a source file path
 * inside the repo, or null when it does not name a module (attribute import).
 */
function resolveModuleFile(mod) {
  const rel = mod.split('.').join(path.sep);
  const asFile = path.join(REPO, `${rel}.py`);
  if (fs.existsSync(asFile)) {
    return asFile;
  }
  const asPkg = path.join(REPO, rel, '__init__.py');
  if (fs.existsSync(asPkg)) {
    return asPkg;
  }
  return null;
}

/** Ancestor package `__init__.py` files that execute before `mod` loads. */
function ancestorInitFiles(mod) {
  const parts = mod.split('.');
  const files = [];
  for (let i = 1; i < parts.length; i++) {
    const pkg = parts.slice(0, i).join('.');
    const file = resolveModuleFile(pkg);
    if (file && file.endsWith(`${path.sep}__init__.py`)) {
      files.push(file);
    }
  }
  return files;
}

/** Resolve `from . import x` / `from .y import z` relative to a file. */
function resolveRelative(clause, fromFile) {
  const dir = path.dirname(fromFile);
  const parts = dir.split(path.sep).filter(Boolean);
  const level = (clause.module.match(/\./g) || []).length + 1;
  const base = parts.slice(0, parts.length - (level - 1));
  const tail = clause.module.replace(/^\.+/, '');
  const absolute = [...base, ...(tail ? tail.split('.') : [])].join('.');
  return absolute || null;
}

function main(options = {}) {
  const write = options.write !== false;
  if (!fs.existsSync(path.join(REPO, 'pyproject.toml'))) {
    console.error('engine source not found (no pyproject.toml at repo root)');
    process.exit(1);
  }

  const queue = [];
  const reachedFiles = new Set();
  const thirdParty = new Map(); // top-level name -> first importer
  const unscanned = [];

  const pushModule = (mod, importer) => {
    const file = resolveModuleFile(mod);
    if (file) {
      for (const init of ancestorInitFiles(mod)) {
        if (!reachedFiles.has(init)) {
          reachedFiles.add(init);
          queue.push(init);
        }
      }
      if (!reachedFiles.has(file)) {
        reachedFiles.add(file);
        queue.push(file);
      }
      return;
    }
    const top = mod.split('.')[0];
    if (isStdlib(top) || top === 'app' || top === 'sdk') {
      return;
    }
    // A repo-local top-level module would be bundled too (it lives beside
    // `app`/`sdk` under the same engine root); anything else is third-party
    // and is reported for review - the bare-venv integration test is the
    // arbiter of whether the closure really can live without it.
    if (resolveModuleFile(top)) {
      pushModule(top, importer);
      return;
    }
    if (!thirdParty.has(top)) {
      thirdParty.set(top, importer);
    }
  };

  for (const root of ROOTS) {
    pushModule(root, '(bridge root)');
  }

  while (queue.length > 0) {
    const file = queue.pop();
    const relFromRepo = path.relative(REPO, file);
    let clauses;
    try {
      clauses = importClauses(readSource(file));
    } catch (error) {
      unscanned.push(`${relFromRepo}: ${error.message}`);
      continue;
    }
    for (const clause of clauses) {
      if (clause.kind === 'import') {
        pushModule(clause.module, relFromRepo);
        continue;
      }
      let mod = clause.module;
      if (mod.startsWith('.')) {
        const absolute = resolveRelative(clause, file);
        if (!absolute) {
          continue;
        }
        mod = absolute;
      }
      pushModule(mod, relFromRepo);
      // `from a.b import c` may name a submodule; include it when it exists.
      const names = clause.rest
        .split(/[(),]/)
        .map((part) => part.trim().split(/\s+as\s+/)[0])
        .filter((part) => /^[A-Za-z_]\w*$/.test(part));
      for (const name of names) {
        pushModule(`${mod}.${name}`, relFromRepo);
      }
    }
  }

  if (unscanned.length > 0) {
    console.error('failed to scan:', unscanned);
    process.exit(1);
  }

  // ------------------------------------------------------------- copy + hash
  const files = [...reachedFiles].sort();
  if (files.length === 0) {
    console.error('closure resolved to zero files - refusing to write a bundle');
    process.exit(1);
  }

  if (write) {
    fs.rmSync(ENGINE_OUT, { recursive: true, force: true });
  }
  const manifest = {};
  let totalBytes = 0;
  for (const source of files) {
    const rel = path.relative(REPO, source).split(path.sep).join('/');
    const bytes = fs.readFileSync(source);
    if (write) {
      const target = path.join(ENGINE_OUT, rel);
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.writeFileSync(target, bytes);
    }
    manifest[rel] = crypto.createHash('sha256').update(bytes).digest('hex');
    totalBytes += bytes.length;
  }

  const pyproject = fs.readFileSync(path.join(REPO, 'pyproject.toml'), 'utf8');
  const start = pyproject.indexOf('[project]');
  const nextSection = start >= 0 ? pyproject.indexOf('\n[', start + 1) : -1;
  const projectSection =
    start >= 0 ? pyproject.slice(start, nextSection === -1 ? pyproject.length : nextSection) : '';
  const version = /^\s*version\s*=\s*"([^"]+)"/m.exec(projectSection);
  const requiresPython = /requires-python\s*=\s*"([^"]+)"/.exec(projectSection);
  if (!version) {
    console.error('could not read engine version from pyproject.toml');
    process.exit(1);
  }

  const treeLines = Object.keys(manifest)
    .sort()
    .map((rel) => `${rel}\n${manifest[rel]}\n`)
    .join('');
  const treeSha256 = crypto.createHash('sha256').update(treeLines, 'utf8').digest('hex');

  const bundle = {
    format: BUNDLE_FORMAT,
    engineVersion: version[1],
    requiresPython: requiresPython ? requiresPython[1] : '>=3.11,<3.15',
    fileCount: Object.keys(manifest).length,
    treeSha256,
    files: manifest,
  };
  if (write) {
    fs.writeFileSync(
      path.join(ENGINE_OUT, 'manifest.json'),
      `${JSON.stringify(bundle, null, 2)}\n`,
      'utf8',
    );
  }

  console.log(
    `engine bundle: ${bundle.fileCount} files, ${(totalBytes / 1024).toFixed(0)} KB, ` +
      `engine ${bundle.engineVersion}, tree ${treeSha256.slice(0, 16)}...`,
  );
  if (thirdParty.size > 0) {
    console.log('third-party imports reached by the closure (review):');
    for (const [name, importer] of [...thirdParty].sort()) {
      console.log(`  - ${name}  (from ${importer})`);
    }
  } else {
    console.log('third-party imports reached by the closure: none (standard library only)');
  }
  return { bundle, treeSha256, manifest };
}

/**
 * Verify that the committed bundle matches the canonical engine source.
 *
 * The bundle is what the extension actually ships, so a stale bundle means
 * the extension runs different code than the repository. The check is
 * read-only: it never rewrites `engine/`.
 */
function verify() {
  const manifestPath = path.join(ENGINE_OUT, 'manifest.json');
  if (!fs.existsSync(manifestPath)) {
    console.error(
      'engine bundle is missing: run `node tools/build-engine-bundle.js` and commit the result',
    );
    process.exit(1);
  }
  const committed = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  const rebuilt = main({ write: false });
  const committedFiles = committed.files || {};
  const rebuiltFiles = rebuilt.manifest;
  const problems = [];
  for (const rel of Object.keys(committedFiles)) {
    if (!(rel in rebuiltFiles)) {
      problems.push(`${rel}: committed but no longer part of the engine closure`);
    } else if (committedFiles[rel] !== rebuiltFiles[rel]) {
      problems.push(`${rel}: committed copy differs from the canonical source`);
    }
  }
  for (const rel of Object.keys(rebuiltFiles)) {
    if (!(rel in committedFiles)) {
      problems.push(`${rel}: part of the engine closure but missing from the committed bundle`);
    }
  }
  if (committed.treeSha256 !== rebuilt.treeSha256) {
    problems.push(
      `tree hash differs (committed ${String(committed.treeSha256).slice(0, 16)}..., ` +
        `rebuilt ${rebuilt.treeSha256.slice(0, 16)}...)`,
    );
  }
  if (problems.length > 0) {
    console.error('engine bundle is STALE - the extension would ship different code:');
    for (const problem of problems) {
      console.error(`  - ${problem}`);
    }
    console.error('Fix: node tools/build-engine-bundle.js && commit extensions/vscode/engine/');
    process.exit(1);
  }
  console.log(
    `engine bundle verified: ${rebuilt.bundle.fileCount} files, tree ` +
      `${rebuilt.treeSha256.slice(0, 16)}... matches the canonical engine source`,
  );
}

if (process.argv.includes('--verify')) {
  verify();
} else {
  main();
}
