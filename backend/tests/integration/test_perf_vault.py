"""Performance budgets at 10,000 entries (issue #134, NFR-PRF-01, FR-PRC-03).

Run on demand and nightly with ``uv run pytest -m perf``; not part of the pull request run. The
numbers are server-side (repository calls on PostgreSQL), without network, on whatever machine
runs them: the CI runner is slower than the reference deployment, which is why the budget is the
documented one and failures there deserve a look rather than a retry.
"""

import math
import os
import statistics
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from mtgvault.adapters.db.unit_of_work import SqlAlchemyUnitOfWork
from mtgvault.application.vault_query import build_vault_query
from mtgvault.domain.identity import Principal

pytestmark = [pytest.mark.integration, pytest.mark.perf]

BUDGET_MS = float(os.environ.get("PERF_BUDGET_MS", "300"))
ENTRIES = 10_000
CONDITIONS = ("NM", "LP", "MP", "HP")
REPEATS = 40
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def over_budget(samples: list[float], budget_ms: float) -> bool:
    return p95(samples) * 1000 > budget_ms


def measure(action: Callable[[], object]) -> list[float]:
    action()  # warm-up: plans and caches
    samples = []
    for _ in range(REPEATS):
        started = time.perf_counter()
        action()
        samples.append(time.perf_counter() - started)
    return samples


@pytest.fixture
def big_vault(migrated: Engine) -> UUID:
    sessions = sessionmaker(migrated, expire_on_commit=False)
    with SqlAlchemyUnitOfWork(sessions) as unit:
        user = unit.users.provision(Principal("big", "Big Collector"), NOW, timedelta(hours=1))
        unit.commit()
    with migrated.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO cards (scryfall_id, oracle_id, name, name_search, set_code, set_name,
                    collector_number, lang, rarity, layout, type_line, colors, finishes, usd,
                    usd_foil, eur, prices_updated_at, data_updated_at)
                SELECT gen_random_uuid(), gen_random_uuid(), 'Card ' || n, 'card ' || n,
                    'set' || (n % 50), 'Set', n::text, 'en',
                    (ARRAY['common','uncommon','rare','mythic'])[1 + n % 4], 'normal', 'Creature',
                    ARRAY['R'], ARRAY['nonfoil','foil'], (n % 500) / 10.0,
                    CASE WHEN n % 7 = 0 THEN NULL ELSE (n % 900) / 10.0 END,
                    CASE WHEN n % 5 = 0 THEN NULL ELSE (n % 400) / 10.0 END, :now, :now
                FROM generate_series(1, :cards) AS n
                """
            ),
            {"cards": ENTRIES // len(CONDITIONS), "now": NOW},
        )
        connection.execute(
            text(
                """
                INSERT INTO vault_entries (id, user_id, card_id, quantity, condition, finish,
                    created_at, updated_at)
                SELECT gen_random_uuid(), :user, c.scryfall_id, 1 + (random() * 9)::int, k.cond,
                    'nonfoil', :now + (row_number() OVER ())::int * interval '1 second', :now
                FROM cards c CROSS JOIN unnest(CAST(:conditions AS text[])) AS k(cond)
                """
            ),
            {"user": user.id, "now": NOW, "conditions": list(CONDITIONS)},
        )
        connection.execute(text("ANALYZE"))
    return user.id


def budget(samples: list[float], what: str) -> None:
    value = p95(samples) * 1000
    print(f"PERF {what}: p50={statistics.median(samples) * 1000:.1f} ms p95={value:.1f} ms")
    assert not over_budget(samples, BUDGET_MS), f"{what}: p95 {value:.1f} ms > {BUDGET_MS} ms"


def listing(migrated: Engine, user: UUID, **query: object) -> Callable[[], object]:
    sessions = sessionmaker(migrated, expire_on_commit=False)

    def run() -> object:
        with SqlAlchemyUnitOfWork(sessions) as unit:
            return unit.vault.list_items(user, build_vault_query(**query))  # type: ignore[arg-type]

    return run


def test_the_vault_has_ten_thousand_entries(migrated: Engine, big_vault: UUID) -> None:
    with migrated.connect() as connection:
        count = connection.execute(text("SELECT count(*) FROM vault_entries")).scalar_one()
    assert count == ENTRIES


def test_a_page_of_the_list_meets_the_budget(migrated: Engine, big_vault: UUID) -> None:
    budget(measure(listing(migrated, big_vault, page=3, page_size=50)), "list newest first")
    budget(
        measure(listing(migrated, big_vault, page=3, sort="price", direction="desc")),
        "list by price",
    )
    budget(measure(listing(migrated, big_vault, q="card 12", sort="name")), "list filtered by name")
    budget(
        measure(listing(migrated, big_vault, rarity="rare", colors="R", sort="set")),
        "list with filters",
    )


def test_the_summary_meets_the_budget(migrated: Engine, big_vault: UUID) -> None:
    sessions = sessionmaker(migrated, expire_on_commit=False)

    def run() -> object:
        with SqlAlchemyUnitOfWork(sessions) as unit:
            return unit.vault.summary(big_vault)

    budget(measure(run), "summary")


def test_looking_for_stale_cards_meets_the_budget(migrated: Engine, big_vault: UUID) -> None:
    sessions = sessionmaker(migrated, expire_on_commit=False)

    def run() -> object:
        with SqlAlchemyUnitOfWork(sessions) as unit:
            return unit.vault.stale_card_ids(big_vault, NOW + timedelta(days=1), 75)

    budget(measure(run), "stale card ids")


def test_the_budget_check_itself_flags_a_slow_series() -> None:
    assert over_budget([0.4] * 20, 300)
    assert not over_budget([0.1] * 19 + [0.9], 300)  # one outlier in twenty is not the p95
    assert over_budget([0.1] * 10 + [0.5] * 10, 300)
