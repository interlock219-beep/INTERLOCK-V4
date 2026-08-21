from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.application.dto.auth import UserResponse
from app.domain.exceptions.domain_errors import ApprovalError
from app.domain.services.hitl_queue import HITLQueue
from app.infrastructure.config.settings import get_settings
from app.infrastructure.logging.audit_logger import log_security_event
from app.infrastructure.observability.metrics import metrics
from app.presentation.api.dependencies.auth import require_hitl_approver

router = APIRouter(prefix="/approval", tags=["Approval"])

_hitl_queue = HITLQueue()

HitLApprover = Annotated[UserResponse, Depends(require_hitl_approver)]


def _get_hitl_queue() -> HITLQueue:
    settings = get_settings()
    return HITLQueue(
        ttl_seconds=settings.hitl_ttl_seconds,
        required_approvers=settings.hitl_required_approvers,
    )


@router.get("/pending")
async def list_pending(
    current_user: HitLApprover,
) -> dict[str, object]:
    """List pending approval requests (authorized approvers only)."""
    hitl_queue = _get_hitl_queue()
    pending = await hitl_queue.list_pending_requests()
    return {"pending": pending}


@router.post("/{request_id}/approve")
async def approve_request(
    request: Request,
    request_id: str,
    current_user: HitLApprover,
) -> dict[str, object]:
    """Approve an HITL request (authorized approver only).

    Supports dual approval: the request is only marked as approved when
    the required number of distinct approvers have accepted it.
    Self-approval is not permitted.
    """
    correlation_id = getattr(request.state, "correlation_id", "")
    hitl_queue = _get_hitl_queue()
    try:
        entry = await hitl_queue.approve_request(
            request_id, decided_by=current_user.id
        )
    except ApprovalError as exc:
        log_security_event(
            "approval_approve_failed",
            correlation_id=correlation_id,
            request_id=request_id,
            user_id=str(current_user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    log_security_event(
        "approval_approved",
        correlation_id=correlation_id,
        request_id=request_id,
        user_id=str(current_user.id),
        risk_score=entry.get("risk_score"),
    )
    metrics.increment_hitl_event("approved")
    return {"request_id": request_id, "status": entry.get("status", "approved")}


@router.post("/{request_id}/reject")
async def reject_request(
    request: Request,
    request_id: str,
    current_user: HitLApprover,
) -> dict[str, object]:
    """Reject an HITL request (authorized approver only)."""
    correlation_id = getattr(request.state, "correlation_id", "")
    hitl_queue = _get_hitl_queue()
    try:
        entry = await hitl_queue.reject_request(
            request_id, decided_by=current_user.id
        )
    except ApprovalError as exc:
        log_security_event(
            "approval_reject_failed",
            correlation_id=correlation_id,
            request_id=request_id,
            user_id=str(current_user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    log_security_event(
        "approval_rejected",
        correlation_id=correlation_id,
        request_id=request_id,
        user_id=str(current_user.id),
        risk_score=entry.get("risk_score"),
    )
    metrics.increment_hitl_event("rejected")
    return {"request_id": request_id, "status": entry.get("status", "rejected")}


@router.post("/{request_id}/revoke")
async def revoke_request(
    request: Request,
    request_id: str,
    current_user: HitLApprover,
) -> dict[str, object]:
    """Revoke an approved or pending HITL request (authorized approver only).

    Revocation prevents a previously approved request from being executed.
    """
    correlation_id = getattr(request.state, "correlation_id", "")
    hitl_queue = _get_hitl_queue()
    try:
        entry = await hitl_queue.revoke_request(request_id)
    except ApprovalError as exc:
        log_security_event(
            "approval_revoke_failed",
            correlation_id=correlation_id,
            request_id=request_id,
            user_id=str(current_user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    log_security_event(
        "approval_revoked",
        correlation_id=correlation_id,
        request_id=request_id,
        user_id=str(current_user.id),
        risk_score=entry.get("risk_score"),
    )
    metrics.increment_hitl_event("revoked")
    return {"request_id": request_id, "status": entry.get("status", "revoked")}
