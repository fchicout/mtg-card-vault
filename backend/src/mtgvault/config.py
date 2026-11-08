"""Typed settings read from the environment (12-factor, FR-OPS-03). Fails fast when invalid.

Every variable is documented in docs/05 section 7.2. No setting has a secret default.
"""

import sys
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Signing algorithms we accept for access tokens: asymmetric only (never ``none`` or HMAC).
ASYMMETRIC_ALGORITHMS = frozenset(
    {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "PS256", "PS384", "PS512"}
)


def is_acceptable_url(url: str) -> bool:
    """HTTPS only, except for loopback hosts (local development and tests)."""
    parts = urlsplit(url)
    if parts.scheme == "https" and parts.hostname:
        return True
    return parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1", "::1")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # e.g. postgresql+psycopg://user:password@db:5432/mtgvault
    # No default on purpose: credentials must be supplied by the environment.
    database_url: str = Field(min_length=1)
    log_level: LogLevel = "INFO"
    # Loopback unless told otherwise; the container image sets BIND_HOST explicitly (it must be
    # reachable from the proxy), so a bare `python -m mtgvault.serve` never listens on the network.
    bind_host: str = "127.0.0.1"
    bind_port: int = Field(default=8000, ge=1, le=65535)
    # Identity provider (ADR-003). No defaults: an API without an issuer must not start.
    oidc_issuer_url: str = Field(min_length=1)
    oidc_audience: str = Field(min_length=1)
    oidc_allowed_algs: str = "RS256"
    # Comma-separated browser origins allowed to call the API; empty means no cross-origin access.
    cors_origins: str = ""
    # Scryfall (FR-DAT-01): identify the application with a contact, as their API rules ask.
    scryfall_user_agent: str = Field(min_length=10)
    scryfall_base_url: str = "https://api.scryfall.com"
    # How long the circuit stays open after repeated Scryfall failures before one probe (FR-DAT-03).
    scryfall_breaker_open_seconds: float = Field(default=30.0, ge=1, le=600)
    # Catalogue results are cached briefly (ADR-007).
    catalog_cache_ttl_seconds: int = Field(default=300, ge=1, le=3600)
    catalog_cache_max_entries: int = Field(default=500, ge=1, le=10000)
    # Scans per user per minute (FR-SCN-08).
    scan_rate_per_minute: int = Field(default=30, ge=1, le=600)
    # Prices older than this are marked stale in the vault (FR-DAT-03).
    price_stale_after_hours: int = Field(default=24, ge=1, le=720)
    # When the worker refreshes every owned card (ADR-012): a 5-field cron expression in UTC.
    price_refresh_cron: str = "0 4 * * *"
    # Also run one refresh when the worker starts (for example right after a deployment).
    price_refresh_on_start: bool = False
    # The worker touches this file regularly; the container healthcheck reads its age.
    worker_heartbeat_file: str = "/tmp/mtgvault-worker.alive"  # noqa: S108  # tmpfs in the container
    # The interactive API documentation is for development; production leaves it off.
    api_docs_enabled: bool = False

    @field_validator("oidc_issuer_url", "scryfall_base_url")
    @classmethod
    def _urls_are_https(cls, value: str) -> str:
        if not is_acceptable_url(value):
            raise ValueError("must be an https URL (http only for localhost)")
        return value.rstrip("/")

    @field_validator("price_refresh_cron")
    @classmethod
    def _cron_is_valid(cls, value: str) -> str:
        from mtgvault.cron import cron_trigger

        try:
            cron_trigger(value)
        except ValueError as error:
            raise ValueError(
                f"must be a 5-field cron expression such as '0 4 * * *' ({error})"
            ) from error
        return value.strip()

    @field_validator("oidc_allowed_algs")
    @classmethod
    def _algs_are_asymmetric(cls, value: str) -> str:
        names = [n.strip() for n in value.split(",") if n.strip()]
        bad = [n for n in names if n not in ASYMMETRIC_ALGORITHMS]
        if bad or not names:
            raise ValueError(f"only asymmetric algorithms are accepted, not {bad or value!r}")
        return ",".join(names)

    @field_validator("cors_origins")
    @classmethod
    def _origins_are_explicit(cls, value: str) -> str:
        for origin in (o.strip() for o in value.split(",") if o.strip()):
            parts = urlsplit(origin)
            if (
                origin == "*"
                or parts.scheme not in ("http", "https")
                or not parts.hostname
                or parts.path not in ("", "/")
            ):
                raise ValueError(
                    f"{origin!r} is not an explicit origin such as https://app.example"
                )
        return value

    @property
    def oidc_algorithms(self) -> list[str]:
        return self.oidc_allowed_algs.split(",")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]


def load_settings() -> Settings:
    """Read and validate the environment, or exit with a readable message (never echo values)."""
    try:
        return Settings()  # type: ignore[call-arg]  # values come from the environment
    except ValidationError as error:
        lines = [
            f"  - {'.'.join(str(part) for part in problem['loc']).upper()}: {problem['msg']}"
            for problem in error.errors()
        ]
        sys.stderr.write("Invalid configuration, refusing to start:\n" + "\n".join(lines) + "\n")
        raise SystemExit(2) from error
