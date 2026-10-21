import * as assert from 'assert';
import * as os from 'os';
import * as path from 'path';
import {
  isAcceptableRelativeResource,
  isInside,
  resolveWithin,
  stripResourceScheme,
  toResourceId,
} from '../../src/paths';

const ROOT = path.join(path.sep === '\\' ? 'C:\\' : '/', 'workspace-root');

describe('workspace confinement pre-checks', () => {
  it('accepts ordinary relative resources', () => {
    assert.ok(isAcceptableRelativeResource('src/app.ts'));
    assert.ok(isAcceptableRelativeResource('config.yaml'));
    assert.ok(isAcceptableRelativeResource('deep/nested/file.txt'));
  });

  it('refuses parent traversal, absolute paths, UNC paths and drive letters', () => {
    assert.ok(!isAcceptableRelativeResource('../outside.txt'));
    assert.ok(!isAcceptableRelativeResource('src/../../outside.txt'));
    assert.ok(!isAcceptableRelativeResource('/etc/passwd'));
    assert.ok(!isAcceptableRelativeResource('\\\\server\\share\\file'));
    assert.ok(!isAcceptableRelativeResource('C:\\Windows\\System32\\drivers'));
    assert.ok(!isAcceptableRelativeResource(''));
    assert.ok(!isAcceptableRelativeResource('   '));
    assert.ok(!isAcceptableRelativeResource('bad\u0000file'));
  });

  it('strips file: style schemes', () => {
    assert.strictEqual(stripResourceScheme('file:src/app.ts'), 'src/app.ts');
    assert.strictEqual(stripResourceScheme('path:/a/b'), '/a/b');
    assert.strictEqual(stripResourceScheme('fs:c.txt'), 'c.txt');
    assert.strictEqual(stripResourceScheme('plain.txt'), 'plain.txt');
  });

  it('resolveWithin returns workspace-relative paths only for inside targets', () => {
    assert.deepStrictEqual(resolveWithin(ROOT, path.join(ROOT, 'a', 'b.txt')), 'a/b.txt');
    assert.strictEqual(resolveWithin(ROOT, '../escape.txt'), null);
    assert.strictEqual(resolveWithin(ROOT, path.join(ROOT, '..', 'escape.txt')), null);
    assert.strictEqual(resolveWithin(ROOT, ROOT), null); // root itself is not a file
    assert.strictEqual(resolveWithin(ROOT, ''), null);
    assert.strictEqual(resolveWithin(ROOT, '\\\\server\\share\\x'), null);
  });

  it('isInside is prefix-safe (no sibling-directory confusion)', () => {
    assert.ok(isInside('/workspace-root', '/workspace-root/file'));
    assert.ok(!isInside('/workspace-root', '/workspace-root-evil/file'));
    assert.ok(isInside('/workspace-root', '/workspace-root'));
    assert.ok(!isInside('/workspace-root', '/etc/passwd'));
  });

  it('toResourceId only emits resources inside the workspace', () => {
    const inside = toResourceId(ROOT, path.join(ROOT, 'src', 'x.ts'));
    assert.strictEqual(inside, 'file:src/x.ts');
    assert.strictEqual(toResourceId(ROOT, path.join(ROOT, '..', 'x.ts')), null);
    assert.strictEqual(toResourceId(ROOT, '/etc/passwd'), null);
  });

  it('refuses Windows drive-rooted paths even when joined on POSIX', () => {
    // A C:/ style path must not be treated as a valid relative resource.
    assert.ok(!isAcceptableRelativeResource('C:/Windows/notepad.exe'));
  });

  it('works with a real temp directory', () => {
    const realRoot = os.tmpdir();
    const rel = resolveWithin(realRoot, path.join(realRoot, 'sub', 'file.txt'));
    assert.strictEqual(rel, 'sub/file.txt');
  });
});
