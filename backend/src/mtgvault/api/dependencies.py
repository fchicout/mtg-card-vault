"""FastAPI dependency providers. Concrete objects are wired by the composition root (main.py)."""

from collections.abc import Callable, Iterator
from typing import cast

from fastapi import Request

from mtgvault.application.greeting_service import GreetingService
from mtgvault.application.ports import ReadinessProbe, UnitOfWork


def get_greeting_service(request: Request) -> GreetingService:
    return cast("GreetingService", request.app.state.greeting_service)


def get_readiness_probe(request: Request) -> ReadinessProbe:
    return cast("ReadinessProbe", request.app.state.readiness_probe)


def get_unit_of_work(request: Request) -> Iterator[UnitOfWork]:
    """One unit of work per request, closed (and rolled back unless committed) afterwards."""
    factory = cast("Callable[[], UnitOfWork]", request.app.state.unit_of_work_factory)
    with factory() as unit_of_work:
        yield unit_of_work
