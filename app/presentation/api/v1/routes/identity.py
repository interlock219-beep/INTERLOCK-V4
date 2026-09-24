from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.domain.services.identity_anomaly_detection import IdentityAnomalyDetectionService
from app.presentation.api.dependencies.auth import CurrentUser

router = APIRouter(prefix="/identity", tags=["Identity"])


@router.get("/anomalies/{tenant_id}/{agent_id}")
async def get_identity_anomalies(
    tenant_id: str,
    agent_id: str,
    current_user: CurrentUser,
) -> dict[str, object]:
    """Detect identity anomalies for an agent. IDY-010."""
    service = IdentityAnomalyDetectionService()
    anomalies = await service.detect_anomalies(
        tenant_id=tenant_id,
        agent_id=agent_id,
    )
    return {
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "anomalies": [
            {
                "type": a.anomaly_type,
                "severity": a.severity,
                "description": a.description,
                "detected_at": a.detected_at.isoformat() if a.detected_at else None,
            }
            for a in anomalies
        ],
        "count": len(anomalies),
    }
