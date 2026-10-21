"""Shared recovery-credit enforcement for the execution routes.

Every route that runs a recovery execution (execute / resume, both API
variants) gates on the same contract:

1. reserve one credit before the billable work (atomically; re-entrant for
   retries of the same plan; ``None`` for evaluation tenants with no wallet),
2. run the engine **unchanged**,
3. settle the hold from the engine's verified outcome -- charge only when
   ``status == "completed"`` AND ``verification_status ==
   "executed_and_verified"``, release otherwise.

Billing uses its own database session so a billing rollback can never touch
recovery-engine writes, and recovery failures still release their holds.
Emergency containment is a different set of routes and is never gated here.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.domain.exceptions.billing_errors import InsufficientCreditsError
from app.domain.services.recovery_credit_service import (
    CreditHold,
    RecoveryCreditService,
)
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_credit_repositories import (
    SQLAlchemyCreditRepository,
)


def build_credit_service() -> tuple[Session, RecoveryCreditService]:
    """Return a ``(session, service)`` pair; the caller must close the session."""
    session = SessionLocal()
    service = RecoveryCreditService(
        SQLAlchemyCreditRepository(session),
        reservation_ttl_minutes=get_settings().credit_reservation_ttl_minutes,
    )
    return session, service


async def reserve_recovery_credit(
    service: RecoveryCreditService, tenant_id: str, plan_id: str
) -> CreditHold | None:
    """Reserve one credit. ``None`` means evaluation mode (unbilled).

    Raises HTTP 402 with balance + renewal context when the tenant's
    allowance is exhausted.
    """
    try:
        return await service.reserve_for_execution(tenant_id, plan_id)
    except InsufficientCreditsError as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "message": "Your recovery allowance is exhausted for this billing period.",
                "available": exc.available,
                "required": exc.required,
                "renewal_at": exc.period_end.isoformat() if exc.period_end else None,
                "upgrade_hint": "Upgrade to Pro (250 credits/month) from the billing page.",
            },
        ) from exc


def is_billable_result(execution_result: dict[str, Any] | None) -> bool:
    """The documented billable point: completed AND independently verified."""
    if not execution_result:
        return False
    return (
        execution_result.get("status") == "completed"
        and execution_result.get("verification_status") == "executed_and_verified"
    )


async def settle_recovery_credit(
    service: RecoveryCreditService,
    hold: CreditHold | None,
    execution_result: dict[str, Any] | None,
) -> None:
    """Charge the held credit on a billable outcome, release it otherwise."""
    if hold is None:
        return
    await service.finalize_hold(hold, billable=is_billable_result(execution_result))
