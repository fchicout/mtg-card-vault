"""An in-memory sliding-window rate limiter (FR-SCN-08), behind the ``RateLimiter`` port.

One process only: if the API is ever scaled out, a shared implementation replaces this one.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Callable

from mtgvault.domain.errors import RateLimited

_PRUNE_EVERY = 1024  # checks between sweeps that forget users who have gone quiet


class SlidingWindowRateLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}
        self._checks = 0

    def check(self, key: str) -> None:
        """Count one use for ``key``; raises ``RateLimited`` (with the wait) over the limit."""
        now = self._clock()
        with self._lock:
            self._checks += 1
            if self._checks % _PRUNE_EVERY == 0:
                self._prune(now)
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self._window:
                hits.popleft()
            if len(hits) >= self._limit:
                wait = max(1, math.ceil(self._window - (now - hits[0])))
                raise RateLimited("Too many scans; wait a moment.", retry_after_seconds=wait)
            hits.append(now)

    def _prune(self, now: float) -> None:
        for key in [k for k, h in self._hits.items() if not h or now - h[-1] >= self._window]:
            del self._hits[key]
