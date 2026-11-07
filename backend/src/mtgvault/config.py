"""Typed settings read from the environment (12-factor, FR-OPS-03). Fails fast when invalid.

Every variable is documented in docs/05 section 7.2. No setting has a secret default.
"""

import sys
from typing import Literal

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


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
