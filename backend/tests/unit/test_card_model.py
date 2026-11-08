from dataclasses import FrozenInstanceError
from decimal import Decimal
from uuid import uuid4

import pytest
from tests.support.fake_cards import FakeCardProvider, make_card

from mtgvault.application.ports import CardDataProvider
from mtgvault.domain.card import Page, Prices
from mtgvault.domain.errors import NotFound, UpstreamUnavailable


def test_cards_are_immutable_and_prices_are_decimals() -> None:
    card = make_card()
    with pytest.raises(FrozenInstanceError):
        card.name = "x"  # type: ignore[misc]
    assert isinstance(card.prices.usd, Decimal)
    assert Prices().usd is None  # a missing price is not zero


def test_page_carries_its_position() -> None:
    page = Page(items=(1, 2), page=1, has_more=True, total=5)
    assert (page.page, page.has_more, page.total) == (1, True, 5)


def test_the_fake_satisfies_the_port_and_behaves_like_a_provider() -> None:
    cards = [
        make_card("Lightning Bolt"),
        make_card("Lightning Bolt", "m10", "146"),
        make_card("Giant Growth"),
    ]
    provider: CardDataProvider = FakeCardProvider(cards)
    found = provider.search('name:"lightning"', 1)
    assert [c.name for c in found.items] == ["Lightning Bolt"]  # unique cards
    assert provider.get(cards[2].id).name == "Giant Growth"
    assert len(provider.printings(cards[0].oracle_id, 1).items) == 2  # type: ignore[arg-type]
    with pytest.raises(NotFound):
        provider.get(uuid4())


def test_the_fake_can_simulate_an_outage() -> None:
    provider = FakeCardProvider([make_card()])
    provider.fail = True
    with pytest.raises(UpstreamUnavailable):
        provider.search("x", 1)
