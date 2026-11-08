"""The one gateway to Scryfall (FR-DAT-01, Appendix B of the requirements, ADR-007).

* Every request carries a descriptive ``User-Agent`` and ``Accept``; timeouts everywhere.
* Requests start at least ``min_interval`` (100 ms) apart, process-wide: build ONE client.
* Only paths built by the adapter are requested, on the configured host; redirects are not followed.
* 429 and transient failures are retried with exponential backoff and full jitter, honouring
  ``Retry-After``, within a deadline. What remains is translated to the application's errors.
* An optional circuit breaker fails fast during an outage (FR-DAT-03).
"""

from __future__ import annotations

import email.utils
import logging
import random
import re
import threading
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from mtgvault.adapters.resilience import CircuitBreaker
from mtgvault.config import is_acceptable_url
from mtgvault.domain.errors import NotFound, RateLimited, UpstreamUnavailable, ValidationFailed

_log = logging.getLogger("mtgvault.scryfall")
_PATH = re.compile(r"^/[A-Za-z0-9_./-]*$")
_RETRY_STATUS = frozenset({429, 502, 503, 504})


class RequestSpacer:
    """Hands out start times at least ``interval`` seconds apart (thread-safe)."""

    def __init__(
        self,
        interval: float,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._interval = interval
        self._clock = clock
        self._sleeper = sleeper
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            if now < self._next:
                self._sleeper(self._next - now)
                now = self._next
            self._next = now + self._interval


def parse_retry_after(
    value: str | None, now: Callable[[], datetime] = lambda: datetime.now(UTC)
) -> float | None:
    """Seconds from a ``Retry-After`` header (delay or HTTP date); None when absent or unusable."""
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        moment = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return max(0.0, (moment - now()).total_seconds())


class ScryfallClient:
    def __init__(  # explicit keyword configuration reads better than a bag
        self,
        *,
        base_url: str,
        user_agent: str,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        rng: Callable[[], float] = random.random,
        min_interval: float = 0.1,
        timeout: float = 8.0,
        max_attempts: int = 4,
        deadline: float = 20.0,
        base_delay: float = 0.5,
        max_delay: float = 8.0,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        if not is_acceptable_url(base_url):
            raise ValueError("the Scryfall base URL must be https (http only for localhost)")
        self._base = base_url.rstrip("/")
        self._host = urlsplit(self._base).netloc
        self._client = httpx.Client(
            transport=transport,
            timeout=timeout,
            follow_redirects=False,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
        )
        self._clock, self._sleeper, self._rng = clock, sleeper, rng
        self._spacer = RequestSpacer(min_interval, clock, sleeper)
        self._max_attempts, self._deadline = max_attempts, deadline
        self._base_delay, self._max_delay = base_delay, max_delay
        self._breaker = breaker

    # ------------------------------------------------------------------ public
    def get_json(self, path: str, params: Mapping[str, str | int] | None = None) -> dict[str, Any]:
        url = self._url(path)
        if self._breaker:
            self._breaker.allow()
        try:
            document = self._get_with_retries(url, params)
        except (UpstreamUnavailable, RateLimited):
            if self._breaker:
                self._breaker.record_failure()
            raise
        except (NotFound, ValidationFailed):
            if self._breaker:
                self._breaker.record_success()  # the service answered: it is up
            raise
        if self._breaker:
            self._breaker.record_success()
        return document

    # ------------------------------------------------------------------ internals
    def _url(self, path: str) -> str:
        if not _PATH.match(path) or ".." in path or "//" in path:
            raise ValueError(f"not an acceptable Scryfall path: {path!r}")
        url = self._base + path
        if urlsplit(url).netloc != self._host:  # defence in depth
            raise ValueError("the request would leave the configured host")
        return url

    def _get_with_retries(self, url: str, params: Mapping[str, str | int] | None) -> dict[str, Any]:
        started = self._clock()
        retry_hint: float | None = None
        for attempt in range(1, self._max_attempts + 1):
            self._spacer.wait()
            try:
                response = self._client.get(url, params=params)
            except httpx.HTTPError as error:
                _log.warning("scryfall request failed: %s", type(error).__name__)
                status, hint = 0, None
            else:
                status, hint = (
                    response.status_code,
                    parse_retry_after(response.headers.get("Retry-After")),
                )
                if status not in _RETRY_STATUS:
                    return self._interpret(response)
            retry_hint = hint
            if attempt == self._max_attempts:
                break
            delay = hint if hint is not None else self._backoff(attempt)
            if self._clock() - started + delay > self._deadline:
                break
            self._sleeper(delay)
        raise self._final_error(status, retry_hint)

    def _backoff(self, attempt: int) -> float:
        """Exponential backoff with full jitter."""
        return self._rng() * min(self._max_delay, self._base_delay * (1 << (attempt - 1)))

    @staticmethod
    def _final_error(status: int, retry_after: float | None) -> Exception:
        if status == 429:
            seconds = int(retry_after) + 1 if retry_after is not None else None
            return RateLimited(
                "The data source asked us to slow down.", retry_after_seconds=seconds
            )
        return UpstreamUnavailable("The data source is temporarily unavailable.")

    @staticmethod
    def _interpret(response: httpx.Response) -> dict[str, Any]:
        status = response.status_code
        if status == 404:
            raise NotFound("The data source does not know this item.")
        if status in (400, 422):
            raise ValidationFailed("The data source could not understand the request.")
        if status != 200:  # redirects and any other surprise
            raise UpstreamUnavailable("The data source answered unexpectedly.")
        try:
            document = response.json()
        except ValueError as error:
            raise UpstreamUnavailable("The data source sent an unreadable answer.") from error
        if not isinstance(document, dict):
            raise UpstreamUnavailable("The data source sent an unexpected answer.")
        return document
