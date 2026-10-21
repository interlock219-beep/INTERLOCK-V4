import type { DemoState } from './types';
import { SCENARIOS } from './scenarios';

/**
 * Builds a plain-text report from FICTIONAL simulation state only.
 * It never contains visitor data — the simulation holds nothing about the
 * visitor beyond what is written into browser memory by their own clicks.
 */
export function buildReport(state: DemoState): string {
  const spec = SCENARIOS[state.scenario];
  const lines: string[] = [
    'INTERLOCK V6 — SIMULATED RECOVERY REPORT',
    'Simulated environment — fictional data only — no real files modified.',
    '',
    `Scenario   : ${spec.label}`,
    `Project    : ${spec.project} (fictional)`,
    `Phase      : ${state.phase}`,
    `Progress   : ${state.progress}%`,
    `Approval   : ${state.approval}`,
    '',
    'FILES',
  ];

  for (const file of state.files) {
    const matches = file.current === file.original;
    lines.push(
      ` - ${file.path}: ${matches ? 'matches pre-incident content' : 'differs from pre-incident content'} (changed by ${file.changedBy})`,
    );
  }

  if (state.refusal) {
    lines.push('', 'REFUSAL', ` - precondition: ${state.refusal.id}`, ` - ${state.refusal.detail}`);
  }

  if (state.conflict) {
    lines.push(
      '',
      'CONFLICT',
      ` - path: ${state.conflict.path}`,
      ` - expected: ${state.conflict.expected}`,
      ` - found: ${state.conflict.found}`,
      ` - why unsafe: ${state.conflict.reason}`,
    );
  }

  if (state.verification) {
    lines.push(
      '',
      'VERIFICATION',
      ` - status: ${state.verification.status}`,
      ` - summary: ${state.verification.summary}`,
      ` - restored: ${state.verification.restored}/${state.verification.checked}`,
    );
    for (const digest of state.verification.digests) {
      lines.push(` - ${digest.path}: sha256=${digest.sha256} ${digest.matches ? 'MATCH' : 'MISMATCH'}`);
    }
  } else {
    lines.push('', 'VERIFICATION: not performed in this run');
  }

  lines.push('', 'EVENT LOG');
  for (const event of state.events) {
    lines.push(` ${event.time} [${event.level}] ${event.message}`);
  }

  lines.push('', 'This report contains fictional simulation data only.');
  return lines.join('\n');
}
