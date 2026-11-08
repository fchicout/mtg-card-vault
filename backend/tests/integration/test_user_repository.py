"""FR-AUTH-04 on real PostgreSQL: the users table and the race-safe upsert."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from mtgvault.adapters.db import models  # noqa: F401
from mtgvault.adapters.db.base import Base
from mtgvault.adapters.db.migrate import upgrade_to_head
from mtgvault.adapters.db.unit_of_work import SqlAlchemyUnitOfWork
from mtgvault.domain.identity import Principal

BACKEND_DIR = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)


@pytest.fixture
def migrated(database_url: str, engine: Engine) -> Engine:
    upgrade_to_head(database_url, BACKEND_DIR)
    return engine


def provision(factory: sessionmaker[Session], principal: Principal, now: datetime = NOW):  # type: ignore[no-untyped-def]
    with SqlAlchemyUnitOfWork(factory) as uow:
        user = uow.users.provision(principal, now, HOUR)
        uow.commit()
    return user


def rows(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(text("SELECT count(*) FROM users")).scalar_one())


def test_the_models_match_the_migrations(migrated: Engine) -> None:
    with migrated.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == []


def test_users_table_shape(migrated: Engine) -> None:
    inspector = inspect(migrated)
    columns = {c["name"]: c for c in inspector.get_columns("users")}
    assert set(columns) == {"id", "sub", "display_name", "email", "created_at", "last_login_at"}
    assert not columns["sub"]["nullable"]
    assert columns["display_name"]["nullable"]
    assert [u["column_names"] for u in inspector.get_unique_constraints("users")] == [["sub"]]


def test_first_call_creates_the_user(migrated: Engine) -> None:
    factory = sessionmaker(migrated, expire_on_commit=False)
    user = provision(factory, Principal("sub-1", "Ada", "ada@example.org"))
    assert (user.subject, user.display_name, user.email) == ("sub-1", "Ada", "ada@example.org")
    assert user.last_login_at == NOW
    assert rows(migrated) == 1


def test_second_call_returns_the_same_user_without_a_rewrite(migrated: Engine) -> None:
    factory = sessionmaker(migrated, expire_on_commit=False)
    first = provision(factory, Principal("sub-1", "Ada", None))
    again = provision(factory, Principal("sub-1", "Ada", None), NOW + timedelta(minutes=5))
    assert again.id == first.id
    assert again.last_login_at == NOW  # younger than the refresh window: not rewritten
    assert rows(migrated) == 1


def test_old_login_timestamp_is_refreshed(migrated: Engine) -> None:
    factory = sessionmaker(migrated, expire_on_commit=False)
    provision(factory, Principal("sub-1", "Ada", None))
    later = NOW + timedelta(hours=2)
    assert provision(factory, Principal("sub-1", "Ada", None), later).last_login_at == later


def test_a_changed_profile_is_updated_and_a_missing_one_is_kept(migrated: Engine) -> None:
    factory = sessionmaker(migrated, expire_on_commit=False)
    provision(factory, Principal("sub-1", "Ada", "ada@example.org"))
    renamed = provision(factory, Principal("sub-1", "Ada L.", "ada@example.org"))
    assert renamed.display_name == "Ada L."
    kept = provision(factory, Principal("sub-1", None, None))  # token without name/email
    assert (kept.display_name, kept.email) == ("Ada L.", "ada@example.org")


def test_parallel_first_calls_create_exactly_one_row(migrated: Engine) -> None:
    factory = sessionmaker(migrated, expire_on_commit=False)
    principal = Principal("racer", "Racer", None)
    with ThreadPoolExecutor(max_workers=8) as pool:
        users = list(pool.map(lambda _: provision(factory, principal), range(16)))
    assert rows(migrated) == 1
    assert len({u.id for u in users}) == 1


def test_subject_is_unique_at_the_database_level(migrated: Engine) -> None:
    with migrated.begin() as connection:
        insert = text(
            "INSERT INTO users (id, sub, last_login_at) VALUES (gen_random_uuid(), 's', now())"
        )
        connection.execute(insert)
        with pytest.raises(IntegrityError):
            connection.execute(insert)


def test_downgrade_removes_the_table(database_url: str, migrated: Engine) -> None:
    from alembic import command

    from mtgvault.adapters.db.migrate import alembic_config

    command.downgrade(alembic_config(database_url, BACKEND_DIR), "0001")
    assert not inspect(migrated).has_table("users")
