from __future__ import annotations



import hashlib

import logging

import secrets

from collections import defaultdict, deque

from dataclasses import dataclass, field

from dataclasses import asdict

from datetime import UTC, datetime

from enum import StrEnum

from typing import Any



from app.domain.entities.protected_action import ProtectedAction, Reversibility

from app.domain.entities.surgical_recovery_types import (

    CompensationType,

    ConflictStatus,

    RecoveryEvidence,

)



logger = logging.getLogger("intentlock.recovery_intelligence")





class RecoveryStrategy(StrEnum):

    MINIMAL_CHANGE = "minimal_change"

    MAX_SAFETY = "max_safety"

    MIN_DOWNTIME = "min_downtime"

    MIN_DATA_LOSS = "min_data_loss"

    EMERGENCY = "emergency"

    DEFERRED = "deferred"





class PlanComparisonCriterion(StrEnum):

    COST = "cost"

    TIME = "time"

    COLLATERAL_DAMAGE = "collateral_damage"

    UNCERTAINTY = "uncertainty"

    COMPLETENESS = "completeness"

    SAFETY = "safety"

    HUMAN_IMPACT = "human_impact"





class PlanValidity(StrEnum):

    VALID = "valid"

    INVALID_CYCLE = "invalid_cycle"

    INVALID_PREREQUISITE = "invalid_prerequisite"

    INVALID_CONFLICT = "invalid_conflict"

    INVALID_BOUNDARY = "invalid_boundary"

    EXPIRED = "expired"

    SUPERSEDED = "superseded"





class PlanningMode(StrEnum):

    STANDARD = "standard"

    EMERGENCY = "emergency"

    DEFERRED = "deferred"

    SIMULATION_ONLY = "simulation_only"





@dataclass(frozen=True, slots=True)

class DependencyNode:

    action_id: str

    parent_action_id: str | None

    children: list[str] = field(default_factory=list)

    depends_on: list[str] = field(default_factory=list)

    resource: str = ""

    tool: str = ""

    reversibility: Reversibility = Reversibility.UNKNOWN





@dataclass(frozen=True, slots=True)

class DependencyGraph:

    nodes: dict[str, DependencyNode]

    roots: list[str]

    leaves: list[str]

    topological_order: list[str]

    reverse_topological_order: list[str]

    cycles: list[list[str]] = field(default_factory=list)





@dataclass(frozen=True, slots=True)

class ConflictAnalysis:

    action_id: str

    conflict_status: ConflictStatus

    details: dict[str, Any] = field(default_factory=dict)

    blocking: bool = False

    resolution_hints: list[str] = field(default_factory=list)





@dataclass(frozen=True, slots=True)

class PrerequisiteCheck:

    action_id: str

    satisfied: bool

    failed_checks: list[str] = field(default_factory=list)

    details: dict[str, Any] = field(default_factory=dict)





@dataclass(frozen=True, slots=True)

class BoundaryDefinition:

    rollback_boundary: list[str] = field(default_factory=list)

    compensation_boundary: list[str] = field(default_factory=list)

    human_approval_boundary: list[str] = field(default_factory=list)

    verification_boundary: list[str] = field(default_factory=list)





@dataclass(frozen=True, slots=True)

class PlanMetrics:

    estimated_cost: float = 0.0

    estimated_time_seconds: float = 0.0

    collateral_damage_score: float = 0.0

    uncertainty_score: float = 0.0

    completeness_score: float = 0.0

    safety_score: float = 0.0

    human_impact_score: float = 0.0





@dataclass(frozen=True, slots=True)

class RecoveryAlternative:

    plan_id: str

    strategy: RecoveryStrategy

    topological_order: list[str]

    metrics: PlanMetrics

    affected_actions: list[str]

    compensation_actions: list[dict[str, Any]]

    prerequisites: list[PrerequisiteCheck]

    conflicts: list[ConflictAnalysis]

    boundaries: BoundaryDefinition

    warnings: list[str] = field(default_factory=list)

    explanations: list[str] = field(default_factory=list)

    provenance: dict[str, Any] = field(default_factory=dict)





@dataclass(frozen=True, slots=True)

class PlanComparison:

    alternatives: list[RecoveryAlternative]

    ranked_by: PlanComparisonCriterion

    ranking: list[str]

    selection: str | None = None

    selection_rationale: str = ""





@dataclass(frozen=True, slots=True)

class ValidationResult:

    validity: PlanValidity

    errors: list[str] = field(default_factory=list)

    warnings: list[str] = field(default_factory=list)

    failed_checks: list[str] = field(default_factory=list)





@dataclass(frozen=True, slots=True)

class RecoveryPlanVersion:

    plan_id: str

    version: str

    plan_hash: str

    created_at: datetime

    supersedes: str | None = None

    superseded_by: str | None = None

    expires_at: datetime | None = None

    is_active: bool = True

    metadata: dict[str, Any] = field(default_factory=dict)





@dataclass(frozen=True, slots=True)

class SafetyGateResult:

    gate_name: str

    passed: bool

    details: dict[str, Any] = field(default_factory=dict)

    blocking: bool = True

    remediation: str = ""





@dataclass(frozen=True, slots=True)

class HumanImpactAssessment:

    action_id: str

    requires_human_approval: bool

    approval_reason: str = ""

    estimated_human_time_seconds: float = 0.0

    affected_parties: list[str] = field(default_factory=list)

    notification_required: bool = False





@dataclass(frozen=True, slots=True)

class CascadingImpactAnalysis:

    root_action_id: str

    cascade_depth: int

    affected_resources: list[str]

    cross_system_impacts: dict[str, list[str]] = field(default_factory=dict)

    blast_radius_estimate: int = 0

    containment_options: list[str] = field(default_factory=list)





@dataclass(frozen=True, slots=True)

class FeasibilityReport:

    feasible: bool

    feasibility_score: float

    blockers: list[str] = field(default_factory=list)

    warnings: list[str] = field(default_factory=list)

    mitigations: list[str] = field(default_factory=list)

    recommended_strategy: RecoveryStrategy | None = None

    evidence_completeness: float = 0.0

    dependency_coverage: float = 0.0

    risk_level: str = "unknown"





class RecoveryIntelligenceService:

    def __init__(

        self,

        action_repository: Any = None,

        evidence_repository: Any = None,

        adapters: list[Any] | None = None,

    ) -> None:

        self._action_repo = action_repository

        self._evidence_repo = evidence_repository

        self._adapters = adapters or []

        self._plan_versions: dict[str, list[RecoveryPlanVersion]] = defaultdict(list)



    async def build_dependency_graph(

        self,

        tenant_id: str,

        root_action_id: str,

        max_depth: int = 100,

    ) -> DependencyGraph:

        action = await self._get_action(tenant_id, root_action_id)

        if action is None:

            raise ValueError(f"Root action {root_action_id} not found")



        descendants, _ = await self._get_descendants(tenant_id, root_action_id, max_depth)

        all_actions = [action] + descendants



        nodes: dict[str, DependencyNode] = {}

        child_counts: dict[str, int] = defaultdict(int)

        parent_map: dict[str, str | None] = {}



        for a in all_actions:

            node = DependencyNode(

                action_id=a.action_id,

                parent_action_id=a.parent_action_id,

                resource=a.resource,

                tool=a.tool,

                reversibility=Reversibility.normalize(a.reversibility),

            )

            nodes[a.action_id] = node

            parent_map[a.action_id] = a.parent_action_id

            if a.parent_action_id:

                child_counts[a.parent_action_id] += 1



        for a in all_actions:

            if a.parent_action_id and a.parent_action_id in nodes:

                nodes[a.parent_action_id].children.append(a.action_id)

            for dep in self._infer_dependencies(a, all_actions):

                if dep in nodes:

                    nodes[a.action_id].depends_on.append(dep)



        roots = [n.action_id for n in nodes.values() if n.parent_action_id is None]

        leaves = [n.action_id for n in nodes.values() if not n.children]



        topological_order = self._compute_topological_order(nodes, child_counts)

        reverse_topo = list(reversed(topological_order))

        cycles = self._detect_cycles(nodes)



        return DependencyGraph(

            nodes=nodes,

            roots=roots,

            leaves=leaves,

            topological_order=topological_order,

            reverse_topological_order=reverse_topo,

            cycles=cycles,

        )



    def _infer_dependencies(

        self, action: ProtectedAction, all_actions: list[ProtectedAction]

    ) -> list[str]:

        deps = []

        if action.parent_action_id:

            deps.append(action.parent_action_id)

        for other in all_actions:

            if other.action_id == action.action_id:

                continue

            if (

                other.resource == action.resource

                and other.action_id != action.action_id

                and other.created_at < action.created_at

            ):

                deps.append(other.action_id)

        return deps



    def _compute_topological_order(

        self, nodes: dict[str, DependencyNode], child_counts: dict[str, int]

    ) -> list[str]:

        queue: deque[str] = deque()

        for node_id, _node in nodes.items():

            if child_counts.get(node_id, 0) == 0:

                queue.append(node_id)



        order: list[str] = []

        visited: set[str] = set()

        temp_counts = dict(child_counts)



        while queue:

            current = queue.popleft()

            if current in visited:

                continue

            visited.add(current)

            order.append(current)



            parent = nodes[current].parent_action_id

            if parent and parent in temp_counts:

                temp_counts[parent] -= 1

                if temp_counts[parent] == 0:

                    queue.append(parent)



        for node_id in nodes:

            if node_id not in visited:

                order.append(node_id)



        return order



    def _detect_cycles(self, nodes: dict[str, DependencyNode]) -> list[list[str]]:

        visited: set[str] = set()

        rec_stack: set[str] = set()

        cycles: list[list[str]] = []

        path: list[str] = []



        def dfs(node_id: str) -> None:

            visited.add(node_id)

            rec_stack.add(node_id)

            path.append(node_id)



            for dep in nodes[node_id].depends_on:

                if dep not in nodes:

                    continue

                if dep not in visited:

                    dfs(dep)

                elif dep in rec_stack:

                    cycle_start = path.index(dep)

                    cycles.append(path[cycle_start:] + [dep])



            rec_stack.remove(node_id)

            path.pop()



        for node_id in nodes:

            if node_id not in visited:

                dfs(node_id)



        return cycles



    async def analyze_conflicts(

        self,

        tenant_id: str,

        actions: list[ProtectedAction],

        current_states: dict[str, dict[str, Any]] | None = None,

    ) -> list[ConflictAnalysis]:

        current_states = current_states or {}

        analyses: list[ConflictAnalysis] = []



        for action in actions:

            evidence = await self._get_evidence(tenant_id, action.action_id)

            if evidence is None:

                analyses.append(ConflictAnalysis(

                    action_id=action.action_id,

                    conflict_status=ConflictStatus.INSUFFICIENT_EVIDENCE,

                    details={"reason": "No recovery evidence"},

                    blocking=True,

                    resolution_hints=["Capture recovery evidence before planning"],

                ))

                continue



            conflict = await self._check_conflicts(

                action, evidence, current_states.get(action.resource)

            )

            analyses.append(conflict)



        return analyses



    async def _check_conflicts(

        self,

        action: ProtectedAction,

        evidence: RecoveryEvidence,

        current_state: dict[str, Any] | None,

    ) -> ConflictAnalysis:

        for adapter in self._adapters:

            if hasattr(adapter, "check_conflicts"):

                try:

                    result = await adapter.check_conflicts(

                        action, evidence, current_state

                    )

                    blocking = result.status not in (

                        ConflictStatus.NO_CONFLICT,

                        ConflictStatus.INSUFFICIENT_EVIDENCE,

                    )

                    hints = self._generate_conflict_hints(result.status, evidence)

                    return ConflictAnalysis(

                        action_id=action.action_id,

                        conflict_status=result.status,

                        details=result.details,

                        blocking=blocking,

                        resolution_hints=hints,

                    )

                except Exception as exc:  # pragma: no cover - best effort

                    logger.warning(

                        "Conflict check failed for %s: %s", action.action_id, exc

                    )

                    continue



        return ConflictAnalysis(

            action_id=action.action_id,

            conflict_status=ConflictStatus.NO_CONFLICT,

            details={},

            blocking=False,

            resolution_hints=[],

        )



    def _generate_conflict_hints(

        self, status: ConflictStatus, evidence: RecoveryEvidence

    ) -> list[str]:

        hints = []

        if status == ConflictStatus.VERSION_MISMATCH:

            hints.append("Resource version has changed; consider re-capturing state")

        elif status == ConflictStatus.CONCURRENT_MUTATION:

            hints.append("Concurrent modification detected; coordinate with other actors")

        elif status == ConflictStatus.RESOURCE_MISSING:

            hints.append("Target resource no longer exists; manual recreation may be needed")

        elif status == ConflictStatus.PRECONDITION_FAILED:

            hints.append("Preconditions not met; verify system state before recovery")

        return hints



    async def check_prerequisites(

        self,

        tenant_id: str,

        actions: list[ProtectedAction],

        current_states: dict[str, dict[str, Any]] | None = None,

    ) -> list[PrerequisiteCheck]:

        current_states = current_states or {}

        checks: list[PrerequisiteCheck] = []



        for action in actions:

            evidence = await self._get_evidence(tenant_id, action.action_id)

            if evidence is None:

                checks.append(PrerequisiteCheck(

                    action_id=action.action_id,

                    satisfied=False,

                    failed_checks=["No recovery evidence"],

                    details={"reason": "evidence_missing"},

                ))

                continue



            satisfied = True

            failed = []

            details: dict[str, Any] = {}



            if not evidence.before_state_reference:

                satisfied = False

                failed.append("before_state_missing")

                details["before_state_missing"] = True



            if evidence.reversibility_classification == Reversibility.IRREVERSIBLE:

                satisfied = False

                failed.append("irreversible_action")

                details["irreversible"] = True



            for adapter in self._adapters:

                if hasattr(adapter, "check_preconditions"):

                    try:

                        result = await adapter.check_preconditions(

                            action, current_states.get(action.resource)

                        )

                        if not result.satisfied:

                            satisfied = False

                            failed.extend(result.failed_checks)

                            details.update(result.details)

                    except Exception as exc:  # pragma: no cover - best effort

                        logger.warning(

                            "Precondition check failed for %s: %s", action.action_id, exc

                        )

                        continue



            checks.append(PrerequisiteCheck(

                action_id=action.action_id,

                satisfied=satisfied,

                failed_checks=failed,

                details=details,

            ))



        return checks



    def define_boundaries(

        self,

        actions: list[ProtectedAction],

        conflicts: list[ConflictAnalysis],

        prerequisites: list[PrerequisiteCheck],

    ) -> BoundaryDefinition:

        rollback_boundary = []

        compensation_boundary = []

        human_approval_boundary = []

        verification_boundary = []



        for action in actions:

            rev = Reversibility.normalize(action.reversibility)

            if rev in (

                Reversibility.AUTOMATICALLY_REVERSIBLE,

                Reversibility.CONDITIONALLY_REVERSIBLE,

            ):

                rollback_boundary.append(action.action_id)

                compensation_boundary.append(action.action_id)

            if rev in (

                Reversibility.CONDITIONALLY_REVERSIBLE,

                Reversibility.MANUALLY_RECOVERABLE,

            ):

                human_approval_boundary.append(action.action_id)

            if rev != Reversibility.IRREVERSIBLE:

                verification_boundary.append(action.action_id)



        for conflict in conflicts:

            if conflict.blocking:

                if conflict.action_id in rollback_boundary:

                    rollback_boundary.remove(conflict.action_id)

                if conflict.action_id in compensation_boundary:

                    compensation_boundary.remove(conflict.action_id)



        for prereq in prerequisites:

            if not prereq.satisfied:

                if prereq.action_id in rollback_boundary:

                    rollback_boundary.remove(prereq.action_id)

                if prereq.action_id in compensation_boundary:

                    compensation_boundary.remove(prereq.action_id)



        return BoundaryDefinition(

            rollback_boundary=rollback_boundary,

            compensation_boundary=compensation_boundary,

            human_approval_boundary=human_approval_boundary,

            verification_boundary=verification_boundary,

        )



    def compute_metrics(

        self,

        actions: list[ProtectedAction],

        conflicts: list[ConflictAnalysis],

        prerequisites: list[PrerequisiteCheck],

        boundaries: BoundaryDefinition,

        strategy: RecoveryStrategy,

    ) -> PlanMetrics:

        total = len(actions)

        if total == 0:

            return PlanMetrics()



        rev_norm = Reversibility.normalize

        auto_rev = Reversibility.AUTOMATICALLY_REVERSIBLE

        cond_rev = Reversibility.CONDITIONALLY_REVERSIBLE

        irr_rev = Reversibility.IRREVERSIBLE

        unk_rev = Reversibility.UNKNOWN



        directly_reversible = sum(1 for a in actions if rev_norm(a.reversibility) == auto_rev)

        conditionally_reversible = sum(1 for a in actions if rev_norm(a.reversibility) == cond_rev)

        _irreversible = sum(1 for a in actions if rev_norm(a.reversibility) == irr_rev)

        unknown = sum(1 for a in actions if rev_norm(a.reversibility) == unk_rev)



        blocked_conflicts = sum(1 for c in conflicts if c.blocking)

        failed_prereqs = sum(1 for p in prerequisites if not p.satisfied)



        base_cost = total * 1.0

        base_time = total * 2.0



        if strategy == RecoveryStrategy.MINIMAL_CHANGE:

            cost = base_cost * 0.8

            time = base_time * 0.7

            collateral = 0.2

            safety = 0.6

        elif strategy == RecoveryStrategy.MAX_SAFETY:

            cost = base_cost * 1.5

            time = base_time * 2.0

            collateral = 0.1

            safety = 1.0

        elif strategy == RecoveryStrategy.MIN_DOWNTIME:

            cost = base_cost * 1.2

            time = base_time * 0.5

            collateral = 0.4

            safety = 0.5

        elif strategy == RecoveryStrategy.MIN_DATA_LOSS:

            cost = base_cost * 1.3

            time = base_time * 1.5

            collateral = 0.3

            safety = 0.9

        elif strategy == RecoveryStrategy.EMERGENCY:

            cost = base_cost * 2.0

            time = base_time * 0.3

            collateral = 0.6

            safety = 0.4

        else:

            cost = base_cost * 1.0

            time = base_time * 3.0

            collateral = 0.2

            safety = 0.7



        uncertainty = (unknown + blocked_conflicts + failed_prereqs) / max(total, 1)

        completeness = (directly_reversible + conditionally_reversible) / max(total, 1)

        human_impact = len(boundaries.human_approval_boundary) / max(total, 1)



        return PlanMetrics(

            estimated_cost=round(cost, 2),

            estimated_time_seconds=round(time, 2),

            collateral_damage_score=round(collateral, 2),

            uncertainty_score=round(uncertainty, 2),

            completeness_score=round(completeness, 2),

            safety_score=round(safety, 2),

            human_impact_score=round(human_impact, 2),

        )



    async def generate_alternatives(

        self,

        tenant_id: str,

        root_action_id: str,

        strategies: list[RecoveryStrategy] | None = None,

        mode: PlanningMode = PlanningMode.STANDARD,

    ) -> list[RecoveryAlternative]:

        strategies = strategies or [

            RecoveryStrategy.MINIMAL_CHANGE,

            RecoveryStrategy.MAX_SAFETY,

            RecoveryStrategy.MIN_DOWNTIME,

            RecoveryStrategy.MIN_DATA_LOSS,

            RecoveryStrategy.EMERGENCY,

            RecoveryStrategy.DEFERRED,

        ]



        graph = await self.build_dependency_graph(tenant_id, root_action_id)

        actions = [

            self._node_to_action(graph.nodes[nid])

            for nid in graph.topological_order

            if nid in graph.nodes

        ]



        current_states: dict[str, dict[str, Any]] = {}

        conflicts = await self.analyze_conflicts(tenant_id, actions, current_states)

        prerequisites = await self.check_prerequisites(tenant_id, actions, current_states)



        alternatives: list[RecoveryAlternative] = []



        for strategy in strategies:

            if mode == PlanningMode.EMERGENCY and strategy != RecoveryStrategy.EMERGENCY:

                continue

            if mode == PlanningMode.DEFERRED and strategy != RecoveryStrategy.DEFERRED:

                continue



            boundaries = self.define_boundaries(actions, conflicts, prerequisites)

            metrics = self.compute_metrics(

                actions, conflicts, prerequisites, boundaries, strategy

            )

            compensation_actions = await self._generate_compensation_actions(

                tenant_id, actions, strategy

            )

            explanations = self._generate_explanations(

                actions, conflicts, prerequisites, boundaries, strategy

            )

            warnings = self._generate_warnings(

                actions, conflicts, prerequisites, strategy

            )



            plan_id = f"plan-{secrets.token_hex(8)}-{strategy.value}"

            _plan_hash = self._compute_plan_hash(plan_id, graph.topological_order)



            provenance = {

                "generated_at": datetime.now(UTC).isoformat(),

                "generator": "RecoveryIntelligenceService",

                "root_action_id": root_action_id,

                "strategy": strategy.value,

                "mode": mode.value,

                "graph_hash": hashlib.sha256(

                    str(graph.topological_order).encode()

                ).hexdigest()[:16],

            }



            alt = RecoveryAlternative(

                plan_id=plan_id,

                strategy=strategy,

                topological_order=graph.topological_order,

                metrics=metrics,

                affected_actions=[a.action_id for a in actions],

                compensation_actions=compensation_actions,

                prerequisites=prerequisites,

                conflicts=conflicts,

                boundaries=boundaries,

                warnings=warnings,

                explanations=explanations,

                provenance=provenance,

            )

            alternatives.append(alt)



        return alternatives



    def _node_to_action(self, node: DependencyNode) -> ProtectedAction:

        return ProtectedAction(

            action_id=node.action_id,

            tenant_id="",

            actor_user_id=None,

            agent_id="",

            authority_grant_id=None,

            tool=node.tool,

            resource=node.resource,

            action_type="",

            reversibility=node.reversibility,

        )



    async def _generate_compensation_actions(

        self,

        tenant_id: str,

        actions: list[ProtectedAction],

        strategy: RecoveryStrategy,

    ) -> list[dict[str, Any]]:

        comp_actions: list[dict[str, Any]] = []



        for action in actions:

            evidence = await self._get_evidence(tenant_id, action.action_id)

            if evidence is None:

                continue



            rev = Reversibility.normalize(evidence.reversibility_classification)

            if rev == Reversibility.IRREVERSIBLE:

                continue



            for adapter in self._adapters:

                if hasattr(adapter, "generate_compensation"):

                    try:

                        comp = await adapter.generate_compensation(action, evidence)

                        comp_actions.append({

                            "action_id": comp.action_id,

                            "compensation_type": comp.compensation_type.value,

                            "target_system": comp.target_system,

                            "target_resource": comp.target_resource,

                            "execution_order": comp.execution_order,

                            "reversibility": comp.reversibility.value,

                            "idempotency_key": comp.idempotency_key,

                            "verification_requirements": comp.verification_requirements,

                            "dependency_edges": comp.dependency_edges,

                        })

                        break

                    except Exception as exc:  # pragma: no cover - best effort

                        logger.warning(

                            "Compensation generation failed for %s: %s",

                            action.action_id,

                            exc,

                        )

                        continue



            if not any(c["action_id"] == action.action_id for c in comp_actions):

                comp_actions.append({

                    "action_id": action.action_id,

                    "compensation_type": CompensationType.CUSTOM.value,

                    "target_system": evidence.target_system,

                    "target_resource": evidence.target_resource,

                    "execution_order": 0,

                    "reversibility": rev.value,

                    "idempotency_key": evidence.idempotency_key or f"idem-{action.action_id}",

                    "verification_requirements": evidence.verification_requirements,

                    "dependency_edges": evidence.dependency_edges,

                })



        comp_actions.sort(key=lambda c: c["execution_order"])

        return comp_actions



    def _generate_explanations(

        self,

        actions: list[ProtectedAction],

        conflicts: list[ConflictAnalysis],

        prerequisites: list[PrerequisiteCheck],

        boundaries: BoundaryDefinition,

        strategy: RecoveryStrategy,

    ) -> list[str]:

        explanations = [

            f"Strategy: {strategy.value} - prioritizes {strategy.value.replace('_', ' ')}",

            f"Total actions: {len(actions)}",

            f"Rollback boundary: {len(boundaries.rollback_boundary)} actions",

            f"Compensation boundary: {len(boundaries.compensation_boundary)} actions",

            f"Human approval required for: {len(boundaries.human_approval_boundary)} actions",

            f"Verification boundary: {len(boundaries.verification_boundary)} actions",

        ]



        for conflict in conflicts:

            if conflict.blocking:

                hints = ", ".join(conflict.resolution_hints)

                explanations.append(

                    f"BLOCKING CONFLICT: {conflict.action_id} - "

                    f"{conflict.conflict_status.value}: {hints}"

                )



        for prereq in prerequisites:

            if not prereq.satisfied:

                failed = ", ".join(prereq.failed_checks)

                explanations.append(

                    f"PREREQUISITE FAILED: {prereq.action_id} - {failed}"

                )



        return explanations



    def _generate_warnings(

        self,

        actions: list[ProtectedAction],

        conflicts: list[ConflictAnalysis],

        prerequisites: list[PrerequisiteCheck],

        strategy: RecoveryStrategy,

    ) -> list[str]:

        warnings = []



        rev_norm = Reversibility.normalize

        irr_rev = Reversibility.IRREVERSIBLE

        unk_rev = Reversibility.UNKNOWN



        irreversible = [

            a.action_id for a in actions if rev_norm(a.reversibility) == irr_rev

        ]

        if irreversible:

            warnings.append(f"Irreversible actions (cannot auto-recover): {irreversible}")



        unknown = [

            a.action_id for a in actions if rev_norm(a.reversibility) == unk_rev

        ]

        if unknown:

            warnings.append(f"Unknown reversibility (fail closed): {unknown}")



        blocking_conflicts = [c.action_id for c in conflicts if c.blocking]

        if blocking_conflicts:

            warnings.append(f"Blocking conflicts: {blocking_conflicts}")



        failed_prereqs = [p.action_id for p in prerequisites if not p.satisfied]

        if failed_prereqs:

            warnings.append(f"Failed prerequisites: {failed_prereqs}")



        if strategy == RecoveryStrategy.EMERGENCY:

            warnings.append("EMERGENCY MODE: Reduced safety checks, higher collateral risk")



        return warnings



    def _compute_plan_hash(self, plan_id: str, topological_order: list[str]) -> str:

        payload = f"{plan_id}:{topological_order}"

        return hashlib.sha256(payload.encode()).hexdigest()



    def compare_alternatives(

        self,

        alternatives: list[RecoveryAlternative],

        criterion: PlanComparisonCriterion = PlanComparisonCriterion.SAFETY,

    ) -> PlanComparison:

        if not alternatives:

            return PlanComparison(alternatives=[], ranked_by=criterion, ranking=[])



        def score(alt: RecoveryAlternative) -> float:

            m = alt.metrics

            if criterion == PlanComparisonCriterion.COST:

                return -m.estimated_cost

            elif criterion == PlanComparisonCriterion.TIME:

                return -m.estimated_time_seconds

            elif criterion == PlanComparisonCriterion.COLLATERAL_DAMAGE:

                return -m.collateral_damage_score

            elif criterion == PlanComparisonCriterion.UNCERTAINTY:

                return -m.uncertainty_score

            elif criterion == PlanComparisonCriterion.COMPLETENESS:

                return m.completeness_score

            elif criterion == PlanComparisonCriterion.SAFETY:

                return m.safety_score

            elif criterion == PlanComparisonCriterion.HUMAN_IMPACT:

                return -m.human_impact_score

            return 0.0



        ranked = sorted(alternatives, key=score, reverse=True)

        ranking = [a.plan_id for a in ranked]

        selection = ranking[0] if ranking else None



        rationale_parts = [f"Selected {selection} by {criterion.value}"]

        if selection:

            selected = next(a for a in ranked if a.plan_id == selection)

            rationale_parts.append(f"score={score(selected):.2f}")

            rationale_parts.append(f"safety={selected.metrics.safety_score:.2f}")

            rationale_parts.append(f"cost={selected.metrics.estimated_cost:.2f}")

            rationale_parts.append(f"time={selected.metrics.estimated_time_seconds:.2f}s")



        return PlanComparison(

            alternatives=alternatives,

            ranked_by=criterion,

            ranking=ranking,

            selection=selection,

            selection_rationale="; ".join(rationale_parts),

        )



    def select_best_plan(

        self,

        comparison: PlanComparison,

        safety_threshold: float = 0.5,

        max_cost: float | None = None,

        max_time: float | None = None,

    ) -> RecoveryAlternative | None:

        for alt in comparison.alternatives:

            if alt.metrics.safety_score < safety_threshold:

                continue

            if max_cost is not None and alt.metrics.estimated_cost > max_cost:

                continue

            if max_time is not None and alt.metrics.estimated_time_seconds > max_time:

                continue

            if any(c.blocking for c in alt.conflicts):

                continue

            if any(not p.satisfied for p in alt.prerequisites):

                continue

            return alt

        return None



    def validate_plan(self, alternative: RecoveryAlternative) -> ValidationResult:

        errors: list[str] = []

        warnings: list[str] = []

        failed_checks: list[str] = []



        if alternative.metrics.uncertainty_score > 0.5:

            errors.append(f"High uncertainty: {alternative.metrics.uncertainty_score:.2f}")

            failed_checks.append("uncertainty_threshold")



        if any(c.blocking for c in alternative.conflicts):

            errors.append("Blocking conflicts present")

            failed_checks.append("blocking_conflicts")



        if any(not p.satisfied for p in alternative.prerequisites):

            errors.append("Unsatisfied prerequisites")

            failed_checks.append("prerequisites")



        if not alternative.boundaries.verification_boundary:

            warnings.append("No verification boundary defined")



        if alternative.metrics.collateral_damage_score > 0.7:

            warnings.append(

                f"High collateral damage risk: "

                f"{alternative.metrics.collateral_damage_score:.2f}"

            )



        if alternative.metrics.human_impact_score > 0.8:

            warnings.append(

                f"High human impact: {alternative.metrics.human_impact_score:.2f}"

            )



        if not errors:

            return ValidationResult(validity=PlanValidity.VALID, warnings=warnings)



        has_cycle = any("cycle" in e.lower() for e in errors)

        has_prereq = any("prerequisite" in e.lower() for e in errors)

        has_conflict = any("conflict" in e.lower() for e in errors)



        if has_cycle:

            return ValidationResult(

                validity=PlanValidity.INVALID_CYCLE,

                errors=errors,

                warnings=warnings,

                failed_checks=failed_checks,

            )

        if has_prereq:

            return ValidationResult(

                validity=PlanValidity.INVALID_PREREQUISITE,

                errors=errors,

                warnings=warnings,

                failed_checks=failed_checks,

            )

        if has_conflict:

            return ValidationResult(

                validity=PlanValidity.INVALID_CONFLICT,

                errors=errors,

                warnings=warnings,

                failed_checks=failed_checks,

            )



        return ValidationResult(

            validity=PlanValidity.INVALID_BOUNDARY,

            errors=errors,

            warnings=warnings,

            failed_checks=failed_checks,

        )



    def evaluate_safety_gates(self, alternative: RecoveryAlternative) -> list[SafetyGateResult]:

        gates: list[SafetyGateResult] = []



        # Check for irreversible actions - use metrics as proxy

        # completeness_score < 1.0 implies some irreversible/unknown actions

        has_irreversible = alternative.metrics.completeness_score < 1.0

        irreversible_count = int(has_irreversible)  # placeholder



        gates.append(SafetyGateResult(

            gate_name="irreversible_actions_check",

            passed=not has_irreversible,

            details={"irreversible_count": irreversible_count},

            blocking=True,

            remediation="Remove or manually handle irreversible actions",

        ))



        gates.append(SafetyGateResult(

            gate_name="evidence_completeness",

            passed=alternative.metrics.completeness_score >= 0.5,

            details={"completeness": alternative.metrics.completeness_score},

            blocking=True,

            remediation="Capture evidence for all affected actions",

        ))



        blocking_conflicts = [

            c.action_id for c in alternative.conflicts if c.blocking

        ]

        gates.append(SafetyGateResult(

            gate_name="conflict_free",

            passed=not blocking_conflicts,

            details={"blocking_conflicts": blocking_conflicts},

            blocking=True,

            remediation="Resolve conflicts before execution",

        ))



        failed_prereqs = [

            p.action_id for p in alternative.prerequisites if not p.satisfied

        ]

        gates.append(SafetyGateResult(

            gate_name="prerequisites_met",

            passed=not failed_prereqs,

            details={"failed_prerequisites": failed_prereqs},

            blocking=True,

            remediation="Satisfy all prerequisites",

        ))



        requires_approval = alternative.boundaries.human_approval_boundary

        gates.append(SafetyGateResult(

            gate_name="human_approval_boundary",

            passed=len(requires_approval) == 0

            or alternative.strategy != RecoveryStrategy.EMERGENCY,

            details={"requires_approval": requires_approval},

            blocking=False,

            remediation="Obtain human approvals before execution",

        ))



        gates.append(SafetyGateResult(

            gate_name="verification_capability",

            passed=len(alternative.boundaries.verification_boundary) > 0,

            details={

                "verifiable_actions": len(

                    alternative.boundaries.verification_boundary

                )

            },

            blocking=False,

            remediation="Ensure verification capability for all recovery actions",

        ))



        return gates



    def assess_human_impact(

        self,

        alternative: RecoveryAlternative,

    ) -> list[HumanImpactAssessment]:

        assessments: list[HumanImpactAssessment] = []



        for action_id in alternative.boundaries.human_approval_boundary:

            action = next((a for a in alternative.affected_actions if a == action_id), None)

            if action:

                assessments.append(HumanImpactAssessment(

                    action_id=action_id,

                    requires_human_approval=True,

                    approval_reason=(

                        f"Action {action_id} requires manual review "

                        f"per recovery strategy"

                    ),

                    estimated_human_time_seconds=300.0,

                    affected_parties=["security_team", "system_owner"],

                    notification_required=True,

                ))



        return assessments



    def analyze_cascading_impact(

        self,

        graph: DependencyGraph,

        root_action_id: str,

    ) -> CascadingImpactAnalysis:

        affected = set()

        cross_system: dict[str, list[str]] = defaultdict(list)



        def traverse(node_id: str, depth: int) -> int:

            if node_id not in graph.nodes:

                return depth

            affected.add(node_id)

            node = graph.nodes[node_id]

            system = node.tool

            cross_system[system].append(node_id)

            max_d = depth

            for child in node.children:

                max_d = max(max_d, traverse(child, depth + 1))

            for dep in node.depends_on:

                max_d = max(max_d, traverse(dep, depth + 1))

            return max_d



        max_depth = traverse(root_action_id, 0)

        blast_radius = len(affected)



        containment_options = []

        if blast_radius > 10:

            containment_options.append("staged_recovery")

        if len(cross_system) > 1:

            containment_options.append("cross_system_coordination")

        if max_depth > 5:

            containment_options.append("depth_limited_recovery")



        return CascadingImpactAnalysis(

            root_action_id=root_action_id,

            cascade_depth=max_depth,

            affected_resources=list(affected),

            cross_system_impacts=dict(cross_system),

            blast_radius_estimate=blast_radius,

            containment_options=containment_options,

        )



    def register_plan_version(

        self,

        plan_id: str,

        version: str,

        plan_hash: str,

        supersedes: str | None = None,

        expires_at: datetime | None = None,

        metadata: dict[str, Any] | None = None,

    ) -> RecoveryPlanVersion:

        pv = RecoveryPlanVersion(

            plan_id=plan_id,

            version=version,

            plan_hash=plan_hash,

            created_at=datetime.now(UTC),

            supersedes=supersedes,

            expires_at=expires_at,

            metadata=metadata or {},

        )



        if supersedes:

            # Update superseded version - create new version with superseded_by

            updated_versions = []

            for v in self._plan_versions[plan_id]:

                if v.version == supersedes:

                    # Create new version with superseded_by set

                    updated = RecoveryPlanVersion(

                        plan_id=v.plan_id,

                        version=v.version,

                        plan_hash=v.plan_hash,

                        created_at=v.created_at,

                        supersedes=v.supersedes,

                        superseded_by=version,

                        expires_at=v.expires_at,

                        is_active=v.is_active,

                        metadata=v.metadata,

                    )

                    updated_versions.append(updated)

                else:

                    updated_versions.append(v)

            self._plan_versions[plan_id] = updated_versions



        self._plan_versions[plan_id].append(pv)

        return pv



    def get_plan_versions(self, plan_id: str) -> list[RecoveryPlanVersion]:

        return self._plan_versions.get(plan_id, [])



    def get_active_version(self, plan_id: str) -> RecoveryPlanVersion | None:

        versions = self._plan_versions.get(plan_id, [])

        now = datetime.now(UTC)

        active = [

            v

            for v in versions

            if v.is_active and (v.expires_at is None or v.expires_at > now)

        ]

        return max(active, key=lambda v: v.created_at) if active else None



    async def analyze_recovery_feasibility(

        self,

        tenant_id: str,

        actions: list[ProtectedAction],

        conflicts: list[ConflictAnalysis],

        prerequisites: list[PrerequisiteCheck],

        boundaries: BoundaryDefinition,

    ) -> FeasibilityReport:

        blockers: list[str] = []

        warnings: list[str] = []

        mitigations: list[str] = []



        blocking_conflicts = [c for c in conflicts if c.blocking]

        failed_prereqs = [p for p in prerequisites if not p.satisfied]

        irreversible_actions = [

            a.action_id for a in actions

            if Reversibility.normalize(a.reversibility) == Reversibility.IRREVERSIBLE

        ]

        unknown_rev_actions = [

            a.action_id for a in actions

            if Reversibility.normalize(a.reversibility) == Reversibility.UNKNOWN

        ]



        if not actions:

            blockers.append("No actions to recover")

            return FeasibilityReport(

                feasible=False,

                feasibility_score=0.0,

                blockers=blockers,

                warnings=warnings,

                mitigations=mitigations,

                risk_level="critical",

            )



        total = len(actions)



        for c in blocking_conflicts:

            blockers.append(f"Blocking conflict on {c.action_id}: {c.conflict_status.value}")

            mitigations.extend(c.resolution_hints)



        for p in failed_prereqs:

            blockers.append(f"Unsatisfied prerequisite on {p.action_id}: {p.failed_checks}")



        if irreversible_actions:

            blockers.append(f"Irreversible actions cannot auto-recover: {irreversible_actions}")

            mitigations.append("Manual recovery required for irreversible actions")



        if unknown_rev_actions:

            warnings.append(f"Unknown reversibility (fail closed): {unknown_rev_actions}")



        if not boundaries.rollback_boundary and total > 0:

            warnings.append("Empty rollback boundary - no auto-recoverable actions")



        evidence_count = 0

        for action in actions:

            evidence = await self._get_evidence(tenant_id, action.action_id)

            if evidence is not None and evidence.before_state_reference:

                evidence_count += 1



        evidence_completeness = evidence_count / total if total > 0 else 0.0

        if evidence_completeness < 0.5:

            warnings.append(f"Low evidence completeness: {evidence_completeness:.2f}")

            mitigations.append("Capture before-state references for all actions")



        dep_coverage = 0.0

        dep_checked = 0

        for action in actions:

            evidence = await self._get_evidence(tenant_id, action.action_id)

            if evidence is not None:

                dep_checked += 1

                if evidence.dependency_edges:

                    pass

        dependency_coverage = dep_checked / total if total > 0 else 0.0



        if total > 0:

            dep_edges_ok = 0

            for a in actions:

                evidence = await self._get_evidence(tenant_id, a.action_id)

                if evidence is not None:

                                dep_edges_ok += 1

                                if evidence.dependency_edges:

                                                dep_edges_ok += 1

                                dep_edges_ok = min(dep_edges_ok, total)

            dependency_coverage = dep_edges_ok / total

            dependency_coverage = dep_edges_ok / total

        else:

            dependency_coverage = 0.0



        penalty = (

            len(blocking_conflicts) * 0.2

            + len(failed_prereqs) * 0.15

            + len(irreversible_actions) * 0.25

            + len(unknown_rev_actions) * 0.05

            + (1.0 - evidence_completeness) * 0.2

            + (1.0 - dependency_coverage) * 0.1

        )

        feasibility_score = max(0.0, min(1.0, 1.0 - penalty))



        if feasibility_score >= 0.7:

            risk_level = "low"

        elif feasibility_score >= 0.4:

            risk_level = "medium"

        else:

            risk_level = "high"



        if feasibility_score < 0.3 or len(irreversible_actions) > total * 0.5:

            recommended = RecoveryStrategy.MAX_SAFETY

        elif feasibility_score < 0.6:

            recommended = RecoveryStrategy.MINIMAL_CHANGE

        else:

            recommended = RecoveryStrategy.MIN_DOWNTIME



        feasible = len(blockers) == 0 and feasibility_score >= 0.3



        return FeasibilityReport(

            feasible=feasible,

            feasibility_score=round(feasibility_score, 4),

            blockers=blockers,

            warnings=warnings,

            mitigations=mitigations,

            recommended_strategy=recommended,

            evidence_completeness=round(evidence_completeness, 4),

            dependency_coverage=round(dependency_coverage, 4),

            risk_level=risk_level,

        )




    async def assess_feasibility(
        self,
        tenant_id: str,
        actions: list[ProtectedAction],
        conflicts: list[ConflictAnalysis],
        prerequisites: list[PrerequisiteCheck],
        boundaries: BoundaryDefinition,
        confidence_score: float | None = None,
        safety_score: float | None = None,
    ) -> FeasibilityReport:
        """Assess recovery feasibility with confidence/safety evidence integration.

        Extends the basic feasibility assessment by optionally incorporating
        explicit recovery-score and confidence-level evidence. A low confidence
        or safety score introduces additional warnings and reduces the
        feasibility score accordingly.
        """
        blockers: list[str] = []
        warnings: list[str] = []
        mitigations: list[str] = []

        blocking_conflicts = [c for c in conflicts if c.blocking]
        failed_prereqs = [p for p in prerequisites if not p.satisfied]
        irreversible_actions = [
            a.action_id for a in actions
            if Reversibility.normalize(a.reversibility) == Reversibility.IRREVERSIBLE
        ]
        unknown_rev_actions = [
            a.action_id for a in actions
            if Reversibility.normalize(a.reversibility) == Reversibility.UNKNOWN
        ]

        if not actions:
            blockers.append("No actions to recover")
            return FeasibilityReport(
                feasible=False,
                feasibility_score=0.0,
                blockers=blockers,
                warnings=warnings,
                mitigations=mitigations,
                risk_level="critical",
            )

        total = len(actions)

        for c in blocking_conflicts:
            blockers.append(
                f"Blocking conflict on {c.action_id}: {c.conflict_status.value}"
            )
            mitigations.extend(c.resolution_hints)

        for p in failed_prereqs:
            blockers.append(
                f"Unsatisfied prerequisite on {p.action_id}: {p.failed_checks}"
            )

        if irreversible_actions:
            blockers.append(
                f"Irreversible actions cannot auto-recover: {irreversible_actions}"
            )
            mitigations.append("Manual recovery required for irreversible actions")

        if unknown_rev_actions:
            warnings.append(
                f"Unknown reversibility (fail closed): {unknown_rev_actions}"
            )

        if not boundaries.rollback_boundary and total > 0:
            warnings.append("Empty rollback boundary - no auto-recoverable actions")

        evidence_by_action: dict[str, RecoveryEvidence] = {}
        evidence_count = 0
        dep_edges_ok = 0

        for action in actions:
            evidence = await self._get_evidence(tenant_id, action.action_id)
            if evidence is not None:
                evidence_by_action[action.action_id] = evidence
                if evidence.before_state_reference:
                    evidence_count += 1
                if evidence.dependency_edges:
                    dep_edges_ok += 1

        evidence_completeness = evidence_count / total if total > 0 else 0.0
        dependency_coverage = dep_edges_ok / total if total > 0 else 0.0

        if evidence_completeness < 0.5:
            warnings.append(
                f"Low evidence completeness: {evidence_completeness:.2f}"
            )
            mitigations.append("Capture before-state references for all actions")

        if confidence_score is not None and confidence_score < 0.5:
            warnings.append(f"Low confidence score: {confidence_score:.2f}")
            mitigations.append(
                "Improve evidence completeness and adapter reliability before recovery"
            )

        if safety_score is not None and safety_score < 0.5:
            warnings.append(f"Low safety score: {safety_score:.2f}")
            mitigations.append("Address safety concerns before recovery")

        penalty = (
            len(blocking_conflicts) * 0.2
            + len(failed_prereqs) * 0.15
            + len(irreversible_actions) * 0.25
            + len(unknown_rev_actions) * 0.05
            + (1.0 - evidence_completeness) * 0.2
            + (1.0 - dependency_coverage) * 0.1
        )

        if confidence_score is not None and confidence_score < 0.5:
            penalty += (1.0 - confidence_score) * 0.15
        if safety_score is not None and safety_score < 0.5:
            penalty += (1.0 - safety_score) * 0.15


        feasibility_score = max(0.0, min(1.0, 1.0 - penalty))

        if feasibility_score >= 0.7:
            risk_level = "low"
        elif feasibility_score >= 0.4:
            risk_level = "medium"
        else:
            risk_level = "high"

        if feasibility_score < 0.3 or len(irreversible_actions) > total * 0.5:
            recommended = RecoveryStrategy.MAX_SAFETY
        elif feasibility_score < 0.6:
            recommended = RecoveryStrategy.MINIMAL_CHANGE
        else:
            recommended = RecoveryStrategy.MIN_DOWNTIME

        feasible = len(blockers) == 0 and feasibility_score >= 0.3

        return FeasibilityReport(
            feasible=feasible,
            feasibility_score=round(feasibility_score, 4),
            blockers=blockers,
            warnings=warnings,
            mitigations=mitigations,
            recommended_strategy=recommended,
            evidence_completeness=round(evidence_completeness, 4),
            dependency_coverage=round(dependency_coverage, 4),
            risk_level=risk_level,
        )


    def compute_recovery_ordering(

        self,

        graph: DependencyGraph,

        mode: str = "standard",

    ) -> list[str]:

        order = list(graph.topological_order)



        if graph.cycles:

            cycle_nodes: set[str] = set()

            for cycle in graph.cycles:

                cycle_nodes.update(cycle)

            order = [nid for nid in order if nid not in cycle_nodes]



        missing = [nid for nid in order if nid not in graph.nodes]

        order = [nid for nid in order if nid in graph.nodes]



        if mode == "leaves_first":

            order = list(reversed(order))

        elif mode == "roots_first":

            order = list(order)

        elif mode == "reversibility_first":

            rev_norm = Reversibility.normalize

            auto_rev = Reversibility.AUTOMATICALLY_REVERSIBLE

            cond_rev = Reversibility.CONDITIONALLY_REVERSIBLE

            auto = [n for n in order if graph.nodes[n].reversibility == auto_rev]

            cond = [n for n in order if graph.nodes[n].reversibility == cond_rev]

            other = [n for n in order if graph.nodes[n].reversibility not in (auto_rev, cond_rev)]

            order = auto + cond + other



        if missing:

            logger.warning("Removed missing nodes from ordering: %s", missing)



        return order



    def compute_boundary_risk(

        self,

        boundaries: BoundaryDefinition,

        actions: list[ProtectedAction],

        conflicts: list[ConflictAnalysis],

        prerequisites: list[PrerequisiteCheck],

    ) -> dict[str, Any]:

        total = len(actions) if actions else 0

        if total == 0:

            return {"overall_risk": 0.0, "risk_level": "low", "details": {}}



        rollback_count = len(boundaries.rollback_boundary)

        comp_count = len(boundaries.compensation_boundary)

        human_count = len(boundaries.human_approval_boundary)

        verify_count = len(boundaries.verification_boundary)



        blocking_conflicts = [c for c in conflicts if c.blocking]

        failed_prereqs = [p for p in prerequisites if not p.satisfied]



        rollback_risk = 1.0 - (rollback_count / total)

        comp_risk = 1.0 - (comp_count / total)

        human_risk = human_count / total

        verify_risk = 1.0 - (verify_count / total)

        conflict_risk = len(blocking_conflicts) / total

        prereq_risk = len(failed_prereqs) / total



        overall = (

            rollback_risk * 0.2

            + comp_risk * 0.2

            + human_risk * 0.15

            + verify_risk * 0.15

            + conflict_risk * 0.15

            + prereq_risk * 0.15

        )

        overall = max(0.0, min(1.0, overall))



        if overall >= 0.7:

            risk_level = "critical"

        elif overall >= 0.4:

            risk_level = "high"

        elif overall >= 0.2:

            risk_level = "medium"

        else:

            risk_level = "low"



        return {

            "overall_risk": round(overall, 4),

            "risk_level": risk_level,

            "details": {

                "rollback_risk": round(rollback_risk, 4),

                "compensation_risk": round(comp_risk, 4),

                "human_approval_risk": round(human_risk, 4),

                "verification_risk": round(verify_risk, 4),

                "conflict_risk": round(conflict_risk, 4),

                "prerequisite_risk": round(prereq_risk, 4),

                "rollback_count": rollback_count,

                "compensation_count": comp_count,

                "human_approval_count": human_count,

                "verification_count": verify_count,

                "blocking_conflicts": len(blocking_conflicts),

                "failed_prerequisites": len(failed_prereqs),

            },

        }



    def _augment_alternatives(

        self,

        alternatives: list[RecoveryAlternative],

        comparison: PlanComparison,

    ) -> list[RecoveryAlternative]:

        augmented: list[RecoveryAlternative] = []

        selected_id = comparison.selection



        for alt in alternatives:

            is_selected = alt.plan_id == selected_id

            rank_idx = comparison.ranking.index(alt.plan_id) if alt.plan_id in comparison.ranking else -1

            explanations = list(alt.explanations)

            if is_selected:

                explanations.append(f"Selected as best plan by {comparison.ranked_by.value}")

            elif rank_idx >= 0:

                explanations.append(

                    f"Ranked #{rank_idx + 1} by {comparison.ranked_by.value}"

                )



            alt_dict = asdict(alt)

            alt_dict["explanations"] = explanations

            try:

                augmented.append(RecoveryAlternative(**alt_dict))

            except Exception:

                augmented.append(alt)



        return augmented



    def compare_alternatives_with_evidence(

        self,

        alternatives: list[RecoveryAlternative],

        criterion: PlanComparisonCriterion = PlanComparisonCriterion.SAFETY,

        confidence_weight: float = 0.3,

        safety_weight: float = 0.4,

        evidence_weight: float = 0.3,

    ) -> PlanComparison:

        if not alternatives:

            return PlanComparison(alternatives=[], ranked_by=criterion, ranking=[])



        def combined_score(alt: RecoveryAlternative) -> float:

            m = alt.metrics

            if criterion == PlanComparisonCriterion.SAFETY:

                criterion_score = m.safety_score

            elif criterion == PlanComparisonCriterion.COST:

                criterion_score = -m.estimated_cost

            elif criterion == PlanComparisonCriterion.TIME:

                criterion_score = -m.estimated_time_seconds

            elif criterion == PlanComparisonCriterion.COLLATERAL_DAMAGE:

                criterion_score = -m.collateral_damage_score

            elif criterion == PlanComparisonCriterion.UNCERTAINTY:

                criterion_score = -m.uncertainty_score

            elif criterion == PlanComparisonCriterion.COMPLETENESS:

                criterion_score = m.completeness_score

            elif criterion == PlanComparisonCriterion.HUMAN_IMPACT:

                criterion_score = -m.human_impact_score

            else:

                criterion_score = m.safety_score



            has_blocking = any(c.blocking for c in alt.conflicts)

            has_unsatisfied = any(not p.satisfied for p in alt.prerequisites)

            safety_penalty = 0.0

            if has_blocking:

                safety_penalty -= 0.5

            if has_unsatisfied:

                safety_penalty -= 0.3



            evidence_score = m.completeness_score

            if not alt.boundaries.verification_boundary:

                evidence_score -= 0.2



            return (

                confidence_weight * criterion_score

                + safety_weight * (m.safety_score + safety_penalty)

                + evidence_weight * evidence_score

            )



        ranked = sorted(alternatives, key=combined_score, reverse=True)

        ranking = [a.plan_id for a in ranked]

        selection = ranking[0] if ranking else None



        rationale_parts = [f"Selected {selection} by {criterion.value} (evidence-aware)"]

        if selection:

            selected = next(a for a in ranked if a.plan_id == selection)

            rationale_parts.append(f"combined_score={combined_score(selected):.2f}")

            rationale_parts.append(f"safety={selected.metrics.safety_score:.2f}")

            rationale_parts.append(f"evidence_completeness={selected.metrics.completeness_score:.2f}")



        comparison = PlanComparison(

            alternatives=alternatives,

            ranked_by=criterion,

            ranking=ranking,

            selection=selection,

            selection_rationale="; ".join(rationale_parts),

        )



        return PlanComparison(

            alternatives=alternatives,

            ranked_by=criterion,

            ranking=ranking,

            selection=selection,

            selection_rationale="; ".join(rationale_parts),

        )



    async def _get_action(self, tenant_id: str, action_id: str) -> ProtectedAction | None:

        if self._action_repo is None:

            return None

        result = await self._action_repo.get_by_action_id(tenant_id, action_id)

        return result if isinstance(result, ProtectedAction) else None



    async def _get_descendants(

        self,

        tenant_id: str,

        action_id: str,

        max_depth: int,

    ) -> tuple[list[ProtectedAction], int]:

        if self._action_repo is None:

            return [], 0

        result = await self._action_repo.list_descendants(

            tenant_id, action_id, limit=1000, offset=0

        )

        if isinstance(result, tuple) and len(result) == 2:

            actions, total = result

            return (

                actions if isinstance(actions, list) else [],

                total if isinstance(total, int) else 0,

            )

        return [], 0



    async def _get_evidence(self, tenant_id: str, action_id: str) -> RecoveryEvidence | None:

        if self._evidence_repo is None:

            return None

        result = await self._evidence_repo.get_by_action_id(tenant_id, action_id)

        return result if isinstance(result, RecoveryEvidence) else None





async def create_recovery_plan_from_intelligence(

    intelligence: RecoveryIntelligenceService,

    tenant_id: str,

    root_action_id: str,

    strategy: RecoveryStrategy = RecoveryStrategy.MAX_SAFETY,

    mode: PlanningMode = PlanningMode.STANDARD,

) -> tuple[

    RecoveryAlternative | None, PlanComparison, ValidationResult, list[SafetyGateResult]

]:

    alternatives = await intelligence.generate_alternatives(

        tenant_id, root_action_id, [strategy], mode

    )

    if not alternatives:

        return (

            None,

            PlanComparison(

                alternatives=[], ranked_by=PlanComparisonCriterion.SAFETY, ranking=[]

            ),

            ValidationResult(

                validity=PlanValidity.INVALID_BOUNDARY, errors=["No alternatives generated"]

            ),

            [],

        )



    comparison = intelligence.compare_alternatives(

        alternatives, PlanComparisonCriterion.SAFETY

    )

    selected = intelligence.select_best_plan(comparison)

    validation = (

        intelligence.validate_plan(selected)

        if selected

        else ValidationResult(

            validity=PlanValidity.INVALID_BOUNDARY, errors=["No valid plan"]

        )

    )

    gates = intelligence.evaluate_safety_gates(selected) if selected else []



    return selected, comparison, validation, gates
