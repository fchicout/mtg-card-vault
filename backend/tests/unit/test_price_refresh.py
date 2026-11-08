"""The refresh of prices with fakes only (issue #138, US-022, FR-PRC-04)."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Self
from uuid import UUID, uuid4

from tests.support.fake_cards import FakeCardProvider, make_card

from mtgvault.application.price_refresh import (
    ABORT_AFTER_FAILED_BATCHES,
    BATCH_SIZE,
    PriceRefresher,
)
from mtgvault.domain.card import Card, LookupResult, Prices
from mtgvault.domain.errors import RateLimited, UpstreamUnavailable

NOW = datetime(2026, 11, 8, 4, 0, tzinfo=UTC)


class Store:
    """The shared state behind the fake unit of work: stored prices and the owned ids."""

    def __init__(self) -> None:
        self.prices: dict[UUID, Prices] = {}
        self.stamps: dict[UUID, datetime] = {}
        self.owned: list[UUID] = []
        self.commits = 0
        self.fail_commit_on: int | None = None


class FakeCards:
    def __init__(self, store: Store, pending: dict[UUID, Prices]) -> None:
        self.store, self.pending = store, pending

    def owned_ids(self, after: UUID | None, limit: int) -> list[UUID]:
        ids = sorted(self.store.owned)
        return [i for i in ids if after is None or i > after][:limit]

    def prices_of(self, card_ids: list[UUID]) -> dict[UUID, Prices]:
        return {i: self.store.prices[i] for i in card_ids if i in self.store.prices}

    def upsert_snapshots(self, cards: tuple[Card, ...], now: datetime) -> None:
        for card in cards:
            self.pending[card.id] = card.prices
            self.store.stamps[card.id] = now


class FakeUnit:
    def __init__(self, store: Store) -> None:
        self.store, self.pending = store, {}
        self.cards = FakeCards(store, self.pending)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def commit(self) -> None:
        self.store.commits += 1
        if self.store.fail_commit_on == self.store.commits:
            raise UpstreamUnavailable("db")
        self.store.prices.update(self.pending)


def build(n: int, price: str = "1.00", **provider_kwargs: object):  # type: ignore[no-untyped-def]
    cards = [
        make_card(f"Card {i}", "tst", str(i), prices=Prices(usd=Decimal(price))) for i in range(n)
    ]
    store = Store()
    store.owned = [c.id for c in cards]
    store.prices = {c.id: Prices(usd=Decimal("1.00")) for c in cards}
    provider = FakeCardProvider(list(cards))
    refresher = PriceRefresher(lambda: FakeUnit(store), provider, lambda: NOW, timer=lambda: 0.0)
    return cards, store, provider, refresher


def test_unchanged_updated_and_not_found_are_counted() -> None:
    cards, store, provider, refresher = build(4)
    provider.cards[0] = make_card("Card 0", "tst", "0", prices=Prices(usd=Decimal("2.00")))
    provider.cards.pop()  # the source no longer knows the last one
    summary = refresher.refresh_all()
    assert (summary.updated, summary.unchanged, summary.not_found, summary.failed) == (1, 2, 1, 0)
    assert store.prices[cards[0].id].usd == Decimal("2.00")
    assert store.prices[cards[3].id].usd == Decimal("1.00")  # kept as it was
    assert cards[3].id not in store.stamps


def test_batches_never_exceed_75_and_each_is_committed_on_its_own() -> None:
    _, store, provider, refresher = build(160)
    summary = refresher.refresh_all()
    assert [len(c) for c in provider.lookup_calls] == [75, 75, 10]
    assert BATCH_SIZE == 75 and summary.batches == 3
    assert store.commits == 3 and summary.refreshed == 160


def test_a_failed_batch_does_not_stop_the_others_and_keeps_what_is_stored() -> None:
    cards, store, provider, refresher = build(160, price="5.00")
    calls = iter(range(3))
    original = provider.lookup

    def flaky(ids):  # type: ignore[no-untyped-def]
        if next(calls) == 1:
            raise RateLimited("slow down")
        return original(ids)

    provider.lookup = flaky  # type: ignore[method-assign]
    summary = refresher.refresh_all()
    assert (summary.failed, summary.refreshed, summary.aborted) == (75, 85, False)
    ordered = sorted(c.id for c in cards)
    assert store.prices[ordered[0]].usd == Decimal("5.00")  # batch 1 committed
    assert store.prices[ordered[80]].usd == Decimal("1.00")  # batch 2 failed: unchanged
    assert store.prices[ordered[150]].usd == Decimal("5.00")  # batch 3 committed after the failure


def test_an_outage_ends_the_run_after_a_few_failed_batches() -> None:
    _, _, provider, refresher = build(75 * 6)
    provider.fail = True
    summary = refresher.refresh_all()
    assert summary.aborted and summary.batches == ABORT_AFTER_FAILED_BATCHES
    assert summary.failed == 75 * ABORT_AFTER_FAILED_BATCHES and summary.refreshed == 0


def test_a_success_resets_the_failure_streak() -> None:
    _, _, provider, refresher = build(75 * 6)
    original = provider.lookup
    script = iter([True, True, False, True, True, False])

    def sometimes(ids):  # type: ignore[no-untyped-def]
        if next(script):
            raise UpstreamUnavailable("blip")
        return original(ids)

    provider.lookup = sometimes  # type: ignore[method-assign]
    summary = refresher.refresh_all()
    assert not summary.aborted and summary.batches == 6 and summary.failed == 75 * 4


def test_a_storage_failure_counts_the_batch_as_failed_and_the_run_goes_on() -> None:
    _, store, _, refresher = build(150)
    store.fail_commit_on = 1
    summary = refresher.refresh_all()
    assert (summary.failed, summary.refreshed) == (75, 75)


def test_the_run_stops_between_batches_when_asked() -> None:
    _, _, provider, refresher = build(300)
    stops = iter([False, False, True])
    summary = refresher.refresh_all(should_stop=lambda: next(stops))
    assert summary.batches == 2 and len(provider.lookup_calls) == 2


def test_refreshing_given_ids_deduplicates_and_batches() -> None:
    cards, _, provider, refresher = build(80)
    ids = [c.id for c in cards] + [cards[0].id, uuid4()]
    summary = refresher.refresh(ids)
    assert [len(c) for c in provider.lookup_calls] == [75, 6]
    assert summary.not_found == 1 and summary.refreshed == 80


def test_nothing_owned_is_an_empty_successful_run() -> None:
    _, _, provider, refresher = build(0)
    summary = refresher.refresh_all()
    assert summary.batches == 0 and provider.lookup_calls == [] and not summary.aborted
    assert LookupResult((), ()).cards == ()
