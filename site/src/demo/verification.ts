import type { FictionalFile, VerificationResult } from './types';
import { sha256 } from './text';

/**
 * Verification runs over the FICTIONAL file contents held in browser memory.
 * Nothing here opens, reads, or writes a real file, and the result is derived
 * from the actual simulation state — never hardcoded.
 */
export function verifyIntegrity(files: FictionalFile[]): VerificationResult {
  const digests = files.map((file) => {
    const expected = sha256(file.original);
    const actual = sha256(file.current);
    return { path: file.path, sha256: actual, matches: expected === actual };
  });

  const mismatched = files.filter((f) => f.current !== f.original).map((f) => f.path);
  const restored = files.length - mismatched.length;
  const unresolvedConflicts = files.filter((f) => f.humanEdit && f.current !== f.original).length;
  const residue = files.filter((f) => f.path.endsWith('.recovery_tmp')).map((f) => f.path);
  const pass = mismatched.length === 0 && unresolvedConflicts === 0 && residue.length === 0;

  const summary = pass
    ? `All ${files.length} fictional files match their pre-incident content.`
    : `${restored} of ${files.length} fictional files match; ${mismatched.length} still differ.`;

  return {
    status: pass ? 'pass' : 'fail',
    checked: files.length,
    restored,
    mismatched,
    unresolvedConflicts,
    residue,
    digests,
    summary,
  };
}

/** Restores one fictional file to its pre-incident content. */
export function restoreFile(file: FictionalFile): FictionalFile {
  return { ...file, current: file.original, deleted: false, changedBy: 'none' };
}
