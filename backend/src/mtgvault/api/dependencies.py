"""FastAPI dependency providers. Concrete objects are wired by the composition root (main.py)."""

from typing import cast

from fastapi import Request

from mtgvault.application.greeting_service import GreetingService
from mtgvault.application.ports import ReadinessProbe


def get_greeting_service(request: Request) -> GreetingService:
    return cast("GreetingService", request.app.state.greeting_service)


def get_readiness_probe(request: Request) -> ReadinessProbe:
    return cast("ReadinessProbe", request.app.state.readiness_probe)
