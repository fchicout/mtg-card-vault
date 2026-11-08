"""A bounded, thread-safe TTL cache with single-flight loading (ADR-007).

Behind the ``Cache`` port so a shared cache could replace it if the API is ever scaled out.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any


class TtlCache:
    def __init__(
        self,
        ttl_seconds: float,
        max_entries: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._loading: dict[str, threading.Event] = {}

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def get_or_load[T](self, key: str, loader: Callable[[], T]) -> T:
        while True:
            with self._lock:
                hit = self._fresh(key)
                if hit is not None:
                    return hit[0]  # type: ignore[no-any-return]
                waiting = self._loading.get(key)
                if waiting is None:
                    self._loading[key] = threading.Event()
                    break
            waiting.wait()  # another thread is loading this key: wait, then re-check
        try:
            value = loader()
        except BaseException:
            self._finish(key, None)
            raise
        self._finish(key, (value,))
        return value

    def _fresh(self, key: str) -> tuple[Any] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        stored_at, value = entry
        if self._clock() - stored_at >= self._ttl:
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return (value,)

    def _finish(self, key: str, result: tuple[Any] | None) -> None:
        with self._lock:
            if result is not None:
                self._entries[key] = (self._clock(), result[0])
                self._entries.move_to_end(key)
                while len(self._entries) > self._max:
                    self._entries.popitem(last=False)
            self._loading.pop(key).set()
