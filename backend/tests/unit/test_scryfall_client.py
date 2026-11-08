"""Compliance (headers, spacing, allow-list) and resilience (backoff, errors) of the client."""

import threading
import time
from datetime import UTC, datetime
from itertools import pairwise

import httpx
import pytest

from mtgvault.adapters.resilience import CircuitBreaker
from mtgvault.adapters.scryfall.client import RequestSpacer, ScryfallClient, parse_retry_after
from mtgvault.domain.errors import NotFound, RateLimited, UpstreamUnavailable, ValidationFailed

UA = "MTGCardVault/0.3 (+https://example.org/contact)"


class Clock:
    """A fake clock whose sleeper advances it, so backoff and spacing cost no real time."""

    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make(handler, clock: Clock | None = None, **kwargs):  # type: ignore[no-untyped-def]
    clock = clock or Clock()
    client = ScryfallClient(
        base_url="https://api.scryfall.test",
        user_agent=UA,
        transport=httpx.MockTransport(handler),
        clock=clock,
        sleeper=clock.sleep,
        rng=lambda: 1.0,  # full jitter at its maximum: delays are predictable
        **kwargs,
    )
    return client, clock


def ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"object": "list", "data": []})


# ---------------------------------------------------------------------------- compliance
def test_every_request_identifies_us_and_asks_for_json() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return ok(request)

    client, _ = make(handler)
    client.get_json("/cards/search", {"q": "bolt"})
    client.get_json("/cards/abc")
    assert {r.headers["user-agent"] for r in seen} == {UA}
    assert {r.headers["accept"] for r in seen} == {"application/json"}
    assert seen[0].url.params["q"] == "bolt"


def test_requests_start_at_least_100_ms_apart() -> None:
    starts: list[float] = []
    clock = Clock()

    def handler(request: httpx.Request) -> httpx.Response:
        starts.append(clock())
        return ok(request)

    client, _ = make(handler, clock)
    for _ in range(5):
        client.get_json("/cards/x")
    gaps = [b - a for a, b in pairwise(starts)]
    assert all(gap >= 0.1 - 1e-9 for gap in gaps)


def test_spacing_holds_across_threads() -> None:
    starts: list[float] = []
    lock = threading.Lock()
    spacer = RequestSpacer(0.02)

    def worker() -> None:
        spacer.wait()
        with lock:
            starts.append(time.monotonic())

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    starts.sort()
    assert all(b - a >= 0.005 for a, b in pairwise(starts))


@pytest.mark.parametrize(
    "path",
    [
        "https://evil.example/cards",
        "//evil.example/x",
        "/cards/../admin",
        "cards/x",
        "/cards?x=1",
        "/cards/x#y",
        "",
    ],
)
def test_only_plain_paths_on_the_configured_host_are_requested(path: str) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return ok(request)

    client, _ = make(handler)
    with pytest.raises(ValueError, match="acceptable"):
        client.get_json(path)
    assert calls == []


def test_the_base_url_must_be_https_or_loopback() -> None:
    with pytest.raises(ValueError, match="https"):
        ScryfallClient(base_url="http://api.scryfall.example", user_agent=UA)
    ScryfallClient(base_url="http://localhost:9100", user_agent=UA)


# ---------------------------------------------------------------------------- errors
def status_handler(*codes: int):  # type: ignore[no-untyped-def]
    """Answer with the given status codes in turn (the last one repeats)."""
    remaining = list(codes)

    def handler(request: httpx.Request) -> httpx.Response:
        code = remaining.pop(0) if len(remaining) > 1 else remaining[0]
        if code == 200:
            return ok(request)
        return httpx.Response(code, json={"object": "error"})

    return handler


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (404, NotFound),
        (400, ValidationFailed),
        (422, ValidationFailed),
        (500, UpstreamUnavailable),
        (302, UpstreamUnavailable),
    ],
)
def test_statuses_become_application_errors(status: int, error: type[Exception]) -> None:
    client, _ = make(status_handler(status))
    with pytest.raises(error):
        client.get_json("/cards/x")


def test_unreadable_answers_are_upstream_failures() -> None:
    for response in (httpx.Response(200, content=b"not json"), httpx.Response(200, json=[1, 2])):
        client, _ = make(lambda request, r=response: r)
        with pytest.raises(UpstreamUnavailable):
            client.get_json("/cards/x")


# ---------------------------------------------------------------------------- backoff
def test_transient_failures_are_retried_with_exponential_backoff() -> None:
    client, clock = make(status_handler(503, 503, 200))
    assert client.get_json("/cards/x")["object"] == "list"
    # attempts 1 and 2 failed: backoff 0.5 then 1.0 (jitter at maximum), plus 0.1 s spacing
    backoffs = [s for s in clock.sleeps if s >= 0.4]
    assert backoffs == [0.5, 1.0]


def test_the_attempt_limit_ends_in_upstream_unavailable() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503)

    client, _ = make(handler, max_attempts=3)
    with pytest.raises(UpstreamUnavailable):
        client.get_json("/cards/x")
    assert len(calls) == 3


def test_retry_after_is_honoured_for_429() -> None:
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "3"})
        return ok(request)

    client, clock = make(handler)
    client.get_json("/cards/x")
    assert 3.0 in clock.sleeps


def test_a_long_retry_after_beyond_the_deadline_is_reported_not_waited() -> None:
    client, clock = make(
        lambda request: httpx.Response(429, headers={"Retry-After": "120"}), deadline=20.0
    )
    with pytest.raises(RateLimited) as limited:
        client.get_json("/cards/x")
    assert limited.value.retry_after_seconds == 121
    assert 120.0 not in clock.sleeps


def test_network_errors_are_retried_then_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    client, _ = make(handler, max_attempts=2)
    with pytest.raises(UpstreamUnavailable):
        client.get_json("/cards/x")


@pytest.mark.parametrize(
    ("value", "expected"),
    [("5", 5.0), ("0", 0.0), ("-3", 0.0), (None, None), ("", None), ("soon", None)],
)
def test_retry_after_seconds(value: str | None, expected: float | None) -> None:
    assert parse_retry_after(value) == expected


def test_retry_after_as_an_http_date() -> None:
    now = datetime(2026, 11, 8, 12, 0, 0, tzinfo=UTC)
    assert parse_retry_after("Sun, 08 Nov 2026 12:00:30 GMT", now=lambda: now) == 30.0
    assert parse_retry_after("Sun, 08 Nov 2026 11:00:00 GMT", now=lambda: now) == 0.0


# ---------------------------------------------------------------------------- breaker
def test_the_breaker_opens_after_repeated_failures_and_fails_fast() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503)

    clock = Clock()
    breaker = CircuitBreaker("scryfall", failure_threshold=2, open_seconds=30, clock=clock)
    client, _ = make(handler, clock, max_attempts=1, breaker=breaker)
    for _ in range(2):
        with pytest.raises(UpstreamUnavailable):
            client.get_json("/cards/x")
    made = len(calls)
    assert breaker.state == "open"
    with pytest.raises(UpstreamUnavailable):
        client.get_json("/cards/x")
    assert len(calls) == made  # no I/O while open


def test_the_breaker_recovers_through_a_probe() -> None:
    healthy = {"yes": False}

    def handler(request: httpx.Request) -> httpx.Response:
        return ok(request) if healthy["yes"] else httpx.Response(503)

    clock = Clock()
    breaker = CircuitBreaker("scryfall", failure_threshold=1, open_seconds=30, clock=clock)
    client, _ = make(handler, clock, max_attempts=1, breaker=breaker)
    with pytest.raises(UpstreamUnavailable):
        client.get_json("/cards/x")
    clock.now += 31
    assert breaker.state == "half-open"
    healthy["yes"] = True
    client.get_json("/cards/x")
    assert breaker.state == "closed"


def test_a_failed_probe_reopens_the_circuit_and_not_found_counts_as_up() -> None:
    clock = Clock()
    breaker = CircuitBreaker("scryfall", failure_threshold=1, open_seconds=30, clock=clock)
    client, _ = make(status_handler(503), clock, max_attempts=1, breaker=breaker)
    with pytest.raises(UpstreamUnavailable):
        client.get_json("/cards/x")
    clock.now += 31
    with pytest.raises(UpstreamUnavailable):
        client.get_json("/cards/x")  # the probe fails
    assert breaker.state == "open"
    other = CircuitBreaker("x", failure_threshold=1, clock=clock)
    missing, _ = make(status_handler(404), clock, breaker=other)
    for _ in range(3):
        with pytest.raises(NotFound):
            missing.get_json("/cards/x")
    assert other.state == "closed"


def test_only_one_probe_is_let_through_while_half_open() -> None:
    clock = Clock()
    breaker = CircuitBreaker("x", failure_threshold=1, open_seconds=10, clock=clock)
    breaker.allow()
    breaker.record_failure()
    clock.now += 11
    breaker.allow()  # the probe
    with pytest.raises(UpstreamUnavailable):
        breaker.allow()
