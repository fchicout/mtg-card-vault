"""A circuit breaker for calls to an unreliable dependency (FR-DAT-03, NFR-REL-01).

After ``failure_threshold`` consecutive failures the circuit opens and calls fail at once, without
I/O. After ``open_seconds`` one probe call is let through (half-open); success closes the circuit,
failure opens it again.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from mtgvault.domain.errors import UpstreamUnavailable

_log = logging.getLogger("mtgvault.resilience")


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        open_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._name = name
        self._threshold = failure_threshold
        self._open_seconds = open_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._failures = 0
        self._opened_at: float | None = None
        self._probing = False

    @property
    def state(self) -> str:
        with self._lock:
            return self._state()

    def _state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if self._clock() - self._opened_at >= self._open_seconds and not self._probing:
            return "half-open"
        return "open"

    def allow(self) -> None:
        """Raise ``UpstreamUnavailable`` unless a call may go through now."""
        with self._lock:
            state = self._state()
            if state == "open":
                raise UpstreamUnavailable("The data source is temporarily unavailable.")
            if state == "half-open":
                self._probing = True  # exactly one probe at a time

    def record_success(self) -> None:
        with self._lock:
            if self._opened_at is not None:
                _log.info("circuit %s closed", self._name)
            self._failures, self._opened_at, self._probing = 0, None, False

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            was_probe = self._probing
            self._probing = False
            if was_probe or self._failures >= self._threshold:
                if self._opened_at is None or was_probe:
                    _log.warning("circuit %s opened after %d failures", self._name, self._failures)
                self._opened_at = self._clock()
