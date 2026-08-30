from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities.causal_state_types import (
    AIChangeSet,
    CausalRelationType,
    CausalStateEdge,
    CausalStateGraph,
    CausalStateNode,
    ChangeOrigin,
    CheckpointStrategy,
    ConfidenceLevel,
    DeltaType,
    DurableExecutionStep,
    RecoveryConfidence,
    RecoveryReport,
    ResourceVersion,
    StateCheckpoint,
    StateDelta,
    VerificationStatus,
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
from app.infrastructure.persistence.models.causal_state_models import (
    AIChangeSetModel,
    CausalStateGraphModel,
    DurableExecutionStepModel,
    RecoveryConfidenceModel,
    RecoveryReportModel,
    ResourceVersionModel,
    StateCheckpointModel,
    StateDeltaModel,
)


def _serialize_json_field(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str, sort_keys=True)


def _deserialize_json(value: str | None) -> Any:
    if value is None or value == "":
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def _deserialize_json_list(value: str | None) -> list[Any]:
    result = _deserialize_json(value)
    if isinstance(result, list):
        return result
    return []


def _deserialize_json_dict(value: str | None) -> dict[str, Any]:
    result = _deserialize_json(value)
    if isinstance(result, dict):
        return result
    return {}


class SQLAlchemyStateCheckpointRepository(StateCheckpointRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def _to_entity(self, model: StateCheckpointModel) -> StateCheckpoint:
        return StateCheckpoint(
            checkpoint_id=model.checkpoint_id,
            tenant_id=model.tenant_id,
            action_id=model.action_id,
            agent_id=model.agent_id,
            resource_id=model.resource_id,
            resource_type=model.resource_type,
            strategy=CheckpointStrategy(model.strategy),
            created_at=model.created_at,
            resource_version=model.resource_version,
            state_hash=model.state_hash,
            recoverable_fields=_deserialize_json_dict(model.recoverable_fields),
            version_token=model.version_token,
            etag=model.etag,
            transaction_id=model.transaction_id,
            snapshot_reference=model.snapshot_reference,
            object_generation=model.object_generation,
            config_revision=model.config_revision,
            checkpoint_metadata=_deserialize_json_dict(model.checkpoint_metadata),
            checkpoint_hash=model.checkpoint_hash,
        )

    async def get_by_checkpoint_id(
        self, tenant_id: str, checkpoint_id: str
    ) -> StateCheckpoint | None:
        stmt = select(StateCheckpointModel).where(
            StateCheckpointModel.checkpoint_id == checkpoint_id,
            StateCheckpointModel.tenant_id == tenant_id,
        )
        result = self._session.execute(stmt).scalar_one_or_none()
        return self._to_entity(result) if result else None

    async def get_by_action_id(
        self, tenant_id: str, action_id: str
    ) -> StateCheckpoint | None:
        stmt = select(StateCheckpointModel).where(
            StateCheckpointModel.action_id == action_id,
            StateCheckpointModel.tenant_id == tenant_id,
        )
        result = self._session.execute(stmt).scalar_one_or_none()
        return self._to_entity(result) if result else None

    async def list_by_resource(
        self, tenant_id: str, resource_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[StateCheckpoint], int]:
        stmt = (
            select(StateCheckpointModel)
            .where(
                StateCheckpointModel.resource_id == resource_id,
                StateCheckpointModel.tenant_id == tenant_id,
            )
            .order_by(StateCheckpointModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        results = self._session.execute(stmt).scalars().all()
        return [self._to_entity(r) for r in results], len(results)

    async def save(self, checkpoint: StateCheckpoint) -> StateCheckpoint:
        model = StateCheckpointModel(
            checkpoint_id=checkpoint.checkpoint_id,
            tenant_id=checkpoint.tenant_id,
            action_id=checkpoint.action_id,
            agent_id=checkpoint.agent_id,
            resource_id=checkpoint.resource_id,
            resource_type=checkpoint.resource_type,
            strategy=checkpoint.strategy.value,
            resource_version=checkpoint.resource_version,
            state_hash=checkpoint.state_hash,
            recoverable_fields=_serialize_json_field(checkpoint.recoverable_fields),
            version_token=checkpoint.version_token,
            etag=checkpoint.etag,
            transaction_id=checkpoint.transaction_id,
            snapshot_reference=checkpoint.snapshot_reference,
            object_generation=checkpoint.object_generation,
            config_revision=checkpoint.config_revision,
            checkpoint_metadata=_serialize_json_field(checkpoint.checkpoint_metadata),
            checkpoint_hash=checkpoint.checkpoint_hash,
            created_at=checkpoint.created_at,
        )
        self._session.add(model)
        self._session.flush()
        return checkpoint


class SQLAlchemyResourceVersionRepository(ResourceVersionRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def _to_entity(self, model: ResourceVersionModel) -> ResourceVersion:
        return ResourceVersion(
            version_id=model.version_id,
            tenant_id=model.tenant_id,
            resource_id=model.resource_id,
            resource_type=model.resource_type,
            version_number=model.version_number,
            change_origin=ChangeOrigin(model.change_origin),
            causal_owner=model.causal_owner,
            created_at=model.created_at,
            state_hash=model.state_hash,
            external_version=model.external_version,
            version_token=model.version_token,
            action_id=model.action_id,
            agent_id=model.agent_id,
            previous_version_id=model.previous_version_id,
            version_metadata=_deserialize_json_dict(model.version_metadata),
        )

    async def get_by_version_id(
        self, tenant_id: str, version_id: str
    ) -> ResourceVersion | None:
        stmt = select(ResourceVersionModel).where(
            ResourceVersionModel.version_id == version_id,
            ResourceVersionModel.tenant_id == tenant_id,
        )
        result = self._session.execute(stmt).scalar_one_or_none()
        return self._to_entity(result) if result else None

    async def list_by_resource(
        self, tenant_id: str, resource_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[ResourceVersion], int]:
        stmt = (
            select(ResourceVersionModel)
            .where(
                ResourceVersionModel.resource_id == resource_id,
                ResourceVersionModel.tenant_id == tenant_id,
            )
            .order_by(ResourceVersionModel.version_number.asc())
            .limit(limit)
            .offset(offset)
        )
        results = self._session.execute(stmt).scalars().all()
        return [self._to_entity(r) for r in results], len(results)

    async def get_latest_version(
        self, tenant_id: str, resource_id: str
    ) -> ResourceVersion | None:
        stmt = (
            select(ResourceVersionModel)
            .where(
                ResourceVersionModel.resource_id == resource_id,
                ResourceVersionModel.tenant_id == tenant_id,
            )
            .order_by(ResourceVersionModel.version_number.desc())
            .limit(1)
        )
        result = self._session.execute(stmt).scalar_one_or_none()
        return self._to_entity(result) if result else None

    async def save(self, version: ResourceVersion) -> ResourceVersion:
        model = ResourceVersionModel(
            version_id=version.version_id,
            tenant_id=version.tenant_id,
            resource_id=version.resource_id,
            resource_type=version.resource_type,
            version_number=version.version_number,
            change_origin=version.change_origin.value,
            causal_owner=version.causal_owner,
            state_hash=version.state_hash,
            external_version=version.external_version,
            version_token=version.version_token,
            action_id=version.action_id,
            agent_id=version.agent_id,
            previous_version_id=version.previous_version_id,
            version_metadata=_serialize_json_field(version.version_metadata),
            created_at=version.created_at,
        )
        self._session.add(model)
        self._session.flush()
        return version


class SQLAlchemyStateDeltaRepository(StateDeltaRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def _to_entity(self, model: StateDeltaModel) -> StateDelta:
        return StateDelta(
            delta_id=model.delta_id,
            tenant_id=model.tenant_id,
            resource_id=model.resource_id,
            delta_type=DeltaType(model.delta_type),
            created_at=model.created_at,
            before_version_id=model.before_version_id,
            after_version_id=model.after_version_id,
            changed_fields=_deserialize_json_list(model.changed_fields),
            added_fields=_deserialize_json_list(model.added_fields),
            removed_fields=_deserialize_json_list(model.removed_fields),
            before_values=_deserialize_json_dict(model.before_values),
            after_values=_deserialize_json_dict(model.after_values),
            is_safe_delta=model.is_safe_delta,
            delta_metadata=_deserialize_json_dict(model.delta_metadata),
        )

    async def get_by_delta_id(
        self, tenant_id: str, delta_id: str
    ) -> StateDelta | None:
        stmt = select(StateDeltaModel).where(
            StateDeltaModel.delta_id == delta_id,
            StateDeltaModel.tenant_id == tenant_id,
        )
        result = self._session.execute(stmt).scalar_one_or_none()
        return self._to_entity(result) if result else None

    async def list_by_resource(
        self, tenant_id: str, resource_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[StateDelta], int]:
        stmt = (
            select(StateDeltaModel)
            .where(
                StateDeltaModel.resource_id == resource_id,
                StateDeltaModel.tenant_id == tenant_id,
            )
            .order_by(StateDeltaModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        results = self._session.execute(stmt).scalars().all()
        return [self._to_entity(r) for r in results], len(results)

    async def save(self, delta: StateDelta) -> StateDelta:
        model = StateDeltaModel(
            delta_id=delta.delta_id,
            tenant_id=delta.tenant_id,
            resource_id=delta.resource_id,
            delta_type=delta.delta_type.value,
            before_version_id=delta.before_version_id,
            after_version_id=delta.after_version_id,
            changed_fields=_serialize_json_field(delta.changed_fields),
            added_fields=_serialize_json_field(delta.added_fields),
            removed_fields=_serialize_json_field(delta.removed_fields),
            before_values=_serialize_json_field(delta.before_values),
            after_values=_serialize_json_field(delta.after_values),
            is_safe_delta=delta.is_safe_delta,
            delta_metadata=_serialize_json_field(delta.delta_metadata),
            created_at=delta.created_at,
        )
        self._session.add(model)
        self._session.flush()
        return delta


class SQLAlchemyChangeSetRepository(ChangeSetRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def _to_entity(self, model: AIChangeSetModel) -> AIChangeSet:
        return AIChangeSet(
            changeset_id=model.changeset_id,
            tenant_id=model.tenant_id,
            incident_id=model.incident_id,
            agent_id=model.agent_id,
            root_action_id=model.root_action_id,
            correlation_id=model.correlation_id,
            created_at=model.created_at,
            root_cause=model.root_cause,
            causal_actions=_deserialize_json_list(model.causal_actions),
            affected_resources=_deserialize_json_list(model.affected_resources),
            before_references=_deserialize_json_dict(model.before_references),
            after_references=_deserialize_json_dict(model.after_references),
            current_references=_deserialize_json_dict(model.current_references),
            dependency_graph=_deserialize_json_dict(model.dependency_graph),
            unrelated_mutations=_deserialize_json_list(model.unrelated_mutations),
            recoverability=_deserialize_json_dict(model.recoverability),
            unknown_areas=_deserialize_json_list(model.unknown_areas),
            direct_changes=_deserialize_json_list(model.direct_changes),
            indirect_changes=_deserialize_json_list(model.indirect_changes),
            dependent_changes=_deserialize_json_list(model.dependent_changes),
            external_effects=_deserialize_json_list(model.external_effects),
        )

    async def get_by_changeset_id(
        self, tenant_id: str, changeset_id: str
    ) -> AIChangeSet | None:
        stmt = select(AIChangeSetModel).where(
            AIChangeSetModel.changeset_id == changeset_id,
            AIChangeSetModel.tenant_id == tenant_id,
        )
        result = self._session.execute(stmt).scalar_one_or_none()
        return self._to_entity(result) if result else None

    async def get_by_incident(
        self, tenant_id: str, incident_id: str
    ) -> AIChangeSet | None:
        stmt = select(AIChangeSetModel).where(
            AIChangeSetModel.incident_id == incident_id,
            AIChangeSetModel.tenant_id == tenant_id,
        )
        result = self._session.execute(stmt).scalar_one_or_none()
        return self._to_entity(result) if result else None

    async def save(self, changeset: AIChangeSet) -> AIChangeSet:
        model = AIChangeSetModel(
            changeset_id=changeset.changeset_id,
            tenant_id=changeset.tenant_id,
            incident_id=changeset.incident_id,
            agent_id=changeset.agent_id,
            root_action_id=changeset.root_action_id,
            correlation_id=changeset.correlation_id,
            root_cause=changeset.root_cause,
            causal_actions=_serialize_json_field(changeset.causal_actions),
            affected_resources=_serialize_json_field(changeset.affected_resources),
            before_references=_serialize_json_field(changeset.before_references),
            after_references=_serialize_json_field(changeset.after_references),
            current_references=_serialize_json_field(changeset.current_references),
            dependency_graph=_serialize_json_field(changeset.dependency_graph),
            unrelated_mutations=_serialize_json_field(changeset.unrelated_mutations),
            recoverability=_serialize_json_field(changeset.recoverability),
            unknown_areas=_serialize_json_field(changeset.unknown_areas),
            direct_changes=_serialize_json_field(changeset.direct_changes),
            indirect_changes=_serialize_json_field(changeset.indirect_changes),
            dependent_changes=_serialize_json_field(changeset.dependent_changes),
            external_effects=_serialize_json_field(changeset.external_effects),
            created_at=changeset.created_at,
        )
        self._session.add(model)
        self._session.flush()
        return changeset


class SQLAlchemyCausalStateGraphRepository(CausalStateGraphRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def _to_entity(self, model: CausalStateGraphModel) -> CausalStateGraph:
        raw_nodes = _deserialize_json_list(model.nodes)
        raw_edges = _deserialize_json_list(model.edges)
        nodes = [
            CausalStateNode(
                node_id=n.get("node_id", ""),
                node_type=n.get("node_type", ""),
                entity_id=n.get("entity_id", ""),
                tenant_id=n.get("tenant_id", ""),
                state_before=n.get("state_before"),
                state_after=n.get("state_after"),
                version_before=n.get("version_before"),
                version_after=n.get("version_after"),
                agent_id=n.get("agent_id"),
                action_id=n.get("action_id"),
                resource_id=n.get("resource_id"),
                node_metadata=n.get("node_metadata", {}),
            )
            for n in raw_nodes
        ]
        edges = [
            CausalStateEdge(
                edge_id=e.get("edge_id", ""),
                source_node_id=e.get("source_node_id", ""),
                target_node_id=e.get("target_node_id", ""),
                relation_type=CausalRelationType(e.get("relation_type", "parent_child")),
                tenant_id=e.get("tenant_id", ""),
                edge_metadata=e.get("edge_metadata", {}),
            )
            for e in raw_edges
        ]
        return CausalStateGraph(
            graph_id=model.graph_id,
            tenant_id=model.tenant_id,
            incident_id=model.incident_id,
            root_action_id=model.root_action_id,
            created_at=model.created_at,
            nodes=nodes,
            edges=edges,
            subgraph_extractions=_deserialize_json_list(model.subgraph_extractions),
        )

    async def get_by_graph_id(
        self, tenant_id: str, graph_id: str
    ) -> CausalStateGraph | None:
        stmt = select(CausalStateGraphModel).where(
            CausalStateGraphModel.graph_id == graph_id,
            CausalStateGraphModel.tenant_id == tenant_id,
        )
        result = self._session.execute(stmt).scalar_one_or_none()
        return self._to_entity(result) if result else None

    async def get_by_incident(
        self, tenant_id: str, incident_id: str
    ) -> CausalStateGraph | None:
        stmt = select(CausalStateGraphModel).where(
            CausalStateGraphModel.incident_id == incident_id,
            CausalStateGraphModel.tenant_id == tenant_id,
        )
        result = self._session.execute(stmt).scalar_one_or_none()
        return self._to_entity(result) if result else None

    async def save(self, graph: CausalStateGraph) -> CausalStateGraph:
        nodes_data = [
            {
                "node_id": n.node_id,
                "node_type": n.node_type,
                "entity_id": n.entity_id,
                "tenant_id": n.tenant_id,
                "state_before": n.state_before,
                "state_after": n.state_after,
                "version_before": n.version_before,
                "version_after": n.version_after,
                "agent_id": n.agent_id,
                "action_id": n.action_id,
                "resource_id": n.resource_id,
                "node_metadata": n.node_metadata,
            }
            for n in graph.nodes
        ]
        edges_data = [
            {
                "edge_id": e.edge_id,
                "source_node_id": e.source_node_id,
                "target_node_id": e.target_node_id,
                "relation_type": e.relation_type.value,
                "tenant_id": e.tenant_id,
                "edge_metadata": e.edge_metadata,
            }
            for e in graph.edges
        ]
        model = CausalStateGraphModel(
            graph_id=graph.graph_id,
            tenant_id=graph.tenant_id,
            incident_id=graph.incident_id,
            root_action_id=graph.root_action_id,
            nodes=_serialize_json_field(nodes_data),
            edges=_serialize_json_field(edges_data),
            subgraph_extractions=_serialize_json_field(graph.subgraph_extractions),
            created_at=graph.created_at,
        )
        self._session.add(model)
        self._session.flush()
        return graph


class SQLAlchemyConfidenceRepository(ConfidenceRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def _to_entity(self, model: RecoveryConfidenceModel) -> RecoveryConfidence:
        return RecoveryConfidence(
            confidence_id=model.confidence_id,
            tenant_id=model.tenant_id,
            plan_id=model.plan_id,
            level=ConfidenceLevel(model.level),
            created_at=model.created_at,
            before_state_available=model.before_state_available,
            after_state_available=model.after_state_available,
            current_state_available=model.current_state_available,
            adapter_support=model.adapter_support,
            version_match=model.version_match,
            drift_detected=model.drift_detected,
            conflict_detected=model.conflict_detected,
            dependency_completeness=model.dependency_completeness,
            verification_capability=model.verification_capability,
            evidence_completeness=model.evidence_completeness,
            factors=_deserialize_json_list(model.factors),
            recommendations=_deserialize_json_list(model.recommendations),
        )

    async def get_by_confidence_id(
        self, tenant_id: str, confidence_id: str
    ) -> RecoveryConfidence | None:
        stmt = select(RecoveryConfidenceModel).where(
            RecoveryConfidenceModel.confidence_id == confidence_id,
            RecoveryConfidenceModel.tenant_id == tenant_id,
        )
        result = self._session.execute(stmt).scalar_one_or_none()
        return self._to_entity(result) if result else None

    async def get_by_plan(
        self, tenant_id: str, plan_id: str
    ) -> RecoveryConfidence | None:
        stmt = select(RecoveryConfidenceModel).where(
            RecoveryConfidenceModel.plan_id == plan_id,
            RecoveryConfidenceModel.tenant_id == tenant_id,
        )
        result = self._session.execute(stmt).scalar_one_or_none()
        return self._to_entity(result) if result else None

    async def save(self, confidence: RecoveryConfidence) -> RecoveryConfidence:
        model = RecoveryConfidenceModel(
            confidence_id=confidence.confidence_id,
            tenant_id=confidence.tenant_id,
            plan_id=confidence.plan_id,
            level=confidence.level.value,
            before_state_available=confidence.before_state_available,
            after_state_available=confidence.after_state_available,
            current_state_available=confidence.current_state_available,
            adapter_support=confidence.adapter_support,
            version_match=confidence.version_match,
            drift_detected=confidence.drift_detected,
            conflict_detected=confidence.conflict_detected,
            dependency_completeness=confidence.dependency_completeness,
            verification_capability=confidence.verification_capability,
            evidence_completeness=confidence.evidence_completeness,
            factors=_serialize_json_field(confidence.factors),
            recommendations=_serialize_json_field(confidence.recommendations),
            created_at=confidence.created_at,
        )
        self._session.add(model)
        self._session.flush()
        return confidence


class SQLAlchemyDurableExecutionRepository(DurableExecutionRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def _to_entity(self, model: DurableExecutionStepModel) -> DurableExecutionStep:
        return DurableExecutionStep(
            step_id=model.step_id,
            plan_id=model.plan_id,
            action_id=model.action_id,
            execution_order=model.execution_order,
            tenant_id=model.tenant_id,
            execution_state=model.execution_state,
            created_at=model.created_at,
            idempotency_key=model.idempotency_key,
            target_system=model.target_system,
            target_resource=model.target_resource,
            compensation_payload=_deserialize_json_dict(model.compensation_payload),
            started_at=model.started_at,
            completed_at=model.completed_at,
            error=model.error,
            verification_passed=model.verification_passed,
            retry_count=model.retry_count,
            max_retries=model.max_retries,
            step_metadata=_deserialize_json_dict(model.step_metadata),
        )

    async def get_by_step_id(
        self, tenant_id: str, step_id: str
    ) -> DurableExecutionStep | None:
        stmt = select(DurableExecutionStepModel).where(
            DurableExecutionStepModel.step_id == step_id,
            DurableExecutionStepModel.tenant_id == tenant_id,
        )
        result = self._session.execute(stmt).scalar_one_or_none()
        return self._to_entity(result) if result else None

    async def list_by_plan(
        self, tenant_id: str, plan_id: str, limit: int = 500, offset: int = 0
    ) -> tuple[list[DurableExecutionStep], int]:
        stmt = (
            select(DurableExecutionStepModel)
            .where(
                DurableExecutionStepModel.plan_id == plan_id,
                DurableExecutionStepModel.tenant_id == tenant_id,
            )
            .order_by(DurableExecutionStepModel.execution_order.asc())
            .limit(limit)
            .offset(offset)
        )
        results = self._session.execute(stmt).scalars().all()
        return [self._to_entity(r) for r in results], len(results)

    async def save(self, step: DurableExecutionStep) -> DurableExecutionStep:
        model = DurableExecutionStepModel(
            step_id=step.step_id,
            plan_id=step.plan_id,
            action_id=step.action_id,
            execution_order=step.execution_order,
            tenant_id=step.tenant_id,
            execution_state=step.execution_state,
            idempotency_key=step.idempotency_key,
            target_system=step.target_system,
            target_resource=step.target_resource,
            compensation_payload=_serialize_json_field(step.compensation_payload),
            started_at=step.started_at,
            completed_at=step.completed_at,
            error=step.error,
            verification_passed=step.verification_passed,
            retry_count=step.retry_count,
            max_retries=step.max_retries,
            step_metadata=_serialize_json_field(step.step_metadata),
            created_at=step.created_at,
        )
        self._session.add(model)
        self._session.flush()
        return step


class SQLAlchemyRecoveryReportRepository(RecoveryReportRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def _to_entity(self, model: RecoveryReportModel) -> RecoveryReport:
        return RecoveryReport(
            report_id=model.report_id,
            tenant_id=model.tenant_id,
            plan_id=model.plan_id,
            incident_id=model.incident_id,
            created_at=model.created_at,
            ai_changes_recovered=_deserialize_json_list(model.ai_changes_recovered),
            ai_changes_failed=_deserialize_json_list(model.ai_changes_failed),
            unrelated_changes_preserved=_deserialize_json_list(model.unrelated_changes_preserved),
            manual_recovery_required=_deserialize_json_list(model.manual_recovery_required),
            verification_status=VerificationStatus(model.verification_status),
            confidence_level=ConfidenceLevel(model.confidence_level),
            resource_results=_deserialize_json_dict(model.resource_results),
            summary=model.summary,
            limitations=_deserialize_json_list(model.limitations),
        )

    async def get_by_report_id(
        self, tenant_id: str, report_id: str
    ) -> RecoveryReport | None:
        stmt = select(RecoveryReportModel).where(
            RecoveryReportModel.report_id == report_id,
            RecoveryReportModel.tenant_id == tenant_id,
        )
        result = self._session.execute(stmt).scalar_one_or_none()
        return self._to_entity(result) if result else None

    async def get_by_plan(
        self, tenant_id: str, plan_id: str
    ) -> RecoveryReport | None:
        stmt = select(RecoveryReportModel).where(
            RecoveryReportModel.plan_id == plan_id,
            RecoveryReportModel.tenant_id == tenant_id,
        )
        result = self._session.execute(stmt).scalar_one_or_none()
        return self._to_entity(result) if result else None

    async def get_by_incident(
        self, tenant_id: str, incident_id: str
    ) -> RecoveryReport | None:
        stmt = select(RecoveryReportModel).where(
            RecoveryReportModel.incident_id == incident_id,
            RecoveryReportModel.tenant_id == tenant_id,
        )
        result = self._session.execute(stmt).scalar_one_or_none()
        return self._to_entity(result) if result else None

    async def save(self, report: RecoveryReport) -> RecoveryReport:
        model = RecoveryReportModel(
            report_id=report.report_id,
            tenant_id=report.tenant_id,
            plan_id=report.plan_id,
            incident_id=report.incident_id,
            ai_changes_recovered=_serialize_json_field(report.ai_changes_recovered),
            ai_changes_failed=_serialize_json_field(report.ai_changes_failed),
            unrelated_changes_preserved=_serialize_json_field(report.unrelated_changes_preserved),
            manual_recovery_required=_serialize_json_field(report.manual_recovery_required),
            verification_status=report.verification_status.value,
            confidence_level=report.confidence_level.value,
            resource_results=_serialize_json_field(report.resource_results),
            summary=report.summary,
            limitations=_serialize_json_field(report.limitations),
            created_at=report.created_at,
        )
        self._session.add(model)
        self._session.flush()
        return report
