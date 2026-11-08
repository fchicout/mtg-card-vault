"""An in-memory CardDataProvider for service and API tests (no network, no fixtures)."""

import re
from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID, uuid5

from mtgvault.domain.card import Card, LookupResult, Prices, ResultPage
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


_TERM = re.compile(r'(name|t):"([^"]*)"|(set|c|r|cn):(\S+)')


def _matches(card: Card, query: str) -> bool:
    """Understands exactly the terms the application builds (name, set, c, t, r)."""
    for match in _TERM.finditer(query):
        key = match.group(1) or match.group(3)
        value = (match.group(2) if match.group(1) else match.group(4)).lower()
        if key == "name" and value not in card.name.lower():
            return False
        if key == "t" and value not in (card.type_line or "").lower():
            return False
        if key == "set" and card.set_code != value:
            return False
        if key == "cn" and card.collector_number != value:
            return False
        if key == "r" and card.rarity != value:
            return False
        if key == "c" and not set(value.upper()) <= set(card.colors):
            return False
    return True


class FakeCardProvider:
    """Substring search over a list, ``PAGE_SIZE`` per page; can be told to fail."""

    def __init__(self, cards: list[Card] | None = None) -> None:
        self.cards = cards or []
        self.fail = False
        self.search_calls: list[tuple[str, int]] = []
        self.get_calls: list[UUID] = []
        self.printings_calls: list[tuple[UUID, int]] = []
        self.lookup_calls: list[tuple[UUID, ...]] = []

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
        seen: set[UUID | None] = set()
        found = []
        for card in self.cards:
            if _matches(card, query) and card.oracle_id not in seen:
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

    def lookup(self, card_ids: Sequence[UUID]) -> LookupResult:
        self._check()
        self.lookup_calls.append(tuple(card_ids))
        known = {card.id: card for card in self.cards}
        found = tuple(known[i] for i in card_ids if i in known)
        return LookupResult(found, tuple(i for i in card_ids if i not in known))
