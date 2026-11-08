"""Batch lookup through POST /cards/collection (issue #135, FR-PRC-04, FR-DAT-01)."""

from collections.abc import Iterator
from itertools import pairwise
from uuid import UUID, uuid4

import httpx
import pytest
from tests.support.scryfall_double import MAX_COLLECTION, ScryfallDouble

from mtgvault.adapters.resilience import CircuitBreaker
from mtgvault.adapters.scryfall.client import ScryfallClient
from mtgvault.adapters.scryfall.provider import BATCH_SIZE, ScryfallCardProvider
from mtgvault.domain.errors import RateLimited, UpstreamUnavailable

UA = "MTGCardVault/0.3 (+https://example.org/contact)"


@pytest.fixture(scope="module")
def double() -> Iterator[ScryfallDouble]:
    d = ScryfallDouble().start()
    yield d
    d.stop()


@pytest.fixture(autouse=True)
def _clean(double: ScryfallDouble) -> None:
    double.reset()


def provider(double: ScryfallDouble, **kwargs: object) -> ScryfallCardProvider:
    client = ScryfallClient(
        base_url=double.base_url, user_agent=UA, min_interval=0.05, base_delay=0.01,
        max_delay=0.02, **kwargs,
    )  # type: ignore[arg-type]  # fmt: skip
    return ScryfallCardProvider(client)


def collection_log(double: ScryfallDouble) -> list[dict[str, object]]:
    return [r for r in double.requests if r["path"] == "/cards/collection"]


def control(double: ScryfallDouble, **change: object) -> None:
    httpx.post(f"{double.base_url}/__control", json=change).raise_for_status()


def test_the_batch_size_is_what_the_service_accepts() -> None:
    assert BATCH_SIZE == MAX_COLLECTION == 75


def test_known_cards_are_mapped_and_unknown_ids_are_reported(double: ScryfallDouble) -> None:
    known = [UUID(i) for i in list(double._cards)[:3]]
    unknown = uuid4()
    result = provider(double).lookup([*known, unknown])
    assert {c.id for c in result.cards} == set(known)
    assert result.not_found == (unknown,)
    assert all(c.name for c in result.cards)


@pytest.mark.parametrize(
    ("count", "requests"),
    [(0, []), (1, [1]), (74, [74]), (75, [75]), (76, [75, 1]), (151, [75, 75, 1])],
)
def test_never_more_than_75_identifiers_per_request(
    double: ScryfallDouble, count: int, requests: list[int]
) -> None:
    result = provider(double).lookup([uuid4() for _ in range(count)])
    assert len(result.not_found) == count
    assert result.cards == ()
    assert [r["identifiers"] for r in collection_log(double)] == requests


def test_requests_carry_the_headers_and_stay_spaced(double: ScryfallDouble) -> None:
    provider(double).lookup([uuid4() for _ in range(160)])
    log = collection_log(double)
    assert {r["method"] for r in log} == {"POST"}
    assert {r["user_agent"] for r in log} == {UA}
    assert {r["accept"] for r in log} == {"application/json"}
    assert all(b["at"] - a["at"] >= 0.04 for a, b in pairwise(log))  # type: ignore[operator]


def test_a_throttled_post_is_retried_with_the_same_body() -> None:
    bodies: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        if len(bodies) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"object": "list", "data": [], "not_found": []})

    client = ScryfallClient(
        base_url="https://api.example.org", user_agent=UA, transport=httpx.MockTransport(handler),
        min_interval=0.0, base_delay=0.0, max_delay=0.0, sleeper=lambda _: None,
    )  # fmt: skip
    ScryfallCardProvider(client).lookup([uuid4()])
    assert len(bodies) == 2
    assert bodies[0] == bodies[1]


def test_throttling_and_outages_surface_as_typed_errors(double: ScryfallDouble) -> None:
    source = provider(double, max_attempts=2)
    control(double, fail=429, retry_after=0)
    with pytest.raises(RateLimited):
        source.lookup([uuid4()])
    control(double, fail=503)
    with pytest.raises(UpstreamUnavailable):
        source.lookup([uuid4()])
    control(double, fail=0, garbage=True)
    with pytest.raises(UpstreamUnavailable):
        source.lookup([uuid4()])


def test_an_answer_of_the_wrong_shape_is_an_upstream_error(double: ScryfallDouble) -> None:
    class Odd(ScryfallClient):
        def post_json(self, path, body):  # type: ignore[no-untyped-def]
            return {"object": "list", "data": [{"id": "not-a-card"}], "not_found": []}

    source = ScryfallCardProvider(Odd(base_url=double.base_url, user_agent=UA))
    ids = [uuid4()]
    with pytest.raises(UpstreamUnavailable):
        source.lookup(ids)


def test_the_breaker_opens_during_an_outage(double: ScryfallDouble) -> None:
    clock = [0.0]
    breaker = CircuitBreaker(
        "scryfall", failure_threshold=2, open_seconds=5, clock=lambda: clock[0]
    )
    source = provider(double, max_attempts=1, breaker=breaker)
    control(double, fail=503)
    for _ in range(2):
        with pytest.raises(UpstreamUnavailable):
            source.lookup([uuid4()])
    sent = len(collection_log(double))
    with pytest.raises(UpstreamUnavailable):
        source.lookup([uuid4()])
    assert len(collection_log(double)) == sent  # failed fast, nothing was sent


def test_the_double_refuses_more_than_75_and_serves_changed_prices(double: ScryfallDouble) -> None:
    too_many = [{"id": str(uuid4())} for _ in range(MAX_COLLECTION + 1)]
    response = httpx.post(f"{double.base_url}/cards/collection", json={"identifiers": too_many})
    assert response.status_code == 422
    card_id = next(iter(double._cards))
    control(double, prices={card_id: {"usd": "123.45", "eur": None}})
    card = provider(double).lookup([UUID(card_id)]).cards[0]
    assert str(card.prices.usd) == "123.45"
    assert card.prices.eur is None
    control(double, reset=True)
    assert str(provider(double).lookup([UUID(card_id)]).cards[0].prices.usd) != "123.45"
