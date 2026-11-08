"""The refresh against real PostgreSQL and the Scryfall double, including a partial failure (#138)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker
from tests.support.fake_cards import make_card
from tests.support.scryfall_double import ScryfallDouble

from mtgvault.adapters.db.unit_of_work import SqlAlchemyUnitOfWork
from mtgvault.adapters.scryfall.client import ScryfallClient
from mtgvault.adapters.scryfall.provider import ScryfallCardProvider
from mtgvault.application.price_refresh import PriceRefresher
from mtgvault.domain.card import Prices
from mtgvault.domain.identity import Principal
from mtgvault.domain.vault import Condition, Finish

pytestmark = pytest.mark.integration
OLD = datetime(2026, 11, 1, 4, 0, tzinfo=UTC)
NOW = datetime(2026, 11, 8, 4, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def double() -> Iterator[ScryfallDouble]:
    d = ScryfallDouble().start()
    yield d
    d.stop()


@pytest.fixture(autouse=True)
def _clean(double: ScryfallDouble) -> None:
    double.reset()


def control(double: ScryfallDouble, **change: object) -> None:
    httpx.post(f"{double.base_url}/__control", json=change).raise_for_status()


def refresher(engine: Engine, double: ScryfallDouble) -> PriceRefresher:
    sessions = sessionmaker(engine, expire_on_commit=False)
    client = ScryfallClient(
        base_url=double.base_url, user_agent="MTGCardVault/0.3 (+https://example.org)",
        min_interval=0.0, max_attempts=1,
    )  # fmt: skip
    return PriceRefresher(
        lambda: SqlAlchemyUnitOfWork(sessions), ScryfallCardProvider(client), lambda: NOW
    )


def own_the_double_cards(engine: Engine, double: ScryfallDouble, count: int) -> list[UUID]:
    """Stale snapshots (price 0.01) of cards the double knows, owned by one user."""
    sessions = sessionmaker(engine, expire_on_commit=False)
    ids = [UUID(i) for i in list(double._cards)[:count]]
    with SqlAlchemyUnitOfWork(sessions) as unit:
        user = unit.users.provision(Principal("owner", "Owner"), OLD, timedelta(hours=1))
        for card_id in ids:
            card = make_card(
                f"Old {card_id}", "tst", str(card_id)[:6], prices=Prices(usd=Decimal("0.01"))
            )
            card = type(card)(**{**card.__dict__, "id": card_id})
            unit.cards.upsert_snapshot(card, OLD)
            unit.vault.add_or_merge(user.id, card_id, 1, Condition.NM, Finish.NONFOIL, OLD)
        unit.commit()
    return ids


def test_prices_and_data_are_refreshed_from_the_source(
    migrated: Engine, double: ScryfallDouble
) -> None:
    ids = own_the_double_cards(migrated, double, 4)
    control(double, prices={str(ids[0]): {"usd": "42.42"}})
    summary = refresher(migrated, double).refresh_all()
    assert summary.refreshed == 4
    assert summary.failed == 0
    with migrated.connect() as connection:
        usd = connection.execute(
            text("SELECT usd FROM cards WHERE scryfall_id = :i"), {"i": ids[0]}
        ).scalar_one()
        names = connection.execute(
            text("SELECT name FROM cards WHERE scryfall_id = :i"), {"i": ids[0]}
        ).scalar_one()
        stamps = (
            connection.execute(text("SELECT DISTINCT prices_updated_at FROM cards")).scalars().all()
        )
    assert usd == Decimal("42.42")
    assert not names.startswith("Old ")
    assert stamps == [NOW]


def test_a_source_outage_leaves_the_stored_prices_untouched(
    migrated: Engine, double: ScryfallDouble
) -> None:
    ids = own_the_double_cards(migrated, double, 3)
    control(double, fail=503)
    summary = refresher(migrated, double).refresh_all()
    assert summary.failed == 3
    assert summary.refreshed == 0
    with migrated.connect() as connection:
        rows = connection.execute(text("SELECT usd, prices_updated_at FROM cards")).all()
    assert {(r[0], r[1]) for r in rows} == {(Decimal("0.01"), OLD)}
    assert len(ids) == len(rows)


def test_a_card_the_source_forgot_keeps_its_stored_data(
    migrated: Engine, double: ScryfallDouble
) -> None:
    sessions = sessionmaker(migrated, expire_on_commit=False)
    ghost = make_card("Ghost", "tst", "1", prices=Prices(usd=Decimal("3.00")))
    with SqlAlchemyUnitOfWork(sessions) as unit:
        user = unit.users.provision(Principal("owner", "Owner"), OLD, timedelta(hours=1))
        unit.cards.upsert_snapshot(ghost, OLD)
        unit.vault.add_or_merge(user.id, ghost.id, 1, Condition.NM, Finish.NONFOIL, OLD)
        unit.commit()
    summary = refresher(migrated, double).refresh_all()
    assert summary.not_found == 1
    assert summary.refreshed == 0
    with migrated.connect() as connection:
        assert connection.execute(text("SELECT usd FROM cards")).scalar_one() == Decimal("3.00")
