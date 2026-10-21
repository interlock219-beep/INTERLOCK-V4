/**
 * Configuration reading and validation (pure, no `vscode` import).
 *
 * Invalid values never throw: they are reported as issues so the UI can show
 * actionable fixes while falling back to safe defaults.
 */

export interface InterlockSettings {
  /** Explicit interpreter path/command; empty means auto-detect. */
  pythonPath: string;
  /** Interlock checkout root (directory containing the `app` package). */
  engineRoot: string;
  autoDetectEngine: boolean;
  timeoutSeconds: number;
  maxBaselineBytes: number;
  showGitChanges: boolean;
  allowedDocumentationUrls: string[];
  /**
   * Automatically establish or refresh recovery baselines at documented safe
   * checkpoints (workspace analysis with no evidence, and immediately before
   * an Interlock-managed recovery). Never overwrites usable evidence.
   */
  automaticBaselineProtection: boolean;
  /** Extra workspace-relative patterns excluded from automatic capture. */
  baselineExclusions: string[];
  /**
   * Approver identity recorded in the engine's audit result for a recovery.
   * The engine requires a non-empty identity, but nobody should have to type
   * it on every recovery: when this is set, recovery uses it (and says so in
   * the confirmation) instead of asking.
   */
  approverIdentity: string;
}

export interface ConfigIssue {
  key: string;
  message: string;
}

export const DEFAULTS: InterlockSettings = {
  pythonPath: '',
  engineRoot: '',
  autoDetectEngine: true,
  timeoutSeconds: 60,
  maxBaselineBytes: 5 * 1024 * 1024,
  showGitChanges: true,
  allowedDocumentationUrls: ['https://github.com/interlock219-beep/INTERLOCK-V4'],
  automaticBaselineProtection: true,
  baselineExclusions: [],
  approverIdentity: '',
};

const MIN_TIMEOUT_SECONDS = 5;
const MAX_TIMEOUT_SECONDS = 900;
const MIN_BASELINE_BYTES = 1024;
const MAX_BASELINE_BYTES = 200 * 1024 * 1024;
const MAX_APPROVER_IDENTITY_LENGTH = 200;

export interface ConfigResult {
  settings: InterlockSettings;
  issues: ConfigIssue[];
}

/** Validate raw setting values, returning safe defaults plus any issues. */
export function normalizeSettings(raw: Record<string, unknown>): ConfigResult {
  const issues: ConfigIssue[] = [];
  const settings: InterlockSettings = { ...DEFAULTS };

  const pythonPath = asTrimmedString(raw['pythonPath']);
  if (pythonPath !== undefined) {
    if (hasControlChars(pythonPath)) {
      issues.push({
        key: 'interlock.pythonPath',
        message: 'Interpreter path contains line breaks or NUL characters and was ignored.',
      });
    } else {
      settings.pythonPath = pythonPath;
    }
  }

  const engineRoot = asTrimmedString(raw['engineRoot']);
  if (engineRoot !== undefined) {
    if (hasControlChars(engineRoot)) {
      issues.push({
        key: 'interlock.engineRoot',
        message: 'Engine root contains line breaks or NUL characters and was ignored.',
      });
    } else {
      settings.engineRoot = engineRoot;
    }
  }

  const autoDetect = raw['autoDetectEngine'];
  if (typeof autoDetect === 'boolean') {
    settings.autoDetectEngine = autoDetect;
  }

  const timeout = raw['timeoutSeconds'];
  if (typeof timeout === 'number' && Number.isFinite(timeout)) {
    if (timeout < MIN_TIMEOUT_SECONDS || timeout > MAX_TIMEOUT_SECONDS) {
      issues.push({
        key: 'interlock.timeoutSeconds',
        message: `Timeout must be between ${MIN_TIMEOUT_SECONDS} and ${MAX_TIMEOUT_SECONDS} seconds; using ${DEFAULTS.timeoutSeconds}s.`,
      });
    } else {
      settings.timeoutSeconds = Math.floor(timeout);
    }
  } else if (timeout !== undefined && timeout !== null && timeout !== '') {
    issues.push({
      key: 'interlock.timeoutSeconds',
      message: 'Timeout must be a number; using the default.',
    });
  }

  const maxBytes = raw['maxBaselineBytes'];
  if (typeof maxBytes === 'number' && Number.isFinite(maxBytes)) {
    if (maxBytes < MIN_BASELINE_BYTES || maxBytes > MAX_BASELINE_BYTES) {
      issues.push({
        key: 'interlock.maxBaselineBytes',
        message: `Baseline size limit must be between ${MIN_BASELINE_BYTES} and ${MAX_BASELINE_BYTES} bytes; using ${DEFAULTS.maxBaselineBytes}.`,
      });
    } else {
      settings.maxBaselineBytes = Math.floor(maxBytes);
    }
  }

  const gitChanges = raw['showGitChanges'];
  if (typeof gitChanges === 'boolean') {
    settings.showGitChanges = gitChanges;
  }

  const autoProtection = raw['automaticBaselineProtection'];
  if (typeof autoProtection === 'boolean') {
    settings.automaticBaselineProtection = autoProtection;
  }

  const exclusions = raw['baselineExclusions'];
  if (Array.isArray(exclusions)) {
    const accepted: string[] = [];
    for (const entry of exclusions) {
      const candidate = typeof entry === 'string' ? entry.trim() : '';
      if (!candidate) {
        continue;
      }
      if (hasControlChars(candidate) || candidate.length > 200) {
        issues.push({
          key: 'interlock.baselineExclusions',
          message: 'An exclusion pattern was ignored (control characters or too long).',
        });
        continue;
      }
      if (accepted.length >= 50) {
        issues.push({
          key: 'interlock.baselineExclusions',
          message: 'At most 50 exclusion patterns are kept; the rest were ignored.',
        });
        break;
      }
      accepted.push(candidate);
    }
    // User exclusions are strictly additive: secret/credential markers stay
    // enforced in `protection.ts` and cannot be removed through settings.
    settings.baselineExclusions = accepted;
  }

  const urls = raw['allowedDocumentationUrls'];
  if (Array.isArray(urls)) {
    const accepted: string[] = [];
    for (const entry of urls) {
      const candidate = typeof entry === 'string' ? entry.trim() : '';
      if (!candidate) {
        continue;
      }
      const parsed = safeParseUrl(candidate);
      if (!parsed || parsed.protocol !== 'https:') {
        issues.push({
          key: 'interlock.allowedDocumentationUrls',
          message: `Only https:// documentation URLs are allowed; rejected "${candidate}".`,
        });
        continue;
      }
      if (accepted.length >= 20) {
        break;
      }
      accepted.push(parsed.toString());
    }
    if (accepted.length > 0) {
      settings.allowedDocumentationUrls = accepted;
    } else {
      issues.push({
        key: 'interlock.allowedDocumentationUrls',
        message: 'No valid https URL remained; the repository URL default is used.',
      });
    }
  }

  const approver = asTrimmedString(raw['approverIdentity']);
  if (approver !== undefined) {
    if (hasControlChars(approver)) {
      issues.push({
        key: 'interlock.approverIdentity',
        message: 'Approver identity contains line breaks or NUL characters and was ignored.',
      });
    } else if (approver.length > MAX_APPROVER_IDENTITY_LENGTH) {
      issues.push({
        key: 'interlock.approverIdentity',
        message: `Approver identity is longer than ${MAX_APPROVER_IDENTITY_LENGTH} characters and was ignored.`,
      });
    } else {
      settings.approverIdentity = approver;
    }
  }

  return { settings, issues };
}

export function asTrimmedString(value: unknown): string | undefined {
  if (typeof value !== 'string') {
    return undefined;
  }
  return value.trim();
}

export function hasControlChars(value: string): boolean {
   
  return /[\u0000-\u001f\u007f]/.test(value);
}

export function safeParseUrl(value: string): URL | undefined {
  try {
    return new URL(value);
  } catch {
    return undefined;
  }
}

/**
 * True when `url` may be opened by the documentation command: https only and
 * the origin must be listed in the user-approved allow-list.
 */
export function isAllowedDocumentationUrl(url: string, allowList: string[]): boolean {
  const parsed = safeParseUrl(url);
  if (!parsed || parsed.protocol !== 'https:' || !parsed.hostname) {
    return false;
  }
  return allowList.some((entry) => {
    const allowed = safeParseUrl(entry);
    return (
      allowed !== undefined &&
      allowed.protocol === 'https:' &&
      allowed.origin === parsed.origin
    );
  });
}
