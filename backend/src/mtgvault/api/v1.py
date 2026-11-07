"""The versioned API surface. Feature routers are included here as they are built."""

from fastapi import APIRouter

API_PREFIX = "/api/v1"

router = APIRouter(prefix=API_PREFIX)
