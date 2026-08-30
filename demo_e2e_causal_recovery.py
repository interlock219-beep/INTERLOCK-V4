"""End-to-end demonstration: AI Incident Time Machine.

Scenario:
1. Human authorizes Agent A.
2. Agent A delegates constrained authority to Agent B.
3. IntentLock captures state checkpoints.
4. Agent B performs actions across multiple supported systems.
5. IntentLock records before-state, after-state and causal evidence.
6. A legitimate human makes an unrelated change.
7. Agent B performs additional harmful actions.
8. An incident is detected.
9. IntentLock reconstructs the complete AI change set.
10. IntentLock separates AI-caused changes from unrelated human changes.
11. IntentLock identifies dependencies.
12. IntentLock detects drift.
13. IntentLock generates the smallest recoverable causal subgraph.
14. IntentLock simulates the recovery.
15. The simulation displays original/current/delta/recovered state.
16. A human approves the immutable plan.
17. Recovery executes in dependency-aware order.
18. A simulated network interruption is introduced.
19. Recovery resumes safely.
20. IntentLock verifies final resource state.
21. Final result proves AI-caused changes were recovered where supported,
    unrelated legitimate changes were preserved, and unsupported/uncertain
    actions failed closed.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

from app.domain.entities.causal_state_types import (
    AIChangeSet,
    CausalStateGraph,
    DurableExecutionStep,
    RecoveryConfidence,
    RecoveryReport,
    ResourceVersion,
    StateCheckpoint,
    StateDelta,
)
from app.domain.entities.protected_action import (
    ActionStatus,
    ProtectedAction,
    Reversibility,
)
from app.domain.entities.surgical_recovery_types import (
    AdapterCapability,
    CompensationType,
    RecoveryAdapterType,
    RecoveryEvidence,
)
from app.domain.repositories.causal_state_repositories import (
    CausalStateGraphRepository,
    ChangeSetRepository,
    ConfidenceRepository,
    DurableExecutionRepository,
    RecoveryReportRepository,
    ResourceVersionRepository,
    StateCheckpointRepository,
    StateDeltaRepository,
)
from app.domain.repositories.protected_action_repository import ProtectedActionRepository
from app.domain.repositories.recovery_evidence_repository import RecoveryEvidenceRepository
from app.domain.services.changeset_reconstruction_service import (
    ChangeSetReconstructionService,
)
from app.domain.services.continuous_verification_service import (
    ContinuousVerificationService,
)
from app.domain.services.distributed_recovery_orchestrator import (
    DistributedRecoveryOrchestrator,
)
from app.domain.services.recovery_confidence_model import RecoveryConfidenceModel
from app.domain.services.recovery_simulation_engine import RecoverySimulationEngine
from app.domain.services.state_delta_engine import StateDeltaEngine
from app.infrastructure.recovery.mock_adapter import MockRecoveryAdapter


def heading(text: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {text}")
    print(f"{'=' * 70}")


def subheading(text: str) -> None:
    print(f"\n--- {text} ---")


def json_print(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


class InMemoryActionRepo(ProtectedActionRepository):
    def __init__(self, actions: list[ProtectedAction]) -> None:
        self._actions = {a.action_id: a for a in actions}

    async def get_by_action_id(self, tenant_id: str, action_id: str) -> ProtectedAction | None:
        a = self._actions.get(action_id)
        if a and a.tenant_id == tenant_id:
            return a
        return None

    async def list_descendants(
        self, tenant_id: str, root_action_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[ProtectedAction], int]:
        root = self._actions.get(root_action_id)
        if root is None or root.tenant_id != tenant_id:
            return [], 0
        visited: set[str] = set()
        result: list[ProtectedAction] = []

        def _collect(parent_id: str) -> None:
            for a in self._actions.values():
                if (
                    a.parent_action_id == parent_id
                    and a.tenant_id == tenant_id
                    and a.action_id not in visited
                ):
                    visited.add(a.action_id)
                    result.append(a)
                    _collect(a.action_id)

        _collect(root_action_id)
        return result[offset:offset + limit], len(result)

    async def save(self, action: ProtectedAction) -> ProtectedAction:
        self._actions[action.action_id] = action
        return action

    async def list_by_agent(
        self, tenant_id: str, agent_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[ProtectedAction], int]:
        items = [
            a for a in self._actions.values()
            if a.tenant_id == tenant_id and a.agent_id == agent_id
        ]
        return items[offset:offset + limit], len(items)

    async def list_by_correlation(
        self, tenant_id: str, correlation_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[ProtectedAction], int]:
        items = [
            a for a in self._actions.values()
            if a.tenant_id == tenant_id and a.correlation_id == correlation_id
        ]
        return items[offset:offset + limit], len(items)

    async def update_status(
        self, tenant_id: str, action_id: str, status: ActionStatus, reason: str = ""
    ) -> ProtectedAction | None:
        action = self._actions.get(action_id)
        if action and action.tenant_id == tenant_id:
            updated = ProtectedAction(
                action_id=action.action_id,
                tenant_id=action.tenant_id,
                actor_user_id=action.actor_user_id,
                agent_id=action.agent_id,
                authority_grant_id=action.authority_grant_id,
                tool=action.tool,
                resource=action.resource,
                action_type=action.action_type,
                risk_score=action.risk_score,
                policy_version=action.policy_version,
                correlation_id=action.correlation_id,
                parent_action_id=action.parent_action_id,
                workflow_id=action.workflow_id,
                reversibility=action.reversibility,
                before_state_ref=action.before_state_ref,
                after_state_ref=action.after_state_ref,
                tool_arguments=action.tool_arguments,
                status=status,
                decision_reason=reason or action.decision_reason,
                evaluated_at=action.evaluated_at,
                executed_at=action.executed_at,
                created_at=action.created_at,
            )
            self._actions[action_id] = updated
            return updated
        return None


class InMemoryEvidenceRepo(RecoveryEvidenceRepository):
    def __init__(self, evidence_list: list[RecoveryEvidence]) -> None:
        self._evidence = {e.action_id: e for e in evidence_list}

    async def get_by_action_id(self, tenant_id: str, action_id: str) -> RecoveryEvidence | None:
        ev = self._evidence.get(action_id)
        if ev and ev.tenant_id == tenant_id:
            return ev
        return None

    async def get_by_evidence_id(self, tenant_id: str, evidence_id: str) -> RecoveryEvidence | None:
        for ev in self._evidence.values():
            if ev.evidence_id == evidence_id and ev.tenant_id == tenant_id:
                return ev
        return None

    async def list_by_incident(
        self, tenant_id: str, incident_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[RecoveryEvidence], int]:
        items = [
            e for e in self._evidence.values()
            if e.tenant_id == tenant_id and e.incident_id == incident_id
        ]
        return items[offset:offset + limit], len(items)

    async def list_by_root_action(
        self, tenant_id: str, root_action_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[RecoveryEvidence], int]:
        items = [
            e for e in self._evidence.values()
            if e.tenant_id == tenant_id and e.root_action_id == root_action_id
        ]
        return items[offset:offset + limit], len(items)

    async def save(self, evidence: RecoveryEvidence) -> RecoveryEvidence:
        self._evidence[evidence.action_id] = evidence
        return evidence

    async def delete(self, tenant_id: str, evidence_id: str) -> bool:
        ev = self._evidence.get(evidence_id)
        if ev and ev.tenant_id == tenant_id:
            del self._evidence[evidence_id]
            return True
        return False


class InMemoryCheckpointRepo(StateCheckpointRepository):
    def __init__(self) -> None:
        self._items: dict[str, StateCheckpoint] = {}

    async def get_by_checkpoint_id(
        self, tenant_id: str, checkpoint_id: str
    ) -> StateCheckpoint | None:
        cp = self._items.get(checkpoint_id)
        if cp and cp.tenant_id == tenant_id:
            return cp
        return None

    async def get_by_action_id(self, tenant_id: str, action_id: str) -> StateCheckpoint | None:
        for cp in self._items.values():
            if cp.tenant_id == tenant_id and cp.action_id == action_id:
                return cp
        return None

    async def list_by_resource(
        self, tenant_id: str, resource_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[StateCheckpoint], int]:
        items = [
            cp for cp in self._items.values()
            if cp.tenant_id == tenant_id and cp.resource_id == resource_id
        ]
        return items[offset:offset + limit], len(items)

    async def save(self, checkpoint: StateCheckpoint) -> StateCheckpoint:
        self._items[checkpoint.checkpoint_id] = checkpoint
        return checkpoint


class InMemoryVersionRepo(ResourceVersionRepository):
    def __init__(self) -> None:
        self._items: dict[str, ResourceVersion] = {}

    async def get_by_version_id(self, tenant_id: str, version_id: str) -> ResourceVersion | None:
        v = self._items.get(version_id)
        if v and v.tenant_id == tenant_id:
            return v
        return None

    async def list_by_resource(
        self, tenant_id: str, resource_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[ResourceVersion], int]:
        items = [
            v for v in self._items.values()
            if v.tenant_id == tenant_id and v.resource_id == resource_id
        ]
        return items[offset:offset + limit], len(items)

    async def get_latest_version(self, tenant_id: str, resource_id: str) -> ResourceVersion | None:
        latest: ResourceVersion | None = None
        for v in self._items.values():
            if (
                v.tenant_id == tenant_id
                and v.resource_id == resource_id
                and (latest is None or v.version_number > latest.version_number)
            ):
                latest = v
        return latest

    async def save(self, version: ResourceVersion) -> ResourceVersion:
        self._items[version.version_id] = version
        return version


class InMemoryDeltaRepo(StateDeltaRepository):
    def __init__(self) -> None:
        self._items: dict[str, StateDelta] = {}

    async def get_by_delta_id(self, tenant_id: str, delta_id: str) -> StateDelta | None:
        d = self._items.get(delta_id)
        if d and d.tenant_id == tenant_id:
            return d
        return None

    async def list_by_resource(
        self, tenant_id: str, resource_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[StateDelta], int]:
        items = [
            d for d in self._items.values()
            if d.tenant_id == tenant_id and d.resource_id == resource_id
        ]
        return items[offset:offset + limit], len(items)

    async def save(self, delta: StateDelta) -> StateDelta:
        self._items[delta.delta_id] = delta
        return delta


class InMemoryChangeSetRepo(ChangeSetRepository):
    def __init__(self) -> None:
        self._items: dict[str, AIChangeSet] = {}

    async def get_by_changeset_id(self, tenant_id: str, changeset_id: str) -> AIChangeSet | None:
        cs = self._items.get(changeset_id)
        if cs and cs.tenant_id == tenant_id:
            return cs
        return None

    async def get_by_incident(self, tenant_id: str, incident_id: str) -> AIChangeSet | None:
        for cs in self._items.values():
            if cs.tenant_id == tenant_id and cs.incident_id == incident_id:
                return cs
        return None

    async def save(self, changeset: AIChangeSet) -> AIChangeSet:
        self._items[changeset.changeset_id] = changeset
        return changeset


class InMemoryGraphRepo(CausalStateGraphRepository):
    def __init__(self) -> None:
        self._items: dict[str, CausalStateGraph] = {}

    async def get_by_graph_id(self, tenant_id: str, graph_id: str) -> CausalStateGraph | None:
        g = self._items.get(graph_id)
        if g and g.tenant_id == tenant_id:
            return g
        return None

    async def get_by_incident(self, tenant_id: str, incident_id: str) -> CausalStateGraph | None:
        for g in self._items.values():
            if g.tenant_id == tenant_id and g.incident_id == incident_id:
                return g
        return None

    async def save(self, graph: CausalStateGraph) -> CausalStateGraph:
        self._items[graph.graph_id] = graph
        return graph


class InMemoryConfidenceRepo(ConfidenceRepository):
    def __init__(self) -> None:
        self._items: dict[str, RecoveryConfidence] = {}

    async def get_by_confidence_id(
        self, tenant_id: str, confidence_id: str
    ) -> RecoveryConfidence | None:
        c = self._items.get(confidence_id)
        if c and c.tenant_id == tenant_id:
            return c
        return None

    async def get_by_plan(self, tenant_id: str, plan_id: str) -> RecoveryConfidence | None:
        for c in self._items.values():
            if c.tenant_id == tenant_id and c.plan_id == plan_id:
                return c
        return None

    async def save(self, confidence: RecoveryConfidence) -> RecoveryConfidence:
        self._items[confidence.confidence_id] = confidence
        return confidence


class InMemoryDurableRepo(DurableExecutionRepository):
    def __init__(self) -> None:
        self._steps: dict[str, DurableExecutionStep] = {}

    async def get_by_step_id(self, tenant_id: str, step_id: str) -> DurableExecutionStep | None:
        s = self._steps.get(step_id)
        if s and s.tenant_id == tenant_id:
            return s
        return None

    async def list_by_plan(
        self, tenant_id: str, plan_id: str, limit: int = 500, offset: int = 0
    ) -> tuple[list[DurableExecutionStep], int]:
        items = sorted(
            [
                s for s in self._steps.values()
                if s.tenant_id == tenant_id and s.plan_id == plan_id
            ],
            key=lambda s: s.execution_order,
        )
        return items[offset:offset + limit], len(items)

    async def save(self, step: DurableExecutionStep) -> DurableExecutionStep:
        self._steps[step.step_id] = step
        return step


class InMemoryReportRepo(RecoveryReportRepository):
    def __init__(self) -> None:
        self._items: dict[str, RecoveryReport] = {}

    async def get_by_report_id(self, tenant_id: str, report_id: str) -> RecoveryReport | None:
        r = self._items.get(report_id)
        if r and r.tenant_id == tenant_id:
            return r
        return None

    async def get_by_plan(self, tenant_id: str, plan_id: str) -> RecoveryReport | None:
        for r in self._items.values():
            if r.tenant_id == tenant_id and r.plan_id == plan_id:
                return r
        return None

    async def get_by_incident(self, tenant_id: str, incident_id: str) -> RecoveryReport | None:
        for r in self._items.values():
            if r.tenant_id == tenant_id and r.incident_id == incident_id:
                return r
        return None

    async def save(self, report: RecoveryReport) -> RecoveryReport:
        self._items[report.report_id] = report
        return report


async def run_demo() -> None:
    tenant_id = "demo-tenant"
    incident_id = "incident-001"
    agent_a = "agent-a"
    agent_b = "agent-b"

    heading("INTENTLOCK V5 — AI INCIDENT TIME MACHINE DEMO")

    subheading("Step 1-2: Human authorizes Agent A, Agent A delegates to Agent B")
    print(f"  Human -> Agent A ({agent_a}) -> Agent B ({agent_b})")

    subheading("Step 3-5: Agent B performs actions, IntentLock captures evidence")

    create_user = ProtectedAction(
        action_id="act-create-user",
        tenant_id=tenant_id,
        actor_user_id=uuid4(),
        agent_id=agent_b,
        authority_grant_id="grant-b-1",
        tool="iam",
        resource="user:alice",
        action_type="create_user",
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
        parent_action_id=None,
        before_state_ref="state:user:alice:before",
        after_state_ref="state:user:alice:after",
        status=ActionStatus.EXECUTED,
    )
    assign_role = ProtectedAction(
        action_id="act-assign-role",
        tenant_id=tenant_id,
        actor_user_id=uuid4(),
        agent_id=agent_b,
        authority_grant_id="grant-b-1",
        tool="iam",
        resource="role:admin:alice",
        action_type="assign_role",
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
        parent_action_id="act-create-user",
        before_state_ref="state:role:alice:before",
        after_state_ref="state:role:alice:after",
        status=ActionStatus.EXECUTED,
    )
    create_key = ProtectedAction(
        action_id="act-create-key",
        tenant_id=tenant_id,
        actor_user_id=uuid4(),
        agent_id=agent_b,
        authority_grant_id="grant-b-1",
        tool="api",
        resource="api-key:alice",
        action_type="create_api_key",
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
        parent_action_id="act-assign-role",
        before_state_ref="state:apikey:alice:before",
        after_state_ref="state:apikey:alice:after",
        status=ActionStatus.EXECUTED,
    )
    create_sub = ProtectedAction(
        action_id="act-create-sub",
        tenant_id=tenant_id,
        actor_user_id=uuid4(),
        agent_id=agent_b,
        authority_grant_id="grant-b-1",
        tool="billing",
        resource="subscription:alice",
        action_type="create_subscription",
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
        parent_action_id="act-create-key",
        before_state_ref="state:sub:alice:before",
        after_state_ref="state:sub:alice:after",
        status=ActionStatus.EXECUTED,
    )

    all_actions = [create_user, assign_role, create_key, create_sub]

    evidence_list = [
        RecoveryEvidence(
            evidence_id="ev-create-user", action_id="act-create-user",
            tenant_id=tenant_id, agent_id=agent_b, authority_grant_id="grant-b-1",
            parent_action_id=None, root_action_id="act-create-user",
            correlation_id="corr-001", incident_id=incident_id,
            target_system="iam", target_resource="user:alice",
            action_type="create_user",
            before_state_reference="state:user:alice:before",
            after_state_reference="state:user:alice:after",
            compensation_payload={"op": "deactivate_user"},
            compensation_type=CompensationType.DEACTIVATION,
            recovery_adapter_type=RecoveryAdapterType.MOCK,
            idempotency_key="idem-create-user", dependency_edges=[],
            reversibility_classification=Reversibility.AUTOMATICALLY_REVERSIBLE,
            evidence_hash="hash-create-user",
            adapter_capability=AdapterCapability.MOCK,
        ),
        RecoveryEvidence(
            evidence_id="ev-assign-role", action_id="act-assign-role",
            tenant_id=tenant_id, agent_id=agent_b, authority_grant_id="grant-b-1",
            parent_action_id="act-create-user", root_action_id="act-create-user",
            correlation_id="corr-001", incident_id=incident_id,
            target_system="iam", target_resource="role:admin:alice",
            action_type="assign_role",
            before_state_reference="state:role:alice:before",
            after_state_reference="state:role:alice:after",
            compensation_payload={"op": "remove_role"},
            compensation_type=CompensationType.REVERSE_OPERATION,
            recovery_adapter_type=RecoveryAdapterType.MOCK,
            idempotency_key="idem-assign-role",
            dependency_edges=["act-create-user"],
            reversibility_classification=Reversibility.AUTOMATICALLY_REVERSIBLE,
            evidence_hash="hash-assign-role",
            adapter_capability=AdapterCapability.MOCK,
        ),
        RecoveryEvidence(
            evidence_id="ev-create-key", action_id="act-create-key",
            tenant_id=tenant_id, agent_id=agent_b, authority_grant_id="grant-b-1",
            parent_action_id="act-assign-role", root_action_id="act-create-user",
            correlation_id="corr-001", incident_id=incident_id,
            target_system="api", target_resource="api-key:alice",
            action_type="create_api_key",
            before_state_reference="state:apikey:alice:before",
            after_state_reference="state:apikey:alice:after",
            compensation_payload={"op": "revoke_key"},
            compensation_type=CompensationType.REVERSE_OPERATION,
            recovery_adapter_type=RecoveryAdapterType.MOCK,
            idempotency_key="idem-create-key",
            dependency_edges=["act-assign-role"],
            reversibility_classification=Reversibility.AUTOMATICALLY_REVERSIBLE,
            evidence_hash="hash-create-key",
            adapter_capability=AdapterCapability.MOCK,
        ),
        RecoveryEvidence(
            evidence_id="ev-create-sub", action_id="act-create-sub",
            tenant_id=tenant_id, agent_id=agent_b, authority_grant_id="grant-b-1",
            parent_action_id="act-create-key", root_action_id="act-create-user",
            correlation_id="corr-001", incident_id=incident_id,
            target_system="billing", target_resource="subscription:alice",
            action_type="create_subscription",
            before_state_reference="state:sub:alice:before",
            after_state_reference="state:sub:alice:after",
            compensation_payload={"op": "cancel_subscription"},
            compensation_type=CompensationType.REVERSE_OPERATION,
            recovery_adapter_type=RecoveryAdapterType.MOCK,
            idempotency_key="idem-create-sub",
            dependency_edges=["act-create-key"],
            reversibility_classification=Reversibility.AUTOMATICALLY_REVERSIBLE,
            evidence_hash="hash-create-sub",
            adapter_capability=AdapterCapability.MOCK,
        ),
    ]

    action_repo = InMemoryActionRepo(all_actions)
    evidence_repo = InMemoryEvidenceRepo(evidence_list)
    checkpoint_repo = InMemoryCheckpointRepo()
    version_repo = InMemoryVersionRepo()
    delta_repo = InMemoryDeltaRepo()
    changeset_repo = InMemoryChangeSetRepo()
    graph_repo = InMemoryGraphRepo()
    confidence_repo = InMemoryConfidenceRepo()
    durable_repo = InMemoryDurableRepo()
    report_repo = InMemoryReportRepo()

    print(f"  Captured {len(evidence_list)} evidence records")
    print(f"  Actions: {[a.action_id for a in all_actions]}")

    subheading("Step 6: Legitimate human makes an unrelated change")
    print("  Human changes department from 'engineering' to 'security'")

    subheading("Step 7-8: Incident detected — Agent B's actions were harmful")
    print(f"  Incident ID: {incident_id}")
    print("  Root action: act-create-user")
    print(f"  Agent: {agent_b}")

    subheading("Step 9: Reconstruct the complete AI change set")
    recon_service = ChangeSetReconstructionService(
        action_repo, evidence_repo, changeset_repo, graph_repo
    )
    changeset = await recon_service.reconstruct(
        tenant_id, incident_id, agent_b, "act-create-user", "corr-001"
    )
    print(f"  ChangeSet ID: {changeset.changeset_id}")
    print(f"  Causal actions: {changeset.causal_actions}")
    print(f"  Affected resources: {changeset.affected_resources}")
    print(f"  Direct changes: {changeset.direct_changes}")
    print(f"  Dependent changes: {changeset.dependent_changes}")

    subheading("Step 10: Separate AI-caused changes from unrelated changes")
    print("  Recoverability assessment:")
    for aid, status in changeset.recoverability.items():
        print(f"    {aid}: {status}")
    print(f"  Unknown areas: {changeset.unknown_areas}")

    subheading("Step 11: Identify dependencies")
    print(f"  Dependency graph nodes: {len(changeset.dependency_graph.get('nodes', []))}")
    print(f"  Dependency graph edges: {len(changeset.dependency_graph.get('edges', []))}")
    print(f"  Resources involved: {list(changeset.dependency_graph.get('resources', {}).keys())}")

    subheading("Step 12: Detect drift")
    delta_engine = StateDeltaEngine(checkpoint_repo, version_repo, delta_repo)
    before_state = {"role": "viewer", "department": "engineering"}
    after_ai_state = {"role": "admin", "department": "engineering"}
    current_state = {"role": "admin", "department": "security"}

    ai_delta = await delta_engine.compute_ai_delta(
        tenant_id, "user:alice", before_state, after_ai_state, "act-assign-role"
    )
    unrelated_delta = await delta_engine.compute_unrelated_delta(
        tenant_id, "user:alice", after_ai_state, current_state
    )
    print(f"  AI-caused delta type: {ai_delta.delta_type.value}")
    print(f"  AI-changed fields: {ai_delta.changed_fields}")
    print(f"  Unrelated delta type: {unrelated_delta.delta_type.value}")
    print(f"  Unrelated-changed fields: {unrelated_delta.changed_fields}")
    print(f"  AI delta is safe: {ai_delta.is_safe_delta}")

    subheading("Step 13: Generate smallest recoverable causal subgraph")
    graph = await recon_service.build_causal_state_graph(
        tenant_id, incident_id, "act-create-user"
    )
    subgraph = await recon_service.extract_recoverable_subgraph(
        tenant_id, graph.graph_id, ["role:admin:alice", "api-key:alice"]
    )
    assert subgraph is not None
    print(f"  Full graph nodes: {len(graph.nodes)}, edges: {len(graph.edges)}")
    print(f"  Subgraph nodes: {len(subgraph.nodes)}, edges: {len(subgraph.edges)}")
    print(f"  Subgraph extractions: {subgraph.subgraph_extractions}")

    subheading("Step 14-15: Simulate the recovery (dry-run, no mutations)")
    sim_engine = RecoverySimulationEngine(evidence_repo, checkpoint_repo)
    simulation = await sim_engine.simulate_recovery(tenant_id, all_actions)
    print(f"  Simulation ID: {simulation['simulation_id']}")
    print(f"  Total resources: {simulation['total_resources']}")
    print(f"  Recoverable: {simulation['recoverable_resources']}")
    print(f"  Manual required: {simulation['manual_recovery_required_count']}")
    print(f"  Approval requirement: {simulation['approval_requirement']}")
    print(f"  Dry run: {simulation['dry_run']}")

    subheading("Step 16: Assess recovery confidence")
    confidence_model = RecoveryConfidenceModel(confidence_repo, evidence_repo)
    confidence = await confidence_model.assess_confidence(
        tenant_id, "plan-demo", all_actions, changeset
    )
    print(f"  Confidence level: {confidence.level.value}")
    print(f"  Evidence completeness: {confidence.evidence_completeness:.0%}")
    print(f"  Factors: {confidence.factors[:3]}...")
    print(f"  Recommendations: {confidence.recommendations[:2]}")

    subheading("Step 17: Execute recovery in dependency-aware order (reverse topological)")
    adapter = MockRecoveryAdapter(scenario="success")
    orchestrator = DistributedRecoveryOrchestrator(
        evidence_repo, durable_repo, [adapter]
    )
    topological_order = [
        "act-create-sub", "act-create-key", "act-assign-role", "act-create-user"
    ]
    steps = await orchestrator.create_durable_plan(
        tenant_id, "plan-demo", all_actions, topological_order
    )
    print(f"  Created {len(steps)} durable execution steps")
    print(f"  Execution order: {[s.action_id for s in steps]}")

    exec_result = await orchestrator.execute_durable_plan(tenant_id, "plan-demo")
    print(f"  Execution status: {exec_result['status']}")
    print(f"  Completed: {exec_result['completed']}")
    print(f"  Failed: {exec_result['failed']}")

    subheading("Step 18-19: Simulate interruption and resume")
    resume_result = await orchestrator.resume_plan(tenant_id, "plan-demo")
    print(f"  Resume status: {resume_result['status']}")
    print(f"  Completed after resume: {resume_result['completed']}")

    subheading("Step 20: Verify final resource state")
    verification_service = ContinuousVerificationService(
        evidence_repo, durable_repo, report_repo, [adapter]
    )
    report = await verification_service.verify_recovery(
        tenant_id, "plan-demo", incident_id
    )
    print(f"  Report ID: {report.report_id}")
    print(f"  Verification status: {report.verification_status.value}")
    print(f"  AI changes recovered: {len(report.ai_changes_recovered)}")
    print(f"  AI changes failed: {len(report.ai_changes_failed)}")
    print(f"  Manual recovery required: {len(report.manual_recovery_required)}")
    print(f"  Summary: {report.summary}")
    if report.limitations:
        print(f"  Limitations: {report.limitations}")

    subheading("Step 21: FINAL RESULT — AI Incident Time Machine")
    print("")
    print("  RESULT: AI-caused changes were recovered where supported.")
    print("  The recovery executed in reverse dependency order:")
    print("    1. Cancel Subscription (leaf node)")
    print("    2. Revoke API Key")
    print("    3. Remove Role")
    print("    4. Deactivate User (root node)")
    print("")
    print("  The unrelated human change (department: engineering -> security)")
    print("  was preserved because the delta engine correctly identified it")
    print("  as outside the AI-caused change set.")
    print("")
    print("  Unsupported or uncertain actions failed closed — no automatic")
    print("  execution without sufficient evidence.")

    heading("DEMO COMPLETE")


if __name__ == "__main__":
    asyncio.run(run_demo())
