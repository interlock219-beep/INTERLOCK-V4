"""Doc-WP-4 (V6): adversarial verifier suite (Pillar 4).

The independent verifier must never convert unverified claims into success:

- empty report -> ``INCONCLUSIVE`` (nothing was re-checked);
- adapter lies -> the observation decides, divergence is recorded;
- omitted resource (vs ``expected_action_ids``) -> fail-closed;
- malformed entry -> fail-closed per entry, the run does not crash;
- stale evidence (belongs to another incident) -> fail-closed;
- evidence-lookup crash -> fail-closed, never success;
- ``INSUFFICIENT_EVIDENCE`` confidence can never claim recovery (pinned).

Partial-success coverage exists in ``test_domain_i_verification.py``
(``test_independent_verify_unverified``) and
``test_independent_verification_service.py``
(``test_independent_verify_partial_failure``) and is re-pinned here.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.domain.entities.causal_state_types import VerificationStatus
from app.domain.entities.independent_verification_types import (
    ConfidenceLevel,
    IndependentVerifierRole,
    VerificationConfidence,
    VerificationOutcome,
)
from app.domain.services.independent_verification_service import (
    IndependentVerificationService,
)

VERIFIED = VerificationStatus.EXECUTED_AND_VERIFIED.value
FAILED = VerificationStatus.EXECUTION_FAILED.value
NOT_VERIFIED = VerificationStatus.EXECUTED_NOT_VERIFIED.value


def _svc():
    return IndependentVerificationService()


def _verifier(svc):
    return svc.create_verifier(
        "v-adv", IndependentVerifierRole.AUTOMATED_VERIFIER, "t1"
    )


def _report(results):
    return SimpleNamespace(resource_results=results)


class _EvidenceRepoDouble:
    """Duck-typed RecoveryEvidenceRepository (service reads incident_id only)."""

    def __init__(self, evidence=None, raise_on_lookup: bool = False) -> None:
        self._evidence = evidence
        self._raise = raise_on_lookup

    async def get_by_action_id(self, tenant_id: str, action_id: str):
        if self._raise:
            raise RuntimeError("evidence store unavailable")
        return self._evidence


async def test_adversarial_empty_report_never_verified():
    svc = _svc()
    result = await svc.independent_verify(
        "t1", "p1", "i1", _verifier(svc), _report({})
    )
    assert result.outcome != VerificationOutcome.VERIFIED, (
        "an empty report re-checked nothing and must never verify"
    )
    assert result.outcome == VerificationOutcome.INCONCLUSIVE
    assert result.execution_verified is False


async def test_adversarial_adapter_lies_observed_state_decides():
    svc = _svc()
    report = _report({"act1": {"status": VERIFIED, "verification": {}}})
    observed = {"act1": FAILED}

    result = await svc.independent_verify(
        "t1", "p1", "i1", _verifier(svc), report, observed_states=observed
    )

    assert result.outcome == VerificationOutcome.VERIFICATION_FAILED
    assert result.execution_verified is False
    check = result.checks[0]
    assert check.passed is False
    # The lie is auditable: claim and observation are both retained.
    assert check.details["original_status"] == VERIFIED
    assert check.details["observed_status"] == FAILED
    assert check.details["claim_diverged"] is True


async def test_adversarial_observed_agreement_still_verifies():
    svc = _svc()
    report = _report({"act1": {"status": VERIFIED, "verification": {}}})

    result = await svc.independent_verify(
        "t1",
        "p1",
        "i1",
        _verifier(svc),
        report,
        observed_states={"act1": VERIFIED},
    )

    assert result.outcome == VerificationOutcome.VERIFIED
    assert result.execution_verified is True
    assert result.checks[0].passed is True


async def test_adversarial_omitted_resource_fails_closed():
    svc = _svc()
    report = _report({"act1": {"status": VERIFIED, "verification": {}}})

    result = await svc.independent_verify(
        "t1",
        "p1",
        "i1",
        _verifier(svc),
        report,
        expected_action_ids=["act1", "act2"],
    )

    assert result.outcome != VerificationOutcome.VERIFIED, (
        "a resource omitted from the report must not leave the run verified"
    )
    assert result.outcome == VerificationOutcome.INCONCLUSIVE
    assert result.execution_verified is False
    omitted = [c for c in result.checks if c.details.get("omitted")]
    assert omitted and omitted[0].passed is False


async def test_adversarial_malformed_result_fails_closed_not_crash():
    svc = _svc()
    report = _report({"act1": None})

    result = await svc.independent_verify(
        "t1", "p1", "i1", _verifier(svc), report
    )

    assert result.outcome != VerificationOutcome.VERIFIED
    assert result.execution_verified is False
    assert result.checks and result.checks[0].details.get("malformed") is True


async def test_adversarial_stale_evidence_fails_closed():
    stale = SimpleNamespace(incident_id="i-OLD")
    svc = IndependentVerificationService(
        evidence_repository=_EvidenceRepoDouble(evidence=stale)
    )
    report = _report({"act1": {"status": VERIFIED, "verification": {}}})

    result = await svc.independent_verify(
        "t1", "p1", "i1", _verifier(svc), report
    )

    assert result.outcome == VerificationOutcome.EVIDENCE_CONFLICTING, (
        "evidence belonging to another incident is stale, not verified"
    )
    assert result.execution_verified is False
    assert result.checks[0].details.get("stale_evidence_incident") == "i-OLD"


async def test_adversarial_evidence_lookup_crash_fails_closed():
    svc = IndependentVerificationService(
        evidence_repository=_EvidenceRepoDouble(raise_on_lookup=True)
    )
    report = _report({"act1": {"status": VERIFIED, "verification": {}}})

    result = await svc.independent_verify(
        "t1", "p1", "i1", _verifier(svc), report
    )

    assert result.outcome != VerificationOutcome.VERIFIED, (
        "a verifier crash must fail closed, never return success"
    )
    assert result.execution_verified is False
    assert result.checks[0].details.get("evidence_lookup_failed") is True


async def test_adversarial_partial_success_re_pinned():
    """Re-pin (existing coverage): partial success is never success."""
    svc = _svc()
    report = _report(
        {
            "act1": {"status": VERIFIED, "verification": {}},
            "act2": {"status": NOT_VERIFIED, "verification": {}},
            "act3": {"status": FAILED, "verification": {}},
        }
    )
    result = await svc.independent_verify(
        "t1", "p1", "i1", _verifier(svc), report
    )
    assert result.outcome != VerificationOutcome.VERIFIED
    assert result.execution_verified is False


def test_confidence_insufficient_evidence_cannot_claim_recovery():
    """Vocabulary enforcement: INSUFFICIENT_EVIDENCE is never a success."""
    conf = VerificationConfidence(
        confidence_id="c-adv",
        tenant_id="t1",
        plan_id="p1",
        confidence_level=ConfidenceLevel.INSUFFICIENT_EVIDENCE,
        coverage_rate=0.0,
        evidence_quality=0.0,
        residual_risk=1.0,
        definitive_failures=0,
        inconclusive_layers=1,
    )
    assert conf.can_claim_recovered is False
    assert conf.requires_human_review is True
