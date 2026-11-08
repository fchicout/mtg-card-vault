"""Stale prices are refreshed once, after the response, and never break anything (US-023)."""

import threading
import time
from collections.abc import Sequence
from uuid import UUID, uuid4

from mtgvault.application.lazy_refresh import MAX_PER_REQUEST, InFlight, LazyPriceRefresher
from mtgvault.application.price_refresh import RefreshSummary


class Slow:
    """A refresher that takes a while, like a real batch, and records what it was asked."""

    def __init__(self, seconds: float = 0.2, error: Exception | None = None) -> None:
        self.seconds, self.error = seconds, error
        self.calls: list[list[UUID]] = []
        self._lock = threading.Lock()

    def refresh(self, card_ids: Sequence[UUID]) -> RefreshSummary:
        with self._lock:
            self.calls.append(list(card_ids))
        time.sleep(self.seconds)
        if self.error:
            raise self.error
        return RefreshSummary(updated=len(card_ids))


def test_claiming_hands_out_each_id_once_until_it_is_released() -> None:
    guard, a, b = InFlight(), uuid4(), uuid4()
    assert guard.claim([a, a, b]) == [a, b]
    assert guard.claim([a, b]) == []
    guard.release([a])
    assert guard.claim([a, b]) == [a]
    assert len(guard) == 2


def test_fifty_concurrent_requests_for_one_stale_card_start_one_refresh() -> None:
    refresher, card = Slow(), uuid4()
    lazy = LazyPriceRefresher(refresher)
    start = threading.Barrier(50)
    results: list[object] = []

    def request() -> None:
        start.wait()
        results.append(lazy.refresh_now([card]))

    threads = [threading.Thread(target=request) for _ in range(50)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert refresher.calls == [[card]]
    assert sum(r is not None for r in results) == 1


def test_overlapping_requests_share_the_work_without_repeating_a_card() -> None:
    refresher, a, b, c = Slow(0.3), uuid4(), uuid4(), uuid4()
    lazy = LazyPriceRefresher(refresher)
    first = threading.Thread(target=lazy.refresh_now, args=([a, b],))
    first.start()
    time.sleep(0.05)
    lazy.refresh_now([b, c])  # b is already in flight
    first.join()
    assert sorted(map(str, [i for call in refresher.calls for i in call])) == sorted(
        map(str, [a, b, c])
    )


def test_a_failing_refresh_releases_its_cards_and_does_not_raise() -> None:
    refresher, card = Slow(0.0, RuntimeError("boom")), uuid4()
    guard = InFlight()
    lazy = LazyPriceRefresher(refresher, guard)
    assert lazy.refresh_now([card]) is None
    assert len(guard) == 0
    refresher.error = None
    assert lazy.refresh_now([card]) is not None  # the next request can try again


def test_one_request_refreshes_at_most_one_batch() -> None:
    refresher = Slow(0.0)
    LazyPriceRefresher(refresher).refresh_now([uuid4() for _ in range(MAX_PER_REQUEST + 30)])
    assert [len(c) for c in refresher.calls] == [MAX_PER_REQUEST]
