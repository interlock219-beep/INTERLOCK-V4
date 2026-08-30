# Causal Recovery

Causal recovery is the mechanism that lets Interlock undo an agent's changes without destroying unrelated work done by humans or other agents at the same time.

## The problem with time-based rollback

A naive approach rolls back "everything that changed in the last 10 minutes." That destroys legitimate concurrent work. If a human changed a user's department from `engineering` to `security` while an agent was creating that user and assigning roles, a time-based rollback would revert the human's change too.

Interlock does not use time-based rollback. It uses **causal attribution**.

## Causal attribution

Every protected action is journaled with:

- `agent_id` — who performed it.
- `correlation_id` — which session/incident it belongs to.
- `parent_action_id` — the action that triggered it.
- `before_state_reference` / `after_state_reference` — what changed.

`ChangeSetReconstructionService` uses these links to reconstruct the **causal change set**: the complete tree of mutations that trace back to an incident's root action.

## State deltas

`StateDeltaEngine` computes two deltas per resource:

- **AI-caused delta** — fields changed by the agent between before-state and after-state.
- **Unrelated delta** — fields that changed between the agent's after-state and the current state, caused by someone else.

Each delta carries a safety flag. An AI delta is "safe" to compensate only if it does not collide with an unrelated delta on the same field.

## Causal graph

`CausalGraphService` builds a directed graph:

- **Nodes** — protected actions in the change set.
- **Edges** — dependency relationships (parent → child).

From this graph, Interlock extracts the **smallest recoverable subgraph**: the minimal set of compensations needed to undo the incident. Actions outside the subgraph are left alone.

## Conflict and drift

Before executing, Interlock checks each action:

- **Drift detection** — has the resource changed since the agent's action? (hash-based)
- **Conflict detection** — does the compensation collide with a newer legitimate change?

Conflicted or drifted actions are classified `BLOCKED_BY_CONFLICT` or `BLOCKED_BY_DRIFT` and escalated to human review rather than silently overwritten.

## Example

```
Agent B creates user Alice
  → assigns admin role to Alice
  → creates API key for Alice
  → creates subscription for Alice

Meanwhile, a human changes Alice's department: engineering → security

Incident detected. Recovery analysis:
  - create_user:     AUTOMATICALLY_REVERSIBLE
  - assign_role:     AUTOMATICALLY_REVERSIBLE
  - create_api_key:  AUTOMATICALLY_REVERSIBLE
  - create_subscription: AUTOMATICALLY_REVERSIBLE

Recovery executes in reverse dependency order:
  1. Cancel subscription  (leaf)
  2. Revoke API key
  3. Remove role
  4. Deactivate user      (root)

Result:
  - Agent's changes: reverted.
  - Human's department change: preserved.
  - Forensic evidence: retained.
```

This is not a benchmark result. It illustrates the workflow using the scenario from `demo_e2e_causal_recovery.py`.
