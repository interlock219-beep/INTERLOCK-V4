from __future__ import annotations
import hashlib, json, logging, secrets
from datetime import UTC, datetime
from typing import Any
from app.domain.entities.causal_state_types import ConfidenceLevel, RecoveryReport, VerificationStatus
from app.domain.entities.independent_verification_types import (EvidenceAssessment, IndependentVerificationReport, IndependentVerificationResult, IndependentVerifier, IndependentVerifierRole, ResidualRisk, VerificationCheck, VerificationCheckType, VerificationConfidence, VerificationCoverage, VerificationLayer, VerificationLayerResult, VerificationOutcome)
from app.domain.entities.surgical_recovery_types import RecoveryEvidence
from app.domain.repositories.recovery_evidence_repository import RecoveryEvidenceRepository
from app.domain.services.evidence_verification_service import EvidenceVerificationService
logger = logging.getLogger('intentlock.independent_verification')
class IndependentVerificationService:
    ALL_LAYERS = list(VerificationLayer)
    def __init__(self, evidence_repository: RecoveryEvidenceRepository | None = None) -> None:
        self._evidence_repo = evidence_repository
        self._evidence_verifier = EvidenceVerificationService()
    def create_verifier(self, verifier_id: str, role: IndependentVerifierRole, tenant_id: str, credentials: dict[str, Any] | None = None, delegation_chain: list[str] | None = None) -> IndependentVerifier:
        return IndependentVerifier(verifier_id=verifier_id, role=role, tenant_id=tenant_id, credentials=credentials or {}, delegation_chain=delegation_chain or [])
    def create_verification_check(self, check_id: str, check_type: VerificationCheckType, description: str, expected: Any, actual: Any, passed: bool, evidence_references: list[str] | None = None, details: dict[str, Any] | None = None) -> VerificationCheck:
        return VerificationCheck(check_id=check_id, check_type=check_type, description=description, expected=expected, actual=actual, passed=passed, details=details or {}, evidence_references=evidence_references or [])
    def build_verification_result(self, result: VerificationCheck) -> bool:
        return result.passed
    def verify_evidence(self, evidence: RecoveryEvidence) -> EvidenceAssessment:
        integrity = self._evidence_verifier.verify_evidence_integrity(evidence)
        tamper_indicators, missing_fields, conflict_details, inconclusive_reasons = [], [], [], []
        if not integrity['integrity_ok']:
            for issue in integrity['issues']:
                il = issue.lower()
                if 'tamper' in il or 'hash' in il: tamper_indicators.append(issue)
                if 'missing' in il: missing_fields.append(issue)
                if 'conflict' in il: conflict_details.append(issue)
                if 'inconclusive' in il: inconclusive_reasons.append(issue)
        return EvidenceAssessment(evidence_id=evidence.evidence_id, is_tampered=len(tamper_indicators) > 0, is_missing=len(missing_fields) > 0, is_conflicting=len(conflict_details) > 0, is_inconclusive=len(inconclusive_reasons) > 0, tamper_indicators=tamper_indicators, missing_fields=missing_fields, conflict_details=conflict_details, inconclusive_reasons=inconclusive_reasons)
    def independent_verify(self, tenant_id: str, plan_id: str, incident_id: str, verifier: IndependentVerifier, verification_report: RecoveryReport) -> IndependentVerificationResult:
        rechecked_steps, all_checks_passed, overall_outcome = [], True, VerificationOutcome.VERIFIED
        for action_id, result in verification_report.resource_results.items():
            status = result.get('status', VerificationStatus.UNKNOWN_EXTERNAL_OUTCOME.value)
            if status == VerificationStatus.EXECUTED_AND_VERIFIED.value: passed=True; check_outcome=VerificationOutcome.VERIFIED
            elif status == VerificationStatus.EXECUTED_NOT_VERIFIED.value: passed=False; check_outcome=VerificationOutcome.UNVERIFIED; all_checks_passed=False
            elif status == VerificationStatus.EXECUTION_FAILED.value: passed=False; check_outcome=VerificationOutcome.VERIFICATION_FAILED; all_checks_passed=False
            else: passed=False; check_outcome=VerificationOutcome.MANUAL_CHECK_REQUIRED; all_checks_passed=False
            if check_outcome != VerificationOutcome.VERIFIED: overall_outcome = check_outcome
            check = self.create_verification_check(check_id=f'check-{plan_id}-{action_id}', check_type=VerificationCheckType.INTEGRITY, description=f'Independent check for action {action_id}', expected='executed_and_verified', actual=status, passed=passed, evidence_references=[f'evidence-{action_id}'], details={'original_status': status, 'original_verification': result.get('verification'), 'independent_check': True})
            rechecked_steps.append(check)
        return IndependentVerificationResult(verification_id=f'verif-{plan_id}-{secrets.token_hex(8)}', plan_id=plan_id, tenant_id=tenant_id, verifier=verifier, action_id='', outcome=overall_outcome, checks=rechecked_steps, execution_verified=all_checks_passed, verification_timestamp=datetime.now(UTC))
    def build_verification_report(self, tenant_id: str, plan_id: str, incident_id: str, verifier: IndependentVerifier, results: list[IndependentVerificationResult]) -> IndependentVerificationReport:
        if not results: overall = VerificationOutcome.UNKNOWN
        elif all(r.outcome == VerificationOutcome.VERIFIED for r in results): overall = VerificationOutcome.VERIFIED
        elif any(r.outcome in (VerificationOutcome.VERIFICATION_FAILED, VerificationOutcome.EVIDENCE_TAMPERED) for r in results): overall = VerificationOutcome.VERIFICATION_FAILED
        else: overall = VerificationOutcome.UNVERIFIED
        return IndependentVerificationReport(report_id=f'ivr-{plan_id}-{secrets.token_hex(8)}', tenant_id=tenant_id, plan_id=plan_id, incident_id=incident_id, verifier=verifier, results=results, overall_outcome=overall)
    def assess_evidence_chain(self, evidences: list[RecoveryEvidence]) -> dict[str, Any]:
        return self._evidence_verifier.verify_evidence_chain(evidences)
    def compute_verification_hash(self, verification_data: dict[str, Any]) -> str:
        canonical = json.dumps(verification_data, sort_keys=True, default=str, separators=(',', ':'))
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    def run_multi_layer_verification(self, tenant_id: str, plan_id: str, action_id: str, before_state: dict[str, Any] | None = None, after_state: dict[str, Any] | None = None, evidence: RecoveryEvidence | None = None, context: dict[str, Any] | None = None) -> list[VerificationLayerResult]:
        context = context or {}
        results = []
        checks = [(VerificationLayer.EXACT_STATE, self._check_exact_state), (VerificationLayer.BYTE_CONTENT, self._check_byte_content), (VerificationLayer.STRUCTURAL, self._check_structural), (VerificationLayer.SEMANTIC, self._check_semantic), (VerificationLayer.INTEGRITY, self._check_integrity), (VerificationLayer.DEPENDENCY, self._check_dependency), (VerificationLayer.PERMISSIONS, self._check_permissions), (VerificationLayer.IDENTITY, self._check_identity), (VerificationLayer.DB_CONSTRAINTS, self._check_db_constraints), (VerificationLayer.APP_INVARIANTS, self._check_app_invariants), (VerificationLayer.BUSINESS_INVARIANTS, self._check_business_invariants), (VerificationLayer.CROSS_SYSTEM, self._check_cross_system), (VerificationLayer.RECOVERY_COMPLETENESS, self._check_recovery_completeness), (VerificationLayer.HUMAN_CHANGE_PRESERVATION, self._check_human_change_preservation)]
        for layer, check_fn in checks:
            try: passed, status, details = check_fn(before_state=before_state, after_state=after_state, evidence=evidence, context=context)
            except Exception as exc: passed=False; status=VerificationOutcome.INCONCLUSIVE; details={'error': str(exc)}
            results.append(VerificationLayerResult(layer=layer, passed=passed, status=status, details=details, evidence_references=[f'evidence-{action_id}'] if evidence else []))
        return results
    def _check_exact_state(self, before_state, after_state, evidence, context):
        if before_state is None or after_state is None: return False, VerificationOutcome.INCONCLUSIVE, {'reason': 'before/after state not provided'}
        expected = context.get('expected_state')
        if expected is None: return True, VerificationOutcome.VERIFIED, {'reason': 'no expected_state specified'}
        after_hash = self._evidence_verifier.compute_state_hash(after_state)
        expected_hash = self._evidence_verifier.compute_state_hash(expected) if isinstance(expected, dict) else expected
        passed = after_hash == expected_hash
        return passed, (VerificationOutcome.VERIFIED if passed else VerificationOutcome.VERIFICATION_FAILED), {'after_hash': after_hash, 'expected_hash': expected_hash, 'exact_match': passed}
    def _check_byte_content(self, before_state, after_state, evidence, context):
        if after_state is None: return False, VerificationOutcome.INCONCLUSIVE, {'reason': 'after_state not provided'}
        content_hashes = [hashlib.sha256(json.dumps(v, sort_keys=True, default=str).encode('utf-8')).hexdigest() for v in after_state.values()]
        immutable_fields = context.get('immutable_fields', [])
        all_consistent = True
        for field in immutable_fields:
            if field in before_state and field in after_state and before_state[field] != after_state[field]: all_consistent = False
        return all_consistent, (VerificationOutcome.VERIFIED if all_consistent else VerificationOutcome.VERIFICATION_FAILED), {'content_hashes': content_hashes, 'immutable_preserved': all_consistent, 'checked_fields': list(after_state.keys())}
    def _check_structural(self, before_state, after_state, evidence, context):
        if after_state is None: return False, VerificationOutcome.INCONCLUSIVE, {'reason': 'after_state not provided'}
        required_fields = context.get('required_fields', [])
        missing = [f for f in required_fields if f not in after_state]
        type_errors = []
        for field, expected_type in context.get('type_checks', {}).items():
            if field in after_state and not isinstance(after_state[field], expected_type): type_errors.append(f'{field}: expected {expected_type.__name__}')
        passed = len(missing) == 0 and len(type_errors) == 0
        return passed, (VerificationOutcome.VERIFIED if passed else VerificationOutcome.VERIFICATION_FAILED), {'missing_fields': missing, 'type_errors': type_errors, 'structural_ok': passed}
    def _check_semantic(self, before_state, after_state, evidence, context):
        if after_state is None: return False, VerificationOutcome.INCONCLUSIVE, {'reason': 'after_state not provided'}
        invariants = context.get('semantic_invariants', [])
        violations = []
        for inv in invariants:
            if callable(inv):
                try:
                    if inv(after_state) is False: violations.append(getattr(inv, '__name__', 'custom'))
                except Exception as exc: violations.append(f"{getattr(inv, '__name__', 'custom')}_error:{exc}")
            elif isinstance(inv, str) and inv not in after_state: violations.append(f'missing_semantic_field:{inv}')
        passed = len(violations) == 0
        return passed, (VerificationOutcome.VERIFIED if passed else VerificationOutcome.VERIFICATION_FAILED), {'violations': violations, 'semantic_ok': passed}
    def _check_integrity(self, before_state, after_state, evidence, context):
        if evidence is not None:
            integrity = self._evidence_verifier.verify_evidence_integrity(evidence)
            passed = integrity['integrity_ok']
            return passed, (VerificationOutcome.VERIFIED if passed else VerificationOutcome.EVIDENCE_TAMPERED), {'integrity_ok': passed, 'issues': integrity['issues'], 'evidence_id': evidence.evidence_id}
        if after_state is None: return False, VerificationOutcome.INCONCLUSIVE, {'reason': 'no evidence and no after_state'}
        state_hash = self._evidence_verifier.compute_state_hash(after_state)
        return True, VerificationOutcome.VERIFIED, {'state_hash': state_hash, 'integrity_ok': True}
    def _check_dependency(self, before_state, after_state, evidence, context):
        dependency_edges = context.get('dependency_edges', [])
        if not dependency_edges: return True, VerificationOutcome.VERIFIED, {'reason': 'no dependencies declared'}
        unsatisfied = []
        for dep in dependency_edges:
            if isinstance(dep, dict): dep_id = dep.get('action_id', str(dep))
            else: dep_id = str(dep)
            dep_status = dep.get('status', 'unknown')
            if dep_status != 'satisfied': unsatisfied.append(dep_id)
        passed = len(unsatisfied) == 0
        return passed, (VerificationOutcome.VERIFIED if passed else VerificationOutcome.VERIFICATION_FAILED), {'dependency_edges': dependency_edges, 'unsatisfied': unsatisfied, 'all_satisfied': passed}
    def _check_permissions(self, before_state, after_state, evidence, context):
        required = context.get('required_permissions', [])
        granted = context.get('granted_permissions', [])
        if not required: return True, VerificationOutcome.VERIFIED, {'reason': 'no permissions required'}
        missing = [p for p in required if p not in granted]
        return len(missing) == 0, VerificationOutcome.VERIFIED if not missing else VerificationOutcome.VERIFICATION_FAILED, {'required': required, 'missing': missing, 'all_granted': not missing}
    def _check_identity(self, before_state, after_state, evidence, context):
        actor_id = context.get('actor_id', '')
        expected = context.get('expected_actors', [])
        verifier_id = context.get('verifier_id', '')
        if not actor_id: return False, VerificationOutcome.VERIFICATION_FAILED, {'reason': 'no actor identified'}
        if expected and actor_id not in expected: return False, VerificationOutcome.VERIFICATION_FAILED, {'reason': 'actor not expected', 'actor_id': actor_id, 'expected': expected}
        ok = bool(verifier_id) or bool(expected)
        return ok, (VerificationOutcome.VERIFIED if ok else VerificationOutcome.UNVERIFIED), {'actor_id': actor_id, 'verifier_id': verifier_id, 'identity_ok': ok}
    def _check_db_constraints(self, before_state, after_state, evidence, context):
        constraint_results = context.get('db_constraint_results', {})
        if not constraint_results: return True, VerificationOutcome.VERIFIED, {'reason': 'no DB constraints'}
        violated = [n for n, ok in constraint_results.items() if not ok]
        return len(violated) == 0, VerificationOutcome.VERIFIED if not violated else VerificationOutcome.VERIFICATION_FAILED, {'constraints': constraint_results, 'violated': violated, 'all_passed': not violated}
    def _check_app_invariants(self, before_state, after_state, evidence, context):
        invariants = context.get('app_invariants', [])
        violations = []
        for inv in invariants:
            if callable(inv):
                try:
                    if inv(after_state) is False: violations.append(getattr(inv, '__name__', 'custom'))
                except Exception as exc: violations.append(f"{getattr(inv, '__name__', 'custom')}_error:{exc}")
            elif isinstance(inv, dict) and not inv.get('condition', True): violations.append(inv.get('rule', ''))
        return len(violations) == 0, VerificationOutcome.VERIFIED if not violations else VerificationOutcome.VERIFICATION_FAILED, {'violations': violations, 'invariants_ok': not violations}
    def _check_business_invariants(self, before_state, after_state, evidence, context):
        rules = context.get('business_rules', [])
        violations = []
        for rule in rules:
            if callable(rule):
                try:
                    if rule(after_state) is False: violations.append(getattr(rule, '__name__', 'custom'))
                except Exception as exc: violations.append(f"{getattr(rule, '__name__', 'custom')}_error:{exc}")
            elif isinstance(rule, dict) and not rule.get('passed', False): violations.append(rule.get('name', ''))
        return len(violations) == 0, VerificationOutcome.VERIFIED if not violations else VerificationOutcome.VERIFICATION_FAILED, {'violations': violations, 'business_rules_ok': not violations}
    def _check_cross_system(self, before_state, after_state, evidence, context):
        system_states = context.get('cross_system_states', {})
        if not system_states: return True, VerificationOutcome.VERIFIED, {'reason': 'no cross-system data'}
        systems = list(system_states.keys())
        primary = system_states[systems[0]]
        inconsistencies = [f'{systems[0]} vs {s}' for s in systems[1:] if system_states[s] != primary]
        return len(inconsistencies) == 0, VerificationOutcome.VERIFIED if not inconsistencies else VerificationOutcome.VERIFICATION_FAILED, {'systems': systems, 'inconsistencies': inconsistencies, 'consistent': not inconsistencies}
    def _check_recovery_completeness(self, before_state, after_state, evidence, context):
        steps = context.get('recovery_steps', [])
        if not steps: return True, VerificationOutcome.VERIFIED, {'reason': 'no recovery steps'}
        incomplete = [s for s in steps if s.get('status') != 'complete']
        return len(incomplete) == 0, VerificationOutcome.VERIFIED if not incomplete else VerificationOutcome.VERIFICATION_FAILED, {'total_steps': len(steps), 'incomplete': incomplete, 'complete': len(steps) - len(incomplete)}
    def _check_human_change_preservation(self, before_state, after_state, evidence, context):
        human_fields = context.get('human_managed_fields', [])
        if not human_fields or before_state is None: return True, VerificationOutcome.VERIFIED, {'reason': 'no human-managed fields'}
        altered = [f for f in human_fields if (f in before_state and f in after_state and before_state[f] != after_state[f]) or (f in before_state and f not in after_state)]
        return len(altered) == 0, VerificationOutcome.VERIFIED if not altered else VerificationOutcome.VERIFICATION_FAILED, {'human_fields': human_fields, 'altered': altered, 'preserved': not altered}
    def measure_verification_coverage(self, layer_results, action_ids=None, action_layer_results=None):
        action_ids = action_ids or []
        action_layer_results = action_layer_results or {}
        total = len(layer_results)
        passed = sum(1 for r in layer_results if r.passed and not r.is_inconclusive)
        failed = sum(1 for r in layer_results if r.status == VerificationOutcome.VERIFICATION_FAILED)
        inconclusive = sum(1 for r in layer_results if r.is_inconclusive)
        rate = passed / total if total > 0 else 0.0
        measured = list({r.layer for r in layer_results})
        all_set = set(self.ALL_LAYERS)
        missing = [l for l in all_set if l not in measured]
        action_cov = {}
        for aid, results in action_layer_results.items():
            if results:
                p = sum(1 for r in results if r.passed and not r.is_inconclusive)
                action_cov[aid] = p / len(results)
            else: action_cov[aid] = 0.0
        if not action_layer_results and action_ids:
            for aid in action_ids: action_cov[aid] = 0.0
        layer_cov = {}
        for layer in self.ALL_LAYERS:
            lr = [r for r in layer_results if r.layer == layer]
            if lr:
                p = sum(1 for r in lr if r.passed and not r.is_inconclusive)
                layer_cov[layer.value] = p / len(lr)
            else: layer_cov[layer.value] = 0.0
        return VerificationCoverage(total_checks=total, passed_checks=passed, failed_checks=failed, inconclusive_checks=inconclusive, coverage_rate=round(rate, 6), layers_measured=[l.value for l in measured], layers_missing=[l.value for l in missing], action_coverage=action_cov, layer_coverage=layer_cov)
    def calculate_residual_risk(self, coverage, layer_results=None, verification_result=None, risk_factors=None):
        layer_results = layer_results or []
        risk_factors = risk_factors or []
        factors = list(risk_factors)
        mitigations = []
        blocking = []
        if coverage.coverage_rate < 1.0:
            factors.append(f'coverage_gap:{1.0 - coverage.coverage_rate:.4f}')
        ml = [l for l in coverage.layers_missing if l]
        if ml: factors.append(f'missing_layers:{chr(44).join(ml)}'); blocking.append(f'Unverified layers: {chr(44).join(ml)}')
        if coverage.inconclusive_checks > 0:
            factors.append(f'inconclusive_checks:{coverage.inconclusive_checks}')
            blocking.append(f'{coverage.inconclusive_checks} inconclusive verification checks')
        if verification_result is not None:
            if verification_result.outcome in (VerificationOutcome.VERIFICATION_FAILED, VerificationOutcome.EVIDENCE_TAMPERED):
                factors.append(f'verification_outcome:{verification_result.outcome.value}')
                blocking.append(f'Verification outcome: {verification_result.outcome.value}')
            elif verification_result.outcome == VerificationOutcome.UNVERIFIED:
                factors.append('verification_unverified'); blocking.append('Steps remain unverified')
        for r in layer_results:
            if r.is_definitive: blocking.append(f'Definitive failure in {r.layer.value}')
            if r.is_inconclusive: factors.append(f'inconclusive_layer:{r.layer.value}')
        if coverage.failed_checks > 0: factors.append(f'failed_checks:{coverage.failed_checks}')
        if not factors and not blocking: risk_score = 0.0
        else: risk_score = min(1.0, coverage.coverage_rate * 0.4 + (1.0 if blocking else 0.0) * 0.4 + coverage.inconclusive_checks * 0.1)
        if risk_score < 0.3: risk_level = 'low'
        elif risk_score < 0.6: risk_level = 'medium'
        elif risk_score < 0.85: risk_level = 'high'
        else: risk_level = 'critical'
        if risk_score < 0.3: mitigations.append('Maintain current verification posture')
        if coverage.coverage_rate < 1.0: mitigations.append('Close coverage gaps by running missing verification layers')
        if blocking: mitigations.append('Resolve blocking factors before claiming recovery')
        return ResidualRisk(risk_score=round(risk_score, 6), risk_level=risk_level, risk_factors=factors, mitigations=mitigations, blocking_factors=blocking)
    def calculate_verification_confidence(self, coverage, residual_risk, verification_result=None, evidence_quality_score=1.0):
        factors = []
        recommendations = []
        limitations = []
        cr = coverage.coverage_rate
        rr = residual_risk.risk_score
        df = sum(1 for r in verification_result.checks if not r.passed) if verification_result else 0
        il = sum(1 for v in coverage.layer_coverage.values() if v < 1.0)
        if cr >= 0.95: factors.append(f'coverage:high ({cr:.2%})')
        elif cr >= 0.7: factors.append(f'coverage:moderate ({cr:.2%})')
        else: factors.append(f'coverage:low ({cr:.2%})')
        if evidence_quality_score >= 0.95: factors.append(f'evidence_quality:high ({evidence_quality_score:.2%})')
        else: factors.append(f'evidence_quality:moderate ({evidence_quality_score:.2%})')
        if rr < 0.3: factors.append(f'residual_risk:low ({rr:.4f})')
        elif rr < 0.6: factors.append(f'residual_risk:medium ({rr:.4f})')
        else: factors.append(f'residual_risk:high ({rr:.4f})')
        if df == 0: factors.append('no_definitive_failures')
        else: factors.append(f'definitive_failures:{df}'); limitations.append(f'{df} definitive verification failures')
        if il == 0: factors.append('all_layers_definitive')
        else: factors.append(f'inconclusive_layers:{il}'); limitations.append(f'{il} layers are inconclusive')
        if residual_risk.blocking_factors: limitations.append('Blocking factors: ' + '; '.join(residual_risk.blocking_factors))
        if cr >= 0.95 and rr < 0.3 and df == 0: confidence_level = ConfidenceLevel.HIGH_CONFIDENCE
        elif cr >= 0.7 and rr < 0.6 and df == 0: confidence_level = ConfidenceLevel.MEDIUM_CONFIDENCE
        elif cr >= 0.5 or rr < 0.85: confidence_level = ConfidenceLevel.LOW_CONFIDENCE
        else: confidence_level = ConfidenceLevel.INSUFFICIENT_EVIDENCE
        if confidence_level == ConfidenceLevel.HIGH_CONFIDENCE: recommendations.append('Recovery can be safely claimed')
        elif confidence_level == ConfidenceLevel.MEDIUM_CONFIDENCE: recommendations.append('Review flagged factors before claiming recovery')
        elif confidence_level == ConfidenceLevel.LOW_CONFIDENCE: recommendations.append('Resolve verification gaps'); limitations.append('Confidence below medium')
        else: recommendations.append('Gather additional evidence'); limitations.append('Insufficient evidence')
        if cr < 1.0: recommendations.append('Close verification coverage gaps')
        if rr > 0.3: recommendations.append('Mitigate residual risk factors')
        return VerificationConfidence(confidence_id=f'conf-verif-{secrets.token_hex(8)}', tenant_id='', plan_id='', confidence_level=confidence_level, coverage_rate=cr, evidence_quality=evidence_quality_score, residual_risk=rr, definitive_failures=df, inconclusive_layers=il, factors=factors, recommendations=recommendations, limitations=limitations)
