"""Compact typed models for the recovery graph.

Provides node/edge/relation models, graph versions and diffs, and
consistency/cycle check result types used by the graph service and
independent verification infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class GraphNodeKind(StrEnum):
    """Classification of a recovery-graph node."""

    ACTION = "action"
    RESOURCE = "resource"
    MUTATION = "mutation"
    AGENT = "agent"
    TENANT = "tenant"
    POLICY = "policy"
    VERIFICATION = "verification"
    RECOVERY_PLAN = "recovery_plan"


class GraphRelation(StrEnum):
    """Directed relation types between graph nodes."""

    DEPENDS_ON = "depends_on"
    TRIGGERED_BY = "triggered_by"
    CAUSES = "causes"
    PRODUCED = "produced"
    AUTHORIZED_BY = "authorized_by"
    OBSERVED_AT = "observed_at"
    RECOVERED_BY = "recovered_by"
    VERIFIED_BY = "verified_by"
    CONTAINS = "contains"
    ALIASES = "aliases"
    CONFLICTS_WITH = "conflicts_with"
    SUPERSEDES = "supersedes"
    UNKNOWN = "unknown"


class ConsistencyLevel(StrEnum):
    """Overall consistency assessment of a graph."""

    CONSISTENT = "consistent"
    INCONSISTENT = "inconsistent"
    UNKNOWN = "unknown"


class CycleStatus(StrEnum):
    """Result of a cycle-detection pass."""

    NO_CYCLE = "no_cycle"
    CYCLE_DETECTED = "cycle_detected"
    CYCLE_POSSIBLE = "cycle_possible"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class GraphNode:
    """A node in the recovery graph."""

    node_id: str
    tenant_id: str
    kind: GraphNodeKind
    entity_id: str
    label: str = ""
    temporal_at: datetime | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """A directed edge in the recovery graph."""

    edge_id: str
    tenant_id: str
    source_node_id: str
    target_node_id: str
    relation: GraphRelation
    valid_at: datetime | None = None
    valid_until: datetime | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class GraphSnapshot:
    """An immutable versioned snapshot of a graph."""

    snapshot_id: str
    tenant_id: str
    graph_id: str
    version: int
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    captured_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class GraphDiff:
    """Computed difference between two graph versions."""

    diff_id: str
    tenant_id: str
    graph_id: str
    from_version: int
    to_version: int
    added_nodes: list[GraphNode] = field(default_factory=list)
    removed_nodes: list[GraphNode] = field(default_factory=list)
    added_edges: list[GraphEdge] = field(default_factory=list)
    removed_edges: list[GraphEdge] = field(default_factory=list)
    changed_nodes: list[GraphNode] = field(default_factory=list)
    changed_edges: list[GraphEdge] = field(default_factory=list)
    computed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ConsistencyReport:
    """Result of a graph consistency check."""

    report_id: str
    tenant_id: str
    graph_id: str
    level: ConsistencyLevel = ConsistencyLevel.UNKNOWN
    issues: list[str] = field(default_factory=list)
    dangling_edges: list[str] = field(default_factory=list)
    orphan_nodes: list[str] = field(default_factory=list)
    duplicate_edges: list[str] = field(default_factory=list)
    temporal_violations: list[str] = field(default_factory=list)
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class CycleReport:
    """Result of a graph cycle-detection pass."""

    report_id: str
    tenant_id: str
    graph_id: str
    status: CycleStatus = CycleStatus.INCONCLUSIVE
    cycles: list[list[str]] = field(default_factory=list)
    cycle_nodes: list[str] = field(default_factory=list)
    cycle_edges: list[str] = field(default_factory=list)
    details: str = ""
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class RecoveryGraph:
    """A tenant-scoped recovery graph for an incident."""

    graph_id: str
    tenant_id: str
    incident_id: str
    root_action_id: str
    version: int = 1
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


__all__ = [
    "ConsistencyLevel",
    "ConsistencyReport",
    "CycleReport",
    "CycleStatus",
    "GraphDiff",
    "GraphEdge",
    "GraphNode",
    "GraphNodeKind",
    "GraphRelation",
    "GraphSnapshot",
    "RecoveryGraph",
]