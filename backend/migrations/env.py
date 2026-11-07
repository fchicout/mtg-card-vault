"""Alembic environment: online migrations against PostgreSQL, serialised by an advisory lock."""

import os

from alembic import context
from sqlalchemy import create_engine, text

from mtgvault.adapters.db.base import Base

config = context.config
target_metadata = Base.metadata

# Held for the whole migration so two API instances starting together never race.
_ADVISORY_LOCK_KEY = 727_274_001


def _database_url() -> str:
    url = config.attributes.get("database_url") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set: cannot run migrations")
    return str(url)


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), pool_pre_ping=True)
    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": _ADVISORY_LOCK_KEY})
        try:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
            connection.commit()
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _ADVISORY_LOCK_KEY})
            connection.commit()
    engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline migrations are not supported: run against a live database")
run_migrations_online()
