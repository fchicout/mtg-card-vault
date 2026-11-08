"""The versioned API surface. Feature routers are included here as they are built.

Every route of this router requires a verified bearer token (US-026); only the health endpoints
live outside it.
"""

from fastapi import APIRouter, Depends, status

from mtgvault.api.errors import Problem
from mtgvault.api.security import current_principal

API_PREFIX = "/api/v1"

router = APIRouter(
    prefix=API_PREFIX,
    dependencies=[Depends(current_principal)],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": Problem, "description": "Missing or invalid token"},
        status.HTTP_403_FORBIDDEN: {"model": Problem, "description": "Not allowed"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": Problem,
            "description": "The identity provider is unreachable",
        },
    },
)
