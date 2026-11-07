"""Typed settings read from the environment (12-factor, FR-OPS-03). Fails fast when invalid."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # e.g. postgresql+psycopg://user:password@db:5432/mtgvault
    # No default on purpose: credentials must be supplied by the environment.
    database_url: str = Field(min_length=1)
