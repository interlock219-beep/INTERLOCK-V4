from __future__ import annotations
import pytest
from unittest.mock import MagicMock, AsyncMock
from app.domain.entities.causal_state_types import ConfidenceLevel, VerificationStatus
from app.domain.entities.independent_verification_types import (
    VerificationOutcome, VerificationCheckType, IndependentVerifierRole,
    VerificationLayer, VerificationLayerResult, VerificationCheck,
    IndependentVerifier, IndependentVerificationResult, IndependentVerificationReport,
    ResidualRisk, VerificationConfidence, VerificationCoverage, EvidenceAssessment,
)
from app.domain.services.independent_verification_service import IndependentVerificationService
from app.domain.services.evidence_verification_service import EvidenceVerificationService

@pytest.fixture
def svc():
    return IndependentVerificationService()

@pytest.fixture
def verifier():
    return IndependentVerificationService().create_verifier('v1', IndependentVerifierRole.AUTOMATED_VERIFIER, 'tenant1', delegation_chain=['sys'])

class TestFeature69_IndependentVerificationService:
    def test_create_verifier(self, svc):
        v = svc.create_verifier('vid', IndependentVerifierRole.EXTERNAL_AUDITOR, 't1', credentials={'key': 'val'}, delegation_chain=['a', 'b'])
        assert v.verifier_id == 'vid'
        assert v.role == IndependentVerifierRole.EXTERNAL_AUDITOR
        assert v.tenant_id == 't1'
        assert v.credentials == {'key': 'val'}
        assert v.delegation_chain == ['a', 'b']

    def test_create_verifier_defaults(self, svc):
        v = svc.create_verifier('vid', IndependentVerifierRole.HUMAN_REVIEWER, 't1')
        assert v.credentials == {}
        assert v.delegation_chain == []

    def test_create_verification_check(self, svc):
        chk = svc.create_verification_check('c1', VerificationCheckType.INTEGRITY, 'desc', 'exp', 'act', True, evidence_references=['e1'], details={'k': 'v'})
        assert chk.check_id == 'c1'
        assert chk.passed is True
        assert chk.evidence_references == ['e1']

    def test_build_verification_result_true(self, svc):
        chk = svc.create_verification_check('c1', VerificationCheckType.INTEGRITY, 'd', 'e', 'a', True)
        assert svc.build_verification_result(chk) is True

    def test_build_verification_result_false(self, svc):
        chk = svc.create_verification_check('c1', VerificationCheckType.INTEGRITY, 'd', 'e', 'a', False)
        assert svc.build_verification_result(chk) is False

    async def test_verify_evidence_ok(self, svc):
        ev = MagicMock()
        ev.evidence_id = 'e1'
        ev.action_id = 'a1'
        ev.tenant_id = 't1'
        ev.target_resource = 'r1'
        ev.reversibility_classification = MagicMock(value='reversible')
        ev.before_state_reference = 'b1'
        ev.after_state_reference = 'a2'
        ev.state_hash = 'sha256:abc'
        # Real evidence always carries a metadata dict (dataclass default {},
        # repository round-trip guaranteed); without it the v2 verifier
        # correctly fails closed, which this test-double would otherwise trip.
        ev.recovery_metadata = {}
        result = await svc.verify_evidence(ev)
        assert result.is_tampered is False
        assert result.is_missing is False
        assert result.outcome in (VerificationOutcome.VERIFIED, VerificationOutcome.UNKNOWN)

    async def test_verify_evidence_missing_fields(self, svc):
        ev = MagicMock()
        ev.evidence_id = ''
        ev.action_id = ''
        ev.tenant_id = 't1'
        ev.target_resource = 'r1'
        ev.reversibility_classification = MagicMock(value='reversible')
        ev.before_state_reference = None
        ev.after_state_reference = None
        ev.state_hash = None
        result = await svc.verify_evidence(ev)
        assert result.is_missing is True

    async def test_independent_verify_all_verified(self, svc, verifier):
        report = MagicMock()
        report.resource_results = {'act1': {'status': VerificationStatus.EXECUTED_AND_VERIFIED.value, 'verification': {}}}
        result = await svc.independent_verify('t1', 'p1', 'i1', verifier, report)
        assert result.outcome == VerificationOutcome.VERIFIED
        assert result.execution_verified is True
        assert result.plan_id == 'p1'
        assert result.tenant_id == 't1'
        assert result.checks

    async def test_independent_verify_unverified(self, svc, verifier):
        report = MagicMock()
        report.resource_results = {'act1': {'status': VerificationStatus.EXECUTED_NOT_VERIFIED.value, 'verification': {}}}
        result = await svc.independent_verify('t1', 'p1', 'i1', verifier, report)
        assert result.outcome == VerificationOutcome.UNVERIFIED
        assert result.execution_verified is False

    def test_build_verification_report_all_verified(self, svc, verifier):
        r1 = IndependentVerificationResult(verification_id='v1', plan_id='p1', tenant_id='t1', verifier=verifier, action_id='a1', outcome=VerificationOutcome.VERIFIED, checks=[], execution_verified=True)
        r2 = IndependentVerificationResult(verification_id='v2', plan_id='p1', tenant_id='t1', verifier=verifier, action_id='a2', outcome=VerificationOutcome.VERIFIED, checks=[], execution_verified=True)
        report = svc.build_verification_report('t1', 'p1', 'i1', verifier, [r1, r2])
        assert report.overall_outcome == VerificationOutcome.VERIFIED
        assert report.all_verified is True

    def test_build_verification_report_with_failure(self, svc, verifier):
        r1 = IndependentVerificationResult(verification_id='v1', plan_id='p1', tenant_id='t1', verifier=verifier, action_id='a1', outcome=VerificationOutcome.VERIFIED, checks=[], execution_verified=True)
        r2 = IndependentVerificationResult(verification_id='v2', plan_id='p1', tenant_id='t1', verifier=verifier, action_id='a2', outcome=VerificationOutcome.VERIFICATION_FAILED, checks=[], execution_verified=False)
        report = svc.build_verification_report('t1', 'p1', 'i1', verifier, [r1, r2])
        assert report.overall_outcome == VerificationOutcome.VERIFICATION_FAILED
        assert report.any_failed is True

    def test_compute_verification_hash(self, svc):
        h1 = svc.compute_verification_hash({'a': 1, 'b': 2})
        h2 = svc.compute_verification_hash({'b': 2, 'a': 1})
        assert h1 == h2
        assert len(h1) == 64

class TestFeature70_MultiLayerVerification:
    def test_run_multi_layer_returns_14_layers(self, svc):
        before = {'x': 1}
        after = {'x': 2}
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1', before_state=before, after_state=after)
        assert len(results) == 14
        layers = {r.layer for r in results}
        assert len(layers) == 14

    def test_all_layers_present(self, svc):
        before = {'x': 1}
        after = {'x': 2}
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1', before_state=before, after_state=after)
        expected = {l.value for l in VerificationLayer}
        actual = {r.layer.value for r in results}
        assert actual == expected

    def test_layer_result_structure(self, svc):
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1', before_state={'x': 1}, after_state={'x': 2})
        r = results[0]
        assert isinstance(r.layer, VerificationLayer)
        assert isinstance(r.passed, bool)
        assert isinstance(r.status, VerificationOutcome)
        assert isinstance(r.details, dict)

    def test_exact_state_passes_when_matching(self, svc):
        target = {'key': 'value', 'num': 42}
        after = {'key': 'value', 'num': 42}
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1', before_state={'key': 'old'}, after_state=after, context={'expected_state': target})
        exact = [r for r in results if r.layer == VerificationLayer.EXACT_STATE][0]
        assert exact.passed is True
        assert exact.status == VerificationOutcome.VERIFIED

    def test_exact_state_fails_when_mismatched(self, svc):
        target = {'key': 'value'}
        after = {'key': 'different'}
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1', after_state=after, context={'expected_state': target})
        exact = [r for r in results if r.layer == VerificationLayer.EXACT_STATE][0]
        assert exact.passed is False

    def test_structural_missing_fields(self, svc):
        after = {'a': 1}
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1', after_state=after, context={'required_fields': ['a', 'b']})
        struct = [r for r in results if r.layer == VerificationLayer.STRUCTURAL][0]
        assert struct.passed is False
        assert 'b' in struct.details.get('missing_fields', [])

    def test_structural_passes_with_all_fields(self, svc):
        after = {'a': 1, 'b': 'x'}
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1', after_state=after, context={'required_fields': ['a', 'b']})
        struct = [r for r in results if r.layer == VerificationLayer.STRUCTURAL][0]
        assert struct.passed is True

    def test_dependency_unsatisfied(self, svc):
        after = {'x': 1}
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1', after_state=after, context={'dependency_edges': [{'action_id': 'dep1', 'status': 'pending'}]})
        dep = [r for r in results if r.layer == VerificationLayer.DEPENDENCY][0]
        assert dep.passed is False

    def test_dependency_satisfied(self, svc):
        after = {'x': 1}
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1', after_state=after, context={'dependency_edges': [{'action_id': 'dep1', 'status': 'satisfied'}]})
        dep = [r for r in results if r.layer == VerificationLayer.DEPENDENCY][0]
        assert dep.passed is True

    def test_permissions_missing(self, svc):
        after = {'x': 1}
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1', after_state=after, context={'required_permissions': ['read', 'write'], 'granted_permissions': ['read']})
        perm = [r for r in results if r.layer == VerificationLayer.PERMISSIONS][0]
        assert perm.passed is False

    def test_permissions_all_granted(self, svc):
        after = {'x': 1}
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1', after_state=after, context={'required_permissions': ['read'], 'granted_permissions': ['read', 'write']})
        perm = [r for r in results if r.layer == VerificationLayer.PERMISSIONS][0]
        assert perm.passed is True

    def test_identity_no_actor(self, svc):
        after = {'x': 1}
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1', after_state=after, context={})
        ident = [r for r in results if r.layer == VerificationLayer.IDENTITY][0]
        assert ident.passed is False

    def test_db_constraints_violated(self, svc):
        after = {'x': 1}
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1', after_state=after, context={'db_constraint_results': {'uk_col': True, 'fk_ref': False}})
        db = [r for r in results if r.layer == VerificationLayer.DB_CONSTRAINTS][0]
        assert db.passed is False

    def test_business_invariant_violation(self, svc):
        after = {'total': -100}
        def positive_total(state): return state.get('total', 0) >= 0
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1', after_state=after, context={'business_rules': [positive_total]})
        biz = [r for r in results if r.layer == VerificationLayer.BUSINESS_INVARIANTS][0]
        assert biz.passed is False

    def test_business_invariant_passes(self, svc):
        after = {'total': 100}
        def positive_total(state): return state.get('total', 0) >= 0
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1', after_state=after, context={'business_rules': [positive_total]})
        biz = [r for r in results if r.layer == VerificationLayer.BUSINESS_INVARIANTS][0]
        assert biz.passed is True

    def test_cross_system_consistent(self, svc):
        after = {'x': 1}
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1', after_state=after, context={'cross_system_states': {'sys1': {'x': 1}, 'sys2': {'x': 1}}})
        cs = [r for r in results if r.layer == VerificationLayer.CROSS_SYSTEM][0]
        assert cs.passed is True

    def test_cross_system_inconsistent(self, svc):
        after = {'x': 1}
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1', after_state=after, context={'cross_system_states': {'sys1': {'x': 1}, 'sys2': {'x': 2}}})
        cs = [r for r in results if r.layer == VerificationLayer.CROSS_SYSTEM][0]
        assert cs.passed is False

    def test_recovery_completeness_complete(self, svc):
        after = {'x': 1}
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1', after_state=after, context={'recovery_steps': [{'action_id': 'a1', 'status': 'complete'}, {'action_id': 'a2', 'status': 'complete'}]})
        rc = [r for r in results if r.layer == VerificationLayer.RECOVERY_COMPLETENESS][0]
        assert rc.passed is True

    def test_recovery_completeness_incomplete(self, svc):
        after = {'x': 1}
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1', after_state=after, context={'recovery_steps': [{'action_id': 'a1', 'status': 'complete'}, {'action_id': 'a2', 'status': 'pending'}]})
        rc = [r for r in results if r.layer == VerificationLayer.RECOVERY_COMPLETENESS][0]
        assert rc.passed is False

    def test_human_change_preserved(self, svc):
        after = {'x': 1, 'name': 'Alice'}
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1', before_state={'x': 0, 'name': 'Alice'}, after_state=after, context={'human_managed_fields': ['name']})
        hc = [r for r in results if r.layer == VerificationLayer.HUMAN_CHANGE_PRESERVATION][0]
        assert hc.passed is True

    def test_human_change_altered(self, svc):
        after = {'x': 1, 'name': 'Bob'}
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1', before_state={'x': 0, 'name': 'Alice'}, after_state=after, context={'human_managed_fields': ['name']})
        hc = [r for r in results if r.layer == VerificationLayer.HUMAN_CHANGE_PRESERVATION][0]
        assert hc.passed is False

    def test_byte_content_immutable_preserved(self, svc):
        after = {'id': 1, 'name': 'Alice'}
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1', before_state={'id': 1, 'name': 'Alice'}, after_state=after, context={'immutable_fields': ['id']})
        bc = [r for r in results if r.layer == VerificationLayer.BYTE_CONTENT][0]
        assert bc.passed is True

    def test_semantic_invariant_violation(self, svc):
        after = {'count': -5}
        def non_negative(state): return state.get('count', 0) >= 0
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1', after_state=after, context={'semantic_invariants': [non_negative]})
        sem = [r for r in results if r.layer == VerificationLayer.SEMANTIC][0]
        assert sem.passed is False

    def test_layer_result_is_definitive(self, svc):
        lr = VerificationLayerResult(layer=VerificationLayer.INTEGRITY, passed=False, status=VerificationOutcome.VERIFICATION_FAILED, details={})
        assert lr.is_definitive is True

    def test_layer_result_is_inconclusive(self, svc):
        lr = VerificationLayerResult(layer=VerificationLayer.INTEGRITY, passed=True, status=VerificationOutcome.INCONCLUSIVE, details={})
        assert lr.is_inconclusive is True

    def test_run_multi_layer_no_context(self, svc):
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1')
        assert len(results) == 14
        assert all(isinstance(r, VerificationLayerResult) for r in results)

class TestIntegrityLayerFailClosed:
    """WP-5 (V6): no evidence must never be reported as VERIFIED integrity.

    Before the fix, the integrity layer hashed the *current* after_state and
    returned (True, VERIFIED) whenever evidence was absent — a fail-open
    claim that nothing had actually been verified.
    """

    def test_integrity_no_evidence_is_inconclusive_not_verified(self, svc):
        results = svc.run_multi_layer_verification(
            't1', 'p1', 'a1', before_state={'x': 1}, after_state={'x': 2}
        )
        integrity = [r for r in results if r.layer == VerificationLayer.INTEGRITY][0]
        assert integrity.status != VerificationOutcome.VERIFIED, (
            'fail-open regression: integrity claimed VERIFIED with no evidence'
        )
        assert integrity.passed is False
        assert integrity.status == VerificationOutcome.INCONCLUSIVE
        # The state hash is still surfaced for forensic reference.
        assert integrity.details.get('state_hash'), 'state_hash must be kept'

    def test_integrity_no_evidence_and_no_state_is_inconclusive(self, svc):
        results = svc.run_multi_layer_verification('t1', 'p1', 'a1')
        integrity = [r for r in results if r.layer == VerificationLayer.INTEGRITY][0]
        assert integrity.passed is False
        assert integrity.status == VerificationOutcome.INCONCLUSIVE

class TestFeature71_VerificationCoverage:
    def test_coverage_all_passing(self, svc):
        results = [
            VerificationLayerResult(layer=VerificationLayer.EXACT_STATE, passed=True, status=VerificationOutcome.VERIFIED, details={}),
            VerificationLayerResult(layer=VerificationLayer.INTEGRITY, passed=True, status=VerificationOutcome.VERIFIED, details={}),
        ]
        cov = svc.measure_verification_coverage(results)
        assert cov.coverage_rate == 1.0
        assert cov.passed_checks == 2
        assert cov.total_checks == 2

    def test_coverage_with_failures(self, svc):
        results = [
            VerificationLayerResult(layer=VerificationLayer.EXACT_STATE, passed=True, status=VerificationOutcome.VERIFIED, details={}),
            VerificationLayerResult(layer=VerificationLayer.INTEGRITY, passed=False, status=VerificationOutcome.VERIFICATION_FAILED, details={}),
            VerificationLayerResult(layer=VerificationLayer.DEPENDENCY, passed=True, status=VerificationOutcome.VERIFIED, details={}),
        ]
        cov = svc.measure_verification_coverage(results)
        assert cov.coverage_rate == pytest.approx(2/3)
        assert cov.failed_checks == 1
        assert cov.total_checks == 3

    def test_coverage_missing_layers(self, svc):
        results = [
            VerificationLayerResult(layer=VerificationLayer.EXACT_STATE, passed=True, status=VerificationOutcome.VERIFIED, details={}),
        ]
        cov = svc.measure_verification_coverage(results)
        assert cov.all_layers_measured is False
        assert len(cov.layers_missing) > 0
        assert cov.layers_missing is not None

    def test_coverage_all_layers_measured(self, svc):
        results = [VerificationLayerResult(layer=l, passed=True, status=VerificationOutcome.VERIFIED, details={}) for l in VerificationLayer]
        cov = svc.measure_verification_coverage(results)
        assert cov.all_layers_measured is True
        assert cov.layers_missing == []

    def test_action_coverage(self, svc):
        results = [VerificationLayerResult(layer=l, passed=True, status=VerificationOutcome.VERIFIED, details={}) for l in VerificationLayer]
        cov = svc.measure_verification_coverage(results, action_ids=['a1', 'a2'], action_layer_results={'a1': results, 'a2': results})
        assert cov.action_coverage['a1'] == 1.0
        assert cov.action_coverage['a2'] == 1.0

    def test_layer_coverage(self, svc):
        results = [VerificationLayerResult(layer=l, passed=True, status=VerificationOutcome.VERIFIED, details={}) for l in VerificationLayer]
        cov = svc.measure_verification_coverage(results)
        for layer in VerificationLayer:
            assert cov.layer_coverage[layer.value] == 1.0

    def test_coverage_zero_checks(self, svc):
        cov = svc.measure_verification_coverage([])
        assert cov.total_checks == 0
        assert cov.coverage_rate == 0.0

    def test_fully_covered(self, svc):
        results = [VerificationLayerResult(layer=l, passed=True, status=VerificationOutcome.VERIFIED, details={}) for l in VerificationLayer]
        cov = svc.measure_verification_coverage(results)
        assert cov.fully_covered is True

    def test_not_fully_covered(self, svc):
        results = [
            VerificationLayerResult(layer=l, passed=True, status=VerificationOutcome.VERIFIED, details={})
            for l in VerificationLayer
        ]
        results.append(VerificationLayerResult(layer=VerificationLayer.INTEGRITY, passed=False, status=VerificationOutcome.VERIFICATION_FAILED, details={}))
        cov = svc.measure_verification_coverage(results)
        assert cov.fully_covered is False

class TestFeature72_ResidualRiskAndConfidence:

    def test_residual_risk_low(self, svc):
        cov = svc.measure_verification_coverage([VerificationLayerResult(layer=l, passed=True, status=VerificationOutcome.VERIFIED, details={}) for l in VerificationLayer])
        risk = svc.calculate_residual_risk(cov)
        assert risk.risk_level == 'low'
        assert risk.risk_score < 0.3

    def test_residual_risk_with_blocking(self, svc):
        cov = svc.measure_verification_coverage([VerificationLayerResult(layer=VerificationLayer.EXACT_STATE, passed=True, status=VerificationOutcome.VERIFIED, details={})])
        vr = IndependentVerificationResult(verification_id='v1', plan_id='p1', tenant_id='t1', verifier=MagicMock(), action_id='a1', outcome=VerificationOutcome.VERIFICATION_FAILED, checks=[], execution_verified=False)
        risk = svc.calculate_residual_risk(cov, verification_result=vr)
        assert risk.blocks_recovery_claim is True
        assert len(risk.blocking_factors) > 0

    def test_residual_risk_missing_layers(self, svc):
        cov = svc.measure_verification_coverage([
            VerificationLayerResult(layer=VerificationLayer.EXACT_STATE, passed=True, status=VerificationOutcome.VERIFIED, details={}),
])
        risk = svc.calculate_residual_risk(cov)
        assert risk.risk_level in ('medium', 'high', 'critical')
        assert len(risk.blocking_factors) > 0

    def test_residual_risk_acceptable(self, svc):
        cov = svc.measure_verification_coverage([VerificationLayerResult(layer=l, passed=True, status=VerificationOutcome.VERIFIED, details={}) for l in VerificationLayer])
        risk = svc.calculate_residual_risk(cov)
        assert risk.acceptable is True

    def test_residual_risk_not_acceptable(self, svc):
        cov = svc.measure_verification_coverage([VerificationLayerResult(layer=VerificationLayer.EXACT_STATE, passed=True, status=VerificationOutcome.VERIFIED, details={})])
        vr = IndependentVerificationResult(verification_id='v1', plan_id='p1', tenant_id='t1', verifier=MagicMock(), action_id='a1', outcome=VerificationOutcome.VERIFICATION_FAILED, checks=[], execution_verified=False)
        risk = svc.calculate_residual_risk(cov, verification_result=vr)
        assert risk.acceptable is False

    def test_confidence_high(self, svc):
        results = [VerificationLayerResult(layer=l, passed=True, status=VerificationOutcome.VERIFIED, details={}) for l in VerificationLayer]
        cov = svc.measure_verification_coverage(results)
        risk = svc.calculate_residual_risk(cov)
        vr = IndependentVerificationResult(verification_id='v1', plan_id='p1', tenant_id='t1', verifier=MagicMock(), action_id='a1', outcome=VerificationOutcome.VERIFIED, checks=[], execution_verified=True)
        conf = svc.calculate_verification_confidence(cov, risk, verification_result=vr, evidence_quality_score=0.95)
        assert conf.confidence_level == ConfidenceLevel.HIGH_CONFIDENCE
        assert conf.can_claim_recovered is True
        assert conf.requires_human_review is False

    def test_confidence_medium(self, svc):
        cov = svc.measure_verification_coverage([
            VerificationLayerResult(layer=l, passed=True, status=VerificationOutcome.VERIFIED, details={}) for l in VerificationLayer
        ] + [VerificationLayerResult(layer=VerificationLayer.INTEGRITY, passed=False, status=VerificationOutcome.VERIFICATION_FAILED, details={})])
        risk = svc.calculate_residual_risk(cov)
        vr = IndependentVerificationResult(verification_id='v1', plan_id='p1', tenant_id='t1', verifier=MagicMock(), action_id='a1', outcome=VerificationOutcome.VERIFIED, checks=[], execution_verified=True)
        conf = svc.calculate_verification_confidence(cov, risk, verification_result=vr, evidence_quality_score=0.8)
        assert conf.confidence_level in (ConfidenceLevel.HIGH_CONFIDENCE, ConfidenceLevel.MEDIUM_CONFIDENCE)

    def test_confidence_insufficient(self, svc):
        cov = svc.measure_verification_coverage([VerificationLayerResult(layer=VerificationLayer.EXACT_STATE, passed=True, status=VerificationOutcome.VERIFIED, details={})])
        risk = svc.calculate_residual_risk(cov)
        conf = svc.calculate_verification_confidence(cov, risk, evidence_quality_score=0.3)
        assert conf.confidence_level in (ConfidenceLevel.LOW_CONFIDENCE, ConfidenceLevel.INSUFFICIENT_EVIDENCE)
        assert conf.requires_human_review is True

    def test_confidence_factors_and_recommendations(self, svc):
        cov = svc.measure_verification_coverage([VerificationLayerResult(layer=VerificationLayer.EXACT_STATE, passed=True, status=VerificationOutcome.VERIFIED, details={})])
        risk = svc.calculate_residual_risk(cov)
        conf = svc.calculate_verification_confidence(cov, risk)
        assert len(conf.factors) > 0
        assert isinstance(conf.factors, list)
        assert conf.coverage_rate >= 0.0
        assert conf.residual_risk >= 0.0
        assert conf.definitive_failures >= 0

    def test_confidence_limitations(self, svc):
        cov = svc.measure_verification_coverage([
            VerificationLayerResult(layer=l, passed=True, status=VerificationOutcome.VERIFIED, details={}) for l in VerificationLayer
        ])
        risk = svc.calculate_residual_risk(cov)
        vr = IndependentVerificationResult(verification_id='v1', plan_id='p1', tenant_id='t1', verifier=MagicMock(), action_id='a1', outcome=VerificationOutcome.VERIFIED, checks=[], execution_verified=True)
        conf = svc.calculate_verification_confidence(cov, risk, verification_result=vr)
        assert conf.can_claim_recovered is True
