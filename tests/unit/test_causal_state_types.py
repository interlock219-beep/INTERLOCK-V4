"""Tests for Universal Causal State Recovery domain types and enums."""

from __future__ import annotations

import pytest

from app.domain.entities.causal_state_types import (
    AdapterCapabilityDeclaration,
    AIChangeSet,
    CausalRelationType,
    CausalStateEdge,
    CausalStateGraph,
    CausalStateNode,
    ChangeOrigin,
    CheckpointStrategy,
    ConfidenceLevel,
    ConflictMarker,
    DeltaType,
    DurableExecutionStep,
    MergeSafety,
    RecoveryConfidence,
    RecoveryReport,
    ResourceVersion,
    StateCheckpoint,
    StateDelta,
    VerificationStatus,
)


class TestCausalStateEnums:
    def test_checkpoint_strategy_values(self) -> None:
        assert CheckpointStrategy.FULL_STATE == "full_state"
        assert CheckpointStrategy.DELTA == "delta"
        assert CheckpointStrategy.VERSION_REFERENCE == "version_reference"
        assert CheckpointStrategy.ADAPTER_SNAPSHOT == "adapter_snapshot"

    def test_change_origin_values(self) -> None:
        assert ChangeOrigin.HUMAN == "human"
        assert ChangeOrigin.AI_AGENT == "ai_agent"
        assert ChangeOrigin.SYSTEM == "system"
        assert ChangeOrigin.UNKNOWN == "unknown"

    def test_delta_type_values(self) -> None:
        assert DeltaType.FIELD_LEVEL == "field_level"
        assert DeltaType.RECORD_LEVEL == "record_level"
        assert DeltaType.VERSION_RESTORE == "version_restore"
        assert DeltaType.COMPENSATING_OPERATION == "compensating_operation"
        assert DeltaType.SEMANTIC_COMPENSATION == "semantic_compensation"
        assert DeltaType.UNKNOWN == "unknown"

    def test_merge_safety_values(self) -> None:
        assert MergeSafety.MERGE_SAFE == "merge_safe"
        assert MergeSafety.MERGE_CONDITIONAL == "merge_conditional"
        assert MergeSafety.MERGE_UNSUPPORTED == "merge_unsupported"

    def test_confidence_level_values(self) -> None:
        assert ConfidenceLevel.HIGH_CONFIDENCE == "high_confidence"
        assert ConfidenceLevel.MEDIUM_CONFIDENCE == "medium_confidence"
        assert ConfidenceLevel.LOW_CONFIDENCE == "low_confidence"
        assert ConfidenceLevel.INSUFFICIENT_EVIDENCE == "insufficient_evidence"

    def test_verification_status_values(self) -> None:
        assert VerificationStatus.EXECUTED_AND_VERIFIED == "executed_and_verified"
        assert VerificationStatus.EXECUTED_NOT_VERIFIED == "executed_not_verified"
        assert VerificationStatus.EXECUTION_FAILED == "execution_failed"
        assert VerificationStatus.UNKNOWN_EXTERNAL_OUTCOME == "unknown_external_outcome"
        assert VerificationStatus.MANUAL_VERIFICATION_REQUIRED == "manual_verification_required"

    def test_causal_relation_type_values(self) -> None:
        assert CausalRelationType.PARENT_CHILD == "parent_child"
        assert CausalRelationType.DEPENDENCY == "dependency"
        assert CausalRelationType.DELEGATION == "delegation"
        assert CausalRelationType.TRIGGERED == "triggered"


class TestStateCheckpoint:
    def test_create_checkpoint(self) -> None:
        cp = StateCheckpoint(
            checkpoint_id="cp-1",
            tenant_id="t1",
            action_id="a1",
            agent_id="agent-1",
            resource_id="res-1",
            resource_type="database_record",
            strategy=CheckpointStrategy.FULL_STATE,
            state_hash="abc123",
            recoverable_fields={"role": "viewer"},
            checkpoint_hash="hash123",
        )
        assert cp.checkpoint_id == "cp-1"
        assert cp.tenant_id == "t1"
        assert cp.strategy == CheckpointStrategy.FULL_STATE
        assert cp.recoverable_fields == {"role": "viewer"}
        assert cp.checkpoint_hash == "hash123"

    def test_checkpoint_is_frozen(self) -> None:
        cp = StateCheckpoint(
            checkpoint_id="cp-1",
            tenant_id="t1",
            action_id="a1",
            agent_id="agent-1",
            resource_id="res-1",
            resource_type="database_record",
            strategy=CheckpointStrategy.FULL_STATE,
        )
        with pytest.raises(AttributeError):
            cp.checkpoint_id = "cp-2"  # type: ignore[misc]


class TestResourceVersion:
    def test_create_version(self) -> None:
        ver = ResourceVersion(
            version_id="ver-1",
            tenant_id="t1",
            resource_id="res-1",
            resource_type="database_record",
            version_number=2,
            change_origin=ChangeOrigin.AI_AGENT,
            causal_owner="agent-1",
            state_hash="hash456",
            previous_version_id="ver-0",
        )
        assert ver.version_number == 2
        assert ver.change_origin == ChangeOrigin.AI_AGENT
        assert ver.previous_version_id == "ver-0"

    def test_version_is_frozen(self) -> None:
        ver = ResourceVersion(
            version_id="ver-1",
            tenant_id="t1",
            resource_id="res-1",
            resource_type="database_record",
            version_number=1,
            change_origin=ChangeOrigin.HUMAN,
        )
        with pytest.raises(AttributeError):
            ver.version_number = 5  # type: ignore[misc]


class TestStateDelta:
    def test_create_field_level_delta(self) -> None:
        delta = StateDelta(
            delta_id="delta-1",
            tenant_id="t1",
            resource_id="res-1",
            delta_type=DeltaType.FIELD_LEVEL,
            changed_fields=["role"],
            before_values={"role": "viewer"},
            after_values={"role": "admin"},
            is_safe_delta=True,
        )
        assert delta.delta_type == DeltaType.FIELD_LEVEL
        assert delta.changed_fields == ["role"]
        assert delta.is_safe_delta is True

    def test_create_unknown_delta(self) -> None:
        delta = StateDelta(
            delta_id="delta-2",
            tenant_id="t1",
            resource_id="res-1",
            delta_type=DeltaType.UNKNOWN,
            is_safe_delta=False,
        )
        assert delta.is_safe_delta is False


class TestAIChangeSet:
    def test_create_changeset(self) -> None:
        cs = AIChangeSet(
            changeset_id="cs-1",
            tenant_id="t1",
            incident_id="inc-1",
            agent_id="agent-1",
            root_action_id="root-1",
            correlation_id="corr-1",
            root_cause="Agent performed harmful action",
            causal_actions=["root-1", "child-1"],
            affected_resources=["res-1", "res-2"],
            direct_changes=["root-1"],
            indirect_changes=["child-1"],
        )
        assert cs.changeset_id == "cs-1"
        assert len(cs.causal_actions) == 2
        assert len(cs.affected_resources) == 2
        assert cs.direct_changes == ["root-1"]

    def test_changeset_is_frozen(self) -> None:
        cs = AIChangeSet(
            changeset_id="cs-1",
            tenant_id="t1",
            incident_id="inc-1",
            agent_id="agent-1",
            root_action_id="root-1",
            correlation_id="corr-1",
        )
        with pytest.raises(AttributeError):
            cs.root_cause = "new cause"  # type: ignore[misc]


class TestRecoveryConfidence:
    def test_create_high_confidence(self) -> None:
        conf = RecoveryConfidence(
            confidence_id="conf-1",
            tenant_id="t1",
            plan_id="plan-1",
            level=ConfidenceLevel.HIGH_CONFIDENCE,
            before_state_available=True,
            after_state_available=True,
            current_state_available=True,
            adapter_support=True,
            version_match=True,
            dependency_completeness=True,
            verification_capability=True,
            evidence_completeness=0.95,
            factors=["all_factors_positive"],
        )
        assert conf.level == ConfidenceLevel.HIGH_CONFIDENCE
        assert conf.evidence_completeness == 0.95

    def test_create_insufficient_evidence(self) -> None:
        conf = RecoveryConfidence(
            confidence_id="conf-2",
            tenant_id="t1",
            plan_id="plan-1",
            level=ConfidenceLevel.INSUFFICIENT_EVIDENCE,
            evidence_completeness=0.1,
            factors=["no_before_state", "no_adapter_support"],
            recommendations=["Capture before-state references"],
        )
        assert conf.level == ConfidenceLevel.INSUFFICIENT_EVIDENCE
        assert len(conf.recommendations) == 1


class TestCausalStateGraph:
    def test_create_graph(self) -> None:
        node = CausalStateNode(
            node_id="node-1",
            node_type="action",
            entity_id="action-1",
            tenant_id="t1",
            agent_id="agent-1",
            resource_id="res-1",
        )
        edge = CausalStateEdge(
            edge_id="edge-1",
            source_node_id="node-1",
            target_node_id="node-2",
            relation_type=CausalRelationType.PARENT_CHILD,
            tenant_id="t1",
        )
        graph = CausalStateGraph(
            graph_id="graph-1",
            tenant_id="t1",
            incident_id="inc-1",
            root_action_id="root-1",
            nodes=[node],
            edges=[edge],
        )
        assert len(graph.nodes) == 1
        assert len(graph.edges) == 1
        assert graph.edges[0].relation_type == CausalRelationType.PARENT_CHILD


class TestDurableExecutionStep:
    def test_create_step(self) -> None:
        step = DurableExecutionStep(
            step_id="step-1",
            plan_id="plan-1",
            action_id="action-1",
            execution_order=0,
            tenant_id="t1",
            idempotency_key="idem-1",
            target_system="database",
            target_resource="res-1",
        )
        assert step.execution_state == "pending"
        assert step.retry_count == 0
        assert step.max_retries == 3

    def test_step_is_frozen(self) -> None:
        step = DurableExecutionStep(
            step_id="step-1",
            plan_id="plan-1",
            action_id="action-1",
            execution_order=0,
            tenant_id="t1",
        )
        with pytest.raises(AttributeError):
            step.execution_state = "succeeded"  # type: ignore[misc]


class TestAdapterCapabilityDeclaration:
    def test_create_declaration(self) -> None:
        decl = AdapterCapabilityDeclaration(
            adapter_name="mock",
            adapter_type="mock",
            can_capture_before_state=True,
            can_simulate=True,
            can_compensate=True,
            supports_idempotency=True,
            merge_safety=MergeSafety.MERGE_SAFE,
        )
        assert decl.can_capture_before_state is True
        assert decl.merge_safety == MergeSafety.MERGE_SAFE

    def test_default_declaration(self) -> None:
        decl = AdapterCapabilityDeclaration(
            adapter_name="test",
            adapter_type="test",
        )
        assert decl.can_capture_before_state is False
        assert decl.supports_idempotency is False
        assert decl.merge_safety == MergeSafety.MERGE_UNSUPPORTED


class TestRecoveryReport:
    def test_create_report(self) -> None:
        report = RecoveryReport(
            report_id="report-1",
            tenant_id="t1",
            plan_id="plan-1",
            incident_id="inc-1",
            ai_changes_recovered=["action-1"],
            ai_changes_failed=["action-2"],
            manual_recovery_required=["action-3"],
            verification_status=VerificationStatus.EXECUTED_AND_VERIFIED,
            confidence_level=ConfidenceLevel.HIGH_CONFIDENCE,
            summary="Recovery completed successfully",
            limitations=["action-3 requires manual recovery"],
        )
        assert len(report.ai_changes_recovered) == 1
        assert report.verification_status == VerificationStatus.EXECUTED_AND_VERIFIED
        assert len(report.limitations) == 1


class TestConflictMarker:
    def test_create_marker(self) -> None:
        marker = ConflictMarker(
            marker_id="marker-1",
            tenant_id="t1",
            resource_id="res-1",
            field_path="role",
            conflict_type="concurrent_mutation",
            ai_value="admin",
            external_value="security",
            current_value="admin",
        )
        assert marker.conflict_type == "concurrent_mutation"
        assert marker.resolution == "unresolved"
