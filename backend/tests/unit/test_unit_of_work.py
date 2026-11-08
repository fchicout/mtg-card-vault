"""Unit of work semantics, checked on in-memory SQLite (no server needed)."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from mtgvault.adapters.db.base import NAMING_CONVENTION, Base
from mtgvault.adapters.db.unit_of_work import SqlAlchemyUnitOfWork
from mtgvault.api.dependencies import get_unit_of_work
from mtgvault.application.ports import UnitOfWork


@pytest.fixture
def factory():  # type: ignore[no-untyped-def]  # fixture returning a sessionmaker
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE item (name TEXT)"))
    return sessionmaker(engine, expire_on_commit=False)


def count(factory) -> int:  # type: ignore[no-untyped-def]
    with factory() as session:
        return int(session.execute(text("SELECT count(*) FROM item")).scalar_one())


def test_commit_persists(factory) -> None:  # type: ignore[no-untyped-def]
    with SqlAlchemyUnitOfWork(factory) as uow:
        uow.session.execute(text("INSERT INTO item VALUES ('a')"))
        uow.commit()
    assert count(factory) == 1


def test_leaving_without_commit_rolls_back(factory) -> None:  # type: ignore[no-untyped-def]
    with SqlAlchemyUnitOfWork(factory) as uow:
        uow.session.execute(text("INSERT INTO item VALUES ('a')"))
    assert count(factory) == 0


def test_an_exception_rolls_back_even_after_work(factory) -> None:  # type: ignore[no-untyped-def]
    def work_then_fail() -> None:
        with SqlAlchemyUnitOfWork(factory) as uow:
            uow.session.execute(text("INSERT INTO item VALUES ('a')"))
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        work_then_fail()
    assert count(factory) == 0


def test_explicit_rollback_discards_pending_work(factory) -> None:  # type: ignore[no-untyped-def]
    with SqlAlchemyUnitOfWork(factory) as uow:
        uow.session.execute(text("INSERT INTO item VALUES ('a')"))
        uow.rollback()
        uow.commit()
    assert count(factory) == 0


def test_the_session_is_only_available_inside_the_block(factory) -> None:  # type: ignore[no-untyped-def]
    uow = SqlAlchemyUnitOfWork(factory)
    with pytest.raises(RuntimeError, match="not active"):
        _ = uow.session
    with uow:
        assert uow.session is not None
    with pytest.raises(RuntimeError, match="not active"):
        _ = uow.session


def test_the_adapter_satisfies_the_port(factory) -> None:  # type: ignore[no-untyped-def]
    uow: UnitOfWork = SqlAlchemyUnitOfWork(factory)
    with uow:
        uow.commit()


def test_constraint_names_are_deterministic() -> None:
    assert set(NAMING_CONVENTION) == {"ix", "uq", "ck", "fk", "pk"}
    assert Base.metadata.naming_convention == NAMING_CONVENTION


def test_the_request_dependency_gives_one_unit_of_work_per_request(factory) -> None:  # type: ignore[no-untyped-def]
    app = FastAPI()
    app.state.unit_of_work_factory = lambda: SqlAlchemyUnitOfWork(factory)
    seen: list[UnitOfWork] = []

    @app.get("/probe")
    def probe(uow: UnitOfWork = Depends(get_unit_of_work)) -> dict[str, bool]:  # noqa: B008
        seen.append(uow)
        return {"ok": True}

    client = TestClient(app)
    client.get("/probe")
    client.get("/probe")
    assert len(seen) == 2
    assert seen[0] is not seen[1]
