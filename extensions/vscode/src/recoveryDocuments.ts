/**
 * Read-only virtual documents behind the right-hand (and, for deleted files,
 * left-hand) side of the native recovery diff.
 *
 * Nothing here ever touches the workspace: the proposed side lives only in
 * this provider's memory, keyed by the verified baseline hash, and is
 * dropped when a new preview starts. The URI path mirrors the real
 * workspace-relative path, so VS Code detects the language from the file
 * extension exactly as it does for the real file.
 */

import * as vscode from 'vscode';

export const PROPOSED_SCHEME = 'interlock-proposed';
export const MISSING_SCHEME = 'interlock-missing';

export class RecoveryDocuments implements vscode.TextDocumentContentProvider, vscode.Disposable {
  private readonly proposed = new Map<string, string>();
  private readonly missing = new Map<string, string>();
  private readonly emitter = new vscode.EventEmitter<vscode.Uri>();
  readonly onDidChange = this.emitter.event;

  /**
   * Register the exact proposed contents for one file and return its URI.
   * The path keeps the real filename (language detection + a truthful tab),
   * the query carries the verified hash (cache-busting + provenance).
   */
  propose(resource: string, hash: string, text: string): vscode.Uri {
    const key = `${hash}|${resource}`;
    this.proposed.set(key, text);
    return vscode.Uri.from({
      scheme: PROPOSED_SCHEME,
      path: `/${normalizeResourcePath(resource)}`,
      query: `h=${hash}`,
    });
  }

  /** A read-only stand-in for a file that does not exist on disk (deleted). */
  missingDocument(resource: string): vscode.Uri {
    const key = resource;
    if (!this.missing.has(key)) {
      this.missing.set(key, '');
    }
    return vscode.Uri.from({
      scheme: MISSING_SCHEME,
      path: `/${normalizeResourcePath(resource)}`,
      query: 'state=missing',
    });
  }

  /** Drop every stored document (a new preview session supersedes the old). */
  clear(): void {
    this.proposed.clear();
    this.missing.clear();
  }

  provideTextDocumentContent(uri: vscode.Uri): string {
    if (uri.scheme === PROPOSED_SCHEME) {
      const hash = new URLSearchParams(uri.query).get('h') ?? '';
      const resource = normalizeResourcePath(uri.path.replace(/^\//, ''));
      return this.proposed.get(`${hash}|${resource}`) ?? '';
    }
    return this.missing.get(normalizeResourcePath(uri.path.replace(/^\//, ''))) ?? '';
  }

  dispose(): void {
    this.proposed.clear();
    this.missing.clear();
    this.emitter.dispose();
  }
}

/** URIs are built from workspace-relative paths; keep them POSIX-shaped. */
function normalizeResourcePath(resource: string): string {
  return resource.replace(/\\/g, '/').replace(/^\/+/, '');
}
