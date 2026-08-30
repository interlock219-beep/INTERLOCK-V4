"""Tests for ChangeSetReconstructionService."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from app.domain.entities.causal_state_types import (
    AIChangeSet,
    CausalRelationType,
    ChangeOrigin,
    DeltaType,
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
from app.domain.services.changeset_reconstruction_service import (
    ChangeSetReconstructionService,
)
from app.domain.services.state_delta_engine import StateDeltaEngine


def _make_action(
    action_id: str,
    tenant_id: str = "test-tenant",
    parent_action_id: str | None = None,
    reversibility: Reversibility = Reversibility.AUTOMATICALLY_REVERSIBLE,
    before_state_ref: str | None = "state:before:123",
    resource: str = "record:1",
) -> ProtectedAction:
    return ProtectedAction(
        action_id=action_id,
        tenant_id=tenant_id,
        actor_user_id=uuid4(),
        agent_id="agent-1",
        authority_grant_id=None,
        tool="database",
        resource=resource,
        action_type="insert",
        reversibility=reversibility,
        parent_action_id=parent_action_id,
        before_state_ref=before_state_ref,
        after_state_ref="state:after:456" if before_state_ref else None,
        status=ActionStatus.EXECUTED,
    )


def _make_evidence(
    action_id: str,
    tenant_id: str = "test-tenant",
    before_ref: str | None = "state:before:123",
    after_ref: str | None = "state:after:456",
    target_system: str = "database",
    target_resource: str = "record:1",
    reversibility: Reversibility = Reversibility.AUTOMATICALLY_REVERSIBLE,
    dependency_edges: list[str] | None = None,
) -> RecoveryEvidence:
    return RecoveryEvidence(
        evidence_id=f"ev-{action_id}",
        action_id=action_id,
        tenant_id=tenant_id,
        agent_id="agent-1",
        authority_grant_id=None,
        parent_action_id=None,
        root_action_id=action_id,
        correlation_id="corr-1",
        incident_id="inc-1",
        target_system=target_system,
        target_resource=target_resource,
        action_type="insert",
        before_state_reference=before_ref,
        after_state_reference=after_ref,
        compensation_payload={"op": "restore"},
        compensation_type=CompensationType.REVERSE_OPERATION,
        recovery_adapter_type=RecoveryAdapterType.DATABASE_RECORD,
        idempotency_key=f"idem-{action_id}",
        dependency_edges=dependency_edges or [],
        reversibility_classification=reversibility,
        evidence_hash=f"hash-{action_id}",
        adapter_capability=AdapterCapability.REFERENCE_IMPLEMENTATION,
    )


class MockActionRepo:
    def __init__(self, actions: list[ProtectedAction]) -> None:
        self._actions = {a.action_id: a for a in actions}

    async def get_by_action_id(
        self, tenant_id: str, action_id: str
    ) -> ProtectedAction | None:
        action = self._actions.get(action_id)
        if action and action.tenant_id == tenant_id:
            return action
        return None

    async def list_descendants(
        self, tenant_id: str, root_action_id: str, **kwargs: object
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
        return result, len(result)


class MockEvidenceRepo:
    def __init__(self, evidence_list: list[RecoveryEvidence]) -> None:
        self._evidence = {e.action_id: e for e in evidence_list}

    async def get_by_action_id(
        self, tenant_id: str, action_id: str
    ) -> RecoveryEvidence | None:
        ev = self._evidence.get(action_id)
        if ev and ev.tenant_id == tenant_id:
            return ev
        return None

    async def get_by_evidence_id(
        self, tenant_id: str, evidence_id: str
    ) -> RecoveryEvidence | None:
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


class MockChangeSetRepo:
    def __init__(self) -> None:
        self._items: dict[str, AIChangeSet] = {}

    async def get_by_changeset_id(
        self, tenant_id: str, changeset_id: str
    ) -> AIChangeSet | None:
        cs = self._items.get(changeset_id)
        if cs and cs.tenant_id == tenant_id:
            return cs
        return None

    async def get_by_incident(
        self, tenant_id: str, incident_id: str
    ) -> AIChangeSet | None:
        for cs in self._items.values():
            if cs.tenant_id == tenant_id and cs.incident_id == incident_id:
                return cs
        return None

    async def save(self, changeset: AIChangeSet) -> AIChangeSet:
        self._items[changeset.changeset_id] = changeset
        return changeset


class MockGraphRepo:
    def __init__(self) -> None:
        self._items: dict[str, Any] = {}

    async def get_by_graph_id(self, tenant_id: str, graph_id: str) -> Any | None:
        g = self._items.get(graph_id)
        if g and g.tenant_id == tenant_id:
            return g
        return None

    async def get_by_incident(self, tenant_id: str, incident_id: str) -> Any | None:
        for g in self._items.values():
            if g.tenant_id == tenant_id and g.incident_id == incident_id:
                return g
        return None

    async def save(self, graph: Any) -> Any:
        self._items[graph.graph_id] = graph
        return graph


class MockCheckpointRepo:
    def __init__(self, checkpoints: list[StateCheckpoint] | None = None) -> None:
        self._items: dict[str, StateCheckpoint] = {
            cp.checkpoint_id: cp for cp in (checkpoints or [])
        }

    async def get_by_checkpoint_id(
        self, tenant_id: str, checkpoint_id: str
    ) -> StateCheckpoint | None:
        cp = self._items.get(checkpoint_id)
        if cp and cp.tenant_id == tenant_id:
            return cp
        return None

    async def get_by_action_id(
        self, tenant_id: str, action_id: str
    ) -> StateCheckpoint | None:
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


class MockVersionRepo:
    def __init__(self, versions: list[ResourceVersion] | None = None) -> None:
        self._items: dict[str, ResourceVersion] = {
            v.version_id: v for v in (versions or [])
        }

    async def get_by_version_id(
        self, tenant_id: str, version_id: str
    ) -> ResourceVersion | None:
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

    async def get_latest_version(
        self, tenant_id: str, resource_id: str
    ) -> ResourceVersion | None:
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


class MockDeltaRepo:
    def __init__(self) -> None:
        self._items: dict[str, StateDelta] = {}

    async def get_by_delta_id(
        self, tenant_id: str, delta_id: str
    ) -> StateDelta | None:
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


class TestChangeSetReconstructionService:
    @pytest.mark.asyncio
    async def test_reconstruct_simple_incident(self) -> None:
        root = _make_action("root")
        evidence = [_make_evidence("root")]
        action_repo = MockActionRepo([root])
        evidence_repo = MockEvidenceRepo(evidence)
        changeset_repo = MockChangeSetRepo()
        graph_repo = MockGraphRepo()

        service = ChangeSetReconstructionService(
            action_repo, evidence_repo, changeset_repo, graph_repo
        )
        result = await service.reconstruct(
            "test-tenant", "inc-1", "agent-1", "root", "corr-1"
        )

        assert result.incident_id == "inc-1"
        assert result.agent_id == "agent-1"
        assert result.root_action_id == "root"
        assert "root" in result.causal_actions
        assert "record:1" in result.affected_resources
        assert result.recoverability["root"] == "recoverable"

    @pytest.mark.asyncio
    async def test_reconstruct_with_descendants(self) -> None:
        root = _make_action("root", resource="record:1")
        child1 = _make_action("child1", parent_action_id="root", resource="record:2")
        child2 = _make_action("child2", parent_action_id="child1", resource="record:3")
        evidence = [
            _make_evidence("root", target_resource="record:1"),
            _make_evidence("child1", target_resource="record:2"),
            _make_evidence("child2", target_resource="record:3"),
        ]
        action_repo = MockActionRepo([root, child1, child2])
        evidence_repo = MockEvidenceRepo(evidence)
        changeset_repo = MockChangeSetRepo()
        graph_repo = MockGraphRepo()

        service = ChangeSetReconstructionService(
            action_repo, evidence_repo, changeset_repo, graph_repo
        )
        result = await service.reconstruct(
            "test-tenant", "inc-1", "agent-1", "root"
        )

        assert len(result.causal_actions) == 3
        assert len(result.affected_resources) == 3
        assert "root" in result.direct_changes
        assert "child1" in result.direct_changes

    @pytest.mark.asyncio
    async def test_reconstruct_missing_root_action(self) -> None:
        action_repo = MockActionRepo([])
        evidence_repo = MockEvidenceRepo([])
        changeset_repo = MockChangeSetRepo()
        graph_repo = MockGraphRepo()

        service = ChangeSetReconstructionService(
            action_repo, evidence_repo, changeset_repo, graph_repo
        )
        result = await service.reconstruct(
            "test-tenant", "inc-1", "agent-1", "nonexistent"
        )

        assert result.root_action_id == "nonexistent"
        assert "not found" in result.root_cause.lower()
        assert len(result.unknown_areas) > 0

    @pytest.mark.asyncio
    async def test_reconstruct_identifies_unknown_areas(self) -> None:
        root = _make_action("root", before_state_ref=None)
        evidence = [_make_evidence("root", before_ref=None)]
        action_repo = MockActionRepo([root])
        evidence_repo = MockEvidenceRepo(evidence)
        changeset_repo = MockChangeSetRepo()
        graph_repo = MockGraphRepo()

        service = ChangeSetReconstructionService(
            action_repo, evidence_repo, changeset_repo, graph_repo
        )
        result = await service.reconstruct(
            "test-tenant", "inc-1", "agent-1", "root"
        )

        assert any("no_before_state" in u for u in result.unknown_areas)

    @pytest.mark.asyncio
    async def test_reconstruct_irreversible_action(self) -> None:
        root = _make_action("root", reversibility=Reversibility.IRREVERSIBLE)
        evidence = [_make_evidence("root", reversibility=Reversibility.IRREVERSIBLE)]
        action_repo = MockActionRepo([root])
        evidence_repo = MockEvidenceRepo(evidence)
        changeset_repo = MockChangeSetRepo()
        graph_repo = MockGraphRepo()

        service = ChangeSetReconstructionService(
            action_repo, evidence_repo, changeset_repo, graph_repo
        )
        result = await service.reconstruct(
            "test-tenant", "inc-1", "agent-1", "root"
        )

        assert result.recoverability["root"] == "irreversible"

    @pytest.mark.asyncio
    async def test_build_causal_state_graph(self) -> None:
        root = _make_action("root")
        child = _make_action("child", parent_action_id="root")
        evidence = [_make_evidence("root"), _make_evidence("child")]
        action_repo = MockActionRepo([root, child])
        evidence_repo = MockEvidenceRepo(evidence)
        changeset_repo = MockChangeSetRepo()
        graph_repo = MockGraphRepo()

        service = ChangeSetReconstructionService(
            action_repo, evidence_repo, changeset_repo, graph_repo
        )
        graph = await service.build_causal_state_graph("test-tenant", "inc-1", "root")

        assert graph.incident_id == "inc-1"
        assert graph.root_action_id == "root"
        assert len(graph.nodes) == 2
        assert len(graph.edges) >= 1
        assert any(e.relation_type == CausalRelationType.PARENT_CHILD for e in graph.edges)

    @pytest.mark.asyncio
    async def test_extract_recoverable_subgraph(self) -> None:
        root = _make_action("root", resource="record:1")
        child = _make_action("child", parent_action_id="root", resource="record:2")
        evidence = [_make_evidence("root"), _make_evidence("child")]
        action_repo = MockActionRepo([root, child])
        evidence_repo = MockEvidenceRepo(evidence)
        changeset_repo = MockChangeSetRepo()
        graph_repo = MockGraphRepo()

        service = ChangeSetReconstructionService(
            action_repo, evidence_repo, changeset_repo, graph_repo
        )
        full_graph = await service.build_causal_state_graph("test-tenant", "inc-1", "root")
        subgraph = await service.extract_recoverable_subgraph(
            "test-tenant", full_graph.graph_id, ["record:1"]
        )

        assert subgraph is not None
        assert subgraph.incident_id == "inc-1"
        assert len(subgraph.nodes) == 1
        assert subgraph.nodes[0].resource_id == "record:1"


class TestStateDeltaEngine:
    @pytest.mark.asyncio
    async def test_compute_field_level_delta(self) -> None:
        checkpoint_repo = MockCheckpointRepo()
        version_repo = MockVersionRepo()
        delta_repo = MockDeltaRepo()
        engine = StateDeltaEngine(checkpoint_repo, version_repo, delta_repo)

        before = {"role": "viewer", "department": "engineering"}
        after = {"role": "admin", "department": "engineering"}

        delta = await engine.compute_ai_delta(
            "test-tenant", "res-1", before, after, "action-1"
        )

        assert delta.delta_type == DeltaType.FIELD_LEVEL
        assert "role" in delta.changed_fields
        assert delta.before_values["role"] == "viewer"
        assert delta.after_values["role"] == "admin"
        assert delta.is_safe_delta is True

    @pytest.mark.asyncio
    async def test_compute_delta_with_added_fields(self) -> None:
        checkpoint_repo = MockCheckpointRepo()
        version_repo = MockVersionRepo()
        delta_repo = MockDeltaRepo()
        engine = StateDeltaEngine(checkpoint_repo, version_repo, delta_repo)

        before = {"role": "viewer"}
        after = {"role": "admin", "api_key": "key-123"}

        delta = await engine.compute_ai_delta(
            "test-tenant", "res-1", before, after
        )

        assert "api_key" in delta.added_fields
        assert delta.is_safe_delta is True

    @pytest.mark.asyncio
    async def test_compute_delta_with_removed_fields(self) -> None:
        checkpoint_repo = MockCheckpointRepo()
        version_repo = MockVersionRepo()
        delta_repo = MockDeltaRepo()
        engine = StateDeltaEngine(checkpoint_repo, version_repo, delta_repo)

        before = {"role": "viewer", "temp_field": "value"}
        after = {"role": "admin"}

        delta = await engine.compute_ai_delta(
            "test-tenant", "res-1", before, after
        )

        assert "temp_field" in delta.removed_fields
        assert delta.before_values["temp_field"] == "value"

    @pytest.mark.asyncio
    async def test_compute_delta_insufficient_state(self) -> None:
        checkpoint_repo = MockCheckpointRepo()
        version_repo = MockVersionRepo()
        delta_repo = MockDeltaRepo()
        engine = StateDeltaEngine(checkpoint_repo, version_repo, delta_repo)

        delta = await engine.compute_ai_delta(
            "test-tenant", "res-1", None, {"role": "admin"}
        )

        assert delta.delta_type == DeltaType.UNKNOWN
        assert delta.is_safe_delta is False

    @pytest.mark.asyncio
    async def test_determine_target_recovered_state_field_level(self) -> None:
        checkpoint_repo = MockCheckpointRepo()
        version_repo = MockVersionRepo()
        delta_repo = MockDeltaRepo()
        engine = StateDeltaEngine(checkpoint_repo, version_repo, delta_repo)

        delta = StateDelta(
            delta_id="delta-1",
            tenant_id="test-tenant",
            resource_id="res-1",
            delta_type=DeltaType.FIELD_LEVEL,
            changed_fields=["role"],
            before_values={"role": "viewer"},
            after_values={"role": "admin"},
            is_safe_delta=True,
        )

        current = {"role": "admin", "department": "security"}
        target = await engine.determine_target_recovered_state(
            "test-tenant", "res-1", current, delta
        )

        assert target["role"] == "viewer"
        assert target["department"] == "security"

    @pytest.mark.asyncio
    async def test_determine_target_unsafe_delta(self) -> None:
        checkpoint_repo = MockCheckpointRepo()
        version_repo = MockVersionRepo()
        delta_repo = MockDeltaRepo()
        engine = StateDeltaEngine(checkpoint_repo, version_repo, delta_repo)

        delta = StateDelta(
            delta_id="delta-1",
            tenant_id="test-tenant",
            resource_id="res-1",
            delta_type=DeltaType.UNKNOWN,
            is_safe_delta=False,
        )

        current = {"role": "admin"}
        target = await engine.determine_target_recovered_state(
            "test-tenant", "res-1", current, delta
        )

        assert target["_recovery_status"] == "MANUALLY_RECOVERABLE"

    @pytest.mark.asyncio
    async def test_record_resource_version(self) -> None:
        checkpoint_repo = MockCheckpointRepo()
        version_repo = MockVersionRepo()
        delta_repo = MockDeltaRepo()
        engine = StateDeltaEngine(checkpoint_repo, version_repo, delta_repo)

        v1 = await engine.record_resource_version(
            "test-tenant", "res-1", "database_record",
            {"role": "viewer"}, ChangeOrigin.HUMAN, "action-1", "user-1"
        )
        v2 = await engine.record_resource_version(
            "test-tenant", "res-1", "database_record",
            {"role": "admin"}, ChangeOrigin.AI_AGENT, "action-2", "agent-1"
        )

        assert v1.version_number == 1
        assert v2.version_number == 2
        assert v2.previous_version_id == v1.version_id
        assert v1.change_origin == ChangeOrigin.HUMAN
        assert v2.change_origin == ChangeOrigin.AI_AGENT

    @pytest.mark.asyncio
    async def test_create_and_verify_checkpoint(self) -> None:
        checkpoint_repo = MockCheckpointRepo()
        version_repo = MockVersionRepo()
        delta_repo = MockDeltaRepo()
        engine = StateDeltaEngine(checkpoint_repo, version_repo, delta_repo)

        checkpoint = await engine.create_checkpoint(
            "test-tenant", "action-1", "agent-1", "res-1", "database_record",
            {"role": "viewer"}, "full_state", "token-123", "etag-456"
        )

        assert checkpoint.checkpoint_id.startswith("cp-")
        assert checkpoint.state_hash is not None
        assert checkpoint.checkpoint_hash != ""

        integrity = await engine.verify_checkpoint_integrity(
            "test-tenant", checkpoint.checkpoint_id
        )
        assert integrity["valid"] is True

    @pytest.mark.asyncio
    async def test_checkpoint_tampering_detected(self) -> None:
        checkpoint_repo = MockCheckpointRepo()
        version_repo = MockVersionRepo()
        delta_repo = MockDeltaRepo()
        engine = StateDeltaEngine(checkpoint_repo, version_repo, delta_repo)

        checkpoint = await engine.create_checkpoint(
            "test-tenant", "action-1", "agent-1", "res-1", "database_record",
            {"role": "viewer"}
        )

        tampered = StateCheckpoint(
            checkpoint_id=checkpoint.checkpoint_id,
            tenant_id=checkpoint.tenant_id,
            action_id=checkpoint.action_id,
            agent_id=checkpoint.agent_id,
            resource_id=checkpoint.resource_id,
            resource_type=checkpoint.resource_type,
            strategy=checkpoint.strategy,
            state_hash="tampered_hash",
            recoverable_fields={"role": "admin"},
            checkpoint_hash=checkpoint.checkpoint_hash,
        )
        await checkpoint_repo.save(tampered)

        integrity = await engine.verify_checkpoint_integrity(
            "test-tenant", checkpoint.checkpoint_id
        )
        assert integrity["valid"] is False
        assert "tampering" in integrity["reason"] or "mismatch" in integrity["reason"]

    @pytest.mark.asyncio
    async def test_compute_unrelated_delta(self) -> None:
        checkpoint_repo = MockCheckpointRepo()
        version_repo = MockVersionRepo()
        delta_repo = MockDeltaRepo()
        engine = StateDeltaEngine(checkpoint_repo, version_repo, delta_repo)

        after_ai = {"role": "admin", "department": "engineering"}
        current = {"role": "admin", "department": "security"}

        delta = await engine.compute_unrelated_delta(
            "test-tenant", "res-1", after_ai, current
        )

        assert delta.delta_type == DeltaType.FIELD_LEVEL
        assert "department" in delta.changed_fields
        assert delta.before_values["department"] == "engineering"
        assert delta.after_values["department"] == "security"
