"""NFR-PRF-01: a page of a 10,000-entry vault in under 300 ms (p95), with the index in use."""

import statistics
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from mtgvault.adapters.db.unit_of_work import SqlAlchemyUnitOfWork
from mtgvault.application.vault_query import build_vault_query
from mtgvault.domain.identity import Principal

pytestmark = pytest.mark.integration
ROWS = 10_000
BUDGET_SECONDS = 0.300


def seed(engine: Engine) -> object:
    now = datetime(2026, 11, 8, tzinfo=UTC)
    with SqlAlchemyUnitOfWork(sessionmaker(engine, expire_on_commit=False)) as unit:
        user = unit.users.provision(Principal("bench", "Bench"), now, timedelta(hours=1))
        unit.commit()
    with engine.begin() as connection:
        cards = [
            {"id": uuid4(), "name": f"Card {i:05d}", "now": now, "n": i % 50, "i": str(i)}
            for i in range(ROWS)
        ]
        connection.execute(
            text(
                "INSERT INTO cards (scryfall_id, name, name_search, set_code, set_name, collector_number,"
                " lang, rarity, layout, colors, finishes, usd, data_updated_at) VALUES"
                " (:id, :name, lower(:name), 'set' || :n, 'Set', :i, 'en', 'common', 'normal',"
                " ARRAY['R'], ARRAY['nonfoil'], 1.00, :now)"
            ),
            cards,
        )
        connection.execute(
            text(
                "INSERT INTO vault_entries (id, user_id, card_id, quantity, condition, finish, created_at)"
                " VALUES (:eid, :u, :id, 1, 'NM', 'nonfoil', :now)"
            ),
            [
                {"eid": uuid4(), "u": user.id, "id": c["id"], "now": now + timedelta(seconds=k)}
                for k, c in enumerate(cards)
            ],
        )
    return user.id


def test_listing_a_page_over_ten_thousand_entries_meets_the_budget(migrated: Engine) -> None:
    user_id = seed(migrated)
    factory = sessionmaker(migrated, expire_on_commit=False)
    timings: list[float] = []
    for page in range(1, 41):
        started = time.perf_counter()
        with SqlAlchemyUnitOfWork(factory) as unit:
            items, total = unit.vault.list_items(
                user_id, build_vault_query(page=page % 5 + 1, page_size=50)
            )  # type: ignore[arg-type]
        timings.append(time.perf_counter() - started)
        assert len(items) == 50
        assert total == ROWS
    timings.sort()
    p95 = timings[int(len(timings) * 0.95) - 1]
    print(f"vault list p50={statistics.median(timings) * 1000:.1f} ms p95={p95 * 1000:.1f} ms")
    assert p95 < BUDGET_SECONDS


def test_the_default_listing_can_use_the_user_created_index(migrated: Engine) -> None:
    user_id = seed(migrated)
    with migrated.connect() as connection:
        connection.execute(text("ANALYZE vault_entries"))
        plan = "\n".join(
            row[0]
            for row in connection.execute(
                text(
                    "EXPLAIN SELECT * FROM vault_entries WHERE user_id = :u"
                    " ORDER BY created_at DESC LIMIT 50"
                ),
                {"u": user_id},
            )
        )
    assert "ix_vault_entries_user_created" in plan, plan
