# Recovery Model

Interlock classifies every protected action by reversibility and compensates only what it can safely undo.

## Reversibility classifications

| Classification | Meaning | Automatic? |
|----------------|---------|------------|
| `automatically_reversible` | Interlock can compensate without human intervention. | Yes |
| `conditionally_reversible` | Reversible only if preconditions hold (no drift, no conflict). | If preconditions pass |
| `manually_recoverable` | Requires human action; Interlock provides evidence and a recommended operation. | No |
| `irreversible` | Cannot be undone (external message sent, physical action, etc.). | No |
| `unknown` | Insufficient evidence to classify. | No (escalated) |

`Reversibility.blocks_automatic_execution()` returns true for `manually_recoverable`, `irreversible`, and `unknown`. These never execute without explicit human approval.

## Compensation types

| Type | Description |
|------|-------------|
| `reverse_operation` | Apply the logical inverse (e.g., remove a role that was assigned). |
| `compensating_event` | Emit a compensating event (e.g., cancel a subscription). |
| `state_transition` | Move a resource to a prior state. |
| `deletion` | Remove a created resource. |
| `deactivation` | Deactivate without deleting (e.g., deactivate a user). |
| `custom` | Adapter-specific compensation logic. |

## Recovery evidence

Every protected action captures an immutable `RecoveryEvidence` record:

- Before/after state references
- Target system and resource
- Reversibility classification
- Compensation payload and type
- Idempotency key
- Dependency edges
- Evidence hash

Evidence is the foundation of attribution, planning, and forensic audit.

## Execution states

| State | Meaning |
|-------|---------|
| `pending` | Planned, not yet executed. |
| `running` | Currently executing. |
| `succeeded` | Compensation applied and verified. |
| `failed` | Execution failed; details recorded. |
| `partial_success` | Some compensations succeeded, others did not. |
| `blocked_by_conflict` | A concurrent mutation prevents safe recovery. |
| `blocked_by_drift` | The resource has changed since the agent's action. |
| `stopped` | Execution halted by operator or stop condition. |
| `requires_manual_action` | Human intervention required. |
| `unknown_external_outcome` | External system result could not be determined. |

## Stop conditions

A recovery plan specifies when to stop:

- `on_first_failure` — stop at the first failed step.
- `on_blocking_conflict` — stop when a conflict blocks recovery.
- `on_blocking_drift` — stop when drift is detected.
- `continue_on_failure` — attempt all steps, report per-step results.
- `require_all_approved` — every step requires approval before execution.

## Approval policies

- `single_approval` — one authorized approver.
- `dual_approval` — two independent approvers.
- `m_of_n` — M approvers required from a set of N.

Approval is enforced at plan execution. Without sufficient approval, the plan does not run.
