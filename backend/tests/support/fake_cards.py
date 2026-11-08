"""An in-memory CardDataProvider for service and API tests (no network, no fixtures)."""

from decimal import Decimal
from uuid import UUID, uuid5

from mtgvault.domain.card import Card, Prices, ResultPage
from mtgvault.domain.errors import NotFound, UpstreamUnavailable

NAMESPACE = UUID("00000000-0000-0000-0000-00000000c0de")
PAGE_SIZE = 3


def make_card(
    name: str = "Lightning Bolt",
    set_code: str = "lea",
    number: str = "161",
    oracle: str | None = None,
    **overrides: object,
) -> Card:
    values: dict[str, object] = {
        "id": uuid5(NAMESPACE, f"{set_code}/{number}/{name}"),
        "oracle_id": uuid5(NAMESPACE, oracle or name),
        "name": name,
        "set_code": set_code,
        "set_name": set_code.upper(),
        "collector_number": number,
        "lang": "en",
        "rarity": "common",
        "layout": "normal",
        "type_line": "Instant",
        "colors": ("R",),
        "finishes": ("nonfoil", "foil"),
        "prices": Prices(usd=Decimal("1.50")),
    }
    values.update(overrides)
    return Card(**values)  # type: ignore[arg-type]


class FakeCardProvider:
    """Substring search over a list, ``PAGE_SIZE`` per page; can be told to fail."""

    def __init__(self, cards: list[Card] | None = None) -> None:
        self.cards = cards or []
        self.fail = False
        self.search_calls: list[tuple[str, int]] = []
        self.get_calls: list[UUID] = []
        self.printings_calls: list[tuple[UUID, int]] = []

    def _check(self) -> None:
        if self.fail:
            raise UpstreamUnavailable("down")

    def _page(self, found: list[Card], page: int) -> ResultPage[Card]:
        start = (page - 1) * PAGE_SIZE
        chunk = found[start : start + PAGE_SIZE]
        return ResultPage(tuple(chunk), page, start + PAGE_SIZE < len(found), len(found))

    def search(self, query: str, page: int) -> ResultPage[Card]:
        self._check()
        self.search_calls.append((query, page))
        needle = query.lower()
        seen: set[UUID | None] = set()
        found = []
        for card in self.cards:
            if needle in card.name.lower() and card.oracle_id not in seen:
                seen.add(card.oracle_id)
                found.append(card)
        return self._page(found, page)

    def get(self, card_id: UUID) -> Card:
        self._check()
        self.get_calls.append(card_id)
        for card in self.cards:
            if card.id == card_id:
                return card
        raise NotFound("No such card.")

    def printings(self, oracle_id: UUID, page: int) -> ResultPage[Card]:
        self._check()
        self.printings_calls.append((oracle_id, page))
        return self._page([c for c in self.cards if c.oracle_id == oracle_id], page)
