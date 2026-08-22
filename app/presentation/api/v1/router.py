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
)
from app.presentation.api.v1.routes.mfa import email_router, mfa_router, password_router
from app.presentation.api.v1.routes.session import session_router

api_v1_router = APIRouter()
api_v1_router.include_router(health.router)
api_v1_router.include_router(auth.router)
api_v1_router.include_router(mfa_router)
api_v1_router.include_router(password_router)
api_v1_router.include_router(email_router)
api_v1_router.include_router(session_router)
api_v1_router.include_router(intent.router)
api_v1_router.include_router(approval.router)
api_v1_router.include_router(metrics.router)
api_v1_router.include_router(compliance.router)
api_v1_router.include_router(discovery.router)
api_v1_router.include_router(billing.router)
api_v1_router.include_router(activity.router)
