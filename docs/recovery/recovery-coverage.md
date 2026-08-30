# Recovery Coverage

Recovery coverage measures what Interlock can actually recover. It does not assume every agent action is reversible.

## Measurement methodology

For a given incident, Interlock classifies every affected action into one of five categories:

| Category | Criteria |
|----------|----------|
| **Directly reversible** | A production-validated adapter can compensate automatically (e.g., delete a created record, revert a config file, undo a git change). |
| **Compensatable** | Reversible with a supported compensation operation, possibly conditional on preconditions. |
| **Requires human intervention** | Interlock provides the evidence and a recommended operation, but cannot execute automatically. |
| **Irreversible** | Explicitly classified as unrecoverable (external API side effect, message already delivered, physical-world action, time-dependent effect). |
| **Unknown** | Insufficient evidence to classify; escalated rather than assumed safe. |

## How to measure

Run the recovery simulation against a real or representative incident:

```
POST /api/v1/recovery/simulate
```

The response reports recoverable, manual-recovery-required, and conflicted counts per action. Aggregate these across the change set to produce a coverage percentage:

```
recovery_coverage = reversible_actions / total_classified_actions
```

## What the number means

A 97% recovery coverage does **not** mean "97% of actions were automatically undone." It means 97% of actions were classified as reversible or compensatable; the remaining 3% were either irreversible, conflicted, or unknown and escalated to humans.

## Honest reporting

Interlock reports limitations explicitly:

- Unsupported mutations are classified rather than falsely reported as recovered.
- Conflict and drift are surfaced, not silently overwritten.
- The recovery report includes a `limitations` field describing what could not be recovered and why.

## Benchmarks

For measured benchmark data, see [`docs/operations/RECOVERY_VALIDATION_REPORT.md`](operations/RECOVERY_VALIDATION_REPORT.md). Where real benchmark data exists, it should be cited with its date and scope. Where it does not, this methodology should be applied to produce measured numbers rather than illustrative estimates.

> The incident example in the README is illustrative. Real coverage numbers must be produced by running the recovery pipeline against measured scenarios.
