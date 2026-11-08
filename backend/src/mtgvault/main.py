"""Composition root: the only place that knows concrete adapters (ADR-006).

Run with: ``uvicorn mtgvault.main:create_app --factory``
"""

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from mtgvault.adapters.auth.deny_all import DenyAllTokenVerifier
from mtgvault.adapters.auth.jwks import JwksTokenVerifier, httpx_json_fetcher
from mtgvault.adapters.db.unit_of_work import SqlAlchemyUnitOfWork
from mtgvault.adapters.sql_readiness import SqlReadinessProbe
from mtgvault.api import health, v1
from mtgvault.api.errors import PROBLEM_RESPONSES, install_error_handlers
from mtgvault.api.middleware import CorrelationIdMiddleware
from mtgvault.application.ports import ReadinessProbe, TokenVerifier, UnitOfWork
from mtgvault.application.user_service import UserService
from mtgvault.config import Settings, load_settings
from mtgvault.logging_setup import configure_logging


def create_app(
    settings: Settings | None = None,
    *,
    readiness_probe: ReadinessProbe | None = None,
    unit_of_work_factory: Callable[[], UnitOfWork] | None = None,
    token_verifier: TokenVerifier | None = None,
) -> FastAPI:
    """Build the application. Collaborators can be injected (tests, OpenAPI export).

    Without settings and without an injected verifier no token is ever accepted (fail closed).
    """
    if readiness_probe is None:
        settings = settings or load_settings()  # exits with a readable message when invalid
        configure_logging(settings.log_level)
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        readiness_probe = SqlReadinessProbe(engine)
        session_factory = sessionmaker(engine, expire_on_commit=False)
        unit_of_work_factory = unit_of_work_factory or (
            lambda: SqlAlchemyUnitOfWork(session_factory)
        )
    if token_verifier is None:
        token_verifier = (
            JwksTokenVerifier(
                issuer=settings.oidc_issuer_url,
                audience=settings.oidc_audience,
                algorithms=settings.oidc_algorithms,
                fetch_json=httpx_json_fetcher(),
            )
            if settings
            else DenyAllTokenVerifier()
        )
    docs_enabled = settings is None or settings.api_docs_enabled

    app = FastAPI(
        title="MTG Card Vault API",
        version="0.1.0",
        summary="Private, priced inventory of a Magic: The Gathering collection.",
        description=(
            "REST API of MTG Card Vault. Every versioned route needs an OIDC bearer token. "
            "Every error is an RFC 9457 `application/problem+json` document carrying a "
            "`correlation_id`, also returned in the `X-Request-ID` header."
        ),
        openapi_tags=[
            {"name": "health", "description": "Liveness and readiness (public)."},
            {"name": "account", "description": "The signed-in user (bearer token required)."},
        ],
        responses=PROBLEM_RESPONSES,
        openapi_url="/api/v1/openapi.json" if docs_enabled else None,
        docs_url="/api/v1/docs" if docs_enabled else None,
        redoc_url=None,
    )
    app.state.readiness_probe = readiness_probe
    app.state.token_verifier = token_verifier
    app.state.unit_of_work_factory = unit_of_work_factory or _no_database
    app.state.user_service = UserService(app.state.unit_of_work_factory)
    app.add_middleware(CorrelationIdMiddleware)
    if settings and settings.cors_origin_list:
        # Outermost, so a preflight is answered before authentication. No cookies, no wildcard.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
            expose_headers=["X-Request-ID", "Retry-After"],
            max_age=600,
        )
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(v1.router)
    return app


def _no_database() -> UnitOfWork:
    raise RuntimeError("No unit of work is configured (the app was built without a database)")
