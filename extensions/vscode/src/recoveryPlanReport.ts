/**
 * The engine's recovery plan report (Markdown), rendered from a *validated*
 * engine plan. Pure and dependency-free so it can be unit-tested headlessly
 * and reused by both the "Preview Recovery" and "View Recovery Plan" flows.
 *
 * This report is the audit trail - the side-by-side diff is the review
 * experience. It deliberately contains verdicts, hashes and evidence only:
 * the engine strips file contents from plan payloads (`slim_snapshot`), so
 * the exact bytes for the diff come from the stored baseline instead
 * (see `recoveryPlan.ts`).
 */

import { asArray, asBool, asDict, asStr, asStringArray } from './jsonValues';
import { truncate } from './redact';

export interface PlanSummary {
  wouldSucceed: boolean;
  conflict: string;
  drift: string;
  changed: boolean;
  operation: string | null;
  baselineHash: string | null;
  currentHash: string | null;
  currentExists: boolean;
  baselineCapturedAt: string | null;
}

export function readPlanSummary(plan: Record<string, unknown>): PlanSummary {
  const baseline = asDict(plan['baseline']);
  const current = asDict(plan['current']);
  return {
    wouldSucceed: asBool(plan['would_succeed']),
    conflict: asStr(plan['conflict_status']) ?? 'unknown',
    drift: asStr(plan['drift_status']) ?? 'unknown',
    changed: asBool(asDict(plan['diff'])['changed']),
    operation: asStr(plan['operation']),
    baselineHash: asStr(baseline['hash']),
    currentHash: asStr(current['hash']),
    currentExists: asBool(plan['current_exists']),
    baselineCapturedAt: asStr(plan['baseline_captured_at']),
  };
}

export function buildPlanMarkdown(
  resource: string,
  workspaceRoot: string,
  plan: Record<string, unknown>,
): string {
  const summary = readPlanSummary(plan);
  const diff = asDict(plan['diff']);
  const warnings = asStringArray(plan['warnings']);
  const human = asDict(plan['human_change_analysis']);

  const lines: string[] = [
    `# Interlock recovery plan preview`,
    '',
    `**Resource:** \`${resource}\`  `,
    `**Workspace:** \`${workspaceRoot}\`  `,
    `**Operation:** ${summary.operation ?? 'unknown'}  `,
    `**Preview generated:** ${new Date().toISOString()}`,
    '',
    '> Read-only preview produced by the Interlock engine. **No file was changed.**',
    '',
    '## Engine verdict',
    '',
    '| Check | Result |',
    '| --- | --- |',
    `| Simulation would succeed | ${summary.wouldSucceed ? 'yes' : 'NO'} |`,
    `| Conflict status | \`${summary.conflict}\` |`,
    `| Drift status | \`${summary.drift}\` |`,
    `| Reversibility | \`${asStr(plan['reversibility']) ?? 'unknown'}\` |`,
    `| Current state matches baseline | ${asBool(plan['matches_baseline']) ? 'yes (no changes to undo)' : 'NO - changes detected'} |`,
    `| Requires approval | yes |`,
    '',
    '## State comparison',
    '',
    `- Baseline hash: \`${summary.baselineHash ?? 'unknown'}\` (captured ${summary.baselineCapturedAt ?? 'unknown'})`,
    `- Current hash:  \`${summary.currentHash ?? 'file missing'}\``,
    `- Current file exists: ${summary.currentExists ? 'yes' : 'no'}`,
    '',
  ];

  if (asBool(diff['changed'])) {
    lines.push('## Diff (engine-computed)', '');
    const structural = asDict(diff['structural']);
    if (Object.keys(structural).length > 0) {
      lines.push('**Structural changes**', '', '```json', JSON.stringify(structural, null, 2), '```', '');
    }
    const semantic = asArray(diff['semantic']);
    if (semantic.length > 0) {
      lines.push('**Semantic changes**', '');
      for (const entry of semantic.slice(0, 40).map(asDict)) {
        const before = truncate(JSON.stringify(entry['before'] ?? null), 200);
        const after = truncate(JSON.stringify(entry['after'] ?? null), 200);
        lines.push(`- \`${asStr(entry['path']) ?? '?'}\`: ${asStr(entry['change']) ?? 'changed'}`);
        lines.push(`  - before: \`${before.replace(/`/g, "'")}\``);
        lines.push(`  - after: \`${after.replace(/`/g, "'")}\``);
      }
      if (semantic.length > 40) {
        lines.push(`- … ${semantic.length - 40} more entries omitted`);
      }
      lines.push('');
    }
    const binary = asDict(diff['binary']);
    if (asBool(binary['changed'])) {
      lines.push('**Binary/content changes**', '');
      lines.push(`- before hash: \`${asStr(binary['before_hash']) ?? 'n/a'}\``);
      lines.push(`- after hash: \`${asStr(binary['after_hash']) ?? 'n/a'}\``, '');
    }
  } else {
    lines.push('_No differences between the baseline and the current file._', '');
  }

  if (Object.keys(human).length > 0) {
    lines.push('## Human-change analysis', '', '```json', truncate(JSON.stringify(human, null, 2), 3000), '```', '');
  }

  if (warnings.length > 0) {
    lines.push('## Engine warnings', '');
    for (const warning of warnings) {
      lines.push(`- ${warning}`);
    }
    lines.push('');
  }

  lines.push(
    '## What happens next',
    '',
    '1. The side-by-side diff is the review: the current file on the left, the exact',
    '   proposed recovery (the stored baseline bytes, hash-verified) on the right.',
    '   Opening or closing a diff never changes a file.',
    '2. "Interlock: Apply Recovery" re-runs this plan, lists every affected file and',
    '   asks for one explicit confirmation. A change/ticket reference is optional.',
    '3. The approver identity recorded in the engine result comes from the',
    '   "interlock.approverIdentity" setting, the value confirmed earlier in this',
    '   session, or your git user.name - it is typed only when none of those exists.',
    '4. The engine re-checks conflicts, drift, and containment immediately before writing.',
    '5. After writing, the engine verifies the bytes against the baseline and the extension',
    '   re-checks the hash independently. Success is reported only if both agree.',
    '',
    `Evidence was captured at preview time${
      asStr(plan['evidence_captured_at']) ? ` (${asStr(plan['evidence_captured_at'])})` : ''
    }. If the file changes afterwards, execution is refused - preview again to re-observe.`,
    '',
  );

  return lines.join('\n');
}
