import threading

import pytest

from mtgvault.adapters.cache import TtlCache


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_values_are_cached_until_the_ttl() -> None:
    clock = Clock()
    cache = TtlCache(300, 10, clock)
    calls = []

    def load() -> int:
        calls.append(1)
        return len(calls)

    assert cache.get_or_load("k", load) == 1
    clock.now = 299.9
    assert cache.get_or_load("k", load) == 1
    clock.now = 300.0
    assert cache.get_or_load("k", load) == 2
    assert len(calls) == 2


def test_the_least_recently_used_entry_is_evicted_at_capacity() -> None:
    cache = TtlCache(300, 2, Clock())
    cache.get_or_load("a", lambda: 1)
    cache.get_or_load("b", lambda: 2)
    cache.get_or_load("a", lambda: 99)  # a is now the most recent
    cache.get_or_load("c", lambda: 3)  # evicts b
    assert len(cache) == 2
    assert cache.get_or_load("a", lambda: -1) == 1
    assert cache.get_or_load("b", lambda: -2) == -2


def test_a_failing_loader_stores_nothing_and_releases_waiters() -> None:
    cache = TtlCache(300, 10, Clock())

    def broken() -> int:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        cache.get_or_load("k", broken)
    assert cache.get_or_load("k", lambda: 7) == 7


def test_concurrent_identical_misses_share_one_load() -> None:
    cache = TtlCache(300, 10, Clock())
    started = threading.Event()
    release = threading.Event()
    calls = []

    def slow() -> str:
        calls.append(1)
        started.set()
        release.wait(2)
        return "value"

    results: list[str] = []
    threads = [
        threading.Thread(target=lambda: results.append(cache.get_or_load("k", slow)))
        for _ in range(10)
    ]
    for t in threads:
        t.start()
    started.wait(2)
    release.set()
    for t in threads:
        t.join()
    assert results == ["value"] * 10
    assert len(calls) == 1


def test_different_keys_load_independently() -> None:
    cache = TtlCache(300, 10, Clock())
    assert cache.get_or_load("a", lambda: 1) == 1
    assert cache.get_or_load("b", lambda: 2) == 2
