"""Composition root: the only place that knows concrete adapters (ADR-006).

Run with: ``uvicorn mtgvault.main:create_app --factory``
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from mtgvault.adapters.auth.deny_all import DenyAllTokenVerifier
from mtgvault.adapters.auth.jwks import JwksTokenVerifier, httpx_json_fetcher
from mtgvault.adapters.cache import TtlCache
from mtgvault.adapters.db.unit_of_work import SqlAlchemyUnitOfWork
from mtgvault.adapters.ocr.tesseract import TesseractRecognizer, find_tesseract
from mtgvault.adapters.rate_limit import SlidingWindowRateLimiter
from mtgvault.adapters.resilience import CircuitBreaker
from mtgvault.adapters.scryfall.client import ScryfallClient
from mtgvault.adapters.scryfall.provider import ScryfallCardProvider
from mtgvault.adapters.sql_readiness import SqlReadinessProbe
from mtgvault.api import health, v1
from mtgvault.api.errors import PROBLEM_RESPONSES, install_error_handlers
from mtgvault.api.image_upload import MAX_BYTES
from mtgvault.api.limits import BodyLimitMiddleware
from mtgvault.api.middleware import CorrelationIdMiddleware
from mtgvault.application.catalog_service import CatalogService
from mtgvault.application.lazy_refresh import LazyPriceRefresher
from mtgvault.application.ports import (
    Cache,
    CardDataProvider,
    RateLimiter,
    ReadinessProbe,
    RecognizedText,
    TextRecognizer,
    TokenVerifier,
    UnitOfWork,
)
from mtgvault.application.price_refresh import PriceRefresher
from mtgvault.application.scan_service import ScanService
from mtgvault.application.user_service import UserService
from mtgvault.application.vault_service import VaultService
from mtgvault.config import Settings, load_settings
from mtgvault.domain.card import Card, LookupResult, ResultPage
from mtgvault.domain.errors import UpstreamUnavailable
from mtgvault.logging_setup import configure_logging


class _Collaborators(NamedTuple):
    token_verifier: TokenVerifier
    card_provider: CardDataProvider | None
    cache: Cache
    scan_rate_limiter: RateLimiter
    text_recognizer: TextRecognizer | None


def _resolve_database(
    settings: Settings | None,
    readiness_probe: ReadinessProbe | None,
    unit_of_work_factory: Callable[[], UnitOfWork] | None,
) -> tuple[Settings | None, ReadinessProbe | None, Callable[[], UnitOfWork] | None]:
    """The real database when no probe was injected (exits with a readable message if invalid)."""
    if readiness_probe is not None:
        return settings, readiness_probe, unit_of_work_factory
    settings = settings or load_settings()
    configure_logging(settings.log_level)
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    sessions = sessionmaker(engine, expire_on_commit=False)
    return (
        settings,
        SqlReadinessProbe(engine),
        unit_of_work_factory or (lambda: SqlAlchemyUnitOfWork(sessions)),
    )


def create_app(
    settings: Settings | None = None,
    *,
    readiness_probe: ReadinessProbe | None = None,
    unit_of_work_factory: Callable[[], UnitOfWork] | None = None,
    token_verifier: TokenVerifier | None = None,
    card_provider: CardDataProvider | None = None,
    cache: Cache | None = None,
    text_recognizer: TextRecognizer | None = None,
    scan_rate_limiter: RateLimiter | None = None,
) -> FastAPI:
    """Build the application. Collaborators can be injected (tests, OpenAPI export).

    Without settings and without an injected verifier no token is ever accepted (fail closed).
    """
    settings, readiness_probe, unit_of_work_factory = _resolve_database(
        settings, readiness_probe, unit_of_work_factory
    )
    parts = _Collaborators(
        # `is None`, not `or`: an injected empty cache is falsy (it defines __len__) but is kept.
        token_verifier=_build_verifier(settings) if token_verifier is None else token_verifier,
        card_provider=_build_card_provider(settings) if card_provider is None else card_provider,
        cache=_build_cache(settings) if cache is None else cache,
        scan_rate_limiter=scan_rate_limiter or _build_rate_limiter(settings),
        text_recognizer=_build_recognizer(settings) if text_recognizer is None else text_recognizer,
    )
    token_verifier, card_provider, cache = parts.token_verifier, parts.card_provider, parts.cache
    scan_rate_limiter, text_recognizer = parts.scan_rate_limiter, parts.text_recognizer
    docs_enabled = settings is None or settings.api_docs_enabled

    app = FastAPI(
        title="MTG Card Vault API",
        version="0.5.0",
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
            {"name": "vault", "description": "The signed-in user's collection."},
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
    catalog = CatalogService(card_provider or _NoCards(), cache)
    app.state.catalog_service = catalog
    app.state.scan_rate_limiter = scan_rate_limiter
    app.state.scan_service = ScanService(text_recognizer or _NoRecognizer(), catalog)
    app.state.vault_service = VaultService(
        unit_of_work_factory or _no_database,
        catalog,
        stale_after=_stale_after(settings),
        lazy=LazyPriceRefresher(
            PriceRefresher(
                unit_of_work_factory or _no_database, card_provider or _NoCards(), _utc_now
            )
        ),
    )
    app.state.unit_of_work_factory = unit_of_work_factory or _no_database
    app.state.user_service = UserService(app.state.unit_of_work_factory)
    app.add_middleware(CorrelationIdMiddleware)
    # Whole body at most the image limit plus a little for the multipart envelope.
    app.add_middleware(
        BodyLimitMiddleware, path_prefix="/api/v1/scans", max_bytes=MAX_BYTES + 16 * 1024
    )
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
            breaker=CircuitBreaker("scryfall", open_seconds=settings.scryfall_breaker_open_seconds),
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


_NO_SOURCE = "No card data source is configured."


class _NoCards:
    """Stands in when no card source is configured (tests that do not touch the catalogue)."""

    def search(self, *_: object) -> ResultPage[Card]:
        raise UpstreamUnavailable(_NO_SOURCE)

    def get(self, *_: object) -> Card:
        raise UpstreamUnavailable(_NO_SOURCE)

    def printings(self, *_: object) -> ResultPage[Card]:
        raise UpstreamUnavailable(_NO_SOURCE)

    def lookup(self, *_: object) -> LookupResult:
        raise UpstreamUnavailable(_NO_SOURCE)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _build_rate_limiter(settings: Settings | None) -> RateLimiter:
    return SlidingWindowRateLimiter(settings.scan_rate_per_minute if settings else 30)


def _stale_after(settings: Settings | None) -> timedelta:
    return timedelta(hours=settings.price_stale_after_hours if settings else 24)


def _build_recognizer(settings: Settings | None) -> TextRecognizer | None:
    """Tesseract when the real service runs and the engine is installed (the API image has it)."""
    command = find_tesseract() if settings else None
    return TesseractRecognizer(command) if command else None


class _NoRecognizer:
    """Stands in when no OCR engine is configured (tests that do not scan)."""

    def read(self, *_: object) -> RecognizedText:
        raise UpstreamUnavailable("Card recognition is not available.")
