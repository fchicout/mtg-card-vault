"""Readiness against a real PostgreSQL started by testcontainers (needs Docker)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from testcontainers.community.postgres import PostgresContainer

from mtgvault.adapters.sql_readiness import SqlReadinessProbe
from mtgvault.config import Settings
from mtgvault.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
def postgres() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:17-alpine", driver="psycopg") as container:
        yield container


def test_probe_is_ready_with_a_live_database(postgres: PostgresContainer) -> None:
    engine = create_engine(postgres.get_connection_url())
    assert SqlReadinessProbe(engine).is_ready() is True


def test_api_readyz_follows_the_database_lifecycle(postgres: PostgresContainer) -> None:
    app = create_app(Settings(database_url=postgres.get_connection_url()))
    with TestClient(app) as http:
        assert http.get("/readyz").status_code == 200
        # Stop (not remove) the Docker container: the fixture's `with` block removes it afterwards.
        container = postgres.get_wrapped_container()
        assert container is not None
        container.stop(timeout=1)
        assert http.get("/readyz").status_code == 503
        assert http.get("/healthz").status_code == 200  # liveness never depends on the database


def test_probe_is_not_ready_when_nothing_listens() -> None:
    engine = create_engine(
        "postgresql+psycopg://nobody:nothing@127.0.0.1:1/none",
        connect_args={"connect_timeout": 2},
    )
    assert SqlReadinessProbe(engine).is_ready() is False
