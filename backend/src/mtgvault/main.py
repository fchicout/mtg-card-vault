"""Composition root: the only place that knows concrete adapters (ADR-006).

Run with: ``uvicorn mtgvault.main:create_app --factory``
"""

from fastapi import FastAPI
from sqlalchemy import create_engine

from mtgvault.adapters.in_memory_greeting import InMemoryGreetingProvider
from mtgvault.adapters.sql_readiness import SqlReadinessProbe
from mtgvault.api import health, hello
from mtgvault.application.greeting_service import GreetingService
from mtgvault.application.ports import GreetingProvider, ReadinessProbe
from mtgvault.config import Settings


def create_app(
    settings: Settings | None = None,
    *,
    greeting_provider: GreetingProvider | None = None,
    readiness_probe: ReadinessProbe | None = None,
) -> FastAPI:
    """Build the application. Collaborators can be injected (tests, OpenAPI export)."""
    if readiness_probe is None:
        settings = settings or Settings()  # type: ignore[call-arg]  # values come from the environment
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        readiness_probe = SqlReadinessProbe(engine)

    app = FastAPI(
        title="MTG Card Vault API",
        version="0.1.0",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
    )
    app.state.greeting_service = GreetingService(greeting_provider or InMemoryGreetingProvider())
    app.state.readiness_probe = readiness_probe
    app.include_router(health.router)
    app.include_router(hello.router)
    return app
