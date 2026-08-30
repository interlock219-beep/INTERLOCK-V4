# Adapter Model

Recovery adapters are the mechanism by which Interlock actually compensates mutations in external systems. They implement a common protocol so the recovery engine can plan and execute against many systems uniformly.

## Protocol

Every adapter implements the `RecoveryAdapter` protocol:

- `capability` — production-validated, reference-implementation, simulation-capable, mock, stub, or unsupported.
- `supports(evidence)` — whether the adapter can handle a given evidence record.
- `simulate(compensation)` — dry-run the compensation and predict impact without mutating state.
- `execute(compensation)` — apply the compensation and return a `CompensationResult`.
- `verify(compensation)` — independently confirm the resulting state.

## Adapter registry

`AdapterFactory` builds adapters from the `RECOVERY_ADAPTER_NAMES` setting. The factory registry maps adapter names to implementations.

## Production-validated adapters

These perform real operations against real systems:

| Adapter | Type | Operations |
|---------|------|------------|
| `ConfigRecoveryAdapter` | Configuration | Atomic file replacement, hash-based drift detection, conflict detection |
| `DatabaseRecoveryAdapter` | Database (SQL) | INSERT recovery (delete row), UPDATE recovery (restore values), DELETE recovery (re-insert). Whitelist-validated table/column names, parameterized queries, transaction-safe, foreign-key aware. SQLite and PostgreSQL |
| `FilesystemRecoveryAdapter` | Filesystem | File create/modify/delete/rename recovery with metadata preservation and atomic operations |
| `GitRepositoryAdapter` | Git repository | Commit-aware and working-tree recovery with conflict detection |

## Reference / simulation adapters

These return `REQUIRES_MANUAL_ACTION` on execution. They exist to model the protocol and to test the planning pipeline without touching real systems:

| Adapter | Type | Capability |
|---------|------|------------|
| `DatabaseRecordAdapter` | Database (legacy) | Reference implementation |
| `FileVersionAdapter` | Filesystem (legacy) | Reference implementation |
| `ConfigRollbackAdapter` | Configuration (legacy) | Reference implementation |

## Simulation adapter

`MockRecoveryAdapter` is scenario-driven. It is used by the end-to-end demos and tests to exercise the full recovery pipeline deterministically without external dependencies.

## Adapter capability levels

| Level | Meaning |
|-------|---------|
| `production_validated` | Performs real operations; validated against real systems. |
| `reference_implementation` | Models the protocol; returns `REQUIRES_MANUAL_ACTION`. |
| `simulation_capable` | Can simulate but not execute against production. |
| `mock` | Scenario-driven; used for demos and tests. |
| `stub` | Minimal implementation; placeholder. |
| `unsupported` | No adapter available for this system/type. |

## Extending with new adapters

To add production recovery for a new system:

1. Implement the `RecoveryAdapter` protocol.
2. Register it in `AdapterFactory`.
3. Add reversibility and compensation logic for the new system's operations.
4. Validate against a real instance of the target system.
5. Document the capability level honestly.

New adapters should be production-validated before they are classified as such.
