"""Emergency-deny enforcement chokepoint at execution boundaries (PILLAR 6).

``EmergencyControlService`` promises that "emergency deny immediately
blocks all execution for a tenant". This module is the single guard that
every execution entry point calls, so ACTIVATION (the emergency routes)
and ENFORCEMENT (execute/resume/intent paths) observe the same
process-wide deny state. A policy decision that no execution path reads
is exactly the "UI-only" bypass the mission calls out:

    A policy decision in the UI is insufficient if an alternate execution
    path bypasses enforcement.
"""

from fastapi import HTTPException, status

from app.domain.services.emergency_control_service import (
    get_emergency_control_service,
)


async def assert_execution_permitted(tenant_id: str) -> None:
    """Raise 403 when emergency deny is active for the tenant.

    An empty tenant id (tenancy disabled by configuration) has no deny
    state to consult and passes through, matching the repository
    convention used elsewhere for unset tenants.
    """
    service = get_emergency_control_service()
    if tenant_id and await service.is_emergency_deny_active(tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "EMERGENCY DENY is active for this tenant — all execution blocked."
            ),
        )
