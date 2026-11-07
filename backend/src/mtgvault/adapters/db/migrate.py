"""Run Alembic migrations programmatically (FR-OPS-03)."""

from pathlib import Path

from alembic import command
from alembic.config import Config


def alembic_config(database_url: str, base_dir: Path | None = None) -> Config:
    """``base_dir`` holds ``alembic.ini``; default: the working directory (``/app`` in Docker)."""
    config = Config(str((base_dir or Path.cwd()) / "alembic.ini"))
    config.attributes["database_url"] = database_url
    return config


def upgrade_to_head(database_url: str, base_dir: Path | None = None) -> None:
    command.upgrade(alembic_config(database_url, base_dir), "head")
