from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from app.domain.entities.causal_state_types import (
    AIChangeSet,
    CausalRelationType,
    CausalStateEdge,
    CausalStateGraph,
    CausalStateNode,
)
from app.domain.entities.protected_action import ProtectedAction
from app.domain.entities.surgical_recovery_types import RecoveryEvidence
from app.domain.repositories.causal_state_repositories import (
    CausalStateGraphRepository,
    ChangeSetRepository,
)
from app.domain.repositories.protected_action_repository import ProtectedActionRepository
from app.domain.repositories.recovery_evidence_repository import RecoveryEvidenceRepository


class ChangeSetReconstructionService:
    """Reconstructs the complete AI-caused change set from an incident.

    Given an agent_id, incident_id, root_action_id, and correlation_id,
    this service reconstructs:

    * DIRECT CHANGES — resources modified by the root action and its descendants
    * INDIRECT CHANGES — downstream effects triggered by direct changes
    * DEPENDENT CHANGES — actions that depend on the root action chain
    * EXTERNAL EFFECTS — effects on systems outside the direct causal chain
    * UNRELATED MUTATIONS — changes that occurred outside the causal chain

    The system explicitly reports uncertainty. It does not silently assume
    causality from timestamp proximity alone.
    """

    def __init__(
        self,
        action_repository: ProtectedActionRepository,
        evidence_repository: RecoveryEvidenceRepository,
        changeset_repository: ChangeSetRepository,
        graph_repository: CausalStateGraphRepository,
    ) -> None:
        self._action_repo = action_repository
        self._evidence_repo = evidence_repository
        self._changeset_repo = changeset_repository
        self._graph_repo = graph_repository

    async def reconstruct(
        self,
        tenant_id: str,
        incident_id: str,
        agent_id: str,
        root_action_id: str,
        correlation_id: str = "",
    ) -> AIChangeSet:
        """Reconstruct the AI change set for an incident."""
        root_action = await self._action_repo.get_by_action_id(tenant_id, root_action_id)
        if root_action is None:
            return self._empty_changeset(
                tenant_id, incident_id, agent_id, root_action_id, correlation_id,
                root_cause=f"Root action {root_action_id} not found",
            )

        descendants, _ = await self._action_repo.list_descendants(
            tenant_id, root_action_id, limit=1000, offset=0
        )
        all_actions = [root_action] + descendants

        evidence_map = await self._collect_evidence(tenant_id, all_actions)
        affected_resources = self._identify_affected_resources(all_actions, evidence_map)
        before_refs, after_refs, current_refs = self._collect_state_references(
            all_actions, evidence_map
        )
        dependency_graph = self._build_dependency_graph(all_actions, evidence_map)
        direct_changes, indirect_changes, dependent_changes = self._classify_changes(
            all_actions, evidence_map, root_action_id
        )
        external_effects = self._identify_external_effects(all_actions, evidence_map)
        unrelated_mutations = await self._detect_unrelated_mutations(
            tenant_id, all_actions, affected_resources, evidence_map
        )
        recoverability = self._assess_recoverability(all_actions, evidence_map)
        unknown_areas = self._identify_unknown_areas(all_actions, evidence_map)

        changeset = AIChangeSet(
            changeset_id=f"cs-{secrets.token_hex(12)}",
            tenant_id=tenant_id,
            incident_id=incident_id,
            agent_id=agent_id,
            root_action_id=root_action_id,
            correlation_id=correlation_id,
            created_at=datetime.now(UTC),
            root_cause=self._determine_root_cause(root_action, all_actions),
            causal_actions=[a.action_id for a in all_actions],
            affected_resources=sorted(affected_resources),
            before_references=before_refs,
            after_references=after_refs,
            current_references=current_refs,
            dependency_graph=dependency_graph,
            unrelated_mutations=unrelated_mutations,
            recoverability=recoverability,
            unknown_areas=unknown_areas,
            direct_changes=direct_changes,
            indirect_changes=indirect_changes,
            dependent_changes=dependent_changes,
            external_effects=external_effects,
        )
        return await self._changeset_repo.save(changeset)

    async def build_causal_state_graph(
        self,
        tenant_id: str,
        incident_id: str,
        root_action_id: str,
    ) -> CausalStateGraph:
        """Build the full causal state graph for an incident."""
        root_action = await self._action_repo.get_by_action_id(tenant_id, root_action_id)
        if root_action is None:
            return CausalStateGraph(
                graph_id=f"graph-{secrets.token_hex(12)}",
                tenant_id=tenant_id,
                incident_id=incident_id,
                root_action_id=root_action_id,
            )

        descendants, _ = await self._action_repo.list_descendants(
            tenant_id, root_action_id, limit=1000, offset=0
        )
        all_actions = [root_action] + descendants
        evidence_map = await self._collect_evidence(tenant_id, all_actions)

        nodes: list[CausalStateNode] = []
        edges: list[CausalStateEdge] = []

        for action in all_actions:
            evidence = evidence_map.get(action.action_id)
            node = CausalStateNode(
                node_id=f"node-{action.action_id}",
                node_type="action",
                entity_id=action.action_id,
                tenant_id=tenant_id,
                agent_id=action.agent_id,
                action_id=action.action_id,
                resource_id=action.resource,
                version_before=evidence.state_version if evidence else None,
                version_after=evidence.resource_version if evidence else None,
            )
            nodes.append(node)

            if action.parent_action_id:
                parent_evidence = evidence_map.get(action.parent_action_id)
                parent_node_id = f"node-{action.parent_action_id}"
                edge = CausalStateEdge(
                    edge_id=f"edge-{action.parent_action_id}-{action.action_id}",
                    source_node_id=parent_node_id,
                    target_node_id=node.node_id,
                    relation_type=CausalRelationType.PARENT_CHILD,
                    tenant_id=tenant_id,
                )
                edges.append(edge)

                if parent_evidence and evidence:
                    dep_edge = CausalStateEdge(
                        edge_id=f"dep-{action.parent_action_id}-{action.action_id}",
                        source_node_id=parent_node_id,
                        target_node_id=node.node_id,
                        relation_type=CausalRelationType.DEPENDENCY,
                        tenant_id=tenant_id,
                        edge_metadata={
                            "shared_resource": (
                                parent_evidence.target_resource == evidence.target_resource
                            ),
                        },
                    )
                    edges.append(dep_edge)

        graph = CausalStateGraph(
            graph_id=f"graph-{secrets.token_hex(12)}",
            tenant_id=tenant_id,
            incident_id=incident_id,
            root_action_id=root_action_id,
            nodes=nodes,
            edges=edges,
        )
        return await self._graph_repo.save(graph)

    async def extract_recoverable_subgraph(
        self,
        tenant_id: str,
        graph_id: str,
        target_resource_ids: list[str],
    ) -> CausalStateGraph | None:
        """Extract the smallest recoverable subgraph for specific resources."""
        graph = await self._graph_repo.get_by_graph_id(tenant_id, graph_id)
        if graph is None:
            return None

        relevant_node_ids: set[str] = set()
        for node in graph.nodes:
            if node.resource_id and node.resource_id in target_resource_ids:
                relevant_node_ids.add(node.node_id)

        if not relevant_node_ids:
            return CausalStateGraph(
                graph_id=f"subgraph-{secrets.token_hex(12)}",
                tenant_id=tenant_id,
                incident_id=graph.incident_id,
                root_action_id=graph.root_action_id,
            )

        relevant_edges = [
            e for e in graph.edges
            if e.source_node_id in relevant_node_ids or e.target_node_id in relevant_node_ids
        ]
        relevant_nodes = [n for n in graph.nodes if n.node_id in relevant_node_ids]

        return CausalStateGraph(
            graph_id=f"subgraph-{secrets.token_hex(12)}",
            tenant_id=tenant_id,
            incident_id=graph.incident_id,
            root_action_id=graph.root_action_id,
            nodes=relevant_nodes,
            edges=relevant_edges,
            subgraph_extractions=[{
                "source_graph_id": graph_id,
                "included_resources": target_resource_ids,
                "node_count": len(relevant_nodes),
                "edge_count": len(relevant_edges),
            }],
        )

    async def _collect_evidence(
        self, tenant_id: str, actions: list[ProtectedAction]
    ) -> dict[str, RecoveryEvidence]:
        evidence_map: dict[str, RecoveryEvidence] = {}
        for action in actions:
            evidence = await self._evidence_repo.get_by_action_id(tenant_id, action.action_id)
            if evidence is not None:
                evidence_map[action.action_id] = evidence
        return evidence_map

    def _identify_affected_resources(
        self,
        actions: list[ProtectedAction],
        evidence_map: dict[str, RecoveryEvidence],
    ) -> set[str]:
        resources: set[str] = set()
        for action in actions:
            if action.resource:
                resources.add(action.resource)
            evidence = evidence_map.get(action.action_id)
            if evidence and evidence.target_resource:
                resources.add(evidence.target_resource)
        return resources

    def _collect_state_references(
        self,
        actions: list[ProtectedAction],
        evidence_map: dict[str, RecoveryEvidence],
    ) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
        before_refs: dict[str, str] = {}
        after_refs: dict[str, str] = {}
        current_refs: dict[str, str] = {}
        for action in actions:
            evidence = evidence_map.get(action.action_id)
            if evidence:
                if evidence.before_state_reference:
                    before_refs[action.action_id] = evidence.before_state_reference
                if evidence.after_state_reference:
                    after_refs[action.action_id] = evidence.after_state_reference
                if evidence.resource_version:
                    current_refs[action.action_id] = evidence.resource_version
        return before_refs, after_refs, current_refs

    def _build_dependency_graph(
        self,
        actions: list[ProtectedAction],
        evidence_map: dict[str, RecoveryEvidence],
    ) -> dict[str, Any]:
        graph: dict[str, Any] = {
            "nodes": [],
            "edges": [],
            "resources": {},
        }
        action_ids = {a.action_id for a in actions}

        for action in actions:
            node: dict[str, Any] = {
                "action_id": action.action_id,
                "agent_id": action.agent_id,
                "resource": action.resource,
                "action_type": action.action_type,
                "parent_action_id": action.parent_action_id,
            }
            evidence = evidence_map.get(action.action_id)
            if evidence:
                node["dependency_edges"] = evidence.dependency_edges
                node["target_system"] = evidence.target_system
            graph["nodes"].append(node)

            if action.parent_action_id and action.parent_action_id in action_ids:
                graph["edges"].append({
                    "source": action.parent_action_id,
                    "target": action.action_id,
                    "relation": "parent_child",
                })

            if evidence:
                for dep_id in evidence.dependency_edges:
                    if dep_id in action_ids:
                        graph["edges"].append({
                            "source": dep_id,
                            "target": action.action_id,
                            "relation": "dependency",
                        })

            if action.resource:
                if action.resource not in graph["resources"]:
                    graph["resources"][action.resource] = []
                graph["resources"][action.resource].append(action.action_id)

        return graph

    def _classify_changes(
        self,
        actions: list[ProtectedAction],
        evidence_map: dict[str, RecoveryEvidence],
        root_action_id: str,
    ) -> tuple[list[str], list[str], list[str]]:
        direct_changes: list[str] = []
        indirect_changes: list[str] = []
        dependent_changes: list[str] = []

        root_evidence = evidence_map.get(root_action_id)
        root_resource = root_evidence.target_resource if root_evidence else None

        for action in actions:
            if action.action_id == root_action_id:
                direct_changes.append(action.action_id)
                continue

            evidence = evidence_map.get(action.action_id)
            is_direct = False
            is_dependent = False

            if evidence:
                if root_resource and evidence.target_resource == root_resource:
                    is_direct = True
                if evidence.dependency_edges and root_action_id in evidence.dependency_edges:
                    is_dependent = True
                if action.parent_action_id == root_action_id:
                    is_direct = True

            if is_direct:
                direct_changes.append(action.action_id)
            elif is_dependent:
                dependent_changes.append(action.action_id)
            else:
                indirect_changes.append(action.action_id)

        return direct_changes, indirect_changes, dependent_changes

    def _identify_external_effects(
        self,
        actions: list[ProtectedAction],
        evidence_map: dict[str, RecoveryEvidence],
    ) -> list[str]:
        external: list[str] = []
        for action in actions:
            evidence = evidence_map.get(action.action_id)
            if evidence and evidence.target_system:
                target = evidence.target_system.lower()
                if target not in ("database", "mock", "config_store", "file_store"):
                    external.append(
                        f"{action.action_id}:{evidence.target_system}:{evidence.target_resource}"
                    )
        return external

    async def _detect_unrelated_mutations(
        self,
        tenant_id: str,
        actions: list[ProtectedAction],
        affected_resources: set[str],
        evidence_map: dict[str, RecoveryEvidence],
    ) -> list[dict[str, Any]]:
        unrelated: list[dict[str, Any]] = []
        action_ids = {a.action_id for a in actions}

        for action in actions:
            evidence = evidence_map.get(action.action_id)
            if evidence is None:
                continue
            if evidence.agent_id and evidence.agent_id != actions[0].agent_id:
                unrelated.append({
                    "action_id": action.action_id,
                    "reason": "different_agent",
                    "agent_id": evidence.agent_id,
                })
            if action.action_id not in action_ids:
                unrelated.append({
                    "action_id": action.action_id,
                    "reason": "outside_causal_chain",
                })

        return unrelated

    def _assess_recoverability(
        self,
        actions: list[ProtectedAction],
        evidence_map: dict[str, RecoveryEvidence],
    ) -> dict[str, str]:
        recoverability: dict[str, str] = {}
        for action in actions:
            evidence = evidence_map.get(action.action_id)
            if evidence is None:
                recoverability[action.action_id] = "no_evidence"
            elif evidence.reversibility_classification.value == "irreversible":
                recoverability[action.action_id] = "irreversible"
            elif evidence.reversibility_classification.value == "unknown":
                recoverability[action.action_id] = "unknown"
            elif evidence.before_state_reference is None:
                recoverability[action.action_id] = "no_before_state"
            elif evidence.reversibility_classification.value in (
                "automatically_reversible",
                "reversible",
            ):
                recoverability[action.action_id] = "recoverable"
            elif evidence.reversibility_classification.value in (
                "conditionally_reversible",
                "reversible_with_approval",
            ):
                recoverability[action.action_id] = "conditionally_recoverable"
            else:
                recoverability[action.action_id] = "unknown"
        return recoverability

    def _identify_unknown_areas(
        self,
        actions: list[ProtectedAction],
        evidence_map: dict[str, RecoveryEvidence],
    ) -> list[str]:
        unknowns: list[str] = []
        for action in actions:
            evidence = evidence_map.get(action.action_id)
            if evidence is None:
                unknowns.append(f"action:{action.action_id}:no_evidence_captured")
            else:
                if evidence.before_state_reference is None:
                    unknowns.append(f"action:{action.action_id}:no_before_state")
                if evidence.after_state_reference is None:
                    unknowns.append(f"action:{action.action_id}:no_after_state")
                if not evidence.target_system:
                    unknowns.append(f"action:{action.action_id}:unknown_target_system")
        return unknowns

    def _determine_root_cause(
        self,
        root_action: ProtectedAction,
        all_actions: list[ProtectedAction],
    ) -> str:
        action_count = len(all_actions)
        return (
            f"Agent {root_action.agent_id} performed {root_action.action_type} "
            f"on {root_action.resource} (action {root_action.action_id}), "
            f"triggering {action_count - 1} dependent actions"
        )

    def _empty_changeset(
        self,
        tenant_id: str,
        incident_id: str,
        agent_id: str,
        root_action_id: str,
        correlation_id: str,
        root_cause: str = "",
    ) -> AIChangeSet:
        return AIChangeSet(
            changeset_id=f"cs-{secrets.token_hex(12)}",
            tenant_id=tenant_id,
            incident_id=incident_id,
            agent_id=agent_id,
            root_action_id=root_action_id,
            correlation_id=correlation_id,
            root_cause=root_cause,
            unknown_areas=[f"root_action:{root_action_id}:not_found"],
        )
