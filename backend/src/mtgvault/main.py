"""Composition root: the only place that knows concrete adapters (ADR-006).

Run with: ``uvicorn mtgvault.main:create_app --factory``
"""

from collections.abc import Callable

from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from mtgvault.adapters.db.unit_of_work import SqlAlchemyUnitOfWork
from mtgvault.adapters.in_memory_greeting import InMemoryGreetingProvider
from mtgvault.adapters.sql_readiness import SqlReadinessProbe
from mtgvault.api import health, hello, v1
from mtgvault.api.errors import PROBLEM_RESPONSES, install_error_handlers
from mtgvault.api.middleware import CorrelationIdMiddleware
from mtgvault.application.greeting_service import GreetingService
from mtgvault.application.ports import GreetingProvider, ReadinessProbe, UnitOfWork
from mtgvault.config import Settings, load_settings
from mtgvault.logging_setup import configure_logging


def create_app(
    settings: Settings | None = None,
    *,
    greeting_provider: GreetingProvider | None = None,
    readiness_probe: ReadinessProbe | None = None,
    unit_of_work_factory: Callable[[], UnitOfWork] | None = None,
) -> FastAPI:
    """Build the application. Collaborators can be injected (tests, OpenAPI export)."""
    if readiness_probe is None:
        settings = settings or load_settings()  # exits with a readable message when invalid
        configure_logging(settings.log_level)
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        readiness_probe = SqlReadinessProbe(engine)
        session_factory = sessionmaker(engine, expire_on_commit=False)
        unit_of_work_factory = unit_of_work_factory or (
            lambda: SqlAlchemyUnitOfWork(session_factory)
        )

    app = FastAPI(
        title="MTG Card Vault API",
        version="0.1.0",
        summary="Private, priced inventory of a Magic: The Gathering collection.",
        description=(
            "REST API of MTG Card Vault. Every error is an RFC 9457 `application/problem+json` "
            "document carrying a `correlation_id`, also returned in the `X-Request-ID` header."
        ),
        openapi_tags=[
            {"name": "health", "description": "Liveness and readiness (public)."},
            {
                "name": "skeleton",
                "description": "Temporary skeleton route, removed with issue #15.",
            },
        ],
        responses=PROBLEM_RESPONSES,
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
    )
    app.state.greeting_service = GreetingService(greeting_provider or InMemoryGreetingProvider())
    app.state.readiness_probe = readiness_probe
    app.state.unit_of_work_factory = unit_of_work_factory or _no_database
    app.add_middleware(CorrelationIdMiddleware)
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(hello.router)
    app.include_router(v1.router)
    return app


def _no_database() -> UnitOfWork:
    raise RuntimeError("No unit of work is configured (the app was built without a database)")
