from fastapi import APIRouter

from app.presentation.api.v1.routes import (
    activity,
    approval,
    auth,
    billing,
    compliance,
    discovery,
    health,
    intent,
    metrics,
    surgical_recovery,
)
from app.presentation.api.v1.routes.actions import router as actions_router
from app.presentation.api.v1.routes.agent_sessions import router as agent_sessions_router
from app.presentation.api.v1.routes.agents import router as agents_router
from app.presentation.api.v1.routes.authority import router as authority_router
from app.presentation.api.v1.routes.control import router as control_router
from app.presentation.api.v1.routes.discover import router as discover_router
from app.presentation.api.v1.routes.incident import router as incident_router
from app.presentation.api.v1.routes.incidents import router as incidents_router
from app.presentation.api.v1.routes.mfa import email_router, mfa_router, password_router
from app.presentation.api.v1.routes.session import session_router
from app.presentation.api.v1.routes.sso import sso_router
from app.presentation.api.v1.routes.webhook import router as webhook_router

api_v1_router = APIRouter()
api_v1_router.include_router(health.router)
api_v1_router.include_router(auth.router)
api_v1_router.include_router(mfa_router)
api_v1_router.include_router(password_router)
api_v1_router.include_router(email_router)
api_v1_router.include_router(session_router)
api_v1_router.include_router(sso_router)
api_v1_router.include_router(intent.router)
api_v1_router.include_router(approval.router)
api_v1_router.include_router(metrics.router)
api_v1_router.include_router(compliance.router)
api_v1_router.include_router(discovery.router)
api_v1_router.include_router(discover_router)
api_v1_router.include_router(billing.router)
api_v1_router.include_router(activity.router)
api_v1_router.include_router(surgical_recovery.router)
api_v1_router.include_router(agents_router, prefix="/agents")
api_v1_router.include_router(agent_sessions_router, prefix="/agent-sessions")
api_v1_router.include_router(authority_router, prefix="/authority")
api_v1_router.include_router(actions_router, prefix="/actions")
api_v1_router.include_router(control_router)
api_v1_router.include_router(incident_router)
api_v1_router.include_router(incidents_router)
api_v1_router.include_router(webhook_router)
