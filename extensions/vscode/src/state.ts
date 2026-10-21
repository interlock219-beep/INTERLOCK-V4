/**
 * Extension-private persistence: recovery baselines and last-known results.
 *
 * Baselines contain the engine's own before-state snapshot (including file
 * contents, base64-encoded) - they live ONLY in the extension's private
 * storage directory, are never written into the user's workspace, and are
 * never written to the output log.
 *
 * Baseline documents are produced by the ENGINE (which seals them with an
 * integrity hash) and stored verbatim. The extension never builds a baseline
 * document itself, and the engine re-verifies the seal before any baseline is
 * used to plan, preview, recover or verify.
 */

import * as crypto from 'crypto';
import * as fs from 'fs/promises';
import * as path from 'path';

import { asStr } from './jsonValues';

export const BASELINE_FORMAT = 'interlock-baseline-v2';

export interface BaselineDocument {
  format: string;
  workspace: string;
  resource: string;
  captured_at?: string;
  snapshot: Record<string, unknown>;
  /** Engine integrity seal (every document the engine produced carries it). */
  baseline_hash?: string;
  baseline_hash_spec?: string;
}

/**
 * Convert the engine's sealed baseline document into the stored shape.
 *
 * Returns null when the value is not a usable baseline document. The engine's
 * own fields (including the integrity seal) are preserved verbatim: the
 * extension never rewrites a document the engine produced.
 */
export function toBaselineDocument(raw: unknown): BaselineDocument | null {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
    return null;
  }
  const record = raw as Record<string, unknown>;
  const format = asStr(record['format']);
  const workspace = asStr(record['workspace']);
  const resource = asStr(record['resource']);
  const snapshot = record['snapshot'];
  if (
    !format ||
    !workspace ||
    !resource ||
    snapshot === null ||
    typeof snapshot !== 'object' ||
    Array.isArray(snapshot)
  ) {
    return null;
  }
  return {
    ...record,
    format,
    workspace,
    resource,
    captured_at: asStr(record['captured_at']) ?? undefined,
    snapshot: snapshot as Record<string, unknown>,
  } as BaselineDocument;
}

export interface BaselineSummary {
  workspace: string;
  resource: string;
  file: string;
  hash: string | null;
  size: number | null;
  capturedAt: string | null;
}

/** One stored baseline, read once: metadata plus the stored snapshot. */
export interface BaselineEntry {
  resource: string;
  file: string;
  hash: string | null;
  size: number | null;
  capturedAt: string | null;
  /** The stored snapshot, or null when the document could not be used. */
  snapshot: Record<string, unknown> | null;
}

/**
 * The canonical spelling of a workspace path.
 *
 * VS Code hands out `c:\work\dir` (lower-case drive letter) while the engine
 * resolves the very same folder to `C:\work\dir`. The baseline store is keyed
 * by the workspace path, so both sides have to agree on ONE spelling - the
 * engine's. On POSIX the path is case-sensitive and is used exactly as given.
 */
export function canonicalWorkspace(workspace: string): string {
  const resolved = path.resolve(workspace);
  if (process.platform !== 'win32') {
    return resolved;
  }
  return resolved.charAt(0).toUpperCase() + resolved.slice(1);
}

/** True when two workspace paths name the same folder. */
export function sameWorkspace(
  left: string | null | undefined,
  right: string | null | undefined,
): boolean {
  if (left === null || left === undefined || right === null || right === undefined) {
    return false;
  }
  return canonicalWorkspace(left) === canonicalWorkspace(right);
}

export class BaselineStore {
  private readonly directory: string;

  constructor(storageRootAbsolute: string) {
    this.directory = path.join(storageRootAbsolute, 'baselines');
  }

  static key(workspace: string, resource: string): string {
    return crypto
      .createHash('sha256')
      .update(`${canonicalWorkspace(workspace)}|${resource}`, 'utf8')
      .digest('hex');
  }

  fileFor(workspace: string, resource: string): string {
    return path.join(this.directory, `${BaselineStore.key(workspace, resource)}.json`);
  }

  /** Persist a baseline document; returns the absolute file path. */
  async save(document: BaselineDocument): Promise<string> {
    const target = this.fileFor(document.workspace, document.resource);
    // The baseline holds the file's CONTENTS (including secrets the user chose
    // to protect), so the store and the documents are owner-only. On POSIX
    // the mode is honoured; on Windows the directory ACL applies.
    await fs.mkdir(this.directory, { recursive: true, mode: 0o700 });
    const tmp = `${target}.tmp`;
    await fs.writeFile(tmp, JSON.stringify(document), { encoding: 'utf8', mode: 0o600 });
    await fs.rename(tmp, target); // atomic replace within the same directory
    return target;
  }

  /**
   * Load a baseline, returning `null` when it is missing, unreadable, or does
   * not belong to exactly this workspace/resource pair.
   */
  async load(workspace: string, resource: string): Promise<BaselineDocument | null> {
    const file = this.fileFor(workspace, resource);
    let raw: string;
    try {
      raw = await fs.readFile(file, 'utf8');
    } catch {
      return null;
    }
    try {
      const parsed = JSON.parse(raw) as BaselineDocument;
      if (
        parsed === null ||
        typeof parsed !== 'object' ||
        parsed.format !== BASELINE_FORMAT ||
        typeof parsed.workspace !== 'string' ||
        typeof parsed.resource !== 'string' ||
        !sameWorkspace(parsed.workspace, workspace) ||
        parsed.resource !== resource ||
        parsed.snapshot === null ||
        typeof parsed.snapshot !== 'object' ||
        typeof parsed.snapshot['hash'] !== 'string'
      ) {
        return null;
      }
      return parsed;
    } catch {
      return null;
    }
  }

  async summaries(): Promise<BaselineSummary[]> {
    let entries: string[];
    try {
      entries = await fs.readdir(this.directory);
    } catch {
      return [];
    }
    const out: BaselineSummary[] = [];
    for (const entry of entries) {
      if (!entry.endsWith('.json')) {
        continue;
      }
      try {
        const raw = await fs.readFile(path.join(this.directory, entry), 'utf8');
        const parsed = JSON.parse(raw) as BaselineDocument;
        if (!parsed || parsed.format !== BASELINE_FORMAT) {
          continue;
        }
        const snapshot = (parsed.snapshot ?? {}) as Record<string, unknown>;
        out.push({
          workspace: parsed.workspace,
          resource: parsed.resource,
          file: path.join(this.directory, entry),
          hash: typeof snapshot['hash'] === 'string' ? snapshot['hash'] : null,
          size: typeof snapshot['size'] === 'number' ? snapshot['size'] : null,
          capturedAt:
            typeof parsed.captured_at === 'string' ? parsed.captured_at : null,
        });
      } catch {
        // Skip unreadable entries rather than failing the whole listing.
      }
    }
    out.sort((a, b) => a.resource.localeCompare(b.resource));
    return out;
  }

  /**
   * Every stored baseline of ONE workspace, read and parsed exactly once.
   *
   * The Recovery Inbox needs the stored document (to validate the evidence)
   * together with the metadata (to compare the current file). Reading the
   * same file twice is what makes a scan slow on a large workspace, so both
   * come from this single pass.
   */
  async list(workspace: string): Promise<BaselineEntry[]> {
    let entries: string[];
    try {
      entries = await fs.readdir(this.directory);
    } catch {
      return [];
    }
    const out: BaselineEntry[] = [];
    for (const entry of entries) {
      if (!entry.endsWith('.json')) {
        continue;
      }
      const file = path.join(this.directory, entry);
      try {
        const raw = await fs.readFile(file, 'utf8');
        const parsed = JSON.parse(raw) as BaselineDocument;
        if (!parsed || parsed.format !== BASELINE_FORMAT) {
          continue;
        }
        if (parsed.workspace !== workspace && !sameWorkspace(parsed.workspace, workspace)) {
          continue;
        }
        const snapshot =
          parsed.snapshot !== null && typeof parsed.snapshot === 'object'
            ? (parsed.snapshot as Record<string, unknown>)
            : null;
        out.push({
          resource: parsed.resource,
          file,
          hash:
            snapshot !== null && typeof snapshot['hash'] === 'string' ? snapshot['hash'] : null,
          size:
            snapshot !== null && typeof snapshot['size'] === 'number' ? snapshot['size'] : null,
          capturedAt:
            typeof parsed.captured_at === 'string' ? parsed.captured_at : null,
          snapshot,
        });
      } catch {
        // Unreadable evidence: report it as an unusable document, never as a
        // silently missing file.
        out.push({
          resource: entry,
          file,
          hash: null,
          size: null,
          capturedAt: null,
          snapshot: null,
        });
      }
    }
    out.sort((a, b) => a.resource.localeCompare(b.resource));
    return out;
  }

  async remove(workspace: string, resource: string): Promise<void> {
    try {
      await fs.unlink(this.fileFor(workspace, resource));
      await fs.unlink(`${this.fileFor(workspace, resource)}.evidence.json`);
    } catch {
      // Nothing to remove.
    }
  }
}

/** Deterministic sidecar path used by the bridge for preview evidence. */
export function evidencePathFor(baselineFile: string): string {
  return `${baselineFile}.evidence.json`;
}

export interface StoredVerification {
  workspace: string;
  resource: string;
  at: string;
  success: boolean;
  reason: string;
  checksPassed: string[];
  checksFailed: string[];
}

export interface StoredStatus {
  at: string;
  engineAvailable: boolean;
  engineVersion: string | null;
  engineRoot: string | null;
  pythonVersion: string | null;
  platformStatus: string;
  headline: string;
}
