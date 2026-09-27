from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.domain.repositories.recovery_evidence_repository import RecoveryEvidenceRepository
from app.domain.services.evidence_verification_service import EvidenceVerificationService
from app.infrastructure.logging.audit_logger import log_security_event
from app.infrastructure.observability.metrics import metrics
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_recovery_evidence_repository import (
    SQLAlchemyRecoveryEvidenceRepository,
)
from app.presentation.api.dependencies.auth import CurrentUser, get_user_tenant_id

router = APIRouter(tags=["Evidence"])


def _get_session() -> Any:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _get_evidence_repo(
    session: Annotated[Session, Depends(_get_session)],
) -> RecoveryEvidenceRepository:
    return SQLAlchemyRecoveryEvidenceRepository(session)


@router.post("/verify/integrity", response_model=dict[str, Any])
async def verify_evidence_integrity(
    body: dict[str, Any],
    current_user: CurrentUser,
    evidence_repo: Annotated[RecoveryEvidenceRepository, Depends(_get_evidence_repo)],
) -> dict[str, Any]:
    """Verify integrity of a single evidence record. VER-001."""
    evidence_id = body.get("evidence_id")
    if not evidence_id:
        raise HTTPException(status_code=400, detail="evidence_id is required")

    evidence = await evidence_repo.get_by_evidence_id(get_user_tenant_id(current_user), evidence_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="Evidence not found")

    service = EvidenceVerificationService(evidence_repo)
    result = service.verify_evidence_integrity(evidence)

    log_security_event(
        "evidence_integrity_verified",
        tenant_id=get_user_tenant_id(current_user),
        evidence_id=evidence_id,
        integrity_ok=result.get("integrity_ok", False),
    )
    metrics.increment_security_exception("evidence_integrity_verified")
    return result


@router.post("/verify/state", response_model=dict[str, Any])
async def verify_state_transition(
    body: dict[str, Any],
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Verify integrity of a state transition. VER-001."""
    before_state = body.get("before_state")
    after_state = body.get("after_state")
    expected_hash = body.get("expected_hash")

    if before_state is None or after_state is None:
        raise HTTPException(status_code=400, detail="before_state and after_state are required")

    service = EvidenceVerificationService()
    result = service.verify_state_integrity(before_state, after_state, expected_hash=expected_hash)

    log_security_event(
        "state_transition_verified",
        tenant_id=get_user_tenant_id(current_user),
        verified=result.get("verified", False),
    )
    metrics.increment_security_exception("state_transition_verified")
    return result


@router.post("/verify/chain", response_model=dict[str, Any])
async def verify_evidence_chain(
    body: dict[str, Any],
    current_user: CurrentUser,
    evidence_repo: Annotated[RecoveryEvidenceRepository, Depends(_get_evidence_repo)],
) -> dict[str, Any]:
    """Verify chain of custody for evidence items. PRP-006."""
    evidence_ids = body.get("evidence_ids", [])
    if not evidence_ids:
        raise HTTPException(status_code=400, detail="evidence_ids must be a non-empty list")

    tenant_id = get_user_tenant_id(current_user)
    evidences: list[Any] = []
    for eid in evidence_ids:
        ev = await evidence_repo.get_by_evidence_id(tenant_id, eid)
        if ev is not None:
            evidences.append(ev)

    service = EvidenceVerificationService(evidence_repo)
    result = service.verify_evidence_chain(evidences)

    log_security_event(
        "evidence_chain_verified",
        tenant_id=tenant_id,
        chain_valid=result.get("chain_valid", False),
        evidence_count=result.get("evidence_count", 0),
    )
    metrics.increment_security_exception("evidence_chain_verified")
    return result


@router.post("/verify/recovery", response_model=dict[str, Any])
async def independent_verify_recovery(
    body: dict[str, Any],
    current_user: CurrentUser,
    evidence_repo: Annotated[RecoveryEvidenceRepository, Depends(_get_evidence_repo)],
) -> dict[str, Any]:
    """Independently verify a recovery result. VER-001."""
    plan_id = body.get("plan_id")
    tenant_id = body.get("tenant_id") or get_user_tenant_id(current_user)

    if not plan_id:
        raise HTTPException(status_code=400, detail="plan_id is required")

    from app.domain.entities.causal_state_types import RecoveryReport, VerificationStatus

    verification_report = RecoveryReport(
        report_id=f"report-{plan_id}",
        plan_id=plan_id,
        tenant_id=tenant_id,
        incident_id=plan_id,
        verification_status=VerificationStatus.EXECUTED_AND_VERIFIED,
        resource_results=body.get("resource_results", {}),
    )

    service = EvidenceVerificationService(evidence_repo)
    result = await service.independent_verify_recovery(tenant_id, plan_id, verification_report)

    log_security_event(
        "recovery_independently_verified",
        tenant_id=tenant_id,
        plan_id=plan_id,
        all_verified=result.get("all_steps_verified", False),
    )
    metrics.increment_security_exception("recovery_independently_verified")
    return result
