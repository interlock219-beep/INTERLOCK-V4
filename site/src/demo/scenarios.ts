import type { ScenarioSpec } from './types';

/**
 * Four deterministic fictional scenarios.
 *
 * Everything below is invented sample data for an imaginary project called
 * `orbit-dashboard`. No real repository, customer, or visitor file appears
 * here, and nothing in this file can be executed.
 */

const ORBIT_CONFIG_ORIGINAL = `export const API_URL = "http://localhost:8080";
export const RETRIES = 3;
export const TIMEOUT_MS = 5000;
`;

const ORBIT_CONFIG_AGENT = `export const API_URL = "http://api.internal:9999";
export const RETRIES = 50;
export const TIMEOUT_MS = 30000;
export const DEBUG_VERBOSE = true;
`;

const ORBIT_CONFIG_HUMAN = `export const API_URL = "http://localhost:8081";
export const RETRIES = 4;
export const TIMEOUT_MS = 5000;
export const FEATURE_FLAG_BANNER = true;
`;

const CLIENT_ORIGINAL = `export async function request(path: string) {
  const res = await fetch(API_URL + path);
  if (!res.ok) throw new Error("request failed");
  return res.json();
}
`;

const CLIENT_AGENT = `export async function request(path: string) {
  const res = await fetch(API_URL + path, { cache: "no-store" });
  return res.json();
}
`;

const PACKAGE_ORIGINAL = `{
  "name": "orbit-dashboard",
  "version": "1.4.0",
  "scripts": {
    "build": "vite build",
    "test": "vitest run"
  }
}
`;

const PACKAGE_AGENT = `{
  "name": "orbit-dashboard",
  "version": "2.0.0-rc1",
  "scripts": {
    "build": "vite build",
    "test": "vitest run",
    "postinstall": "node ./tools/bootstrap.js"
  }
}
`;

const VERIFY_DOC_ORIGINAL = `# Verification checklist

1. Run the build.
2. Compare SHA-256 digests of released artifacts.
3. Record the result in the release log.
`;

const ROUTES_ORIGINAL = `export const routes = ["/", "/settings", "/billing"];
`;

const ROUTES_AGENT = `export const routes = ["/", "/settings", "/billing", "/internal-debug"];
`;

const DEPLOY_ENV_ORIGINAL = `DEPLOY_WEBHOOK=https://hooks.example.test/rotate
DEPLOY_TOKEN=fictional-token-not-real
`;

const DEPLOY_ENV_AGENT = `DEPLOY_WEBHOOK=https://hooks.example.test/rotate
DEPLOY_TOKEN=fictional-token-rotated-by-agent
ALLOW_INSECURE=true
`;

export const SUCCESS_SCENARIO: ScenarioSpec = {
  id: 'success',
  label: 'Successful recovery',
  title: 'Agent overwrote four project files',
  summary:
    'A fictional coding agent rewrote configuration, client code, package metadata and deleted the verification checklist. All pre-action evidence exists, so the recovery plan is safe to execute.',
  expectation:
    'Every file returns to its pre-incident content, the integrity checks pass, and no staging residue remains.',
  project: 'orbit-dashboard',
  files: [
    {
      path: 'src/config.ts',
      original: ORBIT_CONFIG_ORIGINAL,
      current: ORBIT_CONFIG_AGENT,
      changedBy: 'agent',
      evidenceCaptured: true,
    },
    {
      path: 'src/api/client.ts',
      original: CLIENT_ORIGINAL,
      current: CLIENT_AGENT,
      changedBy: 'agent',
      evidenceCaptured: true,
    },
    {
      path: 'package.json',
      original: PACKAGE_ORIGINAL,
      current: PACKAGE_AGENT,
      changedBy: 'agent',
      evidenceCaptured: true,
    },
    {
      path: 'docs/VERIFICATION.md',
      original: VERIFY_DOC_ORIGINAL,
      current: '',
      changedBy: 'agent',
      evidenceCaptured: true,
      deleted: true,
    },
  ],
  timeline: [
    {
      time: '10:24:11',
      title: 'Incident detected',
      detail: 'Agent session agent-007 modified 4 files in orbit-dashboard.',
      kind: 'agent',
    },
    {
      time: '10:24:32',
      title: 'Pre-action evidence matched',
      detail: 'Captured snapshots exist for all 4 targets.',
      kind: 'system',
    },
    {
      time: '10:25:06',
      title: 'Recovery plan drafted',
      detail: '4 restore operations, 0 skips, 0 conflicts.',
      kind: 'system',
    },
    {
      time: '10:28:17',
      title: 'Verification scheduled',
      detail: 'Digest comparison runs after the restore completes.',
      kind: 'system',
    },
  ],
};

export const CONFLICT_SCENARIO: ScenarioSpec = {
  id: 'conflict',
  label: 'File changed by a person',
  title: 'A human edited the file after the agent',
  summary:
    'The agent rewrote two files, then a developer edited src/config.ts by hand. The current content no longer matches what the recovery plan expects, so automatic recovery would destroy the human edit.',
  expectation:
    'The conflict is detected before anything is written, the normal recovery path is blocked, and only review or reset is available.',
  project: 'orbit-dashboard',
  files: [
    {
      path: 'src/config.ts',
      original: ORBIT_CONFIG_ORIGINAL,
      current: ORBIT_CONFIG_HUMAN,
      changedBy: 'human',
      evidenceCaptured: true,
      humanEdit: true,
    },
    {
      path: 'src/routes.ts',
      original: ROUTES_ORIGINAL,
      current: ROUTES_AGENT,
      changedBy: 'agent',
      evidenceCaptured: true,
    },
    {
      path: 'package.json',
      original: PACKAGE_ORIGINAL,
      current: PACKAGE_AGENT,
      changedBy: 'agent',
      evidenceCaptured: true,
    },
  ],
  timeline: [
    {
      time: '11:02:14',
      title: 'Incident detected',
      detail: 'Agent session agent-011 modified 2 files in orbit-dashboard.',
      kind: 'agent',
    },
    {
      time: '11:04:40',
      title: 'Human edit recorded',
      detail: 'Developer edited src/config.ts 42 seconds after the agent action.',
      kind: 'human',
    },
    {
      time: '11:05:12',
      title: 'Drift found during pre-flight',
      detail: 'Current bytes differ from the state the plan expects.',
      kind: 'error',
    },
  ],
  conflict: {
    path: 'src/config.ts',
    expected: 'bytes matching the pre-action snapshot (3 lines)',
    found: 'human-authored content with FEATURE_FLAG_BANNER (4 lines)',
    reason:
      'A human edit landed after the agent action. Restoring the original would silently discard that work.',
  },
};

export const REFUSAL_SCENARIO: ScenarioSpec = {
  id: 'refusal',
  label: 'Unsafe recovery request',
  title: 'Plan includes a file with no pre-action evidence',
  summary:
    'The agent touched a deployment environment file that was never captured before the action. Interlock cannot restore content it never observed, so the plan is refused instead of guessed.',
  expectation:
    'A failed precondition is shown, simulated recovery is refused, and the normal recovery path cannot continue.',
  project: 'orbit-dashboard',
  files: [
    {
      path: 'secrets/deploy.env',
      original: DEPLOY_ENV_ORIGINAL,
      current: DEPLOY_ENV_AGENT,
      changedBy: 'agent',
      evidenceCaptured: false,
    },
    {
      path: 'src/config.ts',
      original: ORBIT_CONFIG_ORIGINAL,
      current: ORBIT_CONFIG_AGENT,
      changedBy: 'agent',
      evidenceCaptured: true,
    },
  ],
  timeline: [
    {
      time: '13:41:05',
      title: 'Incident detected',
      detail: 'Agent session agent-014 modified 2 files in orbit-dashboard.',
      kind: 'agent',
    },
    {
      time: '13:41:37',
      title: 'Evidence gap found',
      detail: 'secrets/deploy.env has no captured pre-action snapshot.',
      kind: 'error',
    },
    {
      time: '13:41:58',
      title: 'Safety gate engaged',
      detail: 'Recovery refuses to invent content for a file it never observed.',
      kind: 'system',
    },
  ],
  precondition: {
    id: 'pre-action-evidence-present',
    label: 'Every restore target has pre-action evidence',
    detail:
      'secrets/deploy.env has no captured pre-action snapshot, so its original bytes cannot be proven. Guessing a restore value would be an unverified write.',
    remediation:
      'Restore the file manually from your own backup, or re-run the workflow with evidence capture enabled for that path.',
  },
};

export const INTERRUPTED_SCENARIO: ScenarioSpec = {
  id: 'interrupted',
  label: 'Recovery interrupted',
  title: 'The simulated worker stops halfway through',
  summary:
    'Recovery starts normally, then the in-memory worker is interrupted after restoring two of four files. The workflow is incomplete, and incomplete work must never be reported as success.',
  expectation:
    'Verification shows a partial restore, the interface stays in an incomplete state, and success is only reported after a resume plus a passing check.',
  project: 'orbit-dashboard',
  files: [
    {
      path: 'src/config.ts',
      original: ORBIT_CONFIG_ORIGINAL,
      current: ORBIT_CONFIG_AGENT,
      changedBy: 'agent',
      evidenceCaptured: true,
    },
    {
      path: 'src/api/client.ts',
      original: CLIENT_ORIGINAL,
      current: CLIENT_AGENT,
      changedBy: 'agent',
      evidenceCaptured: true,
    },
    {
      path: 'package.json',
      original: PACKAGE_ORIGINAL,
      current: PACKAGE_AGENT,
      changedBy: 'agent',
      evidenceCaptured: true,
    },
    {
      path: 'docs/VERIFICATION.md',
      original: VERIFY_DOC_ORIGINAL,
      current: '',
      changedBy: 'agent',
      evidenceCaptured: true,
      deleted: true,
    },
  ],
  timeline: [
    {
      time: '15:12:03',
      title: 'Incident detected',
      detail: 'Agent session agent-007 modified 4 files in orbit-dashboard.',
      kind: 'agent',
    },
    {
      time: '15:12:44',
      title: 'Recovery started',
      detail: 'Two restore operations completed.',
      kind: 'system',
    },
    {
      time: '15:12:51',
      title: 'Worker interrupted',
      detail: 'Simulated interruption: the remaining two operations never ran.',
      kind: 'error',
    },
  ],
  interruptAfter: 55,
};

export const SCENARIOS: Record<string, ScenarioSpec> = {
  success: SUCCESS_SCENARIO,
  conflict: CONFLICT_SCENARIO,
  refusal: REFUSAL_SCENARIO,
  interrupted: INTERRUPTED_SCENARIO,
};

export const SCENARIO_ORDER: ScenarioSpec[] = [
  SUCCESS_SCENARIO,
  CONFLICT_SCENARIO,
  REFUSAL_SCENARIO,
  INTERRUPTED_SCENARIO,
];
