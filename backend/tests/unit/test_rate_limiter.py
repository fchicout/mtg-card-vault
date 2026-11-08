import pytest

from mtgvault.adapters.rate_limit import SlidingWindowRateLimiter
from mtgvault.domain.errors import RateLimited


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_the_thirtieth_is_allowed_and_the_thirty_first_is_refused_with_a_wait() -> None:
    clock = Clock()
    limiter = SlidingWindowRateLimiter(30, 60, clock)
    for _ in range(30):
        limiter.check("alice")
        clock.now += 0.5  # 15 s for the burst
    with pytest.raises(RateLimited) as refused:
        limiter.check("alice")
    assert refused.value.retry_after_seconds == 45  # until the first hit leaves the window


def test_the_window_slides_and_service_resumes() -> None:
    clock = Clock()
    limiter = SlidingWindowRateLimiter(2, 60, clock)
    limiter.check("a")
    limiter.check("a")
    with pytest.raises(RateLimited):
        limiter.check("a")
    clock.now += 60
    limiter.check("a")


def test_users_are_independent() -> None:
    limiter = SlidingWindowRateLimiter(1, 60, Clock())
    limiter.check("alice")
    limiter.check("bob")
    with pytest.raises(RateLimited):
        limiter.check("alice")


def test_idle_users_are_forgotten() -> None:
    clock = Clock()
    limiter = SlidingWindowRateLimiter(5, 60, clock)
    for index in range(1023):
        limiter.check(f"user-{index}")
    clock.now += 120
    limiter.check("someone-new")  # the 1024th check sweeps
    assert len(limiter._hits) <= 2  # only recent users remain
