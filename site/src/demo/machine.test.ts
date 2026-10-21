import { describe, expect, it } from 'vitest';
import {
  availableActions,
  createInitialState,
  transition,
} from './machine';
import type { DemoAction, DemoState } from './types';
import { diffLines, sha256 } from './text';
import { verifyIntegrity } from './verification';

function run(state: DemoState, actions: DemoAction[]): DemoState {
  return actions.reduce((acc, action) => transition(acc, { type: 'RUN', action }), state);
}

function tickUntil(state: DemoState, limit = 40): DemoState {
  let current = state;
  let guard = 0;
  while (current.phase === 'recovering' && guard < limit) {
    current = transition(current, { type: 'TICK' });
    guard += 1;
  }
  if (current.phase === 'verifying') current = transition(current, { type: 'TICK' });
  return current;
}

describe('sha256 (used for simulated integrity checks)', () => {
  it('matches the published vectors', () => {
    expect(sha256('')).toBe('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');
    expect(sha256('abc')).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
  });

  it('is stable for multi-line fictional content', () => {
    expect(sha256('line one\nline two\n')).toBe(sha256('line one\nline two\n'));
    expect(sha256('line one\nline two\n')).not.toBe(sha256('line one\nline 2\n'));
  });
});

describe('diffLines', () => {
  it('marks added and removed lines', () => {
    const diff = diffLines('a\nb\nc', 'a\nx\nc');
    expect(diff.filter((l) => l.kind === 'remove').map((l) => l.text)).toEqual(['b']);
    expect(diff.filter((l) => l.kind === 'add').map((l) => l.text)).toEqual(['x']);
    expect(diff.filter((l) => l.kind === 'context')).toHaveLength(2);
  });
});

describe('scenario A — successful recovery', () => {
  it('runs the full workflow to verified and restores every file', () => {
    let state = createInitialState('success');
    expect(state.phase).toBe('idle');

    state = run(state, ['START', 'ANALYZE', 'CREATE_PLAN', 'REQUEST_APPROVAL']);
    expect(state.phase).toBe('awaiting_approval');
    expect(state.plan?.every((entry) => entry.operation === 'restore')).toBe(true);

    state = transition(state, { type: 'RUN', action: 'APPROVE' });
    expect(state.phase).toBe('recovering');
    expect(state.approval).toBe('granted');

    state = tickUntil(state);
    expect(state.phase).toBe('verified');
    expect(state.verification?.status).toBe('pass');
    expect(state.verification?.restored).toBe(4);
    expect(state.verification?.mismatched).toEqual([]);
    for (const file of state.files) {
      expect(file.current).toBe(file.original);
    }
    expect(state.events.some((event) => event.level === 'success')).toBe(true);
  });

  it('refuses to run recovery before analysis, planning and approval', () => {
    const idle = createInitialState('success');
    expect(transition(idle, { type: 'RUN', action: 'APPROVE' })).toEqual(idle);
    expect(transition(idle, { type: 'RUN', action: 'CREATE_PLAN' })).toEqual(idle);
    expect(transition(idle, { type: 'TICK' })).toEqual(idle);

    const detected = run(idle, ['START']);
    expect(transition(detected, { type: 'RUN', action: 'REQUEST_APPROVAL' })).toEqual(detected);

    const analyzed = run(idle, ['START', 'ANALYZE']);
    expect(transition(analyzed, { type: 'RUN', action: 'APPROVE' })).toEqual(analyzed);
  });

  it('never reports success while approval is withheld', () => {
    let state = run(createInitialState('success'), [
      'START',
      'ANALYZE',
      'CREATE_PLAN',
      'REQUEST_APPROVAL',
      'REJECT',
    ]);
    expect(state.phase).toBe('plan_created');
    expect(state.approval).toBe('withheld');
    state = tickUntil(state);
    expect(state.phase).toBe('plan_created');
    expect(state.verification).toBeNull();
  });

  it('resets back to the pristine scenario state', () => {
    let state = run(createInitialState('success'), ['START', 'ANALYZE', 'CREATE_PLAN']);
    state = transition(state, { type: 'RUN', action: 'RESET' });
    expect(state).toEqual(createInitialState('success'));
  });
});

describe('scenario B — conflict detected', () => {
  it('blocks recovery and never reaches verified', () => {
    let state = run(createInitialState('conflict'), [
      'START',
      'ANALYZE',
      'CREATE_PLAN',
      'REQUEST_APPROVAL',
    ]);
    expect(state.plan?.find((entry) => entry.path === 'src/config.ts')?.operation).toBe('skip');

    state = transition(state, { type: 'RUN', action: 'APPROVE' });
    expect(state.phase).toBe('conflict');
    expect(state.conflict?.path).toBe('src/config.ts');
    expect(state.verification).toBeNull();

    state = tickUntil(state);
    expect(state.phase).toBe('conflict');
    expect(state.verification).toBeNull();
  });

  it('requires a separate review and then only reset', () => {
    let state = run(createInitialState('conflict'), [
      'START',
      'ANALYZE',
      'CREATE_PLAN',
      'REQUEST_APPROVAL',
      'APPROVE',
    ]);
    expect(availableActions(state)).toEqual(['REVIEW_CONFLICT', 'RESET']);
    state = transition(state, { type: 'RUN', action: 'REVIEW_CONFLICT' });
    expect(state.phase).toBe('conflict_review');
    expect(availableActions(state)).toEqual(['RESET']);
    expect(transition(state, { type: 'RUN', action: 'APPROVE' })).toEqual(state);
  });

  it('keeps the human edit intact after reset', () => {
    const state = run(createInitialState('conflict'), ['START', 'ANALYZE', 'RESET']);
    const humanFile = state.files.find((file) => file.path === 'src/config.ts');
    expect(humanFile?.changedBy).toBe('human');
    expect(humanFile?.humanEdit).toBe(true);
    expect(humanFile?.current).not.toBe(humanFile?.original);
  });
});

describe('scenario C — unsafe recovery refused', () => {
  it('refuses at plan time with an explicit precondition', () => {
    const state = run(createInitialState('refusal'), ['START', 'ANALYZE', 'CREATE_PLAN']);
    expect(state.phase).toBe('refused');
    expect(state.refusal?.id).toBe('pre-action-evidence-present');
    expect(state.refusal?.detail).toContain('no captured pre-action snapshot');
    expect(state.verification).toBeNull();
    expect(availableActions(state)).toEqual(['RESET']);
  });

  it('cannot be pushed through approval', () => {
    const refused = run(createInitialState('refusal'), ['START', 'ANALYZE', 'CREATE_PLAN']);
    expect(transition(refused, { type: 'RUN', action: 'APPROVE' })).toEqual(refused);
    expect(transition(refused, { type: 'TICK' })).toEqual(refused);
  });

  it('recovers normally in another scenario after reset', () => {
    let state = run(createInitialState('refusal'), ['START', 'ANALYZE', 'CREATE_PLAN', 'RESET']);
    expect(state.phase).toBe('idle');
    expect(state.refusal).toBeNull();

    state = transition(state, { type: 'SELECT_SCENARIO', scenario: 'success' });
    state = run(state, ['START', 'ANALYZE', 'CREATE_PLAN', 'REQUEST_APPROVAL', 'APPROVE']);
    state = tickUntil(state);
    expect(state.phase).toBe('verified');
    expect(state.verification?.status).toBe('pass');
  });
});

describe('scenario D — interrupted workflow', () => {
  it('interrupts part-way and does not claim success', () => {
    let state = run(createInitialState('interrupted'), [
      'START',
      'ANALYZE',
      'CREATE_PLAN',
      'REQUEST_APPROVAL',
      'APPROVE',
    ]);
    state = tickUntil(state);
    expect(state.phase).toBe('interrupted');
    expect(state.progress).toBe(55);
    expect(state.verification).toBeNull();

    const restored = state.files.filter((file) => file.current === file.original).length;
    expect(restored).toBe(2);
  });

  it('verification before resuming reports incomplete work', () => {
    let state = run(createInitialState('interrupted'), [
      'START',
      'ANALYZE',
      'CREATE_PLAN',
      'REQUEST_APPROVAL',
      'APPROVE',
    ]);
    state = tickUntil(state);
    state = transition(state, { type: 'RUN', action: 'VERIFY' });
    expect(state.phase).toBe('verifying');
    state = transition(state, { type: 'TICK' });
    expect(state.phase).toBe('interrupted');
    expect(state.verification?.status).toBe('fail');
    expect(state.verification?.restored).toBe(2);
    expect(state.verification?.mismatched).toHaveLength(2);
  });

  it('reports success only after resume plus a passing check', () => {
    let state = run(createInitialState('interrupted'), [
      'START',
      'ANALYZE',
      'CREATE_PLAN',
      'REQUEST_APPROVAL',
      'APPROVE',
    ]);
    state = tickUntil(state);
    state = transition(state, { type: 'RUN', action: 'RESUME' });
    expect(state.phase).toBe('recovering');
    state = tickUntil(state);
    expect(state.phase).toBe('verified');
    expect(state.verification?.status).toBe('pass');
    expect(state.verification?.restored).toBe(4);
  });
});

describe('scenario switching and stale state', () => {
  it('clears results when switching scenarios', () => {
    let state = run(createInitialState('success'), [
      'START',
      'ANALYZE',
      'CREATE_PLAN',
      'REQUEST_APPROVAL',
      'APPROVE',
    ]);
    state = tickUntil(state);
    expect(state.verification).not.toBeNull();

    state = transition(state, { type: 'SELECT_SCENARIO', scenario: 'conflict' });
    expect(state.phase).toBe('idle');
    expect(state.scenario).toBe('conflict');
    expect(state.verification).toBeNull();
    expect(state.analysis).toBeNull();
    expect(state.plan).toBeNull();
    expect(state.conflict).toBeNull();
    expect(state.progress).toBe(0);
    expect(state.files.map((file) => file.path)).toEqual([
      'src/config.ts',
      'src/routes.ts',
      'package.json',
    ]);
  });
});

describe('verification derives from fictional state', () => {
  it('passes only when content matches the captured original', () => {
    const files = [
      {
        path: 'a.txt',
        original: 'original',
        current: 'original',
        changedBy: 'none' as const,
        evidenceCaptured: true,
      },
    ];
    expect(verifyIntegrity(files).status).toBe('pass');

    files[0].current = 'agent rewrite';
    const failed = verifyIntegrity(files);
    expect(failed.status).toBe('fail');
    expect(failed.mismatched).toEqual(['a.txt']);
    expect(failed.digests[0].matches).toBe(false);
    expect(failed.digests[0].sha256).toBe(sha256('agent rewrite'));
  });

  it('counts unresolved human-edit conflicts', () => {
    const result = verifyIntegrity([
      {
        path: 'config.ts',
        original: 'v1',
        current: 'human v2',
        changedBy: 'human',
        evidenceCaptured: true,
        humanEdit: true,
      },
    ]);
    expect(result.unresolvedConflicts).toBe(1);
    expect(result.status).toBe('fail');
  });
});

describe('allowed actions', () => {
  it('offers only valid commands for each phase', () => {
    expect(availableActions(createInitialState('success'))).toEqual(['START', 'RESET']);
    const detecting = run(createInitialState('success'), ['START']);
    expect(availableActions(detecting)).toContain('ANALYZE');
    expect(availableActions(detecting)).not.toContain('APPROVE');
  });
});
