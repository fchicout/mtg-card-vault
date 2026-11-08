"""FastAPI dependency providers. Concrete objects are wired by the composition root (main.py)."""

from collections.abc import Callable, Iterator
from typing import cast

from fastapi import Request

from mtgvault.application.catalog_service import CatalogService
from mtgvault.application.ports import ReadinessProbe, UnitOfWork
from mtgvault.application.user_service import UserService
from mtgvault.application.vault_service import VaultService


def get_catalog_service(request: Request) -> CatalogService:
    return cast("CatalogService", request.app.state.catalog_service)


def get_vault_service(request: Request) -> VaultService:
    return cast("VaultService", request.app.state.vault_service)


def get_user_service(request: Request) -> UserService:
    return cast("UserService", request.app.state.user_service)


def get_readiness_probe(request: Request) -> ReadinessProbe:
    return cast("ReadinessProbe", request.app.state.readiness_probe)


def get_unit_of_work(request: Request) -> Iterator[UnitOfWork]:
    """One unit of work per request, closed (and rolled back unless committed) afterwards."""
    factory = cast("Callable[[], UnitOfWork]", request.app.state.unit_of_work_factory)
    with factory() as unit_of_work:
        yield unit_of_work
