"""Catalogue use cases: search, card detail and printings (US-012..US-014, UC-10)."""

from uuid import UUID

from mtgvault.application.catalog_query import CatalogFilters, build_query
from mtgvault.application.ports import Cache, CardDataProvider
from mtgvault.domain.card import Card, Page


class CatalogService:
    def __init__(self, provider: CardDataProvider, cache: Cache) -> None:
        self._provider = provider
        self._cache = cache

    def search(self, text: str | None, filters: CatalogFilters, page: int) -> Page[Card]:
        query = build_query(text, filters)  # validates; the provider only sees safe queries
        return self._cache.get_or_load(
            f"search|{page}|{query}", lambda: self._provider.search(query, page)
        )

    def get(self, card_id: UUID) -> Card:
        return self._cache.get_or_load(f"card|{card_id}", lambda: self._provider.get(card_id))

    def printings(self, card_id: UUID, page: int) -> Page[Card]:
        """All printings of the card with this id (the printing itself is just one of them)."""
        card = self.get(card_id)
        oracle_id = card.oracle_id
        if oracle_id is None:
            return Page(items=(card,), page=1, has_more=False, total=1)
        return self._cache.get_or_load(
            f"printings|{oracle_id}|{page}", lambda: self._provider.printings(oracle_id, page)
        )
