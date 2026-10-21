import { useEffect, useMemo, useReducer, useState } from 'react';
import { usePageMeta } from '../components/PageMeta';
import { Icon, type IconName } from '../components/Icon';
import { Reveal } from '../components/Reveal';
import { Section } from '../components/Layout';
import { Callout, CopyButton } from '../components/CodeBlock';
import { SCENARIO_ORDER, SCENARIOS } from '../demo/scenarios';
import { availableActions, createInitialState, transition } from '../demo/machine';
import { diffLines } from '../demo/text';
import { buildReport } from '../demo/report';
import type { DemoAction, DemoState, Phase, ScenarioId } from '../demo/types';

/**
 * Action labels in plain language: every button says exactly what it will do.
 * "Approve and continue" is the only label that can let a restore run.
 */
const ACTION_META: Record<
  DemoAction,
  { label: string; hint: string; variant: 'primary' | 'secondary' | 'ghost'; icon: IconName }
> = {
  START: {
    label: 'Start incident',
    hint: 'Begin the simulated incident and load the fictional event stream.',
    variant: 'primary',
    icon: 'play',
  },
  ANALYZE: {
    label: 'Review changes',
    hint: 'Classify each fictional file by risk so you can see what is safe to restore.',
    variant: 'secondary',
    icon: 'eye',
  },
  CREATE_PLAN: {
    label: 'Preview recovery',
    hint: 'Draft the read-only recovery plan: what would be restored, what would be skipped, and which files lack evidence.',
    variant: 'secondary',
    icon: 'code',
  },
  REQUEST_APPROVAL: {
    label: 'Request approval',
    hint: 'Ask for explicit human approval before any restore operation is allowed to run.',
    variant: 'secondary',
    icon: 'shield-check',
  },
  APPROVE: {
    label: 'Approve and continue',
    hint: 'Explicitly approve the previewed plan — the only action that lets restore operations run.',
    variant: 'primary',
    icon: 'shield-check',
  },
  REJECT: {
    label: "Don't approve",
    hint: 'Withhold approval for this run. The plan stays visible but nothing is restored.',
    variant: 'ghost',
    icon: 'x',
  },
  VERIFY: {
    label: 'Run verification',
    hint: 'Recompute the fictional digests and compare them with the captured originals.',
    variant: 'secondary',
    icon: 'check-circle',
  },
  RESUME: {
    label: 'Resume recovery',
    hint: 'Continue the interrupted recovery workflow from where the worker stopped.',
    variant: 'secondary',
    icon: 'shield-check',
  },
  REVIEW_CONFLICT: {
    label: 'Review conflict',
    hint: 'Inspect the detected drift and decide how to handle it.',
    variant: 'secondary',
    icon: 'alert',
  },
  RESET: {
    label: 'Reset simulation',
    hint: 'Restore the fictional baseline and clear the walkthrough state.',
    variant: 'ghost',
    icon: 'rotate',
  },
};

/** The recovery workflow, in the order a visitor experiences it. */
const STEP_ORDER: { key: string; label: string }[] = [
  { key: 'incident', label: 'Incident' },
  { key: 'review', label: 'Review' },
  { key: 'preview', label: 'Preview' },
  { key: 'approve', label: 'Approve' },
  { key: 'recover', label: 'Recover' },
  { key: 'verify', label: 'Verify' },
];

/**
 * Index of the step the visitor is working on right now, derived purely from
 * simulation state (never from display strings): once the incident is
 * detected the next step is Review, and so on.
 */
const PHASE_STEP: Record<Phase, number> = {
  idle: 0,
  incident_detected: 1,
  analyzed: 2,
  plan_created: 3,
  awaiting_approval: 3,
  recovering: 4,
  verifying: 5,
  verified: 6,
  interrupted: 4,
  conflict: 3,
  conflict_review: 3,
  refused: 2,
  error: 5,
};

const BLOCKED_PHASES: Phase[] = ['conflict', 'conflict_review', 'refused', 'error'];

function stepClass(index: number, phase: Phase): string {
  const current = PHASE_STEP[phase];
  if (index < current) return 'done';
  if (index === current) return BLOCKED_PHASES.includes(phase) ? 'blocked' : 'current';
  return '';
}

function fileState(file: DemoState['files'][number]): { cls: string; label: string } {
  if (file.current === file.original) {
    return file.changedBy === 'none'
      ? { cls: 'unchanged', label: 'unchanged' }
      : { cls: 'restored', label: 'restored' };
  }
  if (file.humanEdit) return { cls: 'human', label: 'human edit' };
  if (file.deleted) return { cls: 'missing', label: 'deleted' };
  return { cls: 'changed', label: 'changed' };
}

/**
 * Milestone timestamps are read from the real event log. A step that has not
 * run yet simply has no time — nothing is invented for the flow.
 */
const STAGE_MARKERS: string[][] = [
  ['Incident detected in'],
  ['Analysis complete:'],
  ['Recovery plan created:', 'Recovery refused — precondition'],
  ['Plan queued for explicit human approval.', 'Approval rejected', 'Approval withheld'],
  ['Approval granted by visitor', 'Simulated worker interruption'],
  ['Verification passed', 'Verification failed', 'Verifying current in-memory state'],
];

function stageTime(state: DemoState, index: number): string {
  for (const marker of STAGE_MARKERS[index]) {
    const event = state.events.find((e) => e.message.includes(marker));
    if (event) return event.time;
  }
  return '';
}

/** One plain-language line per flow step, computed from real state fields. */
function stageDesc(state: DemoState, index: number): string {
  switch (index) {
    case 0:
      return state.phase === 'idle'
        ? 'Not started — the fictional incident is waiting.'
        : `${state.files.filter((f) => f.current !== f.original).length} of ${state.files.length} files show changes.`;
    case 1: {
      if (!state.analysis) return 'Classify every changed file by risk.';
      const high = state.analysis.filter((item) => item.risk === 'high').length;
      return high > 0
        ? `${state.analysis.length} files classified · ${high} at high risk.`
        : `${state.analysis.length} files classified · none at high risk.`;
    }
    case 2: {
      if (state.phase === 'refused') return 'Stopped — a safety precondition failed.';
      if (!state.plan) return 'List what recovery would change, before changing anything.';
      const restores = state.plan.filter((entry) => entry.operation === 'restore').length;
      const skips = state.plan.length - restores;
      return `${restores} to restore · ${skips} skipped.`;
    }
    case 3: {
      if (state.phase === 'conflict' || state.phase === 'conflict_review') {
        return 'Stopped — a file changed after the plan was made.';
      }
      if (state.approval === 'granted') return 'Approved by you — nothing ran without it.';
      if (state.approval === 'withheld') return 'Approval withheld — nothing ran.';
      if (state.phase === 'awaiting_approval') return 'Waiting for your explicit approval.';
      return 'A human must approve before anything changes.';
    }
    case 4:
      if (state.phase === 'interrupted') return `Stopped at ${state.progress}% — not finished.`;
      if (state.phase === 'recovering') return `Applying the approved plan — ${state.progress}%.`;
      if (state.phase === 'verifying' || state.phase === 'verified' || state.phase === 'error') {
        return 'Approved plan applied in memory.';
      }
      return 'Runs only after you approve.';
    case 5:
    default:
      if (state.verification) return state.verification.summary;
      if (state.phase === 'verifying') return 'Recomputing digests…';
      return 'Byte-exact check against captured evidence.';
  }
}

interface FlowStage {
  key: string;
  label: string;
  time: string;
  desc: string;
  cls: string;
}

function flowStages(state: DemoState): FlowStage[] {
  return STEP_ORDER.map((step, index) => ({
    key: step.key,
    label: step.label,
    time: stageTime(state, index),
    desc: stageDesc(state, index),
    cls: stepClass(index, state.phase),
  }));
}

interface Result {
  cls: 'ok' | 'warn' | 'danger';
  title: string;
  body: string;
  icon: IconName;
}

/**
 * Only genuine end states get a result, and only in the words the outcome
 * supports: verified, blocked, incomplete, or failed. In-progress phases
 * explain themselves in the task panel instead.
 */
function resultFor(state: DemoState): Result | null {
  switch (state.phase) {
    case 'verified':
      return {
        cls: 'ok',
        title: 'Recovery verified',
        body: `${state.verification?.summary ?? 'The required independent verification passed.'} This result was computed from the fictional files, not assumed.`,
        icon: 'check-circle',
      };
    case 'conflict':
      return {
        cls: 'danger',
        title: 'Recovery blocked',
        body: `${state.conflict?.reason ?? 'A file changed after the plan was made.'} Recovery did not run, because running it could overwrite a human edit.`,
        icon: 'shield-x',
      };
    case 'refused':
      return {
        cls: 'danger',
        title: 'Recovery blocked',
        body: `${state.refusal?.detail ?? 'A safety precondition failed.'} Nothing was modified.`,
        icon: 'shield-x',
      };
    case 'interrupted':
      return {
        cls: 'warn',
        title: 'Recovery incomplete',
        body: 'The simulated worker stopped part-way. Verify the current state, then resume — nothing here counts as a success.',
        icon: 'alert',
      };
    case 'error':
      return {
        cls: 'danger',
        title: 'Verification failed',
        body: `${state.verification?.summary ?? 'The resulting files did not match the captured originals.'} Nothing is reported as recovered.`,
        icon: 'x-circle',
      };
    default:
      return null;
  }
}

/** The one main task for the current phase, in plain language. */
function taskCopy(state: DemoState): { heading: string; body: string } {
  switch (state.phase) {
    case 'idle':
      return {
        heading: 'Nothing has happened yet',
        body: 'Start the incident to walk through recovery, step by step.',
      };
    case 'incident_detected':
      return {
        heading: 'Incident detected',
        body: 'An AI agent changed files in the fictional project. Review what changed before anything is restored.',
      };
    case 'analyzed':
      return {
        heading: 'Changes reviewed',
        body: 'Every fictional file now has a risk classification. Preview what recovery would change.',
      };
    case 'plan_created':
      return {
        heading: 'Recovery ready to preview',
        body: 'The plan lists what would be restored and what would be skipped. Request approval when the plan looks right.',
      };
    case 'awaiting_approval':
      return {
        heading: 'Waiting for explicit approval',
        body: 'Nothing runs without your approval. Approve to continue, or withhold approval to leave every file unchanged.',
      };
    case 'recovering':
      return {
        heading: 'Applying the approved plan',
        body: `Restore operations are running against the fictional files in memory — ${state.progress}%.`,
      };
    case 'verifying':
      return {
        heading: 'Verifying the result',
        body: 'The plan finished applying. Now every file is compared with its captured original, byte for byte.',
      };
    case 'verified':
      return {
        heading: 'Walkthrough finished',
        body: 'The independent verification passed. Reset the simulation to run another scenario.',
      };
    case 'interrupted':
      return {
        heading: 'The workflow stopped',
        body: 'The simulated worker stopped part-way, so recovery is not finished. Run verification first, then resume.',
      };
    case 'conflict':
      return {
        heading: 'A conflict needs your review',
        body: 'A file changed after the plan was made, so recovery did not run. Review the conflict to decide what happens next.',
      };
    case 'conflict_review':
      return {
        heading: 'Conflict review open',
        body: 'You are looking at the drift that blocked recovery. Reset the simulation, or switch scenario, to continue.',
      };
    case 'refused':
      return {
        heading: 'A safety gate stopped recovery',
        body: 'The plan failed a precondition before anything ran. Reset the simulation to start over.',
      };
    case 'error':
    default:
      return {
        heading: 'Checks did not match',
        body: 'Verification found files that do not match the captured originals. The result is reported as failed, not recovered.',
      };
  }
}

const PHASE_ANNOUNCE: Record<Phase, string> = {
  idle: 'Simulation idle.',
  incident_detected: 'Incident detected.',
  analyzed: 'Changes analysed.',
  plan_created: 'Recovery plan created.',
  awaiting_approval: 'Awaiting explicit approval.',
  recovering: 'Recovery running.',
  verifying: 'Verification running.',
  verified: 'Recovery verified successfully.',
  interrupted: 'Workflow interrupted and incomplete.',
  conflict: 'Conflict detected. Recovery blocked.',
  conflict_review: 'Conflict review open.',
  refused: 'Recovery refused by a safety precondition.',
  error: 'Verification failed.',
};

export function DemoPage() {
  usePageMeta({
    title: 'Interactive demo — Interlock V6',
    description:
      'Walk through a simulated AI agent recovery in your browser, step by step: incident, review, preview, approval, recovery and verification — plus conflict, refusal and interruption scenarios. Fictional data only.',
  });

  const [state, dispatch] = useReducer(transition, 'success', createInitialState);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [view, setView] = useState<'diff' | 'current' | 'original'>('diff');

  const spec = SCENARIOS[state.scenario];
  const activeFiles = state.files;
  const currentPath = selectedPath && activeFiles.some((f) => f.path === selectedPath)
    ? selectedPath
    : (activeFiles[0]?.path ?? null);
  const selectedFile = activeFiles.find((f) => f.path === currentPath) ?? null;

  const actions = availableActions(state);
  const mainAction = actions.find((action) => action !== 'RESET');

  // Deterministic in-memory worker: advances recovery and verification only.
  useEffect(() => {
    if (state.phase !== 'recovering' && state.phase !== 'verifying') return;
    const timer = window.setInterval(() => dispatch({ type: 'TICK' }), 750);
    return () => window.clearInterval(timer);
  }, [state.phase]);

  const diff = useMemo(() => {
    if (!selectedFile) return [];
    return diffLines(selectedFile.original, selectedFile.current);
  }, [selectedFile]);

  const grouped = useMemo(() => {
    const groups = new Map<string, typeof activeFiles>();
    activeFiles.forEach((file) => {
      const dir = file.path.includes('/') ? `${file.path.slice(0, file.path.lastIndexOf('/'))}/` : '/';
      const list = groups.get(dir) ?? [];
      list.push(file);
      groups.set(dir, list);
    });
    return Array.from(groups.entries());
  }, [activeFiles]);

  const report = useMemo(() => buildReport(state), [state]);
  const result = resultFor(state);
  const task = taskCopy(state);
  const stages = useMemo(() => flowStages(state), [state]);
  const restoredNow = activeFiles.filter((f) => f.current === f.original && f.changedBy !== 'none').length;

  return (
    <>
      <div className="demo-banner">
        Simulated environment — fictional data only — no real files modified
      </div>

      <div className="page-hero">
        <div className="container">
          <Reveal>
            <span className="eyebrow">Interactive demo</span>
            <h1>Recovery, step by step.</h1>
            <p className="section-lead">
              Follow a fictional incident from detection to a verified result. Everything runs in
              your browser on invented data — no real files are opened, changed or restored.
            </p>
          </Reveal>
        </div>
      </div>

      <Section labelledBy="demo-title">
        <h2 id="demo-title" className="sr-only">
          Recovery walkthrough
        </h2>

        {/* 1 — choose a fictional scenario (plain titles, one sentence each) */}
        <div className="scenario-list" role="group" aria-label="Fictional scenario">
          {SCENARIO_ORDER.map((scenario) => (
            <button
              key={scenario.id}
              type="button"
              className={`scenario-option${state.scenario === scenario.id ? ' is-on' : ''}`}
              aria-pressed={state.scenario === scenario.id}
              onClick={() => {
                dispatch({ type: 'SELECT_SCENARIO', scenario: scenario.id as ScenarioId });
                setSelectedPath(null);
                setView('diff');
              }}
            >
              <span className="scenario-dot" aria-hidden="true" />
              <span className="scenario-text">
                <span className="scenario-name">{scenario.label}</span>
                <span className="scenario-note">{scenario.title}</span>
              </span>
            </button>
          ))}
        </div>

        {/* 2 — where we are in the workflow */}
        <ol className="phase-steps" aria-label="Workflow progress">
          {STEP_ORDER.map((step, index) => {
            const cls = stepClass(index, state.phase);
            return (
              <li
                key={step.key}
                className={`phase-step ${cls}`}
                aria-current={cls === 'current' || cls === 'blocked' ? 'step' : undefined}
              >
                <span className="idx" aria-hidden="true">
                  {index + 1}
                </span>
                {step.label}
              </li>
            );
          })}
        </ol>

        <p className="sr-only" role="status" aria-live="polite">
          {PHASE_ANNOUNCE[state.phase]}
          {state.verification ? ` ${state.verification.summary}` : ''}
        </p>

        <div className="demo-grid">
          {/* left — the recovery flow, filled in as it happens */}
          <div className="demo-col">
            <div className="demo-panel">
              <div className="demo-panel-head">
                <span>Recovery flow</span>
                <span>{spec.project}</span>
              </div>
              <div className="demo-panel-body">
                <ol className="flow">
                  {stages.map((stage) => (
                    <li
                      key={stage.key}
                      className={`flow-item ${stage.cls}`}
                      aria-current={
                        stage.cls === 'current' || stage.cls === 'blocked' ? 'step' : undefined
                      }
                    >
                      <span className="flow-mark" aria-hidden="true">
                        {stage.cls === 'done' ? (
                          <Icon name="check" width={12} height={12} />
                        ) : stage.cls === 'blocked' ? (
                          <Icon name="alert" width={12} height={12} />
                        ) : (
                          <span className="flow-dot" />
                        )}
                      </span>
                      <span className="flow-body">
                        <span className="flow-top">
                          <span className="flow-label">{stage.label}</span>
                          <span className="flow-time">{stage.time}</span>
                        </span>
                        <span className="flow-desc">{stage.desc}</span>
                      </span>
                      {stage.cls === 'current' ? <span className="sr-only"> (current step)</span> : null}
                    </li>
                  ))}
                </ol>
              </div>
            </div>
          </div>

          {/* right — one main task at a time, then one honest result */}
          <div className="demo-col">
            {result ? (
              <div className={`outcome ${result.cls}`}>
                <Icon name={result.icon} />
                <div>
                  <strong>{result.title}</strong>
                  <p>{result.body}</p>
                  {result.cls === 'ok' && state.verification ? (
                    <div className="result-stats">
                      <span>
                        <b>{state.verification.restored}</b> of {state.verification.checked} files restored
                      </span>
                      <span>
                        <b>{state.verification.unresolvedConflicts}</b> conflicts remain
                      </span>
                      <span>
                        <b>{state.verification.digests.filter((d) => !d.matches).length}</b> content mismatches
                      </span>
                    </div>
                  ) : null}
                </div>
              </div>
            ) : null}

            <div className="demo-panel">
              <div className="demo-panel-head">
                <h3 className="task-heading">{task.heading}</h3>
                <span>
                  {state.phase === 'idle'
                    ? 'not started'
                    : `step ${Math.min(PHASE_STEP[state.phase] + 1, STEP_ORDER.length)} of ${STEP_ORDER.length}`}
                </span>
              </div>
              <div className="demo-panel-body stack">
                <p className="task-text">{task.body}</p>

                {state.phase === 'idle' ? <p className="task-note faint">{spec.summary}</p> : null}

                {state.phase === 'incident_detected' ? (
                  <ul className="file-list">
                    {state.files.map((file) => {
                      const st = fileState(file);
                      return (
                        <li key={file.path}>
                          <span className="path">{file.path}</span>
                          <span className={`state ${st.cls}`}>{st.label}</span>
                        </li>
                      );
                    })}
                  </ul>
                ) : null}

                {state.phase === 'analyzed' && state.analysis ? (
                  <ul className="file-list">
                    {state.analysis.map((item) => (
                      <li key={item.path}>
                        <span>
                          <span className="path">{item.path}</span>
                          <span className="reason">{item.reason}</span>
                        </span>
                        <span className={`risk-chip ${item.risk}`}>{item.risk}</span>
                      </li>
                    ))}
                  </ul>
                ) : null}

                {state.phase === 'plan_created' && state.plan ? (
                  <>
                    <ul className="file-list">
                      {state.plan.map((entry) => (
                        <li key={entry.path}>
                          <span>
                            <span className="path">{entry.path}</span>
                            <span className="reason">{entry.reason}</span>
                          </span>
                          <span className={`op ${entry.operation}`}>{entry.operation}</span>
                        </li>
                      ))}
                    </ul>
                    {state.plan.some((entry) => entry.reason.startsWith('Refused:')) ? (
                      <p className="task-note warn">
                        {state.plan.filter((entry) => entry.reason.startsWith('Refused:')).length}{' '}
                        file(s) have no pre-action evidence — recovery refuses to touch them.
                      </p>
                    ) : null}
                  </>
                ) : null}

                {state.phase === 'awaiting_approval' ? (
                  <div className="demo-approve">
                    <Icon name="lock" width={16} height={16} />
                    <span>
                      Explicit approval is required before any restore operation runs.
                      {state.approval === 'granted' ? ' Approval recorded for this simulated run.' : ''}
                    </span>
                  </div>
                ) : null}

                {state.progress > 0 && state.phase !== 'verified' ? (
                  <>
                    <div className="progress" aria-label={`Recovery progress: ${state.progress}%`}>
                      <span className="progress-bar" style={{ width: `${state.progress}%` }} />
                    </div>
                    <div className="progress-meta">
                      <span>{state.progress}% applied</span>
                      <span>
                        {restoredNow} of {state.files.length} files match their originals
                      </span>
                    </div>
                  </>
                ) : null}

                {/* one main action per step, plus reset */}
                <div className="demo-actions">
                  {mainAction ? (
                    <button
                      type="button"
                      className={`btn ${
                        ACTION_META[mainAction].variant === 'primary' ? 'btn-primary' : 'btn-secondary'
                      }`}
                      onClick={() => dispatch({ type: 'RUN', action: mainAction })}
                    >
                      <Icon name={ACTION_META[mainAction].icon} width={16} height={16} />
                      {ACTION_META[mainAction].label}
                    </button>
                  ) : null}
                  {actions
                    .filter((action) => action !== mainAction && action !== 'RESET')
                    .map((action) => (
                      <button
                        key={action}
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => dispatch({ type: 'RUN', action })}
                      >
                        <Icon name={ACTION_META[action].icon} width={16} height={16} />
                        {ACTION_META[action].label}
                      </button>
                    ))}
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => dispatch({ type: 'RUN', action: 'RESET' })}
                  >
                    <Icon name={ACTION_META.RESET.icon} width={16} height={16} />
                    {ACTION_META.RESET.label}
                  </button>
                </div>
                <p className="faint small">
                  {mainAction ? ACTION_META[mainAction].hint : ACTION_META.RESET.hint}
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* 3 — the advanced detail, hidden until asked for */}
        <details className="demo-details">
          <summary>View technical details</summary>

          <div className="tech-grid">
            <div className="demo-col">
              <div className="demo-panel">
                <div className="demo-panel-head">
                  <span>Project tree · {spec.project}</span>
                  <span>fictional</span>
                </div>
                <div className="demo-panel-body flush">
                  {grouped.map(([dir, files]) => (
                    <ul className="tree" key={dir}>
                      <li className="tree-dir">{dir}</li>
                      {files.map((file) => {
                        const st = fileState(file);
                        return (
                          <li key={file.path}>
                            <button
                              type="button"
                              className="tree-file"
                              aria-current={currentPath === file.path}
                              onClick={() => {
                                setSelectedPath(file.path);
                                setView('diff');
                              }}
                            >
                              <span>{file.path.split('/').pop()}</span>
                              <span className={`state ${st.cls}`}>{st.label}</span>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  ))}
                </div>
              </div>

              <div className="demo-panel">
                <div className="demo-panel-head">
                  <span>Diff · {currentPath ?? 'no file selected'}</span>
                  <span className="row" style={{ gap: 6 }}>
                    {(['diff', 'current', 'original'] as const).map((mode) => (
                      <button
                        key={mode}
                        type="button"
                        className="copy-btn"
                        aria-pressed={view === mode}
                        style={view === mode ? { color: 'var(--yellow)', borderColor: 'var(--yellow)' } : undefined}
                        onClick={() => setView(mode)}
                      >
                        {mode}
                      </button>
                    ))}
                  </span>
                </div>
                <div className="demo-panel-body flush">
                  {selectedFile ? (
                    view === 'diff' ? (
                      <>
                        <div className="diff" aria-label={`Simulated diff for ${selectedFile.path}`}>
                          {diff.map((line, index) => (
                            <div className={`diff-line ${line.kind}`} key={`${line.oldLine ?? 'x'}-${index}`}>
                              <span className="ln">{line.oldLine ?? line.newLine ?? ''}</span>
                              <span>{line.text}</span>
                            </div>
                          ))}
                        </div>
                        <div className="diff-legend">
                          <span>− line removed</span>
                          <span>+ line added</span>
                        </div>
                      </>
                    ) : (
                      <pre className="diff" aria-label={`${view} content of ${selectedFile.path}`}>
                        {view === 'current' ? selectedFile.current : selectedFile.original}
                      </pre>
                    )
                  ) : (
                    <p className="faint small mb-0" style={{ padding: 'var(--space-4)' }}>
                      No file selected. Choose a file in the tree to inspect its simulated diff.
                    </p>
                  )}
                </div>
              </div>
            </div>

            <div className="demo-col">
              <div className="demo-panel">
                <div className="demo-panel-head">
                  <span>Risk analysis</span>
                  <span>{state.analysis ? `${state.analysis.length} files` : 'not run'}</span>
                </div>
                <div className="demo-panel-body flush">
                  {state.analysis ? (
                    <table className="risk-table">
                      <thead>
                        <tr>
                          <th scope="col">File</th>
                          <th scope="col">Risk</th>
                          <th scope="col">Reason</th>
                        </tr>
                      </thead>
                      <tbody>
                        {state.analysis.map((item) => (
                          <tr key={item.path}>
                            <td>{item.path}</td>
                            <td>
                              <span className={`risk-chip ${item.risk}`}>{item.risk}</span>
                            </td>
                            <td>{item.reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <p className="faint small mb-0" style={{ padding: 'var(--space-4)' }}>
                      No analysis yet. Start the incident, then run Review changes to classify every
                      fictional file by risk.
                    </p>
                  )}
                </div>
              </div>

              <div className="demo-panel">
                <div className="demo-panel-head">
                  <span>Verification detail</span>
                  <span>{state.verification ? state.verification.status : 'not run'}</span>
                </div>
                <div className="demo-panel-body flush">
                  {state.verification ? (
                    <ul className="verify-rows">
                      {state.verification.digests.map((digest) => (
                        <li key={digest.path}>
                          <span className="digest">
                            {digest.path}
                            <span className="digest-hash" title="SHA-256 of the fictional file content, computed in your browser">
                              sha256:{digest.sha256.slice(0, 16)}…
                            </span>
                          </span>
                          <span className={digest.matches ? 'match' : 'mismatch'}>
                            {digest.matches ? 'match' : 'mismatch'}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="muted small mb-0" style={{ padding: 'var(--space-4)' }}>
                      Verification has not run. Success is never shown here unless the digest
                      comparison over the fictional files actually passes.
                    </p>
                  )}
                </div>
              </div>
            </div>

            <div className="demo-col">
              <div className="demo-panel">
                <div className="demo-panel-head">
                  <span>Simulated event log</span>
                  <span>{state.events.length} events</span>
                </div>
                <div className="demo-panel-body flush">
                  <div className="log" role="log" aria-label="Simulated event log">
                    {state.events.map((event) => (
                      <div className={`log-line ${event.level}`} key={event.id}>
                        <span className="t">{event.time}</span>
                        <span className="lvl">{event.level}</span>
                        <span className="msg">{event.message}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="demo-panel">
                <div className="demo-panel-head">
                  <span>Run report</span>
                  <CopyButton text={report} label="Copy report" />
                </div>
                <div className="demo-panel-body flush">
                  <pre className="demo-code" aria-label="Demo state report">
                    {report}
                  </pre>
                </div>
              </div>
            </div>
          </div>
        </details>

        <div className="grid grid-2" style={{ marginTop: 'var(--space-6)' }}>
          <Callout type="info" title="What this demo is">
            <p>
              A deterministic state machine (<code>idle → incident → analyse → plan → approve →
              recover → verify → verified</code>) running entirely in your browser over invented
              file contents. Invalid transitions are rejected: recovery cannot start before
              analysis and approval, a conflict cannot become success, and a refused scenario
              cannot proceed.
            </p>
          </Callout>
          <Callout type="warn" title="What this demo is not">
            <p>
              It is not Interlock’s real engine, and it performs no real file operations, no
              restores, no shell commands and no network calls. The real product&rsquo;s recovery
              path is approval-gated and independently verified — the same rules this walkthrough
              demonstrates over fictional data.
            </p>
          </Callout>
        </div>
      </Section>
    </>
  );
}
