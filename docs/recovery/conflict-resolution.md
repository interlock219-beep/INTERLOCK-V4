# Conflict Resolution

A core design principle of Interlock is that recovery must not destroy legitimate work performed by humans or other agents during or after an incident.

## Why conflicts happen

An agent mutates a resource. Later, a human or another agent mutates the same resource for an unrelated reason. If Interlock naively reverts the agent's change, it overwrites the legitimate later change.

## Drift detection

`StateDeltaEngine` computes a hash-based drift signal:

- `no_drift` — the resource matches the agent's after-state; safe to compensate.
- `drift_detected` — the resource has changed since the agent's action.
- `concurrent_mutation` — a specific concurrent change was identified.
- `insufficient_evidence` — not enough data to determine drift.
- `resource_missing` — the resource no longer exists.
- `version_mismatch` — version identifier does not match.
- `precondition_failed` — a required precondition no longer holds.

## Conflict detection

Conflict detection classifies whether a compensation can proceed safely:

- `no_conflict` — safe to compensate.
- `conflict_detected` — a concurrent mutation would be overwritten.
- `concurrent_mutation` — specific concurrent change identified.
- `version_mismatch` — version drift detected.
- `resource_missing` — target resource gone.
- `insufficient_evidence` — cannot determine safety.
- `precondition_failed` — precondition no longer satisfied.

## Resolution behavior

When drift or conflict is detected, Interlock does **not** silently overwrite. The action is classified:

- `BLOCKED_BY_CONFLICT` — a concurrent mutation prevents safe recovery.
- `BLOCKED_BY_DRIFT` — the resource has changed in an unrecoverable way.
- `REQUIRES_MANUAL_ACTION` — a human must decide.

These actions are escalated, not auto-executed. The recovery report surfaces them explicitly so operators can resolve them deliberately.

## Preserving legitimate changes

Because Interlock attributes changes by agent and correlation ID (not by timestamp), a human's unrelated change to the same resource is:

1. Identified as an unrelated delta.
2. Excluded from the recoverable subgraph.
3. Preserved during recovery.

This is the difference between Interlock's causal recovery and a naive time-based rollback.

## Partial recovery

A conflict on one action does not block recovery of unrelated actions. Interlock recovers what it can and reports what it cannot, with explicit reasoning for each blocked action.
