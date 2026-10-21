/**
 * Secret-safe logging helpers.
 *
 * Everything the extension writes to its output channel, notifications, or
 * stored state goes through {@link redact} first, so subprocess output,
 * environment fragments, and engine messages can never leak credentials.
 */

const PATTERNS: Array<{ pattern: RegExp; replacement: string }> = [
  // Authorization headers
  { pattern: /\bBearer\s+[A-Za-z0-9._~+/=-]{8,}/gi, replacement: 'Bearer [redacted]' },
  // JWT-shaped tokens (three base64url segments)
  {
    pattern: /\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\b/g,
    replacement: '[redacted-jwt]',
  },
  // key=value / key: value secret assignments.
  // The lookahead keeps already-redacted placeholders (and the "Bearer"
  // keyword left behind by the header rule) from being re-mangled.
  {
    pattern:
      /\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|auth[_-]?orization|private[_-]?key|credential)\b(\s*[=:]\s*)("?)(?!\[redacted)(?!Bearer\b)[^\s"',;&]+/gi,
    replacement: '$1$2$3[redacted]',
  },
  // AWS-style access key ids
  { pattern: /\bAKIA[0-9A-Z]{16}\b/g, replacement: '[redacted-aws-key]' },
  // PEM private key blocks
  {
    pattern: /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g,
    replacement: '[redacted-private-key]',
  },
];

/** Redact secret-shaped substrings from free text. */
export function redact(text: string): string {
  if (!text) {
    return text;
  }
  let out = text;
  for (const { pattern, replacement } of PATTERNS) {
    // RegExp objects are per-call literals (no shared lastIndex state).
    out = out.replace(new RegExp(pattern.source, pattern.flags), replacement);
  }
  return out;
}

/** Redact a structured value, masking secret-named keys entirely. */
export function redactObject(value: unknown, keyHint = ''): unknown {
  if (keyHint && isSensitiveKey(keyHint)) {
    return '[redacted]';
  }
  if (value === null || value === undefined) {
    return value;
  }
  if (typeof value === 'string') {
    return redact(value);
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item) => redactObject(item));
  }
  if (typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      out[key] = redactObject(item, key);
    }
    return out;
  }
  return String(value);
}

function isSensitiveKey(key: string): boolean {
  const lowered = key.toLowerCase();
  return [
    'password',
    'passwd',
    'secret',
    'token',
    'api_key',
    'apikey',
    'credential',
    'private_key',
    'authorization',
  ].some((needle) => lowered.includes(needle));
}

/** Truncate long text for logs, keeping the head and a clear marker. */
export function truncate(text: string, maxChars: number): string {
  if (text.length <= maxChars) {
    return text;
  }
  const head = text.slice(0, maxChars);
  return `${head}\n… [truncated ${text.length - maxChars} characters]`;
}
