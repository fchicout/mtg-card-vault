"""Liveness and readiness endpoints (FR-OPS-01). Intentionally unauthenticated."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from mtgvault.api.dependencies import get_readiness_probe
from mtgvault.application.ports import ReadinessProbe

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    status: str


@router.get("/healthz", operation_id="getLiveness", summary="Liveness: the process is up")
def liveness() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get(
    "/readyz",
    operation_id="getReadiness",
    summary="Readiness: dependencies are reachable",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthStatus}},
)
def readiness(
    response: Response,
    probe: Annotated[ReadinessProbe, Depends(get_readiness_probe)],
) -> HealthStatus:
    if probe.is_ready():
        return HealthStatus(status="ready")
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthStatus(status="unavailable")
