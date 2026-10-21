/**
 * Tiny coercion helpers for untyped engine/JSON values.
 *
 * Deliberately strict: anything that is not the expected shape collapses to a
 * neutral value (`{}`, `[]`, `null`, `false`) instead of throwing or leaking
 * half-parsed structures into the UI. Pure and dependency-free so every
 * consumer (command handlers, plan reports) can share one definition.
 */

export function asDict(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

export function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

export function asStr(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

export function asBool(value: unknown): boolean {
  return value === true;
}

export function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((entry): entry is string => typeof entry === 'string')
    : [];
}
