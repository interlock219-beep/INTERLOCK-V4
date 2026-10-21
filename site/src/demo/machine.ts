import { SCENARIOS, SUCCESS_SCENARIO } from './scenarios';
import type {
  DemoAction,
  DemoCommand,
  DemoState,
  FileAnalysis,
  FictionalFile,
  LogEvent,
  PlanEntry,
  RiskLevel,
  ScenarioId,
  ScenarioSpec,
} from './types';
import { formatClock } from './text';
import { restoreFile, verifyIntegrity } from './verification';

/** Seconds added to the virtual clock for each new log event. */
const TICK_SECONDS = 7;
/** Base clock: 10:24:11 — mirrors the incident timeline in the reference UI. */
const BASE_CLOCK = 10 * 3600 + 24 * 60 + 11;
/** Progress applied per TICK while the simulated worker runs. */
const TICK_STEP = 15;

function cloneFiles(spec: ScenarioSpec): FictionalFile[] {
  return spec.files.map((file) => ({ ...file }));
}

function log(state: DemoState, level: LogEvent['level'], message: string): DemoState {
  const clock = state.clock + TICK_SECONDS;
  const event: LogEvent = { id: state.nextEventId, time: formatClock(clock), level, message };
  return {
    ...state,
    clock,
    nextEventId: state.nextEventId + 1,
    events: [...state.events, event],
  };
}

/**
 * Fresh state for a scenario. Selecting a scenario always goes through here,
 * so switching scenarios can never leave stale analysis, verification, or
 * conflict results behind.
 */
export function createInitialState(scenario: ScenarioId = 'success'): DemoState {
  const spec = SCENARIOS[scenario] ?? SUCCESS_SCENARIO;
  const state: DemoState = {
    scenario: spec.id,
    phase: 'idle',
    progress: 0,
    files: cloneFiles(spec),
    analysis: null,
    plan: null,
    approval: 'pending',
    refusal: null,
    conflict: null,
    verification: null,
    events: [],
    nextEventId: 1,
    clock: BASE_CLOCK,
  };
  return log(
    state,
    'info',
    `Scenario loaded: ${spec.label} — fictional project ${spec.project} (simulated data only).`,
  );
}

function analyze(state: DemoState): FileAnalysis[] {
  return state.files.map((file) => {
    if (!file.evidenceCaptured) {
      return {
        path: file.path,
        risk: 'high' as RiskLevel,
        reason: 'No pre-action evidence captured — original bytes cannot be proven.',
        changeKind: 'missing-evidence' as const,
      };
    }
    if (file.humanEdit) {
      return {
        path: file.path,
        risk: 'high' as RiskLevel,
        reason: 'Human edit recorded after the agent action — restoring would discard it.',
        changeKind: 'human-edit' as const,
      };
    }
    if (file.deleted) {
      return {
        path: file.path,
        risk: 'high' as RiskLevel,
        reason: 'File deleted by the agent — restore recreates it from captured evidence.',
        changeKind: 'deleted' as const,
      };
    }
    const lineDelta = file.current.split('\n').length - file.original.split('\n').length;
    const risk: RiskLevel = Math.abs(lineDelta) >= 2 ? 'high' : 'medium';
    return {
      path: file.path,
      risk,
      reason: `Agent rewrote content (${lineDelta >= 0 ? '+' : ''}${lineDelta} lines).`,
      changeKind: 'modified' as const,
    };
  });
}

function isRestorable(file: FictionalFile): boolean {
  return file.evidenceCaptured && !file.humanEdit;
}

function buildPlan(state: DemoState, spec: ScenarioSpec): PlanEntry[] {
  return state.files.map((file) => {
    if (spec.precondition && !file.evidenceCaptured) {
      return { path: file.path, operation: 'skip', reason: 'Refused: precondition failed.' };
    }
    if (file.humanEdit) {
      return { path: file.path, operation: 'skip', reason: 'Conflict: human edit preserved.' };
    }
    return { path: file.path, operation: 'restore', reason: 'Pre-action evidence matches.' };
  });
}

/** Actions that the machine currently accepts. Anything else is rejected. */
export function availableActions(state: DemoState): DemoAction[] {
  switch (state.phase) {
    case 'idle':
      return ['START', 'RESET'];
    case 'incident_detected':
      return ['ANALYZE', 'RESET'];
    case 'analyzed':
      return ['CREATE_PLAN', 'RESET'];
    case 'plan_created':
      return ['REQUEST_APPROVAL', 'RESET'];
    case 'awaiting_approval':
      return ['APPROVE', 'REJECT', 'RESET'];
    case 'recovering':
    case 'verifying':
    case 'verified':
    case 'conflict_review':
    case 'refused':
    case 'error':
      return ['RESET'];
    case 'interrupted':
      return ['VERIFY', 'RESUME', 'RESET'];
    case 'conflict':
      return ['REVIEW_CONFLICT', 'RESET'];
    default:
      return ['RESET'];
  }
}

function can(state: DemoState, action: DemoAction): boolean {
  return availableActions(state).includes(action);
}

function startRecovery(state: DemoState, spec: ScenarioSpec): DemoState {
  const drifted =
    spec.conflict !== undefined &&
    state.files.some((file) => file.path === spec.conflict?.path && file.current !== file.original);

  if (drifted && spec.conflict) {
    const blocked: DemoState = {
      ...state,
      phase: 'conflict',
      conflict: spec.conflict,
      approval: 'granted',
    };
    return log(
      log(blocked, 'error', `Pre-flight conflict on ${spec.conflict.path} — recovery blocked.`),
      'warn',
      'Automatic recovery is unsafe while drift is unresolved. Review required.',
    );
  }

  const approved: DemoState = { ...state, approval: 'granted', progress: 0, phase: 'recovering' };
  return log(
    log(approved, 'info', 'Approval granted by visitor. Recovery started (simulated).'),
    'info',
    'Restore operations are applied to browser-held fictional files only.',
  );
}

/**
 * Applies restores gradually so progress reflects real simulation state:
 * a file is only restored once its share of the work has been completed.
 */
function applyProgressive(files: FictionalFile[], progress: number): FictionalFile[] {
  const restorableIndexes = files.map((f, i) => (isRestorable(f) ? i : -1)).filter((i) => i >= 0);
  const total = Math.max(restorableIndexes.length, 1);
  return files.map((file, index) => {
    const slot = restorableIndexes.indexOf(index);
    if (slot === -1) return file;
    const threshold = ((slot + 1) / total) * 100;
    return progress >= threshold ? restoreFile(file) : file;
  });
}

function finishRecovery(state: DemoState): DemoState {
  const done: DemoState = { ...state, phase: 'verifying', progress: 100 };
  return log(done, 'info', 'Restore complete. Independent verification started.');
}

function finalizeVerification(state: DemoState): DemoState {
  const result = verifyIntegrity(state.files);

  if (result.status === 'pass') {
    const passed: DemoState = { ...state, verification: result, phase: 'verified', progress: 100 };
    return log(
      log(passed, 'success', `Verification passed — ${result.summary}`),
      'success',
      'Recovery successful: integrity verified against captured evidence, no residue.',
    );
  }

  if (state.scenario === 'interrupted') {
    const partial: DemoState = { ...state, verification: result, phase: 'interrupted' };
    return log(
      log(
        partial,
        'warn',
        `Verification found an incomplete workflow: ${result.restored} of ${result.checked} files restored.`,
      ),
      'warn',
      'Incomplete work is never reported as success. Resume, then verify again.',
    );
  }

  const failed: DemoState = { ...state, verification: result, phase: 'error' };
  return log(failed, 'error', `Verification failed — ${result.summary}`);
}

function tickRecovery(state: DemoState, by: number): DemoState {
  const spec = SCENARIOS[state.scenario];
  const target = Math.min(100, state.progress + by);

  if (
    spec.interruptAfter !== undefined &&
    target >= spec.interruptAfter &&
    state.progress < spec.interruptAfter
  ) {
    const interrupted: DemoState = {
      ...state,
      progress: spec.interruptAfter,
      files: applyProgressive(state.files, spec.interruptAfter),
      phase: 'interrupted',
    };
    return log(
      log(interrupted, 'error', 'Simulated worker interruption mid-recovery.'),
      'warn',
      'Restore operations stopped part-way. Workflow state: incomplete.',
    );
  }

  const files = applyProgressive(state.files, target);
  if (target >= 100) {
    return finishRecovery({ ...state, files, progress: 100 });
  }
  return { ...state, files, progress: target };
}

/**
 * The single transition function. Invalid commands return the previous state
 * unchanged, so the machine can never skip approval, jump to success, or
 * continue past a refusal or conflict.
 */
export function transition(state: DemoState, command: DemoCommand): DemoState {
  if (command.type === 'SELECT_SCENARIO') {
    return createInitialState(command.scenario);
  }

  if (command.type === 'TICK') {
    if (state.phase === 'recovering') return tickRecovery(state, command.by ?? TICK_STEP);
    if (state.phase === 'verifying') return finalizeVerification(state);
    return state;
  }

  const action = command.action;
  if (!can(state, action)) return state;

  const spec = SCENARIOS[state.scenario];

  switch (action) {
    case 'START': {
      const started: DemoState = { ...state, phase: 'incident_detected' };
      return log(
        log(
          started,
          'warn',
          `Incident detected in ${spec.project}: agent modified ${state.files.length} file(s).`,
        ),
        'info',
        'Simulated event — this browser demo performs no real recovery.',
      );
    }
    case 'ANALYZE': {
      const analysis = analyze(state);
      const high = analysis.filter((entry) => entry.risk === 'high').length;
      const analyzed: DemoState = {
        ...state,
        phase: 'analyzed',
        analysis,
      };
      return log(
        log(analyzed, 'info', `Analysis complete: ${analysis.length} file(s) classified, ${high} high risk.`),
        spec.precondition ? 'error' : 'info',
        spec.precondition
          ? `Precondition failed — ${spec.precondition.label}.`
          : 'All restore targets have pre-action evidence.',
      );
    }
    case 'CREATE_PLAN': {
      const plan = buildPlan(state, spec);
      if (spec.precondition) {
        const refused: DemoState = {
          ...state,
          phase: 'refused',
          refusal: spec.precondition,
          plan,
        };
        return log(
          log(refused, 'error', `Recovery refused — precondition "${spec.precondition.id}" failed.`),
          'warn',
          spec.precondition.detail,
        );
      }
      const restores = plan.filter((entry) => entry.operation === 'restore').length;
      const planned: DemoState = {
        ...state,
        phase: 'plan_created',
        plan,
      };
      return log(planned, 'info', `Recovery plan created: ${restores} restore(s), ${plan.length - restores} skip(s).`);
    }
    case 'REQUEST_APPROVAL': {
      const queued: DemoState = { ...state, phase: 'awaiting_approval', approval: 'pending' };
      return log(log(queued, 'info', 'Plan queued for explicit human approval.'), 'info', 'Recovery will not start without approval.');
    }
    case 'APPROVE': {
      if (spec.precondition) {
        const refused: DemoState = {
          ...state,
          phase: 'refused',
          refusal: spec.precondition,
        };
        return log(refused, 'error', 'Approval rejected — safety precondition failed, recovery refused.');
      }
      return startRecovery(state, spec);
    }
    case 'REJECT': {
      const withheld: DemoState = { ...state, phase: 'plan_created', approval: 'withheld' };
      return log(withheld, 'warn', 'Approval withheld by visitor. Recovery did not run.');
    }
    case 'VERIFY': {
      const verifying: DemoState = { ...state, phase: 'verifying' };
      return log(verifying, 'info', 'Verifying current in-memory state against pre-incident content.');
    }
    case 'RESUME': {
      const resumed: DemoState = { ...state, phase: 'recovering' };
      return log(resumed, 'info', 'Resuming the interrupted workflow from the recorded position.');
    }
    case 'REVIEW_CONFLICT': {
      const reviewing: DemoState = { ...state, phase: 'conflict_review' };
      return log(
        reviewing,
        'warn',
        `Conflict review opened for ${state.conflict?.path ?? 'unknown file'}. Reset or switch scenario to continue.`,
      );
    }
    case 'RESET':
      return createInitialState(state.scenario);
    default:
      return state;
  }
}

export type { DemoAction, DemoCommand, DemoState };
