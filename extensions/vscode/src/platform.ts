/**
 * Compatibility reporting that keeps two different claims apart:
 *
 *  - **extension support**: where this VS Code extension package runs
 *    (TypeScript/Node - it installs on every platform VS Code supports);
 *  - **engine support**: what `docs/operations/SUPPORTED_PLATFORMS.md`
 *    actually evidences for the Interlock recovery engine.
 *
 * The extension must never present "the package installs here" as "the engine
 * is validated here".
 */

export type SupportStatus =
  | 'tested_primary'
  | 'declared_ci_pending'
  | 'untested'
  | 'unsupported'
  | 'unknown';

export interface PlatformInput {
  system: string;
  machine: string;
  filesystem?: string;
  driveType?: string;
  longPathsEnabled?: number | null;
  pathLength?: number;
}

export interface PlatformVerdict {
  /** Engine-side verdict (the strict one). */
  engineStatus: SupportStatus;
  detail: string;
  warnings: string[];
  /** True only for the recorded primary environment. */
  engineValidated: boolean;
  /** The extension package itself can run here. */
  extensionRunsHere: boolean;
}

const UNSUPPORTED_FILESYSTEMS = new Set([
  'fat',
  'fat32',
  'exfat',
  'vfat',
  'msdos',
  'smbfs',
  'cifs',
  'nfs',
  'nfs4',
  'afp',
]);

/** Mirror of the repository's support matrix, used when the engine is absent. */
export function platformVerdict(input: PlatformInput): PlatformVerdict {
  // Node's os.type() reports "Windows_NT"; accept that and plain "Windows".
  const system = input.system.toLowerCase() === 'windows_nt' ? 'windows' : input.system.toLowerCase();
  const machine = input.machine.toLowerCase();
  const fs = (input.filesystem ?? 'unknown').toLowerCase();
  const drive = (input.driveType ?? 'unknown').toLowerCase();
  const warnings: string[] = [];
  let engineStatus: SupportStatus = 'untested';
  let detail = 'No recorded evidence for this environment.';

  if (system === 'windows') {
    if (machine === 'amd64' || machine === 'x64' || machine === 'x86_64') {
      engineStatus = 'tested_primary';
      detail =
        'Windows x64 + NTFS + Python 3.11.9 is the recorded primary test environment.';
    } else {
      engineStatus = 'untested';
      detail = `Windows on ${input.machine}: no engine evidence recorded.`;
    }
    if (drive === 'network' || ['smbfs', 'cifs', 'nfs', 'nfs4'].includes(fs)) {
      engineStatus = 'unsupported';
      detail = 'Network/redirected drive: no local atomic-replace guarantee.';
      warnings.push('Workspace is on a network drive - the engine declares this UNSUPPORTED.');
    } else if (UNSUPPORTED_FILESYSTEMS.has(fs)) {
      engineStatus = 'unsupported';
      detail = `Filesystem ${input.filesystem} does not guarantee rename durability.`;
      warnings.push(
        `Filesystem ${input.filesystem} is declared UNSUPPORTED by the engine support matrix.`,
      );
    }
    if (input.longPathsEnabled === 0) {
      warnings.push(
        'Windows long paths are disabled (LongPathsEnabled=0); paths over 260 chars are untested.',
      );
    }
    if (typeof input.pathLength === 'number' && input.pathLength > 260) {
      warnings.push('Workspace path exceeds 260 characters - untested for the engine.');
    }
  } else if (system === 'darwin') {
    if (machine === 'arm64' || machine === 'aarch64') {
      engineStatus = 'declared_ci_pending';
      detail = 'macOS arm64: dependencies resolved; engine validation still pending CI.';
      warnings.push('macOS engine support is DECLARED - not yet validated by executed CI.');
    } else {
      engineStatus = 'unsupported';
      detail = 'macOS Intel: dependency-blocked for the engine (no cryptography wheel).';
      warnings.push('macOS Intel is dependency-blocked for the engine.');
    }
  } else if (system === 'linux') {
    engineStatus = 'declared_ci_pending';
    detail = 'Linux x64: declared support; the CI job has never executed.';
    warnings.push('Linux engine support is DECLARED - not yet validated by executed CI.');
  } else {
    detail = `Unrecognized platform: ${input.system}.`;
  }

  return {
    engineStatus,
    detail,
    warnings,
    engineValidated: engineStatus === 'tested_primary',
    extensionRunsHere: true,
  };
}

export function statusLabel(status: SupportStatus): string {
  switch (status) {
    case 'tested_primary':
      return 'TESTED - PRIMARY';
    case 'declared_ci_pending':
      return 'DECLARED - CI PENDING';
    case 'unsupported':
      return 'UNSUPPORTED';
    case 'untested':
      return 'UNTESTED';
    default:
      return 'UNKNOWN';
  }
}
