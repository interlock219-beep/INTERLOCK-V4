# Interlock Recovery Engine

The recovery engine is Interlock's answer to the question: *"The agent already changed the system — now what?"*

It does not claim that every action is reversible. It reconstructs what happened, classifies what can be undone, plans the compensations, executes them in the right order, and verifies the result.

## Pipeline

```
Observe → Attribute → Discover → Plan → Simulate → Recover → Verify
```

### 1. Observe

Every protected action records **recovery evidence**:

- `before_state_reference` / `after_state_reference`
- `target_system`, `target_resource`, `action_type`
- `reversibility_classification`
- `compensation_payload` and `compensation_type`
- `idempotency_key`
- `dependency_edges` (parent/child action links)
- `evidence_hash`

Evidence is captured at the domain boundary by the protected-action journal, so recovery data is a first-class output of normal execution — not a retroactive audit log.

### 2. Attribute

`ChangeSetReconstructionService` reconstructs the complete set of mutations attributable to an incident:

- **Direct changes** — actions taken by the affected agent.
- **Dependent changes** — child actions triggered by the agent's actions.
- **Unrelated changes** — concurrent mutations by humans or other agents, identified and preserved.

Attribution separates the AI-caused change set from everything else. This is what makes surgical recovery possible: Interlock does not roll back "the last N minutes," it rolls back *what the agent changed*.

### 3. Discover

`StateDeltaEngine` and `CausalGraphService` build the causal picture:

- **State deltas** — per-field AI-caused delta vs. unrelated delta, with a safety flag.
- **Causal graph** — nodes are actions, edges are dependency relationships.
- **Recoverable subgraph** — the minimal set of actions that must be compensated, extracted from the full graph.
- **Drift detection** — hash-based detection of changes that happened after the agent's action.
- **Conflict detection** — identification of concurrent mutations that would be overwritten by a naive rollback.

### 4. Plan

`RecoveryPlanningService` produces an immutable, human-approvable plan:

- Reversibility classification for each action.
- Reverse-topological execution order (leaf actions first, root actions last).
- Compensation payloads ready for the appropriate adapter.
- Approval policy (single, dual, or M-of-N) based on risk.

### 5. Simulate

`RecoverySimulationEngine` performs a dry-run without mutations:

- Predicts success/failure per action.
- Surfaces drift and conflict risks before execution.
- Reports `recoverable`, `manual_recovery_required`, and `approval_requirement` counts.

Simulation is the default. No recovery executes without a human-approved plan unless explicitly configured otherwise.

### 6. Recover

`DistributedRecoveryOrchestrator` executes the plan:

- **Dependency-aware order** — reverse topological, so dependent actions are compensated before their parents.
- **Durable execution steps** — each step is persisted with its execution state.
- **Resume after interruption** — a simulated network failure mid-recovery is detected and the plan resumes safely from the last completed step.
- **Idempotency** — re-executing a completed step returns the prior result without re-applying.
- **Partial recovery** — a failed step does not block independent recoveries; mixed states are tracked per-action.
- **Fail-closed** — unsupported or uncertain actions are not auto-executed.

### 7. Verify

`ContinuousVerificationService` independently confirms the outcome:

- Compares actual resource state against the expected recovered state.
- Produces a `RecoveryReport` with counts of recovered, failed, manual-required, and limitations.
- Attaches forensic evidence for audit.

## Containment

Recovery is paired with containment (`CascadeContainmentService`):

- **Quarantine** the compromised agent.
- **Revoke authority grants** across the delegation chain (human → Agent A → Agent B).
- **Calculate blast radius** — which agents, authorities, sessions, and actions are affected.
- **Freeze sessions** to prevent further execution during recovery.

Containment stops the bleeding; recovery heals the wound.
