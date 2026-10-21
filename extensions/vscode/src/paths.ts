/**
 * Extension-side workspace confinement pre-checks.
 *
 * These are deliberately conservative *pre*-checks that mirror the rules the
 * engine enforces in `sdk.workspace_protection.path_security` and in
 * `FilesystemRecoveryAdapter._assert_contained`. They are not a replacement:
 * every command still passes the real path to the engine, which remains the
 * authority and may refuse independently.
 */

import * as path from 'path';

/** Strip a `file:`-style scheme prefix the engine also accepts. */
export function stripResourceScheme(value: string): string {
  const match = /^(file|path|fs):/i.exec(value);
  return match ? value.slice(match[0].length) : value;
}

/**
 * True when a workspace-relative resource is syntactically acceptable:
 * non-empty, no `..`, no absolute/UNC/drive-rooted form, no NUL.
 */
export function isAcceptableRelativeResource(rel: string): boolean {
  if (!rel || rel.trim() === '') {
    return false;
  }
   
  if (/[\u0000-\u001f]/.test(rel)) {
    return false;
  }
  const normalized = stripResourceScheme(rel).replace(/\\/g, '/');
  if (normalized.startsWith('/') || normalized.startsWith('//')) {
    return false;
  }
  if (/^[A-Za-z]:/.test(normalized)) {
    return false;
  }
  const segments = normalized.split('/').filter((segment) => segment.length > 0);
  if (segments.includes('..')) {
    return false;
  }
  return segments.length > 0;
}

/** Case-aware containment test used on the current platform. */
export function isInside(root: string, candidate: string): boolean {
  const normalizedRoot = normalizeForCompare(root);
  const normalizedCandidate = normalizeForCompare(candidate);
  if (normalizedRoot === normalizedCandidate) {
    return true;
  }
  const withSep = normalizedRoot.endsWith(path.sep)
    ? normalizedRoot
    : normalizedRoot + path.sep;
  return normalizedCandidate.startsWith(withSep);
}

/**
 * Resolve `candidate` against `root` and return a workspace-relative path, or
 * `null` when it escapes the workspace or is syntactically refused.
 */
export function resolveWithin(root: string, candidate: string): string | null {
  const cleaned = stripResourceScheme(candidate);
  if (!cleaned || cleaned.includes('\u0000')) {
    return null;
  }
  if (cleaned.startsWith('\\\\')) {
    return null; // UNC
  }
  const base = path.resolve(root);
  const resolved = path.isAbsolute(cleaned) ? path.resolve(cleaned) : path.resolve(base, cleaned);
  if (!isInside(base, resolved)) {
    return null;
  }
  const relative = path.relative(base, resolved);
  if (relative === '') {
    return null; // the workspace root itself is not a target file
  }
  return relative.split(path.sep).join('/');
}

/** Convert an absolute path inside the workspace to a `file:` resource id. */
export function toResourceId(workspaceRoot: string, absolutePath: string): string | null {
  const rel = resolveWithin(workspaceRoot, absolutePath);
  return rel === null ? null : `file:${rel}`;
}

function normalizeForCompare(value: string): string {
  const resolved = path.resolve(value);
  return process.platform === 'win32' ? resolved.toLowerCase() : resolved;
}
