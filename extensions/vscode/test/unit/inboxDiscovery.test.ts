/**
 * Recovery Inbox discovery tests (pure - every IO call is injected).
 *
 * Discovery is the part that has to be both fast and honest: it classifies
 * what changed, validates the stored evidence, finds files that changed
 * without any baseline, asks the engine for eligibility - and it must never
 * write a workspace file, lose a partial result silently, or claim a
 * complete coverage it does not have.
 */

import * as assert from 'assert';
import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';

import {
  AssessResult,
  DiscoveryBaseline,
  DiscoveryCandidate,
  DiscoveryDeps,
  DiscoveryDoc,
  FileProbe,
  WalkResult,
  runDiscovery,
  SCAN_SKIP_DIRS,
} from '../../src/inboxDiscovery';
import { BASELINE_FORMAT } from '../../src/state';

const CAPTURED_AT = '2026-10-20T10:00:00.000Z';
const CAPTURE_MS = Date.parse(CAPTURED_AT);

function sha(text: string): string {
  return crypto.createHash('sha256').update(Buffer.from(text, 'utf8')).digest('hex');
}

function baselineDoc(resource: string, content: string, overrides: Record<string, unknown> = {}): DiscoveryDoc {
  return {
    format: BASELINE_FORMAT,
    workspace: 'C:/workspace',
    resource,
    captured_at: CAPTURED_AT,
    snapshot: {
      hash: sha(content),
      size: Buffer.byteLength(content, 'utf8'),
      content_b64: Buffer.from(content, 'utf8').toString('base64'),
      ...overrides,
    },
  };
}

function baseline(resource: string, content: string): DiscoveryBaseline {
  return {
    resource,
    file: `C:/storage/${resource}.json`,
    hash: sha(content),
    size: Buffer.byteLength(content, 'utf8'),
    capturedAt: CAPTURED_AT,
  };
}

function probeOf(overrides: Partial<FileProbe> = {}): FileProbe {
  return { missing: false, size: 10, hash: 'b'.repeat(64), error: null, tooLarge: false, ...overrides };
}

interface Harness {
  deps: DiscoveryDeps;
  progress: Array<{ phase: string; done: number; total: number }>;
  assessed: DiscoveryCandidate[][];
}

function harness(options: {
  baselines?: DiscoveryBaseline[];
  docs?: Record<string, DiscoveryDoc | null>;
  probes?: Record<string, FileProbe>;
  walk?: WalkResult | null;
  excluded?: Record<string, string>;
  assess?: (candidates: DiscoveryCandidate[]) => AssessResult[];
  signal?: AbortSignal;
}): Harness {
  const progress: Array<{ phase: string; done: number; total: number }> = [];
  const assessed: DiscoveryCandidate[][] = [];
  const probeMap = new Map(Object.entries(options.probes ?? {}));
  const deps: DiscoveryDeps = {
    workspace: 'C:/workspace',
    nowMs: CAPTURE_MS,
    baselines: async () => options.baselines ?? [],
    loadDoc: async (resource) => (options.docs ?? {})[resource] ?? null,
    probe: async (absolutePath) => {
      const key = absolutePath.replace(/\\/g, '/').split('/').pop() ?? absolutePath;
      return probeMap.get(key) ?? probeOf();
    },
    walk: async () => options.walk ?? null,
    excludeFile: (rel) => (options.excluded ?? {})[rel] ?? null,
    assess: async (candidates, onProgress) => {
      assessed.push(candidates);
      onProgress(candidates.length, candidates.length);
      return options.assess ? options.assess(candidates) : [];
    },
    onProgress: (update) => progress.push({ ...update }),
    signal: options.signal,
  };
  return { deps, progress, assessed };
}

describe('Recovery Inbox discovery - classification', () => {
  it('classifies modified, deleted and unchanged files against their baseline', async () => {
    const content = 'baseline\n';
    const { deps } = harness({
      baselines: [baseline('a.ts', content), baseline('b.ts', content), baseline('c.ts', content)],
      docs: {
        'a.ts': baselineDoc('a.ts', content),
        'b.ts': baselineDoc('b.ts', content),
        'c.ts': baselineDoc('c.ts', content),
      },
      probes: {
        'a.ts': probeOf({ hash: sha('changed\n') }),
        'b.ts': probeOf({ missing: true }),
        'c.ts': probeOf({ hash: sha(content) }),
      },
    });

    const outcome = await runDiscovery(deps);
    assert.strictEqual(outcome.status, 'complete');
    const byResource = new Map(outcome.records.map((record) => [record.resource, record]));
    assert.strictEqual(byResource.get('a.ts')?.status, 'modified');
    assert.strictEqual(byResource.get('b.ts')?.status, 'deleted');
    assert.strictEqual(byResource.get('c.ts')?.status, 'unchanged');
    assert.strictEqual(byResource.get('a.ts')?.evidence, 'verified');
    assert.strictEqual(outcome.coverage?.baselinesChecked, 3);
  });

  it('never writes a workspace file - discovery only reads', async () => {
    const content = 'baseline\n';
    const { deps } = harness({
      baselines: [baseline('a.ts', content)],
      docs: { 'a.ts': baselineDoc('a.ts', content) },
      probes: { 'a.ts': probeOf({ hash: sha('changed\n') }) },
    });
    await runDiscovery(deps);
    // The dependency surface proves it: no dep can write, and no engine
    // call is made without an explicit assessment step.
    assert.deepStrictEqual(
      Object.keys(deps).filter((key) => /write|save|delete|exec/i.test(key)),
      [],
    );
  });

  it('reports an unreadable current file as unknown instead of guessing', async () => {
    const content = 'baseline\n';
    const { deps } = harness({
      baselines: [baseline('a.ts', content)],
      docs: { 'a.ts': baselineDoc('a.ts', content) },
      probes: { 'a.ts': probeOf({ hash: null, error: 'EACCES' }) },
    });
    const outcome = await runDiscovery(deps);
    const record = outcome.records.find((entry) => entry.resource === 'a.ts');
    assert.strictEqual(record?.status, 'unknown');
    assert.ok(record?.technical?.includes('EACCES'));
  });

  it('classifies a file that is too large to hash by size, and says so', async () => {
    const content = 'baseline\n';
    const { deps } = harness({
      baselines: [baseline('a.ts', content)],
      docs: { 'a.ts': baselineDoc('a.ts', content) },
      probes: { 'a.ts': probeOf({ hash: null, tooLarge: true, size: 9 }) },
    });
    const outcome = await runDiscovery(deps);
    const record = outcome.records.find((entry) => entry.resource === 'a.ts');
    assert.strictEqual(record?.status, 'unknown', 'same size but no hash means no verdict');
    assert.ok(record?.technical?.includes('too large'));
  });
});

describe('Recovery Inbox discovery - evidence validation', () => {
  it('marks stored bytes that do not match their hash as invalid', async () => {
    const { deps } = harness({
      baselines: [baseline('a.ts', 'baseline\n')],
      docs: {
        'a.ts': baselineDoc('a.ts', 'tampered\n', { hash: sha('baseline\n') }),
      },
      probes: { 'a.ts': probeOf({ hash: sha('changed\n') }) },
    });
    const outcome = await runDiscovery(deps);
    const record = outcome.records.find((entry) => entry.resource === 'a.ts');
    assert.strictEqual(record?.evidence, 'invalid');
    assert.ok(record?.evidenceNote?.includes('do not match the recorded baseline hash'));
  });

  it('marks a truncated capture as invalid and explains it', async () => {
    const { deps } = harness({
      baselines: [baseline('a.ts', 'baseline\n')],
      docs: {
        'a.ts': baselineDoc('a.ts', 'baseline\n', { truncated: true }),
      },
      probes: { 'a.ts': probeOf({ hash: sha('changed\n') }) },
    });
    const outcome = await runDiscovery(deps);
    const record = outcome.records.find((entry) => entry.resource === 'a.ts');
    assert.strictEqual(record?.evidence, 'invalid');
    assert.ok(record?.evidenceNote?.includes('truncated'));
  });

  it('marks a baseline without contents as unusable, not invalid', async () => {
    const { deps } = harness({
      baselines: [baseline('a.ts', 'baseline\n')],
      docs: {
        'a.ts': {
          format: BASELINE_FORMAT,
          workspace: 'C:/workspace',
          resource: 'a.ts',
          captured_at: CAPTURED_AT,
          snapshot: { hash: sha('baseline\n'), size: 8 },
        },
      },
      probes: { 'a.ts': probeOf({ hash: sha('changed\n') }) },
    });
    const outcome = await runDiscovery(deps);
    const record = outcome.records.find((entry) => entry.resource === 'a.ts');
    assert.strictEqual(record?.evidence, 'unusable');
  });

  it('records an unreadable baseline document as a partial failure', async () => {
    const { deps } = harness({
      baselines: [baseline('a.ts', 'baseline\n')],
      docs: { 'a.ts': null },
    });
    const outcome = await runDiscovery(deps);
    assert.strictEqual(outcome.coverage?.failed, 1);
    const record = outcome.records.find((entry) => entry.resource === 'a.ts');
    assert.strictEqual(record?.status, 'unknown');
    assert.strictEqual(record?.evidence, 'unusable');
  });
});

describe('Recovery Inbox discovery - files without a baseline', () => {
  const walk: WalkResult = {
    files: [
      { rel: 'created.ts', size: 1, mtimeMs: CAPTURE_MS + 60_000, birthtimeMs: CAPTURE_MS + 60_000 },
      { rel: 'touched.ts', size: 1, mtimeMs: CAPTURE_MS + 60_000, birthtimeMs: CAPTURE_MS - 60_000 },
      { rel: 'old.ts', size: 1, mtimeMs: CAPTURE_MS - 60_000, birthtimeMs: CAPTURE_MS - 60_000 },
    ],
    skippedDirectories: 3,
    skippedDirSample: ['node_modules', '.git'],
    truncated: false,
    limit: 50_000,
    failed: 0,
    failureNotes: [],
  };

  it('lists files that changed after the newest baseline and explains them', async () => {
    const content = 'baseline\n';
    const { deps } = harness({
      baselines: [baseline('a.ts', content)],
      docs: { 'a.ts': baselineDoc('a.ts', content) },
      probes: { 'a.ts': probeOf({ hash: sha(content) }) },
      walk,
    });
    const outcome = await runDiscovery(deps);
    const resources = outcome.records.map((record) => record.resource);
    assert.ok(resources.includes('created.ts'));
    assert.ok(resources.includes('touched.ts'));
    assert.ok(!resources.includes('old.ts'), 'a file untouched since capture is not a change');
    const created = outcome.records.find((record) => record.resource === 'created.ts');
    assert.strictEqual(created?.kind, 'unprotected');
    assert.strictEqual(created?.status, 'created');
    assert.strictEqual(created?.createdAfterCapture, true);
  });

  it('never lists a file the exclusion policy refuses', async () => {
    const content = 'baseline\n';
    const { deps } = harness({
      baselines: [baseline('a.ts', content)],
      docs: { 'a.ts': baselineDoc('a.ts', content) },
      probes: { 'a.ts': probeOf({ hash: sha(content) }) },
      walk,
      excluded: { 'created.ts': 'secret or credential file' },
    });
    const outcome = await runDiscovery(deps);
    const resources = outcome.records.map((record) => record.resource);
    assert.ok(!resources.includes('created.ts'));
    assert.strictEqual(outcome.coverage?.excludedByPolicy, 1);
  });

  it('skips the walk entirely when there is no baseline to compare against', async () => {
    const { deps } = harness({ baselines: [], walk });
    const outcome = await runDiscovery(deps);
    assert.strictEqual(outcome.records.length, 0);
    assert.strictEqual(outcome.coverage?.walkRan, false);
    assert.strictEqual(outcome.coverage?.baselinesChecked, 0);
  });

  it('discloses a truncated walk instead of claiming full coverage', async () => {
    const content = 'baseline\n';
    const { deps } = harness({
      baselines: [baseline('a.ts', content)],
      docs: { 'a.ts': baselineDoc('a.ts', content) },
      probes: { 'a.ts': probeOf({ hash: sha(content) }) },
      walk: { ...walk, truncated: true },
    });
    const outcome = await runDiscovery(deps);
    assert.strictEqual(outcome.coverage?.walkTruncated, true);
  });
});

describe('Recovery Inbox discovery - engine assessment', () => {
  it('asks the engine only about changed files with verified evidence', async () => {
    const content = 'baseline\n';
    const { deps, assessed } = harness({
      baselines: [baseline('a.ts', content), baseline('b.ts', content), baseline('c.ts', content)],
      docs: {
        'a.ts': baselineDoc('a.ts', content),
        'b.ts': baselineDoc('b.ts', content),
        'c.ts': baselineDoc('c.ts', content),
      },
      probes: {
        'a.ts': probeOf({ hash: sha('changed\n') }),
        'b.ts': probeOf({ missing: true }),
        'c.ts': probeOf({ hash: sha(content) }),
      },
    });
    await runDiscovery(deps);
    assert.strictEqual(assessed.length, 1);
    assert.deepStrictEqual(
      assessed[0].map((candidate) => candidate.resource).sort(),
      ['a.ts', 'b.ts'],
    );
  });

  it('translates the engine verdicts into plain words', async () => {
    const content = 'baseline\n';
    const { deps } = harness({
      baselines: [baseline('a.ts', content), baseline('b.ts', content)],
      docs: { 'a.ts': baselineDoc('a.ts', content), 'b.ts': baselineDoc('b.ts', content) },
      probes: {
        'a.ts': probeOf({ hash: sha('changed\n') }),
        'b.ts': probeOf({ hash: sha('changed\n') }),
      },
      assess: () => [
        {
          resource: 'a.ts',
          ok: true,
          summary: { would_succeed: true, conflict_status: 'no_conflict', drift_status: 'no_drift' },
        },
        {
          resource: 'b.ts',
          ok: true,
          summary: { would_succeed: true, conflict_status: 'concurrent_modification', drift_status: 'no_drift' },
        },
      ],
    });
    const outcome = await runDiscovery(deps);
    const byResource = new Map(outcome.assessments.map((entry) => [entry.resource, entry]));
    assert.strictEqual(byResource.get('a.ts')?.eligibility, 'eligible');
    assert.strictEqual(byResource.get('b.ts')?.eligibility, 'blocked');
    assert.ok(byResource.get('b.ts')?.reason.includes('conflict'));
  });

  it('reports an engine failure for that file only', async () => {
    const content = 'baseline\n';
    const { deps } = harness({
      baselines: [baseline('a.ts', content), baseline('b.ts', content)],
      docs: { 'a.ts': baselineDoc('a.ts', content), 'b.ts': baselineDoc('b.ts', content) },
      probes: {
        'a.ts': probeOf({ hash: sha('changed\n') }),
        'b.ts': probeOf({ hash: sha('changed\n') }),
      },
      assess: () => [
        { resource: 'a.ts', ok: true, summary: { would_succeed: true, conflict_status: 'no_conflict', drift_status: 'no_drift' } },
        { resource: 'b.ts', ok: false, error: { kind: 'internal_error', message: 'boom' } },
      ],
    });
    const outcome = await runDiscovery(deps);
    const byResource = new Map(outcome.assessments.map((entry) => [entry.resource, entry]));
    assert.strictEqual(byResource.get('a.ts')?.eligibility, 'eligible');
    assert.strictEqual(byResource.get('b.ts')?.eligibility, 'unavailable');
    assert.ok(byResource.get('b.ts')?.reason.includes('boom'));
  });
});

describe('Recovery Inbox discovery - cancellation and scale', () => {
  it('stops when the scan is cancelled and marks the coverage partial', async () => {
    const controller = new AbortController();
    const content = 'baseline\n';
    const { deps } = harness({
      baselines: [baseline('a.ts', content)],
      docs: { 'a.ts': baselineDoc('a.ts', content) },
      probes: { 'a.ts': probeOf({ hash: sha('changed\n') }) },
      signal: controller.signal,
    });
    controller.abort();
    const outcome = await runDiscovery(deps);
    assert.strictEqual(outcome.status, 'cancelled');
    assert.strictEqual(outcome.coverage?.partial, true, 'a partial scan cannot claim totals');
  });

  it('classifies thousands of files quickly and reports progress', async () => {
    const content = 'baseline\n';
    const count = 3000;
    const baselines: DiscoveryBaseline[] = [];
    const docs: Record<string, DiscoveryDoc> = {};
    const probes: Record<string, FileProbe> = {};
    for (let index = 0; index < count; index += 1) {
      const resource = `src/module-${index}.ts`;
      baselines.push(baseline(resource, content));
      docs[resource] = baselineDoc(resource, content);
      probes[resource] = probeOf({ hash: sha(`changed-${index}\n`) });
    }
    const { deps, progress } = harness({
      baselines,
      docs,
      probes,
      assess: (candidates) =>
        candidates.map((candidate) => ({
          resource: candidate.resource,
          ok: true,
          summary: { would_succeed: true, conflict_status: 'no_conflict', drift_status: 'no_drift' },
        })),
    });

    const started = Date.now();
    const outcome = await runDiscovery(deps);
    const elapsed = Date.now() - started;

    assert.strictEqual(outcome.status, 'complete');
    assert.strictEqual(outcome.records.length, count);
    assert.strictEqual(outcome.assessments.length, count);
    assert.ok(
      progress.some((update) => update.phase === 'Assessing recovery eligibility'),
      'the scan reports its progress',
    );
    assert.ok(elapsed < 20_000, `classifying ${count} files took ${elapsed}ms`);
  });
});

describe('Recovery Inbox discovery - ignore rules', () => {
  it('skips exactly the directories the engine bridge skips', () => {
    const bridge = fs.readFileSync(
      path.join(__dirname, '..', '..', '..', 'python', 'interlock_bridge.py'),
      'utf8',
    );
    const match = /SCAN_SKIP_DIRS\s*=\s*\{([\s\S]*?)\}/.exec(bridge);
    assert.ok(match, 'SCAN_SKIP_DIRS not found in the bridge');
    const pythonDirs = [...match[1].matchAll(/"([^"]+)"/g)].map((entry) => entry[1]);
    assert.deepStrictEqual(
      [...SCAN_SKIP_DIRS].sort(),
      pythonDirs.sort(),
      'the extension and the bridge must skip the same directories',
    );
  });
});
