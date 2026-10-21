import * as assert from 'assert';
import * as fs from 'fs/promises';
import * as os from 'os';
import * as path from 'path';
import {
  BASELINE_FORMAT,
  BaselineStore,
  BaselineDocument,
  evidencePathFor,
  sameWorkspace,
} from '../../src/state';

function sampleDocument(workspace: string, resource = 'file:src/a.ts'): BaselineDocument {
  return {
    format: BASELINE_FORMAT,
    workspace,
    resource,
    captured_at: '2026-10-19T00:00:00Z',
    snapshot: { hash: 'abc123', size: 42, content_b64: 'aGVsbG8=' },
  };
}

describe('baseline store', () => {
  let root: string;
  let store: BaselineStore;
  beforeEach(async () => {
    root = await fs.mkdtemp(path.join(os.tmpdir(), 'interlock-baseline-'));
    store = new BaselineStore(root);
  });

  afterEach(async () => {
    await fs.rm(root, { recursive: true, force: true });
  });

  it('round-trips a document through save and load', async () => {
    const doc = sampleDocument('C:/ws');
    const file = await store.save(doc);
    assert.ok(file.startsWith(path.join(root, 'baselines')));
    const loaded = await store.load('C:/ws', doc.resource);
    assert.deepStrictEqual(loaded, doc);
  });

  it('stores baselines outside the workspace root', async () => {
    const workspace = path.join(root, 'user-workspace');
    await fs.mkdir(workspace, { recursive: true });
    const doc = sampleDocument(workspace);
    const file = await store.save(doc);
    assert.ok(!file.startsWith(workspace + path.sep), 'baseline must not land in the workspace');
    // And the workspace stays clean.
    const entries = await fs.readdir(workspace);
    assert.deepStrictEqual(entries, []);
  });

  it('returns null for missing, foreign, and corrupt baselines', async () => {
    assert.strictEqual(await store.load('C:/missing', 'file:x'), null);

    await store.save(sampleDocument('C:/ws', 'file:a.txt'));
    // Different workspace, same resource -> no match.
    assert.strictEqual(await store.load('C:/other-ws', 'file:a.txt'), null);
    // Different resource, same workspace -> no match.
    assert.strictEqual(await store.load('C:/ws', 'file:b.txt'), null);

    // Corrupt file content.
    const file = store.fileFor('C:/ws', 'file:a.txt');
    await fs.writeFile(file, 'not json', 'utf8');
    assert.strictEqual(await store.load('C:/ws', 'file:a.txt'), null);

    // Wrong format tag.
    await fs.writeFile(file, JSON.stringify({ format: 'other', workspace: 'C:/ws', resource: 'file:a.txt', snapshot: { hash: 'x' } }), 'utf8');
    assert.strictEqual(await store.load('C:/ws', 'file:a.txt'), null);

    // Missing snapshot hash.
    await fs.writeFile(file, JSON.stringify({ format: BASELINE_FORMAT, workspace: 'C:/ws', resource: 'file:a.txt', snapshot: {} }), 'utf8');
    assert.strictEqual(await store.load('C:/ws', 'file:a.txt'), null);
  });

  it('derives a stable, collision-resistant file key', () => {
    const a = BaselineStore.key('C:/ws', 'file:a.txt');
    const b = BaselineStore.key('C:/ws', 'file:a.txt');
    const c = BaselineStore.key('C:/ws', 'file:b.txt');
    const d = BaselineStore.key('C:/ws2', 'file:a.txt');
    assert.strictEqual(a, b);
    assert.notStrictEqual(a, c);
    assert.notStrictEqual(a, d);
    assert.match(a, /^[0-9a-f]{64}$/);
    // Keys cannot be path-shaped (no traversal via resource names).
    assert.ok(!a.includes('/') && !a.includes('\\'));
  });

  it('lists summaries sorted by resource and skips foreign entries', async () => {
    await store.save(sampleDocument('C:/ws', 'file:z.txt'));
    await store.save(sampleDocument('C:/ws', 'file:a.txt'));
    await fs.writeFile(
      store.fileFor('C:/ws', 'file:bad.txt'),
      JSON.stringify({ format: 'wrong' }),
      'utf8',
    );
    const summaries = await store.summaries();
    assert.deepStrictEqual(
      summaries.map((s) => s.resource),
      ['file:a.txt', 'file:z.txt'],
    );
    assert.strictEqual(summaries[0].hash, 'abc123');
    assert.strictEqual(summaries[0].size, 42);
  });

  it('returns an empty summary list when nothing exists yet', async () => {
    assert.deepStrictEqual(await store.summaries(), []);
  });

  it('removes a baseline together with its evidence sidecar', async () => {
    const doc = sampleDocument('C:/ws', 'file:a.txt');
    const file = await store.save(doc);
    await fs.writeFile(evidencePathFor(file), '{"ok":true}', 'utf8');

    await store.remove('C:/ws', doc.resource);
    await assert.rejects(fs.access(file));
    await assert.rejects(fs.access(evidencePathFor(file)));
    assert.strictEqual(await store.load('C:/ws', doc.resource), null);
    // Removing again is a no-op, not an error.
    await store.remove('C:/ws', doc.resource);
  });

  it('places the evidence sidecar next to the baseline file', async () => {
    const doc = sampleDocument('C:/ws');
    const file = await store.save(doc);
    assert.strictEqual(evidencePathFor(file), `${file}.evidence.json`);
  });
});

describe('baseline store - the workspace path has one spelling', () => {
  it('keys a workspace the same way the engine does (Windows drive letter)', () => {
    // VS Code hands out a lower-case drive letter, the engine resolves the
    // same folder with an upper-case one. Both must key the same baseline.
    const lower = 'c:\\work\\dir';
    const upper = 'C:\\work\\dir';
    assert.strictEqual(
      BaselineStore.key(lower, 'src/app.ts'),
      BaselineStore.key(upper, 'src/app.ts'),
      'the same folder must produce the same baseline key',
    );
  });

  it('keeps different workspaces apart', () => {
    assert.notStrictEqual(
      BaselineStore.key('C:\\work\\a', 'src/app.ts'),
      BaselineStore.key('C:\\work\\b', 'src/app.ts'),
    );
  });

  it('recognises the same workspace written with a different drive letter case', () => {
    assert.ok(sameWorkspace('c:\\work\\dir', 'C:\\work\\dir'));
    assert.ok(!sameWorkspace('C:\\work\\dir', 'C:\\work\\other'));
    assert.ok(!sameWorkspace(null, 'C:\\work\\dir'));
  });
});
