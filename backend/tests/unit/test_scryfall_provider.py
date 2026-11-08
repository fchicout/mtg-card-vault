"""The Scryfall adapter against recorded responses, over real HTTP (issues #74-#79)."""

from collections.abc import Iterator
from itertools import pairwise
from uuid import UUID

import httpx
import pytest
from tests.support.scryfall_double import ScryfallDouble

from mtgvault.adapters.resilience import CircuitBreaker
from mtgvault.adapters.scryfall.client import ScryfallClient
from mtgvault.adapters.scryfall.provider import ScryfallCardProvider
from mtgvault.domain.errors import NotFound, RateLimited, UpstreamUnavailable

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


def test_search_maps_a_real_list_response(double: ScryfallDouble) -> None:
    page = provider(double).search("lightning bolt", 1)
    assert [c.name for c in page.items] == [
        "Emeritus of Conflict // Lightning Bolt",
        "Lightning Bolt",
    ]
    assert page.total == 2
    assert page.has_more is False
    plain = page.items[1]
    assert plain.image_normal is not None
    assert plain.image_normal.startswith("https://cards.scryfall.io/")
    assert plain.prices.usd is not None
    assert "foil" in plain.finishes


def test_no_matches_is_an_empty_page_not_an_error(double: ScryfallDouble) -> None:
    page = provider(double).search("zzzqqq", 1)
    assert page.items == ()
    assert page.total == 0


def test_get_maps_transform_and_split_layouts(double: ScryfallDouble) -> None:
    ids = {
        c["layout"]: c["id"]
        for c in double._cards.values()
        if c["layout"] in ("transform", "split")
    }
    p = provider(double)
    transform = p.get(UUID(ids["transform"]))
    assert transform.name == "Delver of Secrets // Insectile Aberration"
    assert len(transform.faces) == 2
    assert transform.image_normal is not None
    assert transform.faces[0].image_normal is not None
    assert transform.mana_cost is not None
    assert "{U}" in transform.mana_cost
    split = p.get(UUID(ids["split"]))
    assert split.name == "Fire // Ice"
    assert len(split.faces) == 2
    assert split.colors


def test_a_card_without_prices_has_none_not_zero(double: ScryfallDouble) -> None:
    card_id = next(c["id"] for c in double._cards.values() if c["finishes"] == ["foil"])
    card = provider(double).get(UUID(card_id))
    assert card.finishes == ("foil",)
    assert card.prices.usd is None
    assert card.prices.usd_foil is None


def test_tokens_with_two_faces_are_supported(double: ScryfallDouble) -> None:
    page = provider(double).search("treasure token", 1)
    assert page.items
    assert all(len(c.faces) == 2 for c in page.items)
    assert all(c.oracle_id is not None for c in page.items)


def test_printings_lists_every_printing_of_a_card(double: ScryfallDouble) -> None:
    oracle = UUID(double._cards[next(iter(double._cards))]["oracle_id"])
    page = provider(double).printings(oracle, 1)
    assert len(page.items) == 6
    assert {c.lang for c in page.items} >= {"en"}
    sent = double.requests[-1]["query"]
    assert sent["q"] == f"oracleid:{oracle}"
    assert sent["unique"] == "prints"


def test_unknown_cards_raise_not_found(double: ScryfallDouble) -> None:
    source = provider(double)
    missing = UUID("00000000-0000-4000-8000-000000000000")
    with pytest.raises(NotFound):
        source.get(missing)


def test_requests_carry_the_required_headers_and_are_spaced(double: ScryfallDouble) -> None:
    p = provider(double)
    for term in ("bolt", "bolt token", "zzz"):
        p.search(term, 1)
    log = [r for r in double.requests if r["path"] == "/cards/search"]
    assert {r["user_agent"] for r in log} == {UA}
    assert {r["accept"] for r in log} == {"application/json"}
    assert all(b["at"] - a["at"] >= 0.04 for a, b in pairwise(log))


def test_throttling_and_outages_surface_as_typed_errors(double: ScryfallDouble) -> None:
    p = provider(double, max_attempts=2)
    httpx.post(f"{double.base_url}/__control", json={"fail": 429, "retry_after": 0})
    with pytest.raises(RateLimited):
        p.search("bolt", 1)
    httpx.post(f"{double.base_url}/__control", json={"fail": 503})
    with pytest.raises(UpstreamUnavailable):
        p.search("bolt", 1)
    httpx.post(f"{double.base_url}/__control", json={"fail": 0, "garbage": True})
    with pytest.raises(UpstreamUnavailable):
        p.search("bolt", 1)


def test_the_breaker_opens_during_an_outage_and_heals_afterwards(double: ScryfallDouble) -> None:
    clock = [0.0]
    breaker = CircuitBreaker(
        "scryfall", failure_threshold=2, open_seconds=5, clock=lambda: clock[0]
    )
    p = provider(double, max_attempts=1, breaker=breaker)
    httpx.post(f"{double.base_url}/__control", json={"fail": 503})
    for _ in range(2):
        with pytest.raises(UpstreamUnavailable):
            p.search("bolt", 1)
    served = len(double.requests)
    with pytest.raises(UpstreamUnavailable):
        p.search("bolt", 1)
    assert len(double.requests) == served  # failed fast, no I/O
    httpx.post(f"{double.base_url}/__control", json={"fail": 0})
    clock[0] += 6
    assert p.search("bolt", 1).items
    assert breaker.state == "closed"
