"""FR-OPS-03 / NFR-REL-02: migrations, isolation and the unit of work on real PostgreSQL."""

import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from mtgvault.adapters.db.migrate import alembic_config, upgrade_to_head
from mtgvault.adapters.db.unit_of_work import SqlAlchemyUnitOfWork

BACKEND_DIR = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration
# The newest revision of the chain, read from the scripts: a new migration needs no edit here.
HEAD = ScriptDirectory.from_config(
    alembic_config("postgresql://x/x", BACKEND_DIR)
).get_current_head()


def versions(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        if not inspect(connection).has_table("alembic_version"):
            return []
        return [
            row[0] for row in connection.execute(text("SELECT version_num FROM alembic_version"))
        ]


def test_upgrade_then_downgrade_round_trip(database_url: str, engine: Engine) -> None:
    config = alembic_config(database_url, BACKEND_DIR)
    command.upgrade(config, "head")
    assert versions(engine) == [HEAD]
    command.downgrade(config, "base")
    assert versions(engine) == []
    command.upgrade(config, "head")  # and up again: the chain is repeatable
    assert versions(engine) == [HEAD]


def test_upgrade_to_head_is_idempotent(database_url: str, engine: Engine) -> None:
    upgrade_to_head(database_url, BACKEND_DIR)
    upgrade_to_head(database_url, BACKEND_DIR)
    assert versions(engine) == [HEAD]


def test_changes_in_db_session_are_rolled_back_between_tests(
    engine: Engine, db_session: Session
) -> None:
    db_session.execute(text("CREATE TABLE scratch (id int)"))
    db_session.execute(text("INSERT INTO scratch VALUES (1)"))
    assert db_session.execute(text("SELECT count(*) FROM scratch")).scalar_one() == 1
    db_session.close()
    # The outer transaction is still open, so the table is invisible to other connections.
    assert not inspect(engine).has_table("scratch")


def test_each_test_gets_an_empty_database(engine: Engine) -> None:
    assert inspect(engine).get_table_names() == []


def test_unit_of_work_commit_and_rollback_on_postgres(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE item (name text)"))
    factory = sessionmaker(engine, expire_on_commit=False)

    with SqlAlchemyUnitOfWork(factory) as uow:
        uow.session.execute(text("INSERT INTO item VALUES ('kept')"))
        uow.commit()
    with SqlAlchemyUnitOfWork(factory) as uow:
        uow.session.execute(text("INSERT INTO item VALUES ('discarded')"))

    with engine.connect() as connection:
        assert [r[0] for r in connection.execute(text("SELECT name FROM item"))] == ["kept"]


def test_concurrent_migrations_do_not_race(database_url: str, engine: Engine) -> None:
    """Several API processes starting together: the advisory lock serialises their migrations."""
    code = (
        "import sys; from pathlib import Path; "
        "from mtgvault.adapters.db.migrate import upgrade_to_head; "
        "upgrade_to_head(sys.argv[1], Path(sys.argv[2]))"
    )
    processes = [
        subprocess.Popen(  # noqa: S603  # fixed interpreter and arguments under test control
            [sys.executable, "-c", code, database_url, str(BACKEND_DIR)],
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(4)
    ]
    results = [(p.wait(timeout=120), p.stderr.read() if p.stderr else "") for p in processes]
    assert [code for code, _ in results] == [0, 0, 0, 0], results
    assert versions(engine) == [HEAD]


def test_api_container_entry_uses_the_real_engine(database_url: str) -> None:
    upgrade_to_head(database_url, BACKEND_DIR)
    engine = create_engine(database_url)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1
    engine.dispose()
