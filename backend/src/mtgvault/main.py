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
from mtgvault.adapters.cache import TtlCache
from mtgvault.adapters.db.unit_of_work import SqlAlchemyUnitOfWork
from mtgvault.adapters.resilience import CircuitBreaker
from mtgvault.adapters.scryfall.client import ScryfallClient
from mtgvault.adapters.scryfall.provider import ScryfallCardProvider
from mtgvault.adapters.sql_readiness import SqlReadinessProbe
from mtgvault.api import health, v1
from mtgvault.api.errors import PROBLEM_RESPONSES, install_error_handlers
from mtgvault.api.middleware import CorrelationIdMiddleware
from mtgvault.application.catalog_service import CatalogService
from mtgvault.application.ports import (
    Cache,
    CardDataProvider,
    ReadinessProbe,
    TokenVerifier,
    UnitOfWork,
)
from mtgvault.application.user_service import UserService
from mtgvault.config import Settings, load_settings
from mtgvault.domain.card import Card, ResultPage
from mtgvault.domain.errors import UpstreamUnavailable
from mtgvault.logging_setup import configure_logging


def create_app(
    settings: Settings | None = None,
    *,
    readiness_probe: ReadinessProbe | None = None,
    unit_of_work_factory: Callable[[], UnitOfWork] | None = None,
    token_verifier: TokenVerifier | None = None,
    card_provider: CardDataProvider | None = None,
    cache: Cache | None = None,
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
    # `is None`, not `or`: an injected empty cache is falsy (it defines __len__) but must be kept.
    token_verifier = _build_verifier(settings) if token_verifier is None else token_verifier
    card_provider = _build_card_provider(settings) if card_provider is None else card_provider
    cache = _build_cache(settings) if cache is None else cache
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
            {"name": "catalog", "description": "Search cards, details and printings."},
        ],
        responses=PROBLEM_RESPONSES,
        openapi_url="/api/v1/openapi.json" if docs_enabled else None,
        docs_url="/api/v1/docs" if docs_enabled else None,
        redoc_url=None,
    )
    app.state.readiness_probe = readiness_probe
    app.state.token_verifier = token_verifier
    app.state.card_provider = card_provider
    app.state.catalog_cache = cache
    app.state.catalog_service = CatalogService(card_provider or _NoCards(), cache)
    app.state.unit_of_work_factory = unit_of_work_factory or _no_database
    app.state.user_service = UserService(app.state.unit_of_work_factory)
    app.add_middleware(CorrelationIdMiddleware)
    _add_cors(app, settings)
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(v1.router)
    return app


def _build_verifier(settings: Settings | None) -> TokenVerifier:
    if settings is None:
        return DenyAllTokenVerifier()
    return JwksTokenVerifier(
        issuer=settings.oidc_issuer_url,
        audience=settings.oidc_audience,
        algorithms=settings.oidc_algorithms,
        fetch_json=httpx_json_fetcher(),
    )


def _build_card_provider(settings: Settings | None) -> CardDataProvider | None:
    if settings is None:
        return None
    # ONE client: its request spacing and circuit breaker are process-wide (FR-DAT-01).
    return ScryfallCardProvider(
        ScryfallClient(
            base_url=settings.scryfall_base_url,
            user_agent=settings.scryfall_user_agent,
            breaker=CircuitBreaker("scryfall"),
        )
    )


def _build_cache(settings: Settings | None) -> Cache:
    if settings is None:
        return TtlCache(300, 500)
    return TtlCache(settings.catalog_cache_ttl_seconds, settings.catalog_cache_max_entries)


def _add_cors(app: FastAPI, settings: Settings | None) -> None:
    if settings is None or not settings.cors_origin_list:
        return
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


def _no_database() -> UnitOfWork:
    raise RuntimeError("No unit of work is configured (the app was built without a database)")


class _NoCards:
    """Stands in when no card source is configured (tests that do not touch the catalogue)."""

    def search(self, *_: object) -> ResultPage[Card]:
        raise UpstreamUnavailable("No card data source is configured.")

    def get(self, *_: object) -> Card:
        raise UpstreamUnavailable("No card data source is configured.")

    def printings(self, *_: object) -> ResultPage[Card]:
        raise UpstreamUnavailable("No card data source is configured.")
