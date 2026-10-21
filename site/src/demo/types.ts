/**
 * Types for the simulated recovery demo.
 *
 * SAFETY CONTRACT: every value in this module describes FICTIONAL data that
 * lives only in browser memory. Nothing here reads, writes, renames, or
 * inspects a real file, and no network or production recovery API is used.
 */

export type ScenarioId = 'success' | 'conflict' | 'refusal' | 'interrupted';

/** Phases of the simulated recovery state machine. */
export type Phase =
  | 'idle'
  | 'incident_detected'
  | 'analyzed'
  | 'plan_created'
  | 'awaiting_approval'
  | 'recovering'
  | 'verifying'
  | 'verified'
  | 'conflict'
  | 'conflict_review'
  | 'refused'
  | 'interrupted'
  | 'error';

/** Commands the visitor can issue. Invalid ones are rejected by the machine. */
export type DemoAction =
  | 'START'
  | 'ANALYZE'
  | 'CREATE_PLAN'
  | 'REQUEST_APPROVAL'
  | 'APPROVE'
  | 'REJECT'
  | 'VERIFY'
  | 'RESUME'
  | 'REVIEW_CONFLICT'
  | 'RESET';

export type RiskLevel = 'high' | 'medium' | 'low';

/** One fictional file in the simulated project. */
export interface FictionalFile {
  /** Project-relative path (fictional). */
  path: string;
  /** Content captured before the fictional incident. */
  original: string;
  /** Content present now, in the simulation. */
  current: string;
  /** Who wrote the current content. */
  changedBy: 'agent' | 'human' | 'none';
  /** Whether pre-action evidence exists (drives the safety precondition). */
  evidenceCaptured: boolean;
  /** True when the agent deleted the file (current content is empty). */
  deleted?: boolean;
  /** True when a human edit landed after the agent action. */
  humanEdit?: boolean;
}

export interface FileAnalysis {
  path: string;
  risk: RiskLevel;
  reason: string;
  changeKind: 'modified' | 'deleted' | 'human-edit' | 'missing-evidence' | 'unchanged';
}

export interface PlanEntry {
  path: string;
  operation: 'restore' | 'skip';
  reason: string;
}

export interface PreconditionFailure {
  id: string;
  label: string;
  detail: string;
  remediation: string;
}

export interface TimelineEntry {
  time: string;
  title: string;
  detail: string;
  kind: 'agent' | 'system' | 'human' | 'error';
}

export type EventLevel = 'info' | 'warn' | 'error' | 'success';

export interface LogEvent {
  id: number;
  time: string;
  level: EventLevel;
  message: string;
}

export interface VerificationResult {
  status: 'pass' | 'fail';
  checked: number;
  restored: number;
  mismatched: string[];
  unresolvedConflicts: number;
  residue: string[];
  /** SHA-256 (computed in-browser) of each verified fictional file. */
  digests: { path: string; sha256: string; matches: boolean }[];
  summary: string;
}

export interface ScenarioSpec {
  id: ScenarioId;
  label: string;
  title: string;
  summary: string;
  expectation: string;
  project: string;
  files: FictionalFile[];
  timeline: TimelineEntry[];
  /** Evaluated when the recovery plan is built. */
  precondition?: PreconditionFailure;
  /** Evaluated before recovery starts (drift / conflict detection). */
  conflict?: { path: string; expected: string; found: string; reason: string };
  /** Progress percentage at which the simulated worker is interrupted. */
  interruptAfter?: number;
}

export interface DemoState {
  scenario: ScenarioId;
  phase: Phase;
  /** Recovery progress, 0–100. */
  progress: number;
  files: FictionalFile[];
  analysis: FileAnalysis[] | null;
  plan: PlanEntry[] | null;
  approval: 'pending' | 'granted' | 'withheld';
  refusal: PreconditionFailure | null;
  conflict: ScenarioSpec['conflict'] | null;
  verification: VerificationResult | null;
  events: LogEvent[];
  nextEventId: number;
  /** Deterministic virtual clock (seconds past midnight) for event stamps. */
  clock: number;
}

export type DemoCommand =
  | { type: 'SELECT_SCENARIO'; scenario: ScenarioId }
  | { type: 'RUN'; action: DemoAction }
  | { type: 'TICK'; by?: number };
